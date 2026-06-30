import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

def extract_ts_ms(record):
    for key in ("ts_ms", "timestamp_ms", "decision_ts_ms", "event_ts_ms", "created_ts_ms", "updated_ts_ms", "bar_close_ts_ms", "timestamp", "ts"):
        v = record.get(key)
        if isinstance(v, (int, float)):
            if v > 1e15:
                return int(v / 1000)
            if v > 1e12:
                return int(v)
            if v > 1e9:
                return int(v * 1000)
        elif isinstance(v, str):
            v_clean = v.strip()
            if v_clean.endswith("Z"):
                try:
                    dt = datetime.fromisoformat(v_clean.replace("Z", "+00:00"))
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    pass
            try:
                return int(float(v_clean))
            except ValueError:
                pass
    return None

def ms_to_utc_iso(ts_ms):
    if ts_ms is None:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")

files = sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl")))

print("=== Analyzing files in order_log_old/ ===")
for f in files:
    print(f"\nFile: {f.name}")
    line_count = 0
    malformed = 0
    first_ts = None
    last_ts = None
    first_event = None
    last_event = None
    events = Counter()
    symbols = set()
    strategies = set()
    boot_events = []
    
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            line_count += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            
            ts_ms = extract_ts_ms(rec)
            ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
            sym = rec.get("symbol")
            strat = rec.get("strategy_id") or rec.get("strategy")
            
            if sym:
                symbols.add(sym)
            if strat:
                strategies.add(strat)
                
            events[ev] += 1
            
            if first_ts is None:
                first_ts = ts_ms
                first_event = ev
            last_ts = ts_ms
            last_event = ev
            
            if ev == "BOOT" or rec.get("event_type") == "BOOT":
                boot_events.append((idx, ts_ms, rec))
                
    print(f"  Line count: {line_count}")
    print(f"  Malformed: {malformed}")
    print(f"  First TS: {first_ts} ({ms_to_utc_iso(first_ts)}) | Event: {first_event}")
    print(f"  Last TS: {last_ts} ({ms_to_utc_iso(last_ts)}) | Event: {last_event}")
    print(f"  BOOT events count: {len(boot_events)}")
    for idx, ts, b in boot_events:
        print(f"    Line {idx} | TS: {ts} ({ms_to_utc_iso(ts)}) | rid: {b.get('rid')} | symbol: {b.get('symbol')}")
    print(f"  Symbols: {sorted(list(symbols))}")
    print(f"  Strategies: {sorted(list(strategies))}")
    print(f"  Events distribution: {dict(events)}")
