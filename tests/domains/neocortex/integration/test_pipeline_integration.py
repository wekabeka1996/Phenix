import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import NeocortexStateAggregator
from apps.reference.domains.neocortex.logic.brain.baseline_inference import BaselineController


@patch("apps.reference.domains.neocortex.logic.brain.baseline_inference.joblib.load")
def test_full_pipeline_ingest_to_baseline(mock_load):
    # Setup mock baseline model
    mock_model = MagicMock()
    # Mock to predict BLOCK (index 1 -> 0.9 probability)
    mock_model.predict_proba.return_value = np.array([[0.1, 0.9]])
    mock_model.classes_ = np.array([0, 1])

    mock_load.return_value = {
        "model": mock_model,
        "feature_columns": ["f_symbol", "f_observation__features__volatility", "f_observation__features__price", "f_intent__side"],
        "threshold": 0.8
    }

    # Init pipeline components
    ingest_config = IngestConfig(
        feature_list=["volatility", "price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        feature_clip_abs={},
        price_feature_mode="raw",
        delta_price_mode="raw"
    )

    aggregator = NeocortexStateAggregator(
        ingest_config, tick_trigger_event_types=["EVT:BAR_CLOSED"])
    controller = BaselineController("dummy_path.pkl")

    # 1. Ingest Features
    aggregator.ingest_event({
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "payload": {
            "features": {"volatility": 1.5, "price": 50000.0}
        }
    })

    # 2. Ingest Intent
    aggregator.ingest_event({
        "event_type": "EVT:TRADE_INTENT_PROPOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000005,
        "payload": {
            "side": "BUY",
            "quantity": 1.0
        }
    })

    # 3. Trigger Snapshot
    snapshot = aggregator.ingest_event({
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000001000,
        "payload": {}
    })

    assert snapshot is not None
    assert snapshot.symbol == "BTCUSDT"

    # 4. Snapshot to state vector for baseline controller
    snapshot_dict = {
        "symbol": snapshot.symbol,
        "trigger_event_type": snapshot.trigger_event_type,
        "intent": {
            "side": snapshot.intent_side
        },
        "observation": {
            "features": {
                "volatility": snapshot.observation.features_vector[0],
                "price": snapshot.observation.features_vector[1]
            }
        }
    }

    state_vector = controller.state_vector_from_snapshot(snapshot_dict)

    # 5. Predict intent
    decision = controller.predict_intent(state_vector)

    assert decision == "BLOCK"
    # verify expected state vector mapping
    assert state_vector[0] == "BTCUSDT"
    assert state_vector[3] == "BUY"
