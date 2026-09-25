"""Server-owned tactical battles and transactional capture results."""
import random
from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb

from db import connect
from hex_rules import coordinates, HEX_BUILDINGS
from battle_rules import NEIGHBORS, WALL_HEALTH, choose_defenders, damage, defense_budget, distance, reachable
from army import award_general_victory, home_hex
from movement import movement_cost
from game_clock import _clock

router=APIRouter()
UNIT_FIELDS=('id','battle_id','side','assignment_id','unit_id','is_general','name','image_path','x','y',
             'health','max_health','attack','defense','armor','attack_range','speed','initiative','active','moved','attacked','is_wall')
BATTLE_FIELDS=('id','attacker_user_id','general_id','target_q','target_r','source_q','source_r',
               'target_owner_type','target_owner_id','purpose','status','round_number','created_turn','last_side','destroyed_at','deployment_locked')


def _int(value,default=0):
    try:return int(value)
    except (TypeError,ValueError):return default


def _capture_neighbor(conn, q, r, user_id):
    return conn.execute('''SELECT data FROM hexes WHERE (q,r) IN
        ((%s,%s),(%s,%s),(%s,%s),(%s,%s),(%s,%s),(%s,%s))
        AND data->>'Тип владельца'='Игрок' AND data->>'Владелец'=%s LIMIT 1''',
        tuple(value for dq,dr in NEIGHBORS for value in (q+dq,r+dr))+(str(user_id),)).fetchone()


def _battle(conn,battle_id,user_id,lock=True):
    suffix=' FOR UPDATE' if lock else ''
    row=conn.execute('''SELECT id,attacker_user_id,general_id,target_q,target_r,source_q,source_r,
        target_owner_type,target_owner_id,purpose,status,round_number,created_turn,last_side,destroyed_at,deployment_locked
        FROM game_battles WHERE id=%s'''+suffix,(battle_id,)).fetchone()
    if not row or row[1]!=user_id:raise HTTPException(404,'Бой не найден')
    return dict(zip(BATTLE_FIELDS,row))


def _units(conn,battle_id):
    rows=conn.execute('''SELECT id,battle_id,side,assignment_id,unit_id,is_general,name,image_path,x,y,
        health,max_health,attack,defense,armor,attack_range,speed,initiative,active,moved,attacked,is_wall
        FROM game_battle_units WHERE battle_id=%s ORDER BY id''',(battle_id,)).fetchall()
    return [dict(zip(UNIT_FIELDS,row)) for row in rows]


def _event(conn,battle,kind,details):
    conn.execute('INSERT INTO game_battle_events(battle_id,round_number,event_type,details) VALUES (%s,%s,%s,%s)',
                 (battle['id'],battle['round_number'],kind,Jsonb(details)))


def _state(conn,battle):
    events=conn.execute('SELECT id,round_number,event_type,details FROM game_battle_events WHERE battle_id=%s ORDER BY id',
                        (battle['id'],)).fetchall()
    units=_units(conn,battle['id'])
    side,eligible=_next_actor(battle,units) if battle['status']=='active' and battle['deployment_locked'] else (None,[])
    return {'battle':battle,'units':units,'current_side':side,'eligible_unit_ids':[u['id'] for u in eligible],
            'events':[dict(zip(('id','round','type','details'),row)) for row in events]}


def _activate_general(conn,battle,units):
    attackers=sum(unit['side']=='attacker' and not unit['is_general'] and unit['health']>0 for unit in units)
    defenders=sum(unit['side']=='defender' and not unit.get('is_wall') and unit['health']>0 for unit in units)
    general=next((unit for unit in units if unit['is_general']),None)
    if general and not general['active'] and attackers<defenders:
        conn.execute('UPDATE game_battle_units SET active=true WHERE id=%s',(general['id'],))
        general['active']=True
        _event(conn,battle,'general_activated',{'unit_id':general['id']})


def _next_actor(battle,units):
    available=[u for u in units if u['health']>0 and u['active'] and not u['attacked'] and not u.get('is_wall')
               and not (u['side']=='attacker' and u['attack_range']>2 and u['moved'])]
    if not available:return None,[]
    bonus=2 if battle['round_number']==1 else 1 if battle['round_number']==2 else 0
    score=max(u['initiative']+(bonus if u['side']=='attacker' else 0) for u in available)
    tied=[u for u in available if u['initiative']+(bonus if u['side']=='attacker' else 0)==score]
    sides={u['side'] for u in tied}
    side=('defender' if battle.get('last_side')=='attacker' else 'attacker') if len(sides)>1 else next(iter(sides))
    return side,[u for u in tied if u['side']==side]


def _record_side(conn,battle,side):
    battle['last_side']=side
    conn.execute('UPDATE game_battles SET last_side=%s WHERE id=%s',(side,battle['id']))


def _drive_ai(conn,battle,units):
    """Resolve defender activations until the next player activation or result."""
    while battle['status']=='active':
        side,tied=_next_actor(battle,units)
        if side=='attacker':return
        if side is None:
            battle['round_number']+=1
            conn.execute('UPDATE game_battles SET round_number=%s WHERE id=%s',(battle['round_number'],battle['id']))
            conn.execute('UPDATE game_battle_units SET moved=false,attacked=false WHERE battle_id=%s',(battle['id'],))
            for unit in units:unit['moved']=False;unit['attacked']=False
            _event(conn,battle,'round_started',{'round':battle['round_number']})
            continue
        defender=min(tied,key=lambda u:u['id'])
        targets=[u for u in units if u['side']=='attacker' and u['health']>0 and u['active']]
        if not targets:
            _finish(conn,battle,'defender');return
        adjacent=[u for u in targets if 0<distance((defender['x'],defender['y']),(u['x'],u['y']))<=defender['attack_range']]
        if not adjacent:
            target=min(targets,key=lambda u:distance((defender['x'],defender['y']),(u['x'],u['y'])))
            occupied={(u['x'],u['y']) for u in units if u['health']>0 and u['id']!=defender['id']}
            options=[(x,y) for x in range(10) for y in range(10)
                     if reachable((defender['x'],defender['y']),(x,y),defender['speed'],occupied)]
            if options:
                next_cell=min(options,key=lambda p:distance(p,(target['x'],target['y'])))
                conn.execute('UPDATE game_battle_units SET x=%s,y=%s WHERE id=%s',(*next_cell,defender['id']))
                defender['x'],defender['y']=next_cell
                _event(conn,battle,'move',{'unit_id':defender['id'],'x':next_cell[0],'y':next_cell[1]})
            adjacent=[u for u in targets if 0<distance((defender['x'],defender['y']),(u['x'],u['y']))<=defender['attack_range']]
        if adjacent:
            target=min(adjacent,key=lambda u:(u['health'],u['id']))
            roll_a,roll_d=random.randint(1,6),random.randint(1,6)
            points=damage(defender['attack'],target['defense'],target['armor'],roll_a,roll_d)
            target['health']=max(0,target['health']-points)
            conn.execute('UPDATE game_battle_units SET health=%s WHERE id=%s',(target['health'],target['id']))
            _event(conn,battle,'attack',{'attacker_id':defender['id'],'target_id':target['id'],
                'attack_roll':roll_a,'defense_roll':roll_d,'damage':points,'remaining':target['health']})
            _activate_general(conn,battle,units)
        defender['attacked']=True
        conn.execute('UPDATE game_battle_units SET attacked=true WHERE id=%s',(defender['id'],))
        _record_side(conn,battle,'defender')
        if not any(u['health']>0 for u in units if u['side']=='attacker'):
            _finish(conn,battle,'defender');return


def _pay_raid(conn,battle):
    target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',
                        (battle['target_q'],battle['target_r'])).fetchone()
    if not target or target[0].get('Тип владельца','Ничейная территория')!=battle['target_owner_type'] or str(target[0].get('Владелец') or '')!=battle['target_owner_id']:
        raise HTTPException(409,'Владелец гекса изменился во время боя')
    level=max(0,min(7,_int(target[0].get('Уровень гекса'))))
    balance=conn.execute('''SELECT gold,peasant_percent,peasant_nominal,morale_penalty
        FROM raid_balance WHERE building_level=%s''',(level,)).fetchone()
    if not balance:raise HTTPException(409,'Не задан баланс грабежа')
    gold,percent,nominal,morale=balance
    conn.execute('''INSERT INTO game_hex_raids(q,r,last_turn) VALUES (%s,%s,%s)
        ON CONFLICT(q,r) DO UPDATE SET last_turn=EXCLUDED.last_turn''',
        (battle['target_q'],battle['target_r'],battle['created_turn']))
    if gold:
        conn.execute('UPDATE game_wallets SET gold=gold+%s WHERE user_id=%s',(gold,battle['attacker_user_id']))
        conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason,related_general_id) VALUES (%s,%s,'raid',%s)",
                     (battle['attacker_user_id'],gold,battle['general_id']))
    peasants=0
    if battle['target_owner_type']!='Игрок' or battle['target_owner_id']!=str(battle['attacker_user_id']):
        peasants=max(1,round(nominal*percent/100))
        conn.execute('''INSERT INTO barony_peasant_reserve(user_id,quantity) VALUES (%s,%s)
            ON CONFLICT(user_id) DO UPDATE SET quantity=barony_peasant_reserve.quantity+EXCLUDED.quantity''',
            (battle['attacker_user_id'],peasants))
    else:
        cells=conn.execute('''SELECT q,r FROM hexes WHERE data->>'Тип владельца'='Игрок'
            AND data->>'Владелец'=%s''',(str(battle['attacker_user_id']),)).fetchall()
        for q,r in cells:
            ring=distance((q,r),(battle['target_q'],battle['target_r']))
            if ring>3:continue
            penalty=morale/(2**ring)
            conn.execute('''INSERT INTO game_hex_morale(q,r,morale) VALUES (%s,%s,%s)
                ON CONFLICT(q,r) DO UPDATE SET morale=greatest(0,game_hex_morale.morale-%s)''',
                (q,r,max(0,100-penalty),penalty))
    _event(conn,battle,'raid_reward',{'gold':gold,'peasants':peasants})


def create_encounter_battle(conn,user_id,general_id,source,target,target_data,turn,kind):
    """Create a random battle in the same transaction as strategic movement."""
    q,r=target
    conn.execute('SELECT pg_advisory_xact_lock(%s,%s)',(q,r))
    if conn.execute("SELECT 1 FROM game_battles WHERE status='active' AND (general_id=%s OR (target_q=%s AND target_r=%s))",
                    (general_id,q,r)).fetchone():
        raise HTTPException(409,'На гексе уже идёт бой')
    general=conn.execute('''SELECT pg.name,pg.icon,gc.health,gc.attack+pg.attack_bonus,
        gc.defense+pg.defense_bonus,gc.speed,gc.initiative FROM player_generals pg
        JOIN general_catalog gc ON gc.id=pg.catalog_id WHERE pg.id=%s FOR UPDATE''',(general_id,)).fetchone()
    attackers=conn.execute('''SELECT pgu.id,uc.id,uc.name,uc.image_path,pgu.current_health,uc.health,
        uc.attack,uc.defense,uc.armor,uc.attack_range,uc.speed,uc.initiative
        FROM player_general_units pgu JOIN unit_catalog uc ON uc.id=pgu.unit_id
        WHERE pgu.general_id=%s AND pgu.status='ready' ORDER BY pgu.slot FOR UPDATE OF pgu''',(general_id,)).fetchall()
    prefix='units/animal-%' if kind=='animals' else 'units/barbarians-%'
    candidates=[dict(zip(('id','name','image_path','health','attack','defense','armor','attack_range','speed','initiative','combat_level'),row))
                for row in conn.execute('''SELECT id,name,image_path,health,attack,defense,armor,attack_range,speed,initiative,combat_level
                    FROM unit_catalog WHERE active AND image_path LIKE %s''',(prefix,)).fetchall()]
    budget=defense_budget(_int(target_data.get('Защита')),_int(target_data.get('Уровень гекса')))
    defenders=choose_defenders(candidates,budget,random)
    if not defenders:raise HTTPException(409,'В каталоге нет противников для случайной встречи')
    battle_id=conn.execute('''INSERT INTO game_battles(attacker_user_id,general_id,target_q,target_r,source_q,source_r,
        target_owner_type,target_owner_id,purpose,created_turn) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'encounter',%s) RETURNING id''',
        (user_id,general_id,q,r,source[0],source[1],target_data.get('Тип владельца','Ничейная территория'),
         str(target_data.get('Владелец') or ''),turn)).fetchone()[0]
    for index,unit in enumerate(attackers):
        conn.execute('''INSERT INTO game_battle_units(battle_id,side,assignment_id,unit_id,name,image_path,x,y,
            health,max_health,attack,defense,armor,attack_range,speed,initiative)
            VALUES (%s,'attacker',%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (battle_id,unit[0],unit[1],unit[2],unit[3],index+1,*unit[4:9],max(1,unit[9]),*unit[10:]))
    conn.execute('''INSERT INTO game_battle_units(battle_id,side,is_general,name,image_path,x,y,
        health,max_health,attack,defense,armor,attack_range,speed,initiative,active)
        VALUES (%s,'attacker',true,%s,%s,0,5,%s,%s,%s,%s,0,1,%s,%s,%s)''',
        (battle_id,general[0],general[1],general[2],general[2],general[3],general[4],general[5],general[6],len(attackers)<len(defenders)))
    for index,unit in enumerate(defenders):
        conn.execute('''INSERT INTO game_battle_units(battle_id,side,unit_id,name,image_path,x,y,
            health,max_health,attack,defense,armor,attack_range,speed,initiative)
            VALUES (%s,'defender',%s,%s,%s,8,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (battle_id,unit['id'],unit['name'],unit['image_path'],index+1,unit['health'],unit['health'],
             unit['attack'],unit['defense'],unit['armor'],max(1,unit['attack_range']),unit['speed'],unit['initiative']))
    _apply_template(conn,battle_id,user_id)
    battle=_battle(conn,battle_id,user_id)
    _event(conn,battle,'encounter',{'kind':kind,'attackers':len(attackers)+1,'defenders':len(defenders)})
    return _state(conn,battle)


def _pay_encounter(conn,battle):
    rows=conn.execute('''SELECT u.image_path,c.combat_level FROM game_battle_units u
        JOIN unit_catalog c ON c.id=u.unit_id WHERE u.battle_id=%s AND u.side='defender' AND u.health=0''',
        (battle['id'],)).fetchall()
    animals=sum(level for image,level in rows if image.startswith('units/animal-'))
    bandits=sum(level for image,level in rows if image.startswith('units/barbarians-'))
    if bandits:
        conn.execute('UPDATE game_wallets SET gold=gold+%s WHERE user_id=%s',(bandits,battle['attacker_user_id']))
        conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason,related_general_id) VALUES (%s,%s,'encounter',%s)",
                     (battle['attacker_user_id'],bandits,battle['general_id']))
    for code in ('hide','food'):
        if not animals:break
        conn.execute('''INSERT INTO game_inventory(user_id,resource_code,quantity) VALUES (%s,%s,%s)
            ON CONFLICT(user_id,resource_code) DO UPDATE SET quantity=game_inventory.quantity+EXCLUDED.quantity''',
            (battle['attacker_user_id'],code,animals))
        conn.execute("INSERT INTO game_resource_ledger(user_id,resource_code,amount,reason,related_general_id) VALUES (%s,%s,%s,'encounter',%s)",
                     (battle['attacker_user_id'],code,animals,battle['general_id']))
    _event(conn,battle,'encounter_reward',{'gold':bandits,'hide':animals,'food':animals})


def _apply_template(conn,battle_id,user_id):
    template={slot:(x,y) for slot,x,y in conn.execute('''SELECT slot,x,y FROM game_deployment_template
        WHERE user_id=%s''',(user_id,)).fetchall()}
    if not template:return
    rows=conn.execute('''SELECT u.id,COALESCE(pgu.slot,0),u.x,u.y FROM game_battle_units u
        LEFT JOIN player_general_units pgu ON pgu.id=u.assignment_id
        WHERE u.battle_id=%s AND u.side='attacker' ORDER BY u.id''',(battle_id,)).fetchall()
    positions=[template.get(slot,(x,y)) for _,slot,x,y in rows]
    if len(set(positions))!=len(positions):return
    for (unit_id,_,_,_),(x,y) in zip(rows,positions):
        conn.execute('UPDATE game_battle_units SET x=%s,y=%s WHERE id=%s',(x,y,unit_id))


def _insert_wall(conn,battle_id,level):
    health=WALL_HEALTH.get(level)
    if not health:return
    conn.execute('''INSERT INTO game_battle_units(battle_id,side,is_wall,name,image_path,x,y,
        health,max_health,attack,defense,armor,attack_range,speed,initiative,active)
        VALUES (%s,'defender',true,'Стена','',7,5,%s,%s,0,0,0,1,0,0,false)''',
        (battle_id,health,health))


def _finish(conn,battle,winner,retreat=False):
    if battle['status']!='active':raise HTTPException(409,'Бой уже завершён')
    units=_units(conn,battle['id'])
    general=conn.execute('SELECT id,user_id,last_retreat_turn FROM player_generals WHERE id=%s FOR UPDATE',(battle['general_id'],)).fetchone()
    if not general:raise HTTPException(409,'Генерал больше не существует')
    if winner=='defender' and not retreat:
        conn.execute("DELETE FROM player_general_units WHERE general_id=%s AND status='wounded'",(battle['general_id'],))
    for unit in units:
        if unit['side']!='attacker' or unit['is_general'] or unit['assignment_id'] is None:continue
        if unit['health']<=0:
            conn.execute('DELETE FROM player_general_units WHERE id=%s',(unit['assignment_id'],))
        else:
            wounded=unit['health']*5<unit['max_health']*4
            conn.execute('''UPDATE player_general_units SET current_health=%s,status=%s,recover_turn=%s WHERE id=%s''',
                         (unit['health'],'wounded' if wounded else 'ready',battle['created_turn']+2 if wounded else None,
                          unit['assignment_id']))
    if winner=='defender':
        if not retreat and battle['target_owner_type']=='Игрок' and battle['target_owner_id'].isdigit() and battle['target_owner_id']!=str(general[1]):
            conn.execute('DELETE FROM player_general_units WHERE general_id=%s',(battle['general_id'],))
            conn.execute('''UPDATE player_generals SET status='captive',captor_user_id=%s,captured_at=now(),
                q=NULL,r=NULL,previous_q=NULL,previous_r=NULL,logistics_left=0 WHERE id=%s''',
                (int(battle['target_owner_id']),battle['general_id']))
            _event(conn,battle,'captured',{'general_id':battle['general_id'],'captor_user_id':int(battle['target_owner_id'])})
        elif not retreat and general[2]==battle['created_turn']:
            home=home_hex(conn,general[1])
            if not home:raise HTTPException(409,'Не найдена территория восстановления генерала')
            conn.execute('''UPDATE player_generals SET status='recovering',recover_turn=%s,q=%s,r=%s,
                previous_q=NULL,previous_r=NULL,logistics_left=0 WHERE id=%s''',
                (battle['created_turn']+2,home[0],home[1],battle['general_id']))
            _event(conn,battle,'sent_home',{'general_id':battle['general_id']})
        else:
            conn.execute('''UPDATE player_generals SET q=%s,r=%s,previous_q=NULL,previous_r=NULL,
                logistics_left=0 WHERE id=%s''',(battle['source_q'],battle['source_r'],battle['general_id']))
    elif winner=='attacker' and battle['purpose']=='capture':
        conn.execute('SELECT pg_advisory_xact_lock(%s,%s)',(battle['target_q'],battle['target_r']))
        target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',(battle['target_q'],battle['target_r'])).fetchone()
        source=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(battle['source_q'],battle['source_r'])).fetchone()
        neighbor=_capture_neighbor(conn,battle['target_q'],battle['target_r'],general[1])
        if not target or not source or not neighbor:
            raise HTTPException(409,'Цель больше не соседствует с владениями баронства')
        if target[0].get('Тип владельца','Ничейная территория')!=battle['target_owner_type'] or str(target[0].get('Владелец') or '')!=battle['target_owner_id']:
            raise HTTPException(409,'Владелец цели изменился во время боя')
        ownership={'Тип владельца':'Игрок','Владелец':str(general[1])}
        for field in ('ID территории','Название территории','Название баронии','Цвет баронии','Герб баронии'):
            ownership[field]=neighbor[0].get(field,'')
        conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s',
                     (Jsonb(ownership),battle['target_q'],battle['target_r']))
    elif winner=='attacker' and battle['purpose']=='raid':
        _pay_raid(conn,battle)
    elif winner=='attacker' and battle['purpose']=='encounter':
        _pay_encounter(conn,battle)
    if winner=='attacker':
        general_unit=next((unit for unit in units if unit['is_general']),None)
        if general_unit and general_unit['health']*5<general_unit['max_health']*4:
            conn.execute("UPDATE player_generals SET status='recovering',recover_turn=%s WHERE id=%s",
                         (battle['created_turn']+2,battle['general_id']))
        award_general_victory(conn,battle['general_id'])
    status='retreated' if retreat else ('attacker_won' if winner=='attacker' else 'defender_won')
    conn.execute('UPDATE game_battles SET status=%s,finished_at=now() WHERE id=%s',(status,battle['id']))
    battle['status']=status
    _event(conn,battle,'finished',{'winner':winner,'purpose':battle['purpose'],'retreat':retreat})


@router.post('/api/game/hexes/{q}/{r}/battle')
async def start_capture_battle(q:int,r:int,request:Request):
    return await _start_battle(q,r,request,'capture')


@router.post('/api/game/hexes/{q}/{r}/raid')
async def start_raid_battle(q:int,r:int,request:Request):
    return await _start_battle(q,r,request,'raid')


async def _start_battle(q:int,r:int,request:Request,purpose:str):
    try:data=await request.json()
    except ValueError:raise HTTPException(400,'Укажите генерала')
    if not isinstance(data,dict) or set(data)!={'general_id'} or type(data['general_id']) is not int:
        raise HTTPException(400,'Укажите генерала')
    if (q,r) not in coordinates():raise HTTPException(404,'Гекс вне полотна')
    user_id=request.state.user['user_id']
    with connect() as conn:
        turn,_,_=_clock(conn)
        general=conn.execute('''SELECT pg.id,pg.q,pg.r,pg.status,gc.health,gc.attack+pg.attack_bonus,
            gc.defense+pg.defense_bonus,gc.initiative,gc.speed,pg.name,pg.icon,pg.logistics_left
            FROM player_generals pg JOIN general_catalog gc ON gc.id=pg.catalog_id
            WHERE pg.id=%s AND pg.user_id=%s FOR UPDATE''',(data['general_id'],user_id)).fetchone()
        if not general or general[3]!='active' or general[1] is None:
            raise HTTPException(404,'Доступный генерал не найден')
        if (q-general[1],r-general[2]) not in NEIGHBORS and not (purpose=='raid' and (q,r)==(general[1],general[2])):
            raise HTTPException(409,'Цель должна соседствовать с генералом')
        if conn.execute('SELECT 1 FROM game_turn_votes WHERE turn_number=%s AND user_id=%s',(turn,user_id)).fetchone():
            raise HTTPException(409,'Глобальный ход уже завершён')
        conn.execute('SELECT pg_advisory_xact_lock(%s,%s)',(q,r))
        source=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s',(general[1],general[2])).fetchone()
        target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',(q,r)).fetchone()
        if not source:
            raise HTTPException(409,'Исходный гекс недоступен')
        if not target or target[0].get('Категория')=='Море':
            raise HTTPException(409,'Целевой гекс недоступен')
        travel_cost=0
        if (q,r)!=(general[1],general[2]):
            travel_cost,_=movement_cost(conn,general[0],(general[1],general[2]),(q,r),source[0],target[0],general[11])
        owner_type=target[0].get('Тип владельца','Ничейная территория')
        owner_id=str(target[0].get('Владелец') or '')
        if purpose=='capture' and owner_type=='Игрок' and owner_id==str(user_id):
            raise HTTPException(409,'Свой гекс захватывать нельзя')
        if purpose=='capture' and not _capture_neighbor(conn,q,r,user_id):
            raise HTTPException(409,'Цель должна соседствовать с владениями баронства')
        if purpose=='raid':
            last=conn.execute('SELECT last_turn FROM game_hex_raids WHERE q=%s AND r=%s',(q,r)).fetchone()
            cooldown=conn.execute('SELECT cooldown_turns FROM raid_balance WHERE building_level=%s',(max(0,min(7,_int(target[0].get('Уровень гекса')))),)).fetchone()
            if not cooldown:raise HTTPException(409,'Не задан баланс грабежа')
            if last and turn-last[0]<cooldown[0]:raise HTTPException(409,'Гекс ещё нельзя грабить повторно')
        if conn.execute("SELECT 1 FROM game_battles WHERE status='active' AND (general_id=%s OR (target_q=%s AND target_r=%s))",
                        (general[0],q,r)).fetchone():
            raise HTTPException(409,'Бой уже идёт')
        attackers=conn.execute('''SELECT pgu.id,uc.id,uc.name,uc.image_path,pgu.current_health,uc.health,
            uc.attack,uc.defense,uc.armor,uc.attack_range,uc.speed,uc.initiative
            FROM player_general_units pgu JOIN unit_catalog uc ON uc.id=pgu.unit_id
            WHERE pgu.general_id=%s AND pgu.status='ready' ORDER BY pgu.slot FOR UPDATE OF pgu''',(general[0],)).fetchall()
        building=max(0,min(7,_int(target[0].get('Уровень гекса'))))
        budget=defense_budget(_int(target[0].get('Защита')),building)
        prefix='units/barbarians-%' if owner_type=='Ничейная территория' else 'units/unit-%'
        candidates=[dict(zip(('id','name','image_path','health','attack','defense','armor','attack_range','speed','initiative','combat_level'),row))
                    for row in conn.execute('''SELECT id,name,image_path,health,attack,defense,armor,attack_range,speed,initiative,combat_level
                        FROM unit_catalog WHERE active AND image_path LIKE %s''',(prefix,)).fetchall()]
        defenders=choose_defenders(candidates,budget,random)
        if not defenders:raise HTTPException(409,'Нет доступных защитников для этого гекса')
        battle_id=conn.execute('''INSERT INTO game_battles(attacker_user_id,general_id,target_q,target_r,source_q,source_r,
            target_owner_type,target_owner_id,purpose,created_turn) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (user_id,general[0],q,r,general[1],general[2],owner_type,owner_id,purpose,turn)).fetchone()[0]
        for index,unit in enumerate(attackers):
            conn.execute('''INSERT INTO game_battle_units(battle_id,side,assignment_id,unit_id,name,image_path,x,y,
                health,max_health,attack,defense,armor,attack_range,speed,initiative)
                VALUES (%s,'attacker',%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (battle_id,unit[0],unit[1],unit[2],unit[3],index+1,*unit[4:9],max(1,unit[9]),*unit[10:]))
        conn.execute('''INSERT INTO game_battle_units(battle_id,side,is_general,name,image_path,x,y,
            health,max_health,attack,defense,armor,attack_range,speed,initiative,active)
            VALUES (%s,'attacker',true,%s,%s,0,5,%s,%s,%s,%s,0,1,%s,%s,%s)''',
            (battle_id,general[9],general[10],general[4],general[4],general[5],general[6],general[8],general[7],len(attackers)<len(defenders)))
        for index,unit in enumerate(defenders):
            conn.execute('''INSERT INTO game_battle_units(battle_id,side,unit_id,name,image_path,x,y,
                health,max_health,attack,defense,armor,attack_range,speed,initiative)
                VALUES (%s,'defender',%s,%s,%s,8,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (battle_id,unit['id'],unit['name'],unit['image_path'],index+1,unit['health'],unit['health'],
                 unit['attack'],unit['defense'],unit['armor'],max(1,unit['attack_range']),unit['speed'],unit['initiative']))
        _insert_wall(conn,battle_id,building)
        _apply_template(conn,battle_id,user_id)
        conn.execute('''UPDATE player_generals SET previous_q=q,previous_r=r,q=%s,r=%s,
            logistics_left=logistics_left-%s WHERE id=%s''',(q,r,travel_cost,general[0]))
        battle=_battle(conn,battle_id,user_id)
        _event(conn,battle,'started',{'attackers':len(attackers)+1,'defenders':len(defenders)})
        return _state(conn,battle)


@router.get('/api/game/battles/{battle_id}')
def get_battle(battle_id:int,request:Request):
    with connect() as conn:
        return _state(conn,_battle(conn,battle_id,request.state.user['user_id'],False))


@router.get('/api/game/active-battle')
def get_active_battle(request:Request):
    with connect() as conn:
        row=conn.execute("SELECT id FROM game_battles WHERE attacker_user_id=%s AND status='active' ORDER BY id LIMIT 1",
                         (request.state.user['user_id'],)).fetchone()
        return _state(conn,_battle(conn,row[0],request.state.user['user_id'],False)) if row else {'battle':None}


@router.post('/api/game/battles/{battle_id}/deployment')
async def save_deployment(battle_id:int,request:Request):
    try:data=await request.json()
    except ValueError:raise HTTPException(400,'Укажите расстановку')
    positions=data.get('positions') if isinstance(data,dict) and set(data)=={'positions'} else None
    if not isinstance(positions,list) or not 1<=len(positions)<=6 or any(
        not isinstance(item,dict) or set(item)!={'id','x','y'} or any(type(item[key]) is not int for key in item)
        for item in positions):
        raise HTTPException(400,'Укажите позиции всех своих бойцов')
    if any(not 0<=item['x']<=3 or not 0<=item['y']<=9 for item in positions):
        raise HTTPException(400,'Расстановка возможна в первых четырёх столбцах')
    if len({item['id'] for item in positions})!=len(positions) or len({(item['x'],item['y']) for item in positions})!=len(positions):
        raise HTTPException(400,'Бойцы не могут делить клетку')
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['status']!='active' or battle['deployment_locked'] or battle['round_number']!=1:
            raise HTTPException(409,'Расстановка уже завершена')
        units=_units(conn,battle_id)
        attackers={unit['id']:unit for unit in units if unit['side']=='attacker' and unit['health']>0}
        if {item['id'] for item in positions}!=set(attackers):
            raise HTTPException(400,'Укажите каждого своего бойца ровно один раз')
        slots={row[0]:row[1] for row in conn.execute('''SELECT id,slot FROM player_general_units
            WHERE general_id=%s''',(battle['general_id'],)).fetchall()}
        conn.execute('DELETE FROM game_deployment_template WHERE user_id=%s',(battle['attacker_user_id'],))
        for item in positions:
            unit=attackers[item['id']]
            slot=0 if unit['is_general'] else slots.get(unit['assignment_id'])
            if slot is None:raise HTTPException(409,'Состав армии изменился')
            conn.execute('UPDATE game_battle_units SET x=%s,y=%s WHERE id=%s',(item['x'],item['y'],item['id']))
            conn.execute('''INSERT INTO game_deployment_template(user_id,slot,x,y)
                VALUES (%s,%s,%s,%s)''',(battle['attacker_user_id'],slot,item['x'],item['y']))
            unit['x'],unit['y']=item['x'],item['y']
        conn.execute('UPDATE game_battles SET deployment_locked=true WHERE id=%s',(battle_id,))
        battle['deployment_locked']=True
        _event(conn,battle,'deployment_locked',{})
        _drive_ai(conn,battle,units)
        return _state(conn,battle)


@router.post('/api/game/battles/{battle_id}/units/{unit_id}/move')
async def move_unit(battle_id:int,unit_id:int,request:Request):
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'x','y','round'} or any(type(data[key]) is not int for key in data):
        raise HTTPException(400,'Укажите клетку и номер раунда')
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['status']!='active' or not battle['deployment_locked'] or battle['round_number']!=data['round']:
            raise HTTPException(409,'Бой или раунд уже завершён')
        units=_units(conn,battle_id)
        unit=next((item for item in units if item['id']==unit_id),None)
        if not unit or unit['side']!='attacker' or not unit['active'] or unit['health']<=0 or unit['moved'] or unit['attacked']:
            raise HTTPException(409,'Юнит не может двигаться')
        side,tied=_next_actor(battle,units)
        if side!='attacker' or unit not in tied:raise HTTPException(409,'Сейчас действует другой юнит')
        occupied={(item['x'],item['y']) for item in units if item['health']>0 and item['id']!=unit_id}
        if not reachable((unit['x'],unit['y']),(data['x'],data['y']),unit['speed'],occupied):
            raise HTTPException(409,'Клетка недоступна')
        conn.execute('UPDATE game_battle_units SET x=%s,y=%s,moved=true,attacked=%s WHERE id=%s',
                     (data['x'],data['y'],unit['attack_range']>2,unit_id))
        _event(conn,battle,'move',{'unit_id':unit_id,'x':data['x'],'y':data['y']})
        if unit['attack_range']>2:
            unit['moved']=True;unit['attacked']=True
            _record_side(conn,battle,'attacker')
            _drive_ai(conn,battle,units)
        return _state(conn,battle)


@router.post('/api/game/battles/{battle_id}/units/{unit_id}/attack')
async def attack_unit(battle_id:int,unit_id:int,request:Request):
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'target_id','round'} or any(type(data[key]) is not int for key in data):
        raise HTTPException(400,'Укажите цель и номер раунда')
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['status']!='active' or not battle['deployment_locked'] or battle['round_number']!=data['round']:
            raise HTTPException(409,'Бой или раунд уже завершён')
        units=_units(conn,battle_id)
        attacker=next((item for item in units if item['id']==unit_id),None)
        target=next((item for item in units if item['id']==data['target_id']),None)
        if not attacker or not target or attacker['side']!='attacker' or target['side']!='defender' or not attacker['active'] or attacker['health']<=0 or target['health']<=0 or attacker['attacked']:
            raise HTTPException(409,'Атака недоступна')
        if attacker['moved'] and attacker['attack_range']>2:
            raise HTTPException(409,'Стрелок выбирает движение или выстрел')
        side,tied=_next_actor(battle,units)
        if side!='attacker' or attacker not in tied:raise HTTPException(409,'Сейчас действует другой юнит')
        separation=distance((attacker['x'],attacker['y']),(target['x'],target['y']))
        if separation>attacker['attack_range'] or separation==0:
            raise HTTPException(409,'Цель вне дальности')
        attack_score=attacker['attack']//2 if separation==1 and attacker['attack_range']>2 else attacker['attack']
        roll_a,roll_d=random.randint(1,6),random.randint(1,6)
        points=damage(max(1,attack_score),target['defense'],target['armor'],roll_a,roll_d)
        remaining=max(0,target['health']-points)
        conn.execute('UPDATE game_battle_units SET health=%s WHERE id=%s',(remaining,target['id']))
        conn.execute('UPDATE game_battle_units SET attacked=true WHERE id=%s',(attacker['id'],))
        _event(conn,battle,'attack',{'attacker_id':attacker['id'],'target_id':target['id'],
                                     'attack_roll':roll_a,'defense_roll':roll_d,'damage':points,'remaining':remaining})
        target['health']=remaining
        _activate_general(conn,battle,units)
        if all(item['health']<=0 for item in units if item['side']=='defender'):
            _finish(conn,battle,'attacker')
        else:
            attacker['attacked']=True
            _record_side(conn,battle,'attacker')
            _drive_ai(conn,battle,units)
        return _state(conn,battle)


@router.post('/api/game/battles/{battle_id}/end-turn')
async def end_battle_round(battle_id:int,request:Request):
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'round'} or type(data['round']) is not int:
        raise HTTPException(400,'Укажите номер раунда')
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['status']!='active' or not battle['deployment_locked'] or battle['round_number']!=data['round']:
            raise HTTPException(409,'Бой или раунд уже завершён')
        units=_units(conn,battle_id)
        conn.execute("UPDATE game_battle_units SET attacked=true WHERE battle_id=%s AND side='attacker' AND health>0",
                     (battle_id,))
        for unit in units:
            if unit['side']=='attacker' and unit['health']>0:unit['attacked']=True
        _event(conn,battle,'attacker_passed',{})
        _drive_ai(conn,battle,units)
        return _state(conn,battle)


@router.post('/api/game/battles/{battle_id}/retreat')
async def retreat_battle(battle_id:int,request:Request):
    data=await request.json()
    if not isinstance(data,dict) or set(data)!={'round'} or type(data['round']) is not int:
        raise HTTPException(400,'Укажите номер раунда')
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['status']!='active' or battle['round_number']!=data['round'] or battle['round_number']<2:
            raise HTTPException(409,'Отступление доступно со второго раунда')
        general=conn.execute('SELECT last_retreat_turn FROM player_generals WHERE id=%s FOR UPDATE',(battle['general_id'],)).fetchone()
        if not general or general[0]==battle['created_turn']:
            raise HTTPException(409,'Генерал уже отступал в этом глобальном ходу')
        _finish(conn,battle,'defender',retreat=True)
        conn.execute('UPDATE player_generals SET last_retreat_turn=%s WHERE id=%s',(battle['created_turn'],battle['general_id']))
        _event(conn,battle,'retreated',{})
        return _state(conn,battle)


@router.post('/api/game/battles/{battle_id}/destroy')
def destroy_after_raid(battle_id:int,request:Request):
    with connect() as conn:
        battle=_battle(conn,battle_id,request.state.user['user_id'])
        if battle['purpose']!='raid' or battle['status']!='attacker_won' or battle['destroyed_at'] is not None:
            raise HTTPException(409,'Разрушение сейчас недоступно')
        if battle['target_owner_type']=='Игрок' and battle['target_owner_id']==str(battle['attacker_user_id']):
            raise HTTPException(409,'Свои постройки разрушать после грабежа нельзя')
        target=conn.execute('SELECT data FROM hexes WHERE q=%s AND r=%s FOR UPDATE',
                            (battle['target_q'],battle['target_r'])).fetchone()
        if not target or target[0].get('Тип владельца','Ничейная территория')!=battle['target_owner_type'] or str(target[0].get('Владелец') or '')!=battle['target_owner_id']:
            raise HTTPException(409,'Владелец гекса изменился')
        old=max(0,min(7,_int(target[0].get('Уровень гекса'))))
        if old==0:raise HTTPException(409,'На гексе нет постройки')
        new=old-1
        conn.execute('UPDATE hexes SET data=data || %s,updated_at=now() WHERE q=%s AND r=%s',
                     (Jsonb({'Уровень гекса':str(new),'Постройка':HEX_BUILDINGS[new]}),battle['target_q'],battle['target_r']))
        conn.execute('UPDATE game_battles SET destroyed_at=now() WHERE id=%s',(battle_id,))
        battle['destroyed_at']=True
        _event(conn,battle,'building_destroyed',{'old_level':old,'new_level':new})
        return {'destroyed':True,'old_level':old,'new_level':new,'building':HEX_BUILDINGS[new],
                'battle':_state(conn,battle)}
