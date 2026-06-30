import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

print("--- RECONSTRUCTED TRADES ---")
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

print(f"Total reconstructed trades: {len(trades)}")
unresolved_trades = [t for t in trades if t["terminal_status"] in ("UNRESOLVED", "OPEN", "PARTIAL")]
print(f"Unresolved/Open/Partial trades: {len(unresolved_trades)}")
for ut in unresolved_trades:
    print(f"Trade: {ut['trade_id']}, status: {ut['terminal_status']}, Entry Fee: {ut['entry_fee']}, Close Fee: {ut['close_fee']}, Total Fee: {ut['total_fee']}, Net PnL: {ut['net_pnl']}, Gross PnL: {ut['gross_pnl']}")

print("\n--- ALL TRADES WITH TOTAL FEE == 0 or ENTRY FEE > 0 AND TOTAL FEE < ENTRY FEE ---")
for t in trades:
    entry_fee = float(t["entry_fee"])
    close_fee = float(t["close_fee"])
    total_fee = float(t["total_fee"])
    if total_fee < entry_fee or (total_fee == 0.0 and entry_fee > 0.0):
        print(f"Trade: {t['trade_id']}, status: {t['terminal_status']}, Entry Fee: {t['entry_fee']}, Close Fee: {t['close_fee']}, Total Fee: {t['total_fee']}, Net PnL: {t['net_pnl']}")
