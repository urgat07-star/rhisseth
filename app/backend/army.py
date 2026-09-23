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
UNIT_FIELDS = ('name','troop_type','health','armor','defense','attack','attack_range','speed','initiative','morale','description','image_path','price','building','note','active')
GENERAL_FIELDS = ('name','description','image_path','health','attack','defense','initiative','speed','logistics','skills','experience_per_level','max_level','max_attack_bonus','max_defense_bonus','active')

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
    for row in conn.execute('''SELECT pg.id,pg.name,pg.icon,pg.experience,pg.level,pg.attack_bonus,pg.defense_bonus,
            gc.attack+pg.attack_bonus,gc.defense+pg.defense_bonus
            FROM player_generals pg LEFT JOIN general_catalog gc ON gc.id=pg.catalog_id
            WHERE pg.user_id=%s ORDER BY pg.id''',(user_id,)).fetchall():
        units=conn.execute('''SELECT pgu.id,uc.id,uc.name,uc.troop_type,uc.defense,uc.attack,uc.attack_range,uc.speed,uc.image_path,pgu.slot
            FROM player_general_units pgu JOIN unit_catalog uc ON uc.id=pgu.unit_id
            WHERE pgu.general_id=%s ORDER BY pgu.slot''',(row[0],)).fetchall()
        skills=conn.execute('''SELECT gsc.code,gsc.name,gsc.description,gsc.is_positive,pgs.acquired_level
            FROM player_general_skills pgs JOIN general_skill_catalog gsc ON gsc.id=pgs.skill_id
            WHERE pgs.general_id=%s ORDER BY pgs.acquired_level,gsc.id''',(row[0],)).fetchall()
        generals.append({'id':row[0],'name':row[1],'icon':row[2],'experience':row[3],'level':row[4],
            'attack_bonus':row[5],'defense_bonus':row[6],'attack':row[7],'defense':row[8],
            'skills':[dict(zip(('code','name','description','is_positive','acquired_level'),skill)) for skill in skills],
            'units':[dict(zip(('assignment_id','id','name','troop_type','defense','attack','attack_range','speed','image_path','slot'),unit)) for unit in units]})
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
        template=conn.execute('SELECT id,name,image_path FROM general_catalog WHERE active ORDER BY random() LIMIT 1').fetchone()
        if not template: raise HTTPException(409,'Нет доступных шаблонов генералов')
        row=conn.execute('INSERT INTO player_generals(user_id,name,icon,catalog_id) VALUES (%s,%s,%s,%s) RETURNING id,name,icon',(user_id,name or template[1],template[2],template[0])).fetchone()
    return {'hired':True,'general':dict(zip(('id','name','icon'),row))}

def award_general_victory(conn, general_id, experience_gain=100):
    """Начислить опыт за победу; вызывается транзакцией завершения боя."""
    row=conn.execute('''SELECT pg.experience,pg.level,gc.experience_per_level,gc.max_level,
        gc.max_attack_bonus,gc.max_defense_bonus FROM player_generals pg
        JOIN general_catalog gc ON gc.id=pg.catalog_id WHERE pg.id=%s FOR UPDATE''',(general_id,)).fetchone()
    if not row: raise HTTPException(404,'Генерал не найден')
    experience=row[0]+experience_gain
    level=min(row[3],1+experience//row[2])
    attack_bonus=min(row[4],level-1)
    defense_bonus=min(row[5],level-1)
    conn.execute('UPDATE player_generals SET experience=%s,level=%s,attack_bonus=%s,defense_bonus=%s WHERE id=%s',(experience,level,attack_bonus,defense_bonus,general_id))
    for acquired_level in range(row[1]+1,level+1):
        skill=conn.execute('''SELECT id FROM general_skill_catalog WHERE active AND id NOT IN
            (SELECT skill_id FROM player_general_skills WHERE general_id=%s) ORDER BY random() LIMIT 1''',(general_id,)).fetchone()
        if skill: conn.execute('INSERT INTO player_general_skills(general_id,skill_id,acquired_level) VALUES (%s,%s,%s)',(general_id,skill[0],acquired_level))
    return {'experience':experience,'level':level,'attack_bonus':attack_bonus,'defense_bonus':defense_bonus}

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

@router.get('/admin/generals')
def generals_page(): return FileResponse(Path(__file__).resolve().parents[1]/'frontend/generals-admin.html')

@router.get('/api/admin/generals')
def admin_generals():
    with connect() as conn:
        rows=conn.execute(f'SELECT id,{",".join(GENERAL_FIELDS)} FROM general_catalog ORDER BY id').fetchall()
        return {'generals':[dict(zip(('id',*GENERAL_FIELDS),row)) for row in rows]}

@router.post('/api/admin/generals')
async def create_general(request: Request):
    data=await body(request)
    if set(data)!=set(GENERAL_FIELDS): raise HTTPException(400,'Передайте все поля генерала')
    _validate_general(data)
    with connect() as conn:
        row=conn.execute(f'''INSERT INTO general_catalog ({','.join(GENERAL_FIELDS)}) VALUES ({','.join('%s' for _ in GENERAL_FIELDS)}) RETURNING id''',[data[field].strip() if isinstance(data[field],str) else data[field] for field in GENERAL_FIELDS]).fetchone()
    return {'created':True,'id':row[0]}

def _validate_general(data):
    for key in ('name','description','image_path','skills'):
        if not isinstance(data[key],str) or len(data[key])>4000: raise HTTPException(400,f'Некорректное поле: {key}')
    for key in ('health','attack','defense','initiative','speed','logistics','experience_per_level','max_level','max_attack_bonus','max_defense_bonus'):
        if type(data[key]) is not int or not 0<=data[key]<=10000: raise HTTPException(400,f'{key}: некорректное число')
    if type(data['active']) is not bool or not data['name'].strip(): raise HTTPException(400,'Заполните имя и доступность')
    if not data['image_path'].startswith('general/gen-') or not data['image_path'].endswith('.webp'): raise HTTPException(400,'Изображение должно находиться в general/*.webp')

@router.patch('/api/admin/generals/{general_id}')
async def edit_general(general_id: int, request: Request):
    data=await body(request)
    if set(data)!=set(GENERAL_FIELDS): raise HTTPException(400,'Передайте все поля генерала')
    _validate_general(data)
    values=[data[field].strip() if isinstance(data[field],str) else data[field] for field in GENERAL_FIELDS]
    with connect() as conn:
        if not conn.execute(f'''UPDATE general_catalog SET {','.join(f'{field}=%s' for field in GENERAL_FIELDS)},updated_at=now() WHERE id=%s RETURNING id''',(*values,general_id)).fetchone(): raise HTTPException(404,'Генерал не найден')
    return {'saved':True}

@router.delete('/api/admin/generals/{general_id}')
def delete_general(general_id: int):
    with connect() as conn:
        try:
            if not conn.execute('DELETE FROM general_catalog WHERE id=%s RETURNING id',(general_id,)).fetchone(): raise HTTPException(404,'Генерал не найден')
        except Exception as error:
            if 'foreign key' in str(error).lower(): raise HTTPException(409,'Нельзя удалить генерала, который уже используется в армии')
            raise
    return {'deleted':True}

@router.get('/api/admin/units')
def admin_units():
    with connect() as conn: return {'units':catalogue(conn,False)}

@router.patch('/api/admin/units/{unit_id}')
async def edit_unit(unit_id: int, request: Request):
    data=await body(request)
    editable_fields=tuple(field for field in UNIT_FIELDS if field!='health')
    if set(data)!=set(editable_fields): raise HTTPException(400,'Передайте все редактируемые поля юнита')
    for key in ('name','troop_type','description','image_path','price','building','note'):
        if not isinstance(data[key],str) or len(data[key])>4000: raise HTTPException(400,f'Некорректное поле: {key}')
    for key in ('armor','defense','attack','attack_range','speed','initiative','morale'):
        if type(data[key]) is not int or not 0<=data[key]<=100: raise HTTPException(400,f'{key}: число 0–100')
    if type(data['active']) is not bool or not data['name'].strip() or not data['troop_type'].strip(): raise HTTPException(400,'Заполните название, тип и активность')
    if not data['image_path'].startswith('units/') or not data['image_path'].endswith('.webp'): raise HTTPException(400,'Изображение должно находиться в units/*.webp')
    values=[data[field].strip() if isinstance(data[field],str) else data[field] for field in editable_fields]
    with connect() as conn:
        row=conn.execute(f'''UPDATE unit_catalog SET {','.join(f'{field}=%s' for field in editable_fields)},updated_at=now() WHERE id=%s RETURNING id''',(*values,unit_id)).fetchone()
        if not row: raise HTTPException(404,'Юнит не найден')
    return {'saved':True}

@router.post('/api/admin/units')
async def create_unit(request: Request):
    data=await body(request)
    fields=UNIT_FIELDS
    if set(data)!=set(fields): raise HTTPException(400,'Передайте все поля нового юнита')
    for key in ('name','troop_type','description','image_path','price','building','note'):
        if not isinstance(data[key],str) or len(data[key])>4000: raise HTTPException(400,f'Некорректное поле: {key}')
    if type(data['health']) is not int or not 1<=data['health']<=10000: raise HTTPException(400,'health: число 1–10000')
    for key in ('armor','defense','attack','attack_range','speed','initiative','morale'):
        if type(data[key]) is not int or not 0<=data[key]<=100: raise HTTPException(400,f'{key}: число 0–100')
    if type(data['active']) is not bool or not data['name'].strip() or not data['troop_type'].strip(): raise HTTPException(400,'Заполните название, тип и активность')
    if not data['image_path'].startswith('units/') or not data['image_path'].endswith('.webp'): raise HTTPException(400,'Изображение должно находиться в units/*.webp')
    values=[data[field].strip() if isinstance(data[field],str) else data[field] for field in fields]
    with connect() as conn:
        row=conn.execute(f'''INSERT INTO unit_catalog ({','.join(fields)}) VALUES ({','.join('%s' for _ in fields)}) RETURNING id''',values).fetchone()
    return {'created':True,'id':row[0]}
