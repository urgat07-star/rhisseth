"""Administrator-maintained extractable and produced resource catalogues."""
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from db import connect

router = APIRouter()
KINDS = {
    'extractable': ('extractable_resources', ('code','name','typical_locations','purpose','active')),
    'produced': ('produced_resources', ('code','name','ingredients','required_building','purpose','active')),
}


async def payload(request):
    raw = await request.body()
    if len(raw) > 16000:
        raise HTTPException(413, 'Слишком большой запрос')
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, 'Ожидается JSON')
    if not isinstance(data, dict):
        raise HTTPException(400, 'Ожидается объект')
    return data


def definition(kind):
    if kind not in KINDS:
        raise HTTPException(404, 'Неизвестный вид ресурса')
    return KINDS[kind]


def validate(kind, data, creating):
    _, fields = definition(kind)
    expected = set(fields)
    if not creating:
        expected.remove('code')
    if set(data) != expected:
        raise HTTPException(400, 'Передайте все поля ресурса')
    if creating and (not isinstance(data['code'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', data['code'])):
        raise HTTPException(400, 'Код: 2–64 латинских символа, цифры или подчёркивание')
    for field in expected - {'active'}:
        limit = 120 if field == 'name' else 200 if field == 'required_building' else 2000
        if not isinstance(data[field], str) or len(data[field].strip()) > limit:
            raise HTTPException(400, f'Некорректное поле: {field}')
    if not data['name'].strip() or type(data['active']) is not bool:
        raise HTTPException(400, 'Заполните название и доступность')


def rows(conn, kind):
    table, fields = definition(kind)
    result = conn.execute(f'SELECT {",".join(fields)} FROM {table} ORDER BY name').fetchall()
    return [dict(zip(fields, row)) for row in result]


@router.get('/admin/resources')
def resources_page():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend/resources-admin.html')


@router.get('/api/admin/resources')
def resource_catalogues():
    with connect() as conn:
        return {kind: rows(conn, kind) for kind in KINDS}


@router.post('/api/admin/resources/{kind}')
async def create_resource(kind: str, request: Request):
    data = await payload(request)
    validate(kind, data, True)
    table, fields = definition(kind)
    values = [data[field].strip() if isinstance(data[field], str) else data[field] for field in fields]
    with connect() as conn:
        try:
            conn.execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES ({",".join("%s" for _ in fields)})', values)
        except Exception as error:
            if 'unique' in str(error).lower():
                raise HTTPException(409, 'Код или название уже существует')
            raise
    return {'created': True, 'code': data['code']}


@router.patch('/api/admin/resources/{kind}/{code}')
async def edit_resource(kind: str, code: str, request: Request):
    data = await payload(request)
    validate(kind, data, False)
    table, fields = definition(kind)
    editable = tuple(field for field in fields if field != 'code')
    values = [data[field].strip() if isinstance(data[field], str) else data[field] for field in editable]
    with connect() as conn:
        row = conn.execute(f'UPDATE {table} SET {",".join(f"{field}=%s" for field in editable)},updated_at=now() WHERE code=%s RETURNING code', (*values, code)).fetchone()
        if not row:
            raise HTTPException(404, 'Ресурс не найден')
    return {'saved': True}
