import sqlite3
import pandas as pd

conn = sqlite3.connect('data/order_ledger.db')
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)
print("Tables:", tables['name'].tolist())

for t in tables['name']:
    df = pd.read_sql(f"SELECT * FROM {t} WHERE symbol = 'XRPUSDT' OR symbol = 'XRP' LIMIT 10", conn)
    if not df.empty:
        print(f"\n--- {t} ---")
        print(df.to_string())
