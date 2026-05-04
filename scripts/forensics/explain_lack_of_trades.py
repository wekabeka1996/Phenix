import json
import os
from collections import Counter
from pathlib import Path

def analyze_order_log(file_path):
    print(f"Analyzing {file_path}...")
    if not os.path.exists(file_path):
        print("File not found.")
        return

    event_counts = Counter()
    rejection_reasons = Counter()
    symbol_activity = Counter()
    filled_trades = []
    rejections = []

    with open(file_path, 'r') as f:
        for line in f:
            try:
                event = json.loads(line)
                etype = event.get('event_type')
                symbol = event.get('symbol')
                event_counts[etype] += 1
                symbol_activity[symbol] += 1

                if etype == 'DECISION_INTENT_REJECTED':
                    reason = event.get('why', 'unknown')
                    rejection_reasons[f"{symbol}: {reason}"] += 1
                    rejections.append(event)
                
                if etype == 'ORDER_REJECTED':
                    reason = event.get('why', 'unknown')
                    rejection_reasons[f"{symbol}: ORDER_REJECTED: {reason}"] += 1

                if etype == 'ORDER_FILLED':
                    filled_trades.append(event)

            except Exception as e:
                print(f"Error parsing line: {e}")

    print("\n--- Event Totals ---")
    for k, v in event_counts.most_common():
        print(f"{k}: {v}")

    print("\n--- Symbol Activity ---")
    for k, v in symbol_activity.most_common():
        print(f"{k}: {v}")

    print("\n--- Top Rejection Reasons ---")
    for k, v in rejection_reasons.most_common(20):
        print(f"{v}x | {k}")

    print("\n--- Filled Trades ---")
    for trade in filled_trades:
        print(f"FILLED: {trade.get('symbol')} {trade.get('side')} Qty={trade.get('quantity')} @ {trade.get('price')} (ts={trade.get('timestamp')})")

if __name__ == "__main__":
    log_path = "logs/order_log_v1.jsonl"
    analyze_order_log(log_path)
