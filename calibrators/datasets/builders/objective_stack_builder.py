"""Objective stack joined dataset builder.

Joins decision/intent data with realized trade outcomes to produce training
datasets for entry/exit calibration.

Consumes:
- authority request journal
- authority response journal
- decision ledger
- executed trades reports

Produces:
- calibration_trade_decision_dataset_v1 (JSONL)
- calibration_realized_trade_dataset_v1 (JSONL)
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from calibrators.datasets.builders.common import (
    DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT,
    DEFAULT_PROMOTION_MIN_REQUIRED_ROWS,
    compute_basic_data_quality_summary,
    normalize_side,
    normalize_symbol,
    read_csv,
    read_jsonl,
    safe_parse_int_ts,
    source_paths_for,
    validate_and_count,
    write_jsonl,
    write_manifest_json,
)
from calibrators.datasets.schema_registry import validate_row


@dataclass
class BuilderResult:
    """Result of dataset builder run."""

    decision_rows: list[dict[str, Any]]
    realized_rows: list[dict[str, Any]]
    data_quality_summary: dict[str, Any]
    blockers: list[str]
    warnings: list[str]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _summarize_realized_source_rows(
    rows: list[dict[str, Any]],
    *,
    eligible_input_rows: int,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    exact_roundtrip_count = sum(
        1 for row in rows if row.get("exact_roundtrip"))
    summary = compute_basic_data_quality_summary(
        rows,
        [],
        warnings or [],
        rows_valid=len(rows),
        rows_invalid=0,
        has_realized_outcomes=bool(rows),
        exact_roundtrip_count=exact_roundtrip_count,
        eligible_input_rows=eligible_input_rows,
        matched_rows=len(rows),
        unmatched_rows=max(eligible_input_rows - len(rows), 0),
        min_required_rows=DEFAULT_PROMOTION_MIN_REQUIRED_ROWS,
        min_required_coverage_pct=DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT,
        coverage_row_blocker="INSUFFICIENT_REALIZED_ROWS",
        coverage_pct_blocker="INSUFFICIENT_REALIZED_COVERAGE",
        empty_dataset_blocker="EMPTY_REALIZED_OUTCOME_DATASET",
    )
    if rows and exact_roundtrip_count < len(rows):
        source_blockers = _dedupe_preserve_order(
            [*summary["promotion_blockers"], "PARTIAL_EXACT_ROUNDTRIPS"]
        )
        summary["promotion_blockers"] = source_blockers
        summary["blockers"] = source_blockers
        summary["blocker_count"] = len(source_blockers)
        summary["diagnostics_only"] = True
        summary["promotion_grade"] = False
    return summary


def _load_canonical_realized_source_summary(
    realized_path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_path = realized_path.parent / "dataset_manifest.json"
    manifest_warnings: list[str] = []
    eligible_input_rows = len(rows)

    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            manifest_warnings.append(f"INVALID_REALIZED_SOURCE_MANIFEST:{exc}")
        else:
            manifest_quality = payload.get("data_quality") if isinstance(
                payload.get("data_quality"), dict) else payload
            manifest_eligible = _parse_int(
                manifest_quality.get("eligible_input_rows")
            )
            if manifest_eligible is None:
                manifest_eligible = _parse_int(
                    manifest_quality.get("eligible_decision_rows")
                )
            if manifest_eligible is not None:
                eligible_input_rows = manifest_eligible
    else:
        manifest_warnings.append("MISSING_REALIZED_SOURCE_MANIFEST")

    summary = _summarize_realized_source_rows(
        rows,
        eligible_input_rows=eligible_input_rows,
        warnings=manifest_warnings,
    )
    summary["source_authority"] = "CANONICAL_REALIZED_OUTCOME_DATASET"
    return summary


def summarize_objective_stack_quality(
    decision_rows: list[dict[str, Any]],
    realized_rows: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    *,
    valid_dec: int,
    invalid_dec: int,
    valid_real: int,
    invalid_real: int,
    source_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Summarize objective builder quality without conflating promotion readiness."""
    all_rows = decision_rows + realized_rows
    promotion_blockers = list(blockers)
    has_realized_outcomes = len(realized_rows) > 0
    exact_roundtrip_count = sum(
        1 for row in realized_rows if row.get("exact_roundtrip")
    )
    source_promotion_grade = (
        source_summary.get("promotion_grade")
        if source_summary is not None
        else None
    )
    source_coverage_grade = (
        source_summary.get("coverage_grade")
        if source_summary is not None
        else "NOT_APPLICABLE"
    )
    source_promotion_blockers = list(
        source_summary.get("promotion_blockers", [])
    ) if source_summary is not None else []
    source_eligible_rows = (
        source_summary.get("eligible_input_rows")
        if source_summary is not None
        else len(decision_rows)
    )

    if not has_realized_outcomes:
        promotion_blockers.append("NO_REALIZED_TRADE_ROWS")
    if exact_roundtrip_count == 0:
        promotion_blockers.append("NO_EXACT_ROUNDTRIPS")
    if source_summary is not None and source_promotion_grade is False:
        promotion_blockers.append(
            "SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE")
        promotion_blockers.extend(source_promotion_blockers)

    diagnostics_only = (
        not all_rows
        or not has_realized_outcomes
        or exact_roundtrip_count == 0
        or source_promotion_grade is False
    )
    summary = compute_basic_data_quality_summary(
        all_rows,
        promotion_blockers,
        warnings,
        rows_valid=valid_dec + valid_real,
        rows_invalid=invalid_dec + invalid_real,
        has_realized_outcomes=has_realized_outcomes,
        exact_roundtrip_count=exact_roundtrip_count,
        diagnostics_only=diagnostics_only,
        eligible_input_rows=source_eligible_rows,
        matched_rows=len(realized_rows),
        unmatched_rows=max(source_eligible_rows - len(realized_rows), 0),
        min_required_rows=DEFAULT_PROMOTION_MIN_REQUIRED_ROWS,
        min_required_coverage_pct=DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT,
        coverage_row_blocker="INSUFFICIENT_REALIZED_ROWS",
        coverage_pct_blocker="INSUFFICIENT_REALIZED_COVERAGE",
    )
    summary.update(
        {
            "decision_rows_count": len(decision_rows),
            "decision_rows_valid": valid_dec,
            "realized_rows_count": len(realized_rows),
            "realized_rows_valid": valid_real,
            "exact_roundtrip_count": exact_roundtrip_count,
            "realized_source_coverage_pct": (
                source_summary.get("match_coverage_pct")
                if source_summary is not None
                else summary.get("match_coverage_pct")
            ),
            "source_promotion_grade": source_promotion_grade,
            "source_coverage_grade": source_coverage_grade,
            "source_promotion_blockers": source_promotion_blockers,
            "source_authority": (
                source_summary.get("source_authority")
                if source_summary is not None
                else None
            ),
        }
    )
    return summary


def build_objective_stack_dataset(
    repo_root: Optional[str | Path] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    out_dir: Optional[str | Path] = None,
    realized_outcome_dataset: Optional[str | Path] = None,
) -> BuilderResult:
    """Build objective_stack joined datasets.

    Args:
        repo_root: Repository root path. Auto-detected if None.
        date_start: ISO date start filter (YYYY-MM-DD), optional.
        date_end: ISO date end filter (YYYY-MM-DD), optional.
        out_dir: Output directory. If None, returns in-memory result only.

    Returns:
        BuilderResult with decision rows, realized rows, and quality report.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    blockers: list[str] = []
    warnings: list[str] = []
    decision_rows: list[dict[str, Any]] = []
    realized_rows: list[dict[str, Any]] = []

    # Load source data
    authority_requests = {}  # rid -> request data
    authority_responses = {}  # rid -> response data
    decisions_by_id = {}  # decision_id -> decision data
    executed_trades_by_id = {}  # attempt_id -> trade data
    realized_source = "legacy_executed_trades_master"
    realized_source_path: Optional[str] = None
    canonical_realized_path: Optional[Path] = None

    # Load authority requests
    req_path = repo_root / "data" / "authority_request_journal_v1.jsonl"
    if req_path.exists():
        try:
            for data, line_num, src in read_jsonl(req_path):
                rid = data.get("rid")
                if rid:
                    authority_requests[rid] = {
                        **data, "_source": src, "_line": line_num}
        except Exception as e:
            warnings.append(f"Failed to read authority requests: {e}")
    else:
        warnings.append(f"Authority request journal not found: {req_path}")

    # Load authority responses
    resp_path = repo_root / "data" / "authority_response_journal_v1.jsonl"
    if resp_path.exists():
        try:
            for data, line_num, src in read_jsonl(resp_path):
                rid = data.get("rid")
                if rid:
                    authority_responses[rid] = {
                        **data, "_source": src, "_line": line_num}
        except Exception as e:
            warnings.append(f"Failed to read authority responses: {e}")
    else:
        warnings.append(f"Authority response journal not found: {resp_path}")

    # Load decision ledger
    ledger_path = repo_root / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl"
    if ledger_path.exists():
        try:
            for data, line_num, src in read_jsonl(ledger_path):
                decision_id = data.get("decision_id")
                if decision_id:
                    decisions_by_id[decision_id] = {
                        **data,
                        "_source": src,
                        "_line": line_num,
                    }
        except Exception as e:
            warnings.append(f"Failed to read decision ledger: {e}")
    else:
        warnings.append(f"Decision ledger not found: {ledger_path}")

    # Load realized source
    canonical_realized_rows: list[dict[str, Any]] = []
    if realized_outcome_dataset is not None:
        realized_source = "canonical_realized_outcome_dataset"
        realized_path = Path(realized_outcome_dataset)
        if not realized_path.is_absolute():
            realized_path = repo_root / realized_path
        canonical_realized_path = realized_path
        realized_source_path = str(realized_path)
        if realized_path.exists():
            try:
                for data, line_num, src in read_jsonl(realized_path):
                    validate_row("calibration_realized_trade_dataset_v1", data)
                    canonical_realized_rows.append(
                        {
                            **data,
                            "_source": src,
                            "_line": line_num,
                        }
                    )
            except Exception as e:
                blockers.append(
                    f"Failed to read canonical realized outcome dataset: {e}"
                )
        else:
            blockers.append(
                f"Canonical realized outcome dataset not found: {realized_path}"
            )
    else:
        trades_path = repo_root / "reports" / "executed_trades_master.csv"
        realized_source_path = str(trades_path)
        if trades_path.exists():
            try:
                for data, row_num, src in read_csv(trades_path):
                    attempt_id = data.get("attempt_id")
                    if attempt_id:
                        executed_trades_by_id[attempt_id] = {
                            **data,
                            "_source": src,
                            "_row": row_num,
                        }
            except Exception as e:
                warnings.append(f"Failed to read executed trades: {e}")
        else:
            warnings.append(f"Executed trades report not found: {trades_path}")

    # Build decision rows from ledger
    decision_count = 0
    for decision_id, decision_data in decisions_by_id.items():
        try:
            rid = decision_data.get("rid")
            req_data = authority_requests.get(rid, {}) if rid else {}
            resp_data = authority_responses.get(rid, {}) if rid else {}

            symbol = decision_data.get("symbol") or req_data.get("symbol")
            if not symbol:
                warnings.append(
                    f"Decision {decision_id}: missing symbol, skipping"
                )
                continue

            side = decision_data.get("side") or req_data.get("side")
            try:
                if side:
                    side = normalize_side(side)
            except ValueError:
                warnings.append(
                    f"Decision {decision_id}: invalid side {side!r}")
                continue

            # Build decision row
            decision_row = {
                "dataset_schema": "calibration_trade_decision_dataset_v1",
                "dataset_version": "1.0.0",
                "decision_id": decision_id,
                "rid": rid,
                "symbol": normalize_symbol(symbol),
                "strategy_id": decision_data.get("strategy_id"),
                "side": side,
                "proposed_action": req_data.get("proposed_action"),
                "decision_basis_ts_ms": safe_parse_int_ts(
                    decision_data.get("decision_basis_ts_ms")
                ),
                "request_ts_ms": safe_parse_int_ts(req_data.get("request_ts_ms")),
                "response_ts_ms": safe_parse_int_ts(resp_data.get("response_ts_ms")),
                "authority_mode": decision_data.get("authority_mode"),
                "action": resp_data.get("action"),
                "apply_result": resp_data.get("apply_result"),
                "reason_code": resp_data.get("reason_code"),
                "dataset_visibility": "causal_complete" if rid else "diagnostics_only",
                "observation_causal": True,
                "source_paths": source_paths_for(
                    decision_data.get("_source", ""),
                    req_data.get("_source", ""),
                    resp_data.get("_source", ""),
                ),
                "synthetic": False,
            }

            # Validate and add
            validate_row("calibration_trade_decision_dataset_v1", decision_row)
            decision_rows.append(decision_row)
            decision_count += 1

        except Exception as e:
            warnings.append(
                f"Failed to build decision row for {decision_id}: {e}")

    # Build realized trade rows from canonical realized dataset if provided
    if canonical_realized_rows:
        realized_rows.extend(
            {
                key: value
                for key, value in row.items()
                if not key.startswith("_")
            }
            for row in canonical_realized_rows
        )

    # Build realized trade rows from executed trades
    exact_roundtrip_count = 0
    for attempt_id, trade_data in executed_trades_by_id.items():
        try:
            symbol = trade_data.get("symbol")
            if not symbol:
                continue

            side = trade_data.get("side")
            try:
                if side:
                    side = normalize_side(side)
            except ValueError:
                continue

            # Try to find associated decision
            decision_id = trade_data.get("decision_id")
            decision_data = (
                decisions_by_id.get(decision_id) if decision_id else {}
            )

            # Build realized trade row
            entry_ts_ms = safe_parse_int_ts(trade_data.get("entry_ts_ms"))
            exit_ts_ms = safe_parse_int_ts(trade_data.get("exit_ts_ms"))
            exact_roundtrip = bool(entry_ts_ms and exit_ts_ms)

            realized_row = {
                "dataset_schema": "calibration_realized_trade_dataset_v1",
                "dataset_version": "1.0.0",
                "attempt_id": attempt_id,
                "decision_id": decision_id,
                "rid": trade_data.get("rid"),
                "lifecycle_id": trade_data.get("lifecycle_id"),
                "symbol": normalize_symbol(symbol),
                "strategy_id": trade_data.get("strategy_id"),
                "side": side,
                "intent_ts_ms": safe_parse_int_ts(trade_data.get("intent_ts_ms")),
                "entry_ts_ms": entry_ts_ms,
                "exit_ts_ms": exit_ts_ms,
                "entry_price": _parse_float(trade_data.get("entry_price")),
                "exit_price": _parse_float(trade_data.get("exit_price")),
                "qty": _parse_float(trade_data.get("qty")),
                "outcome": trade_data.get("outcome"),
                "gross_pnl": _parse_float(trade_data.get("gross_pnl")),
                "realized_pnl_net": _parse_float(
                    trade_data.get("realized_pnl_net")
                ),
                "fees": _parse_float(trade_data.get("fees")),
                "commission": _parse_float(trade_data.get("commission")),
                "mfe": _parse_float(trade_data.get("mfe")),
                "mae": _parse_float(trade_data.get("mae")),
                "bars_held": _parse_int(trade_data.get("bars_held")),
                "exact_roundtrip": exact_roundtrip,
                "terminal_status": trade_data.get("terminal_status"),
                "source_paths": source_paths_for(trade_data.get("_source", "")),
                "synthetic": False,
            }

            # Validate and add
            validate_row("calibration_realized_trade_dataset_v1", realized_row)
            realized_rows.append(realized_row)
            if exact_roundtrip:
                exact_roundtrip_count += 1

        except Exception as e:
            warnings.append(
                f"Failed to build realized trade row for {attempt_id}: {e}")

    source_summary: Optional[dict[str, Any]] = None
    if canonical_realized_path is not None:
        source_summary = _load_canonical_realized_source_summary(
            canonical_realized_path,
            realized_rows,
        )
        warnings.extend(source_summary.get("warnings", []))
    elif realized_source == "legacy_executed_trades_master":
        source_summary = _summarize_realized_source_rows(
            realized_rows,
            eligible_input_rows=len(realized_rows),
        )
        source_blockers = _dedupe_preserve_order(
            [
                *source_summary["promotion_blockers"],
                "LEGACY_REALIZED_SOURCE_NOT_PROMOTION_PROVEN",
            ]
        )
        source_summary["promotion_blockers"] = source_blockers
        source_summary["blockers"] = source_blockers
        source_summary["blocker_count"] = len(source_blockers)
        source_summary["promotion_grade"] = False
        source_summary["diagnostics_only"] = True
        source_summary["source_authority"] = "DERIVED_CONVENIENCE_REPORT_ONLY"

    # Validate all rows
    valid_dec, invalid_dec, dec_errors = validate_and_count(
        "calibration_trade_decision_dataset_v1", decision_rows
    )
    valid_real, invalid_real, real_errors = validate_and_count(
        "calibration_realized_trade_dataset_v1", realized_rows
    )

    if invalid_dec > 0:
        blockers.append(
            f"Invalid decision rows: {invalid_dec} out of {len(decision_rows)}"
        )
        warnings.extend(dec_errors[:5])  # Include first 5 errors

    if invalid_real > 0:
        blockers.append(
            f"Invalid realized trade rows: {invalid_real} out of {len(realized_rows)}"
        )
        warnings.extend(real_errors[:5])

    summary = summarize_objective_stack_quality(
        decision_rows,
        realized_rows,
        blockers,
        warnings,
        valid_dec=valid_dec,
        invalid_dec=invalid_dec,
        valid_real=valid_real,
        invalid_real=invalid_real,
        source_summary=source_summary,
    )
    blockers = list(summary["promotion_blockers"])
    warnings = list(summary["warnings"])
    summary.update(
        {
            "authority_requests_count": len(authority_requests),
            "authority_responses_count": len(authority_responses),
            "decision_ledger_count": len(decisions_by_id),
            "executed_trades_count": len(executed_trades_by_id),
            "canonical_realized_rows_count": len(canonical_realized_rows),
            "realized_source": realized_source,
            "realized_source_path": realized_source_path,
            "realized_source_authority": (
                source_summary.get("source_authority")
                if source_summary is not None
                else None
            ),
        }
    )

    # Write output if directory specified
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if decision_rows:
            write_jsonl(out_dir / "trade_decisions.jsonl", decision_rows)
        if realized_rows:
            write_jsonl(out_dir / "realized_trades.jsonl", realized_rows)

        # Write manifest
        manifest = {
            "generated_at_utc": datetime.utcnow().isoformat() + "Z",
            "builder": "objective_stack_builder",
            "output_schemas": [
                "calibration_trade_decision_dataset_v1",
                "calibration_realized_trade_dataset_v1",
            ],
            "data_quality": summary,
        }
        write_manifest_json(out_dir / "dataset_manifest.json", manifest)

        # Write quality report
        report = _generate_quality_report(
            "objective_stack", summary, blockers, warnings
        )
        (out_dir / "DATA_QUALITY_REPORT.md").write_text(report)

    return BuilderResult(
        decision_rows=decision_rows,
        realized_rows=realized_rows,
        data_quality_summary=summary,
        blockers=blockers,
        warnings=warnings,
    )


def _parse_float(value: Any) -> Optional[float]:
    """Parse value to float or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> Optional[int]:
    """Parse value to int or None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _generate_quality_report(
    builder_name: str,
    summary: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> str:
    """Generate markdown quality report."""
    report = f"""# Data Quality Report: {builder_name}

## Builder Execution Status

- Builder valid: {summary.get('builder_valid', False)}
- Schema valid: {summary.get('schema_valid', False)}
- Diagnostics only: {summary.get('diagnostics_only', False)}
- Promotion grade: {summary.get('promotion_grade', False)}

## Dataset Availability

- Rows emitted: {summary.get('rows_emitted', 0)}
- Rows valid: {summary.get('rows_valid', 0)}
- Rows invalid: {summary.get('rows_invalid', 0)}
- Eligible input rows: {summary.get('eligible_input_rows')}
- Matched rows: {summary.get('matched_rows')}
- Unmatched rows: {summary.get('unmatched_rows')}
- Match coverage pct: {summary.get('match_coverage_pct')}
- Has realized outcomes: {summary.get('has_realized_outcomes')}
- Exact roundtrips: {summary.get('exact_roundtrip_count')}
- Exact roundtrip coverage pct: {summary.get('exact_roundtrip_coverage_pct')}
- Min required rows: {summary.get('min_required_rows')}
- Min required coverage pct: {summary.get('min_required_coverage_pct')}
- Coverage grade: {summary.get('coverage_grade')}

## Dataset Counts

"""
    if "decision_rows_count" in summary:
        report += f"- Decision rows: {summary['decision_rows_count']} (valid: {summary.get('decision_rows_valid', 0)})\n"
    if "realized_rows_count" in summary:
        report += f"- Realized trade rows: {summary['realized_rows_count']} (valid: {summary.get('realized_rows_valid', 0)})\n"
    if "exact_roundtrip_count" in summary:
        report += f"- Exact roundtrips: {summary.get('exact_roundtrip_count', 0)}\n"

    report += "\n## Source Inventory\n\n"
    if "authority_requests_count" in summary:
        report += f"- Authority requests: {summary['authority_requests_count']}\n"
    if "authority_responses_count" in summary:
        report += f"- Authority responses: {summary['authority_responses_count']}\n"
    if "decision_ledger_count" in summary:
        report += f"- Decision ledger entries: {summary['decision_ledger_count']}\n"
    if "executed_trades_count" in summary:
        report += f"- Executed trades: {summary['executed_trades_count']}\n"
    if "canonical_realized_rows_count" in summary:
        report += f"- Canonical realized rows: {summary['canonical_realized_rows_count']}\n"
    if "realized_source" in summary:
        report += f"- Realized source: {summary['realized_source']}\n"
    if "realized_source_authority" in summary and summary["realized_source_authority"]:
        report += f"- Realized source authority: {summary['realized_source_authority']}\n"
    if summary.get("realized_source_path"):
        report += f"- Realized source path: {summary['realized_source_path']}\n"
    if "source_promotion_grade" in summary:
        report += f"- Source promotion grade: {summary['source_promotion_grade']}\n"
    if "source_coverage_grade" in summary:
        report += f"- Source coverage grade: {summary['source_coverage_grade']}\n"
    if "realized_source_coverage_pct" in summary:
        report += f"- Realized source coverage pct: {summary['realized_source_coverage_pct']}\n"

    if blockers:
        report += f"\n## Promotion Blockers ({len(blockers)})\n\n"
        for blocker in blockers:
            report += f"- {blocker}\n"

    if warnings:
        report += f"\n## Warnings ({len(warnings)})\n\n"
        for warning in warnings[:20]:  # Cap at 20 for readability
            report += f"- {warning}\n"
        if len(warnings) > 20:
            report += f"\n... and {len(warnings) - 20} more warnings\n"

    return report
