#!/usr/bin/python3
"""Two-phase Rhisseth VDS backup migration; runner side."""
import datetime as dt, hashlib, json, os, re, shlex, socket, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path('/home/avalon/rhisseth.ru'); SPOOL=ROOT/'temp/backup-migration'; RID='da44a388-e458-4379-ab4c-c204696804b2'
def run(args,env=None,timeout=3600):
 p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=timeout)
 if p.returncode: raise RuntimeError(f'command exit_code={p.returncode}; output suppressed')
 return p.stdout
def credential():
 phrase=Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n'); env={**os.environ,'USERPASSWORD':phrase,'userPassword':phrase}
 row=json.loads(run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml','get','resource','--id',RID,'--json'],env,60)); return row['username'],row['password'].rstrip('\r\n')
def hashes(top):
 rows=[]
 for path in sorted(top.rglob('*')):
  if path.is_symlink(): raise RuntimeError('symlink in payload')
  if path.is_file() and path.name not in ('manifest.json','verified.json'):
   with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
   rows.append({'relative':path.relative_to(top).as_posix(),'bytes':path.stat().st_size,'sha256':digest})
 return rows
def main():
 if socket.gethostname().lower().split('.')[0]!='stu-automation-01': raise RuntimeError('runner required')
 mode=sys.argv[1] if len(sys.argv)>1 else ''; now=dt.datetime.now(dt.timezone.utc)
 logs=ROOT/'reports/automation-logs'/now.strftime('%Y-%m-%d'); logs.mkdir(parents=True,exist_ok=True); log=logs/(now.strftime('%Y%m%d-%H%M%S')+'-backup-migration-'+mode+'.md')
 log.write_text(f'# Rhisseth backup migration {mode}\n\nUTC: {now.isoformat()}\nMoscow: {now.astimezone(ZoneInfo("Europe/Moscow")).isoformat()}\nRunner: STU-AUTOMATION-01 / 10.210.52.128\nTarget: 62.113.109.168\nPassbolt resource: {RID}\n\n',encoding='utf-8')
 def audit(s):
  with log.open('a',encoding='utf-8') as f: f.write(s+'\n'); f.flush(); os.fsync(f.fileno())
 user,password=credential(); env={**os.environ,'SSHPASS':password}; base=['sshpass','-e','ssh','-o','StrictHostKeyChecking=yes','-o','PubkeyAuthentication=no','-o','ConnectTimeout=15',f'{user}@62.113.109.168']
 if mode=='stage':
  stage=now.strftime('%Y%m%dT%H%M%SZ'); work=SPOOL/stage; work.mkdir(mode=0o700,parents=True)
  code='''import json,os\nfor root,kind in [("/var/backups/rhisseth","archive"),("/opt/rhisseth/backups","old-deploy"),("/opt/rhisseth","rollback")]:\n rows=[]\n for name in os.listdir(root):\n  if kind=="rollback" and not name.startswith("repository.before-deploy-"): continue\n  path=os.path.join(root,name); st=os.lstat(path)\n  if os.path.islink(path) or not (os.path.isfile(path) or os.path.isdir(path)): continue\n  rows.append({"remote":path,"name":name,"kind":kind,"type":"dir" if os.path.isdir(path) else "file","mtime_ns":st.st_mtime_ns})\n for row in sorted(rows,key=lambda x:x["mtime_ns"],reverse=True)[3:]: print(json.dumps(row))'''
  selected=[json.loads(x) for x in run([*base,'python3 -c '+shlex.quote(code)],env,120).splitlines() if x.strip()]; audit(f'Preflight: selected={len(selected)}; VDS unchanged')
  for item in selected:
   target=work/('old-deploy' if item['kind']=='old-deploy' else 'backups'); target.mkdir(exist_ok=True)
   run(['sshpass','-e','scp','-r','-o','StrictHostKeyChecking=yes','-o','PubkeyAuthentication=no',f'{user}@62.113.109.168:{item["remote"]}',str(target/item['name'])],env)
  files=hashes(work); (work/'manifest.json').write_text(json.dumps({'format':1,'stage':stage,'created_utc':now.isoformat(),'keep_newest':3,'selected':selected,'files':files},indent=2)+'\n',encoding='utf-8')
  audit(f'Validation: copied_objects={len(selected)}; files={len(files)}; deleted=false; reboot=false'); print(json.dumps({'stage':stage,'selected':len(selected),'files':len(files),'log':str(log)}))
 elif mode=='cleanup':
  if len(sys.argv)!=3 or not re.fullmatch(r'\d{8}T\d{6}Z',sys.argv[2]): raise RuntimeError('invalid stage')
  work=SPOOL/sys.argv[2]; manifest=json.loads((work/'manifest.json').read_text()); marker=json.loads((work/'verified.json').read_text())
  if marker.get('stage')!=manifest['stage'] or marker.get('verified_files')!=len(manifest['files']) or hashes(work)!=manifest['files']: raise RuntimeError('verification mismatch')
  for item in manifest['selected']:
   path=item['remote']; allowed=re.fullmatch(r'/var/backups/rhisseth/[A-Za-z0-9_.-]+',path) or re.fullmatch(r'/opt/rhisseth/backups/[A-Za-z0-9_.-]+',path) or re.fullmatch(r'/opt/rhisseth/repository\.before-deploy-[A-Za-z0-9_.-]+',path)
   if not allowed: raise RuntimeError('unsafe cleanup path')
   run([*base,('rm -rf -- ' if item['type']=='dir' else 'rm -f -- ')+shlex.quote(path)],env,300); audit('Deleted verified VDS object: '+path)
  audit(f'Validation: deleted={len(manifest["selected"])}; reboot=false'); print(json.dumps({'stage':manifest['stage'],'deleted':len(manifest['selected']),'log':str(log)}))
 elif mode=='maintenance':
  command="""set -eu
before_apt=$(du -s -B1 /var/cache/apt 2>/dev/null | awk '{print $1}')
before_journal=$(journalctl --disk-usage 2>/dev/null || true)
apt-get clean
install -d -m 0755 /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/rhisseth-size.conf
systemctl restart systemd-journald
journalctl --vacuum-size=100M
after_apt=$(du -s -B1 /var/cache/apt 2>/dev/null | awk '{print $1}')
after_journal=$(journalctl --disk-usage 2>/dev/null || true)
df -B1P /
printf 'APT_BEFORE=%s\nAPT_AFTER=%s\nJOURNAL_BEFORE=%s\nJOURNAL_AFTER=%s\n' "$before_apt" "$after_apt" "$before_journal" "$after_journal"
"""
  output=run([*base,'bash -c '+shlex.quote(command)],env,600)
  audit('Approved changes: apt cache cleaned; journald SystemMaxUse=100M configured; journald restarted; vacuum applied')
  audit('Sanitized validation output:\n'+output)
  audit('Validation: exit_code=0; reboot=false')
  print(json.dumps({'maintenance':'complete','output':output,'log':str(log)}))
 else: raise RuntimeError('mode must be stage, cleanup, or maintenance')
if __name__=='__main__':
 try: main()
 except Exception as error: raise SystemExit(f'backup migration failed: {type(error).__name__}: {error}')
