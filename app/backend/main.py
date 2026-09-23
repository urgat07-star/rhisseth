from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, Response
from hex_rules import FIELDS, CATEGORIES, coordinates, public_row, category_from_share, connected
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
import psycopg
from db import connect
from site_auth import router, current_user
from game_start import router as game_router
from admin_users import router as admin_router
from player_cabinet import router as cabinet_router
from army import router as army_router

app = FastAPI(title='Rhisseth', docs_url=None, redoc_url=None)
app.include_router(router)
app.include_router(game_router)
app.include_router(admin_router)
app.include_router(cabinet_router)
app.include_router(army_router)

@app.middleware('http')
async def access_control(request: Request, call_next):
    path = request.url.path
    if path.startswith(('/api/', '/interactive-map', '/admin')):
        try:
            user = current_user(request)
        except psycopg.Error:
            return JSONResponse({'error':'База данных недоступна'},status_code=503)
        if user is None:
            if path.startswith(('/interactive-map', '/admin')):
                return RedirectResponse('/index.php',status_code=303)
            return JSONResponse({'error':'Требуется вход'},status_code=401)
        request.state.user = user
        if (path in ('/admin','/admin/') or path.startswith(('/admin/users','/api/admin/users'))) and user['role_alias'] != 'admin':
            return JSONResponse({'error':'Доступ только для администраторов'},status_code=403)
        if path.startswith(('/admin/hexes','/admin/units','/api/admin/')) and user['role_alias'] not in ('admin','moderator'):
            return JSONResponse({'error':'Доступ только для администрации'},status_code=403)
        if request.method not in ('GET','HEAD'):
            import secrets
            csrf = request.headers.get('X-CSRF-Token','')
            if not secrets.compare_digest(csrf,user['csrf']):
                return JSONResponse({'error':'Недопустимый CSRF token'},status_code=403)
            territory_name_action = request.method == 'PATCH' and path.endswith('/territory-name') and path.startswith('/api/hexes/')
            start_action = path == '/api/start' and request.method == 'POST'
            cabinet_action = (request.method,path) in {('PATCH','/api/cabinet/account'),('PATCH','/api/cabinet/barony/crest'),('PATCH','/api/cabinet/barony/name'),('DELETE','/api/cabinet/barony')}
            army_action = request.method in ('POST','DELETE') and path.startswith('/api/cabinet/army/')
            game_action = request.method == 'POST' and path.startswith('/api/game/hexes/') and path.endswith('/capture')
            if user['role_alias'] not in ('admin','moderator') and not territory_name_action and not start_action and not cabinet_action and not army_action and not game_action:
                return JSONResponse({'error':'Недостаточно прав для редактирования'},status_code=403)
    response = await call_next(request)
    if path.startswith(('/api/', '/admin', '/interactive-map')):
        response.headers['Cache-Control'] = 'no-store'
    return response
EDITABLE = set(FIELDS)
LIMITS = {'Проходимость': 5, 'Защита': 4, 'Плодородие': 5,
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
        players = dict(conn.execute('SELECT user_id,user_login FROM users').fetchall())
        territories = {str(t[0]): f'{t[2]} {t[1]}' for t in conn.execute('SELECT id,name,kind FROM territories').fetchall()}
    by_coordinate = {(int(row[0]['Q']), int(row[0]['R'])): public_row(row[0]) for row in rows}
    result = [by_coordinate.get((q,r), {'Q':str(q),'R':str(r), 'Тип владельца':'Ничейная территория','Владелец':'','_revision':'missing'}) for q,r in coordinates()]
    for row in result:
        row.setdefault('Статус данных', 'Параметры из существующей БД' if row.get('Категория') in CATEGORIES else 'Требует описания')
        owner = row.get('Владелец','')
        row['Имя владельца'] = (players.get(int(owner),'Неизвестный игрок') if owner.isdigit() else 'Нет владельца') if row.get('Тип владельца')=='Игрок' else territories.get(owner,'Нет владельца')
    return result

@app.get('/admin/hexes')
def admin_page():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend/admin.html')

@app.get('/api/admin/hexes/export')
def export_hexes():
    import csv, io
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['Q','R','Статус данных',*FIELDS,'Имя владельца'], delimiter=';', extrasaction='ignore')
    writer.writeheader()
    for row in hexes():
        # Protect spreadsheet consumers against formulas entered in metadata.
        writer.writerow({k: int(v) if k in ('Q','R') else "'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v for k,v in row.items()})
    return Response('\ufeff'+stream.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename="rhisseth-hexes.csv"'})

@app.get('/api/admin/owners')
def owners():
    with connect() as conn:
        players = conn.execute('SELECT user_id,user_login FROM users ORDER BY user_login').fetchall()
        territories = conn.execute('SELECT id,name,kind,rules FROM territories ORDER BY name').fetchall()
    return {'players':[{'id':str(p[0]),'name':p[1]} for p in players],
            'territories':[{'id':str(t[0]),'name':t[1],'kind':t[2],'rules':t[3]} for t in territories]}

@app.get('/api/me')
def me(request: Request):
    user = request.state.user
    return {'login':user['user_login'],'role':user['role_alias'],
            'id':str(user['user_id']), 'can_edit':user['role_alias'] in ('admin','moderator'),'csrf':user['csrf']}

@app.post('/api/game/hexes/{q}/{r}/capture')
def capture_hex(q: int, r: int, request: Request):
    """Atomically transfer a land hex to the current player's adjacent barony."""
    if (q, r) not in coordinates():
        raise HTTPException(404, 'Гекс вне полотна')
    owner_id = str(request.state.user['user_id'])
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s,%s)', (q, r))
        target = conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE', (q, r)).fetchone()
        if not target:
            raise HTTPException(404, 'Гекс не найден')
        if target[0].get('Категория') == 'Море':
            raise HTTPException(400, 'Морские гексы нельзя захватывать')
        if target[0].get('Владелец') == owner_id and target[0].get('Тип владельца') == 'Игрок':
            raise HTTPException(409, 'Гекс уже принадлежит вам')
        adjacent = [(q+dq, r+dr) for dq,dr in ((1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1))]
        source = None
        for nq, nr in adjacent:
            candidate = conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s', (nq, nr)).fetchone()
            if candidate and candidate[0].get('Тип владельца') == 'Игрок' and candidate[0].get('Владелец') == owner_id:
                source = candidate[0]
                break
        if source is None:
            raise HTTPException(409, 'Захватываемый гекс должен соприкасаться с вашим владением')
        ownership = {'Тип владельца':'Игрок', 'Владелец':owner_id}
        for field in ('ID территории','Название территории','Название баронии','Цвет баронии','Герб баронии'):
            ownership[field] = source.get(field, '')
        result = conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s RETURNING data',
                              (Jsonb(ownership), q, r)).fetchone()
    row = public_row(result[0])
    row['Имя владельца'] = request.state.user['user_login']
    return {'captured': True, 'row': row}

@app.patch('/api/hexes/{q}/{r}/territory-name')
async def rename_owned_territory(q: int, r: int, request: Request):
    import json
    if (q,r) not in coordinates():
        raise HTTPException(404, 'Гекс вне полотна')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4000:
            raise HTTPException(413, 'Слишком большой запрос')
    try:
        payload=json.loads(body)
    except ValueError:
        raise HTTPException(400, 'Ожидается JSON')
    if not isinstance(payload,dict) or set(payload)!={'Название территории'} or not isinstance(payload['Название территории'],str) or len(payload['Название территории'])>200:
        raise HTTPException(400, 'Укажите только название территории до 200 символов')
    with connect() as conn:
        row=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',(q,r)).fetchone()
        if not row:
            raise HTTPException(404, 'Гекс не найден')
        expected=request.headers.get('X-Hex-Revision')
        if expected and expected!=public_row(row[0])['_revision']:
            raise HTTPException(409,'Данные изменены другим редактором. Обновите страницу')
        admin=request.state.user['role_alias'] in ('admin','moderator')
        if not admin and (row[0].get('Тип владельца')!='Игрок' or row[0].get('Владелец')!=str(request.state.user['user_id'])):
            raise HTTPException(403, 'Изменить название может только владелец территории')
        if row[0].get('Тип владельца')=='Компьютерное владение':
            conn.execute('UPDATE territories SET name=%s WHERE id=%s',(payload['Название территории'].strip(),int(row[0]['Владелец'])))
            conn.execute("UPDATE hexes SET data=data || %s,updated_at=now() WHERE data->>'Тип владельца'='Компьютерное владение' AND data->>'Владелец'=%s",(Jsonb({'Название территории':payload['Название территории'].strip()}),row[0]['Владелец']))
        barony=row[0].get('ID территории')
        if barony:
            owner=conn.execute('SELECT user_id FROM player_baronies WHERE id=%s FOR UPDATE',(int(barony),)).fetchone()
            if owner is None or not admin and owner[0]!=request.state.user['user_id']:
                raise HTTPException(403,'Нет прав на название баронии')
            conn.execute('UPDATE player_baronies SET territory_name=%s WHERE id=%s',(payload['Название территории'].strip(),int(barony)))
            conn.execute("UPDATE hexes SET data=data || %s,updated_at=now() WHERE data->>'ID территории'=%s AND data->>'Владелец'=%s",(Jsonb({'Название территории':payload['Название территории'].strip()}),barony,str(owner[0])))
        result=conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s RETURNING data',(Jsonb({'Название территории':payload['Название территории'].strip()}),q,r)).fetchone()
    return {'saved':True,'row':public_row(result[0])}

@app.put('/api/hexes/{q}/{r}')
async def update(q: int, r: int, request: Request):
    import math
    # Match the frontend's full-canvas coordinate bounds; no arbitrary off-map inserts.
    width = math.sqrt(3) * 80
    if not (0 <= r < math.ceil((2200 + 80) / 120)
            and math.ceil(-0.5 - r / 2) <= q <= math.floor(3200 / width + 0.5 - r / 2)):
        raise HTTPException(404, 'Гекс вне полотна')
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
    if 'Категория' in payload and payload['Категория'] not in CATEGORIES:
        raise HTTPException(400, 'Категория: Суша, Побережье или Море')
    if 'Остров' in payload and payload['Остров'] not in ('','Да','Нет'):
        raise HTTPException(400,'Остров: Да или Нет')
    if payload.get('Доля суши, %'):
        category = category_from_share(payload['Доля суши, %'])
        if payload.get('Остров')=='Да':category='Побережье'
        if 'Категория' in payload and payload['Категория'] != category:
            raise HTTPException(400, 'Категория не соответствует доле суши')
        payload['Категория'] = category
    if payload.get('Остров')=='Да':
        if payload.get('Категория','Побережье')!='Побережье':
            raise HTTPException(400,'Остров относится к побережью')
        payload['Категория']='Побережье'
    if any(len(payload.get(field,''))>200 for field in ('Название','Название территории')):
        raise HTTPException(400, 'Название: до 200 символов')
    if payload.get('Состав ландшафта'):
        try:
            parts = json.loads(payload['Состав ландшафта'])
            if not isinstance(parts,list) or not 1<=len(parts)<=10:
                raise ValueError()
            for part in parts:
                if not isinstance(part,dict) or set(part)!={'name','percent'} or not isinstance(part['name'],str) or not 1<=len(part['name'].strip())<=100 or type(part['percent']) not in (int,float) or not math.isfinite(part['percent']) or not 0<part['percent']<=100:
                    raise ValueError()
            if not math.isclose(sum(p['percent'] for p in parts),100,abs_tol=0.001):
                raise ValueError()
            payload['Тип местности'] = ' / '.join(p['name'].strip() for p in parts)
        except (ValueError,TypeError,KeyError):
            raise HTTPException(400, 'Состав ландшафта: названия и доли с суммой 100%')
    elif 'Тип местности' in payload:
        payload['Состав ландшафта']=''
    owner_type = payload.get('Тип владельца')
    if owner_type is not None:
        if owner_type not in ('Игрок','Компьютерное владение','Ничейная территория') or 'Владелец' not in payload:
            raise HTTPException(400, 'Укажите тип и владельца вместе')
        if owner_type == 'Ничейная территория':
            payload['Владелец'] = ''
        elif not payload['Владелец'].isascii() or not payload['Владелец'].isdigit():
            raise HTTPException(400, 'Выберите существующего владельца')
    elif 'Владелец' in payload:
        raise HTTPException(400, 'Укажите тип и владельца вместе')
    if owner_type == 'Компьютерное владение':
        raise HTTPException(400, 'Компьютерное владение назначается группой соседних гексов')
    for key, maximum in LIMITS.items():
        value = payload.get(key, '')
        if value and (not value.isascii() or not value.isdigit() or not 0 <= int(value) <= maximum):
            raise HTTPException(400, f'{key}: требуется целое число 0–{maximum}')
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s,%s)',(q,r))
        previous = conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE', (q,r)).fetchone()
        expected=request.headers.get('X-Hex-Revision')
        if expected and expected!=(public_row(previous[0])['_revision'] if previous else 'missing'):
            raise HTTPException(409,'Данные изменены другим редактором. Обновите страницу')
        if owner_type is not None and previous and previous[0].get('Тип владельца') == 'Компьютерное владение':
            raise HTTPException(400, 'Состав компьютерного владения изменяется через групповое назначение')
        if owner_type == 'Игрок' and not conn.execute('SELECT 1 FROM users WHERE user_id=%s',(int(payload['Владелец']),)).fetchone():
            raise HTTPException(400, 'Игрок не найден')
        if previous and previous[0].get('ID территории') and owner_type is not None and (owner_type!=previous[0].get('Тип владельца') or payload['Владелец']!=previous[0].get('Владелец')):
            payload['ID территории']=''
        if previous and previous[0].get('Остров')=='Да' and payload.get('Остров','Да')=='Да':
            if payload.get('Категория','Побережье')!='Побережье':raise HTTPException(400,'Остров относится к побережью')
        if previous and 'Категория' in payload and 'Доля суши, %' not in payload and previous[0].get('Доля суши, %') and payload.get('Остров',previous[0].get('Остров'))!='Да':
            if category_from_share(previous[0]['Доля суши, %']) != payload['Категория']:
                raise HTTPException(400, 'Измените долю суши вместе с категорией')
        if payload.get('Категория') in CATEGORIES and (payload.get('Тип местности') or previous and previous[0].get('Тип местности')):
            payload['Статус данных']='Описание заполнено'
        row = conn.execute('''INSERT INTO hexes(q,r,data) VALUES (%s,%s,%s)
                           ON CONFLICT(q,r) DO UPDATE
                           SET data=hexes.data || %s, updated_at=now() RETURNING data''',
                           (q, r, Jsonb({'Q': str(q), 'R': str(r), **payload}), Jsonb(payload))).fetchone()
    return {'saved': True, 'row': public_row(row[0])}

@app.post('/api/admin/territories')
async def assign_territory(request: Request):
    import json
    body = await request.body()
    if len(body) > 64000:
        raise HTTPException(413, 'Слишком большой запрос')
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, 'Ожидается JSON')
    if not isinstance(payload,dict) or set(payload)-{'id','name','rules','cells'}:
        raise HTTPException(400, 'Недопустимые поля владения')
    name, rules, cells = payload.get('name'), payload.get('rules',''), payload.get('cells')
    if not isinstance(name,str) or not 1<=len(name.strip())<=200 or not isinstance(rules,str) or len(rules)>4000:
        raise HTTPException(400, 'Укажите название до 200 символов и правила до 4000 символов')
    if not isinstance(cells,list) or not 2<=len(cells)<=10 or any(not isinstance(c,list) or len(c)!=2 or any(type(v) is not int for v in c) for c in cells):
        raise HTTPException(400, 'Владение: от 2 до 10 гексов')
    cells = [tuple(c) for c in cells]
    if len(set(cells))!=len(cells) or not set(cells)<=set(coordinates()) or not connected(cells):
        raise HTTPException(400, 'Гексы должны быть уникальными, на карте и составлять связную территорию')
    territory_id = payload.get('id')
    if territory_id is not None and (type(territory_id) is not int or territory_id<1):
        raise HTTPException(400, 'Недопустимый ID владения')
    kind = 'Баронство' if len(cells)<=3 else 'Княжество' if len(cells)<=6 else 'Королевство'
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        # Do not silently dismantle another computer player's territory.
        for q,r in cells:
            old = conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(q,r)).fetchone()
            if old and old[0].get('Тип владельца')=='Компьютерное владение' and old[0].get('Владелец') != str(territory_id):
                raise HTTPException(409, 'Гекс входит в другое компьютерное владение')
        if territory_id is None:
            territory_id = conn.execute('INSERT INTO territories(name,kind,rules) VALUES (%s,%s,%s) RETURNING id',(name.strip(),kind,rules.strip())).fetchone()[0]
        elif not conn.execute('UPDATE territories SET name=%s,kind=%s,rules=%s WHERE id=%s RETURNING id',(name.strip(),kind,rules.strip(),territory_id)).fetchone():
            raise HTTPException(404, 'Владение не найдено')
        conn.execute("UPDATE hexes SET data=data || %s,updated_at=now() WHERE data->>'Тип владельца'='Компьютерное владение' AND data->>'Владелец'=%s",(Jsonb({'Тип владельца':'Ничейная территория','Владелец':''}),str(territory_id)))
        for q,r in cells:
            patch = {'Тип владельца':'Компьютерное владение','Владелец':str(territory_id),'Название территории':name.strip()}
            patch['ID территории']=''
            conn.execute('INSERT INTO hexes(q,r,data) VALUES (%s,%s,%s) ON CONFLICT(q,r) DO UPDATE SET data=hexes.data || %s,updated_at=now()', (q,r,Jsonb({'Q':str(q),'R':str(r),**patch}),Jsonb(patch)))
    return {'saved':True,'id':territory_id,'kind':kind}

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
