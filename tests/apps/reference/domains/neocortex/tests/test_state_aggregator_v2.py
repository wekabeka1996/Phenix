import numpy as np

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)


def _make_config() -> IngestConfig:
    return IngestConfig(
        feature_list=["price", "obi", "delta_price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        price_feature_mode="log",
        delta_price_mode="pct",
        feature_clip_abs={},
    )


def test_emits_snapshot_on_feature_trigger():
    aggregator = NeocortexStateAggregator(_make_config())

    snapshot = aggregator.ingest_event(
        {
            "event_type": "EVT:FEATURES_CALCULATED",
            "timestamp": 1_700_000_000_000,
            "symbol": "BTCUSDT",
            "mid_price": 100.0,
            "features": {
                "price": 100.0,
                "obi": 0.25,
                "delta_price": 1.0,
            },
        }
    )

    assert snapshot is not None
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.trigger_event_type == "EVT:FEATURES_CALCULATED"
    assert snapshot.observation.normalized is True
    assert snapshot.state_vector.dtype == np.float32
    assert snapshot.state_vector.shape[0] == 14


def test_bar_closed_uses_cached_feature_payload_and_regime_context():
    aggregator = NeocortexStateAggregator(
        _make_config(),
        tick_trigger_event_types=("EVT:BAR_CLOSED",),
    )

    assert (
        aggregator.ingest_event(
            {
                "event_type": "EVT:FEATURES_CALCULATED",
                "timestamp": 1_700_000_000_000,
                "symbol": "ETHUSDT",
                "mid_price": 200.0,
                "features": {
                    "price": 200.0,
                    "obi": -0.5,
                    "delta_price": 2.0,
                },
            }
        )
        is None
    )

    assert (
        aggregator.ingest_event(
            {
                "event_type": "EVT:REGIME_DETECTED",
                "timestamp": 1_700_000_000_500,
                "symbol": "ETHUSDT",
                "regime": "TREND_UP",
                "confidence": 0.61,
            }
        )
        is None
    )

    snapshot = aggregator.ingest_event(
        {
            "event_type": "EVT:BAR_CLOSED",
            "timestamp": 1_700_000_001_000,
            "symbol": "ETHUSDT",
        }
    )

    assert snapshot is not None
    assert snapshot.symbol == "ETHUSDT"
    assert snapshot.trigger_event_type == "EVT:BAR_CLOSED"
    assert snapshot.feature_event_ts_ms == 1_700_000_000_000
    assert snapshot.regime_label == "TREND_UP"
    assert snapshot.regime_confidence == 0.61


def test_strict_clock_rejects_out_of_order_triggers():
    aggregator = NeocortexStateAggregator(
        _make_config(), tick_trigger_event_types=("EVT:BAR_CLOSED",))

    aggregator.ingest_event(
        {
            "event_type": "EVT:FEATURES_CALCULATED",
            "timestamp": 1_700_000_000_000,
            "symbol": "SOLUSDT",
            "mid_price": 50.0,
            "features": {
                "price": 50.0,
                "obi": 0.1,
                "delta_price": 0.5,
            },
        }
    )

    first = aggregator.ingest_event(
        {
            "event_type": "EVT:BAR_CLOSED",
            "timestamp": 1_700_000_001_000,
            "symbol": "SOLUSDT",
        }
    )
    stale = aggregator.ingest_event(
        {
            "event_type": "EVT:BAR_CLOSED",
            "timestamp": 1_700_000_000_900,
            "symbol": "SOLUSDT",
        }
    )

    assert first is not None
    assert stale is None
