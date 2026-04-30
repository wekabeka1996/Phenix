import json
import sys
from collections import defaultdict

file_path = "logs/trade_lifecycle.jsonl"

symbols = defaultdict(lambda: {"SUPPRESSED": 0, "EVALUATED": 0, "SCORES": 0, "RECOMMENDED": 0, "ACTION_SKIPPED": 0})
suppression_reasons = defaultdict(lambda: {"count": 0, "symbols": set(), "first_ts": float('inf'), "last_ts": 0})
scores_stats = defaultdict(lambda: {"min": float('inf'), "max": float('-inf'), "examples": []})

suppressed_examples = []
evaluated_examples = []
scores_examples = []
close_reconciled_events = {"SUPPRESSED": 0, "EVALUATED": 0, "SCORES": 0, "RECOMMENDED": 0, "ACTION_SKIPPED": 0}
close_reconciled_symbols = set()

line_num = 0
with open(file_path, "r", encoding="utf-8") as f:
    for line in f:
        line_num += 1
        if not line.strip(): continue
        try:
            data = json.loads(line)
            event_type = data.get("event_type", "")
            if not event_type.startswith("POSITION_POLICY_SIDECAR_"):
                continue

            sub_type = event_type.replace("POSITION_POLICY_SIDECAR_", "")
            symbol = data.get("symbol", "UNKNOWN")
            ts_ms = data.get("ts_ms", 0)
            trigger_event = data.get("trigger_event", "UNKNOWN")
            
            if trigger_event == "EXECUTION_CLOSE_RECONCILED":
                if sub_type in close_reconciled_events:
                    close_reconciled_events[sub_type] += 1
                close_reconciled_symbols.add(symbol)

            if sub_type in symbols[symbol]:
                symbols[symbol][sub_type] += 1
            
            if sub_type == "SUPPRESSED":
                reasons = data.get("reason_codes", [])
                if not reasons:
                    reason = data.get("reason", "UNKNOWN")
                    reasons = [reason]
                
                for r in reasons:
                    suppression_reasons[r]["count"] += 1
                    suppression_reasons[r]["symbols"].add(symbol)
                    suppression_reasons[r]["first_ts"] = min(suppression_reasons[r]["first_ts"], ts_ms)
                    suppression_reasons[r]["last_ts"] = max(suppression_reasons[r]["last_ts"], ts_ms)
                
                if len(suppressed_examples) < 10:
                    suppressed_examples.append({
                        "line_num": line_num,
                        "ts_ms": ts_ms,
                        "symbol": symbol,
                        "event_type": event_type,
                        "trigger_event": trigger_event,
                        "highlights": {
                            "reason_codes": reasons,
                            "manage_state": data.get("manage_state"),
                            "position_qty": data.get("position_snapshot", {}).get("net_position", data.get("position_qty")),
                            "closing_position": data.get("closing_position")
                        }
                    })

            elif sub_type == "EVALUATED":
                if len(evaluated_examples) < 5:
                    evaluated_examples.append({
                        "line_num": line_num,
                        "ts_ms": ts_ms,
                        "symbol": symbol,
                        "event_type": event_type,
                        "trigger_event": trigger_event,
                        "highlights": {
                            "manage_state": data.get("manage_state"),
                            "closing_position": data.get("closing_position"),
                            "position_qty": data.get("position_snapshot", {}).get("net_position", data.get("position_qty")),
                            "freshness_ok": data.get("freshness_snapshot", {}).get("is_fresh")
                        }
                    })
            
            elif sub_type == "SCORES":
                scores = data.get("scores", {})
                for k, v in scores.items():
                    if isinstance(v, (int, float)):
                        scores_stats[k]["min"] = min(scores_stats[k]["min"], v)
                        scores_stats[k]["max"] = max(scores_stats[k]["max"], v)
                
                if len(scores_examples) < 5:
                    scores_examples.append({
                        "line_num": line_num,
                        "ts_ms": ts_ms,
                        "symbol": symbol,
                        "event_type": event_type,
                        "trigger_event": trigger_event,
                        "highlights": {
                            "position_health_score": scores.get("position_health_score"),
                            "exit_pressure_score": scores.get("exit_pressure_score"),
                            "soft_close_pressure": scores.get("soft_close_pressure"),
                            "manage_state": data.get("manage_state")
                        }
                    })
                    
        except json.JSONDecodeError:
            pass

print("--- SYMBOLS ---")
for sym, counts in symbols.items():
    highest = "SUPPRESSED"
    if counts["ACTION_SKIPPED"] > 0: highest = "ACTION_SKIPPED"
    elif counts["RECOMMENDED"] > 0: highest = "RECOMMENDED"
    elif counts["SCORES"] > 0: highest = "SCORES"
    elif counts["EVALUATED"] > 0: highest = "EVALUATED"
    print(f"{sym}|{counts['SUPPRESSED']}|{counts['EVALUATED']}|{counts['SCORES']}|{counts['RECOMMENDED']}|{counts['ACTION_SKIPPED']}|{highest}")

print("--- REASONS ---")
for r, data in suppression_reasons.items():
    syms = ",".join(list(data["symbols"]))
    print(f"{r}|{data['count']}|{syms}|{data['first_ts']}|{data['last_ts']}")

print("--- SCORES ---")
for k, data in scores_stats.items():
    print(f"{k}|{data['min']}|{data['max']}")

print("--- CLOSE RECONCILED ---")
print(json.dumps(close_reconciled_events))
print(f"Symbols: {','.join(list(close_reconciled_symbols))}")

print("--- SUPPRESSED EXAMPLES ---")
print(json.dumps(suppressed_examples))
print("--- EVALUATED EXAMPLES ---")
print(json.dumps(evaluated_examples))
print("--- SCORES EXAMPLES ---")
print(json.dumps(scores_examples))
