import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

pps_trades = [t for t in trades if "ppsreq" in t["lifecycle_id"] or "pps" in t["lifecycle_id"]]
print(f"Total reconstructed trades: {len(trades)}")
print(f"PPS/ppsreq trades in trades_reconstructed.csv: {len(pps_trades)}")
for pt in pps_trades:
    print(f"Trade: {pt['trade_id']}, lifecycle_id: {pt['lifecycle_id']}, symbol: {pt['symbol']}, net_pnl: {pt['net_pnl']}")
