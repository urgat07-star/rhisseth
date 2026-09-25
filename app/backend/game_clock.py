"""Persistent seasonal clock; all changes are serialized on the clock row."""
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Request
from db import connect

router = APIRouter()
SEASONS = ('Весна', 'Лето', 'Осень', 'Зима')


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
        conn.execute('INSERT INTO game_clock_audit(old_turn_number,new_turn_number,action) VALUES (%s,%s,%s)', (turn, new_turn, 'deadline'))
        turn, started, ends = conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
    return turn, started, ends


def _eligible(conn):
    return {row[0] for row in conn.execute('''SELECT DISTINCT p.user_id FROM game_presence p
        JOIN player_baronies b ON b.user_id=p.user_id
        JOIN hexes h ON h.data->>'Владелец'=p.user_id::text AND h.data->>'Тип владельца'='Игрок'
        WHERE p.seen_at > now()-interval '5 minutes' ''').fetchall()}


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
    return {'turn':turn, 'year':turn // 4, 'season':SEASONS[turn % 4],
            'label':f'{turn // 4} год Эры Дракона, {SEASONS[turn % 4]}',
            'started_at':started.isoformat(), 'ends_at':ends.isoformat(),
            'online_players':len(eligible), 'ready_players':len(eligible & voted),
            'can_vote':user_id in eligible, 'voted':user_id in voted,
            'skip_at':skip_at.isoformat() if skip_at else None,
            'can_skip':bool(skip_at and now>=skip_at and participants-voted and not (eligible-voted))}


@router.post('/api/game/clock/skip')
async def skip_turn(request: Request):
    data = await request.json()
    if not isinstance(data,dict) or set(data)!={'turn'} or type(data['turn']) is not int:
        raise HTTPException(400,'Укажите номер хода')
    with connect() as conn:
        turn,started,ends = _clock(conn)
        if data['turn'] != turn:raise HTTPException(409,'Ход уже завершён; обновите карту')
        user_id=request.state.user['user_id']
        state=_payload(conn,turn,started,ends,user_id)
        if not state['voted']:raise HTTPException(403,'Сначала завершите свой ход')
        if not state['can_skip']:raise HTTPException(409,'Пропуск доступен через две минуты, если непроголосовавший соперник офлайн')
        _advance(conn,turn,turn+1,'test_skip',user_id)
        new,started,ends=conn.execute('SELECT turn_number,started_at,ends_at FROM game_clock WHERE id=true').fetchone()
        return _payload(conn,new,started,ends,user_id)


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
