"""Integration checks run only against a disposable restored database."""
import asyncio
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from starlette.requests import Request

stage=Path(sys.argv[1]);database=sys.argv[2]
if database!='rhisseth_hex_metadata_check':raise SystemExit('Disposable database required')
os.environ['DB_NAME']=database
sys.path.insert(0,str(stage/'app/backend'))
from db import connect
from main import hexes, update, rename_owned_territory, assign_territory, export_hexes
from game_start import start, start_options
from fastapi import HTTPException

def request(payload,user):
    body=json.dumps(payload).encode()
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    result=Request({'type':'http','method':'PUT','headers':[]},receive=receive)
    result.state.user=user
    return result

async def checks():
    rows=hexes();assert len(rows)==465
    assert all('Пресная вода' not in row for row in rows)
    with connect() as conn:
        role=conn.execute("SELECT role_id FROM roles WHERE role_alias='user'").fetchone()[0]
        user=conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s) RETURNING user_id',('hex-integration-player','unused','hex-integration@example.invalid',role)).fetchone()[0]
    player={'user_id':user,'role_alias':'user'}
    admin={'user_id':user,'role_alias':'admin'}
    options=start_options(request({},player));assert options['options']
    result=await start(request({'name':'Тестовая барония','cells':options['options'][0]['cells']},player))
    assert result['title']=='Барон'
    try:await start(request({},player))
    except HTTPException as error:assert error.status_code==409
    else:raise AssertionError('Duplicate start accepted')
    q,r=result['cells'][0]
    await rename_owned_territory(q,r,request({'Название территории':'Имя владельца'},player))
    assert all(row['Название территории']=='Имя владельца' for row in hexes() if row.get('ID территории') and row.get('Владелец')==str(user))
    try:await rename_owned_territory(q,r,request({'Название территории':'Чужое имя'},{'user_id':user+999,'role_alias':'user'}))
    except HTTPException as error:assert error.status_code==403
    else:raise AssertionError('Foreign territory rename accepted')
    saved=await update(q,r,request({'Название':'Географическое имя','Состав ландшафта':'[{"name":"Лес","percent":70},{"name":"Река","percent":30}]'},admin))
    assert saved['row']['Тип местности']=='Лес / Река'
    assert saved['row']['Название территории']=='Имя владельца'
    await update(q,r,request({'Остров':'Да','Доля суши, %':'100','Категория':'Побережье'},admin))
    territory=await assign_territory(request({'name':'Компьютерная барония','rules':'Нейтральные жители','cells':[[0,0],[1,0]]},admin))
    assert territory['kind']=='Баронство'
    assert len(export_hexes().body)>1000
    print('Integration: 465 cells; retired field absent; selected start and repeat rejection; owner rename across barony; foreign owner denied; geographic names independent; fractional terrain; island category; AI connected assignment; CSV export: PASS')

asyncio.run(checks())
