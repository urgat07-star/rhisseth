"""One-time, transactional import. An existing map is never overwritten."""
import argparse
import csv
from pathlib import Path
from psycopg.types.json import Jsonb
from db import connect

def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        required = {'ID', 'Q', 'R', 'Тип местности', 'Проходимость', 'Защита'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Missing required CSV columns')
        rows = list(reader)
    seen = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed CSV row')
        coords = (int(row['Q']), int(row['R']))
        if coords in seen:
            raise ValueError('Duplicate coordinates')
        seen.add(coords)
    if not rows:
        raise ValueError('Empty source')
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    rows = read_rows(args.source)
    if not args.check_only:
        with connect() as conn:
            conn.execute('LOCK TABLE hexes IN EXCLUSIVE MODE')
            if conn.execute('SELECT 1 FROM hexes LIMIT 1').fetchone():
                raise ValueError('Target is not empty; import refused')
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO hexes(q,r,data) VALUES (%s,%s,%s)',
                                [(int(row['Q']), int(row['R']), Jsonb(row)) for row in rows])
    print(f'Validated {len(rows)} rows' if args.check_only else f'Imported {len(rows)} rows')

if __name__ == '__main__':
    main()
