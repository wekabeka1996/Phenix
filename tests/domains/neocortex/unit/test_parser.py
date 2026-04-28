import pytest
import numpy as np

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.parser import (
    FeatureParser,
    _extract_payload_timestamp_contract,
    _flatten_features,
    _infer_payload_time_provenance,
    _normalize_epoch_to_ms,
)


@pytest.fixture
def base_config():
    return IngestConfig(
        feature_list=["delta_price", "volatility", "volume_zscore", "price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        price_feature_mode="raw",
        delta_price_mode="raw",
        feature_clip_abs={"volume_zscore": 5.0}
    )


def test_parser_missing_timestamp(base_config):
    parser = FeatureParser(base_config)
    with pytest.raises(ValueError, match="Payload missing timestamp"):
        parser.parse({"features": {}})


def test_parser_flattening_and_extraction(base_config):
    parser = FeatureParser(base_config)
    payload = {
        "timestamp": 1700000000000,
        "volatility": 1.5,
        "features": {
            "delta": {"price": 0.05},
            "volatility": 1.5,
            "volume_zscore": 2.0,
            "price": 100.0
        }
    }
    obs = parser.parse(payload)
    assert obs.ts == 1700000000000
    assert obs.event_ts_ms == 1700000000000
    assert obs.time_provenance == CausalTimeProvenance.AURORA_EVENT
    assert obs.volatility == 1.5
    # delta_price is flattened from delta.price -> delta_price
    assert np.isclose(obs.features_vector[0], 0.05)  # delta_price
    assert np.isclose(obs.features_vector[1], 1.5)  # volatility
    assert np.isclose(obs.features_vector[2], 2.0)  # volume_zscore
    assert np.isclose(obs.features_vector[3], 100.0)  # price


def test_parser_nan_infinity_handling(base_config):
    parser = FeatureParser(base_config)
    payload = {
        "timestamp": 1700000000000,
        "features": {
            "delta_price": float('nan'),
            "volatility": float('inf'),
            "volume_zscore": "-inf",
            "price": "invalid_string"
        }
    }
    obs = parser.parse(payload)
    # Expected to default to 0.0
    for i in range(4):
        assert obs.features_vector[i] == 0.0


def test_parser_transforms_log_and_pct():
    config = IngestConfig(
        feature_list=["delta_price", "price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        feature_clip_abs={},
        price_feature_mode="log",
        delta_price_mode="pct"
    )
    parser = FeatureParser(config)
    payload = {
        "timestamp": 1700000000000,
        "features": {
            "delta_price": 5.0,
            "price": 100.0
        }
    }
    obs = parser.parse(payload)
    # price is log(100) = 4.605
    # delta_price pct mode = 5.0 / 100.0 = 0.05
    assert np.isclose(obs.features_vector[0], 0.05)
    assert np.isclose(obs.features_vector[1], np.log(100.0))
    assert obs.time_provenance == CausalTimeProvenance.AURORA_EVENT


def test_parser_clipping(base_config):
    parser = FeatureParser(base_config)
    payload = {
        "timestamp": 1700000000000,
        "features": {
            "volume_zscore": 10.0  # Clip limit is 5.0
        }
    }
    obs = parser.parse(payload)
    # volume_zscore is index 2
    assert obs.features_vector[2] == 5.0


def test_parser_helper_fallbacks_and_non_dict_features(base_config):
    assert _normalize_epoch_to_ms(None) is None
    assert _normalize_epoch_to_ms(False) is None
    assert _normalize_epoch_to_ms("1700000000") == 1700000000000
    assert _normalize_epoch_to_ms("bad") is None

    assert _infer_payload_time_provenance(
        {"event_type": "BAR_CLOSED"}, source_key="ts"
    ) is CausalTimeProvenance.BAR_END
    assert _infer_payload_time_provenance(
        {"ts": 1700000000000}, source_key="ts"
    ) is CausalTimeProvenance.AURORA_EVENT
    assert _infer_payload_time_provenance({}, source_key="other") is CausalTimeProvenance.UNKNOWN

    flattened = _flatten_features({"outer.inner": 1.0, "outer": {"inner": 2.0}})
    assert flattened["outer_inner"] == 1.0

    parser = FeatureParser(base_config)
    obs = parser.parse(
        {
            "timestamp": 1700000000000,
            "features": ["not", "a", "dict"],
            "price": 100.0,
            "volatility": 1.5,
        }
    )
    assert obs.time_provenance == CausalTimeProvenance.AURORA_EVENT
    assert obs.features_vector.shape[0] == 4


def test_parser_additional_branch_paths(base_config):
    assert _normalize_epoch_to_ms(1_000_000_000_000) == 1_000_000_000_000
    assert _normalize_epoch_to_ms(1_000_000_000) == 1_000_000_000_000
    assert _normalize_epoch_to_ms(0) is None
    assert _normalize_epoch_to_ms(float("inf")) is None
    assert _normalize_epoch_to_ms(123.0) is None
    assert _infer_payload_time_provenance(
        {"time_provenance": "captured_wallclock"},
        source_key="ts",
    ) is CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert _flatten_features({1: {"two.three": 4}})["1_two_three"] == 4
    ts, event_ts_ms, provenance = _extract_payload_timestamp_contract(
        {"timestamp": "bad", "ts": 1_700_000_000_000}
    )
    assert ts == 1_700_000_000_000.0
    assert event_ts_ms == 1_700_000_000_000
    assert provenance is CausalTimeProvenance.AURORA_EVENT

    parser = FeatureParser(
        IngestConfig(
            feature_list=["delta_price", "price"],
            normalization_method="zscore",
            normalization_window=100,
            normalization_scope="per_symbol",
            buffer_size=1000,
            min_samples_before_ready=10,
            nan_strategy="zero",
            feature_clip_abs={},
            price_feature_mode="log",
            delta_price_mode="raw",
        )
    )
    assert parser._sanitize_finite(float("inf"), default=7.0) == 7.0
    assert parser._safe_float("bad", 7.0) == 7.0
    obs = parser.parse(
        {
            "timestamp": 1700000000000,
            "features": {
                "delta_price": 1.0,
                "price": 0.0,
            },
        }
    )
    assert np.isclose(obs.features_vector[1], 0.0)


def test_parser_timestamp_contract_and_representation_drop_branch():
    config = IngestConfig(
        feature_list=["delta_price", "volatility", "volume_zscore", "price"],
        normalization_method="zscore",
        normalization_window=100,
        normalization_scope="per_symbol",
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        price_feature_mode="drop",
        delta_price_mode="pct",
        feature_clip_abs={},
    )
    parser = FeatureParser(config)
    obs = parser.parse(
        {
            "timestamp": "bad",
            "ts": 1_700_000_000_000,
            "time_source": "captured_wallclock",
            "mid_price": "bad",
            "features": {
                "bb_width": 2.5,
                "obi": 1.5,
                "delta_price": 2.0,
                "price": 1000.0,
            },
        }
    )

    assert obs.event_ts_ms == 1_700_000_000_000
    assert obs.time_provenance == CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert np.isclose(obs.volatility, 2.5)
    assert np.isclose(obs.obi, 1.5)
    assert np.isclose(obs.features_vector[0], 0.002)
    assert obs.features_vector[3] == 0.0
