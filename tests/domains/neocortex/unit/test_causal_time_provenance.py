import logging

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)


def _ingest_config() -> IngestConfig:
    return IngestConfig(
        feature_list=["price", "obi", "delta_price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        feature_clip_abs={},
        price_feature_mode="raw",
        delta_price_mode="raw",
    )


def test_shadow_mode_drops_wallclock_feature_rows(caplog) -> None:
    aggregator = NeocortexStateAggregator(
        _ingest_config(),
        tick_trigger_event_types=("EVT:BAR_CLOSED",),
        neocortex_enforcement_mode="shadow",
    )

    with caplog.at_level(logging.WARNING):
        feature_snapshot = aggregator.ingest_event(
            {
                "event_type": "EVT:FEATURES_CALCULATED",
                "symbol": "BTCUSDT",
                "timestamp_ms": 1_700_000_000_000,
                "payload": {
                    "features": {
                        "price": 100.0,
                        "obi": 0.25,
                        "delta_price": 1.0,
                    },
                    "time_provenance": CausalTimeProvenance.CAPTURED_WALLCLOCK.value,
                },
            }
        )

    assert feature_snapshot is None
    assert "Dropping non-causal Neocortex event" in caplog.text

    trigger_snapshot = aggregator.ingest_event(
        {
            "event_type": "EVT:BAR_CLOSED",
            "symbol": "BTCUSDT",
            "timestamp_ms": 1_700_000_001_000,
            "payload": {
                "time_provenance": CausalTimeProvenance.BAR_END.value,
            },
        }
    )

    assert trigger_snapshot is None


def test_shadow_mode_allows_explicit_legacy_time_only_with_test_flag() -> None:
    aggregator = NeocortexStateAggregator(
        _ingest_config(),
        tick_trigger_event_types=("EVT:BAR_CLOSED",),
        neocortex_enforcement_mode="shadow",
        allow_legacy_non_causal_time=True,
    )

    assert (
        aggregator.ingest_event(
            {
                "event_type": "EVT:FEATURES_CALCULATED",
                "symbol": "BTCUSDT",
                "timestamp_ms": 1_700_000_000_000,
                "payload": {
                    "features": {
                        "price": 100.0,
                        "obi": 0.25,
                        "delta_price": 1.0,
                    },
                    "time_provenance": CausalTimeProvenance.FILE_OFFSET_LEGACY.value,
                },
            }
        )
        is None
    )

    snapshot = aggregator.ingest_event(
        {
            "event_type": "EVT:BAR_CLOSED",
            "symbol": "BTCUSDT",
            "timestamp_ms": 1_700_000_001_000,
            "payload": {
                "time_provenance": CausalTimeProvenance.BAR_END.value,
            },
        }
    )

    assert snapshot is not None
    assert snapshot.feature_time_provenance == CausalTimeProvenance.FILE_OFFSET_LEGACY
