from __future__ import annotations

from pathlib import Path
import sqlite3
from datetime import datetime, timezone

import numpy as np


def inspect_npz(npz_path: Path) -> None:
    print(f"NPZ: {npz_path}")
    npz = np.load(npz_path, allow_pickle=True)
    keys = list(npz.files)
    print(f"  keys ({len(keys)}): {keys}")

    for key in keys:
        arr = npz[key]
        shape = getattr(arr, "shape", None)
        dtype = getattr(arr, "dtype", None)
        print(f"  - {key}: shape={shape} dtype={dtype}")

        try:
            if getattr(arr, "size", 0):
                flat = arr.ravel()
                preview = flat[:5]
                print(f"      preview: {preview}")

                if hasattr(arr, "dtype") and np.issubdtype(arr.dtype, np.number):
                    finite = np.isfinite(flat)
                    if finite.any():
                        vals = flat[finite]
                        print(
                            f"      min/max: {float(vals.min())} {float(vals.max())}")
        except Exception as exc:
            print(f"      <preview error: {exc}>")


def inspect_sqlite(db_path: Path) -> None:
    print(f"DB: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print(f"  tables ({len(tables)}): {tables}")

    for table in tables:
        print(f"\n  == {table} ==")
        cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
        print("   columns:", [(c[1], c[2], c[3], c[4]) for c in cols])

        rows = cur.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
        print(f"   sample_rows={len(rows)}")
        for row in rows:
            d = dict(row)
            for k, v in list(d.items()):
                if isinstance(v, (bytes, bytearray)):
                    d[k] = f"<bytes:{len(v)}>"
                elif isinstance(v, str) and len(v) > 300:
                    d[k] = v[:300] + "…"
            print("    ", d)

    # Extra: ledger summary (dates + counts)
    if "orders" in tables:
        print("\n  -- summary(orders) --")
        total = cur.execute("SELECT COUNT(*) AS n FROM orders").fetchone()[0]
        print(f"   total_rows: {total}")

        mm = cur.execute(
            """
            SELECT
              MIN(created_at) AS min_created,
              MAX(created_at) AS max_created,
              MIN(updated_at) AS min_updated,
              MAX(updated_at) AS max_updated
            FROM orders
            """
        ).fetchone()

        def fmt_ts(ts: object) -> str:
            if ts is None:
                return "<null>"
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                return f"{float(ts):.3f} (UTC {dt.isoformat()})"
            except Exception:
                return str(ts)

        print(
            f"   created_at: {fmt_ts(mm['min_created'])} .. {fmt_ts(mm['max_created'])}")
        print(
            f"   updated_at: {fmt_ts(mm['min_updated'])} .. {fmt_ts(mm['max_updated'])}")

        print("\n   rows_by_symbol:")
        for r in cur.execute(
            "SELECT symbol, COUNT(*) AS n FROM orders GROUP BY symbol ORDER BY n DESC, symbol ASC"
        ).fetchall():
            print(f"     {r['symbol']}: {r['n']}")

        print("\n   rows_by_day(created_at) [last 30 days shown]:")
        for r in cur.execute(
            """
            SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS n
            FROM orders
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
        ).fetchall():
            print(f"     {r['day']}: {r['n']}")

    con.close()


def main() -> None:
    npz_path = Path("data/normalizer_states/normalizer_BTCUSDT.npz")
    db_path = Path("data/order_ledger.db")

    if npz_path.exists():
        inspect_npz(npz_path)
    else:
        print(f"NPZ not found: {npz_path}")

    print("\n" + "-" * 80 + "\n")

    if db_path.exists():
        inspect_sqlite(db_path)
    else:
        print(f"DB not found: {db_path}")


if __name__ == "__main__":
    main()
