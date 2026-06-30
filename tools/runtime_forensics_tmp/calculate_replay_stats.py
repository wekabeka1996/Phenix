import json
from pathlib import Path

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

# Load closed bars
bars = []
for wf in WAL_FILES:
    if not wf.exists():
        continue
    with open(wf, "r", encoding="utf-8") as f:
        for line in f:
            if "BAR_CLOSED" not in line:
                continue
            obj = json.loads(line)
            if obj.get("verb") == "BAR_CLOSED":
                pld = obj.get("pld", {})
                symbol = pld.get("symbol")
                tf = pld.get("tf_sec")
                bar = pld.get("bar", {})
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
bars.sort(key=lambda x: x["bar_close_ts"])

# Replay
pos_size = 10000.0  # 10k USDT
fee_est = 10.0      # 10 USDT total round-trip fee

by_gate = {}

for rid, t in blocked_trades.items():
    symbol = t["symbol"]
    side = t["side"].upper()
    mapped_side = "LONG" if side == "BUY" else "SHORT"
    event_ts = t["event_ts"]
    entry = t["entry_price"]
    stop = t["stop_price"]
    target = t["target_price"]
    gate = t["gate_code"]
    
    if gate not in by_gate:
        by_gate[gate] = {"win_count": 0, "loss_count": 0, "pnl_sum": 0.0, "total_count": 0, "unproven_count": 0}
        
    by_gate[gate]["total_count"] += 1
    
    if entry is None or stop is None or target is None:
        by_gate[gate]["unproven_count"] += 1
        continue
        
    symbol_bars = [b for b in bars if b["symbol"] == symbol and b["bar_close_ts"] > event_ts]
    
    outcome = "OUTCOME_UNPROVEN"
    net_pnl = 0.0
    
    for b in symbol_bars:
        high = b["high"]
        low = b["low"]
        
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
            break
        elif hit_stop:
            outcome = "WOULD_HAVE_LOST"
            pct = (stop - entry) / entry if mapped_side == "LONG" else (entry - stop) / entry
            net_pnl = (pct * pos_size) - fee_est
            break
        elif hit_target:
            outcome = "WOULD_HAVE_WON"
            pct = (target - entry) / entry if mapped_side == "LONG" else (entry - target) / entry
            net_pnl = (pct * pos_size) - fee_est
            break
            
    if outcome == "WOULD_HAVE_WON":
        by_gate[gate]["win_count"] += 1
        by_gate[gate]["pnl_sum"] += net_pnl
    elif outcome == "WOULD_HAVE_LOST":
        by_gate[gate]["loss_count"] += 1
        by_gate[gate]["pnl_sum"] += net_pnl
    else:
        by_gate[gate]["unproven_count"] += 1

print("\n--- Summary by Gate Code (10k USDT size, 10 USDT fee) ---")
for gate, stats in by_gate.items():
    print(f"Gate: {gate}")
    print(f"  Total Blocks: {stats['total_count']}")
    print(f"  Would Have Won (Winners): {stats['win_count']}")
    print(f"  Would Have Lost (Losers): {stats['loss_count']}")
    print(f"  Unproven: {stats['unproven_count']}")
    print(f"  Simulated Net PnL: {stats['pnl_sum']:.4f} USDT")
