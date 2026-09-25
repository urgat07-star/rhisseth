"""Transactional movement of generals on their own territory."""
from fastapi import APIRouter, HTTPException, Request
import random

from battle_rules import NEIGHBORS, encounter
from db import connect
from game_clock import _clock
from hex_rules import coordinates

router=APIRouter()


def has_river(data):
    return 'Река' in f"{data.get('Дополнительный объект','')} {data.get('Тип местности','')}"


def movement_cost(conn,general_id,source_coord,target_coord,source,target,remaining):
    try:cost=int(target.get('Проходимость',''))
    except (TypeError,ValueError):raise HTTPException(409,'Для гекса не установлена проходимость')
    if cost<0:raise HTTPException(409,'Недопустимая проходимость гекса')
    crossing=False
    if has_river(target) and has_river(source):
        a,b=sorted((source_coord,target_coord))
        linked=conn.execute('''SELECT 1 FROM game_river_links WHERE q1=%s AND r1=%s AND q2=%s AND r2=%s''',
                            (*a,*b)).fetchone()
        if linked:cost=max(1,cost//2)
    if has_river(target) and not has_river(source):
        bridge=target.get('Водная переправа') in ('Мост','Переправа')
        scout=conn.execute('''SELECT 1 FROM player_general_units pgu JOIN unit_catalog uc ON uc.id=pgu.unit_id
            WHERE pgu.general_id=%s AND pgu.status='ready' AND uc.image_path='units/unit-019.webp' LIMIT 1''',
            (general_id,)).fetchone()
        if not bridge and not scout:
            crossing=True
            cost=remaining
    if remaining<cost or remaining<=0:raise HTTPException(409,'Недостаточно логистики')
    return cost,crossing


@router.post('/api/game/generals/{general_id}/move')
async def move_general(general_id:int,request:Request):
    try:data=await request.json()
    except ValueError:raise HTTPException(400,'Укажите целевой гекс')
    if not isinstance(data,dict) or set(data)!={'q','r'} or any(type(data[key]) is not int for key in ('q','r')):
        raise HTTPException(400,'Укажите координаты целевого гекса')
    q,r=data['q'],data['r']
    if (q,r) not in coordinates():raise HTTPException(404,'Гекс вне карты')
    user_id=request.state.user['user_id']
    with connect() as conn:
        turn,_,_=_clock(conn)
        general=conn.execute('''SELECT q,r,status,logistics_left FROM player_generals
            WHERE id=%s AND user_id=%s FOR UPDATE''',(general_id,user_id)).fetchone()
        if not general or general[2]!='active' or general[0] is None:
            raise HTTPException(404,'Доступный генерал не найден')
        if (q-general[0],r-general[1]) not in NEIGHBORS:
            raise HTTPException(409,'Перемещение возможно только на соседний гекс')
        if conn.execute('SELECT 1 FROM game_turn_votes WHERE turn_number=%s AND user_id=%s',(turn,user_id)).fetchone():
            raise HTTPException(409,'Глобальный ход уже завершён')
        if conn.execute("SELECT 1 FROM game_battles WHERE general_id=%s AND status='active'",(general_id,)).fetchone():
            raise HTTPException(409,'Сначала завершите текущий бой')
        source=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(general[0],general[1])).fetchone()
        target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(q,r)).fetchone()
        if not source:
            raise HTTPException(409,'Исходный гекс недоступен')
        if not target or target[0].get('Категория')=='Море':
            raise HTTPException(409,'Целевой гекс недоступен')
        cost,crossing=movement_cost(conn,general_id,(general[0],general[1]),(q,r),source[0],target[0],general[3])
        conn.execute('''UPDATE player_generals SET previous_q=q,previous_r=r,q=%s,r=%s,
            logistics_left=logistics_left-%s WHERE id=%s''',(q,r,cost,general_id))
        result={'moved':True,'q':q,'r':r,'logistics_left':general[3]-cost,'cost':cost,'crossing':crossing}
        level=max(0,min(7,int(target[0].get('Уровень гекса') or 0)))
        try:danger=int(target[0].get('Опасность') or 0)
        except (TypeError,ValueError):danger=0
        roll=random.randint(1,6)
        own=target[0].get('Тип владельца')=='Игрок' and target[0].get('Владелец')==str(user_id)
        kind=encounter(roll,danger,level,'own') if own else None
        if kind:
            from battle import create_encounter_battle
            result['battle']=create_encounter_battle(conn,user_id,general_id,(general[0],general[1]),(q,r),target[0],turn,kind)
        result['encounter_roll']=roll
        return result
