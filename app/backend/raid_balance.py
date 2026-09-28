"""Administrator-editable initial raid values."""
from fastapi import APIRouter, HTTPException, Request
from db import connect

router = APIRouter()
FIELDS = ('gold', 'peasant_percent', 'peasant_nominal', 'morale_penalty', 'cooldown_turns')


@router.get('/api/admin/game/raid-balance')
def read_balance(request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    with connect() as conn:
        rows = conn.execute('''SELECT r.building_level,b.name,r.gold,r.peasant_percent,r.peasant_nominal,
            r.morale_penalty,r.cooldown_turns FROM raid_balance r JOIN hex_building_levels b
            ON b.level=r.building_level ORDER BY r.building_level''').fetchall()
    return {'rows': [dict(zip(('building_level','building_name',*FIELDS), row)) for row in rows]}


@router.put('/api/admin/game/raid-balance/{level}')
async def update_balance(level: int, request: Request):
    if request.state.user['role_alias'] != 'admin':
        raise HTTPException(403, 'Доступ только для администратора')
    data = await request.json()
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise HTTPException(400, 'Укажите все параметры грабежа')
    for field in FIELDS:
        limit = 100 if field in ('peasant_percent','morale_penalty','cooldown_turns') else 1000000
        if type(data[field]) is not int or not 0 <= data[field] <= limit:
            raise HTTPException(400, f'Недопустимое значение: {field}')
    with connect() as conn:
        result = conn.execute('''UPDATE raid_balance SET gold=%s,peasant_percent=%s,peasant_nominal=%s,
            morale_penalty=%s,cooldown_turns=%s WHERE building_level=%s RETURNING building_level''',
            (*(data[field] for field in FIELDS), level)).fetchone()
        if not result:
            raise HTTPException(404, 'Уровень постройки не найден')
    return {'saved':True, 'building_level':level}
