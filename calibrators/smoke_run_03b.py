from calibrators.datasets.builders.objective_stack_builder import build_objective_stack_dataset
from calibrators.datasets.builders.low_vol_gate_builder import build_low_vol_gate_dataset
import sys
from pathlib import Path

"""Smoke run for Package 03B builders."""

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


# Objective stack builder
print("=" * 60)
print("SMOKE RUN: Objective Stack Builder")
print("=" * 60)

out_dir = Path("artifacts/calibration_datasets/_smoke_03b_objective")
out_dir.mkdir(parents=True, exist_ok=True)

result = build_objective_stack_dataset(out_dir=str(out_dir))

print(
    f"Decision rows: {result.data_quality_summary.get('decision_rows_count', 0)}")
print(
    f"Realized trade rows: {result.data_quality_summary.get('realized_rows_count', 0)}")
print(
    f"Exact roundtrips: {result.data_quality_summary.get('exact_roundtrip_count', 0)}")
print(f"Blockers: {len(result.blockers)}")
print(f"Warnings: {len(result.warnings)}")
print(
    f"Builder valid: {result.data_quality_summary.get('builder_valid', False)}")
print(
    f"Schema valid: {result.data_quality_summary.get('schema_valid', False)}")
print(
    f"Diagnostics only: {result.data_quality_summary.get('diagnostics_only', False)}")
print(
    f"Promotion grade: {result.data_quality_summary.get('promotion_grade', False)}")
print(f"Output: {out_dir}")

if result.blockers:
    print("\nBlockers:")
    for b in result.blockers[:5]:
        print(f"  - {b}")
    if len(result.blockers) > 5:
        print(f"  ... and {len(result.blockers) - 5} more")

# Low-vol gate builder
print("\n" + "=" * 60)
print("SMOKE RUN: Low-Vol Gate Builder")
print("=" * 60)

out_dir2 = Path("artifacts/calibration_datasets/_smoke_03b_lowvol")
out_dir2.mkdir(parents=True, exist_ok=True)

result2 = build_low_vol_gate_dataset(out_dir=str(out_dir2))

print(f"Gate rows: {result2.data_quality_summary.get('gate_rows_count', 0)}")
print(
    f"Exact roundtrips: {result2.data_quality_summary.get('exact_roundtrip_count', 0)}")
print(f"Blockers: {len(result2.blockers)}")
print(f"Warnings: {len(result2.warnings)}")
print(
    f"Builder valid: {result2.data_quality_summary.get('builder_valid', False)}")
print(
    f"Schema valid: {result2.data_quality_summary.get('schema_valid', False)}")
print(
    f"Diagnostics only: {result2.data_quality_summary.get('diagnostics_only', False)}")
print(
    f"Promotion grade: {result2.data_quality_summary.get('promotion_grade', False)}")
print(f"Output: {out_dir2}")

if result2.blockers:
    print("\nBlockers:")
    for b in result2.blockers[:5]:
        print(f"  - {b}")
    if len(result2.blockers) > 5:
        print(f"  ... and {len(result2.blockers) - 5} more")

print("\n" + "=" * 60)
print("SMOKE RUN COMPLETE")
print("=" * 60)
