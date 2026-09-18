# Release review 2026-09-18 (0.0.2): Owner-scoped profile, barony statistics, crest, rename, and confirmed abandonment.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Player-owned account and barony management; never accepts another player's ID."""
from collections import Counter
import json
import math
import re
import secrets
import bcrypt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from db import connect
from game_start import CRESTS
from hex_rules import FIELDS, public_row
from site_auth import verify_password, token_hash, set_cookie

router = APIRouter()
RATINGS = {'Проходимость':5, 'Защита':4, 'Плодородие':5, 'Опасность':5, 'Богатство ресурса':5}

async def payload(request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4000: raise HTTPException(413,'Слишком большой запрос')
    try: result=json.loads(body)
    except ValueError: raise HTTPException(400,'Ожидается JSON')
    if not isinstance(result,dict): raise HTTPException(400,'Ожидается объект')
    return result

def statistics(rows):
    categories=Counter(row.get('Категория') or 'Нет данных' for row in rows)
    resources=Counter(row['Основной ресурс'] for row in rows if row.get('Основной ресурс'))
    landscapes=Counter(row['Тип местности'] for row in rows if row.get('Тип местности'))
    ratings={}
    for field,maximum in RATINGS.items():
        values=[]
        for row in rows:
            raw=row.get(field)
            try: value=float(raw) if raw not in (None,'') else None
            except (ValueError,TypeError): value=None
            if value is not None and math.isfinite(value) and 0<=value<=maximum: values.append(value)
        ratings[field]={'known':len(values),'missing':len(rows)-len(values),'maximum':maximum,
                        'mean':round(sum(values)/len(values),2) if values else None,
                        'min':min(values) if values else None,'max':max(values) if values else None}
    return {'hex_count':len(rows),'categories':dict(categories),'resources':dict(resources),
            'landscapes':dict(landscapes),'islands':sum(row.get('Остров')=='Да' for row in rows),
            'objects':sum(bool(row.get('Дополнительный объект')) for row in rows),'ratings':ratings}

@router.get('/api/cabinet')
def cabinet(request: Request):
    user_id=request.state.user['user_id']
    with connect() as conn:
        account=conn.execute('SELECT user_login,user_email FROM users WHERE user_id=%s',(user_id,)).fetchone()
        if not account: raise HTTPException(401,'Требуется вход')
        row=conn.execute('SELECT id,name,title,crest,color FROM player_baronies WHERE user_id=%s',(user_id,)).fetchone()
        barony=None
        if row:
            cells=[public_row(item[0]) for item in conn.execute("SELECT data FROM hexes WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s AND data->>'ID территории'=%s ORDER BY r,q",(str(user_id),str(row[0]))).fetchall()]
            barony=dict(zip(('id','name','title','crest','color'),row))
            barony.update(hexes=cells,statistics=statistics(cells))
    return {'account':dict(zip(('login','email'),account)), 'barony':barony,
            'crests':CRESTS,'hex_fields':FIELDS}

@router.patch('/api/cabinet/account')
async def account(request: Request):
    data=await payload(request)
    required={'login','email','current_password','expected'}
    if not required<=set(data) or set(data)-required-{'password','password_confirm'}:
        raise HTTPException(400,'Укажите логин, e-mail, текущий пароль и исходные данные')
    login,email,current,new,confirmation=[data.get(key,'') for key in ('login','email','current_password','password','password_confirm')]
    if not all(isinstance(value,str) for value in (login,email,current,new,confirmation)):
        raise HTTPException(400,'Неверный формат данных')
    login,email=login.strip(),email.strip()
    if not 3<=len(login)<=50 or len(email)>255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(current)>4096:
        raise HTTPException(400,'Проверьте логин (3–50 символов), e-mail и пароль')
    if (new or confirmation) and (new!=confirmation or len(new)<8 or not 8<=len(new.encode())<=72):
        raise HTTPException(400,'Новые пароли должны совпадать: от 8 символов, до 72 байт')
    try:
        with connect() as conn:
            user_id=request.state.user['user_id']
            old=conn.execute('SELECT user_login,user_email,user_pass FROM users WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
            if not old: raise HTTPException(401,'Требуется вход')
            if not verify_password(current,old[2]): raise HTTPException(403,'Неверный текущий пароль')
            if data['expected']!={'login':old[0],'email':old[1]}:
                raise HTTPException(409,'Данные аккаунта изменились. Обновите кабинет')
            conn.execute('UPDATE users SET user_login=%s,user_email=%s WHERE user_id=%s',(login,email,user_id))
            if new:
                stored=bcrypt.hashpw(new.encode(),bcrypt.gensalt(rounds=12)).decode()
                conn.execute('UPDATE users SET user_pass=%s WHERE user_id=%s',(stored,user_id))
            token,csrf=secrets.token_hex(32),secrets.token_hex(32)
            conn.execute('DELETE FROM user_sessions WHERE user_id=%s',(user_id,))
            conn.execute("INSERT INTO user_sessions(token_hash,csrf,user_id,expires_at) VALUES (%s,%s,%s,now()+interval '12 hours')",(token_hash(token),csrf,user_id))
    except UniqueViolation: raise HTTPException(409,'Логин или e-mail уже используется')
    response=JSONResponse({'saved':True,'account':{'login':login,'email':email},'csrf':csrf})
    set_cookie(response,token)
    return response

@router.patch('/api/cabinet/barony/name')
async def rename(request: Request):
    data=await payload(request)
    if set(data)!={'barony_id','name','expected_name'} or type(data['barony_id']) is not int or not isinstance(data['name'],str) or not isinstance(data['expected_name'],str) or not 1<=len(data['name'].strip())<=200:
        raise HTTPException(400,'Укажите название баронии (1–200 символов)')
    name=data['name'].strip()
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        user_id=request.state.user['user_id']
        conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(user_id,))
        row=conn.execute('SELECT id,name FROM player_baronies WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
        if not row or row[0]!=data['barony_id'] or row[1]!=data['expected_name']:
            raise HTTPException(409,'Барония изменилась. Обновите кабинет')
        conn.execute('UPDATE player_baronies SET name=%s WHERE id=%s',(name,row[0]))
        conn.execute("UPDATE hexes SET data=data || %s,updated_at=now() WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s AND data->>'ID территории'=%s",(Jsonb({'Название баронии':name}),str(user_id),str(row[0])))
        conn.execute('INSERT INTO player_barony_audit(user_id,barony_id,action,details) VALUES (%s,%s,%s,%s)',(user_id,row[0],'rename',Jsonb({'old_name':row[1],'name':name})))
    return {'saved':True}

@router.patch('/api/cabinet/barony/crest')
async def crest(request: Request):
    data=await payload(request)
    if set(data)!={'barony_id','crest','color'} or type(data['barony_id']) is not int or data['crest'] not in CRESTS or not isinstance(data['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',data['color']):
        raise HTTPException(400,'Выберите герб, цвет и текущую баронию')
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        user_id=request.state.user['user_id']
        conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(user_id,))
        row=conn.execute('SELECT id FROM player_baronies WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
        if not row or row[0]!=data['barony_id']: raise HTTPException(409,'Барония изменилась. Обновите кабинет')
        color=data['color'].lower()
        conn.execute('UPDATE player_baronies SET crest=%s,color=%s WHERE id=%s',(data['crest'],color,row[0]))
        conn.execute("UPDATE hexes SET data=data || %s,updated_at=now() WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s AND data->>'ID территории'=%s",(Jsonb({'Герб баронии':data['crest'],'Цвет баронии':color}),str(user_id),str(row[0])))
        conn.execute('INSERT INTO player_barony_audit(user_id,barony_id,action,details) VALUES (%s,%s,%s,%s)',(user_id,row[0],'crest',Jsonb({'crest':data['crest'],'color':color})))
    return {'saved':True}

@router.delete('/api/cabinet/barony')
async def abandon(request: Request):
    data=await payload(request)
    if set(data)!={'barony_id','confirmation','confirmed'} or type(data['barony_id']) is not int or not isinstance(data['confirmation'],str) or data['confirmed'] is not True:
        raise HTTPException(400,'Для отказа подтвердите действие и введите название баронии')
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        user_id=request.state.user['user_id']
        conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(user_id,))
        row=conn.execute('SELECT id,name FROM player_baronies WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
        if not row or row[0]!=data['barony_id']: raise HTTPException(409,'Барония изменилась. Обновите кабинет')
        if data['confirmation']!=row[1]: raise HTTPException(400,'Название баронии не совпадает')
        released=conn.execute("""UPDATE hexes SET data=(data - ARRAY['ID территории','Название баронии','Цвет баронии','Герб баронии']) || %s,updated_at=now()
            WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s AND data->>'ID территории'=%s""",
            (Jsonb({'Тип владельца':'Ничейная территория','Владелец':''}),str(user_id),str(row[0]))).rowcount
        conn.execute('INSERT INTO player_barony_audit(user_id,barony_id,action,details) VALUES (%s,%s,%s,%s)',(user_id,row[0],'abandon',Jsonb({'released_hexes':released})))
        conn.execute('DELETE FROM player_baronies WHERE id=%s AND user_id=%s',(row[0],user_id))
    return {'abandoned':True,'released_hexes':released}
