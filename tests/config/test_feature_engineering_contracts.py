import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config_models as cm
import apps.reference.config.domains.feature_engineering as domain_fe


CONFIG_DIR = Path("config/aurora")


CONTRACT_CASES = {
    "FeatureEngineeringConfig": {
        "required": {"ema", "volume", "volatility", "liquidity", "macro_sync"},
        "defaults": {},
        "class_factories": {},
    },
    "EmaConfigDetailed": {
        "required": {"period_short", "period_long"},
        "defaults": {},
        "class_factories": {},
    },
    "VolumeConfigDetailed": {
        "required": {"sma_length", "window_sec", "min_window_volume_usd"},
        "defaults": {},
        "class_factories": {},
    },
    "VolatilityConfigDetailed": {
        "required": {"sma_length", "window_sec"},
        "defaults": {},
        "class_factories": {},
    },
    "LiquidityConfigDetailed": {
        "required": {"depth_half", "kappa_min", "kappa_max"},
        "defaults": {},
        "class_factories": {},
    },
    "EmaBiasConfig": {
        "required": {"clamp_min", "clamp_max"},
        "defaults": {},
        "class_factories": {},
    },
    "VolumeSpikeConfig": {
        "required": {"cap_max", "sma_len", "eps"},
        "defaults": {},
        "class_factories": {},
    },
    "VolumeZScoreConfig": {
        "required": {"clip_sigma"},
        "defaults": {},
        "class_factories": {},
    },
    "LargeTradeImbalanceConfig": {
        "required": {"enabled", "window_ms", "min_trades", "eps", "use_notional"},
        "defaults": {},
        "class_factories": {},
    },
    "MacroSyncMetricsConfig": {
        "required": {
            "enabled",
            "time_diff_threshold_ms",
            "ttl_ms",
            "min_buffer_size",
            "window",
            "bin_ms",
            "max_gap_bins",
            "max_late_ms",
            "eps",
            "anchors",
            "align_mode",
            "anchor_update_from_ticks",
        },
        "defaults": {},
        "class_factories": {},
    },
    "VolatilityStateConfig": {
        "required": {"cap_max", "tick_floor", "division_eps"},
        "defaults": {},
        "class_factories": {},
    },
    "DepthImbalanceConfig": {
        "required": {"use_laplace_smoothing"},
        "defaults": {},
        "class_factories": {},
    },
    "DeltaPriceConfig": {
        "required": {"spike_filter_ms"},
        "defaults": {},
        "class_factories": {},
    },
    "FeatureDefaultsConfig": {
        "required": {"neutral_value", "zero_value", "correlation_default", "ms_per_sec"},
        "defaults": {},
        "class_factories": {},
    },
    "SpreadHealthGateConfig": {
        "required": {"enabled", "max_age_sec", "min_update_events", "min_trades_count", "window_sec"},
        "defaults": {},
        "class_factories": {},
    },
    "SpreadBpsConfig": {
        "required": {"health_gate"},
        "defaults": {},
        "class_factories": {},
    },
    "FeatureBoundsConfig": {
        "required": {"min", "max"},
        "defaults": {},
        "class_factories": {},
    },
    "FeatureSanityConfig": {
        "required": {"enabled", "nan_inf_behavior", "feature_bounds"},
        "defaults": {},
        "class_factories": {},
    },
    "MacroResidConfig": {
        "required": {"enabled", "beta_window", "mad_window", "winsor_percentile", "var_floor", "scale_floor", "clip", "neutral"},
        "defaults": {},
        "class_factories": {},
    },
    "AbsorptionProxyConfig": {
        "required": {"source", "window", "eps", "dp_cap_pct"},
        "defaults": {},
        "class_factories": {},
    },
    "AbsorptionDedupConfig": {
        "required": {"enabled", "window", "threshold"},
        "defaults": {},
        "class_factories": {},
    },
    "AbsorptionConfig": {
        "required": {"mode", "proxy", "dedup", "clip", "neutral"},
        "defaults": {},
        "class_factories": {},
    },
    "TacticianConfig": {
        "required": {"enabled", "timeframe_sec", "roc_period", "sensitivity", "min_bars"},
        "defaults": {},
        "class_factories": {},
    },
    "OperatorConfig": {
        "required": {"enabled", "timeframe_sec", "linreg_period", "adx_period", "sensitivity", "min_bars"},
        "defaults": {},
        "class_factories": {},
    },
    "StrategistConfig": {
        "required": {"enabled", "timeframe_sec", "sma_period", "sensitivity", "min_bars"},
        "defaults": {},
        "class_factories": {},
    },
    "PillarWeightsConfig": {
        "required": {"tactician", "operator", "strategist"},
        "defaults": {},
        "class_factories": {},
    },
    "PillarBackfillConfig": {
        "required": {"enabled", "d1_candles", "h4_candles", "m15_candles"},
        "defaults": {},
        "class_factories": {},
    },
    "PillarsConfig": {
        "required": {"enabled", "tactician", "operator", "strategist", "weights", "backfill"},
        "defaults": {},
        "class_factories": {},
    },
    "LegacyFeaturesLogConfig": {
        "required": {"mode", "sample_every_n"},
        "defaults": {},
        "class_factories": {},
    },
    "FeatureEngineeringDomainConfig": {
        "required": {
            "enabled_timeframes_sec",
            "enable_new_metrics",
            "trace_features",
            "legacy_features_log",
            "volume_input_mode",
            "ema",
            "volume",
            "volatility",
            "liquidity",
            "ema_bias",
            "volume_spike",
            "volume_zscore",
            "large_trade_imbalance",
            "volatility_state",
            "depth_imbalance",
            "delta_price",
            "macro_sync",
            "defaults",
            "readiness_registry",
            "warmup",
            "spread_bps",
            "feature_sanity",
            "macro_resid",
            "absorption",
            "pillars",
        },
        "defaults": {},
        "class_factories": {},
    },
}


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, object],
    class_factories: dict[str, str],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(class_factories)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay required"
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay optional/defaulted"
        )
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name, expected_factory_name in class_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is getattr(cm, expected_factory_name)


def test_current_aurora_config_loads_feature_engineering_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    fe = cfg.domains.feature_engineering
    assert fe.enable_new_metrics is True
    assert fe.volume_input_mode == "integrate"
    assert fe.enabled_timeframes_sec == [180, 300, 900]
    assert fe.legacy_features_log.mode == "full"
    assert fe.legacy_features_log.sample_every_n == 10
    assert fe.ema.period_short == 1
    assert fe.ema.period_long == 2
    assert fe.macro_sync.anchors == ["BTCUSDT", "ETHUSDT"]
    assert fe.readiness_registry is not None
    assert "macro_resid" in fe.readiness_registry.declared_keys
    assert fe.warmup is not None
    assert fe.warmup.enforcement_mode == "fail_fast"
    assert fe.warmup.degraded_allowed_strategies == ["md_amr"]
    assert fe.spread_bps is not None
    assert fe.spread_bps.health_gate.max_age_sec == 5.0
    assert fe.feature_sanity is not None
    assert fe.feature_sanity.feature_bounds["spread_bps"].max == 10000.0
    assert fe.macro_resid is not None
    assert fe.macro_resid.beta_window == 60
    assert fe.absorption is not None
    assert fe.absorption.mode == "full"
    assert fe.absorption.proxy is not None
    assert fe.absorption.proxy.dp_cap_pct == 0.02
    assert fe.pillars is not None
    assert fe.pillars.enabled is True
    assert fe.pillars.weights.tactician == 0.65
    assert fe.pillars.backfill.d1_candles == 200


def test_feature_engineering_facade_reexports_are_exact_identity() -> None:
    for name in CONTRACT_CASES:
        assert getattr(cm, name) is getattr(domain_fe, name)


def test_feature_engineering_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(
            getattr(cm, name),
            required=contract["required"],
            defaults=contract["defaults"],
            class_factories=contract["class_factories"],
        )


def test_feature_engineering_yaml_contract_fails_closed_on_invalid_ema_period_order(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["feature_engineering"]["ema"]["period_short"] = 3
    domains["feature_engineering"]["ema"]["period_long"] = 2
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "period_long" in message
    assert "period_short" in message


def test_feature_engineering_yaml_contract_fails_closed_on_forbidden_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["feature_engineering"]["unexpected_pkg6_field"] = True
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg6_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_feature_engineering_yaml_contract_fails_closed_on_missing_absorption_dp_cap(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    del domains["feature_engineering"]["absorption"]["proxy"]["dp_cap_pct"]
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "absorption.proxy.dp_cap_pct" in message
    assert "Field required" in message
