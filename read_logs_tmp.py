import json
from pathlib import Path

print("--- logs/features/BTCUSDT.log ---")
try:
    with open('logs/features/BTCUSDT.log', 'r') as f:
        print(f.readline().strip())
        print(f.readline().strip())
except Exception as e:
    print(f"Error: {e}")

print("
--- data/recorder/2026-03-01/BTCUSDT_300.csv ---")
try:
    with open('data/recorder/2026-03-01/BTCUSDT_300.csv', 'r') as f:
        for i in range(5):
            print(f.readline().strip())
except Exception as e:
    print(f"Error: {e}")

print("
--- logs/mean_reversion/bars_300s.jsonl ---")
try:
    with open('logs/mean_reversion/bars_300s.jsonl', 'r') as f:
        print(f.readline().strip())
        print(f.readline().strip())
except Exception as e:
    print(f"Error: {e}")
