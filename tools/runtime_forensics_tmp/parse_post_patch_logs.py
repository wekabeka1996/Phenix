import json
from pathlib import Path
from datetime import datetime, timezone

PATCH_TS_MS = 1782845625000  # 2026-06-30T18:53:45Z UTC

def parse_order_log():
    path = Path("logs/order_log_v1.jsonl")
    if not path.exists():
        print("order log does not exist")
        return
    print("\n--- Scanning order_log_v1.jsonl ---")
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            # Some entries might not have ts_ms directly but might have it under event_ts or similar,
            # or we can check the record fields. Let's see what keys are there.
            ts = row.get("ts_ms") or row.get("event_ts_ms") or row.get("timestamp")
            if not ts and "rid" in row:
                # try to parse ts_ms from rid if it contains timestamp like symbol:ts_ms
                parts = row["rid"].split(":")
                if len(parts) >= 4:
                    try:
                        ts = int(parts[3])
                    except ValueError:
                        pass
            if ts and ts >= PATCH_TS_MS:
                count += 1
                dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                print(f"[{dt}] event_type={row.get('event_type')} rid={row.get('rid')} symbol={row.get('symbol')} side={row.get('side')} strategy={row.get('strategy_id') or row.get('strategy')}")
                if row.get("event_type") == "STRATEGY_DECISION_BLOCKED":
                    print(f"  Blocked reason: {row.get('blocked_reason')} gate_code={row.get('gate_code') or row.get('reject_reason')}")
    print(f"Total post-patch order log rows: {count}")

def parse_shadow_journal():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        return
    print("\n--- Scanning shadow_critical_event_journal_v1.jsonl (Blocks, Rejections, Fills) ---")
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = row.get("ts_ms")
            if ts and ts >= PATCH_TS_MS:
                event_name = row.get("event_name")
                if event_name in ("EVT:TRADE_INTENT_REJECTED", "EVT:GATE_CHAIN_TRACE", "EVT:ORDER_FILLED", "EVT:ORDER_PLACED", "EVT:BOOTSTRAP_COMPLETED"):
                    count += 1
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                    payload = row.get("payload", {})
                    # For GATE_CHAIN_TRACE or TRADE_INTENT_REJECTED, dump relevant fields
                    symbol = payload.get("symbol") or row.get("symbol")
                    side = payload.get("side") or row.get("side")
                    rid = payload.get("rid") or row.get("rid")
                    print(f"[{dt}] event={event_name} symbol={symbol} side={side} rid={rid}")
                    if event_name == "EVT:TRADE_INTENT_REJECTED":
                        print(f"  Reject reason: {payload.get('reject_reason')} gate={payload.get('gate_code') or payload.get('reject_family')}")
                    elif event_name == "EVT:GATE_CHAIN_TRACE":
                        print(f"  Trace: outcome={payload.get('outcome')} why={payload.get('why_short')} nrr027_enforced={payload.get('nrr027_effective_enforced')} nrr029_enforced={payload.get('nrr029_effective_enforced')}")
    print(f"Total post-patch shadow journal tracked events: {count}")

if __name__ == "__main__":
    parse_order_log()
    parse_shadow_journal()
