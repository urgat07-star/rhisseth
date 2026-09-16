import os
from pathlib import Path
import psycopg

def connect():
    password = Path(os.environ['DB_PASSWORD_FILE']).read_text().strip()
    return psycopg.connect(host=os.getenv('DB_HOST', 'db'),
                           dbname=os.getenv('DB_NAME', 'rhisseth'),
                           user=os.getenv('DB_USER', 'rhisseth'),
                           port=int(os.getenv('DB_PORT', '5432')),
                           password=password, connect_timeout=5)
