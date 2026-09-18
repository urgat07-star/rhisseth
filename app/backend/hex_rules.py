# Release review 2026-09-18 (0.0.2): Terrain categories, visible grid coordinates, revisions, and hex connectivity validation.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Hex metadata never changes the raster map or grid geometry."""
import math
from fastapi import HTTPException

CATEGORIES = ('Суша', 'Побережье', 'Море')
FIELDS = ('Название', 'Название территории', 'Категория', 'Остров', 'Доля суши, %', 'Тип местности',
          'Дополнительный объект', 'Проходимость', 'Защита', 'Плодородие',
          'Опасность', 'Основной ресурс', 'Богатство ресурса', 'Глубина',
          'Течение', 'Комментарий', 'Тип владельца', 'Владелец', 'Состав ландшафта')

def coordinates():
    width = math.sqrt(3) * 80
    return [(q, r) for r in range(math.ceil(2280 / 120))
            for q in range(math.ceil(-0.5-r/2), math.floor(3200/width+0.5-r/2)+1)]

def public_row(row):
    import json, hashlib
    result={k: v for k, v in row.items() if k != 'Пресная вода'}
    result['_revision']=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result

def category_from_share(value):
    try:
        share = float(value)
    except (ValueError, TypeError):
        raise HTTPException(400, 'Доля суши: число 0–100')
    if not math.isfinite(share) or not 0 <= share <= 100:
        raise HTTPException(400, 'Доля суши: число 0–100')
    return 'Море' if share == 0 else 'Суша' if share == 100 else 'Побережье'

def connected(cells):
    remaining = set(cells)
    if not remaining:
        return False
    pending = [remaining.pop()]
    while pending:
        q, r = pending.pop()
        for dq, dr in ((1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1)):
            neighbor = (q+dq, r+dr)
            if neighbor in remaining:
                remaining.remove(neighbor)
                pending.append(neighbor)
    return not remaining
