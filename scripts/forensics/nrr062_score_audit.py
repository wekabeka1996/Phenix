"""One-shot: extract scoring/confidence fields from post-restart NRR-062 order_log rows."""
import json
import pathlib

LOG = pathlib.Path("logs/order_log_v1.jsonl")
BOOT = 1777746307386

rows = [json.loads(l) for l in LOG.read_text(
    "utf-8", errors="replace").splitlines() if l.strip()]
nrr062 = [
    r for r in rows
    if r.get("timestamp", 0) >= BOOT and str(r.get("nrr_code", "")) == "NRR-062"
]
print(f"NRR-062 post-restart rows: {len(nrr062)}")

for i, r in enumerate(nrr062, 1):
    meta = r.get("metadata") or {}
    details = r.get("details") or {}
    # check both metadata and details for lvc
    lvc = meta.get("low_vol_cost_floor") or details.get(
        "low_vol_cost_floor") or {}
    sc = meta.get("score_context") or details.get("score_context") or {}
    st = meta.get("strategy_trace") or details.get("strategy_trace") or {}

    print(
        f"\nRow {i}: symbol={r.get('symbol')} side={r.get('side')} ts={r.get('timestamp')}")
    print(f"  top-level rc        : {r.get('regime_confidence')}")
    print(f"  meta keys           : {sorted(meta.keys())[:15]}")
    print(f"  lvc keys            : {sorted(lvc.keys())[:20]}")
    print(f"  violations          : {lvc.get('violations')}")
    print(f"  direction_confidence: {lvc.get('direction_confidence')}")
    print(f"  dir_conf_source     : {lvc.get('direction_confidence_source')}")
    print(
        f"  dir_conf_failure    : {lvc.get('direction_confidence_failure_reason')}")
    print(f"  lvc.signal_score    : {lvc.get('signal_score')}")
    print(f"  lvc.model_conf      : {lvc.get('model_confidence')}")
    print(f"  lvc.strategy_conf   : {lvc.get('strategy_confidence')}")
    print(f"  lvc.final_score     : {lvc.get('final_score')}")
    print(f"  score_context       : {sc}")
    print(f"  strategy_trace keys : {sorted(st.keys())[:15]}")
    print(f"  rr_ratio            : {lvc.get('rr_ratio')}")
    print(f"  rr_ratio_below_min  : {lvc.get('rr_ratio_below_min')}")
    print(f"  actual_tp_bps       : {lvc.get('actual_tp_bps')}")
    print(f"  actual_sl_bps       : {lvc.get('actual_sl_bps')}")
