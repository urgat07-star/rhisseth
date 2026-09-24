"""Transfer peasants won in raids from the barony reserve to owned hexes."""
from fastapi import APIRouter,HTTPException,Request
from db import connect

router=APIRouter()


@router.get('/api/cabinet/peasants')
def read_peasants(request:Request):
    user_id=request.state.user['user_id']
    with connect() as conn:
        row=conn.execute('SELECT quantity FROM barony_peasant_reserve WHERE user_id=%s',(user_id,)).fetchone()
        cells=conn.execute('''SELECT p.q,p.r,p.quantity FROM game_hex_peasants p JOIN hexes h ON h.q=p.q AND h.r=p.r
            WHERE h.data->>'Тип владельца'='Игрок' AND h.data->>'Владелец'=%s ORDER BY p.q,p.r''',
            (str(user_id),)).fetchall()
    return {'reserve':row[0] if row else 0,'hexes':[{'q':q,'r':r,'quantity':quantity} for q,r,quantity in cells]}


@router.post('/api/cabinet/peasants/transfer')
async def transfer_peasants(request:Request):
    try:data=await request.json()
    except ValueError:raise HTTPException(400,'Укажите количество и гекс')
    if not isinstance(data,dict) or set(data)!={'q','r','quantity'} or any(type(data[key]) is not int for key in data) or data['quantity']<=0:
        raise HTTPException(400,'Укажите положительное количество и координаты')
    user_id=request.state.user['user_id']
    with connect() as conn:
        reserve=conn.execute('SELECT quantity FROM barony_peasant_reserve WHERE user_id=%s FOR UPDATE',(user_id,)).fetchone()
        if not reserve or reserve[0]<data['quantity']:
            raise HTTPException(409,'Недостаточно крестьян в резерве')
        target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',(data['q'],data['r'])).fetchone()
        if not target or target[0].get('Тип владельца')!='Игрок' or target[0].get('Владелец')!=str(user_id):
            raise HTTPException(409,'Крестьян можно направить только на свой гекс')
        conn.execute('UPDATE barony_peasant_reserve SET quantity=quantity-%s WHERE user_id=%s',(data['quantity'],user_id))
        conn.execute('''INSERT INTO game_hex_peasants(q,r,quantity) VALUES (%s,%s,%s)
            ON CONFLICT(q,r) DO UPDATE SET quantity=game_hex_peasants.quantity+EXCLUDED.quantity''',
            (data['q'],data['r'],data['quantity']))
    return {'transferred':True,'reserve':reserve[0]-data['quantity']}
