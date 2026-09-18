"""Archive-compatible bcrypt accounts and opaque PostgreSQL-backed sessions."""
import hashlib
import re
import secrets
from pathlib import Path
import bcrypt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation
from db import connect

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'site/templates'))
COOKIE = 'rhisseth_session'
DUMMY_HASH = bcrypt.hashpw(b'no-such-account', bcrypt.gensalt(rounds=12))

def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()

def get_session(request):
    token = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        return None
    with connect() as conn:
        row = conn.execute('''SELECT s.csrf,s.user_id,u.user_login,r.role_alias
            FROM user_sessions s LEFT JOIN users u USING(user_id)
            LEFT JOIN roles r USING(role_id)
            WHERE s.token_hash=%s AND s.expires_at>now()''', (token_hash(token),)).fetchone()
    return None if row is None else dict(zip(('csrf','user_id','user_login','role_alias'),row))

def current_user(request):
    session = get_session(request)
    return session if session and session['user_id'] else None

def new_session(user_id=None):
    token, csrf = secrets.token_hex(32), secrets.token_hex(32)
    with connect() as conn:
        conn.execute('DELETE FROM user_sessions WHERE expires_at<=now()')
        conn.execute("INSERT INTO user_sessions(token_hash,csrf,user_id,expires_at) VALUES (%s,%s,%s,now()+interval '12 hours')", (token_hash(token),csrf,user_id))
    return token, csrf

def set_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=43200, secure=True, httponly=True, samesite='lax', path='/')

def clear_session(request):
    token = request.cookies.get(COOKIE, '')
    if re.fullmatch(r'[a-f0-9]{64}',token):
        with connect() as conn:
            conn.execute('DELETE FROM user_sessions WHERE token_hash=%s', (token_hash(token),))

def csrf_valid(session, value):
    return session is not None and isinstance(value,str) and secrets.compare_digest(session['csrf'],value)

def verify_password(password, stored):
    try:
        # PHP bcrypt ignores bytes beyond 72; preserve existing login compatibility.
        return bcrypt.checkpw(password.encode('utf-8')[:72], stored.encode('ascii'))
    except (ValueError, UnicodeError):
        return False

def page(request, name, session=None, *, error='', success='', login='', status=200):
    token = None
    if session is None:
        token, csrf = new_session()
    else:
        csrf = session['csrf']
    response = templates.TemplateResponse(request=request, name=name, context={'csrf':csrf,'error_message':error,'success_message':success,'login':login}, status_code=status)
    response.headers['Cache-Control'] = 'no-store'
    if token:
        set_cookie(response,token)
    return response

@router.get('/index.php')
def login_page(request: Request):
    session = get_session(request)
    if session and session['user_id']:
        return RedirectResponse('/interactive-map/cabinet.html',status_code=303,headers={'Cache-Control':'no-store'})
    return page(request,'login.html',session)

@router.post('/index.php')
async def login(request: Request):
    form = await request.form(max_fields=10, max_files=0)
    session = get_session(request)
    if not csrf_valid(session, form.get('csrf')):
        raise HTTPException(403,'Обновите страницу входа и повторите попытку')
    name, password = form.get('login',''), form.get('password','')
    if not isinstance(name,str) or not isinstance(password,str) or len(name)>50 or len(password)>4096:
        raise HTTPException(400,'Неверный формат данных')
    name = name.strip()
    with connect() as conn:
        row = conn.execute('SELECT u.user_id,u.user_pass,r.role_alias FROM users u JOIN roles r USING(role_id) WHERE lower(user_login)=lower(%s)',(name,)).fetchone()
    valid = verify_password(password, row[1] if row else DUMMY_HASH.decode())
    if row is None or not valid:
        return page(request,'login.html',session,error='Неверный логин или пароль',login=name,status=401)
    clear_session(request)
    token, _ = new_session(row[0])
    response = RedirectResponse('/interactive-map/cabinet.html',status_code=303,headers={'Cache-Control':'no-store'})
    set_cookie(response,token)
    return response

@router.get('/register.php')
def register_page(request: Request):
    return page(request,'register.html',get_session(request))

@router.post('/register.php')
async def register(request: Request):
    form = await request.form(max_fields=10,max_files=0)
    session = get_session(request)
    if not csrf_valid(session,form.get('csrf')):
        raise HTTPException(403,'Обновите страницу регистрации')
    name,password,confirmation,email = [form.get(k,'') for k in ('login','password','password_confirm','email')]
    if not all(isinstance(value,str) for value in (name,password,confirmation,email)):
        raise HTTPException(400,'Неверный формат данных')
    name,email = name.strip(),email.strip()
    error = ''
    if not 3<=len(name)<=50 or not 8<=len(password.encode())<=72:
        error = 'Логин: 3–50 символов. Пароль: от 8 символов, до 72 байт.'
    elif len(password)<8 or password!=confirmation:
        error = 'Проверьте пароль и его подтверждение'
    elif len(email)>255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        error = 'Укажите корректный e-mail'
    if error:
        return page(request,'register.html',session,error=error,login=name,status=400)
    stored = bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode()
    try:
        with connect() as conn:
            role = conn.execute("SELECT role_id FROM roles WHERE role_alias='user'").fetchone()
            if role is None:
                raise HTTPException(503,'Роли сайта ещё не настроены')
            user_id = conn.execute('INSERT INTO users(user_login,user_pass,user_email,role_id) VALUES (%s,%s,%s,%s) RETURNING user_id',(name,stored,email,role[0])).fetchone()[0]
    except UniqueViolation:
        return page(request,'register.html',session,error='Логин или e-mail уже используется',login=name,status=409)
    clear_session(request)
    token, _ = new_session(user_id)
    response = RedirectResponse('/interactive-map/cabinet.html',status_code=303)
    set_cookie(response,token)
    return response

@router.post('/logout')
async def logout(request: Request):
    form = await request.form(max_fields=2,max_files=0)
    if not csrf_valid(get_session(request),form.get('csrf')):
        raise HTTPException(403,'Недопустимый запрос выхода')
    clear_session(request)
    response = RedirectResponse('/index.php',status_code=303)
    response.delete_cookie(COOKIE,path='/')
    return response
