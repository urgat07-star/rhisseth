"""Admin-maintained connections between adjacent river hexes."""
from fastapi import APIRouter,HTTPException,Request
from battle_rules import NEIGHBORS
from db import connect
from movement import has_river

router=APIRouter()


def _admin(request):
    if request.state.user['role_alias']!='admin':raise HTTPException(403,'Доступ только для администратора')


def _pair(data):
    if not isinstance(data,dict) or set(data)!={'q1','r1','q2','r2'} or any(type(value) is not int for value in data.values()):
        raise HTTPException(400,'Укажите координаты двух речных гексов')
    a=(data['q1'],data['r1']);b=(data['q2'],data['r2'])
    if (b[0]-a[0],b[1]-a[1]) not in NEIGHBORS:
        raise HTTPException(400,'Речные гексы должны соседствовать')
    return (*a,*b) if a<b else (*b,*a)


@router.get('/api/admin/game/river-links')
def read_links(request:Request):
    _admin(request)
    with connect() as conn:
        rows=conn.execute('SELECT q1,r1,q2,r2 FROM game_river_links ORDER BY q1,r1,q2,r2').fetchall()
    return {'links':[dict(zip(('q1','r1','q2','r2'),row)) for row in rows]}


@router.post('/api/admin/game/river-links')
async def add_link(request:Request):
    _admin(request)
    try:pair=_pair(await request.json())
    except ValueError:raise HTTPException(400,'Ожидается JSON')
    with connect() as conn:
        for q,r in (pair[:2],pair[2:]):
            row=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(q,r)).fetchone()
            if not row or not has_river(row[0]):
                raise HTTPException(409,'Оба гекса должны содержать реку')
        conn.execute('''INSERT INTO game_river_links(q1,r1,q2,r2) VALUES (%s,%s,%s,%s)
            ON CONFLICT DO NOTHING''',pair)
    return {'saved':True,'link':dict(zip(('q1','r1','q2','r2'),pair))}


@router.delete('/api/admin/game/river-links')
async def delete_link(request:Request):
    _admin(request)
    try:pair=_pair(await request.json())
    except ValueError:raise HTTPException(400,'Ожидается JSON')
    with connect() as conn:
        result=conn.execute('DELETE FROM game_river_links WHERE (q1,r1,q2,r2)=(%s,%s,%s,%s)',pair)
    return {'deleted':result.rowcount>0}
