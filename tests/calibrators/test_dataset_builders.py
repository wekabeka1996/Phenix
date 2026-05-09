"""Tests for dataset builders (synthetic fixtures only)."""

import csv
import json
import pytest
from pathlib import Path
from calibrators.datasets.builders.common import (
    compute_basic_data_quality_summary,
    normalize_side,
    normalize_symbol,
    read_jsonl,
    read_csv,
    safe_parse_int_ts,
    source_paths_for,
    validate_and_count,
)
from calibrators.datasets.builders.low_vol_gate_builder import (
    build_low_vol_gate_dataset,
    summarize_low_vol_gate_quality,
)
from calibrators.datasets.builders.objective_stack_builder import (
    build_objective_stack_dataset,
    summarize_objective_stack_quality,
)
from calibrators.datasets.builders.walkforward_manifest_builder import (
    build_walkforward_manifest,
)
from calibrators.datasets.schema_examples import (
    example_low_vol_gate_row,
    example_realized_trade_row,
    example_trade_decision_row,
)
from calibrators.datasets.schema_registry import validate_row


EXECUTED_TRADES_FIELDS = [
    "attempt_id",
    "decision_id",
    "rid",
    "lifecycle_id",
    "symbol",
    "strategy_id",
    "side",
    "intent_ts_ms",
    "entry_ts_ms",
    "exit_ts_ms",
    "entry_price",
    "exit_price",
    "qty",
    "outcome",
    "gross_pnl",
    "realized_pnl_net",
    "fees",
    "commission",
    "mfe",
    "mae",
    "bars_held",
    "terminal_status",
    "required_gross_tp_bps_floor",
    "gross_tp_bps",
]

ORDER_ATTEMPTS_FIELDS = [
    "attempt_id",
    "decision_id",
    "target_net_fee_multiple",
    "min_rr",
]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _objective_request_row(index: int) -> dict[str, object]:
    return {
        "rid": f"req_{index}",
        "symbol": "BTCUSDT",
        "side": "buy",
        "proposed_action": "open_long",
        "request_ts_ms": 1714568400000 + index,
    }


def _objective_response_row(index: int) -> dict[str, object]:
    return {
        "rid": f"req_{index}",
        "response_ts_ms": 1714568401000 + index,
        "action": "accepted",
        "apply_result": "accepted",
        "reason_code": None,
    }


def _objective_decision_row(index: int) -> dict[str, object]:
    return {
        "decision_id": f"dec_{index}",
        "rid": f"req_{index}",
        "symbol": "BTCUSDT",
        "strategy_id": "objective_stack",
        "side": "long",
        "decision_basis_ts_ms": 1714568399000 + index,
        "authority_mode": "shadow",
    }


def _canonical_realized_row(index: int) -> dict[str, object]:
    return {
        "dataset_schema": "calibration_realized_trade_dataset_v1",
        "dataset_version": "1.0.0",
        "attempt_id": None,
        "decision_id": f"dec_{index}",
        "rid": f"req_{index}",
        "lifecycle_id": f"lc_{index}",
        "symbol": "BTCUSDT",
        "strategy_id": "objective_stack",
        "side": "long",
        "intent_ts_ms": 1714568400000 + index,
        "entry_ts_ms": 1714568402000 + index,
        "exit_ts_ms": 1714568600000 + index,
        "entry_price": 98850.0,
        "exit_price": 98950.0,
        "qty": 0.5,
        "outcome": "closed_win",
        "gross_pnl": 50.0,
        "realized_pnl_net": 45.0,
        "fees": 5.0,
        "commission": 5.0,
        "mfe": None,
        "mae": None,
        "bars_held": None,
        "exact_roundtrip": True,
        "terminal_status": "EXECUTED_AND_CLOSED",
        "source_paths": [
            "logs/shadow_telemetry/decision_ledger_v1.jsonl",
            "logs/order_log_v1.jsonl",
        ],
        "synthetic": False,
    }


class TestCommonUtilities:
    """Test common builder utilities."""

    def test_normalize_symbol(self):
        """normalize_symbol must uppercase and clean."""
        assert normalize_symbol("btcusdt") == "BTCUSDT"
        assert normalize_symbol("ETHUSDT") == "ETHUSDT"
        assert normalize_symbol("  SOLUSDT  ") == "SOLUSDT"

    def test_normalize_symbol_empty_raises(self):
        """normalize_symbol must fail on empty."""
        with pytest.raises(ValueError):
            normalize_symbol("")

    def test_normalize_side(self):
        """normalize_side must map to canonical form."""
        assert normalize_side("long") == "long"
        assert normalize_side("LONG") == "long"
        assert normalize_side("buy") == "long"
        assert normalize_side("BUY") == "long"
        assert normalize_side("short") == "short"
        assert normalize_side("SHORT") == "short"
        assert normalize_side("sell") == "short"

    def test_normalize_side_invalid_raises(self):
        """normalize_side must fail on unknown."""
        with pytest.raises(ValueError):
            normalize_side("up")

    def test_safe_parse_int_ts(self):
        """safe_parse_int_ts must handle various types."""
        assert safe_parse_int_ts(1714568400000) == 1714568400000
        assert safe_parse_int_ts(1714568400000.5) == 1714568400000
        assert safe_parse_int_ts("1714568400000") == 1714568400000
        assert safe_parse_int_ts(None) is None

    def test_safe_parse_int_ts_invalid_raises(self):
        """safe_parse_int_ts must fail on unparseable."""
        with pytest.raises(ValueError):
            safe_parse_int_ts("not_a_number")

    def test_source_paths_for(self):
        """source_paths_for must deduplicate and sort."""
        paths = source_paths_for("file1.jsonl", "file2.csv", "file1.jsonl")
        assert paths == ["file1.jsonl", "file2.csv"]
        assert len(paths) == 2

    def test_validate_and_count(self):
        """validate_and_count must count valid and invalid rows."""
        rows = [
            {
                "dataset_schema": "calibration_market_bar_dataset_v1",
                "dataset_version": "1.0.0",
                "source_surface": "test",
                "source_file": "test.csv",
                "session_date": None,
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "ts_ms": 1000000000,
                "bar_close_ts_ms": None,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": None,
                "trade_count": None,
                "data_quality": "good",
                "synthetic": False,
            },
            # Invalid row (missing required fields)
            {
                "dataset_schema": "calibration_market_bar_dataset_v1",
                "dataset_version": "1.0.0",
            },
        ]
        valid, invalid, errors = validate_and_count(
            "calibration_market_bar_dataset_v1", rows
        )
        assert valid == 1
        assert invalid == 1
        assert len(errors) > 0


class TestWalkforwardManifestBuilder:
    """Test walk-forward manifest builder."""

    def test_build_walkforward_manifest_valid(self):
        """build_walkforward_manifest must create valid manifest."""
        result = build_walkforward_manifest(
            source_dataset="calibration_market_bar_dataset_v1",
            dataset_id="calibration_market_bar_dataset_v1",
            train_start="2026-01-01",
            train_end="2026-03-01",
            validation_start="2026-03-02",
            validation_end="2026-03-31",
            forward_start="2026-04-01",
            forward_end="2026-04-30",
        )

        assert result.manifest_row["dataset_schema"] == "calibration_walkforward_manifest_v1"
        assert result.manifest_row["train_start"] == "2026-01-01"
        assert result.manifest_row["forward_end"] == "2026-04-30"
        assert result.manifest_row["synthetic_allowed"] is False

    def test_build_walkforward_manifest_missing_dates_raises(self):
        """build_walkforward_manifest must fail if date windows missing."""
        with pytest.raises(ValueError, match="Must provide all of"):
            build_walkforward_manifest(
                source_dataset="test",
                dataset_id="test",
                train_start="2026-01-01",
                # Missing all other dates
            )

    def test_build_walkforward_manifest_with_excluded_sessions(self):
        """build_walkforward_manifest must accept excluded sessions."""
        result = build_walkforward_manifest(
            source_dataset="test",
            dataset_id="test",
            train_start="2026-01-01",
            train_end="2026-03-01",
            validation_start="2026-03-02",
            validation_end="2026-03-31",
            forward_start="2026-04-01",
            forward_end="2026-04-30",
            excluded_sessions=["2026-02-15"],
        )

        assert result.manifest_row["excluded_sessions"] == ["2026-02-15"]

    def test_build_walkforward_manifest_validates_schema(self):
        """build_walkforward_manifest must validate against schema."""
        result = build_walkforward_manifest(
            source_dataset="test",
            dataset_id="test",
            train_start="2026-01-01",
            train_end="2026-03-01",
            validation_start="2026-03-02",
            validation_end="2026-03-31",
            forward_start="2026-04-01",
            forward_end="2026-04-30",
        )

        # Verify it validates
        validate_row(
            "calibration_walkforward_manifest_v1",
            result.manifest_row
        )


class TestQualitySemantics:
    """Test hardened quality semantics for builder summaries."""

    def test_empty_generic_output_never_promotion_grade(self):
        """Empty output may be structurally valid but not promotion-grade."""
        summary = compute_basic_data_quality_summary([], [], [])

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["has_rows"] is False
        assert summary["diagnostics_only"] is True
        assert summary["promotion_grade"] is False
        assert "EMPTY_DATASET" in summary["promotion_blockers"]

    def test_objective_zero_realized_is_diagnostics_only(self):
        """Decision-only objective output must not be promotion-grade."""
        decision_row = example_trade_decision_row().model_dump()

        summary = summarize_objective_stack_quality(
            [decision_row],
            [],
            [],
            [],
            valid_dec=1,
            invalid_dec=0,
            valid_real=0,
            invalid_real=0,
        )

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["promotion_grade"] is False
        assert summary["diagnostics_only"] is True
        assert summary["has_rows"] is True
        assert summary["has_realized_outcomes"] is False
        assert summary["exact_roundtrip_count"] == 0
        assert summary["exact_roundtrip_coverage_pct"] == pytest.approx(0.0)
        assert "NO_REALIZED_TRADE_ROWS" in summary["promotion_blockers"]
        assert "NO_EXACT_ROUNDTRIPS" in summary["promotion_blockers"]

    def test_objective_with_sufficient_exact_roundtrips_can_be_promotion_grade(self):
        """Objective output becomes promotion-grade only when exact rows also meet coverage thresholds."""
        decision_row = example_trade_decision_row().model_dump()
        realized_row = example_realized_trade_row().model_dump()

        summary = summarize_objective_stack_quality(
            [decision_row for _ in range(30)],
            [realized_row for _ in range(30)],
            [],
            [],
            valid_dec=30,
            invalid_dec=0,
            valid_real=30,
            invalid_real=0,
        )

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["diagnostics_only"] is False
        assert summary["promotion_grade"] is True
        assert summary["has_realized_outcomes"] is True
        assert summary["exact_roundtrip_count"] == 30
        assert summary["coverage_grade"] == "PROMOTION_ELIGIBLE"
        assert summary["promotion_blockers"] == []

    def test_low_vol_zero_rows_is_diagnostics_only(self):
        """Empty low-vol output is valid builder execution but not promotion-grade."""
        summary = summarize_low_vol_gate_quality(
            [],
            [],
            [],
            valid_rows=0,
            invalid_rows=0,
        )

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["promotion_grade"] is False
        assert summary["diagnostics_only"] is True
        assert "EMPTY_LOW_VOL_GATE_DATASET" in summary["promotion_blockers"]

    def test_low_vol_valid_outcome_can_be_promotion_grade(self):
        """Low-vol output needs rows, regime, and outcome/counterfactual."""
        gate_row = example_low_vol_gate_row().model_dump()

        summary = summarize_low_vol_gate_quality(
            [gate_row],
            [],
            [],
            valid_rows=1,
            invalid_rows=0,
        )

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["diagnostics_only"] is False
        assert summary["promotion_grade"] is True
        assert summary["promotion_blockers"] == []

    def test_sparse_dataset_coverage_is_not_promotion_grade(self):
        """Sparse matched coverage must remain diagnostics-only even with exact rows."""
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]

        summary = compute_basic_data_quality_summary(
            rows,
            [],
            [],
            has_realized_outcomes=True,
            exact_roundtrip_count=3,
            eligible_input_rows=47,
            matched_rows=3,
            min_required_rows=30,
            min_required_coverage_pct=50.0,
            coverage_row_blocker="INSUFFICIENT_REALIZED_ROWS",
            coverage_pct_blocker="INSUFFICIENT_REALIZED_COVERAGE",
        )

        assert summary["builder_valid"] is True
        assert summary["schema_valid"] is True
        assert summary["coverage_grade"] == "SPARSE_DIAGNOSTIC"
        assert summary["match_coverage_pct"] == pytest.approx(6.383)
        assert summary["exact_roundtrip_coverage_pct"] == pytest.approx(6.383)
        assert summary["diagnostics_only"] is True
        assert summary["promotion_grade"] is False
        assert summary["coverage_blockers"] == [
            "INSUFFICIENT_REALIZED_ROWS",
            "INSUFFICIENT_REALIZED_COVERAGE",
        ]

    def test_sufficient_dataset_coverage_can_be_promotion_eligible(self):
        """Coverage gates allow promotion only when row count and coverage thresholds both pass."""
        rows = [{"id": idx} for idx in range(30)]

        summary = compute_basic_data_quality_summary(
            rows,
            [],
            [],
            has_realized_outcomes=True,
            exact_roundtrip_count=30,
            eligible_input_rows=47,
            matched_rows=30,
            min_required_rows=30,
            min_required_coverage_pct=50.0,
            coverage_row_blocker="INSUFFICIENT_REALIZED_ROWS",
            coverage_pct_blocker="INSUFFICIENT_REALIZED_COVERAGE",
        )

        assert summary["coverage_grade"] == "PROMOTION_ELIGIBLE"
        assert summary["coverage_blockers"] == []
        assert summary["diagnostics_only"] is False
        assert summary["promotion_grade"] is True


class TestBuilderIntegrationSemantics:
    """Integration-level semantics tests for actual builders."""

    def test_objective_builder_zero_realized_is_not_promotion_grade(self, tmp_path: Path):
        """Objective builder must mark decision-only output as diagnostics-only."""
        _write_jsonl(
            tmp_path / "data" / "authority_request_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "proposed_action": "open_long",
                "request_ts_ms": 1714568400000,
            }],
        )
        _write_jsonl(
            tmp_path / "data" / "authority_response_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "response_ts_ms": 1714568401000,
                "action": "accepted",
                "apply_result": "accepted",
                "reason_code": None,
            }],
        )
        _write_jsonl(
            tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
            [{
                "decision_id": "dec_1",
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "strategy_id": "objective_stack",
                "side": "long",
                "decision_basis_ts_ms": 1714568399000,
                "authority_mode": "shadow",
            }],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [],
        )

        result = build_objective_stack_dataset(repo_root=tmp_path)

        assert result.data_quality_summary["builder_valid"] is True
        assert result.data_quality_summary["schema_valid"] is True
        assert result.data_quality_summary["has_rows"] is True
        assert result.data_quality_summary["has_realized_outcomes"] is False
        assert result.data_quality_summary["diagnostics_only"] is True
        assert result.data_quality_summary["promotion_grade"] is False
        assert "NO_REALIZED_TRADE_ROWS" in result.blockers
        assert "NO_EXACT_ROUNDTRIPS" in result.blockers

    def test_objective_builder_legacy_realized_source_stays_diagnostics_only(self, tmp_path: Path):
        """Legacy executed_trades_master remains diagnostics-only even with an exact row."""
        _write_jsonl(
            tmp_path / "data" / "authority_request_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "proposed_action": "open_long",
                "request_ts_ms": 1714568400000,
            }],
        )
        _write_jsonl(
            tmp_path / "data" / "authority_response_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "response_ts_ms": 1714568401000,
                "action": "accepted",
                "apply_result": "accepted",
                "reason_code": None,
            }],
        )
        _write_jsonl(
            tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
            [{
                "decision_id": "dec_1",
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "strategy_id": "objective_stack",
                "side": "long",
                "decision_basis_ts_ms": 1714568399000,
                "authority_mode": "shadow",
            }],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [{
                "attempt_id": "att_1",
                "decision_id": "dec_1",
                "rid": "req_1",
                "lifecycle_id": "lc_1",
                "symbol": "BTCUSDT",
                "strategy_id": "objective_stack",
                "side": "buy",
                "intent_ts_ms": 1714568400000,
                "entry_ts_ms": 1714568402000,
                "exit_ts_ms": 1714568600000,
                "entry_price": 98850.0,
                "exit_price": 98950.0,
                "qty": 0.5,
                "outcome": "closed_win",
                "gross_pnl": 50.0,
                "realized_pnl_net": 45.0,
                "fees": 5.0,
                "commission": 0.0,
                "mfe": 100.0,
                "mae": -20.0,
                "bars_held": 20,
                "terminal_status": "closed",
                "required_gross_tp_bps_floor": "",
                "gross_tp_bps": "",
            }],
        )

        result = build_objective_stack_dataset(repo_root=tmp_path)

        assert result.data_quality_summary["builder_valid"] is True
        assert result.data_quality_summary["schema_valid"] is True
        assert result.data_quality_summary["has_realized_outcomes"] is True
        assert result.data_quality_summary["diagnostics_only"] is True
        assert result.data_quality_summary["promotion_grade"] is False
        assert result.data_quality_summary["exact_roundtrip_count"] == 1
        assert result.data_quality_summary["realized_source"] == "legacy_executed_trades_master"
        assert result.data_quality_summary["source_promotion_grade"] is False
        assert result.data_quality_summary["source_coverage_grade"] == "SPARSE_DIAGNOSTIC"
        assert "LEGACY_REALIZED_SOURCE_NOT_PROMOTION_PROVEN" in result.data_quality_summary[
            "source_promotion_blockers"]
        assert "SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE" in result.blockers

    def test_objective_builder_canonical_source_without_manifest_warns_and_stays_sparse(self, tmp_path: Path):
        """Canonical source without manifest falls back to row counts and emits a manifest warning."""
        _write_jsonl(
            tmp_path / "data" / "authority_request_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "proposed_action": "open_long",
                "request_ts_ms": 1714568400000,
            }],
        )
        _write_jsonl(
            tmp_path / "data" / "authority_response_journal_v1.jsonl",
            [{
                "rid": "req_1",
                "response_ts_ms": 1714568401000,
                "action": "accepted",
                "apply_result": "accepted",
                "reason_code": None,
            }],
        )
        _write_jsonl(
            tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
            [{
                "decision_id": "dec_1",
                "rid": "req_1",
                "symbol": "BTCUSDT",
                "strategy_id": "objective_stack",
                "side": "long",
                "decision_basis_ts_ms": 1714568399000,
                "authority_mode": "shadow",
            }],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [],
        )
        _write_jsonl(
            tmp_path / "artifacts" / "realized" / "realized_trades.jsonl",
            [{
                "dataset_schema": "calibration_realized_trade_dataset_v1",
                "dataset_version": "1.0.0",
                "attempt_id": None,
                "decision_id": "dec_1",
                "rid": "req_1",
                "lifecycle_id": "lc_1",
                "symbol": "BTCUSDT",
                "strategy_id": "objective_stack",
                "side": "long",
                "intent_ts_ms": 1714568400000,
                "entry_ts_ms": 1714568402000,
                "exit_ts_ms": 1714568600000,
                "entry_price": 98850.0,
                "exit_price": 98950.0,
                "qty": 0.5,
                "outcome": "closed_win",
                "gross_pnl": 50.0,
                "realized_pnl_net": 45.0,
                "fees": 5.0,
                "commission": 5.0,
                "mfe": None,
                "mae": None,
                "bars_held": None,
                "exact_roundtrip": True,
                "terminal_status": "EXECUTED_AND_CLOSED",
                "source_paths": [
                    "logs/shadow_telemetry/decision_ledger_v1.jsonl",
                    "logs/order_log_v1.jsonl",
                ],
                "synthetic": False,
            }],
        )

        result = build_objective_stack_dataset(
            repo_root=tmp_path,
            realized_outcome_dataset=tmp_path / "artifacts" /
            "realized" / "realized_trades.jsonl",
        )

        assert result.data_quality_summary["realized_source"] == "canonical_realized_outcome_dataset"
        assert result.data_quality_summary["canonical_realized_rows_count"] == 1
        assert result.data_quality_summary["has_realized_outcomes"] is True
        assert result.data_quality_summary["source_promotion_grade"] is False
        assert result.data_quality_summary["source_coverage_grade"] == "SPARSE_DIAGNOSTIC"
        assert result.data_quality_summary["promotion_grade"] is False
        assert "MISSING_REALIZED_SOURCE_MANIFEST" in result.warnings
        assert result.realized_rows[0]["decision_id"] == "dec_1"

    def test_objective_builder_propagates_diagnostics_only_canonical_source(self, tmp_path: Path):
        """Objective promotion stays false when canonical realized source coverage is diagnostics-only."""
        count = 47
        _write_jsonl(
            tmp_path / "data" / "authority_request_journal_v1.jsonl",
            [_objective_request_row(index) for index in range(count)],
        )
        _write_jsonl(
            tmp_path / "data" / "authority_response_journal_v1.jsonl",
            [_objective_response_row(index) for index in range(count)],
        )
        _write_jsonl(
            tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
            [_objective_decision_row(index) for index in range(count)],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [],
        )
        _write_jsonl(
            tmp_path / "artifacts" / "realized" / "realized_trades.jsonl",
            [_canonical_realized_row(index) for index in range(3)],
        )
        manifest = {
            "eligible_decision_rows": 47,
            "emitted_realized_rows": 3,
            "exact_roundtrip_count": 3,
            "promotion_grade": False,
            "diagnostics_only": True,
            "coverage_grade": "SPARSE_DIAGNOSTIC",
            "promotion_blockers": [
                "INSUFFICIENT_REALIZED_ROWS",
                "INSUFFICIENT_REALIZED_COVERAGE",
            ],
        }
        (tmp_path / "artifacts" / "realized" / "dataset_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        result = build_objective_stack_dataset(
            repo_root=tmp_path,
            realized_outcome_dataset=tmp_path / "artifacts" /
            "realized" / "realized_trades.jsonl",
        )

        assert result.data_quality_summary["source_promotion_grade"] is False
        assert result.data_quality_summary["source_coverage_grade"] == "SPARSE_DIAGNOSTIC"
        assert result.data_quality_summary["realized_source_coverage_pct"] == pytest.approx(
            6.383)
        assert result.data_quality_summary["promotion_grade"] is False
        assert result.data_quality_summary["diagnostics_only"] is True
        assert "SOURCE_REALIZED_DATASET_NOT_PROMOTION_GRADE" in result.blockers
        assert "INSUFFICIENT_REALIZED_ROWS" in result.data_quality_summary[
            "source_promotion_blockers"]
        assert "INSUFFICIENT_REALIZED_COVERAGE" in result.data_quality_summary[
            "source_promotion_blockers"]

    def test_objective_builder_can_be_promotion_grade_with_promotion_source(self, tmp_path: Path):
        """Objective can become promotion-grade only when the canonical realized source is promotion-eligible."""
        count = 30
        _write_jsonl(
            tmp_path / "data" / "authority_request_journal_v1.jsonl",
            [_objective_request_row(index) for index in range(count)],
        )
        _write_jsonl(
            tmp_path / "data" / "authority_response_journal_v1.jsonl",
            [_objective_response_row(index) for index in range(count)],
        )
        _write_jsonl(
            tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
            [_objective_decision_row(index) for index in range(count)],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [],
        )
        realized_rows = [_canonical_realized_row(
            index) for index in range(count)]
        _write_jsonl(
            tmp_path / "artifacts" / "realized" / "realized_trades.jsonl",
            realized_rows,
        )
        manifest = {
            "data_quality": {
                "eligible_input_rows": 30,
                "matched_rows": 30,
                "exact_roundtrip_count": 30,
                "match_coverage_pct": 100.0,
                "coverage_grade": "PROMOTION_ELIGIBLE",
                "promotion_grade": True,
                "diagnostics_only": False,
                "promotion_blockers": [],
            }
        }
        (tmp_path / "artifacts" / "realized" / "dataset_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        result = build_objective_stack_dataset(
            repo_root=tmp_path,
            realized_outcome_dataset=tmp_path / "artifacts" /
            "realized" / "realized_trades.jsonl",
        )

        assert result.data_quality_summary["coverage_grade"] == "PROMOTION_ELIGIBLE"
        assert result.data_quality_summary["source_promotion_grade"] is True
        assert result.data_quality_summary["source_coverage_grade"] == "PROMOTION_ELIGIBLE"
        assert result.data_quality_summary["promotion_grade"] is True
        assert result.data_quality_summary["diagnostics_only"] is False

    def test_low_vol_builder_zero_rows_is_not_promotion_grade(self, tmp_path: Path):
        """Low-vol builder must keep empty output diagnostics-only."""
        _write_jsonl(tmp_path / "logs" /
                     "regime_confidence_audit_v1.jsonl", [])
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [],
        )
        _write_csv(
            tmp_path / "reports" / "order_attempts_master.csv",
            ORDER_ATTEMPTS_FIELDS,
            [],
        )

        result = build_low_vol_gate_dataset(repo_root=tmp_path)

        assert result.data_quality_summary["builder_valid"] is True
        assert result.data_quality_summary["schema_valid"] is True
        assert result.data_quality_summary["promotion_grade"] is False
        assert result.data_quality_summary["diagnostics_only"] is True
        assert "EMPTY_LOW_VOL_GATE_DATASET" in result.blockers

    def test_low_vol_builder_valid_row_can_be_promotion_grade(self, tmp_path: Path):
        """Low-vol builder may become promotion-grade only with usable gate evidence."""
        _write_jsonl(
            tmp_path / "logs" / "regime_confidence_audit_v1.jsonl",
            [{
                "symbol": "ETHUSDT",
                "regime": "low_vol",
                "regime_confidence": 0.75,
                "direction_confidence": 0.65,
            }],
        )
        _write_csv(
            tmp_path / "reports" / "executed_trades_master.csv",
            EXECUTED_TRADES_FIELDS,
            [{
                "attempt_id": "att_lv_1",
                "decision_id": "dec_lv_1",
                "rid": "req_lv_1",
                "lifecycle_id": "lc_lv_1",
                "symbol": "ETHUSDT",
                "strategy_id": "low_vol_cost_floor",
                "side": "buy",
                "intent_ts_ms": 1714568400000,
                "entry_ts_ms": 1714568402000,
                "exit_ts_ms": 1714568600000,
                "entry_price": 3000.0,
                "exit_price": 3010.0,
                "qty": 1.0,
                "outcome": "gate_allowed",
                "gross_pnl": 10.0,
                "realized_pnl_net": 8.0,
                "fees": 2.0,
                "commission": 2.0,
                "mfe": 15.0,
                "mae": -5.0,
                "bars_held": 5,
                "terminal_status": "closed",
                "required_gross_tp_bps_floor": 25.0,
                "gross_tp_bps": 30.0,
            }],
        )
        _write_csv(
            tmp_path / "reports" / "order_attempts_master.csv",
            ORDER_ATTEMPTS_FIELDS,
            [{
                "attempt_id": "att_lv_1",
                "decision_id": "dec_lv_1",
                "target_net_fee_multiple": 2.5,
                "min_rr": 1.5,
            }],
        )

        result = build_low_vol_gate_dataset(repo_root=tmp_path)

        assert result.data_quality_summary["builder_valid"] is True
        assert result.data_quality_summary["schema_valid"] is True
        assert result.data_quality_summary["diagnostics_only"] is False
        assert result.data_quality_summary["promotion_grade"] is True
        assert result.data_quality_summary["has_realized_outcomes"] is True
        assert result.blockers == []


class TestBoundaryGuard:
    """Test that boundary guard (apps/reference does not import calibrators) still passes."""

    def test_apps_reference_does_not_import_calibrators_builders(self):
        """apps/reference must not import calibrators.datasets.builders."""
        import ast

        root = Path(__file__).resolve().parents[2]  # repo root
        runtime_root = root / "apps" / "reference"

        violations = []
        for path in sorted(runtime_root.rglob("*.py")):
            tree = ast.parse(
                path.read_text(encoding="utf-8-sig"), filename=str(path)
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "calibrators" in alias.name:
                            violations.append(
                                f"{path.as_posix()}: import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "calibrators" in module:
                        violations.append(
                            f"{path.as_posix()}: from {module} import ..."
                        )

        assert not violations, (
            "apps/reference must not import calibrators:\n"
            + "\n".join(violations)
        )
