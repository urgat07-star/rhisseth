#!/usr/bin/python3
"""Validate reviewed v0.3 SQL on a restored temporary VDS database."""
import datetime as dt
import asyncio
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psycopg

ROOT=Path('/opt/rhisseth')
ARCHIVE=ROOT/'temp/batell-v03-migrations.tar.gz'
now=dt.datetime.now(dt.timezone.utc)
stamp=now.strftime('%Y%m%d%H%M%S')
db_name='rhisseth_v03_test_'+stamp
backup_dir=ROOT/'backups'/('v03-validation-'+stamp)
log_dir=ROOT/'reports/automation-logs'/now.strftime('%Y-%m-%d')
log_dir.mkdir(parents=True,exist_ok=True)
log=log_dir/(stamp+'-v03-sql-validation.md')
log.write_text(f'''# v0.3 SQL validation

- UTC: {now.isoformat()}
- Europe/Moscow: {now.astimezone(ZoneInfo('Europe/Moscow')).isoformat()}
- Task: batell-v0.3; operator/controller: Codex
- Runner: STU-AUTOMATION-01 / 10.210.52.128
- Target: VDS 62.113.109.168; production read-only backup and temporary validation database {db_name}
- Passbolt resource: da44a388-e458-4379-ab4c-c204696804b2
- Reboot: none

''',encoding='utf-8')


def audit(message):
    with log.open('a',encoding='utf-8') as stream:
        stream.write(message+'\n');stream.flush();os.fsync(stream.fileno())
    print(message,flush=True)


def run(args,input_bytes=None):
    result=subprocess.run(args,input=input_bytes,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    audit(f'{args[0]}: exit_code={result.returncode}; output suppressed')
    if result.returncode:raise RuntimeError(f'{args[0]} failed')
    return result


created=False
try:
    if os.geteuid()!=0 or not ARCHIVE.is_file() or ARCHIVE.stat().st_size==0:
        raise RuntimeError('Preflight failed: root or reviewed archive missing')
    if not re.fullmatch(r'rhisseth_v03_test_\d{14}',db_name):raise RuntimeError('Invalid temporary database name')
    scripts=[];backend={}
    with tarfile.open(ARCHIVE,'r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile():
                raise RuntimeError('Unexpected archive path')
            content=tar.extractfile(member).read()
            if re.fullmatch(r'data/migrations/\d{3}_[A-Za-z0-9_-]+\.sql',member.name):
                scripts.append((Path(member.name).name,content.decode('utf-8')))
            elif re.fullmatch(r'app/backend/[A-Za-z0-9_]+\.py',member.name):
                backend[Path(member.name).name]=content
            else:
                raise RuntimeError('Unexpected archive path')
    if len(scripts)!=33 or len({name for name,_ in scripts})!=len(scripts) or not {'admin_game.py','db.py','hex_rules.py','army.py','battle.py','movement.py','game_clock.py','battle_rules.py'}<=set(backend):
        raise RuntimeError('Migration archive is incomplete or duplicated')
    backup_dir.mkdir(mode=0o700)
    dump=backup_dir/'rhisseth.dump'
    audit(f'Preflight: archive has {len(scripts)} migration files; backup directory ready')
    with dump.open('wb') as stream:
        result=subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-d','rhisseth'],
                              stdout=stream,stderr=subprocess.PIPE,timeout=300)
    audit(f'pg_dump: exit_code={result.returncode}; output suppressed')
    if result.returncode:raise RuntimeError('pg_dump failed')
    dump.chmod(0o600)
    if dump.stat().st_size<1024:raise RuntimeError('Backup size invalid')
    run(['pg_restore','--list',str(dump)])
    audit(f'Backup verified: {dump}; bytes={dump.stat().st_size}')
    run(['runuser','-u','postgres','--','createdb','--owner=rhisseth',db_name]);created=True
    run(['runuser','-u','postgres','--','pg_restore','--no-owner','--no-acl','--role=rhisseth','-d',db_name],dump.read_bytes())
    password=Path('/opt/rhisseth/secrets/db-password.txt').read_text().strip()
    with psycopg.connect(host='127.0.0.1',dbname=db_name,user='rhisseth',password=password,connect_timeout=10) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        applied=[]
        for name,sql in sorted(scripts):
            if conn.execute('SELECT 1 FROM schema_migrations WHERE name=%s',(name,)).fetchone():continue
            conn.execute(sql)
            conn.execute('INSERT INTO schema_migrations(name) VALUES (%s)',(name,))
            applied.append(name)
        baronies=conn.execute('SELECT count(*) FROM player_baronies').fetchone()[0]
        zones=conn.execute('SELECT count(*) FROM barony_start_hexes').fetchone()[0]
        balance=conn.execute('SELECT count(*) FROM raid_balance').fetchone()[0]
        battles=conn.execute('SELECT count(*) FROM game_battles').fetchone()[0]
        with tempfile.TemporaryDirectory(prefix='rhisseth-v03-code-') as work:
            for name,content in backend.items():
                (Path(work)/name).write_bytes(content)
            sys.path.insert(0,work)
            import admin_game
            preview=admin_game._inspect(conn)
            if not preview['ready'] or preview['baronies']!=baronies or preview['recorded_start_hexes']!=zones:
                raise RuntimeError(f'Reset preview blocked: missing={len(preview["missing_start_zones"])}; conflicts={len(preview["conflicts"])}; unknown_owners={len(preview["unknown_owners"])}')
            admin_game.connect=lambda:contextlib.nullcontext(conn)
            actor=conn.execute('SELECT user_id FROM users ORDER BY user_id LIMIT 1').fetchone()[0]
            class Request:
                state=SimpleNamespace(user={'role_alias':'admin','user_id':actor})
                payload={'confirmation':'СБРОСИТЬ ТЕСТ','expected_turn':preview['turn']}
                async def json(self):
                    return self.payload
                async def body(self):
                    return json.dumps(self.payload).encode('utf-8')
            reset=asyncio.run(admin_game.reset_baronies(Request()))
            after=admin_game._inspect(conn)
            gold=conn.execute('''SELECT count(*) FROM player_baronies b JOIN game_wallets w ON w.user_id=b.user_id
                WHERE w.gold=300''').fetchone()[0]
            ownership=conn.execute('''SELECT count(*) FROM hexes WHERE data->>'Тип владельца'='Игрок' ''').fetchone()[0]
            resources=conn.execute('''SELECT count(*) FROM player_baronies b JOIN game_inventory i ON i.user_id=b.user_id
                JOIN game_resources r ON r.code=i.resource_code WHERE i.quantity=r.starting_quantity''').fetchone()[0]
            expected_resources=conn.execute('SELECT count(*) FROM game_resources').fetchone()[0]*baronies
            generals=conn.execute('SELECT count(*) FROM player_generals').fetchone()[0]
            turn=conn.execute('SELECT turn_number FROM game_clock WHERE id=true').fetchone()[0]
            if not(after['ready'] and gold==baronies and ownership==zones and resources==expected_resources
                   and generals==0 and turn==0 and reset['restored_hexes']==zones):
                raise RuntimeError('Full reset invariants failed on restored copy')
            import army
            import battle
            army.connect=lambda:contextlib.nullcontext(conn)
            battle.connect=lambda:contextlib.nullcontext(conn)
            player=conn.execute('SELECT user_id FROM player_baronies ORDER BY id LIMIT 1').fetchone()[0]
            game_request=Request()
            game_request.state=SimpleNamespace(user={'user_id':player})
            hired=army.hire_general(game_request)
            general_id=hired['general']['id']
            unit_id=conn.execute('SELECT id FROM unit_catalog WHERE purchasable AND active ORDER BY id LIMIT 1').fetchone()[0]
            game_request.payload={'unit_id':unit_id}
            asyncio.run(army.hire_unit(general_id,game_request))
            home=conn.execute('SELECT q,r FROM player_generals WHERE id=%s',(general_id,)).fetchone()
            target=None
            for dq,dr in battle.NEIGHBORS:
                cell=(home[0]+dq,home[1]+dr)
                row=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',cell).fetchone()
                if row and row[0].get('Категория')!='Море' and (row[0].get('Тип владельца')!='Игрок' or row[0].get('Владелец')!=str(player)):
                    target=cell;break
            if target is None:raise RuntimeError('No adjacent combat target in reset start zone')
            game_request.payload={'general_id':general_id}
            started=asyncio.run(battle.start_capture_battle(*target,game_request))
            battle_id=started['battle']['id']
            positions=[{'id':unit['id'],'x':unit['x'],'y':unit['y']}
                       for unit in started['units'] if unit['side']=='attacker']
            game_request.payload={'positions':positions}
            deployed=asyncio.run(battle.save_deployment(battle_id,game_request))
            if not deployed['battle']['deployment_locked'] or not deployed['units']:
                raise RuntimeError('Battle deployment did not persist')
            resumed=battle.get_battle(battle_id,game_request)
            if resumed['battle']['id']!=battle_id or len(resumed['units'])!=len(deployed['units']):
                raise RuntimeError('Battle resume failed')
            battle._finish(conn,battle._battle(conn,battle_id,player),'attacker')
            captured=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',target).fetchone()[0]
            if captured.get('Тип владельца')!='Игрок' or captured.get('Владелец')!=str(player):
                raise RuntimeError('Capture settlement did not assign hex to attacker')
            gold_before=conn.execute('SELECT gold FROM game_wallets WHERE user_id=%s',(player,)).fetchone()[0]
            game_request.payload={'general_id':general_id}
            raid=asyncio.run(battle.start_raid_battle(*target,game_request))
            raid_id=raid['battle']['id']
            battle._finish(conn,battle._battle(conn,raid_id,player),'attacker')
            gold_after=conn.execute('SELECT gold FROM game_wallets WHERE user_id=%s',(player,)).fetchone()[0]
            morale=conn.execute('SELECT morale FROM game_hex_morale WHERE q=%s AND r=%s',target).fetchone()
            if gold_after<=gold_before or morale is None or morale[0]>=100:
                raise RuntimeError('Own-hex raid settlement failed')
        conn.rollback()
    audit(f'Validation: SQL transaction succeeded; applied={len(applied)} ({", ".join(applied)}); baronies={baronies}; start_hexes={zones}; raid_levels={balance}; battles={battles}')
    audit(f'Validation: full test reset succeeded on copy; owned_hexes={ownership}; wallets_300={gold}; resource_rows={resources}; generals={generals}; turn={turn}; transaction rolled back')
    audit(f'Validation: paid general/unit hire, combat start, deployment, resume, capture settlement and own-hex raid payout succeeded on copy; battles={battle_id},{raid_id}; transaction rolled back')
    audit('Change/reboot: production database unchanged; temporary database cleanup follows; no reboot')
finally:
    if created:
        result=subprocess.run(['runuser','-u','postgres','--','dropdb',db_name],capture_output=True,text=True,timeout=60)
        audit(f'Temporary database cleanup: exit_code={result.returncode}; target={db_name}')
