from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.strategies.mean_reversion as strategy_mr
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


CONTRACT_CASES = {
    "MRStrategyParamsConfig": {
        "required": {
            "bb_window",
            "bb_num_std",
            "atr_window",
            "rsi_window",
            "score_multiplier",
            "entry_threshold",
            "rsi_oversold",
            "rsi_overbought",
            "min_bars",
            "min_bb_width",
            "max_bb_width",
            "sl_atr_mult",
            "tp_to_mid",
            "cooldown_sec",
            "confidence_base",
            "confidence_bb_slope",
            "confidence_rsi_bonus",
        },
        "defaults": {},
        "optional_fields": set(),
    },
    "MRRegimeThresholdsConfig": {
        "required": {"high_vol_pct", "low_vol_pct"},
        "defaults": {},
        "optional_fields": set(),
    },
    "MRSqueezeExpansionVetoConfig": {
        "required": {
            "enabled",
            "squeeze_width_max",
            "post_squeeze_width_max",
            "expansion_ratio_min",
            "regimes",
            "sides",
        },
        "defaults": {},
        "optional_fields": set(),
    },
    "MRMomentumSeparationVetoConfig": {
        "required": {
            "enabled",
            "lookback_bars",
            "min_drift_pct",
            "min_current_bb_width",
            "regimes",
            "sides",
        },
        "defaults": {},
        "optional_fields": set(),
    },
    "MRMicrostructureVetoConfig": {
        "required": {
            "enabled",
            "tfi_ema_span",
            "tfi_adverse_threshold",
            "obi_confirm_enabled",
            "obi_adverse_threshold",
            "price_reaction_lookback_sec",
            "price_continuation_threshold",
            "absorption_wick_ratio_min",
            "absorption_rebound_threshold",
            "readiness_min_bars",
            "missing_policy",
        },
        "defaults": {},
        "optional_fields": set(),
    },
    "MRDirectionalBiasConfig": {
        "required": {
            "enabled",
            "base_long_threshold",
            "base_short_threshold",
            "funding_shift_magnitude",
            "funding_normalization_scale",
            "funding_deadband",
            "threshold_clamp_min",
            "threshold_clamp_max",
        },
        "defaults": {},
        "optional_fields": set(),
    },
    "MRStrategyOverrideConfig": {
        "required": {
            "bb_window",
            "bb_num_std",
            "min_bb_width",
            "flat_low_short_min_bb_width",
            "squeeze_expansion_veto",
            "momentum_separation_veto",
            "microstructure_veto",
            "directional_bias",
            "entry_threshold",
            "tp_to_mid",
            "sl_atr_mult",
            "cooldown_sec",
            "sl_buffer_pct",
            "tp_buffer_pct",
            "allowed_regimes",
            "confidence_base",
            "confidence_bb_slope",
            "confidence_rsi_bonus",
        },
        "defaults": {},
        "optional_fields": {
            "bb_window",
            "bb_num_std",
            "min_bb_width",
            "flat_low_short_min_bb_width",
            "squeeze_expansion_veto",
            "momentum_separation_veto",
            "microstructure_veto",
            "directional_bias",
            "entry_threshold",
            "tp_to_mid",
            "sl_atr_mult",
            "cooldown_sec",
            "sl_buffer_pct",
            "tp_buffer_pct",
            "allowed_regimes",
            "confidence_base",
            "confidence_bb_slope",
            "confidence_rsi_bonus",
        },
    },
    "MRAssetConfig": {
        "required": {
            "enabled",
            "leverage",
            "strategy",
            "liquidity_gate",
            "allowed_regimes",
            "position_mode",
        },
        "defaults": {},
        "optional_fields": {"leverage", "strategy", "liquidity_gate"},
    },
    "MRRegimeSizingConfig": {
        "required": {"sizing_mult", "stop_mult", "target_mult"},
        "defaults": {},
        "optional_fields": set(),
    },
    "MeanReversion1mStrategyConfig": {
        "required": {
            "mode",
            "enabled",
            "timeframe_sec",
            "strategy",
            "regime_thresholds",
            "assets",
            "regime_sizing",
            "allowed_regimes",
            "liquidity_gate",
            "execution",
            "safety_gates",
            "objective",
            "microstructure_veto",
            "directional_bias",
        },
        "defaults": {
            "allowed_sides": ["BUY", "SELL"],
            "decision": None,
        },
        "optional_fields": {
            "liquidity_gate",
            "objective",
            "microstructure_veto",
            "directional_bias",
            "decision",
        },
    },
}


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _annotation_includes(tp: Any, expected: Any) -> bool:
    return tp is expected or expected in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    optional_fields: set[str],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay required"
        )
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay optional/defaulted"
        )
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    shutil.copytree(src, dst_config_dir)


def _assign_mean_reversion(config_dir: Path) -> None:
    strategies_path = config_dir / "strategies.yaml"
    payload = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    assert isinstance(payload, dict)
    assignments = payload.setdefault("assignments", {})
    assert isinstance(assignments, dict)
    assigned = assignments.setdefault("BTCUSDT", [])
    assert isinstance(assigned, list)
    if "mean_reversion" not in assigned:
        assigned.append("mean_reversion")
    strategies_path.write_text(yaml.safe_dump(
        payload, sort_keys=False), encoding="utf-8")

    mr_profile_path = config_dir / "strategies" / "mean_reversion.yaml"
    mr_payload = yaml.safe_load(mr_profile_path.read_text(encoding="utf-8"))
    assert isinstance(mr_payload, dict)
    mr_root = mr_payload.setdefault("mean_reversion", {})
    assert isinstance(mr_root, dict)
    assets = mr_root.setdefault("assets", {})
    assert isinstance(assets, dict)
    btc = assets.setdefault("BTCUSDT", {})
    assert isinstance(btc, dict)
    btc["enabled"] = True
    mr_profile_path.write_text(yaml.safe_dump(
        mr_payload, sort_keys=False), encoding="utf-8")


def test_mean_reversion_facade_reexports_are_exact_identity() -> None:
    for name in CONTRACT_CASES:
        assert getattr(cm, name) is getattr(strategy_mr, name)


def test_mean_reversion_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    strategy_source = Path(strategy_mr.__file__).read_text(encoding="utf-8")

    for name in CONTRACT_CASES:
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py after Pkg 1 extraction."
        )
        assert strategy_source.count(marker) == 1, (
            f"{name} must have exactly one top-level definition in apps.reference.config.strategies.mean_reversion."
        )


def test_mean_reversion_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(
            getattr(cm, name),
            required=contract["required"],
            defaults=contract["defaults"],
            optional_fields=contract["optional_fields"],
        )


def test_mean_reversion_extraction_preserves_cross_model_annotations() -> None:
    override_fields = cm.MRStrategyOverrideConfig.model_fields
    assert _annotation_includes(
        override_fields["squeeze_expansion_veto"].annotation,
        cm.MRSqueezeExpansionVetoConfig,
    )
    assert _annotation_includes(
        override_fields["momentum_separation_veto"].annotation,
        cm.MRMomentumSeparationVetoConfig,
    )
    assert _annotation_includes(
        override_fields["microstructure_veto"].annotation,
        cm.MRMicrostructureVetoConfig,
    )
    assert _annotation_includes(
        override_fields["directional_bias"].annotation,
        cm.MRDirectionalBiasConfig,
    )

    asset_fields = cm.MRAssetConfig.model_fields
    assert _annotation_includes(
        asset_fields["leverage"].annotation, cm.LeverageConfig)
    assert _annotation_includes(
        asset_fields["strategy"].annotation, cm.MRStrategyOverrideConfig)
    assert _annotation_includes(
        asset_fields["liquidity_gate"].annotation, cm.LiquidityGateConfig)

    mr_fields = cm.MeanReversion1mStrategyConfig.model_fields
    assert mr_fields["strategy"].annotation is cm.MRStrategyParamsConfig
    assert mr_fields["regime_thresholds"].annotation is cm.MRRegimeThresholdsConfig
    assert _annotation_includes(
        mr_fields["assets"].annotation, cm.MRAssetConfig)
    assert _annotation_includes(
        mr_fields["regime_sizing"].annotation, cm.MRRegimeSizingConfig)
    assert mr_fields["execution"].annotation is cm.StrategyExecutionConfig
    assert mr_fields["safety_gates"].annotation is cm.SafetyGatesConfig
    assert _annotation_includes(
        mr_fields["objective"].annotation, cm.StrategyObjectiveConfig)
    assert _annotation_includes(
        mr_fields["microstructure_veto"].annotation, cm.MRMicrostructureVetoConfig)
    assert _annotation_includes(
        mr_fields["directional_bias"].annotation, cm.MRDirectionalBiasConfig)


def test_mean_reversion_rebuild_seam_accepts_execution_and_objective_blocks() -> None:
    cfg = cm.MeanReversion1mStrategyConfig(
        mode="shadow",
        enabled=True,
        timeframe_sec=300,
        strategy={
            "bb_window": 20,
            "bb_num_std": 2.0,
            "atr_window": 14,
            "rsi_window": 14,
            "score_multiplier": 1.0,
            "entry_threshold": 0.08,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "min_bars": 50,
            "min_bb_width": 0.01,
            "max_bb_width": 0.25,
            "sl_atr_mult": 1.5,
            "tp_to_mid": True,
            "cooldown_sec": 60,
            "confidence_base": 0.5,
            "confidence_bb_slope": 2.0,
            "confidence_rsi_bonus": 0.2,
        },
        regime_thresholds={
            "high_vol_pct": 0.02,
            "low_vol_pct": 0.005,
        },
        assets={
            "BTCUSDT": {
                "enabled": True,
                "leverage": None,
                "strategy": None,
                "liquidity_gate": None,
                "allowed_regimes": ["FLAT_LOW"],
                "position_mode": "STRICT",
            }
        },
        regime_sizing={
            "FLAT_LOW": {
                "sizing_mult": 1.0,
                "stop_mult": 1.0,
                "target_mult": 1.0,
            }
        },
        allowed_regimes=["FLAT_LOW"],
        liquidity_gate=None,
        execution={
            "entry_order_type": "LIMIT",
            "entry_tif": "GTX",
            "exit_order_type": None,
            "exit_tif": None,
            "exit_limit_ttl_ms": None,
            "gtx_retry_max": 0,
            "gtx_retry_offset_bps": 2.0,
        },
        safety_gates={
            "enabled": False,
            "system_stress_policy": "off",
            "stress_attenuation_factor": 0.5,
        },
        objective={
            "enabled": True,
            "regimes": {
                "FLAT_LOW": {
                    "weights": {"net_pnl": 1.0},
                    "multiplier": {
                        "m_min": 0.5,
                        "m_max": 1.5,
                        "lambda_scale": 1.0,
                        "penalty_center": 0.0,
                        "penalty_scale": 1.0,
                    },
                    "gate": {
                        "min_objective_score": 0.2,
                        "enforcement_mode": "OBSERVE",
                    },
                }
            },
        },
        microstructure_veto=None,
        directional_bias=None,
    )

    assert type(cfg.execution) is cm.StrategyExecutionConfig
    assert type(cfg.objective) is cm.StrategyObjectiveConfig


def test_assigned_mean_reversion_config_loads_extracted_contract(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _assign_mean_reversion(config_dir)

    cfg = ConfigLoader(config_dir=config_dir).load_config()
    mr = cfg.strategies.mean_reversion

    assert mr is not None
    assert type(mr) is cm.MeanReversion1mStrategyConfig
    assert type(mr.strategy) is cm.MRStrategyParamsConfig
    assert type(mr.regime_thresholds) is cm.MRRegimeThresholdsConfig
    assert type(next(iter(mr.assets.values()))) is cm.MRAssetConfig
    assert type(next(iter(mr.regime_sizing.values()))
                ) is cm.MRRegimeSizingConfig
    assert type(mr.execution) is cm.StrategyExecutionConfig
    assert type(mr.safety_gates) is cm.SafetyGatesConfig

    for asset in mr.assets.values():
        assert type(asset) is cm.MRAssetConfig
        if asset.strategy is not None:
            assert type(asset.strategy) is cm.MRStrategyOverrideConfig
            if asset.strategy.squeeze_expansion_veto is not None:
                assert type(
                    asset.strategy.squeeze_expansion_veto) is cm.MRSqueezeExpansionVetoConfig
            if asset.strategy.momentum_separation_veto is not None:
                assert type(
                    asset.strategy.momentum_separation_veto) is cm.MRMomentumSeparationVetoConfig
            if asset.strategy.microstructure_veto is not None:
                assert type(
                    asset.strategy.microstructure_veto) is cm.MRMicrostructureVetoConfig
            if asset.strategy.directional_bias is not None:
                assert type(
                    asset.strategy.directional_bias) is cm.MRDirectionalBiasConfig


def test_mean_reversion_runtime_import_smoke() -> None:
    handler_mod = importlib.import_module(
        "apps.reference.domains.strategies.runtimes.mean_reversion.handler"
    )
    plugin_mod = importlib.import_module(
        "apps.reference.domains.strategies.plugins.mean_reversion"
    )
    registry_mod = importlib.import_module(
        "apps.reference.domains.strategies.registry"
    )

    assert handler_mod.MeanReversion1mStrategyConfig is cm.MeanReversion1mStrategyConfig
    assert handler_mod.MRAssetConfig is cm.MRAssetConfig
    assert plugin_mod.MeanReversionHandler is handler_mod.MeanReversionHandler
    assert hasattr(registry_mod, "StrategyRuntime")


def test_mean_reversion_yaml_contract_fails_closed_on_forbidden_override_extra_field(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _assign_mean_reversion(config_dir)

    mr_profile_path = config_dir / "strategies" / "mean_reversion.yaml"
    mr_payload = yaml.safe_load(mr_profile_path.read_text(encoding="utf-8"))
    assert isinstance(mr_payload, dict)
    btc_strategy = mr_payload["mean_reversion"]["assets"]["BTCUSDT"].setdefault(
        "strategy", {})
    assert isinstance(btc_strategy, dict)
    btc_strategy["unexpected_pkg1_override_field"] = True
    mr_profile_path.write_text(yaml.safe_dump(
        mr_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=config_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg1_override_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_mean_reversion_yaml_contract_fails_closed_on_invalid_directional_bias_range(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _assign_mean_reversion(config_dir)

    mr_profile_path = config_dir / "strategies" / "mean_reversion.yaml"
    mr_payload = yaml.safe_load(mr_profile_path.read_text(encoding="utf-8"))
    assert isinstance(mr_payload, dict)
    mr_payload["mean_reversion"]["directional_bias"] = {
        "enabled": True,
        "base_long_threshold": 0.06,
        "base_short_threshold": 0.08,
        "funding_shift_magnitude": 0.02,
        "funding_normalization_scale": 0.0003,
        "funding_deadband": 0.1,
        "threshold_clamp_min": 0.12,
        "threshold_clamp_max": 0.10,
    }
    mr_profile_path.write_text(yaml.safe_dump(
        mr_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=config_dir).load_config()

    message = str(exc_info.value)
    assert "threshold_clamp_min" in message
    assert "threshold_clamp_max" in message
    assert "must be <" in message
