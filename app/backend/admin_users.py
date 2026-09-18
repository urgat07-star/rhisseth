"""Account administration, protected by the application's access middleware."""
import json
import re
import bcrypt
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from db import connect

router = APIRouter()

@router.get('/admin')
@router.get('/admin/')
def home():
    return RedirectResponse('/admin/users', status_code=303)

@router.get('/admin/users')
def panel():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend/users.html')

@router.get('/api/admin/users')
def users(q: str = '', role: str = '', page: int = 1):
    if len(q)>100 or role not in ('','admin','moderator','user') or not 1<=page<=100000:
        raise HTTPException(400,'Некорректные параметры поиска')
    where = "WHERE (%s='' OR strpos(lower(user_login),lower(%s))>0 OR strpos(lower(user_email),lower(%s))>0) AND (%s='' OR role_alias=%s)"
    params=(q,q,q,role,role)
    with connect() as conn:
        count=conn.execute('SELECT count(*) FROM users JOIN roles USING(role_id) '+where,params).fetchone()[0]
        rows=conn.execute('SELECT user_id,user_login,user_email,role_alias FROM users JOIN roles USING(role_id) '+where+' ORDER BY user_id LIMIT 50 OFFSET %s',(*params,(page-1)*50)).fetchall()
    return {'total':count,'page':page,'page_size':50,'users':[dict(zip(('id','login','email','role'),row)) for row in rows]}

@router.patch('/api/admin/users/{user_id}')
async def edit(user_id: int, request: Request):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4000: raise HTTPException(413,'Слишком большой запрос')
    try: data=json.loads(body)
    except ValueError: raise HTTPException(400,'Ожидается JSON')
    if not isinstance(data,dict) or not {'login','email','role','expected'}<=set(data) or set(data)-{'login','email','role','expected','password','password_confirm'}:
        raise HTTPException(400,'Укажите логин, e-mail, группу и исходную версию')
    login,email,role=data['login'],data['email'],data['role']
    if not all(isinstance(v,str) for v in (login,email,role)):
        raise HTTPException(400,'Неверный формат данных')
    login,email=login.strip(),email.strip()
    password,confirmation=data.get('password',''),data.get('password_confirm','')
    if not isinstance(password,str) or not isinstance(confirmation,str):
        raise HTTPException(400,'Неверный формат пароля')
    if password or confirmation:
        if password!=confirmation or len(password)<8 or not 8<=len(password.encode('utf-8'))<=72:
            raise HTTPException(400,'Пароли должны совпадать: минимум 8 символов, максимум 72 байта UTF-8')
    if not 3<=len(login)<=50 or len(email)>255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or role not in ('admin','moderator','user'):
        raise HTTPException(400,'Проверьте логин (3–50 символов), e-mail и группу')
    try:
        with connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(731605)')
            actor=conn.execute('SELECT role_alias FROM users JOIN roles USING(role_id) WHERE user_id=%s FOR UPDATE OF users',(request.state.user['user_id'],)).fetchone()
            if not actor or actor[0]!='admin': raise HTTPException(403,'Права администратора изменились')
            old=conn.execute('SELECT user_login,user_email,role_alias FROM users JOIN roles USING(role_id) WHERE user_id=%s FOR UPDATE OF users',(user_id,)).fetchone()
            if not old: raise HTTPException(404,'Пользователь не найден')
            previous=dict(zip(('login','email','role'),old))
            if data['expected']!=previous: raise HTTPException(409,'Данные изменились. Обновите список')
            if old[2]=='admin' and role!='admin':
                if user_id==request.state.user['user_id']: raise HTTPException(409,'Нельзя понизить собственную группу')
                if conn.execute("SELECT count(*) FROM users JOIN roles USING(role_id) WHERE role_alias='admin'").fetchone()[0]<=1:
                    raise HTTPException(409,'Нельзя понизить последнего администратора')
            role_row=conn.execute('SELECT role_id FROM roles WHERE role_alias=%s',(role,)).fetchone()
            if not role_row: raise HTTPException(503,'Группы не настроены')
            conn.execute('UPDATE users SET user_login=%s,user_email=%s,role_id=%s WHERE user_id=%s',(login,email,role_row[0],user_id))
            changed=sorted(k for k in previous if previous[k]!=dict(login=login,email=email,role=role)[k])
            if password:
                stored=bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt(rounds=12)).decode('ascii')
                conn.execute('UPDATE users SET user_pass=%s WHERE user_id=%s',(stored,user_id))
                changed.append('password')
            if changed:
                conn.execute('INSERT INTO user_admin_audit(actor_id,target_id,changed_fields,old_role,new_role) VALUES (%s,%s,%s,%s,%s)',(request.state.user['user_id'],user_id,Jsonb(changed),old[2],role))
                if password or user_id!=request.state.user['user_id']:
                    conn.execute('DELETE FROM user_sessions WHERE user_id=%s',(user_id,))
    except UniqueViolation: raise HTTPException(409,'Логин или e-mail уже используется')
    return {'saved':True,'reauthenticate':bool(password) and user_id==request.state.user['user_id']}

@router.delete('/api/admin/users/{user_id}')
def remove(user_id: int, request: Request):
    """Delete an account and return all of its player territory to neutral state."""
    if user_id < 1:
        raise HTTPException(404,'Пользователь не найден')
    if user_id == request.state.user['user_id']:
        raise HTTPException(409,'Нельзя удалить собственный аккаунт')
    with connect() as conn:
        # Also serializes role changes and protects against deleting the last admin.
        conn.execute('SELECT pg_advisory_xact_lock(731605)')
        actor=conn.execute('SELECT role_alias FROM users JOIN roles USING(role_id) WHERE user_id=%s FOR UPDATE OF users',(request.state.user['user_id'],)).fetchone()
        if not actor or actor[0]!='admin':
            raise HTTPException(403,'Права администратора изменились')
        target=conn.execute('SELECT user_login,role_alias FROM users JOIN roles USING(role_id) WHERE user_id=%s FOR UPDATE OF users',(user_id,)).fetchone()
        if not target:
            raise HTTPException(404,'Пользователь не найден')
        if target[1]=='admin' and conn.execute("SELECT count(*) FROM users JOIN roles USING(role_id) WHERE role_alias='admin'").fetchone()[0]<=1:
            raise HTTPException(409,'Нельзя удалить последнего администратора')
        # Game start locks this table as well, so a newly issued barony cannot survive deletion.
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        released=conn.execute("""UPDATE hexes SET data=data || %s,updated_at=now()
            WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s""",
            (Jsonb({'Тип владельца':'Ничейная территория','Владелец':'','Название территории':'','ID территории':''}),str(user_id))).rowcount
        conn.execute('INSERT INTO user_admin_audit(actor_id,target_id,target_login,changed_fields,old_role,new_role) VALUES (%s,%s,%s,%s,%s,%s)',
                     (request.state.user['user_id'],user_id,target[0],Jsonb(['deleted']),target[1],''))
        conn.execute('DELETE FROM player_baronies WHERE user_id=%s',(user_id,))
        conn.execute('DELETE FROM users WHERE user_id=%s',(user_id,))
    return {'deleted':True,'released_hexes':released}
