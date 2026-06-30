import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

print(f"Total reconstructed trades: {len(trades)}")
status_counts = {}
pnl_sums = {}
fee_sums = {}
for t in trades:
    status = t["terminal_status"]
    status_counts[status] = status_counts.get(status, 0) + 1
    pnl_sums[status] = pnl_sums.get(status, 0.0) + float(t["net_pnl"])
    fee_sums[status] = fee_sums.get(status, 0.0) + float(t["total_fee"])

print("\nReported status breakdowns:")
for status, count in status_counts.items():
    print(f"  {status}: count={count}, Net PnL={pnl_sums[status]:.6f}, Total Fee={fee_sums[status]:.6f}")

print(f"\nAll trades sum: Net PnL={sum(float(t['net_pnl']) for t in trades):.6f}, Total Fee={sum(float(t['total_fee']) for t in trades):.6f}")
