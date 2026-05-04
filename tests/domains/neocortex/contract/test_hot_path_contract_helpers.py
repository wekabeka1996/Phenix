from __future__ import annotations

from collections import UserDict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
    _coerce_dataset_visibility,
    _coerce_optional_int,
    _coerce_source_mapping,
    build_observation_envelope,
    resolve_alias_value,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
    _add_feature,
    _flatten_scalars,
    _safe_float,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


class _NestedModel:
    def __init__(self) -> None:
        self.named_steps = {"model": _NestedPredictModel()}

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return self.named_steps["model"].predict_proba(frame)


class _NestedPredictModel:
    classes_ = np.array([0, 1])

    def predict_proba(self, _frame: pd.DataFrame) -> np.ndarray:
        return np.array([[0.25, 0.75]])


def _trainable_snapshot():
    config = load_config(CONFIG_DIR)
    aggregator = NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode="disabled",
    )
    snapshot = aggregator.ingest_event(
        {
            "event_name": "EVT:FEATURES_CALCULATED",
            "captured_ts_ms": 1_700_000_000_000,
            "payload": {
                "symbol": "BTCUSDT",
                "timestamp_ms": 1_700_000_000_000,
                "time_provenance": CausalTimeProvenance.AURORA_EVENT.value,
                "features": {
                    "price": 100.0,
                    "obi": 0.25,
                    "delta_price": 1.0,
                },
            },
        }
    )
    assert snapshot is not None
    return snapshot


def setup_function() -> None:
    reset_failure_outcomes()


def test_observation_envelope_helper_fallbacks_and_rejections() -> None:
    snapshot = _trainable_snapshot()
    source = {
        "observation": {"features": {"price": 123.0}},
        "decision_id": "decision-a",
        "event_name": "EVT:BAR_CLOSED",
    }

    envelope = build_observation_envelope(snapshot, source)
    assert isinstance(envelope, ObservationEnvelope)
    assert envelope.observation_id == "decision-a"
    assert envelope.source_event_name == "EVT:BAR_CLOSED"
    assert envelope.source_event_id == "decision-a"
    assert envelope.market_features["price"] == 123.0
    assert envelope.regime_state["label"] == snapshot.regime_label
    assert envelope.portfolio_state["side"] == snapshot.position_side
    assert envelope.candidate_intent_summary["side"] == snapshot.intent_side

    assert _coerce_source_mapping(None) == {}
    assert resolve_alias_value(
        {"observation_id": None, "decision_id": "fallback"},
        "observation_id",
        ("observation_id", "decision_id"),
        required=False,
    ) == "fallback"
    assert resolve_alias_value(
        {"observation_id": "   ", "decision_id": "fallback"},
        "observation_id",
        ("observation_id", "decision_id"),
        required=False,
    ) == "fallback"
    assert resolve_alias_value(
        {"observation_id": ""},
        "observation_id",
        ("observation_id", "decision_id"),
        required=False,
    ) is None
    assert _coerce_optional_int(None, field_name="decision_basis_ts_ms", default=7) == 7
    assert _coerce_optional_int(True, field_name="decision_basis_ts_ms", default=7) == 7
    assert _coerce_optional_int(8, field_name="decision_basis_ts_ms", default=7) == 8
    assert _coerce_optional_int(8.2, field_name="decision_basis_ts_ms", default=7) == 8
    assert _coerce_optional_int("9.4", field_name="decision_basis_ts_ms", default=7) == 9
    assert _coerce_optional_int(float("inf"), field_name="decision_basis_ts_ms", default=7) == 7
    with pytest.raises(ValueError, match="Invalid integer value"):
        _coerce_optional_int("bad", field_name="decision_basis_ts_ms", default=7)
    with pytest.raises(ValueError, match="Invalid integer value"):
        _coerce_optional_int("   ", field_name="decision_basis_ts_ms", default=7)
    assert _coerce_dataset_visibility("diagnostics_only") == "diagnostics_only"
    with pytest.raises(ValueError, match="Invalid dataset_visibility"):
        _coerce_dataset_visibility("unknown")
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.BLOCK,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) >= 0


def test_observation_envelope_uses_snapshot_fallbacks_and_required_alias_failure() -> None:
    config = load_config(CONFIG_DIR)
    aggregator = NeocortexStateAggregator(
        config.ingest,
        tick_trigger_event_types=["EVT:BAR_CLOSED"],
        strict_clock=True,
        neocortex_enforcement_mode="disabled",
    )
    assert (
        aggregator.ingest_event(
            {
                "event_name": "EVT:FEATURES_CALCULATED",
                "captured_ts_ms": 1_700_000_000_000,
                "payload": {
                    "symbol": "BTCUSDT",
                    "timestamp_ms": 1_700_000_000_000,
                    "time_provenance": CausalTimeProvenance.AURORA_EVENT.value,
                    "features": {"price": 100.0, "obi": 0.25, "delta_price": 1.0},
                },
            }
        )
        is None
    )
    assert (
        aggregator.ingest_event(
            {
                "event_name": "EVT:REGIME_DETECTED",
                "captured_ts_ms": 1_700_000_000_050,
                "payload": {
                    "symbol": "BTCUSDT",
                    "timestamp_ms": 1_700_000_000_050,
                    "regime": "TREND_UP",
                    "confidence": 0.8,
                },
            }
        )
        is None
    )
    assert (
        aggregator.ingest_event(
            {
                "event_name": "EVT:PORTFOLIO_STATE_UPDATED",
                "captured_ts_ms": 1_700_000_000_060,
                "payload": {
                    "symbol": "BTCUSDT",
                    "timestamp_ms": 1_700_000_000_060,
                    "side": "LONG",
                },
            }
        )
        is None
    )

    snapshot = aggregator.ingest_event(
        {
            "event_name": "EVT:BAR_CLOSED",
            "captured_ts_ms": 1_700_000_000_100,
            "payload": {
                "symbol": "BTCUSDT",
                "timestamp_ms": 1_700_000_000_100,
            },
        }
    )
    assert snapshot is not None

    envelope = build_observation_envelope(
        snapshot,
        {
            "decision_id": "decision-e",
            "event_name": "EVT:BAR_CLOSED",
            "observation": ["not", "a", "mapping"],
        },
    )

    assert envelope.market_features["feature_vector"]
    assert envelope.freshness["regime_age_ms"] == 50
    assert envelope.freshness["portfolio_age_ms"] == 40
    assert resolve_alias_value(
        {"observation_id": None, "decision_id": None},
        "observation_id",
        ("observation_id", "decision_id"),
        required=False,
    ) is None
    with pytest.raises(ValueError, match="Missing required alias"):
        resolve_alias_value(
            {},
            "observation_id",
            ("observation_id", "decision_id"),
            required=True,
        )


def test_observation_envelope_explicit_mappings_flip_fallback_branches() -> None:
    snapshot = _trainable_snapshot()
    source = {
        "decision_id": "decision-b",
        "event_name": "EVT:BAR_CLOSED",
        "market_features": {"price": 321.0},
        "regime_state": {"label": "TREND_UP", "confidence": 0.9},
        "portfolio_state": {"side": "LONG"},
        "candidate_intent_summary": {"side": "BUY"},
    }

    envelope = build_observation_envelope(snapshot, source)
    assert envelope.market_features["price"] == 321.0
    assert envelope.regime_state["label"] == "TREND_UP"
    assert envelope.portfolio_state["side"] == "LONG"
    assert envelope.candidate_intent_summary["side"] == "BUY"


def test_observation_envelope_model_validator_blocks_invalid_state() -> None:
    snapshot = _trainable_snapshot()
    envelope = build_observation_envelope(
        snapshot,
        {
            "decision_id": "decision-c",
            "event_name": "EVT:BAR_CLOSED",
            "market_features": {"price": 123.0},
            "regime_state": {"label": "TREND_UP", "confidence": 0.9},
            "portfolio_state": {"side": "LONG"},
            "candidate_intent_summary": {"side": "BUY"},
        },
    )
    payload = envelope.model_dump(mode="python")

    with pytest.raises(ValueError, match="causal state"):
        ObservationEnvelope.model_validate({**payload, "event_time_is_causal": False})
    with pytest.raises(ValueError, match="trainable state"):
        ObservationEnvelope.model_validate({**payload, "trainable": False})
    with pytest.raises(ValueError, match="dataset_visibility"):
        ObservationEnvelope.model_validate(
            {**payload, "dataset_visibility": "diagnostics_only"}
        )


def test_baseline_helper_paths_and_prediction_fallbacks(tmp_path: Path) -> None:
    assert _safe_float(None) is None
    assert _safe_float(True) is None
    assert _safe_float("3.5") == 3.5
    assert _safe_float("bad") is None

    features: dict[str, object] = {}
    _add_feature(features, "flag", True)
    _add_feature(features, "count", 7)
    _add_feature(features, "ratio", 2.5)
    _add_feature(features, "label", "  mixed Case  ")
    _add_feature(features, "long", "x" * 70)
    _flatten_scalars({"outer": {"inner": [1, 2, 3]}}, "prefix", features)
    assert features["f_flag"] == 1.0
    assert features["f_count"] == 7.0
    assert features["f_ratio"] == 2.5
    assert features["f_label"] == "MIXED CASE"
    assert features["f_long"] == "x" * 64
    assert features["f_prefix__outer__inner__len"] == 3.0

    artifact_path = tmp_path / "baseline.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _NestedModel(),
            "feature_columns": ["f_symbol"],
            "threshold": 0.5,
        },
        artifact_path,
    )
    controller = BaselineController(artifact_path)

    with pytest.raises(BaselinePredictionError, match="length"):
        controller.predict_intent(np.array(["BTC", "ETH"]))

    probability = controller.predict_toxic_probability(
        pd.DataFrame([["BTC"]], columns=["f_symbol"])
    )
    assert probability == 0.75

    vector = controller.state_vector_from_snapshot(UserDict({"symbol": "BTC"}))
    assert np.isnan(vector[0])


def test_baseline_controller_constructor_and_shape_branches(tmp_path: Path) -> None:
    non_dict_path = tmp_path / "non-dict.pkl"
    joblib.dump(["not", "a", "dict"], non_dict_path)
    with pytest.raises(BaselineArtifactError, match="must be a dict"):
        BaselineController(non_dict_path)

    missing_predict_proba_path = tmp_path / "missing-predict-proba.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": object(),
            "feature_columns": ["f_symbol"],
            "threshold": 0.5,
        },
        missing_predict_proba_path,
    )
    with pytest.raises(BaselineArtifactError, match="missing predict_proba model"):
        BaselineController(missing_predict_proba_path)

    missing_columns_path = tmp_path / "missing-columns.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _NestedModel(),
            "feature_columns": [],
            "threshold": 0.5,
        },
        missing_columns_path,
    )
    with pytest.raises(BaselineArtifactError, match="missing feature_columns"):
        BaselineController(missing_columns_path)

    threshold_path = tmp_path / "threshold.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _NestedModel(),
            "feature_columns": ["f_symbol"],
            "threshold": 0.5,
        },
        threshold_path,
    )
    controller = BaselineController(threshold_path, threshold=0.7)
    assert controller.threshold == 0.7

    features: dict[str, object] = {}
    _flatten_scalars({"empty": []}, "prefix", features)
    assert features == {}

    controller = BaselineController(threshold_path)
    scalar = controller.predict_intent(np.array(1.0))
    matrix = controller.predict_intent(np.array([["BTC"]], dtype=object))
    assert scalar in {"BLOCK", "ALLOW"}
    assert matrix in {"BLOCK", "ALLOW"}
