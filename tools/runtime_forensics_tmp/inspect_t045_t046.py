import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["trade_id"] in ("T_045", "T_046"):
            print(f"\n==================== {row['trade_id']} ====================")
            for k, v in row.items():
                if v:
                    print(f"  {k}: {v}")
