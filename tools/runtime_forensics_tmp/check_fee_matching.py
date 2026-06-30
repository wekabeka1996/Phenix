import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

mismatches = 0
for t in trades:
    entry_fee = float(t["entry_fee"])
    close_fee = float(t["close_fee"])
    total_fee = float(t["total_fee"])
    sum_fee = entry_fee + close_fee
    diff = abs(total_fee - sum_fee)
    if diff > 1e-5:
        print(f"Trade: {t['trade_id']}, Status: {t['terminal_status']}, Entry Fee: {entry_fee:.6f}, Close Fee: {close_fee:.6f}, Sum: {sum_fee:.6f}, Total Fee (reported): {total_fee:.6f}, Diff: {total_fee - sum_fee:.6f}")
        mismatches += 1

print(f"Total mismatches: {mismatches} out of {len(trades)}")
