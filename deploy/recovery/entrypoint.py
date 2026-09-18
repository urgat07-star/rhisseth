"""Translate a local Compose secret into ephemeral controller credentials."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ALLOWED = {'list','preflight','restore','validate','reboot-test','external-check'}

def prepare(config, directory):
    target = config['target']
    backup = config['backup']
    # Do this before SSH, including host-key discovery: internal targets require runner.
    for address in (target['ip'], backup['ip']):
        if not ipaddress.ip_address(address).is_global:
            raise ValueError('Internal infrastructure requires STU-AUTOMATION-01; Docker workstation mode accepts public IPs only')
    if not target['username'] or not target['password'] or target['password']=='FILL_LOCALLY':
        raise ValueError('Fill target SSH credentials in recovery.local.json')
    for row in (target,backup):
        if not 1 <= int(row.get('port',22)) <= 65535:
            raise ValueError('Invalid SSH port')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    credentials = directory/'target.json'
    credentials.write_text(json.dumps({'uri':'ssh://'+target['ip'],'username':target['username'],'password':target['password']}))
    credentials.chmod(0o600)
    instance = dict(config['instance'])
    instance['test_ip'] = target['ip']
    settings = {
        'enforce_runner':False,
        'targets': {
            'source':{'host':'62.113.109.168'},
            'storage':{'host':backup['ip'],'port':int(backup.get('port',22)), 'automation_identity_file':str(directory/'storage-key')},
            'test':{'host':target['ip'],'port':int(target.get('port',22)), 'username':target['username'],'credentials_file':str(credentials)}
        },
        'instance':instance
    }
    controller = directory/'controller.json'
    controller.write_text(json.dumps(settings))
    controller.chmod(0o600)
    return controller

def main():
    os.umask(0o077)
    args = sys.argv[1:] or ['preflight']
    if args[0] not in ALLOWED or len(args)>2 or (len(args)==2 and args[0]!='restore'):
        print('Allowed: list, preflight, restore [approved-ref], validate, reboot-test, external-check',file=sys.stderr)
        return 2
    directory = Path('/run/controller')
    try:
        config = json.loads(Path('/run/secrets/recovery_config').read_text(encoding='utf-8-sig'))
        controller = prepare(config,directory)
        shutil.copyfile('/run/secrets/storage_key',directory/'storage-key')
        (directory/'storage-key').chmod(0o600)
        shutil.copyfile('/run/secrets/known_hosts','/root/.ssh/known_hosts')
        return subprocess.run([sys.executable,'/app/scripts/automation/Run-RhissethRecovery.py',*args,'--controller-config',str(controller)]).returncode
    except ValueError as error:
        # Only our fixed validation messages may be shown; JSON parsing includes no values.
        print(str(error) if type(error) is ValueError else 'Invalid JSON configuration',file=sys.stderr)
        return 2
    except Exception:
        print('Recovery initialization failed; check config and mounted files (secret details suppressed)',file=sys.stderr)
        return 2
    finally:
        for name in ('target.json','controller.json','storage-key'):
            (directory/name).unlink(missing_ok=True)

if __name__=='__main__':
    raise SystemExit(main())
