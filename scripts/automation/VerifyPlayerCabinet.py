# Release review 2026-09-18 (0.0.2): Real PostgreSQL tests run exclusively against the disposable restored database.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Real PostgreSQL tests run exclusively against the disposable restored database."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
import bcrypt
from starlette.requests import Request

stage=Path(sys.argv[1]);database=sys.argv[2]
if database!='rhisseth_player_onboarding_check':raise SystemExit('Disposable database required')
os.environ.update(DB_NAME=database,DB_HOST='127.0.0.1',DB_PASSWORD_FILE='/opt/rhisseth/secrets/db-password.txt')
sys.path.insert(0,str(stage/'app/backend'))
from db import connect
from game_start import start, candidates, free_cells
from player_cabinet import cabinet,crest,abandon,account,rename
from site_auth import verify_password
from fastapi import HTTPException
from psycopg.types.json import Jsonb

def request(data,user):
    body=json.dumps(data).encode()
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    result=Request({'type':'http','method':'POST','headers':[]},receive=receive)
    result.state.user=user;return result

async def checks():
    suffix=uuid.uuid4().hex[:12]
    password='synthetic-test-password'
    with connect() as conn:
        role=conn.execute("SELECT role_id FROM roles WHERE role_alias='user'").fetchone()[0]
        user_id=conn.execute('INSERT INTO users(user_login,user_email,user_pass,role_id) VALUES (%s,%s,%s,%s) RETURNING user_id',('cabinet-'+suffix,'cabinet-'+suffix+'@example.invalid',bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=4)).decode(),role)).fetchone()[0]
        other=conn.execute('INSERT INTO users(user_login,user_email,user_pass,role_id) VALUES (%s,%s,%s,%s) RETURNING user_id',('other-'+suffix,'other-'+suffix+'@example.invalid','unused',role)).fetchone()[0]
        choices=candidates(conn);assert choices
        cells=choices[0]
        for q,r in cells:
            conn.execute('UPDATE hexes SET data=data || %s WHERE q=%s AND r=%s',(Jsonb({'Название территории':'Existing geography','Плодородие':'0'}),q,r))
    user={'user_id':user_id,'role_alias':'user'}
    await start(request({'name':'Test barony','cells':[list(c) for c in cells],'crest':'gerb_1.png','color':'#b51f24','agreement':True},user))
    result=cabinet(request({},user));barony_id=result['barony']['id']
    assert result['barony']['statistics']['hex_count']==len(cells)
    assert result['barony']['statistics']['ratings']['Плодородие']['mean']==0
    assert all(h['Название территории']=='Existing geography' for h in result['barony']['hexes'])
    await crest(request({'barony_id':barony_id,'crest':'gerb_2.png','color':'#2355aa'},user))
    assert all(h['Герб баронии']=='gerb_2.png' for h in cabinet(request({},user))['barony']['hexes'])
    await rename(request({'barony_id':barony_id,'name':'Renamed barony','expected_name':'Test barony'},user))
    renamed=cabinet(request({},user))['barony']
    assert renamed['name']=='Renamed barony'
    assert all(h['Название баронии']=='Renamed barony' and h['Название территории']=='Existing geography' for h in renamed['hexes'])
    try:await rename(request({'barony_id':barony_id,'name':'Stale','expected_name':'Test barony'},user))
    except HTTPException as error:assert error.status_code==409
    else:raise AssertionError('Stale rename accepted')
    try:await abandon(request({'barony_id':barony_id,'confirmation':'wrong','confirmed':True},user))
    except HTTPException as error:assert error.status_code==400
    else:raise AssertionError('Invalid confirmation accepted')
    try:await abandon(request({'barony_id':barony_id,'confirmation':'Test barony','confirmed':True},{'user_id':other}))
    except HTTPException as error:assert error.status_code==409
    else:raise AssertionError('Another player released a barony')
    with connect() as conn:
        assert not set(cells)&free_cells(conn)
        foreign=next(iter(free_cells(conn)))
        conn.execute('UPDATE hexes SET data=data || %s WHERE q=%s AND r=%s',(Jsonb({'Тип владельца':'Игрок','Владелец':str(other),'ID территории':str(barony_id)}),*foreign))
        foreign_before=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',foreign).fetchone()[0]
    released=await abandon(request({'barony_id':barony_id,'confirmation':'Renamed barony','confirmed':True},user))
    assert released['released_hexes']==len(cells)
    assert cabinet(request({},user))['barony'] is None
    with connect() as conn:
        assert set(cells)<=free_cells(conn)
        assert conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',foreign).fetchone()[0]==foreign_before
        for cell in cells:
            row=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',cell).fetchone()[0]
            assert row['Название территории']=='Existing geography' and row['Плодородие']=='0'
            assert all(key not in row for key in ('Цвет баронии','Герб баронии','Название баронии','ID территории'))
        assert conn.execute('SELECT count(*) FROM player_barony_audit WHERE user_id=%s',(user_id,)).fetchone()[0]==3
    old=result['account'];new_password='synthetic-new-password'
    changed=await account(request({'login':'updated-'+suffix,'email':'updated-'+suffix+'@example.invalid','current_password':password,'password':new_password,'password_confirm':new_password,'expected':old},user))
    assert changed.status_code==200
    with connect() as conn:
        row=conn.execute('SELECT user_pass,role_id FROM users WHERE user_id=%s',(user_id,)).fetchone()
        assert verify_password(new_password,row[0]) and row[1]==role
    print('PASS: restored PostgreSQL; own statistics; zero values; crest; mandatory confirmation; foreign owner protection; neutral free cells; preserved geography; audit; account password and role')

asyncio.run(checks())
