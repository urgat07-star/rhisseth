from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
import psycopg
from db import connect
from site_auth import router, current_user

app = FastAPI(title='Rhisseth', docs_url=None, redoc_url=None)
app.include_router(router)

@app.middleware('http')
async def access_control(request: Request, call_next):
    path = request.url.path
    if path.startswith(('/api/', '/interactive-map')) or path == '/health':
        try:
            user = current_user(request)
        except psycopg.Error:
            return JSONResponse({'error':'База данных недоступна'},status_code=503)
        if user is None:
            if path.startswith('/interactive-map'):
                return RedirectResponse('/index.php',status_code=303)
            return JSONResponse({'error':'Требуется вход'},status_code=401)
        request.state.user = user
        if request.method not in ('GET','HEAD'):
            import secrets
            csrf = request.headers.get('X-CSRF-Token','')
            if not secrets.compare_digest(csrf,user['csrf']):
                return JSONResponse({'error':'Недопустимый CSRF token'},status_code=403)
            if user['role_alias'] not in ('admin','moderator'):
                return JSONResponse({'error':'Недостаточно прав для редактирования'},status_code=403)
    return await call_next(request)
EDITABLE = {'Категория', 'Тип местности', 'Дополнительный объект', 'Проходимость',
            'Защита', 'Плодородие', 'Пресная вода', 'Опасность', 'Основной ресурс',
            'Богатство ресурса', 'Комментарий'}
LIMITS = {'Проходимость': 5, 'Защита': 4, 'Плодородие': 5, 'Пресная вода': 5,
          'Опасность': 5, 'Богатство ресурса': 5}

@app.exception_handler(HTTPException)
async def http_error(request, error):
    return JSONResponse({'error': error.detail}, status_code=error.status_code)

@app.exception_handler(psycopg.Error)
async def database_error(request, error):
    return JSONResponse({'error': 'База данных недоступна или схема не подготовлена'}, status_code=503)

@app.get('/health')
def health():
    with connect() as conn:
        conn.execute('SELECT count(*) FROM hexes').fetchone()
    return {'status': 'ok'}

@app.get('/api/hexes')
def hexes():
    with connect() as conn:
        rows = conn.execute('SELECT data FROM hexes ORDER BY r,q').fetchall()
    return [row[0] for row in rows]

@app.get('/api/me')
def me(request: Request):
    user = request.state.user
    return {'login':user['user_login'],'role':user['role_alias'],
            'can_edit':user['role_alias'] in ('admin','moderator'),'csrf':user['csrf']}

@app.put('/api/hexes/{q}/{r}')
async def update(q: int, r: int, request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64000:
            raise HTTPException(413, 'Слишком большой запрос')
    import json
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Ожидается JSON')
    if not isinstance(payload, dict) or set(payload) - EDITABLE:
        raise HTTPException(400, 'Недопустимые поля')
    if any(not isinstance(v, str) or len(v) > 4000 for v in payload.values()):
        raise HTTPException(400, 'Значения должны быть строками до 4000 символов')
    payload = {k: v.strip() for k, v in payload.items()}
    for key, maximum in LIMITS.items():
        value = payload.get(key, '')
        if value and (not value.isascii() or not value.isdigit() or not 0 <= int(value) <= maximum):
            raise HTTPException(400, f'{key}: требуется целое число 0–{maximum}')
    with connect() as conn:
        row = conn.execute('UPDATE hexes SET data=data || %s, updated_at=now() WHERE q=%s AND r=%s RETURNING data',
                           (Jsonb(payload), q, r)).fetchone()
        if row is None:
            raise HTTPException(404, 'Гекс не найден')
    return {'saved': True, 'row': row[0]}

@app.get('/')
def root():
    return RedirectResponse('/index.php',status_code=303)

@app.get('/map/{path:path}')
def legacy_map(path: str):
    if path in ('','interactive-map/','interactive-map/index.html','index.html'):
        return RedirectResponse('/interactive-map/',status_code=303)
    raise HTTPException(404,'Страница не найдена')

app.mount('/interactive-map', StaticFiles(directory=str(Path(__file__).resolve().parents[1] / 'frontend'), html=True))
app.mount('/site', StaticFiles(directory=str(Path(__file__).resolve().parents[1] / 'site/static')))
