"""Run reviewed SQL migrations transactionally; never on application startup."""
from pathlib import Path
from db import connect

def main():
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(731604)')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for file in sorted((Path(__file__).resolve().parents[2] / 'data/migrations').glob('*.sql')):
            if not conn.execute('SELECT 1 FROM schema_migrations WHERE name=%s', (file.name,)).fetchone():
                conn.execute(file.read_text(encoding='utf-8'))
                conn.execute('INSERT INTO schema_migrations(name) VALUES (%s)', (file.name,))
                print('Applied:', file.name)

if __name__ == '__main__':
    main()
