#!/usr/bin/python3
"""Read only backup filenames and sizes on the external Rhisseth VDS via runner."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

os.umask(0o077)
root=Path('/home/avalon/rhisseth.ru')
now=dt.datetime.now(dt.timezone.utc)
directory=root/'reports/automation-logs'/now.strftime('%Y-%m-%d')
directory.mkdir(parents=True,exist_ok=True)
log=directory/(now.strftime('%Y%m%d-%H%M%S')+'-vds-backup-inventory.md')
log.write_text(f'''# Rhisseth VDS backup inventory

UTC: {now.isoformat()}
Moscow: {now.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
Task: batell-v0.3-start-zones; operator/controller: Codex
Runner: STU-AUTOMATION-01 / 10.210.52.128
Approved target: 62.113.109.168 /opt/rhisseth/backups; read-only inventory
Passbolt resource ID: da44a388-e458-4379-ab4c-c204696804b2
Preflight: audit writable; runner host and source credential verified below
Change/reboot: none / none
''',encoding='utf-8')


def audit(message):
    with log.open('a',encoding='utf-8') as stream:
        stream.write(message+'\n');stream.flush();os.fsync(stream.fileno())


try:
    if socket.gethostname().lower().split('.')[0]!='stu-automation-01':
        raise RuntimeError('Must execute on runner')
    phrase=Path('/etc/avalon-runner/passbolt/passphrase').read_text().rstrip('\r\n')
    env={**os.environ,'USERPASSWORD':phrase,'userPassword':phrase}
    credential=subprocess.run(['passbolt','--config','/etc/avalon-runner/passbolt/passbolt-cli.yaml',
        'get','resource','--id','da44a388-e458-4379-ab4c-c204696804b2','--json'],
        env=env,capture_output=True,text=True,timeout=60)
    audit(f'Passbolt lookup: exit_code={credential.returncode}; raw output suppressed')
    if credential.returncode: raise RuntimeError('Source credential unavailable')
    row=json.loads(credential.stdout)
    if urlsplit(row.get('uri','')).hostname!='62.113.109.168' or not re.fullmatch(r'[a-zA-Z0-9_.-]+',row.get('username','')):
        raise RuntimeError('Source credential target mismatch')
    password=row.get('password','').rstrip('\r\n')
    if not password: raise RuntimeError('Source credential password missing')
    env={**os.environ,'SSHPASS':password}
    base=['sshpass','-e','ssh','-o','StrictHostKeyChecking=yes','-o','PubkeyAuthentication=no',
          '-o','ConnectTimeout=12',f"{row['username']}@62.113.109.168"]
    command="find /opt/rhisseth/backups -maxdepth 1 -type f -printf '%f %s %TY-%Tm-%TdT%TH:%TM:%TS%TZ\\n'"
    result=subprocess.run([*base,command],env=env,capture_output=True,text=True,timeout=45)
    audit(f'VDS read-only inventory: exit_code={result.returncode}; stderr suppressed')
    if result.returncode: raise RuntimeError('VDS inventory failed')
    lines=[]
    for line in result.stdout.splitlines():
        parts=line.split()
        if len(parts)!=3 or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[0]) or not parts[1].isdigit():
            continue
        lines.append({'name':parts[0],'bytes':int(parts[1]),'modified':parts[2]})
    if len(sys.argv)>1 and sys.argv[1]=='--counts':
        counts=[]
        for item in lines:
            name=item['name']
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.dump',name): continue
            restored=subprocess.run([*base,'pg_restore --data-only --table=player_baronies --file=- /opt/rhisseth/backups/'+name],
                env=env,capture_output=True,text=True,timeout=45)
            audit(f'Inspect player_baronies in {name}: exit_code={restored.returncode}; raw data suppressed')
            if restored.returncode: continue
            inside=False;count=0
            for line in restored.stdout.splitlines():
                if line.startswith('COPY public.player_baronies '): inside=True;continue
                if inside and line=='\\.': inside=False;continue
                if inside: count+=1
            counts.append({'name':name,'player_baronies':count})
        print(json.dumps(counts,ensure_ascii=False))
        audit(f'Validation: {len(counts)} dump counts inspected; exit_code=0; no change or reboot')
    elif len(sys.argv)>1 and sys.argv[1]=='--zones':
        def read_table(name,table):
            restored=subprocess.run([*base,'pg_restore --data-only --table='+table+' --file=- /opt/rhisseth/backups/'+name],
                env=env,capture_output=True,text=True,timeout=45)
            audit(f'Inspect {table} in {name}: exit_code={restored.returncode}; raw data suppressed')
            if restored.returncode: raise RuntimeError('Backup table inspection failed')
            columns=None; rows=[]
            for line in restored.stdout.splitlines():
                if line.startswith('COPY public.'+table+' ('):
                    columns=line.split('(',1)[1].split(')',1)[0].split(', ')
                elif columns and line=='\\.':
                    columns=None
                elif columns:
                    values=line.split('\t')
                    rows.append(dict(zip(columns,values)))
            return rows
        snapshots=[]
        for item in sorted(lines,key=lambda row:row['modified']):
            name=item['name']
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.dump',name) or not name.startswith('20260922') and not name.startswith('rhisseth-before-'):
                continue
            baronies=read_table(name,'player_baronies')
            if not baronies: continue
            owned={}
            for hex_row in read_table(name,'hexes'):
                raw=hex_row.get('data','')
                try:
                    data=json.loads(raw.replace('\\\\','\\'))
                except (ValueError,TypeError):
                    continue
                if data.get('Тип владельца')!='Игрок': continue
                owner=str(data.get('Владелец',''))
                owned.setdefault(owner,[]).append([int(hex_row['q']),int(hex_row['r'])])
            summary=[]
            for barony in baronies:
                user_id=barony.get('user_id','')
                cells=sorted(owned.get(user_id,[]))
                summary.append({'barony_id':int(barony['id']),'user_id':int(user_id),'cells':cells})
            snapshots.append({'name':name,'baronies':summary})
        print(json.dumps(snapshots,ensure_ascii=False))
        audit(f'Validation: {len(snapshots)} sanitized snapshots; exit_code=0; no change or reboot')
    else:
        print(json.dumps(lines,ensure_ascii=False))
        audit(f'Validation: {len(lines)} sanitized file entries; exit_code=0; no change or reboot')
except Exception as error:
    audit(f'Failure: {type(error).__name__}; exit_code=1; no change or reboot')
    raise SystemExit('VDS backup inventory failed; see sanitized runner log')
