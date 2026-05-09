"""Low-vol gate joined dataset builder.

Joins low-volatility gate decisions with trade outcomes to produce datasets
for gate/cost-floor calibration.

Consumes:
- order log
- trade lifecycle
- regime confidence audit
- executed trades reports
- order attempts reports

Produces:
- calibration_low_vol_gate_dataset_v1 (JSONL)
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from calibrators.datasets.builders.common import (
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


@dataclass
class BuilderResult:
    """Result of dataset builder run."""

    gate_rows: list[dict[str, Any]]
    data_quality_summary: dict[str, Any]
    blockers: list[str]
    warnings: list[str]


def summarize_low_vol_gate_quality(
    gate_rows: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    *,
    valid_rows: int,
    invalid_rows: int,
) -> dict[str, Any]:
    """Summarize low-vol builder quality without overstating readiness."""
    promotion_blockers = list(blockers)
    has_regime = bool(gate_rows) and all(row.get("regime")
                                         for row in gate_rows)
    has_outcome_or_counterfactual = any(
        row.get("outcome") or row.get("counterfactual_source")
        for row in gate_rows
    )
    exact_roundtrip_count = sum(
        1 for row in gate_rows if row.get("exact_roundtrip")
    )

    if not gate_rows:
        promotion_blockers.append("EMPTY_LOW_VOL_GATE_DATASET")
    if gate_rows and not has_regime:
        promotion_blockers.append("MISSING_LOW_VOL_REGIME")
    if gate_rows and not has_outcome_or_counterfactual:
        promotion_blockers.append("MISSING_LOW_VOL_OUTCOMES")

    diagnostics_only = (
        not gate_rows
        or not has_regime
        or not has_outcome_or_counterfactual
    )
    summary = compute_basic_data_quality_summary(
        gate_rows,
        promotion_blockers,
        warnings,
        rows_valid=valid_rows,
        rows_invalid=invalid_rows,
        has_realized_outcomes=has_outcome_or_counterfactual,
        exact_roundtrip_count=exact_roundtrip_count,
        diagnostics_only=diagnostics_only,
    )
    summary.update(
        {
            "gate_rows_count": len(gate_rows),
            "gate_rows_valid": valid_rows,
            "exact_roundtrip_count": exact_roundtrip_count,
        }
    )
    return summary


def build_low_vol_gate_dataset(
    repo_root: Optional[str | Path] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    out_dir: Optional[str | Path] = None,
) -> BuilderResult:
    """Build low_vol_cost_floor joined datasets.

    Args:
        repo_root: Repository root path. Auto-detected if None.
        date_start: ISO date start filter (YYYY-MM-DD), optional.
        date_end: ISO date end filter (YYYY-MM-DD), optional.
        out_dir: Output directory. If None, returns in-memory result only.

    Returns:
        BuilderResult with gate rows and quality report.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    blockers: list[str] = []
    warnings: list[str] = []
    gate_rows: list[dict[str, Any]] = []

    # Load source data
    regime_confidence = {}  # symbol -> list of regime data
    executed_trades_by_id = {}  # attempt_id -> trade data
    order_attempts = {}  # attempt_id -> order attempt data

    # Load regime confidence audit
    regime_path = repo_root / "logs" / "regime_confidence_audit_v1.jsonl"
    if regime_path.exists():
        try:
            for data, line_num, src in read_jsonl(regime_path):
                symbol = data.get("symbol")
                if symbol:
                    if symbol not in regime_confidence:
                        regime_confidence[symbol] = []
                    regime_confidence[symbol].append(
                        {**data, "_source": src, "_line": line_num}
                    )
        except Exception as e:
            warnings.append(f"Failed to read regime audit: {e}")
    else:
        warnings.append(f"Regime confidence audit not found: {regime_path}")

    # Load executed trades
    trades_path = repo_root / "reports" / "executed_trades_master.csv"
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

    # Load order attempts
    attempts_path = repo_root / "reports" / "order_attempts_master.csv"
    if attempts_path.exists():
        try:
            for data, row_num, src in read_csv(attempts_path):
                attempt_id = data.get("attempt_id")
                if attempt_id:
                    order_attempts[attempt_id] = {
                        **data,
                        "_source": src,
                        "_row": row_num,
                    }
        except Exception as e:
            warnings.append(f"Failed to read order attempts: {e}")
    else:
        warnings.append(f"Order attempts report not found: {attempts_path}")

    # Build gate rows from executed trades filtered for low-vol
    exact_roundtrip_count = 0
    for attempt_id, trade_data in executed_trades_by_id.items():
        try:
            symbol = trade_data.get("symbol")
            if not symbol:
                continue

            symbol = normalize_symbol(symbol)

            # Get regime data for this symbol (use most recent)
            regime_data = {}
            if symbol in regime_confidence:
                regime_data = regime_confidence[symbol][-1]  # Most recent

            # Get order attempt data
            attempt_data = order_attempts.get(attempt_id, {})

            # Check if this is a low-vol regime trade
            regime = regime_data.get("regime")
            if regime and "low" not in regime.lower():
                continue  # Skip non-low-vol trades

            side = trade_data.get("side")
            try:
                if side:
                    side = normalize_side(side)
            except ValueError:
                continue

            # Build gate row
            entry_ts_ms = safe_parse_int_ts(trade_data.get("entry_ts_ms"))
            exit_ts_ms = safe_parse_int_ts(trade_data.get("exit_ts_ms"))
            exact_roundtrip = bool(entry_ts_ms and exit_ts_ms)

            gate_row = {
                "dataset_schema": "calibration_low_vol_gate_dataset_v1",
                "dataset_version": "1.0.0",
                "attempt_id": attempt_id,
                "decision_id": attempt_data.get("decision_id"),
                "symbol": symbol,
                "strategy_id": trade_data.get("strategy_id"),
                "side": side,
                "regime": regime_data.get("regime"),
                "regime_confidence": _parse_float(
                    regime_data.get("regime_confidence")
                ),
                "direction_confidence": _parse_float(
                    regime_data.get("direction_confidence")
                ),
                "target_net_fee_multiple": _parse_float(
                    attempt_data.get("target_net_fee_multiple")
                ),
                "required_gross_tp_bps_floor": _parse_float(
                    trade_data.get("required_gross_tp_bps_floor")
                ),
                "min_rr": _parse_float(attempt_data.get("min_rr")),
                "gross_tp_bps": _parse_float(trade_data.get("gross_tp_bps")),
                "realized_pnl_net": _parse_float(
                    trade_data.get("realized_pnl_net")
                ),
                "commission": _parse_float(trade_data.get("commission")),
                "outcome": trade_data.get("outcome"),
                "counterfactual_source": None,
                "exact_roundtrip": exact_roundtrip,
                "source_paths": source_paths_for(
                    trade_data.get("_source", ""),
                    attempt_data.get("_source", ""),
                    regime_data.get("_source", ""),
                ),
                "synthetic": False,
            }

            # Validate and add
            from calibrators.datasets.schema_registry import validate_row

            validate_row("calibration_low_vol_gate_dataset_v1", gate_row)
            gate_rows.append(gate_row)
            if exact_roundtrip:
                exact_roundtrip_count += 1

        except Exception as e:
            warnings.append(f"Failed to build gate row for {attempt_id}: {e}")

    # Validate all rows
    valid_rows, invalid_rows, val_errors = validate_and_count(
        "calibration_low_vol_gate_dataset_v1", gate_rows
    )

    if invalid_rows > 0:
        blockers.append("INVALID_LOW_VOL_GATE_ROWS")
        warnings.extend(val_errors[:5])

    summary = summarize_low_vol_gate_quality(
        gate_rows,
        blockers,
        warnings,
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
    )
    blockers = list(summary["promotion_blockers"])
    warnings = list(summary["warnings"])
    summary.update(
        {
            "regime_symbols_count": len(regime_confidence),
            "executed_trades_count": len(executed_trades_by_id),
            "order_attempts_count": len(order_attempts),
        }
    )

    # Write output if directory specified
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if gate_rows:
            write_jsonl(out_dir / "low_vol_gate_rows.jsonl", gate_rows)

        # Write manifest
        manifest = {
            "generated_at_utc": datetime.utcnow().isoformat() + "Z",
            "builder": "low_vol_gate_builder",
            "output_schemas": ["calibration_low_vol_gate_dataset_v1"],
            "data_quality": summary,
        }
        write_manifest_json(out_dir / "dataset_manifest.json", manifest)

        # Write quality report
        report = _generate_quality_report(
            "low_vol_gate", summary, blockers, warnings
        )
        (out_dir / "DATA_QUALITY_REPORT.md").write_text(report)

    return BuilderResult(
        gate_rows=gate_rows,
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

- Gate rows: {summary.get('gate_rows_count', 0)} (valid: {summary.get('gate_rows_valid', 0)})
- Exact roundtrips: {summary.get('exact_roundtrip_count', 0)}

## Source Inventory

- Regime confidence symbols: {summary.get('regime_symbols_count', 0)}
- Executed trades: {summary.get('executed_trades_count', 0)}
- Order attempts: {summary.get('order_attempts_count', 0)}

"""

    if blockers:
        report += f"## Promotion Blockers ({len(blockers)})\n\n"
        for blocker in blockers:
            report += f"- {blocker}\n"

    if warnings:
        report += f"\n## Warnings ({len(warnings)})\n\n"
        for warning in warnings[:20]:
            report += f"- {warning}\n"
        if len(warnings) > 20:
            report += f"\n... and {len(warnings) - 20} more warnings\n"

    return report
