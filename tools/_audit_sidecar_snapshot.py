#!/usr/bin/env python3
"""Forensic sidecar snapshot audit script."""
import json
from collections import Counter, defaultdict

LOGFILE = 'logs/trade_lifecycle.jsonl'

suppressed = []
mode_active = []

with open(LOGFILE, encoding='utf-8', errors='replace') as f:
    for lineno, line in enumerate(f, 1):
        if 'POSITION_POLICY_SIDECAR' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        et = obj.get('event_type', '')
        if et == 'POSITION_POLICY_SIDECAR_SUPPRESSED':
            suppressed.append((lineno, obj))
        elif et == 'POSITION_POLICY_SIDECAR_MODE_ACTIVE':
            mode_active.append((lineno, obj))

print(f"SUPPRESSED total: {len(suppressed)}")
print(f"MODE_ACTIVE total: {len(mode_active)}")

# Symbol counts in suppressed
sym_sup = Counter(o.get('symbol', '?') for _, o in suppressed)
print("\n=== SUPPRESSED by symbol (all) ===")
for sym, cnt in sym_sup.most_common(30):
    print(f"  {sym}: {cnt}")

# Suppression reasons
all_reasons = []
sym_reasons = defaultdict(list)
for _, o in suppressed:
    rc = o.get('reason_codes', [])
    sym = o.get('symbol', '?')
    if isinstance(rc, list):
        all_reasons.extend(rc)
        sym_reasons[sym].extend(rc)
    elif rc:
        all_reasons.append(str(rc))
        sym_reasons[sym].append(str(rc))

reason_cnt = Counter(all_reasons)
print("\n=== SUPPRESSION REASONS (all) ===")
for r, c in reason_cnt.most_common(30):
    print(f"  {r}: {c}")

# Per-reason: symbols affected, first/last ts
reason_syms = defaultdict(set)
reason_ts = defaultdict(list)
for _, o in suppressed:
    rc = o.get('reason_codes', [])
    ts = o.get('ts_ms', 0)
    sym = o.get('symbol', '?')
    if isinstance(rc, list):
        for r in rc:
            reason_syms[r].add(sym)
            reason_ts[r].append(ts)
    elif rc:
        reason_syms[rc].add(sym)
        reason_ts[rc].append(ts)

print("\n=== PER-REASON DETAIL (top 15) ===")
for r, c in reason_cnt.most_common(15):
    syms = sorted(reason_syms[r])
    ts_list = reason_ts[r]
    first_ts = min(ts_list) if ts_list else None
    last_ts = max(ts_list) if ts_list else None
    print(
        f"  reason={r} count={c} symbols={syms} first_ts={first_ts} last_ts={last_ts}")

# MODE_ACTIVE detail
print("\n=== MODE_ACTIVE rows ===")
for lineno, o in mode_active:
    print(f"  line={lineno} ts={o.get('ts_ms')} symbol={o.get('symbol')} mode={o.get('mode')} eval_mode={o.get('evaluation_mode')} reasons={o.get('reason_codes')}")

# Sample suppressed rows (varied reasons)
print("\n=== SAMPLE SUPPRESSED ROWS (5) ===")
seen_reasons_in_samples = set()
sample_count = 0
for lineno, o in suppressed:
    rc = o.get('reason_codes', [])
    r_key = tuple(rc) if isinstance(rc, list) else (str(rc),)
    if r_key not in seen_reasons_in_samples or sample_count < 5:
        seen_reasons_in_samples.add(r_key)
        sample_count += 1
        fresh = o.get('freshness_snapshot', {})
        pos = o.get('position_snapshot', {})
        print(
            f"  line={lineno} ts={o.get('ts_ms')} sym={o.get('symbol')} reason_codes={rc}")
        print(
            f"    trigger_event={o.get('trigger_event')} manage_state={o.get('manage_state')}")
        print(
            f"    freshness_keys={list(fresh.keys())[:8] if isinstance(fresh, dict) else fresh}")
        print(
            f"    position_snapshot_keys={list(pos.keys())[:8] if isinstance(pos, dict) else pos}")
        if sample_count >= 8:
            break

# Full payload of first 5 suppressed rows
print("\n=== FULL PAYLOAD FIRST 5 SUPPRESSED ===")
for i, (lineno, o) in enumerate(suppressed[:5]):
    print(f"\n-- SUPPRESSED[{i}] line={lineno} --")
    print(json.dumps(o, indent=2)[:1200])
