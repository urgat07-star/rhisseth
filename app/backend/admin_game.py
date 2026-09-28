"""Reviewable administrative reset of player starting zones."""
from fastapi import APIRouter, HTTPException, Request
from db import connect
from hex_rules import coordinates, connected
from psycopg.types.json import Jsonb

router = APIRouter()


def _inspect(conn):
    rows=conn.execute('''SELECT b.id,b.name,b.user_id,count(s.q) AS start_count
            FROM player_baronies b LEFT JOIN barony_start_hexes s ON s.barony_id=b.id
            GROUP BY b.id,b.name,b.user_id ORDER BY b.id''').fetchall()
    owned=conn.execute("SELECT count(*) FROM hexes WHERE data->>'Тип владельца'='Игрок'").fetchone()[0]
    starts=conn.execute('''SELECT s.barony_id,s.q,s.r,h.data->>'Тип владельца',h.data->>'Владелец'
            FROM barony_start_hexes s LEFT JOIN hexes h ON h.q=s.q AND h.r=s.r ORDER BY s.barony_id,s.position''').fetchall()
    owners={row[0] for row in conn.execute("SELECT DISTINCT data->>'Владелец' FROM hexes WHERE data->>'Тип владельца'='Игрок'").fetchall()}
    expected_owners={str(row[2]) for row in rows}
    turn=conn.execute('SELECT turn_number FROM game_clock WHERE id=true').fetchone()[0]
    missing=[{'barony_id':row[0],'name':row[1],'user_id':row[2],'start_count':row[3]}
             for row in rows if row[3]<2 or row[3]>3]
    conflicts=[{'barony_id':row[0],'q':row[1],'r':row[2],'owner_type':row[3],'owner_id':row[4]}
               for row in starts if row[3]=='Компьютерное владение' or row[3] is None]
    unknown_owners=sorted(owners-expected_owners)
    return {'baronies':len(rows),'turn':turn,
            'barony_list':[{'id':row[0],'name':row[1],'user_id':row[2],'start_count':row[3]} for row in rows],
            'player_owned_hexes':owned,'recorded_start_hexes':len(starts),
            'missing_start_zones':missing,'conflicts':conflicts,'unknown_owners':unknown_owners,
            'ready':not missing and not conflicts and not unknown_owners}


@router.get('/api/admin/game/reset-preview')
def reset_preview(request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    with connect() as conn:
        return _inspect(conn)


@router.post('/api/admin/game/reset-baronies')
async def reset_baronies(request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'confirmation','expected_turn'} or data['confirmation']!='СБРОСИТЬ ТЕСТ' or type(data['expected_turn']) is not int:
        raise HTTPException(400,'Подтвердите полный тестовый сброс')
    with connect() as conn:
        conn.execute('LOCK TABLE hexes IN SHARE ROW EXCLUSIVE MODE')
        conn.execute('SELECT id FROM game_clock WHERE id=true FOR UPDATE')
        turn=conn.execute('SELECT turn_number FROM game_clock WHERE id=true').fetchone()[0]
        if turn!=data['expected_turn']:
            raise HTTPException(409,'Глобальный ход изменился; обновите предварительный просмотр')
        preview=_inspect(conn)
        if not preview['ready'] or not preview['baronies']:
            raise HTTPException(409,'Не все исходные зоны бароний подтверждены')
        baronies=conn.execute('''SELECT b.id,b.user_id,b.name,b.territory_name,b.crest,b.color,
            s.q,s.r FROM player_baronies b JOIN barony_start_hexes s ON s.barony_id=b.id
            ORDER BY b.id,s.position FOR UPDATE OF b''').fetchall()
        user_ids=sorted({row[1] for row in baronies})
        current=conn.execute('SELECT user_id,gold FROM game_wallets WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE',(user_ids,)).fetchall()
        gold_by_user=dict(current)
        inventories=conn.execute('''SELECT user_id,resource_code,quantity FROM game_inventory
            WHERE user_id=ANY(%s) ORDER BY user_id,resource_code FOR UPDATE''',(user_ids,)).fetchall()
        resources={(user_id,code):quantity for user_id,code,quantity in inventories}
        generals=conn.execute('SELECT count(*) FROM player_generals WHERE user_id=ANY(%s)',(user_ids,)).fetchone()[0]
        conn.execute('DELETE FROM game_battles WHERE attacker_user_id=ANY(%s)',(user_ids,))
        conn.execute('DELETE FROM game_deployment_template WHERE user_id=ANY(%s)',(user_ids,))
        conn.execute('DELETE FROM player_generals WHERE user_id=ANY(%s)',(user_ids,))
        conn.execute('DELETE FROM game_hex_raids')
        conn.execute('DELETE FROM game_hex_morale')
        conn.execute('DELETE FROM game_hex_peasants')
        conn.execute('DELETE FROM barony_peasant_reserve WHERE user_id=ANY(%s)',(user_ids,))
        released=conn.execute('''UPDATE hexes SET data=(data - ARRAY['ID территории','Название территории','Название баронии','Цвет баронии','Герб баронии']) || %s,
            updated_at=now() WHERE data->>'Тип владельца'='Игрок' ''',
            (Jsonb({'Тип владельца':'Ничейная территория','Владелец':'','Уровень гекса':'0','Постройка':'- нет -'}),)).rowcount
        for barony_id,user_id,name,territory_name,crest,color,q,r in baronies:
            patch={'Тип владельца':'Игрок','Владелец':str(user_id),'ID территории':str(barony_id),
                   'Название баронии':name,'Название территории':territory_name,
                   'Герб баронии':crest,'Цвет баронии':color,'Уровень гекса':'0','Постройка':'- нет -'}
            conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s',(Jsonb(patch),q,r))
        for user_id in user_ids:
            previous=gold_by_user.get(user_id,0)
            conn.execute('''INSERT INTO game_wallets(user_id,gold) VALUES (%s,300)
                ON CONFLICT(user_id) DO UPDATE SET gold=300''',(user_id,))
            if previous!=300:
                conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason) VALUES (%s,%s,'test_reset')",(user_id,300-previous))
        initial=conn.execute('SELECT code,starting_quantity FROM game_resources ORDER BY code').fetchall()
        reset_resource_count=0
        for user_id in user_ids:
            for code,quantity in initial:
                previous=resources.get((user_id,code),0)
                conn.execute('''INSERT INTO game_inventory(user_id,resource_code,quantity) VALUES (%s,%s,%s)
                    ON CONFLICT(user_id,resource_code) DO UPDATE SET quantity=EXCLUDED.quantity''',(user_id,code,quantity))
                if previous!=quantity:
                    conn.execute("INSERT INTO game_resource_ledger(user_id,resource_code,amount,reason) VALUES (%s,%s,%s,'test_reset')",(user_id,code,quantity-previous))
                reset_resource_count+=1
        conn.execute("UPDATE game_clock SET turn_number=0,started_at=now(),ends_at=now()+interval '12 hours' WHERE id=true")
        conn.execute('DELETE FROM game_turn_votes')
        conn.execute('DELETE FROM game_presence')
        conn.execute("INSERT INTO game_clock_audit(actor_user_id,old_turn_number,new_turn_number,action) VALUES (%s,%s,0,'admin_reset')",
                     (request.state.user['user_id'],turn))
        conn.execute('''INSERT INTO barony_reset_audit(actor_user_id,baronies_count,released_hexes,restored_hexes,
            previous_turn,removed_generals,reset_gold,reset_resources) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
            (request.state.user['user_id'],preview['baronies'],released,len(baronies),turn,generals,len(user_ids),reset_resource_count))
    return {'reset':True,'baronies':preview['baronies'],'released_hexes':released,
            'restored_hexes':len(baronies),'removed_generals':generals,'year':0,'season':'Весна'}


@router.put('/api/admin/game/baronies/{barony_id}/start-zone')
async def set_start_zone(barony_id: int, request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    data=await request.json()
    cells=data.get('cells') if isinstance(data,dict) and set(data)=={'cells'} else None
    if not isinstance(cells,list) or not 2<=len(cells)<=3 or any(not isinstance(cell,list) or len(cell)!=2 or any(type(value) is not int for value in cell) for cell in cells):
        raise HTTPException(400,'Укажите 2–3 стартовых гекса')
    cells=[tuple(cell) for cell in cells]
    if len(set(cells))!=len(cells) or not connected(cells) or any(cell not in coordinates() for cell in cells):
        raise HTTPException(400,'Стартовые гексы должны быть соседними и находиться на карте')
    with connect() as conn:
        barony=conn.execute('SELECT id FROM player_baronies WHERE id=%s FOR UPDATE',(barony_id,)).fetchone()
        if not barony: raise HTTPException(404,'Барония не найдена')
        for q,r in cells:
            row=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(q,r)).fetchone()
            if not row or row[0].get('Категория')=='Море':
                raise HTTPException(409,'Стартовая зона должна быть на суше или побережье')
            occupied=conn.execute('SELECT barony_id FROM barony_start_hexes WHERE q=%s AND r=%s',(q,r)).fetchone()
            if occupied and occupied[0]!=barony_id:
                raise HTTPException(409,'Этот гекс уже записан как стартовый для другой баронии')
        previous=conn.execute('SELECT q,r FROM barony_start_hexes WHERE barony_id=%s ORDER BY position',(barony_id,)).fetchall()
        conn.execute('DELETE FROM barony_start_hexes WHERE barony_id=%s',(barony_id,))
        for index,(q,r) in enumerate(cells,1):
            conn.execute('INSERT INTO barony_start_hexes(barony_id,position,q,r) VALUES (%s,%s,%s,%s)',(barony_id,index,q,r))
        conn.execute('''INSERT INTO barony_start_zone_audit(actor_user_id,barony_id,old_cells,new_cells)
            VALUES (%s,%s,%s,%s)''',(request.state.user['user_id'],barony_id,Jsonb(previous),Jsonb(cells)))
    return {'saved':True,'barony_id':barony_id,'cells':cells}
