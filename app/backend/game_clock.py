"""Persistent seasonal clock; all changes are serialized on the clock row."""
from datetime import timedelta
from collections import defaultdict
import random
from fastapi import APIRouter, HTTPException, Request
from db import connect
from economy_rules import generated_food, grow_population

router = APIRouter()
SEASONS = ('Весна', 'Лето', 'Осень', 'Зима')
PRESENCE_WINDOW_SECONDS = 90


def _annual_resource_income(conn, year):
    """Credit the resource part of an already-locked annual calculation."""
    catalogue={name:(code,is_food) for code,name,is_food in conn.execute(
        'SELECT code,name,is_food FROM game_resources').fetchall()}
    income=defaultdict(lambda:defaultdict(int))
    for owner,data in conn.execute("""SELECT (data->>'Владелец')::integer,data FROM hexes
        WHERE data->>'Тип владельца'='Игрок' AND data->>'Владелец'~'^[0-9]+$'""").fetchall():
        name=str(data.get('Основной ресурс') or '').strip()
        item=catalogue.get({'Киты':'Морской зверь'}.get(name,name))
        try: quantity=max(0,int(data.get('Богатство ресурса') or 0))
        except (TypeError,ValueError): quantity=0
        if item and quantity:
            code,is_food=item
            income[owner]['food' if is_food else code]+=quantity
    for user_id,resources in income.items():
        for code,quantity in resources.items():
            conn.execute('''INSERT INTO game_inventory(user_id,resource_code,quantity) VALUES (%s,%s,%s)
                ON CONFLICT(user_id,resource_code) DO UPDATE
                SET quantity=game_inventory.quantity+EXCLUDED.quantity''',(user_id,code,quantity))
            conn.execute("""INSERT INTO game_resource_ledger(user_id,resource_code,amount,reason)
                VALUES (%s,%s,%s,'annual_economy')""",(user_id,code,quantity))


def _integer(value, default=0, low=0, high=None):
    try: result=int(value)
    except (TypeError,ValueError): result=default
    result=max(low,result)
    return min(high,result) if high is not None else result


def _proportional(total, weighted):
    """Allocate an integer total deterministically by positive coordinate weights."""
    weights={key:max(0,int(value)) for key,value in weighted.items() if value>0}
    denominator=sum(weights.values())
    if total<=0 or not denominator:return {key:0 for key in weighted}
    base={key:total*weight//denominator for key,weight in weights.items()}
    remainder=total-sum(base.values())
    order=sorted(weights,key=lambda key:(-(total*weights[key]%denominator),key))
    for key in order[:remainder]:base[key]+=1
    return {key:base.get(key,0) for key in weighted}


def _annual_population_and_tax(conn, year, rng=random):
    levels={row[0]:row[1:] for row in conn.execute('''SELECT level,population_limit,
        population_growth_min,population_growth_max,tax_min,tax_max
        FROM territory_level_economy ORDER BY level''').fetchall()}
    rows=[]
    for q,r,data in conn.execute('SELECT q,r,data FROM hexes ORDER BY r,q FOR UPDATE').fetchall():
        level=_integer(data.get('Уровень гекса'),1,1,8)
        population=_integer(data.get('Население'),1)
        pure_sea=data.get('Категория')=='Море' and data.get('Остров')!='Да'
        if pure_sea:population=0
        terrain={part.strip().casefold() for part in str(data.get('Тип местности') or '').split('/')}
        owner_type=str(data.get('Тип владельца') or 'Ничейная территория')
        owner_id=str(data.get('Владелец') or '')
        barony=_integer(data.get('ID территории'),0,0) or None
        manual=conn.execute('''SELECT COALESCE(sum(amount),0) FROM hex_population_events
            WHERE year=%s AND q=%s AND r=%s''',(year,q,r)).fetchone()[0]
        food_production=0 if pure_sea else generated_food(_integer(data.get('Плодородие')),population,
            mountain=bool(terrain & {'горы','высокогорье'}),neutral=owner_type!='Игрок')
        rows.append({'q':q,'r':r,'data':data,'level':level,'population':population,
            'pure_sea':pure_sea,'owner_type':owner_type,'owner_id':owner_id,'barony':barony,
            'food':food_production,'food_production':food_production,'reserve_food':0,
            'manual':manual,'famine':0,'federal_used':0})

    player_groups=defaultdict(list)
    for item in rows:
        if item['owner_type']=='Игрок' and item['owner_id'].isdigit():player_groups[int(item['owner_id'])].append(item)
        elif item['food']<0:item['famine']=min(item['population'],-item['food'])
    for user_id,items in player_groups.items():
        reserve=conn.execute('SELECT quantity FROM barony_peasant_reserve WHERE user_id=%s',(user_id,)).fetchone()
        reserve=reserve[0] if reserve else 0
        capital=conn.execute('''SELECT s.q,s.r FROM player_baronies b JOIN barony_start_hexes s ON s.barony_id=b.id
            WHERE b.user_id=%s ORDER BY s.position LIMIT 1''',(user_id,)).fetchone()
        if reserve and capital:
            capital_item=next((item for item in items if (item['q'],item['r'])==capital),None)
            if capital_item:
                capital_item['reserve_food']=reserve
                capital_item['food']-=reserve
        inventory=conn.execute("""SELECT quantity FROM game_inventory
            WHERE user_id=%s AND resource_code='food' FOR UPDATE""",(user_id,)).fetchone()
        stock=inventory[0] if inventory else 0
        balance=sum(item['food'] for item in items)
        if balance>=0:
            conn.execute("""INSERT INTO game_inventory(user_id,resource_code,quantity) VALUES (%s,'food',%s)
                ON CONFLICT(user_id,resource_code) DO UPDATE SET quantity=game_inventory.quantity+EXCLUDED.quantity""",
                (user_id,balance))
        else:
            used=min(stock,-balance); shortage=max(0,-balance-stock)
            if used:conn.execute("UPDATE game_inventory SET quantity=quantity-%s WHERE user_id=%s AND resource_code='food'",(used,user_id))
            deficits={(item['q'],item['r']):-item['food'] for item in items if item['food']<0}
            used_by_hex=_proportional(used,deficits); famine_by_hex=_proportional(shortage,deficits)
            for item in items:
                key=(item['q'],item['r']);item['federal_used']=used_by_hex.get(key,0)
                item['famine']=min(item['population'],famine_by_hex.get(key,0))

    buildings={1:'нет построек',2:'Лагерь',3:'Поселение',4:'Деревня',5:'Крепость',6:'Замок',7:'Город',8:'Столица'}
    for item in rows:
        limit,growth_min,growth_max,tax_min,tax_max=levels[item['level']]
        survivor=max(0,item['population']-item['famine'])
        if item['pure_sea']:grown=0
        elif item['owner_type']=='Ничейная территория' and survivor==0:grown=1
        elif survivor>=limit:grown=survivor
        else:grown=grow_population(survivor,limit,growth_min,growth_max,rng)
        growth=max(0,grown-survivor)
        state=conn.execute('SELECT double_capacity_years FROM hex_economy_state WHERE q=%s AND r=%s FOR UPDATE',(item['q'],item['r'])).fetchone()
        years=(state[0] if state else 0)+1 if item['level']<8 and grown>=2*limit else 0
        promote=years>=5 and item['level']<8
        level_after=item['level']+1 if promote else item['level']
        years=0 if promote else years
        conn.execute('''INSERT INTO hex_economy_state(q,r,double_capacity_years) VALUES (%s,%s,%s)
            ON CONFLICT(q,r) DO UPDATE SET double_capacity_years=EXCLUDED.double_capacity_years''',(item['q'],item['r'],years))
        tax=rng.randint(tax_min,tax_max) if item['owner_type']=='Игрок' and item['owner_id'].isdigit() else 0
        if tax:
            user_id=int(item['owner_id'])
            conn.execute('INSERT INTO game_wallets(user_id,gold) VALUES (%s,%s) ON CONFLICT(user_id) DO UPDATE SET gold=game_wallets.gold+EXCLUDED.gold',(user_id,tax))
            conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason) VALUES (%s,%s,'annual_tax')",(user_id,tax))
        previous=conn.execute('''SELECT population_after FROM hex_economy_history
            WHERE q=%s AND r=%s AND year<%s ORDER BY year DESC LIMIT 1''',(item['q'],item['r'],year)).fetchone()
        population_before=previous[0] if previous else max(0,item['population']-item['manual'])
        conn.execute('''UPDATE hexes SET data=data || jsonb_build_object('Население',%s::text,'Уровень гекса',%s::text,'Постройка',%s::text),updated_at=now()
            WHERE q=%s AND r=%s''',(str(grown),str(level_after),buildings[level_after],item['q'],item['r']))
        conn.execute('''INSERT INTO hex_economy_history(year,q,r,owner_type,owner_id,barony_id,
            population_before,food_production,reserve_food_used,food_delta,federal_food_used,famine_loss,natural_growth,manual_change,
            population_after,tax,level_before,level_after,auto_level_up)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (year,item['q'],item['r'],item['owner_type'],item['owner_id'],item['barony'],population_before,
             item['food_production'],item['reserve_food'],item['food'],item['federal_used'],item['famine'],growth,item['manual'],grown,tax,
             item['level'],level_after,promote))


def _annual_economy(conn, year, rng=random):
    if not conn.execute("SELECT to_regclass('game_economy_years')").fetchone()[0]:return
    resource_year=conn.execute('''INSERT INTO game_economy_years(year) VALUES (%s)
        ON CONFLICT(year) DO NOTHING RETURNING year''',(year,)).fetchone()
    if resource_year:_annual_resource_income(conn,year)
    if not conn.execute("SELECT to_regclass('game_population_years')").fetchone()[0]:return
    population_year=conn.execute('''INSERT INTO game_population_years(year) VALUES (%s)
        ON CONFLICT(year) DO NOTHING RETURNING year''',(year,)).fetchone()
    if population_year:_annual_population_and_tax(conn,year,rng)


def _annual_turns(conn, old, new):
    for turn in range(old+1,new+1):
        if turn % 4 == 3:  # transition after the autumn turn
            _annual_economy(conn,turn//4)


def _turn_effects(conn, new_turn):
    conn.execute('''UPDATE player_general_units pgu SET current_health=uc.health,status='ready',recover_turn=NULL
        FROM unit_catalog uc WHERE pgu.unit_id=uc.id AND pgu.status='wounded'
        AND pgu.recover_turn<=%s''', (new_turn,))
    conn.execute("UPDATE player_generals SET status='active',recover_turn=NULL WHERE status='recovering' AND recover_turn<=%s",
                 (new_turn,))
    conn.execute('''UPDATE player_generals pg SET logistics_left=gc.logistics
        FROM general_catalog gc WHERE pg.catalog_id=gc.id AND pg.status='active' ''')


def _advance(conn, old, new, action, actor=None):
    conn.execute("UPDATE game_clock SET turn_number=%s, started_at=now(), ends_at=now()+interval '12 hours' WHERE id=true", (new,))
    conn.execute('DELETE FROM game_turn_votes')
    if new > old:
        _turn_effects(conn, new)
        _annual_turns(conn,old,new)
    conn.execute('INSERT INTO game_clock_audit(actor_user_id,old_turn_number,new_turn_number,action) VALUES (%s,%s,%s,%s)', (actor, old, new, action))


def _clock(conn):
    turn, started, ends = conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true FOR UPDATE').fetchone()
    now = conn.execute('SELECT now()').fetchone()[0]
    if now >= ends:
        elapsed = (now - ends).total_seconds()
        steps = 1 + int(elapsed // (12 * 3600))
        new_turn = turn + steps
        conn.execute("UPDATE game_clock SET turn_number=%s,started_at=%s,ends_at=%s WHERE id=true", (new_turn, ends + (steps - 1) * (ends - started), ends + steps * (ends - started)))
        conn.execute('DELETE FROM game_turn_votes')
        _turn_effects(conn, new_turn)
        _annual_turns(conn,turn,new_turn)
        conn.execute('INSERT INTO game_clock_audit(old_turn_number,new_turn_number,action) VALUES (%s,%s,%s)', (turn, new_turn, 'deadline'))
        turn, started, ends = conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
    return turn, started, ends


def _eligible(conn):
    return {row[0] for row in conn.execute('''SELECT DISTINCT p.user_id FROM game_presence p
        JOIN player_baronies b ON b.user_id=p.user_id
        JOIN hexes h ON h.data->>'Владелец'=p.user_id::text AND h.data->>'Тип владельца'='Игрок'
        WHERE p.seen_at > now()-(%s * interval '1 second') ''',(PRESENCE_WINDOW_SECONDS,)).fetchall()}


def _participants(conn):
    return {row[0] for row in conn.execute('''SELECT DISTINCT b.user_id FROM player_baronies b
        JOIN hexes h ON h.data->>'Владелец'=b.user_id::text
        AND h.data->>'Тип владельца'='Игрок' ''').fetchall()}


def _payload(conn, turn, started, ends, user_id):
    eligible = _eligible(conn)
    participants = _participants(conn)
    voted = {row[0] for row in conn.execute('SELECT user_id FROM game_turn_votes WHERE turn_number=%s', (turn,)).fetchall()}
    vote_time = conn.execute('SELECT voted_at FROM game_turn_votes WHERE turn_number=%s AND user_id=%s', (turn,user_id)).fetchone() if user_id in voted else None
    skip_at = vote_time[0] + timedelta(minutes=2) if vote_time else None
    now = conn.execute('SELECT now()').fetchone()[0]
    pending_ids = participants - voted
    names = dict(conn.execute('SELECT user_id,user_login FROM users WHERE user_id=ANY(%s)',
                              (list(participants),)).fetchall()) if participants else {}
    wait_elapsed = bool(skip_at and now >= skip_at)
    pending_players = [{'id':player_id, 'login':names.get(player_id,f'Игрок {player_id}'),
                        'online':player_id in eligible,
                        'can_skip':wait_elapsed and player_id not in eligible}
                       for player_id in sorted(pending_ids)]
    skippable = next((player['id'] for player in pending_players if player['can_skip']), None)
    return {'turn':turn, 'year':turn // 4, 'season':SEASONS[turn % 4],
            'label':f'{turn // 4} год Эры Дракона, {SEASONS[turn % 4]}',
            'started_at':started.isoformat(), 'ends_at':ends.isoformat(),
            'online_players':len(eligible), 'ready_players':len(eligible & voted),
            'can_vote':user_id in eligible, 'voted':user_id in voted,
            'skip_at':skip_at.isoformat() if skip_at else None,
            'pending_players':pending_players, 'skippable_player_id':skippable,
            'can_skip':skippable is not None}


@router.post('/api/game/clock/skip')
async def skip_turn(request: Request):
    data = await request.json()
    if (not isinstance(data,dict) or set(data)!={'turn','player_id'} or
            type(data['turn']) is not int or type(data['player_id']) is not int):
        raise HTTPException(400,'Укажите номер хода и игрока')
    with connect() as conn:
        turn,started,ends = _clock(conn)
        if data['turn'] != turn:raise HTTPException(409,'Ход уже завершён; обновите карту')
        user_id=request.state.user['user_id']
        state=_payload(conn,turn,started,ends,user_id)
        if not state['voted']:raise HTTPException(403,'Сначала завершите свой ход')
        target=next((player for player in state['pending_players'] if player['id']==data['player_id']),None)
        if not target:raise HTTPException(409,'Этот игрок уже завершил ход')
        if not target['can_skip']:raise HTTPException(409,'Пропуск доступен через две минуты только для офлайн-игрока')
        conn.execute('INSERT INTO game_turn_votes(turn_number,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                     (turn,data['player_id']))
        voted = {row[0] for row in conn.execute('SELECT user_id FROM game_turn_votes WHERE turn_number=%s',(turn,)).fetchall()}
        if _participants(conn) <= voted:
            _advance(conn,turn,turn+1,'test_skip',user_id)
            turn,started,ends=conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
        return _payload(conn,turn,started,ends,user_id)


@router.get('/api/game/clock')
def get_clock(request: Request):
    with connect() as conn:
        turn, started, ends = _clock(conn)
        user_id = request.state.user['user_id']
        conn.execute('''INSERT INTO game_presence(user_id,seen_at) VALUES (%s,now())
            ON CONFLICT(user_id) DO UPDATE SET seen_at=now()''', (user_id,))
        return _payload(conn, turn, started, ends, user_id)


@router.post('/api/game/clock/end-turn')
async def vote_end_turn(request: Request):
    data = await request.json()
    if not isinstance(data, dict) or set(data) != {'turn'} or type(data['turn']) is not int or data['turn'] < 0:
        raise HTTPException(400, 'Укажите номер завершаемого хода')
    with connect() as conn:
        turn, started, ends = _clock(conn)
        if data['turn'] != turn:
            raise HTTPException(409, 'Ход уже завершён; обновите карту')
        user_id = request.state.user['user_id']
        conn.execute('''INSERT INTO game_presence(user_id,seen_at) VALUES (%s,now())
            ON CONFLICT(user_id) DO UPDATE SET seen_at=now()''', (user_id,))
        eligible = _eligible(conn)
        if user_id not in eligible:
            raise HTTPException(403, 'Для завершения хода нужна барония с территорией')
        conn.execute('INSERT INTO game_turn_votes(turn_number,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (turn, user_id))
        voted = {row[0] for row in conn.execute('SELECT user_id FROM game_turn_votes WHERE turn_number=%s', (turn,)).fetchall()}
        if _participants(conn) <= voted:
            _advance(conn, turn, turn + 1, 'votes', user_id)
            turn, started, ends = conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
        return _payload(conn, turn, started, ends, user_id)


@router.post('/api/admin/game/clock')
async def set_clock(request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    data = await request.json()
    if not isinstance(data, dict) or (set(data) != {'reset'} and set(data) != {'year', 'season'}):
        raise HTTPException(400, 'Укажите сброс либо год и сезон')
    if data.get('reset') is True and set(data) == {'reset'}:
        new_turn, action = 0, 'admin_reset'
    elif type(data.get('year')) is int and 0 <= data['year'] <= 1000000 and data.get('season') in SEASONS:
        new_turn, action = data['year'] * 4 + SEASONS.index(data['season']), 'admin_set'
    else:
        raise HTTPException(400, 'Недопустимые год или сезон')
    with connect() as conn:
        turn, _, _ = _clock(conn)
        _advance(conn, turn, new_turn, action, request.state.user['user_id'])
        turn, started, ends = conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
        return _payload(conn, turn, started, ends, request.state.user['user_id'])
