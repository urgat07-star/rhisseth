"""Single starting barony per player, allocated atomically from neutral land."""
import secrets
import re
from itertools import combinations
from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from db import connect
from hex_rules import coordinates, connected

router = APIRouter()
NEIGHBORS = ((1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1))
CRESTS = tuple(f'gerb_{i}.png' for i in range(1,6))

def free_cells(conn):
    allowed=set(coordinates())
    return {(q,r) for q,r,data in conn.execute('SELECT q,r,data FROM hexes')
            if (q,r) in allowed and (data.get('Категория') in ('Суша','Побережье')
                                     or data.get('Остров')=='Да')
            and data.get('Тип владельца','Ничейная территория')=='Ничейная территория'
            and not str(data.get('Владелец') or '').strip()
            and not data.get('ID территории')}

def candidates(conn):
    free=free_cells(conn)
    options=set()
    for q,r in sorted(free):
        neighbors=sorted((q+dq,r+dr) for dq,dr in NEIGHBORS if (q+dq,r+dr) in free)
        if neighbors:
            for size in (1,2):
                for adjacent in combinations(neighbors,size):
                    options.add(tuple(sorted([(q,r),*adjacent])))
    return sorted(options)

@router.get('/api/start/options')
def start_options(request: Request, random: bool = False):
    with connect() as conn:
        existing=conn.execute('SELECT id,name,territory_name,crest,color FROM player_baronies WHERE user_id=%s',(request.state.user['user_id'],)).fetchone()
        if existing:
            cells=conn.execute("SELECT q,r FROM hexes WHERE data->>'ID территории'=%s AND data->>'Владелец'=%s",(str(existing[0]),str(request.state.user['user_id']))).fetchall()
            return {'started':True,'title':'Барон','name':existing[1],'territory_name':existing[2],
                    'crest':existing[3],'color':existing[4],'cells':cells,'options':[]}
        choices=candidates(conn)
        free=sorted(free_cells(conn))
    return {'started':False,'title':'Барон','available_cells':free,'crests':CRESTS,
            'random_cells':secrets.choice(choices) if random and choices else [],
            'options':[{'cells':list(c)} for c in choices]}

@router.post('/api/start')
async def start(request: Request):
    import json
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4000:raise HTTPException(413,'Слишком большой запрос')
    try:payload=json.loads(body)
    except ValueError:raise HTTPException(400,'Ожидается JSON')
    if not isinstance(payload,dict) or set(payload)-{'cells','name','crest','color','agreement'}:
        raise HTTPException(400,'Недопустимые поля')
    name=payload.get('name','Моя барония')
    if not isinstance(name,str) or not 1<=len(name.strip())<=200:
        raise HTTPException(400,'Название баронии: 1–200 символов')
    crest,color=payload.get('crest'),payload.get('color')
    if crest not in CRESTS or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
        raise HTTPException(400,'Выберите герб и цвет баронии')
    if payload.get('agreement') is not True:
        raise HTTPException(400,'Подтвердите условия создания баронии')
    cells=payload.get('cells')
    if cells is not None:
        if not isinstance(cells,list) or not 2<=len(cells)<=3 or any(not isinstance(c,list) or len(c)!=2 or any(type(v) is not int for v in c) for c in cells):
            raise HTTPException(400,'Начальная барония: 2–3 соседних гекса')
        cells=tuple(sorted(tuple(c) for c in cells))
        if len(set(cells))!=len(cells) or not connected(cells):raise HTTPException(400,'Гексы должны быть соседними')
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(request.state.user['user_id'],))
        if conn.execute('SELECT 1 FROM player_baronies WHERE user_id=%s',(request.state.user['user_id'],)).fetchone():
            raise HTTPException(409,'Начальная барония уже получена')
        choices=candidates(conn)
        if not choices:raise HTTPException(409,'Нет свободных бароний')
        if cells is None:cells=secrets.choice(choices)
        elif not set(cells)<=free_cells(conn):raise HTTPException(409,'Гексы заняты или не подходят для баронии. Обновите карту')
        barony=conn.execute('INSERT INTO player_baronies(user_id,name,crest,color,agreement_at) VALUES (%s,%s,%s,%s,now()) RETURNING id',(request.state.user['user_id'],name.strip(),crest,color.lower())).fetchone()[0]
        for q,r in cells:
            conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s', (Jsonb({'Тип владельца':'Игрок','Владелец':str(request.state.user['user_id']),'Название баронии':name.strip(),'Цвет баронии':color.lower(),'Герб баронии':crest,'ID территории':str(barony)}),q,r))
    return {'started':True,'title':'Барон','name':name.strip(),'crest':crest,'color':color.lower(),'cells':cells}
