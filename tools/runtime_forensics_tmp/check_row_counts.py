import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

csv_files = [
    "normalized_events.csv",
    "trades_reconstructed.csv",
    "orders_normalized.csv",
    "execution_lifecycle_defects.csv",
    "nrr_replay_rows.csv",
    "nrr_economic_join.csv",
    "nrr_usefulness_matrix.csv"
]

for filename in csv_files:
    filepath = REPORTS_DIR / filename
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
            print(f"{filename}: header={len(header)} cols, rows={len(rows)}")
    else:
        print(f"{filename} does not exist!")
