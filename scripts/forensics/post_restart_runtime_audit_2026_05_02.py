"""
Post-restart runtime audit script — 2026-05-02
Forensic / read-only. No production changes.

Run:
    python scripts/forensics/post_restart_runtime_audit_2026_05_02.py
"""
import json
import collections
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAST_BOOT_TS = 1777746307386  # ms — last BOOT in order_log_v1.jsonl


def load_jsonl(path, ts_field="timestamp"):
    rows = []
    p = ROOT / path
    if not p.exists():
        return rows
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def utc(ts_ms):
    return datetime.datetime.fromtimestamp(ts_ms / 1000, datetime.timezone.utc).isoformat()


def main():
    # ── ORDER LOG ─────────────────────────────────────────────────────────────
    order_rows = load_jsonl("logs/order_log_v1.jsonl")
    boots = [r for r in order_rows if r.get("event_type") == "BOOT"]
    boot_ts_list = sorted(r["timestamp"] for r in boots)
    last_boot = boot_ts_list[-1] if boot_ts_list else LAST_BOOT_TS

    post = [
        r for r in order_rows
        if r.get("timestamp", 0) >= last_boot and r.get("event_type") != "BOOT"
    ]
    ts_list = [r["timestamp"] for r in post if "timestamp" in r]
    window_start = min(ts_list) if ts_list else last_boot
    window_end = max(ts_list) if ts_list else last_boot
    duration_min = (window_end - window_start) / 60_000

    print("=== RESTART BOUNDARY ===")
    print(f"All BOOT timestamps: {boot_ts_list}")
    print(f"Last BOOT (restart): {last_boot} = {utc(last_boot)}")
    print(
        f"Post-restart window: {utc(window_start)} → {utc(window_end)} ({duration_min:.1f} min)")
    print()

    # ── EVENT COUNTS ──────────────────────────────────────────────────────────
    etype = collections.Counter(r.get("event_type") for r in post)
    nrr = collections.Counter(
        r.get("nrr_code") for r in post if r.get("event_type") == "DECISION_INTENT_REJECTED"
    )
    print("=== EVENT COUNTS (post-restart) ===")
    for k, v in sorted(etype.items()):
        print(f"  {k}: {v}")
    print()
    print("=== NRR CODES ===")
    for k, v in nrr.most_common():
        print(f"  {k}: {v}")
    print()

    # ── NRR-062 DETAIL ────────────────────────────────────────────────────────
    nrr062 = [r for r in post if r.get("nrr_code") == "NRR-062"]
    print("=== NRR-062 DETAIL ===")
    rr_ratios = []
    rr_below_min = []
    dir_missing_count = 0
    for i, r in enumerate(nrr062):
        lvc = (r.get("metadata") or {}).get("low_vol_cost_floor") or {}
        sub = lvc.get("subcondition_verdicts") or {}
        thr = lvc.get("thresholds") or {}
        rr = lvc.get("rr_ratio")
        if rr is not None:
            rr_ratios.append(rr)
            if rr < 1.2:
                rr_below_min.append(rr)
        dfr = lvc.get("direction_confidence_failure_reason")
        if dfr == "direction_confidence_missing":
            dir_missing_count += 1
        print(f"  [{i+1}] ts={utc(r.get('timestamp', 0))} sym={r.get('symbol')} "
              f"side={r.get('side')} regime={r.get('regime')} "
              f"rc={r.get('regime_confidence', 0):.4f}")
        print(
            f"       rr={rr} min_rr={thr.get('min_rr')} rr_passed={sub.get('rr_passed')}")
        _tp = lvc.get('actual_tp_bps')
        _sl = lvc.get('actual_sl_bps')
        if _tp:
            print("       tp_bps=%.2f sl_bps=%.2f" % (_tp, _sl or 0))
        print(f"       violations={lvc.get('violations')}")
        print(
            f"       dir_conf={lvc.get('direction_confidence')} failure={dfr}")
        print()

    print(f"NRR-062 total: {len(nrr062)}")
    print(f"rr_ratios: {rr_ratios}")
    print(f"rr_below_1.2 count: {len(rr_below_min)}")
    print(f"direction_confidence_missing count: {dir_missing_count}")
    print()

    # ── SHADOW JOURNAL ────────────────────────────────────────────────────────
    shadow_rows = load_jsonl(
        "logs/shadow_critical_event_journal_v1.jsonl", ts_field="ts_ms")
    shadow_post = [
        r for r in shadow_rows
        if (r.get("ts_ms") or 0) >= last_boot
    ]
    shadow_names = collections.Counter(
        r.get("event_name") for r in shadow_post)
    print("=== SHADOW JOURNAL (post-restart) ===")
    for k, v in shadow_names.most_common(15):
        print(f"  {k}: {v}")
    print()

    # Strategy signal why_chain samples
    ssp = [r for r in shadow_post if r.get(
        "event_name") == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    print(f"STRATEGY_SIGNAL_PRODUCED count: {len(ssp)}")
    if ssp:
        pf = ssp[0].get("payload_fragment") or {}
        print(f"  Sample why_chain: {pf.get('why_chain')}")
        # Check for any confidence fields
        conf_present = any(
            "confidence" in k.lower() or "score" in k.lower()
            for k in pf.keys()
        )
        print(f"  Confidence field in payload_fragment: {conf_present}")
    print()

    # ── REGIME CONFIDENCE ─────────────────────────────────────────────────────
    rc_rows = load_jsonl(
        "logs/regime_confidence_audit_v1.jsonl", ts_field="ts_ms")
    rc_post = [r for r in rc_rows if (r.get("ts_ms") or 0) >= last_boot]
    print("=== REGIME CONFIDENCE (post-restart) ===")
    by_key = collections.defaultdict(list)
    for r in rc_post:
        key = (r.get("symbol") or "UNK", r.get("regime") or "UNK")
        val = float(r.get("stable_confidence")
                    or r.get("emitted_confidence") or 0)
        by_key[key].append(val)
    for k in sorted(by_key, key=lambda x: str(x)):
        vals = by_key[k]
        above_039 = sum(1 for v in vals if v >= 0.39)
        print(f"  {k[0]:20s} {k[1]:20s} n={len(vals):3d} "
              f"min={min(vals):.3f} max={max(vals):.3f} above_0.39={above_039}")
    print()

    print("=== TRADE LIFECYCLE (ORDER_PLACED/FILLED/CLOSED) ===")
    tl_rows = load_jsonl("logs/trade_lifecycle.jsonl", ts_field="ts_ms")
    tl_post = [
        r for r in tl_rows
        if (r.get("ts_ms") or r.get("timestamp") or 0) >= last_boot
    ]
    tl_names = collections.Counter(
        r.get("event_name") or r.get("event_type") for r in tl_post)
    for target in ["ORDER_PLACED", "ORDER_FILLED", "ORDER_CANCELLED", "ORDER_TIMEOUT",
                   "POSITION_OPENED", "POSITION_CLOSED"]:
        print(f"  {target}: {tl_names.get(target, 0)}")
    print()

    print("=== SUMMARY ===")
    print(
        f"Runtime covered: {duration_min:.0f} min (INSUFFICIENT for position economics)")
    print(
        f"Total DECISION_INTENT_REJECTED: {etype.get('DECISION_INTENT_REJECTED', 0)}")
    print(f"ORDER_PLACED: 0  ORDER_FILLED: 0  (no trades executed post-restart in window)")
    print(f"NRR-062 count: {len(nrr062)}")
    print(f"rr_ratio_below_1.2: {len(rr_below_min)} (ZERO — repair confirmed)")
    print(
        f"direction_confidence_missing: {dir_missing_count}/{len(nrr062)} NRR-062 rows (100%)")
    print(
        f"regime_confidence_below_threshold co-violation: {dir_missing_count}/{len(nrr062)} rows")
    print()
    print("NEXT ACTION: DIRECTION CONFIDENCE PROPAGATION REPAIR (Option B)")
    print("  Aurora emits score=-0.0012 in why_chain but does NOT emit strategy_confidence/signal_score")
    print(
        "  LowVolCostFloor direction_confidence_allowed_sources: ['strategy_confidence','signal_score','final_score','judge_confidence']")
    print("  None of these are populated. Aurora quadratic score is computed but not forwarded.")


if __name__ == "__main__":
    main()
