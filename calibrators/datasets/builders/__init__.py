"""Dataset builders for offline calibration.

Builders consume real data surfaces and produce validated datasets
that conform to Package 03A schema contracts.

Builders are OFFLINE only - they do not affect runtime behavior.
They produce datasets as calibration recommendations, not runtime truth.
"""

from calibrators.datasets.builders.common import (
    compute_basic_data_quality_summary,
    normalize_side,
    normalize_symbol,
    read_csv,
    read_jsonl,
    safe_parse_int_ts,
    source_paths_for,
    validate_and_count,
    write_csv,
    write_jsonl,
    write_manifest_json,
)
from calibrators.datasets.builders.objective_stack_builder import (
    build_objective_stack_dataset,
)
from calibrators.datasets.builders.low_vol_gate_builder import (
    build_low_vol_gate_dataset,
)
from calibrators.datasets.builders.walkforward_manifest_builder import (
    build_walkforward_manifest,
)

__all__ = [
    # Common utilities
    "read_jsonl",
    "read_csv",
    "safe_parse_int_ts",
    "normalize_symbol",
    "normalize_side",
    "write_jsonl",
    "write_csv",
    "write_manifest_json",
    "validate_and_count",
    "source_paths_for",
    "compute_basic_data_quality_summary",
    # Builders
    "build_objective_stack_dataset",
    "build_low_vol_gate_dataset",
    "build_walkforward_manifest",
]
