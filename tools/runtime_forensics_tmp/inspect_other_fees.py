import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = {t["trade_id"]: t for t in reader}

for tid in ["T_003", "T_004", "T_006", "T_010", "T_018"]:
    t = trades[tid]
    print(f"Trade: {tid}, status: {t['terminal_status']}, Entry Fee: {t['entry_fee']}, Close Fee: {t['close_fee']}, Total Fee: {t['total_fee']}")
