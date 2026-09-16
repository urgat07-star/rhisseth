"""Read-only local asset/seed-grid diagnostics; does not change PNG or database."""
import csv
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
asset = ROOT/'app/frontend/terrain-map-group3-artistic-v5.png'
header = asset.read_bytes()[:24]
width, height = struct.unpack('>II',header[16:24])
with (ROOT/'data/import/hex-initial-parameters.csv').open(encoding='utf-8-sig',newline='') as stream:
    rows = {(int(row['Q']),int(row['R'])):row for row in csv.DictReader(stream,delimiter=';')}

def cell(x,y):
    r=y/120
    q=x/(math.sqrt(3)*80)-r/2
    s=-q-r
    rq,rr,rs=round(q),round(r),round(s)
    dq,dr,ds=abs(rq-q),abs(rr-r),abs(rs-s)
    if dq>dr and dq>ds:
        rq=-rr-rs
    elif dr>ds:
        rr=-rq-rs
    return rq,rr

missing=set()
excluded=set()
covered=0
total=0
for y in range(5,2200,10):
    for x in range(5,3200,10):
        key=cell(x,y)
        row=rows.get(key)
        total+=1
        if row is None:
            missing.add(key)
        elif row['Категория']=='Вне полотна':
            excluded.add(key)
        else:
            covered+=1
print(json.dumps({'asset':asset.name,'png_dimensions':[width,height],
    'legacy_viewbox':[3200,2200],'legacy_radius':80,'seed_count':len(rows),
    'seed_visible_count':sum(row['Категория']!='Вне полотна' for row in rows.values()),
    'sample_coverage_percent':round(100*covered/total,3),
    'missing_sampled_cells':sorted(missing),'excluded_but_sampled_cells':sorted(excluded)},ensure_ascii=False,indent=2))
