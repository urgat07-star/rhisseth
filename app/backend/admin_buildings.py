"""Administrator-maintained catalogue of additional hex buildings."""
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from db import connect

router = APIRouter()
FIELDS = ('code','name','level_1_effect','level_2_effect','level_3_effect','image_path','note','active')


async def body(request):
    raw = await request.body()
    if len(raw) > 24000:
        raise HTTPException(413, 'Слишком большой запрос')
    try:
        value = json.loads(raw)
    except ValueError:
        raise HTTPException(400, 'Ожидается JSON')
    if not isinstance(value, dict):
        raise HTTPException(400, 'Ожидается объект')
    return value


def validate(data, creating):
    expected = set(FIELDS if creating else FIELDS[1:])
    if set(data) != expected:
        raise HTTPException(400, 'Передайте все поля дополнительной постройки')
    if creating and (not isinstance(data['code'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', data['code'])):
        raise HTTPException(400, 'Некорректный код постройки')
    limits = {'name':120,'level_1_effect':2000,'level_2_effect':2000,'level_3_effect':2000,
              'image_path':500,'note':4000}
    for field, limit in limits.items():
        if not isinstance(data[field], str) or len(data[field].strip()) > limit:
            raise HTTPException(400, f'Некорректное поле: {field}')
    if not data['name'].strip() or type(data['active']) is not bool:
        raise HTTPException(400, 'Заполните название и доступность')


@router.get('/admin/buildings')
def page():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend/buildings-admin.html')


@router.get('/api/admin/buildings')
def catalogue():
    with connect() as conn:
        rows = conn.execute(f'SELECT {",".join(FIELDS)} FROM additional_building_catalog ORDER BY name').fetchall()
    return [dict(zip(FIELDS, row)) for row in rows]


@router.post('/api/admin/buildings')
async def create(request: Request):
    data = await body(request); validate(data, True)
    values = [data[field].strip() if isinstance(data[field], str) else data[field] for field in FIELDS]
    with connect() as conn:
        conn.execute(f'INSERT INTO additional_building_catalog ({",".join(FIELDS)}) VALUES ({",".join("%s" for _ in FIELDS)})', values)
    return {'created':True,'code':data['code']}


@router.patch('/api/admin/buildings/{code}')
async def edit(code: str, request: Request):
    data = await body(request); validate(data, False)
    fields = FIELDS[1:]
    values = [data[field].strip() if isinstance(data[field], str) else data[field] for field in fields]
    with connect() as conn:
        row = conn.execute(f'UPDATE additional_building_catalog SET {",".join(f"{field}=%s" for field in fields)},updated_at=now() WHERE code=%s RETURNING code', (*values,code)).fetchone()
        if not row:
            raise HTTPException(404, 'Постройка не найдена')
    return {'saved':True}
