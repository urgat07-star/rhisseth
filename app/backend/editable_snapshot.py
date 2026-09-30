"""Apply the sanitized admin-editable database snapshot tracked in Git."""
import json
from pathlib import Path

SNAPSHOT=Path(__file__).resolve().parents[2]/'data/snapshots/editable-database.json'

def _upsert(conn,table,rows,key,fields,identity=False):
    for row in rows:
        columns=[name for name in fields if name in row]
        updates=[name for name in columns if name not in key]
        sql=(f"INSERT INTO {table} ({','.join(columns)}) {'OVERRIDING SYSTEM VALUE ' if identity else ''}VALUES ({','.join('%s' for _ in columns)}) "
             f"ON CONFLICT ({','.join(key)}) DO UPDATE SET "+','.join(f'{name}=EXCLUDED.{name}' for name in updates))
        conn.execute(sql,[row[name] for name in columns])

def apply_editable_snapshot(conn):
    if not SNAPSHOT.exists():return {'applied':False}
    data=json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    if data.get('format')!=1:raise RuntimeError('Unsupported editable database snapshot format')
    for row in data['hexes']:
        conn.execute('''INSERT INTO hexes(q,r,data) VALUES (%s,%s,%s)
            ON CONFLICT(q,r) DO UPDATE SET data=EXCLUDED.data,updated_at=now()''',(row['q'],row['r'],json.dumps(row['data'],ensure_ascii=False)))
    _upsert(conn,'extractable_resources',data['extractable_resources'],('code',),('code','name','typical_locations','purpose','is_food','active'))
    _upsert(conn,'produced_resources',data['produced_resources'],('code',),('code','name','ingredients','required_building','purpose','is_food','active'))
    _upsert(conn,'additional_building_catalog',data['buildings'],('code',),('code','name','level_1_effect','level_2_effect','level_3_effect','image_path','note','active'))
    _upsert(conn,'general_catalog',data['generals'],('id',),('id','name','description','image_path','health','attack','defense','initiative','speed','logistics','skills','experience_per_level','max_level','max_attack_bonus','max_defense_bonus','active'),True)
    unit_fields=('id','name','troop_type','health','armor','defense','attack','attack_range','speed','initiative','morale','counterattack','description','image_path','price','building','note','active','combat_level','purchasable')
    _upsert(conn,'unit_catalog',data['units'],('id',),unit_fields,True)
    conn.execute('DELETE FROM unit_resource_costs')
    conn.execute('DELETE FROM unit_upgrade_requirements')
    for unit in data['units']:
        for code,quantity in unit.get('cost',{}).items():
            conn.execute('INSERT INTO unit_resource_costs(unit_id,resource_code,quantity) VALUES (%s,%s,%s)',(unit['id'],code,quantity))
        if unit.get('predecessor_unit_id') is not None:
            conn.execute('INSERT INTO unit_upgrade_requirements(unit_id,predecessor_unit_id) VALUES (%s,%s)',(unit['id'],unit['predecessor_unit_id']))
    conn.execute('DELETE FROM hex_additional_buildings')
    _upsert(conn,'hex_additional_buildings',data['hex_buildings'],('q','r','building_code'),('q','r','building_code','building_level','built_at'))
    return {'applied':True,'hexes':len(data['hexes']),'units':len(data['units']),'generals':len(data['generals'])}
