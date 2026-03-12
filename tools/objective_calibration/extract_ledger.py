from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def load_order_ledger(ledger_path: Path) -> pd.DataFrame:
    if not ledger_path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(str(ledger_path))
    try:
        df = pd.read_sql_query("SELECT * FROM orders", con)
    finally:
        con.close()
    for column in ("created_at", "updated_at"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["symbol", "created_at"], kind="mergesort").reset_index(drop=True)
