import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]
WAL_FILES = [
    ROOT / "ops" / "wal" / "2026-06-18.jsonl",
    ROOT / "ops" / "wal" / "2026-06-19.jsonl",
    ROOT / "ops" / "wal" / "2026-06-20.jsonl",
]

# 1. Load all blocked RIDs and their bracket geometry from STRATEGY_SIGNAL_PRODUCED
blocked_trades = {}
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS:
                rid = obj.get("rid")
                if obj.get("event_type") == "DECISION_INTENT_REJECTED":
                    nrr = obj.get("nrr_code")
                    if nrr in ("NRR-027", "NRR-028", "NRR-029", "NRR-030"):
                        blocked_trades[rid] = {
                            "rid": rid,
                            "symbol": obj["symbol"],
                            "side": obj["side"],
                            "event_ts": ts,
                            "gate_code": nrr,
                            "regime": obj.get("regime"),
                            "regime_confidence": obj.get("regime_confidence"),
                            "entry_price": None,
                            "stop_price": None,
                            "target_price": None,
                        }

for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            rid = obj.get("rid")
            if rid in blocked_trades and obj.get("event_type") == "STRATEGY_SIGNAL_PRODUCED":
                meta = obj.get("metadata", {})
                if meta.get("entry_price"):
                    blocked_trades[rid]["entry_price"] = float(meta["entry_price"])
                    blocked_trades[rid]["stop_price"] = float(meta["stop_price"])
                    blocked_trades[rid]["target_price"] = float(meta["target_price"])

# 2. Load all closed bars from WAL files for our symbols and timeframes
print("Loading closed bars from WAL files...")
bars = []
for wf in WAL_FILES:
    if not wf.exists():
        continue
    with open(wf, "r", encoding="utf-8") as f:
        for line in f:
            if "BAR_CLOSED" not in line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("verb") == "BAR_CLOSED":
                    pld = obj.get("pld", {})
                    symbol = pld.get("symbol")
                    tf = pld.get("tf_sec")
                    bar = pld.get("bar", {})
                    # We want the lowest timeframe bar to be most granular (e.g. 180 or 300)
                    if tf in (180, 300):
                        bars.append({
                            "symbol": symbol,
                            "tf_sec": tf,
                            "bar_close_ts": pld.get("bar_close_ts") or bar.get("end_ts_ms"),
                            "open": float(bar["open"]),
                            "high": float(bar["high"]),
                            "low": float(bar["low"]),
                            "close": float(bar["close"]),
                        })
            except Exception as e:
                pass

print(f"Loaded {len(bars)} bars.")
# Sort bars chronologically
bars.sort(key=lambda x: x["bar_close_ts"])

# 3. For each blocked trade, replay the outcome
print("\nReplaying blocked trades...")
for rid, t in blocked_trades.items():
    symbol = t["symbol"]
    side = t["side"].upper() # BUY or SELL
    # Map to LONG/SHORT
    mapped_side = "LONG" if side == "BUY" else "SHORT"
    event_ts = t["event_ts"]
    entry = t["entry_price"]
    stop = t["stop_price"]
    target = t["target_price"]
    
    if entry is None or stop is None or target is None:
        t["replay_result"] = "OUTCOME_UNPROVEN"
        t["pnl"] = None
        t["reason"] = "Geometry missing"
        print(f"rid={rid} symbol={symbol} side={side} result=OUTCOME_UNPROVEN pnl=None reason=Geometry missing")
        continue
        
    # Find all bars for this symbol that closed AFTER the event timestamp
    symbol_bars = [b for b in bars if b["symbol"] == symbol and b["bar_close_ts"] > event_ts]
    
    outcome = "OUTCOME_UNPROVEN"
    pnl = None
    reason = "No bars found or horizon elapsed"
    
    for b in symbol_bars:
        high = b["high"]
        low = b["low"]
        
        # Check if both SL and TP are hit in the same bar
        hit_stop = False
        hit_target = False
        
        if mapped_side == "LONG":
            if low <= stop:
                hit_stop = True
            if high >= target:
                hit_target = True
        elif mapped_side == "SHORT":
            if high >= stop:
                hit_stop = True
            if low <= target:
                hit_target = True
                
        if hit_stop and hit_target:
            outcome = "OUTCOME_UNPROVEN"
            reason = "Both TP and SL hit in the same bar"
            break
        elif hit_stop:
            outcome = "WOULD_HAVE_LOST"
            if mapped_side == "LONG":
                pnl = stop - entry
            else:
                pnl = entry - stop
            reason = f"Hit SL first at {b['bar_close_ts']} (price={stop})"
            break
        elif hit_target:
            outcome = "WOULD_HAVE_WON"
            if mapped_side == "LONG":
                pnl = target - entry
            else:
                pnl = entry - target
            reason = f"Hit TP first at {b['bar_close_ts']} (price={target})"
            break
            
    t["replay_result"] = outcome
    t["pnl"] = pnl
    t["reason"] = reason
    print(f"rid={rid} symbol={symbol} side={side} result={outcome} pnl={pnl} reason={reason}")
