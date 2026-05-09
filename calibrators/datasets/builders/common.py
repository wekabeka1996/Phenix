"""Common utilities for dataset builders.

Reusable functions for reading, writing, normalizing, and validating
calibration datasets with explicit source path lineage and quality tracking.

All functions fail closed on unknown data or missing required fields.
No silent defaults or type coercion.
"""

import csv
import json
from pathlib import Path
from typing import Any, Generator, Optional

from calibrators.datasets.schema_registry import validate_row


DEFAULT_PROMOTION_MIN_REQUIRED_ROWS = 30
DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT = 50.0


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving first-seen order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _coverage_pct(count: Optional[int], total: int) -> Optional[float]:
    """Return percentage coverage for count/total or None if undefined."""
    if count is None:
        return None
    if total <= 0:
        return None
    return round((count / total) * 100.0, 4)


def _compute_coverage_quality(
    *,
    rows_emitted: int,
    exact_roundtrip_count: Optional[int],
    eligible_input_rows: Optional[int],
    matched_rows: Optional[int],
    unmatched_rows: Optional[int],
    min_required_rows: Optional[int],
    min_required_coverage_pct: Optional[float],
    coverage_row_blocker: str,
    coverage_pct_blocker: str,
) -> dict[str, Any]:
    """Compute dataset-level coverage fields and gates."""
    observed_rows = matched_rows if matched_rows is not None else rows_emitted
    if unmatched_rows is None and eligible_input_rows is not None:
        unmatched_rows = max(eligible_input_rows - observed_rows, 0)

    match_coverage_pct = _coverage_pct(observed_rows, eligible_input_rows or 0)
    exact_roundtrip_total = eligible_input_rows if eligible_input_rows is not None else rows_emitted
    exact_roundtrip_coverage_pct = _coverage_pct(
        exact_roundtrip_count,
        exact_roundtrip_total,
    )

    coverage_blockers: list[str] = []
    if min_required_rows is None and min_required_coverage_pct is None:
        coverage_grade = "NOT_APPLICABLE"
    elif observed_rows <= 0:
        coverage_grade = "EMPTY"
        if min_required_rows is not None:
            coverage_blockers.append(coverage_row_blocker)
        if min_required_coverage_pct is not None:
            coverage_blockers.append(coverage_pct_blocker)
    elif min_required_rows is not None and observed_rows < min_required_rows:
        coverage_grade = "SPARSE_DIAGNOSTIC"
        coverage_blockers.append(coverage_row_blocker)
        if (
            min_required_coverage_pct is not None
            and (match_coverage_pct is None or match_coverage_pct < min_required_coverage_pct)
        ):
            coverage_blockers.append(coverage_pct_blocker)
    elif (
        min_required_coverage_pct is not None
        and (match_coverage_pct is None or match_coverage_pct < min_required_coverage_pct)
    ):
        coverage_grade = "PARTIAL_DIAGNOSTIC"
        coverage_blockers.append(coverage_pct_blocker)
    else:
        coverage_grade = "PROMOTION_ELIGIBLE"

    return {
        "eligible_input_rows": eligible_input_rows,
        "matched_rows": observed_rows,
        "unmatched_rows": unmatched_rows,
        "match_coverage_pct": match_coverage_pct,
        "exact_roundtrip_coverage_pct": exact_roundtrip_coverage_pct,
        "min_required_rows": min_required_rows,
        "min_required_coverage_pct": min_required_coverage_pct,
        "coverage_grade": coverage_grade,
        "coverage_blockers": _dedupe_preserve_order(coverage_blockers),
    }


def read_jsonl(path: str | Path) -> list[tuple[dict[str, Any], int, str]]:
    """Read JSONL file with line number and source path provenance.

    Returns:
        List of (data_dict, line_number, source_path) tuples.
        Line numbers are 1-indexed.

    Raises:
        FileNotFoundError: If path does not exist.
        json.JSONDecodeError: On malformed JSON.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    results = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            try:
                data = json.loads(line)
                results.append((data, line_num, str(path)))
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Line {line_num} in {path}: {e.msg}",
                    e.doc,
                    e.pos,
                ) from e
    return results


def read_csv(path: str | Path) -> list[tuple[dict[str, Any], int, str]]:
    """Read CSV file with row number and source path provenance.

    Returns:
        List of (row_dict, row_number, source_path) tuples.
        Row numbers are 1-indexed (1 = header).

    Raises:
        FileNotFoundError: If path does not exist.
        csv.Error: On malformed CSV.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    results = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {path}")
        # 2 = first data row after header
        for row_num, row in enumerate(reader, start=2):
            results.append((row, row_num, str(path)))
    return results


def safe_parse_int_ts(value: Any) -> Optional[int]:
    """Parse timestamp value to milliseconds (int) or return None.

    Accepts:
    - int (assumed milliseconds)
    - float (converted to int milliseconds, truncated)
    - str (parsed as int)
    - None (returned as None)

    Returns:
        Millisecond timestamp (int) or None if parsing fails or input is None.

    Raises:
        ValueError: If type cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            val = int(value)
            return val
        except ValueError:
            try:
                val = float(value)
                return int(val)
            except ValueError:
                raise ValueError(
                    f"Cannot parse timestamp: {value!r}") from None
    raise ValueError(f"Unknown timestamp type: {type(value).__name__}")


def normalize_symbol(value: str) -> str:
    """Normalize symbol to uppercase.

    Args:
        value: Raw symbol string (e.g., 'btcusdt', 'BTCUSDT')

    Returns:
        Normalized symbol (e.g., 'BTCUSDT')

    Raises:
        ValueError: If empty or None.
    """
    if not value:
        raise ValueError("Symbol cannot be empty")
    return str(value).upper().strip()


def normalize_side(value: str) -> str:
    """Normalize side to lowercase canonical form.

    Args:
        value: Raw side string (e.g., 'LONG', 'Long', 'long', 'BUY', 'buy')

    Returns:
        Canonical side ('long' or 'short')

    Raises:
        ValueError: If not a recognized side.
    """
    if not value:
        raise ValueError("Side cannot be empty")
    norm = str(value).lower().strip()
    if norm in ("long", "buy"):
        return "long"
    if norm in ("short", "sell"):
        return "short"
    raise ValueError(f"Unknown side: {value!r}")


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> int:
    """Write rows to JSONL file.

    Args:
        path: Output file path.
        rows: List of dicts to write as JSONL.

    Returns:
        Number of rows written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return len(rows)


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> int:
    """Write rows to CSV file.

    Args:
        path: Output file path.
        rows: List of dicts to write as CSV.

    Returns:
        Number of rows written.

    Raises:
        ValueError: If rows list is empty or fieldnames cannot be inferred.
    """
    if not rows:
        raise ValueError("Cannot write CSV: no rows provided")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_manifest_json(path: str | Path, manifest: dict[str, Any]) -> str:
    """Write manifest dict to JSON file.

    Args:
        path: Output file path.
        manifest: Dict to write as JSON.

    Returns:
        Path as string.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return str(path)


def validate_and_count(
    schema_id: str, row_dicts: list[dict[str, Any]]
) -> tuple[int, int, list[str]]:
    """Validate all rows against schema; return counts and errors.

    Args:
        schema_id: Schema identifier for validation.
        row_dicts: List of row dicts to validate.

    Returns:
        Tuple of (valid_count, invalid_count, error_messages).
        Note: Does not raise; collects errors for reporting.
    """
    valid_count = 0
    invalid_count = 0
    errors = []

    for i, row_dict in enumerate(row_dicts):
        try:
            validate_row(schema_id, row_dict)
            valid_count += 1
        except Exception as e:
            invalid_count += 1
            errors.append(f"Row {i}: {str(e)}")

    return valid_count, invalid_count, errors


def source_paths_for(*paths: str | Path) -> list[str]:
    """Build source_paths list from provided paths.

    Args:
        *paths: Variable number of file paths.

    Returns:
        List of path strings, deduplicated, sorted.
    """
    unique_paths = sorted(set(str(p) for p in paths))
    return unique_paths


def compute_basic_data_quality_summary(
    rows: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    *,
    rows_valid: Optional[int] = None,
    rows_invalid: Optional[int] = None,
    builder_valid: bool = True,
    has_realized_outcomes: Optional[bool] = None,
    exact_roundtrip_count: Optional[int] = None,
    diagnostics_only: Optional[bool] = None,
    empty_dataset_blocker: str = "EMPTY_DATASET",
    eligible_input_rows: Optional[int] = None,
    matched_rows: Optional[int] = None,
    unmatched_rows: Optional[int] = None,
    min_required_rows: Optional[int] = None,
    min_required_coverage_pct: Optional[float] = None,
    coverage_row_blocker: str = "INSUFFICIENT_MATCHED_ROWS",
    coverage_pct_blocker: str = "INSUFFICIENT_MATCH_COVERAGE",
) -> dict[str, Any]:
    """Compute basic data quality summary for a dataset.

    Args:
        rows: Output rows.
        blockers: List of blocker messages (things that prevent promotion).
        warnings: List of warning messages (things that might affect calibration).

    Returns:
        Summary dict that separates builder success from promotion readiness.
    """
    rows_emitted = len(rows)
    if rows_valid is None:
        rows_valid = rows_emitted
    if rows_invalid is None:
        rows_invalid = max(rows_emitted - rows_valid, 0)

    promotion_blockers = list(blockers)
    if rows_emitted == 0 and empty_dataset_blocker not in promotion_blockers:
        promotion_blockers.append(empty_dataset_blocker)

    coverage_summary = _compute_coverage_quality(
        rows_emitted=rows_emitted,
        exact_roundtrip_count=exact_roundtrip_count,
        eligible_input_rows=eligible_input_rows,
        matched_rows=matched_rows,
        unmatched_rows=unmatched_rows,
        min_required_rows=min_required_rows,
        min_required_coverage_pct=min_required_coverage_pct,
        coverage_row_blocker=coverage_row_blocker,
        coverage_pct_blocker=coverage_pct_blocker,
    )
    promotion_blockers.extend(coverage_summary["coverage_blockers"])

    promotion_blockers = _dedupe_preserve_order(promotion_blockers)
    warning_messages = _dedupe_preserve_order(list(warnings))
    schema_valid = rows_invalid == 0
    has_rows = rows_emitted > 0
    if diagnostics_only is None:
        diagnostics_only = (
            not has_rows
            or has_realized_outcomes is False
            or coverage_summary["coverage_grade"]
            not in ("NOT_APPLICABLE", "PROMOTION_ELIGIBLE")
        )

    coverage_ready = coverage_summary["coverage_grade"] in (
        "NOT_APPLICABLE",
        "PROMOTION_ELIGIBLE",
    )

    promotion_grade = (
        builder_valid
        and schema_valid
        and has_rows
        and rows_invalid == 0
        and not diagnostics_only
        and coverage_ready
        and not promotion_blockers
    )

    return {
        "builder_valid": builder_valid,
        "schema_valid": schema_valid,
        "has_rows": has_rows,
        "rows_emitted": rows_emitted,
        "rows_valid": rows_valid,
        "rows_invalid": rows_invalid,
        "has_realized_outcomes": has_realized_outcomes,
        "exact_roundtrip_count": exact_roundtrip_count,
        "eligible_input_rows": coverage_summary["eligible_input_rows"],
        "matched_rows": coverage_summary["matched_rows"],
        "unmatched_rows": coverage_summary["unmatched_rows"],
        "match_coverage_pct": coverage_summary["match_coverage_pct"],
        "exact_roundtrip_coverage_pct": coverage_summary[
            "exact_roundtrip_coverage_pct"
        ],
        "min_required_rows": coverage_summary["min_required_rows"],
        "min_required_coverage_pct": coverage_summary[
            "min_required_coverage_pct"
        ],
        "coverage_grade": coverage_summary["coverage_grade"],
        "coverage_blockers": coverage_summary["coverage_blockers"],
        "diagnostics_only": diagnostics_only,
        "promotion_grade": promotion_grade,
        "promotion_blockers": promotion_blockers,
        "warnings": warning_messages,
        "total_rows": rows_emitted,
        "blockers": promotion_blockers,
        "blocker_count": len(promotion_blockers),
        "warning_count": len(warning_messages),
    }
