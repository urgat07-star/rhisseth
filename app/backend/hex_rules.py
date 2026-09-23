"""Hex metadata never changes the raster map or grid geometry."""
import math
from fastapi import HTTPException

CATEGORIES = ('Суша', 'Побережье', 'Море')
FIELDS = ('Название', 'Название территории', 'Категория', 'Остров', 'Доля суши, %', 'Тип местности',
          'Дополнительный объект', 'Проходимость', 'Защита', 'Плодородие',
          'Опасность', 'Основной ресурс', 'Богатство ресурса', 'Глубина',
          'Течение', 'Комментарий', 'Тип владельца', 'Владелец', 'Состав ландшафта',
          'Уровень гекса', 'Постройка', 'Дорога', 'Водная переправа', 'Объекты гекса')

SEA_TERRAINS = frozenset(('Мелководье', 'Шельф', 'Открытое море', 'Глубоководье',
                          'Подводная впадина', 'Рифы', 'Ледовые воды',
                          'Штормовой район', 'Промысловая зона'))
HEX_BUILDINGS = {0: '- нет -', 1: 'Лагерь', 2: 'Поселение', 3: 'Деревня',
                 4: 'Форпост', 5: 'Крепость', 6: 'Город', 7: 'Столица'}

def validate_terrain_category(category, terrain):
    """Reject sea rules on land and land rules at sea."""
    if not category or not terrain:
        return
    names = {part.strip() for part in terrain.split('/')}
    sea = bool(names & SEA_TERRAINS)
    if category == 'Море' and (not sea or names - SEA_TERRAINS):
        raise HTTPException(400, 'Морской гекс должен иметь морской тип местности')
    if category != 'Море' and sea:
        raise HTTPException(400, 'Сухопутный или прибрежный гекс не может иметь морской тип местности')

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
