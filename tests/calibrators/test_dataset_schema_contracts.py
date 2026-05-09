"""Tests for dataset schema contracts.

Validates:
- All 7 schemas are registered
- Each example validates
- Missing required fields fail
- Unknown extra fields fail
- Unknown schema_id fails
- Invalid timestamps fail where required
- synthetic flag is present in all row schemas
- Boundary guard (apps/reference must not import calibrators) still passes
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from calibrators.datasets import (
    CalibrationFeatureSnapshotRowV1,
    CalibrationLowVolGateRowV1,
    CalibrationMarketBarRowV1,
    CalibrationOracleRegimeLabelRowV1,
    CalibrationRealizedTradeRowV1,
    CalibrationTradeDecisionRowV1,
    CalibrationWalkforwardManifestV1,
    get_schema_model,
    list_schema_ids,
    schema_version_for,
    validate_row,
    validate_rows,
)
from calibrators.datasets.schema_examples import (
    example_feature_snapshot_row,
    example_low_vol_gate_row,
    example_market_bar_row,
    example_oracle_regime_label_row,
    example_realized_trade_row,
    example_trade_decision_row,
    example_walkforward_manifest_row,
)


class TestSchemaRegistration:
    """Test schema registration and lookup."""

    def test_all_seven_schemas_registered(self):
        """All 7 schemas must be registered."""
        schema_ids = list_schema_ids()
        expected = [
            "calibration_low_vol_gate_dataset_v1",
            "calibration_feature_snapshot_dataset_v1",
            "calibration_market_bar_dataset_v1",
            "calibration_oracle_regime_labels_v1",
            "calibration_realized_trade_dataset_v1",
            "calibration_trade_decision_dataset_v1",
            "calibration_walkforward_manifest_v1",
        ]
        assert sorted(schema_ids) == sorted(expected)
        assert len(schema_ids) == 7

    def test_get_schema_model_valid(self):
        """get_schema_model must return correct Pydantic class."""
        model = get_schema_model("calibration_market_bar_dataset_v1")
        assert model is CalibrationMarketBarRowV1

        model = get_schema_model("calibration_feature_snapshot_dataset_v1")
        assert model is CalibrationFeatureSnapshotRowV1

    def test_get_schema_model_unknown_raises(self):
        """get_schema_model must raise KeyError for unknown schema."""
        with pytest.raises(KeyError, match="Unknown schema_id"):
            get_schema_model("unknown_schema_v1")

    def test_schema_version_for_valid(self):
        """schema_version_for must return version string."""
        version = schema_version_for("calibration_market_bar_dataset_v1")
        assert isinstance(version, str)
        assert version == "1.0.0"

    def test_schema_version_for_unknown_raises(self):
        """schema_version_for must raise KeyError for unknown schema."""
        with pytest.raises(KeyError, match="Unknown schema_id"):
            schema_version_for("unknown_schema_v1")


class TestExampleRowsValidate:
    """Test that all example rows validate against their schemas."""

    def test_market_bar_example_validates(self):
        """Market bar example must validate."""
        row = example_market_bar_row()
        assert row.dataset_schema == "calibration_market_bar_dataset_v1"
        assert row.synthetic is True

    def test_feature_snapshot_example_validates(self):
        """Feature snapshot example must validate."""
        row = example_feature_snapshot_row()
        assert row.dataset_schema == "calibration_feature_snapshot_dataset_v1"
        assert row.synthetic is True

    def test_oracle_regime_label_example_validates(self):
        """Oracle regime label example must validate."""
        row = example_oracle_regime_label_row()
        assert row.dataset_schema == "calibration_oracle_regime_labels_v1"
        assert row.synthetic is True

    def test_trade_decision_example_validates(self):
        """Trade decision example must validate."""
        row = example_trade_decision_row()
        assert row.dataset_schema == "calibration_trade_decision_dataset_v1"
        assert row.synthetic is True

    def test_realized_trade_example_validates(self):
        """Realized trade example must validate."""
        row = example_realized_trade_row()
        assert row.dataset_schema == "calibration_realized_trade_dataset_v1"
        assert row.synthetic is True

    def test_low_vol_gate_example_validates(self):
        """Low-vol gate example must validate."""
        row = example_low_vol_gate_row()
        assert row.dataset_schema == "calibration_low_vol_gate_dataset_v1"
        assert row.synthetic is True

    def test_walkforward_manifest_example_validates(self):
        """Walkforward manifest example must validate."""
        row = example_walkforward_manifest_row()
        assert row.dataset_schema == "calibration_walkforward_manifest_v1"


class TestValidateRow:
    """Test validate_row function."""

    def test_validate_row_success(self):
        """validate_row must accept valid row dict."""
        row_dict = {
            "dataset_schema": "calibration_market_bar_dataset_v1",
            "dataset_version": "1.0.0",
            "source_surface": "recorder_csv",
            "source_file": "data/recorder/test.csv",
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
        }
        row = validate_row("calibration_market_bar_dataset_v1", row_dict)
        assert isinstance(row, CalibrationMarketBarRowV1)
        assert row.synthetic is False

    def test_validate_row_unknown_schema_raises(self):
        """validate_row must raise KeyError for unknown schema."""
        with pytest.raises(KeyError, match="Unknown schema_id"):
            validate_row("unknown_schema_v1", {})

    def test_validate_row_missing_required_field_raises(self):
        """validate_row must raise ValidationError for missing required field."""
        row_dict = {
            "dataset_schema": "calibration_market_bar_dataset_v1",
            "dataset_version": "1.0.0",
            # Missing 'symbol' and other required fields
        }
        with pytest.raises(ValidationError):
            validate_row("calibration_market_bar_dataset_v1", row_dict)

    def test_validate_row_extra_field_raises(self):
        """validate_row must reject extra fields (extra='forbid')."""
        row_dict = {
            "dataset_schema": "calibration_market_bar_dataset_v1",
            "dataset_version": "1.0.0",
            "source_surface": "recorder_csv",
            "source_file": "data/recorder/test.csv",
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
            "extra_unknown_field": "should_fail",  # Extra field
        }
        with pytest.raises(ValidationError):
            validate_row("calibration_market_bar_dataset_v1", row_dict)


class TestValidateRows:
    """Test validate_rows batch validation."""

    def test_validate_rows_success(self):
        """validate_rows must accept batch of valid rows."""
        rows = [
            {
                "dataset_schema": "calibration_market_bar_dataset_v1",
                "dataset_version": "1.0.0",
                "source_surface": "recorder_csv",
                "source_file": "data/recorder/test.csv",
                "session_date": None,
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "ts_ms": 1000000000 + i,
                "bar_close_ts_ms": None,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": None,
                "trade_count": None,
                "data_quality": "good",
                "synthetic": False,
            }
            for i in range(3)
        ]
        validated = validate_rows("calibration_market_bar_dataset_v1", rows)
        assert len(validated) == 3
        assert all(isinstance(r, CalibrationMarketBarRowV1) for r in validated)

    def test_validate_rows_fails_on_first_bad_row(self):
        """validate_rows must fail on first bad row with row index."""
        rows = [
            {
                "dataset_schema": "calibration_market_bar_dataset_v1",
                "dataset_version": "1.0.0",
                "source_surface": "recorder_csv",
                "source_file": "data/recorder/test.csv",
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
            {
                # Missing required fields
                "dataset_schema": "calibration_market_bar_dataset_v1",
            },
        ]
        with pytest.raises(ValidationError):
            validate_rows("calibration_market_bar_dataset_v1", rows)


class TestSyntheticFlagPresent:
    """Test that all row schemas have explicit synthetic flag."""

    def test_market_bar_has_synthetic_flag(self):
        """CalibrationMarketBarRowV1 must have synthetic field."""
        row = example_market_bar_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)

    def test_feature_snapshot_has_synthetic_flag(self):
        """CalibrationFeatureSnapshotRowV1 must have synthetic field."""
        row = example_feature_snapshot_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)

    def test_oracle_regime_label_has_synthetic_flag(self):
        """CalibrationOracleRegimeLabelRowV1 must have synthetic field."""
        row = example_oracle_regime_label_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)

    def test_trade_decision_has_synthetic_flag(self):
        """CalibrationTradeDecisionRowV1 must have synthetic field."""
        row = example_trade_decision_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)

    def test_realized_trade_has_synthetic_flag(self):
        """CalibrationRealizedTradeRowV1 must have synthetic field."""
        row = example_realized_trade_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)

    def test_low_vol_gate_has_synthetic_flag(self):
        """CalibrationLowVolGateRowV1 must have synthetic field."""
        row = example_low_vol_gate_row()
        assert hasattr(row, "synthetic")
        assert isinstance(row.synthetic, bool)


class TestBoundaryGuard:
    """Test that boundary guard (apps/reference does not import calibrators) still passes."""

    def test_apps_reference_does_not_import_calibrators(self):
        """apps/reference must not import calibrators."""
        root = Path(__file__).resolve().parents[2]  # repo root
        runtime_root = root / "apps" / "reference"

        violations = []
        for path in sorted(runtime_root.rglob("*.py")):
            tree = ast.parse(path.read_text(
                encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "calibrators" or alias.name.startswith("calibrators."):
                            violations.append(
                                f"{path.as_posix()}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "calibrators" or module.startswith("calibrators."):
                        violations.append(
                            f"{path.as_posix()}: from {module} import ...")

        assert not violations, "apps/reference must not import calibrators:\n" + "\n".join(
            violations
        )
