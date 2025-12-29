#!/usr/bin/env python3
import sqlite3
import json
from collections import OrderedDict

DB_PATH = r"data\order_ledger.db"
LIMIT = 20


def dump_db(path):
    out = OrderedDict()
    try:
        conn = sqlite3.connect(path)
    except Exception as e:
        print(f"ERROR: cannot open {path}: {e}")
        return
    cur = conn.cursor()
    cur.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")
    objs = cur.fetchall()
    tables = [r[0] for r in objs]
    out['db'] = path
    out['tables'] = tables
    out['details'] = OrderedDict()
    for t in tables:
        info = OrderedDict()
        try:
            cur.execute(f"PRAGMA table_info('{t}')")
            cols = cur.fetchall()
            info['columns'] = []
            for c in cols:
                info['columns'].append({
                    'cid': c[0], 'name': c[1], 'type': c[2], 'notnull': bool(c[3]), 'dflt_value': c[4], 'pk': bool(c[5])
                })
            # fetch first LIMIT rows
            try:
                cur.execute(f"SELECT * FROM '{t}' LIMIT {LIMIT}")
                rows = cur.fetchall()
                # get column names from cursor.description if available
                colnames = [d[0]
                            for d in cur.description] if cur.description else []
                info['sample_rows'] = {
                    'colnames': colnames,
                    'rows': rows
                }
            except Exception as e:
                info['sample_rows'] = f"ERROR selecting rows: {e}"
        except Exception as e:
            info['error'] = str(e)
        out['details'][t] = info
    conn.close()
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    dump_db(DB_PATH)
