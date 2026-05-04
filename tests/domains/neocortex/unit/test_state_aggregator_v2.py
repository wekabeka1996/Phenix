import pytest
import numpy as np
from unittest.mock import MagicMock

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.contracts.causal_time import CausalTimeProvenance
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
    _canonical_event_type,
    _extract_timestamp_ms,
    _extract_time_provenance,
    _first_non_empty,
    _encode_side,
    _normalize_symbol,
    _normalize_epoch_to_ms,
    _payload_view,
    _safe_float,
)


@pytest.fixture
def ingest_config():
    reset_failure_outcomes()
    return IngestConfig(
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


def test_aggregator_no_trigger(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config, tick_trigger_event_types=["EVT:BAR_CLOSED"])

    # Feature event should not trigger snapshot
    event = {
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "payload": {
            "features": {"volatility": 1.5, "price": 100}
        }
    }

    snapshot = aggregator.ingest_event(event)
    assert snapshot is None


def test_aggregator_trigger_with_missing_feature(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config, tick_trigger_event_types=["EVT:BAR_CLOSED"])

    # Trigger event without prior feature should return None
    event = {
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000001000,
        "payload": {}
    }
    snapshot = aggregator.ingest_event(event)
    assert snapshot is None


def test_aggregator_trigger_success(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config, tick_trigger_event_types=["EVT:BAR_CLOSED"])

    # 1. Provide feature
    event1 = {
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "payload": {
            "features": {"volatility": 1.5, "price": 100}
        }
    }
    assert aggregator.ingest_event(event1) is None

    # 2. Provide portfolio state
    event2 = {
        "event_type": "EVT:PORTFOLIO_STATE_UPDATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000500,
        "payload": {
            "position_qty": 2.0,
            "side": "LONG"
        }
    }
    assert aggregator.ingest_event(event2) is None

    # 3. Trigger
    event3 = {
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000001000,
        "payload": {}
    }
    snapshot = aggregator.ingest_event(event3)

    assert snapshot is not None
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.tick_ts_ms == 1700000001000
    assert snapshot.position_side == "LONG"

    # Observation vector (dim=2) + context vector (dim=11) = 13
    assert len(snapshot.state_vector) == 13


def test_aggregator_strict_clock(ingest_config):
    aggregator = NeocortexStateAggregator(ingest_config, tick_trigger_event_types=[
                                          "EVT:BAR_CLOSED"], strict_clock=True)

    # Initial setup
    aggregator.ingest_event({
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "payload": {"features": {"volatility": 1.5, "price": 100}}
    })

    # First trigger
    snapshot1 = aggregator.ingest_event({
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000001000,
        "payload": {}
    })
    assert snapshot1 is not None

    # Out of order trigger
    snapshot2 = aggregator.ingest_event({
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000500,  # Older than 1700000001000
        "payload": {}
    })
    assert snapshot2 is None

    # Reset
    aggregator.reset_symbol("BTCUSDT")
    # Now the previous timestamp shouldn't block it (though the feature is also gone)
    aggregator.ingest_event({
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "payload": {"features": {"volatility": 1.5, "price": 100}}
    })
    snapshot3 = aggregator.ingest_event({
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000500,
        "payload": {}
    })
    assert snapshot3 is not None


def test_aggregator_non_causal_shadow_event_records_skip_row(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config,
        tick_trigger_event_types=["EVT:BAR_CLOSED"],
        neocortex_enforcement_mode="shadow",
    )

    snapshot = aggregator.ingest_event({
        "event_type": "EVT:FEATURES_CALCULATED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000000000,
        "time_provenance": "captured_wallclock",
        "payload": {"features": {"volatility": 1.5, "price": 100}},
    })

    assert snapshot is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code="NON_CAUSAL_TIME",
    ) == 1


def test_aggregator_missing_feature_state_records_skip_row(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config, tick_trigger_event_types=["EVT:BAR_CLOSED"]
    )

    snapshot = aggregator.ingest_event({
        "event_type": "EVT:BAR_CLOSED",
        "symbol": "BTCUSDT",
        "timestamp_ms": 1700000001000,
        "payload": {},
    })

    assert snapshot is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code="MISSING_REQUIRED_STATE",
    ) == 1


def test_state_aggregator_helper_branches_and_cache_updates(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config,
        tick_trigger_event_types=["EVT:BAR_CLOSED"],
        neocortex_enforcement_mode="disabled",
    )

    event = {"payload": {"symbol": "BTCUSDT"}}
    assert _payload_view(event) == {"symbol": "BTCUSDT"}
    non_mapping_payload_event = {"payload": ["not", "a", "mapping"]}
    assert _payload_view(non_mapping_payload_event) is non_mapping_payload_event
    assert _canonical_event_type({"op": "EVT", "event_type": "BAR_CLOSED"}) == "EVT:BAR_CLOSED"
    assert _canonical_event_type("bar_closed") == "BAR_CLOSED"
    assert _normalize_symbol(None) is None
    assert _normalize_symbol(" btcusdt ") == "BTCUSDT"
    assert _extract_timestamp_ms({"ts": "1700000000000"}, {}) == 1700000000000
    assert _extract_timestamp_ms({}, {"timestamp": "bad"}) is None
    assert _extract_time_provenance({}, {}, "EVT:BAR_CLOSED") is CausalTimeProvenance.BAR_END
    assert _extract_time_provenance({}, {}, "EVT:REGIME_DETECTED") is CausalTimeProvenance.AURORA_EVENT
    assert _extract_time_provenance(
        {"time_provenance": CausalTimeProvenance.CAPTURED_WALLCLOCK.value},
        {},
        "EVT:FEATURES_CALCULATED",
    ) is CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert _extract_time_provenance({}, {}, "UNKNOWN_EVENT") is CausalTimeProvenance.UNKNOWN
    assert _first_non_empty(None, "  ", "alpha") == "alpha"
    assert _first_non_empty(None, "  ") is None

    assert aggregator._should_drop_non_causal_time(
        symbol="BTCUSDT",
        event_type="EVT:FEATURES_CALCULATED",
        time_provenance=CausalTimeProvenance.AURORA_EVENT,
    ) is False
    aggregator.reset_symbol("   ")
    aggregator.reset_symbol(None)

    assert (
        aggregator.ingest_event(
            {
                "event_type": "EVT:REGIME_DETECTED",
                "timestamp_ms": 1_700_000_000_000,
                "payload": {"symbol": "BTCUSDT", "regime": "TREND_UP"},
            }
        )
        is None
    )
    assert aggregator._regime_ts_ms["BTCUSDT"] == 1_700_000_000_000


def test_state_aggregator_missing_timestamp_and_symbol_return_none(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config,
        tick_trigger_event_types=["EVT:BAR_CLOSED"],
    )

    assert aggregator.ingest_event(
        {
            "event_type": "EVT:FEATURES_CALCULATED",
            "payload": {"symbol": "BTCUSDT", "features": {"volatility": 1.5}},
        }
    ) is None
    assert aggregator.ingest_event(
        {
            "event_type": "EVT:FEATURES_CALCULATED",
            "timestamp_ms": 1_700_000_000_000,
            "payload": {"features": {"volatility": 1.5}},
        }
    ) is None


def test_state_aggregator_build_snapshot_value_error_returns_none(ingest_config):
    aggregator = NeocortexStateAggregator(
        ingest_config,
        tick_trigger_event_types=["EVT:BAR_CLOSED"],
    )
    aggregator._feature_cache["BTCUSDT"] = {
        "symbol": "BTCUSDT",
        "timestamp_ms": 1_700_000_000_000,
        "features": {"volatility": 1.5, "price": 100},
    }
    aggregator._feature_ts_ms["BTCUSDT"] = 1_700_000_000_000
    aggregator._feature_parser.parse = MagicMock(side_effect=ValueError("bad payload"))

    assert (
        aggregator._build_snapshot(
            symbol="BTCUSDT",
            tick_ts_ms=1_700_000_000_100,
            trigger_event_type="EVT:BAR_CLOSED",
        )
        is None
    )


def test_state_aggregator_helper_branches_cover_helper_defaults(ingest_config):
    assert _normalize_epoch_to_ms(None) is None
    assert _normalize_epoch_to_ms(False) is None
    assert _normalize_epoch_to_ms("bad") is None
    assert _normalize_epoch_to_ms(123.0) is None
    assert _normalize_epoch_to_ms(0) is None
    assert _normalize_epoch_to_ms(float("inf")) is None
    assert _normalize_epoch_to_ms(float("nan")) is None
    assert _normalize_epoch_to_ms(1_700_000_000) == 1_700_000_000_000
    assert _normalize_epoch_to_ms(1_700_000_000_000) == 1_700_000_000_000
    assert _safe_float(float("inf"), default=7.0) == 7.0
    assert _safe_float("bad", default=7.0) == 7.0
    assert _encode_side("BUY") == 1.0
    assert _encode_side("short") == -1.0
    assert _encode_side("unknown") == 0.0
