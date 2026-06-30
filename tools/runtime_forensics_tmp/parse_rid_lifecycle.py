import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"
RID = "aurora_BNBUSDT_1781943305149"

print(f"--- Significant events for {RID} ---")
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        if RID in line:
            obj = json.loads(line)
            et = obj.get("event_type")
            if et != "POSITION_POLICY_SIDECAR_SUPPRESSED":
                print(f"[{et}] ts_ms={obj.get('ts_ms') or obj.get('created_ts_ms')} status={obj.get('status')} keys={list(obj.keys())}")
                if "fill_price" in obj or "close_reason" in obj:
                    print(json.dumps({k: v for k, v in obj.items() if k in ('fill_price', 'fill_qty', 'fill_fees', 'close_price', 'close_reason', 'net_pnl', 'realized_pnl', 'fees', 'symbol', 'side')}, indent=2))
