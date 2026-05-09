"""Validate smoke run output artifacts."""
import json
from pathlib import Path

# Check objective builder output
obj_dir = Path("artifacts/calibration_datasets/_smoke_03b_objective")
obj_jsonl = obj_dir / "trade_decisions.jsonl"
obj_manifest = obj_dir / "dataset_manifest.json"
obj_report = obj_dir / "DATA_QUALITY_REPORT.md"

print("=" * 60)
print("OBJECTIVE BUILDER VALIDATION")
print("=" * 60)

if obj_jsonl.exists():
    lines = obj_jsonl.read_text().strip().split("\n")
    print(f"Decision rows in JSONL: {len(lines)}")

    # Validate first row
    if lines:
        first = json.loads(lines[0])
        print(f"First row schema: {first.get('dataset_schema')}")
        print(f"First row version: {first.get('dataset_version')}")
        print(f"Has synthetic field: {'synthetic' in first}")
        print(f"Has source_paths: {'source_paths' in first}")
        print(f"Has dataset_visibility: {'dataset_visibility' in first}")

if obj_manifest.exists():
    manifest = json.loads(obj_manifest.read_text())
    print(f"\nManifest builder: {manifest.get('builder')}")
    print(f"Output schemas: {manifest.get('output_schemas')}")
    summary = manifest.get('data_quality', {})
    print(f"Builder valid: {summary.get('builder_valid')}")
    print(f"Schema valid: {summary.get('schema_valid')}")
    print(f"Diagnostics only: {summary.get('diagnostics_only')}")
    print(f"Promotion grade: {summary.get('promotion_grade')}")

if obj_report.exists():
    report = obj_report.read_text()
    print(f"\nQuality report exists: {len(report)} chars")
    if "Promotion grade:" in report and "Builder valid:" in report:
        print("Quality report format: valid")

# Check low-vol builder output
lowvol_dir = Path("artifacts/calibration_datasets/_smoke_03b_lowvol")
lowvol_manifest = lowvol_dir / "dataset_manifest.json"
lowvol_report = lowvol_dir / "DATA_QUALITY_REPORT.md"

print("\n" + "=" * 60)
print("LOW-VOL BUILDER VALIDATION")
print("=" * 60)

if lowvol_manifest.exists():
    manifest = json.loads(lowvol_manifest.read_text())
    summary = manifest.get('data_quality', {})
    print(f"Gate rows: {summary.get('gate_rows_count', 0)}")
    print(f"Diagnostics only: {summary.get('diagnostics_only')}")
    print(f"Promotion grade: {summary.get('promotion_grade')}")
else:
    print("Low-vol output: No rows produced (acceptable - no matching LOW_VOL trades)")

print("\n" + "=" * 60)
print("VALIDATION COMPLETE")
print("=" * 60)
