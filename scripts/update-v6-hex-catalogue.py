"""Apply the reviewed V6 edge-cell audit and object columns to the seed CSV."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/import/hex-initial-parameters.csv'

EDGE_SHARES = {
 (-1,1):1, (-2,3):1, (-3,5):0, (-3,6):0, (-4,7):0, (-3,7):11,
 (-4,8):97, (-3,8):80, (-5,9):0, (-4,9):94, (-3,9):90,
 (-5,10):14, (-4,10):49, (-3,10):49, (-6,11):0, (-5,11):0,
 (-4,11):0, (-3,11):0, (-6,12):0, (-5,12):5, (-4,12):0,
 (-3,12):29, (-7,13):0, (-6,13):69, (-5,13):35, (-4,13):21,
 (-3,13):7, (-7,14):99, (-6,14):98, (-5,14):90, (-4,14):99,
 (-3,14):14, (-8,15):0, (-7,15):99, (-6,15):95, (-5,15):97,
 (-4,15):43, (-3,15):0, (-8,16):99, (-7,16):92, (-6,16):96,
 (-5,16):85, (-4,16):52, (-3,16):4, (-9,17):0, (-8,17):99,
 (-7,17):100, (-6,17):100, (-5,17):100, (-4,17):99, (-3,17):18,
 (-9,18):97, (-8,18):99, (-7,18):98, (-6,18):100, (-5,18):99,
 (-4,18):95, (-3,18):6,
}

FIELDS = ('Уровень гекса','Постройка','Дорога','Водная переправа','Объекты гекса')

def land_terrain(q, r):
    # Direct visual audit of the clipped western land masses on the V6 raster.
    if r >= 17 and q <= -7 or r in (8,9) and q == -4:
        return 'Горы'
    if r >= 14:
        return 'Густой лес'
    return 'Редколесье'

def apply(row, share):
    q, r = int(row['Q']), int(row['R'])
    row['Доля суши, %'] = str(share)
    row['Комментарий'] = 'Повторно классифицировано по актуальной подложке V6'
    row['Основной ресурс'] = 'Нет'; row['Богатство ресурса'] = '0'
    row['Дополнительный объект'] = ''
    if share <= 5:
        row.update({'Категория':'Море','Тип местности':'Мелководье' if share else 'Открытое море',
                    'Проходимость':'2' if share else '1','Защита':'0','Плодородие':'',
                    'Пресная вода':'','Опасность':'2','Глубина':'1' if share else '3','Течение':'3'})
    else:
        terrain = land_terrain(q,r)
        move, defense, fertility = {'Редколесье':('2','1','3'),'Густой лес':('3','3','2'),'Горы':('5','4','0')}[terrain]
        if share < 100:
            row.update({'Категория':'Побережье','Тип местности':f'Побережье / {terrain}',
                        'Проходимость':move,'Защита':defense,'Плодородие':fertility,
                        'Пресная вода':'2','Опасность':'2','Глубина':'1','Течение':'3'})
        else:
            row.update({'Категория':'Суша','Тип местности':terrain,'Проходимость':move,
                        'Защита':defense,'Плодородие':fertility,'Пресная вода':'2',
                        'Опасность':'2','Глубина':'','Течение':''})

with SOURCE.open(encoding='utf-8-sig', newline='') as stream:
    rows = list(csv.DictReader(stream, delimiter=';'))
fieldnames = list(rows[0]) + [name for name in FIELDS if name not in rows[0]]
known = {(int(row['Q']), int(row['R'])) for row in rows}
for q, r in EDGE_SHARES:
    if (q, r) not in known:
        rows.append({name: '' for name in fieldnames} | {'ID':f'Q{q:+03d}-R{r:+03d}','Q':str(q),'R':str(r)})
rows.sort(key=lambda row: (int(row['R']), int(row['Q'])))
for row in rows:
    for name in FIELDS: row.setdefault(name, '')
    coord = (int(row['Q']), int(row['R']))
    if coord in EDGE_SHARES: apply(row, EDGE_SHARES[coord])
with SOURCE.open('w', encoding='utf-8-sig', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writeheader(); writer.writerows(rows)
print(f'Updated {len(EDGE_SHARES)} V6 edge cells; catalogue rows: {len(rows)}')
