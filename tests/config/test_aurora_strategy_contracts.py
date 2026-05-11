from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.strategies.aurora as strategy_aurora
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


CONTRACT_CASES = {
    "AuroraSideBiasConfig": {
        "required": {"penalty_factor", "window_sec", "target_ratio"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"penalty_factor", "window_sec", "target_ratio"},
    },
    "RegimeTpSlConfig": {
        "required": set(),
        "defaults": {
            "enabled": False,
            "mode": "pct_mult",
            "sl_k_atr": None,
            "rr_by_regime": None,
            "min_sl_pct": 0.003,
            "max_sl_pct": 0.06,
            "min_tp_rr": 0.3,
            "max_tp_rr": 3.0,
            "min_dist_bps": 15,
        },
        "default_factory_values": {
            "sl_mult": {"DEFAULT": 1.0},
            "tp_mult": {"DEFAULT": 1.0},
        },
        "optional_fields": {"sl_k_atr", "rr_by_regime"},
    },
    "AuroraExitConfig": {
        "required": {"sl_pct", "max_hold_sec", "regime_tpsl"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"sl_pct", "max_hold_sec", "regime_tpsl"},
    },
    "AuroraTakeProfitConfig": {
        "required": {"tp_low_ratio", "tp_high_ratio", "partial_exit_pct"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"tp_low_ratio", "tp_high_ratio", "partial_exit_pct"},
    },
    "AuroraTrailingStopConfig": {
        "required": {
            "enabled",
            "activation_pct",
            "trail_pct",
            "trail_atr_mult",
            "min_update_interval_sec",
        },
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {
            "enabled",
            "activation_pct",
            "trail_pct",
            "trail_atr_mult",
            "min_update_interval_sec",
        },
    },
    "AuroraExecutionConfig": {
        "required": {"order_type", "post_only", "max_slippage_bps"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"order_type", "post_only", "max_slippage_bps"},
    },
    "EmaClampConfig": {
        "required": {"enabled", "clamp_min", "clamp_max"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"clamp_min", "clamp_max"},
    },
    "SignalThresholdConfig": {
        "required": {"enabled", "value"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"value"},
    },
    "MaxRiskScoreConfig": {
        "required": {"enabled", "value"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"value"},
    },
    "VolatilityEntryConfig": {
        "required": {"enabled", "regime_multipliers"},
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": set(),
    },
    "AuroraInstrumentConfig": {
        "required": {
            "enabled",
            "weights",
            "side_bias",
            "position_mode",
            "leverage",
            "regime_thresholds",
            "regime_sizing",
            "exit",
            "take_profit",
            "trailing_stop",
            "signal_threshold",
            "max_risk_score",
            "cooldown_sec",
            "allowed_regimes",
            "scoring_version",
            "feature_neutrals",
            "essential_features",
            "liquidity_gate",
            "holding_period",
            "reentry_cooldown_sec",
            "timeframe_sec",
            "volatility_entry_logic",
        },
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {
            "weights",
            "side_bias",
            "position_mode",
            "leverage",
            "regime_thresholds",
            "regime_sizing",
            "exit",
            "take_profit",
            "trailing_stop",
            "signal_threshold",
            "max_risk_score",
            "cooldown_sec",
            "allowed_regimes",
            "scoring_version",
            "feature_neutrals",
            "essential_features",
            "liquidity_gate",
            "holding_period",
            "reentry_cooldown_sec",
            "timeframe_sec",
            "volatility_entry_logic",
        },
    },
    "StrategyExecutionConfig": {
        "required": {
            "entry_order_type",
            "entry_tif",
            "exit_order_type",
            "exit_tif",
            "exit_limit_ttl_ms",
            "gtx_retry_max",
            "gtx_retry_offset_bps",
        },
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {
            "entry_tif",
            "exit_order_type",
            "exit_tif",
            "exit_limit_ttl_ms",
        },
    },
    "AuroraStrategyConfig": {
        "required": {
            "enabled",
            "type",
            "description",
            "timeframe_sec",
            "execution",
            "safety_gates",
            "shadow_mode_enabled",
            "objective",
            "decision",
            "assets",
        },
        "defaults": {},
        "default_factory_values": {},
        "optional_fields": {"objective"},
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
    default_factory_values: dict[str, Any],
    optional_fields: set[str],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(default_factory_values)

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

    for name, expected_value in default_factory_values.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is not None
        assert field_info.default_factory() == expected_value

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _resolve_aurora_low_vol_rr(
    asset_cfg: cm.AuroraInstrumentConfig,
) -> tuple[float, str, float, float]:
    regime_tpsl = asset_cfg.exit.regime_tpsl
    assert regime_tpsl is not None
    assert regime_tpsl.mode == "pct_mult"

    tp_mult_map = dict(regime_tpsl.tp_mult)
    tp_mult_source = "LOW_VOLATILITY" if "LOW_VOLATILITY" in tp_mult_map else "DEFAULT"
    tp_low_ratio = float(asset_cfg.take_profit.tp_low_ratio)
    tp_mult = float(tp_mult_map[tp_mult_source])
    min_tp_rr = float(regime_tpsl.min_tp_rr)
    max_tp_rr = float(regime_tpsl.max_tp_rr)
    effective_rr = min(max(tp_low_ratio * tp_mult, min_tp_rr), max_tp_rr)
    return effective_rr, tp_mult_source, tp_low_ratio, tp_mult


def test_aurora_facade_reexports_are_exact_identity() -> None:
    for name in CONTRACT_CASES:
        assert getattr(cm, name) is getattr(strategy_aurora, name)
    assert cm.CANONICAL_WEIGHT_KEYS is strategy_aurora.CANONICAL_WEIGHT_KEYS


def test_aurora_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    strategy_source = Path(
        strategy_aurora.__file__).read_text(encoding="utf-8")

    for name in CONTRACT_CASES:
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py after Pkg 4 extraction."
        )
        assert strategy_source.count(marker) == 1, (
            f"{name} must have exactly one top-level definition in apps.reference.config.strategies.aurora."
        )


def test_aurora_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(
            getattr(cm, name),
            required=contract["required"],
            defaults=contract["defaults"],
            default_factory_values=contract["default_factory_values"],
            optional_fields=contract["optional_fields"],
        )


def test_aurora_weight_key_constant_contract_is_preserved() -> None:
    expected = {
        "obi",
        "tfi",
        "delta_price",
        "ema_bias",
        "volume_spike",
        "volatility_state",
        "depth_imbalance",
        "macro_sync",
        "macro_resid",
        "absorption",
    }
    assert cm.CANONICAL_WEIGHT_KEYS == expected


def test_aurora_extraction_preserves_cross_model_annotations() -> None:
    exit_fields = cm.AuroraExitConfig.model_fields
    assert _annotation_includes(
        exit_fields["regime_tpsl"].annotation,
        cm.RegimeTpSlConfig,
    )

    instrument_fields = cm.AuroraInstrumentConfig.model_fields
    assert _annotation_includes(
        instrument_fields["side_bias"].annotation,
        cm.AuroraSideBiasConfig,
    )
    assert _annotation_includes(
        instrument_fields["leverage"].annotation,
        cm.AuroraLeverageOverrideConfig,
    )
    assert _annotation_includes(
        instrument_fields["exit"].annotation,
        cm.AuroraExitConfig,
    )
    assert _annotation_includes(
        instrument_fields["take_profit"].annotation,
        cm.AuroraTakeProfitConfig,
    )
    assert _annotation_includes(
        instrument_fields["trailing_stop"].annotation,
        cm.AuroraTrailingStopConfig,
    )
    assert _annotation_includes(
        instrument_fields["signal_threshold"].annotation,
        cm.SignalThresholdConfig,
    )
    assert _annotation_includes(
        instrument_fields["max_risk_score"].annotation,
        cm.MaxRiskScoreConfig,
    )
    assert _annotation_includes(
        instrument_fields["liquidity_gate"].annotation,
        cm.LiquidityGateConfig,
    )
    assert _annotation_includes(
        instrument_fields["holding_period"].annotation,
        cm.HoldingPeriodConfig,
    )
    assert _annotation_includes(
        instrument_fields["volatility_entry_logic"].annotation,
        cm.VolatilityEntryConfig,
    )

    strategy_fields = cm.AuroraStrategyConfig.model_fields
    assert strategy_fields["execution"].annotation is cm.StrategyExecutionConfig
    assert strategy_fields["safety_gates"].annotation is cm.SafetyGatesConfig
    assert strategy_fields["decision"].annotation is cm.DecisionConfig
    assert _annotation_includes(
        strategy_fields["objective"].annotation,
        cm.StrategyObjectiveConfig,
    )
    assert _annotation_includes(
        strategy_fields["assets"].annotation,
        cm.AuroraInstrumentConfig,
    )


def test_aurora_strategy_config_accepts_execution_and_objective_from_strategy_yaml() -> None:
    aurora_payload = _load_yaml(
        CONFIG_DIR / "strategies" / "aurora.yaml")["aurora"]
    cfg = cm.AuroraStrategyConfig(**aurora_payload)

    assert type(cfg.execution) is cm.StrategyExecutionConfig
    assert type(cfg.safety_gates) is cm.SafetyGatesConfig
    assert type(cfg.decision) is cm.DecisionConfig
    assert type(cfg.objective) is cm.StrategyObjectiveConfig
    assert cfg.assets
    first_asset = next(iter(cfg.assets.values()))
    assert type(first_asset) is cm.AuroraInstrumentConfig


def test_aurora_low_vol_rr_contract_clears_low_vol_cost_floor_for_active_symbols() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    min_rr = cfg.domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr

    active_symbols = sorted(
        symbol
        for symbol, strategy_ids in cfg.strategies_registry.assignments.items()
        if isinstance(strategy_ids, list) and "aurora" in strategy_ids
    )
    assert active_symbols

    for symbol in active_symbols:
        asset_cfg = cfg.strategies.aurora.assets[symbol]
        regime_tpsl = asset_cfg.exit.regime_tpsl
        assert regime_tpsl is not None
        assert regime_tpsl.mode == "pct_mult"
        assert "LOW_VOLATILITY" in regime_tpsl.tp_mult

        effective_rr, tp_mult_source, tp_low_ratio, tp_mult = _resolve_aurora_low_vol_rr(
            asset_cfg)
        assert tp_mult_source == "LOW_VOLATILITY"
        assert effective_rr >= min_rr, (
            f"{symbol} low-vol effective RR {effective_rr:.6f} must clear "
            f"domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr={min_rr:.6f}; "
            f"tp_low_ratio={tp_low_ratio}, tp_mult={tp_mult}"
        )


def test_prior_strategy_rebuild_seams_survive_strategy_execution_and_regime_tpsl_move() -> None:
    llm = cm.LLMMicrostructureStrategyConfig(
        enabled=True,
        type="external_intent",
        description="contract test",
        timeframe_sec=60,
        pending_entry_ttl_ms=120000,
        execution={
            "entry_order_type": "LIMIT",
            "entry_tif": "GTC",
            "exit_order_type": "MARKET",
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
    )
    assert type(llm.execution) is cm.StrategyExecutionConfig

    mr = cm.MeanReversion1mStrategyConfig(
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
    assert type(mr.execution) is cm.StrategyExecutionConfig
    assert type(mr.objective) is cm.StrategyObjectiveConfig

    md_amr = cm.MDAMRStrategyConfig(
        enabled=True,
        type="md_amr_v1_2",
        description="contract test",
        timeframe_sec=900,
        defer_ttl_sec=60,
        channel_window_bars=12,
        channel_robust_pct=0.05,
        atr_window=14,
        atr_stats_window=64,
        hysteresis_mult=1.2,
        threshold_z=2.2,
        volatility_dampening_factor=0.5,
        thr_base=0.55,
        thr_floor=0.10,
        alpha=0.25,
        conf_min=0.22,
        hold_edge_min=-0.5,
        target_approach_pct=0.0,
        max_hold_bars=16,
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        fee_bps=4.0,
        slippage_buffer_bps=2.0,
        scaleout_fraction=0.5,
        scaleout_cost_model="round_trip",
        weights={"d1": 0.35, "h1": 0.30, "m30": 0.20, "m15": 0.15},
        execution={
            "entry_order_type": "LIMIT",
            "entry_tif": "GTX",
            "exit_order_type": "MARKET",
            "exit_tif": None,
            "exit_limit_ttl_ms": None,
            "gtx_retry_max": 2,
            "gtx_retry_offset_bps": 2.0,
        },
        safety_gates={
            "enabled": False,
            "system_stress_policy": "off",
            "stress_attenuation_factor": 0.5,
        },
        llm_gate={
            "enabled": False,
            "sentiment_block_threshold": -0.8,
            "block_ttl_sec": 14400,
        },
        reconciliation={
            "enabled": True,
            "interval_sec": 300,
            "drift_tolerance": 1.0e-6,
        },
        concentration_guard={
            "enabled": True,
            "max_simultaneous_entries_per_bar": 2,
        },
        progress_tracking={
            "early_progress_max_pct": 0.25,
            "partial_progress_max_pct": 0.70,
            "near_completion_max_pct": 1.00,
        },
        setup_quality={
            "penetration_depth_full_scale": 0.50,
            "channel_width_pct_full_scale": 1.00,
            "volatility_z_full_penalty": 3.00,
        },
        hold_quality={
            "expected_progress_grace_frac": 0.25,
            "time_decay_weight": 0.35,
            "progress_deficit_weight": 0.45,
        },
        context_validity={
            "regime_confidence_floor": 0.35,
            "regime_confidence_valid": 0.60,
            "volatility_z_weakening": 1.50,
            "volatility_z_invalid": 3.00,
            "channel_width_pct_floor": 0.10,
            "channel_width_pct_valid": 1.00,
            "regime_weight": 0.35,
            "volatility_weight": 0.20,
            "structure_weight": 0.20,
            "progress_alignment_weight": 0.25,
            "valid_score_min": 0.70,
            "invalid_score_max": 0.35,
        },
        entry_anchor_persistence={
            "storage_path": "ops/restore/md_amr_entry_anchor_state_v1.json"
        },
        optuna={
            "oos_split_ratio": 0.3,
            "min_oos_calmar_ratio": 0.3,
        },
        assets={
            "BTCUSDT": {
                "enabled": True,
                "cooldown_sec": 60,
                "position_mode": "STRICT",
                "allowed_regimes": ["low_flat"],
                "exit": {
                    "sl_pct": 0.01,
                    "tp_rr": 1.5,
                    "regime_tpsl": {"enabled": True},
                },
            }
        },
        objective={
            "enabled": True,
            "regimes": {
                "FLAT_LOW": {
                    "weights": {"risk": 1.0},
                    "multiplier": {
                        "m_min": 0.1,
                        "m_max": 1.0,
                        "lambda_scale": 1.0,
                        "penalty_center": -5.0,
                        "penalty_scale": 2.5,
                    },
                    "gate": {
                        "min_objective_score": 0.1,
                        "enforcement_mode": "OBSERVE",
                    },
                }
            },
        },
    )

    asset = md_amr.assets["BTCUSDT"]
    assert type(md_amr.execution) is cm.StrategyExecutionConfig
    assert type(md_amr.objective) is cm.StrategyObjectiveConfig
    assert type(asset.exit.regime_tpsl) is cm.RegimeTpSlConfig


def test_current_aurora_config_loads_aurora_extraction_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    aurora = cfg.strategies.aurora

    assert aurora is not None
    assert type(aurora) is cm.AuroraStrategyConfig
    assert type(aurora.execution) is cm.StrategyExecutionConfig
    assert type(aurora.safety_gates) is cm.SafetyGatesConfig
    assert type(aurora.decision) is cm.DecisionConfig
    assert type(aurora.objective) is cm.StrategyObjectiveConfig

    btc = aurora.assets["BTCUSDT"]
    assert type(btc) is cm.AuroraInstrumentConfig
    if btc.side_bias is not None:
        assert type(btc.side_bias) is cm.AuroraSideBiasConfig
    if btc.leverage is not None:
        assert type(btc.leverage) is cm.AuroraLeverageOverrideConfig
    if btc.exit is not None:
        assert type(btc.exit) is cm.AuroraExitConfig
        if btc.exit.regime_tpsl is not None:
            assert type(btc.exit.regime_tpsl) is cm.RegimeTpSlConfig
    if btc.take_profit is not None:
        assert type(btc.take_profit) is cm.AuroraTakeProfitConfig
    if btc.trailing_stop is not None:
        assert type(btc.trailing_stop) is cm.AuroraTrailingStopConfig
    if btc.signal_threshold is not None:
        assert type(btc.signal_threshold) is cm.SignalThresholdConfig
    if btc.max_risk_score is not None:
        assert type(btc.max_risk_score) is cm.MaxRiskScoreConfig
    if btc.liquidity_gate is not None:
        assert type(btc.liquidity_gate) is cm.LiquidityGateConfig
    if btc.holding_period is not None:
        assert type(btc.holding_period) is cm.HoldingPeriodConfig
    if btc.volatility_entry_logic is not None:
        assert type(btc.volatility_entry_logic) is cm.VolatilityEntryConfig


def test_direct_runtime_consumers_receive_extracted_aurora_types() -> None:
    import logging

    from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver
    from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM

    cfg = ConfigLoader(CONFIG_DIR).load_config()

    resolver = DMConfigResolver(
        config=cfg,
        strategies_registry=cfg.strategies_registry,
        arb_signal_buffer={},
        arb_window_winner={},
        flip_global_enabled=False,
        logger=logging.getLogger("aurora-contract-test"),
    )
    resolved = resolver.get_aurora_instrument_cfg("BTCUSDT")
    assert type(resolved) is cm.AuroraInstrumentConfig

    manage = ManageFlowFSM(config=cfg)
    manage.symbol = "BTCUSDT"
    instr_cfg = manage._get_aurora_instr_cfg()
    assert type(instr_cfg) is cm.AuroraInstrumentConfig


def test_aurora_runtime_import_smoke() -> None:
    config_resolver_mod = importlib.import_module(
        "apps.reference.domains.decision_making.core.config_resolver"
    )
    handler_mod = importlib.import_module(
        "apps.reference.domains.strategies.runtimes.aurora.handler"
    )
    manage_mod = importlib.import_module(
        "apps.reference.domains.execution_position.flows.manage.fsm_manage"
    )
    plugin_mod = importlib.import_module(
        "apps.reference.domains.strategies.plugins.aurora_builtin"
    )
    registry_mod = importlib.import_module(
        "apps.reference.domains.strategies.registry"
    )

    assert hasattr(config_resolver_mod, "DMConfigResolver")
    assert hasattr(handler_mod, "AuroraHandler")
    assert hasattr(manage_mod, "ManageFlowFSM")
    assert hasattr(plugin_mod, "AuroraBuiltinPlugin")
    assert hasattr(registry_mod, "StrategyRuntime")


def test_aurora_yaml_contract_fails_closed_on_forbidden_asset_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    aurora_path = cfg_dir / "strategies" / "aurora.yaml"
    aurora_data = _load_yaml(aurora_path)
    assets = aurora_data["aurora"]["assets"]
    assert isinstance(assets, dict) and assets
    first_asset = next(iter(assets.values()))
    assert isinstance(first_asset, dict)
    first_asset["unexpected_pkg4_asset_field"] = True
    _write_yaml(aurora_path, aurora_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg4_asset_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_aurora_root_tpsl_ssot_validator_still_fails_closed_on_missing_preflight_backoff_ms(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    trading_data = _load_yaml(trading_path)
    trading_data["trading"]["execution"]["preflight_backoff_ms"] = None
    _write_yaml(trading_path, trading_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "preflight_backoff_ms" in message
    assert "TP/SL preflight backoff" in message


def test_aurora_root_tpsl_ssot_validator_fails_closed_on_low_vol_default_fallback(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    aurora_path = cfg_dir / "strategies" / "aurora.yaml"
    aurora_data = _load_yaml(aurora_path)
    eth_tp_mult = aurora_data["aurora"]["assets"]["ETHUSDT"]["exit"]["regime_tpsl"]["tp_mult"]
    assert isinstance(eth_tp_mult, dict)
    eth_tp_mult.pop("LOW_VOLATILITY", None)
    _write_yaml(aurora_path, aurora_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "ETHUSDT" in message
    assert "domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr" in message
    assert "DEFAULT" in message
    assert "low-vol effective RR" in message


def test_aurora_objective_regime_coverage_negative_fixture_still_raises(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    strategies_registry = _load_yaml(cfg_dir / "strategies.yaml")
    assignments = strategies_registry.get("assignments", {})
    assert isinstance(assignments, dict)

    aurora_path = cfg_dir / "strategies" / "aurora.yaml"
    aurora_wrapper = _load_yaml(aurora_path)
    aurora_cfg = aurora_wrapper["aurora"]
    assets = aurora_cfg["assets"]
    objective_regimes = aurora_cfg["objective"]["regimes"]

    expected_regimes: set[str] = set()
    for symbol, strategy_ids in assignments.items():
        if not isinstance(strategy_ids, list) or "aurora" not in strategy_ids:
            continue
        asset = assets.get(symbol)
        if not isinstance(asset, dict) or not asset.get("enabled"):
            continue
        expected_regimes.update(
            str(regime).strip().upper()
            for regime in asset.get("allowed_regimes", [])
            if str(regime).strip()
        )

    removed_regime = next(
        regime for regime in sorted(expected_regimes) if regime in objective_regimes
    )
    objective_regimes.pop(removed_regime)
    _write_yaml(aurora_path, aurora_wrapper)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "objective regime coverage invalid for assigned symbols" in message
    assert f"aurora:missing_objective_regimes={removed_regime}" in message
