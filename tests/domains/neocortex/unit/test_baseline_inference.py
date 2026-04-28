import decimal

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineController,
    _safe_float,
    _add_feature,
    _flatten_scalars,
)


def test_safe_float():
    assert _safe_float("1.23") == 1.23
    assert _safe_float(None) is None
    assert _safe_float(True) is None
    assert _safe_float("invalid") is None
    assert _safe_float(float('inf')) is None
    assert _safe_float(float('nan')) is None


def test_add_feature():
    features = {}
    _add_feature(features, "test_num", 5.0)
    assert features["f_test_num"] == 5.0

    _add_feature(features, "test_decimal", decimal.Decimal("1.25"))
    assert features["f_test_decimal"] == 1.25

    _add_feature(features, "test_bool", True)
    assert features["f_test_bool"] == 1.0

    _add_feature(features, "test_str", "hello")
    assert features["f_test_str"] == "HELLO"

    _add_feature(features, "test_blank", "   ")
    assert "f_test_blank" not in features

    _add_feature(features, "test_nan", float('nan'))
    assert "f_test_nan" not in features

    _add_feature(features, "test_object", object())
    assert "f_test_object" not in features


def test_flatten_scalars():
    features = {}
    _flatten_scalars({"a": 1, "b": {"c": 2}, "d": [
                     1, 2, 3]}, "prefix", features)

    assert features["f_prefix__a"] == 1.0
    assert features["f_prefix__b__c"] == 2.0
    assert features["f_prefix__d__len"] == 3.0
    assert features["f_prefix__d__mean"] == 2.0
    assert features["f_prefix__d__min"] == 1.0


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_init(mock_load):
    mock_model = MagicMock()
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol", "f_intent__side"],
        "threshold": 0.9
    }

    controller = BaselineController("fake_path.pkl")
    assert controller.threshold == 0.9
    assert controller.feature_columns == ["f_symbol", "f_intent__side"]


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_predict(mock_load):
    mock_model = MagicMock()
    # Mock predict_proba to return 0.95 toxic probability
    mock_model.predict_proba.return_value = np.array([[0.05, 0.95]])
    mock_model.classes_ = np.array([0, 1])

    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol", "f_intent__side"],
        "threshold": 0.8
    }

    controller = BaselineController("fake_path.pkl")

    snapshot = {
        "symbol": "BTC",
        "intent": {"side": "BUY"}
    }

    vector = controller.state_vector_from_snapshot(snapshot)
    assert len(vector) == 2

    action = controller.predict_intent(vector)
    assert action == "BLOCK"  # 0.95 > 0.8


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_predict_mismatch(mock_load):
    mock_model = MagicMock()
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol", "f_intent__side"],
        "threshold": 0.8,
    }

    controller = BaselineController("fake_path.pkl")
    with pytest.raises(ValueError, match="does not match model feature count"):
        controller.predict_intent(np.array([1, 2, 3]))


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_missing_threshold_rejected(mock_load):
    mock_model = MagicMock()
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol"],
    }

    with pytest.raises(ValueError, match="threshold must be provided"):
        BaselineController("fake_path.pkl")


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_missing_toxic_class_rejected(mock_load):
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[1.0]])
    mock_model.classes_ = np.array([0])
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol"],
        "threshold": 0.8,
    }

    controller = BaselineController("fake_path.pkl")
    with pytest.raises(ValueError, match="toxic class 1"):
        controller.predict_intent(np.array(["BTC"]))


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_missing_classes_rejected_even_with_named_steps(mock_load):
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.2, 0.8]])
    mock_model.classes_ = None
    mock_model.named_steps = {}
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol"],
        "threshold": 0.8,
    }

    controller = BaselineController("fake_path.pkl")
    with pytest.raises(ValueError, match="classes_ is required"):
        controller.predict_intent(np.array(["BTC"]))


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_snapshot_aliases_support_observation_envelope_shape(mock_load):
    mock_model = MagicMock()
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": [
            "f_symbol",
            "f_snapshot_contract",
            "f_trigger_event_type",
            "f_intent__side",
            "f_observation__features__obi",
            "f_safety_gate__path",
            "f_portfolio_position__side",
        ],
        "threshold": 0.8,
    }

    controller = BaselineController("fake_path.pkl")
    snapshot = {
        "symbol": "BTCUSDT",
        "schema_passport_id": "neocortex.observation_envelope.v1",
        "source_event_name": "EVT:FEATURES_CALCULATED",
        "candidate_intent_summary": {"side": "BUY"},
        "market_features": {"obi": 0.25},
        "gate_trace_summary": {"path": "shadow"},
        "portfolio_state": {"side": "LONG"},
    }

    vector = controller.state_vector_from_snapshot(snapshot)
    assert vector.tolist() == [
        "BTCUSDT",
        "NEOCORTEX.OBSERVATION_ENVELOPE.V1",
        "EVT:FEATURES_CALCULATED",
        "BUY",
        0.25,
        "SHADOW",
        "LONG",
    ]


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_baseline_controller_prefers_explicit_safety_gate_mapping(mock_load):
    mock_model = MagicMock()
    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_safety_gate__path"],
        "threshold": 0.8,
    }

    controller = BaselineController("fake_path.pkl")
    vector = controller.state_vector_from_snapshot(
        {"safety_gate": {"path": "strict"}, "gate_trace_summary": {"path": "shadow"}}
    )

    assert vector.tolist() == ["STRICT"]
