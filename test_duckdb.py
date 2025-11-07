import duckdb
import pandas as pd
import tempfile
import os

fd, db_path = tempfile.mkstemp(suffix='.db')
os.close(fd)
os.unlink(db_path)

with duckdb.connect(db_path) as conn:
    conn.execute('''
        CREATE TABLE features (
            timestamp TIMESTAMP,
            symbol VARCHAR,
            features JSON
        )
    ''')

    conn.execute('''
        INSERT INTO features VALUES (NOW(), 'BTCUSDT', '{"price": 50000}')
    ''')

    rel = conn.execute('SELECT * FROM features')
    print("Type:", type(rel))
    print("Dir:", [x for x in dir(rel) if not x.startswith('_')])
    print("Hasattr fetchdf:", hasattr(rel, 'fetchdf'))

    # Try to get dataframe
    if hasattr(rel, 'fetchdf'):
        df = rel.fetchdf()
    else:
        print("fetchdf doesn't exist, trying alternatives")

if os.path.exists(db_path):
    os.unlink(db_path)
