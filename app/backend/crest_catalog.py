"""Audit and synchronize the WebP crest directory with PostgreSQL."""
import argparse
import hashlib
import json
from pathlib import Path

from db import connect

CRESTS_DIR = Path(__file__).resolve().parents[1] / 'frontend' / 'crests'


def crest_number(filename):
    stem = Path(filename).stem.removeprefix('gerb_')
    return int(stem) if stem.isdigit() else None


def discover_crests(directory=CRESTS_DIR):
    """Return reviewed top-level gerb_N.webp files and their immutable metadata."""
    result = {}
    for path in directory.glob('*.webp'):
        if crest_number(path.name) is None or not path.is_file():
            continue
        result[path.name] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'file_size': path.stat().st_size,
        }
    return dict(sorted(result.items(), key=lambda item: crest_number(item[0])))


def database_crests(conn):
    rows = conn.execute(
        'SELECT filename,sha256,file_size,active FROM crests ORDER BY filename'
    ).fetchall()
    return {row[0]: {'sha256': row[1], 'file_size': row[2], 'active': row[3]} for row in rows}


def compare_crests(files, records):
    file_names, record_names = set(files), set(records)
    changed = sorted(
        name for name in file_names & record_names
        if files[name]['sha256'] != records[name]['sha256']
        or files[name]['file_size'] != records[name]['file_size']
        or not records[name]['active']
    )
    return {
        'added': sorted(file_names - record_names, key=crest_number),
        'changed': sorted(changed, key=crest_number),
        'missing': sorted(record_names - file_names, key=crest_number),
    }


def sync_crests(conn, directory=CRESTS_DIR, apply=False):
    files = discover_crests(directory)
    records = database_crests(conn)
    differences = compare_crests(files, records)
    if apply:
        for filename, metadata in files.items():
            conn.execute(
                '''INSERT INTO crests(filename,sha256,file_size,active)
                   VALUES (%s,%s,%s,true)
                   ON CONFLICT(filename) DO UPDATE SET
                     sha256=excluded.sha256,file_size=excluded.file_size,
                     active=true,checked_at=now()''',
                (filename, metadata['sha256'], metadata['file_size']),
            )
        if differences['missing']:
            conn.execute(
                'UPDATE crests SET active=false,checked_at=now() WHERE filename=ANY(%s)',
                (differences['missing'],),
            )
    return {'files': len(files), **differences, 'synchronized': apply}


def active_crests(conn):
    names = [row[0] for row in conn.execute(
        'SELECT filename FROM crests WHERE active=true'
    ).fetchall()]
    return tuple(sorted(names, key=crest_number))


def main():
    parser = argparse.ArgumentParser(description='Check or synchronize WebP crests')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--sync', action='store_true')
    args = parser.parse_args()
    with connect() as conn:
        report = sync_crests(conn, apply=args.sync)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if args.check and any(report[key] for key in ('added', 'changed', 'missing')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
