import os
from pathlib import Path
import psycopg

def connect():
    password = Path(os.environ['DB_PASSWORD_FILE']).read_text().strip()
    return psycopg.connect(host=os.getenv('DB_HOST', 'db'), dbname='rhisseth',
                           user='rhisseth', password=password)
