import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
QA_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_audit_validation_v1"

with open(QA_DIR / "nrr_replay_validation.csv", 'r', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    mismatches = [row for row in reader if row["result_match"] == "no"]

print(f"Total mismatch rows: {len(mismatches)}")
print("\nFirst 10 mismatches:")
for idx, m in enumerate(mismatches[:10], 1):
    print(f"{idx}. rid: {m['rid']}, gate: {m['nrr_code']}, reported: {m['reported_result']}, validated: {m['validated_result']}")
    print(f"   reported_reason: {m['reported_reason']}")
    print(f"   validated_reason: {m['validated_reason']}")
