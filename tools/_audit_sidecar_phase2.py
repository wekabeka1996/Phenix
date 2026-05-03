#!/usr/bin/env python3
"""Phase 2: deep analysis of suppressed payloads - position_snapshot and freshness fields."""
import json
from collections import Counter, defaultdict

LOGFILE = 'logs/trade_lifecycle.jsonl'

suppressed = []
with open(LOGFILE, encoding='utf-8', errors='replace') as f:
    for lineno, line in enumerate(f, 1):
        if 'POSITION_POLICY_SIDECAR_SUPPRESSED' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        suppressed.append((lineno, obj))

print(f"Total suppressed: {len(suppressed)}")

# Analyze position_snapshot fields across all suppressed rows
manage_states = Counter()
closing_pos = Counter()
portfolio_symbol_present = Counter()
portfolio_snapshot_status = Counter()
post_fill_grace_rows = [(ln, o) for ln, o in suppressed if 'post_fill_grace_active' in (
    o.get('reason_codes') or [])]
startup_grace_rows = [(ln, o) for ln, o in suppressed if 'startup_grace_active' in (
    o.get('reason_codes') or [])]
close_in_progress_rows = [(ln, o) for ln, o in suppressed if 'close_in_progress' in (
    o.get('reason_codes') or [])]
exec_close_recon_rows = [(ln, o) for ln, o in suppressed if 'trigger:execution_close_reconciled' in (
    o.get('reason_codes') or [])]
no_lifecycle_rows = [(ln, o) for ln, o in suppressed if 'no_active_lifecycle' in (
    o.get('reason_codes') or [])]

for ln, o in suppressed:
    ps = o.get('position_snapshot', {})
    manage_states[ps.get('manage_state')] += 1
    closing_pos[ps.get('closing_position')] += 1
    portfolio_symbol_present[ps.get('portfolio_symbol_present')] += 1
    portfolio_snapshot_status[ps.get('portfolio_snapshot_status')] += 1

print("\n=== manage_state distribution (suppressed) ===")
for k, v in manage_states.most_common():
    print(f"  {k}: {v}")

print("\n=== closing_position distribution (suppressed) ===")
for k, v in closing_pos.most_common():
    print(f"  {k}: {v}")

print("\n=== portfolio_symbol_present (suppressed) ===")
for k, v in portfolio_symbol_present.most_common():
    print(f"  {k}: {v}")

print("\n=== portfolio_snapshot_status (suppressed) ===")
for k, v in portfolio_snapshot_status.most_common():
    print(f"  {k}: {v}")

# Check freshness - how many are fully fresh?
fully_fresh = 0
partial_fresh = 0
no_fresh = 0
for _, o in suppressed:
    fs = o.get('freshness_snapshot', {})
    pf = fs.get('portfolio_fresh')
    ff = fs.get('features_fresh')
    rf = fs.get('regime_fresh')
    osf = fs.get('order_state_fresh')
    if all([pf, ff, rf, osf]):
        fully_fresh += 1
    elif any([pf, ff, rf, osf]):
        partial_fresh += 1
    else:
        no_fresh += 1
print(
    f"\n=== Freshness in suppressed: fully_fresh={fully_fresh} partial_fresh={partial_fresh} no_fresh={no_fresh}")

# Show examples of rows with non-null manage_state
print("\n=== SUPPRESSED rows with non-null manage_state (up to 10) ===")
cnt = 0
for ln, o in suppressed:
    ps = o.get('position_snapshot', {})
    ms = ps.get('manage_state')
    if ms is not None:
        print(f"  line={ln} ts={o.get('ts_ms')} sym={o.get('symbol')} manage_state={ms} closing={ps.get('closing_position')} reasons={o.get('reason_codes')}")
        print(
            f"    portfolio_symbol_present={ps.get('portfolio_symbol_present')} portfolio_snapshot_status={ps.get('portfolio_snapshot_status')}")
        fs = o.get('freshness_snapshot', {})
        print(
            f"    freshness: pf={fs.get('portfolio_fresh')} ff={fs.get('features_fresh')} rf={fs.get('regime_fresh')} osf={fs.get('order_state_fresh')}")
        cnt += 1
        if cnt >= 15:
            break

# Post-fill grace samples
print(f"\n=== POST_FILL_GRACE rows: {len(post_fill_grace_rows)} ===")
for ln, o in post_fill_grace_rows[:5]:
    ps = o.get('position_snapshot', {})
    fs = o.get('freshness_snapshot', {})
    print(f"  line={ln} ts={o.get('ts_ms')} sym={o.get('symbol')} manage_state={ps.get('manage_state')} closing={ps.get('closing_position')}")
    print(f"    reasons={o.get('reason_codes')}")
    print(
        f"    portfolio_symbol_present={ps.get('portfolio_symbol_present')} pf={fs.get('portfolio_fresh')} ff={fs.get('features_fresh')} rf={fs.get('regime_fresh')} osf={fs.get('order_state_fresh')}")

# Close-in-progress samples
print(f"\n=== CLOSE_IN_PROGRESS rows: {len(close_in_progress_rows)} ===")
for ln, o in close_in_progress_rows[:5]:
    ps = o.get('position_snapshot', {})
    fs = o.get('freshness_snapshot', {})
    print(f"  line={ln} ts={o.get('ts_ms')} sym={o.get('symbol')} manage_state={ps.get('manage_state')} closing={ps.get('closing_position')}")
    print(f"    reasons={o.get('reason_codes')}")
    print(
        f"    portfolio_symbol_present={ps.get('portfolio_symbol_present')} pf={fs.get('portfolio_fresh')} ff={fs.get('features_fresh')} rf={fs.get('regime_fresh')} osf={fs.get('order_state_fresh')}")

# execution_close_reconciled samples
print(
    f"\n=== EXECUTION_CLOSE_RECONCILED rows: {len(exec_close_recon_rows)} ===")
for ln, o in exec_close_recon_rows:
    ps = o.get('position_snapshot', {})
    fs = o.get('freshness_snapshot', {})
    print(f"  line={ln} ts={o.get('ts_ms')} sym={o.get('symbol')} manage_state={ps.get('manage_state')} closing={ps.get('closing_position')}")
    print(f"    reasons={o.get('reason_codes')}")
    print(
        f"    portfolio_symbol_present={ps.get('portfolio_symbol_present')} pf={fs.get('portfolio_fresh')} ff={fs.get('features_fresh')} rf={fs.get('regime_fresh')} osf={fs.get('order_state_fresh')}")

# Symbol with only SUPPRESSED
sym_all = Counter(o.get('symbol', '?') for _, o in suppressed)
print("\n=== All symbols appear only in SUPPRESSED (no EVALUATED): all 7 symbols ===")
for sym, cnt in sym_all.most_common():
    print(f"  {sym}: {cnt} suppressed rows")
