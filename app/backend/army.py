"""Player armies and administrator-maintained military unit catalogue."""
import json
import random
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from db import connect

router = APIRouter()
FIRST_NAMES = ('Альрик','Борислав','Велемир','Годвин','Драгомир','Казимир','Ратмир','Святозар')
SURNAMES = ('Северный','Железная Рука','Храбрый','Серый Волк','из Речной Долины','Непреклонный')
UNIT_FIELDS = ('name','troop_type','defense','attack','attack_range','speed','description','image_path','price','building','note','active')

async def body(request):
    raw=await request.body()
    if len(raw)>16000: raise HTTPException(413,'Слишком большой запрос')
    try: data=json.loads(raw)
    except ValueError: raise HTTPException(400,'Ожидается JSON')
    if not isinstance(data,dict): raise HTTPException(400,'Ожидается объект')
    return data

def catalogue(conn, active_only=True):
    where=' WHERE active' if active_only else ''
    rows=conn.execute(f'SELECT id,{",".join(UNIT_FIELDS)} FROM unit_catalog{where} ORDER BY id').fetchall()
    return [dict(zip(('id',*UNIT_FIELDS),row)) for row in rows]

def armies(conn,user_id):
    generals=[]
    for row in conn.execute('SELECT id,name,icon FROM player_generals WHERE user_id=%s ORDER BY id',(user_id,)).fetchall():
        units=conn.execute('''SELECT pgu.id,uc.id,uc.name,uc.troop_type,uc.defense,uc.attack,uc.attack_range,uc.speed,uc.image_path,pgu.slot
            FROM player_general_units pgu JOIN unit_catalog uc ON uc.id=pgu.unit_id
            WHERE pgu.general_id=%s ORDER BY pgu.slot''',(row[0],)).fetchall()
        generals.append({'id':row[0],'name':row[1],'icon':row[2],'units':[dict(zip(('assignment_id','id','name','troop_type','defense','attack','attack_range','speed','image_path','slot'),unit)) for unit in units]})
    return generals

@router.get('/api/cabinet/army')
def player_army(request: Request):
    with connect() as conn: return {'generals':armies(conn,request.state.user['user_id']),'catalogue':catalogue(conn)}

@router.post('/api/cabinet/army/generals')
def hire_general(request: Request):
    user_id=request.state.user['user_id']
    with connect() as conn:
        if conn.execute('SELECT count(*) FROM player_generals WHERE user_id=%s',(user_id,)).fetchone()[0]>=10: raise HTTPException(409,'Допускается не более 10 генералов')
        name=f'{random.choice(FIRST_NAMES)} {random.choice(SURNAMES)}'
        icon=f'general/gen-0{1+random.randrange(2)}.webp'
        row=conn.execute('INSERT INTO player_generals(user_id,name,icon) VALUES (%s,%s,%s) RETURNING id,name,icon',(user_id,name,icon)).fetchone()
    return {'hired':True,'general':dict(zip(('id','name','icon'),row))}

@router.delete('/api/cabinet/army/generals/{general_id}')
def dismiss_general(general_id: int, request: Request):
    with connect() as conn:
        row=conn.execute('DELETE FROM player_generals WHERE id=%s AND user_id=%s RETURNING id',(general_id,request.state.user['user_id'])).fetchone()
        if not row: raise HTTPException(404,'Генерал не найден')
    return {'dismissed':True}

@router.post('/api/cabinet/army/generals/{general_id}/units')
async def hire_unit(general_id: int, request: Request):
    data=await body(request)
    if set(data)!={'unit_id'} or type(data['unit_id']) is not int: raise HTTPException(400,'Выберите военного юнита')
    with connect() as conn:
        general=conn.execute('SELECT id FROM player_generals WHERE id=%s AND user_id=%s FOR UPDATE',(general_id,request.state.user['user_id'])).fetchone()
        if not general: raise HTTPException(404,'Генерал не найден')
        if not conn.execute('SELECT 1 FROM unit_catalog WHERE id=%s AND active',(data['unit_id'],)).fetchone(): raise HTTPException(404,'Военный юнит недоступен')
        used={row[0] for row in conn.execute('SELECT slot FROM player_general_units WHERE general_id=%s',(general_id,)).fetchall()}
        slot=next((value for value in range(1,6) if value not in used),None)
        if slot is None: raise HTTPException(409,'В армии уже пять юнитов')
        conn.execute('INSERT INTO player_general_units(general_id,unit_id,slot) VALUES (%s,%s,%s)',(general_id,data['unit_id'],slot))
    return {'hired':True,'slot':slot}

@router.delete('/api/cabinet/army/generals/{general_id}/units/{assignment_id}')
def dismiss_unit(general_id: int, assignment_id: int, request: Request):
    with connect() as conn:
        row=conn.execute('''DELETE FROM player_general_units pgu USING player_generals pg
            WHERE pgu.id=%s AND pgu.general_id=%s AND pg.id=pgu.general_id AND pg.user_id=%s RETURNING pgu.id''',(assignment_id,general_id,request.state.user['user_id'])).fetchone()
        if not row: raise HTTPException(404,'Юнит в вашей армии не найден')
    return {'dismissed':True}

@router.get('/api/game/armies')
def game_armies(request: Request):
    with connect() as conn: return {'generals':armies(conn,request.state.user['user_id'])}

@router.get('/admin/units')
def units_page(): return FileResponse(Path(__file__).resolve().parents[1]/'frontend/units-admin.html')

@router.get('/api/admin/units')
def admin_units():
    with connect() as conn: return {'units':catalogue(conn,False)}

@router.patch('/api/admin/units/{unit_id}')
async def edit_unit(unit_id: int, request: Request):
    data=await body(request)
    if set(data)!=set(UNIT_FIELDS): raise HTTPException(400,'Передайте все поля юнита')
    for key in ('name','troop_type','description','image_path','price','building','note'):
        if not isinstance(data[key],str) or len(data[key])>4000: raise HTTPException(400,f'Некорректное поле: {key}')
    for key in ('defense','attack','attack_range','speed'):
        if type(data[key]) is not int or not 0<=data[key]<=100: raise HTTPException(400,f'{key}: число 0–100')
    if type(data['active']) is not bool or not data['name'].strip() or not data['troop_type'].strip(): raise HTTPException(400,'Заполните название, тип и активность')
    if not data['image_path'].startswith('units/') or not data['image_path'].endswith('.webp'): raise HTTPException(400,'Изображение должно находиться в units/*.webp')
    values=[data[field].strip() if isinstance(data[field],str) else data[field] for field in UNIT_FIELDS]
    with connect() as conn:
        row=conn.execute(f'''UPDATE unit_catalog SET {','.join(f'{field}=%s' for field in UNIT_FIELDS)},updated_at=now() WHERE id=%s RETURNING id''',(*values,unit_id)).fetchone()
        if not row: raise HTTPException(404,'Юнит не найден')
    return {'saved':True}
