import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]
SHADOW_JOURNAL = ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"

rejections = {}
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
                if ts < T8_TS_MS:
                    continue
                if obj.get("event_type") == "DECISION_INTENT_REJECTED":
                    nrr = obj.get("nrr_code")
                    if nrr in ("NRR-027", "NRR-028", "NRR-029", "NRR-030"):
                        rejections[obj["rid"]] = {
                            "rid": obj["rid"],
                            "symbol": obj["symbol"],
                            "side": obj["side"],
                            "strategy_id": obj["strategy_id"],
                            "event_ts": ts,
                            "gate_code": nrr,
                            "observed_block_reason": obj.get("why", ""),
                            "regime": obj.get("regime", ""),
                            "regime_confidence": obj.get("regime_confidence", None),
                            "trace_found": False
                        }
            except Exception as e:
                pass

print(f"Loaded {len(rejections)} rejections from order logs.")

# Now scan shadow journal to populate details
with open(SHADOW_JOURNAL, "r", encoding="utf-8") as f:
    for line in f:
        if "EVT:DECISION_TRACE_EMITTED" not in line:
            continue
        try:
            obj = json.loads(line)
            rid = obj.get("rid")
            if rid in rejections:
                pf = obj.get("payload_fragment", {})
                rejections[rid]["trend_dir"] = pf.get("trend_dir")
                rejections[rid]["trend_confidence"] = pf.get("trend_confidence")
                rejections[rid]["trend_run_length"] = pf.get("trend_run_length")
                rejections[rid]["pm_norm_10s"] = pf.get("pm_norm_10s")
                rejections[rid]["pm_norm_60s"] = pf.get("pm_norm_60s")
                rejections[rid]["pm_norm_300s"] = pf.get("pm_norm_300s")
                rejections[rid]["trace_found"] = True
        except Exception as e:
            pass

# Count how many traces were found
traces_found = sum(1 for r in rejections.values() if r["trace_found"])
print(f"Found shadow journal traces for {traces_found} out of {len(rejections)} rejections.")

for r in rejections.values():
    if not r["trace_found"]:
        print(f"MISSING TRACE: rid={r['rid']} symbol={r['symbol']} gate={r['gate_code']}")
    else:
        print(f"[{r['gate_code']}] rid={r['rid']} trend={r.get('trend_dir')}({r.get('trend_run_length')}) pm_60={r.get('pm_norm_60s')} pm_300={r.get('pm_norm_300s')}")
