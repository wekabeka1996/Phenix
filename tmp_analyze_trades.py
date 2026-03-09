import json
from pathlib import Path

# We want to find losing trades/positions and why they were closed.
# The `order_log_v1.jsonl` contains orders. But let's check `aurora_trades.log` which has trades.
try:
    trade_path = Path('logs/aurora_trades.log')
    trades = trade_path.read_text(encoding='utf-8', errors='replace').strip().split('\n')
    print(f"Read {len(trades)} lines from aurora_trades.log")
    for t in trades[:5]:
        print(t)
    print("---")
    for t in trades[-5:]:
        print(t)
except Exception as e:
    print(f"Error reading aurora_trades.log: {e}")

# Also analyze `order_log_v1.jsonl` for filled orders that might be closing a position.
# Look for ORDER_FILLED or similar.
path = Path('logs/order_log_v1.jsonl')
lines = path.read_text(encoding='utf-8', errors='replace').strip().split('\n')

fills = []
for line in lines:
    if not line.strip(): continue
    try:
        obj = json.loads(line)
        et = obj.get('event_type')
        if et in ('ORDER_FILLED', 'ORDER_FILL_DISCOVERED', 'TRADE'):
            fills.append(obj)
        # some logs might just use `status` = 'FILLED'
        if obj.get('status') == 'FILLED' or obj.get('adapter_response', {}).get('status') == 'FILLED':
            fills.append(obj)
    except Exception:
        pass

print(f"\nFound {len(fills)} filled orders in order_log.")
for f in fills[:5]:
    print(f)
