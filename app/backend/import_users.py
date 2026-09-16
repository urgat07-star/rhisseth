"""Convert only users/roles INSERT values; never execute the MySQL dump."""
import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile
from db import connect

def decode(data):
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1251')

def parse_dump(text):
    tables = {'roles': [], 'users': []}
    expected = {'roles': {'role_id','role_name','role_alias'},
                'users': {'user_id','user_login','user_pass','user_email','role_id'}}
    token = re.compile(r"\s*(?:'((?:\\.|''|[^'])*)'|(-?\d+)|(NULL)|([(),;]))", re.S)
    for match in re.finditer(r'INSERT INTO\s+`(roles|users)`\s*\(([^)]+)\)\s*VALUES\s*', text, re.I):
        table = match[1].lower()
        columns = [c.strip().strip('`') for c in match[2].split(',')]
        if set(columns) != expected[table] or len(columns) != len(expected[table]):
            raise ValueError('Unexpected dump columns')
        pos, values, inside = match.end(), [], False
        while True:
            parsed = token.match(text, pos)
            if not parsed:
                raise ValueError('Unsupported dump value syntax')
            pos = parsed.end()
            string, number, null, punctuation = parsed.groups()
            if punctuation == ';':
                if inside:
                    raise ValueError('Malformed dump row')
                break
            if punctuation == '(':
                if inside:
                    raise ValueError('Nested SQL expressions are unsupported')
                inside, values = True, []
            elif punctuation == ')':
                if not inside or len(values) != len(columns):
                    raise ValueError('Invalid dump row width')
                tables[table].append(dict(zip(columns, values)))
                inside = False
            elif punctuation == ',':
                continue
            elif inside:
                if string is not None:
                    substitutions = {'0':'\0','n':'\n','r':'\r','t':'\t','Z':'\x1a'}
                    value = re.sub(r'\\(.)', lambda m: substitutions.get(m[1], m[1]), string).replace("''", "'")
                else:
                    value = int(number) if number is not None else None
                values.append(value)
            else:
                raise ValueError('Value outside row')
    if not tables['roles'] or not tables['users']:
        raise ValueError('Dump must contain roles and users')
    for table, rows in tables.items():
        ids = [row['role_id' if table == 'roles' else 'user_id'] for row in rows]
        if len(set(ids)) != len(ids) or any(not isinstance(i, int) or i <= 0 for i in ids):
            raise ValueError('Invalid or duplicate IDs')
    role_ids = {row['role_id'] for row in tables['roles']}
    for row in tables['users']:
        if row['role_id'] not in role_ids or not re.fullmatch(r'\$2[aby]\$(0[4-9]|1[0-6])\$[./A-Za-z0-9]{53}', row['user_pass'] or ''):
            raise ValueError('Invalid role reference or unsupported password hash')
    return tables

def load_archive(path):
    with ZipFile(path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if len(files) != 1 or files[0].file_size > 10_000_000 or not files[0].filename.endswith('.sql'):
            raise ValueError('Expected a single bounded SQL dump')
        return parse_dump(decode(archive.read(files[0])))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    tables = load_archive(args.archive)
    if not args.check_only:
        with connect() as conn:
            conn.execute('LOCK TABLE users,roles IN EXCLUSIVE MODE')
            if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone() or conn.execute('SELECT 1 FROM roles LIMIT 1').fetchone():
                raise ValueError('Existing account data; import refused')
            for table, rows in tables.items():
                columns = list(rows[0])
                statement = f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(["%s"]*len(columns))})'
                with conn.cursor() as cur:
                    cur.executemany(statement, [tuple(row[c] for c in columns) for row in rows])
            conn.execute("SELECT setval(pg_get_serial_sequence('users','user_id'), (SELECT max(user_id) FROM users))")
    print(json.dumps({'roles':len(tables['roles']), 'users':len(tables['users']), 'role_aliases':[r['role_alias'] for r in tables['roles']], 'mode':'validated' if args.check_only else 'imported'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
