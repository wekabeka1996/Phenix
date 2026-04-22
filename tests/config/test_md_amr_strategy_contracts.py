from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.strategies.md_amr as strategy_md_amr
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


CONTRACT_CASES = {
    "MDAMRWeightsConfig": {
        "required": {"d1", "h1", "m30", "m15"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRLLMGateConfig": {
        "required": set(),
        "defaults": {
            "enabled": False,
            "sentiment_block_threshold": -0.8,
            "block_ttl_sec": 14400,
        },
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRAssetConfig": {
        "required": set(),
        "defaults": {
            "enabled": True,
            "cooldown_sec": 60,
            "position_mode": "STRICT",
            "allowed_regimes": None,
            "exit": None,
        },
        "default_factories": {},
        "optional_fields": {"allowed_regimes", "exit"},
    },
    "MDAMRReconciliationConfig": {
        "required": set(),
        "defaults": {
            "enabled": True,
            "interval_sec": 300,
            "drift_tolerance": 1e-6,
        },
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRConcentrationGuardConfig": {
        "required": set(),
        "defaults": {
            "enabled": False,
            "max_simultaneous_entries_per_bar": 2,
        },
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMROptunaConfig": {
        "required": set(),
        "defaults": {
            "oos_split_ratio": 0.30,
            "min_oos_calmar_ratio": 0.3,
        },
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRProgressTrackingConfig": {
        "required": {
            "early_progress_max_pct",
            "partial_progress_max_pct",
            "near_completion_max_pct",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRSetupQualityConfig": {
        "required": {
            "penetration_depth_full_scale",
            "channel_width_pct_full_scale",
            "volatility_z_full_penalty",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRHoldQualityConfig": {
        "required": {
            "expected_progress_grace_frac",
            "time_decay_weight",
            "progress_deficit_weight",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRContextValidityConfig": {
        "required": {
            "regime_confidence_floor",
            "regime_confidence_valid",
            "volatility_z_weakening",
            "volatility_z_invalid",
            "channel_width_pct_floor",
            "channel_width_pct_valid",
            "regime_weight",
            "volatility_weight",
            "structure_weight",
            "progress_alignment_weight",
            "valid_score_min",
            "invalid_score_max",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMREntryAnchorPersistenceConfig": {
        "required": {"storage_path"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "MDAMRExitConfig": {
        "required": {"sl_pct"},
        "defaults": {
            "tp_rr": 1.0,
            "regime_tpsl": None,
        },
        "default_factories": {},
        "optional_fields": {"regime_tpsl"},
    },
    "MDAMRStrategyConfig": {
        "required": {
            "enabled",
            "type",
            "description",
            "timeframe_sec",
            "channel_window_bars",
            "atr_window",
            "atr_stats_window",
            "hysteresis_mult",
            "threshold_z",
            "volatility_dampening_factor",
            "thr_base",
            "thr_floor",
            "alpha",
            "conf_min",
            "hold_edge_min",
            "target_approach_pct",
            "max_hold_bars",
            "atr_zscore_clamp",
            "atr_std_floor_pct",
            "fee_bps",
            "slippage_buffer_bps",
            "scaleout_fraction",
            "scaleout_cost_model",
            "weights",
            "execution",
            "safety_gates",
            "progress_tracking",
            "setup_quality",
            "hold_quality",
            "context_validity",
            "entry_anchor_persistence",
        },
        "defaults": {
            "defer_ttl_sec": 60,
            "channel_robust_pct": 0.0,
            "objective": None,
        },
        "default_factories": {
            "llm_gate": cm.MDAMRLLMGateConfig,
            "reconciliation": cm.MDAMRReconciliationConfig,
            "concentration_guard": cm.MDAMRConcentrationGuardConfig,
            "optuna": cm.MDAMROptunaConfig,
            "assets": dict,
        },
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
    default_factories: dict[str, Any],
    optional_fields: set[str],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(default_factories)

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

    for name, expected_factory in default_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is expected_factory

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


def _first_asset(md_amr_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assets = md_amr_data["md_amr"]["assets"]
    assert isinstance(assets, dict) and assets
    symbol = next(iter(assets))
    asset = assets[symbol]
    assert isinstance(asset, dict)
    return symbol, asset


def test_md_amr_facade_reexports_are_exact_identity() -> None:
    for name in CONTRACT_CASES:
        assert getattr(cm, name) is getattr(strategy_md_amr, name)
    assert cm._MD_AMR_ALLOWED_REGIME_ALIASES is strategy_md_amr._MD_AMR_ALLOWED_REGIME_ALIASES
    assert cm._MD_AMR_ALLOWED_REGIMES is strategy_md_amr._MD_AMR_ALLOWED_REGIMES


def test_md_amr_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    strategy_source = Path(
        strategy_md_amr.__file__).read_text(encoding="utf-8")

    for name in CONTRACT_CASES:
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py after Pkg 2 extraction."
        )
        assert strategy_source.count(marker) == 1, (
            f"{name} must have exactly one top-level definition in apps.reference.config.strategies.md_amr."
        )


def test_md_amr_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(
            getattr(cm, name),
            required=contract["required"],
            defaults=contract["defaults"],
            default_factories=contract["default_factories"],
            optional_fields=contract["optional_fields"],
        )


def test_md_amr_extraction_preserves_cross_model_annotations() -> None:
    asset_fields = cm.MDAMRAssetConfig.model_fields
    assert _annotation_includes(
        asset_fields["exit"].annotation,
        cm.MDAMRExitConfig,
    )

    exit_fields = cm.MDAMRExitConfig.model_fields
    assert _annotation_includes(
        exit_fields["regime_tpsl"].annotation,
        cm.RegimeTpSlConfig,
    )

    strategy_fields = cm.MDAMRStrategyConfig.model_fields
    assert strategy_fields["weights"].annotation is cm.MDAMRWeightsConfig
    assert strategy_fields["execution"].annotation is cm.StrategyExecutionConfig
    assert strategy_fields["safety_gates"].annotation is cm.SafetyGatesConfig
    assert strategy_fields["llm_gate"].annotation is cm.MDAMRLLMGateConfig
    assert strategy_fields["reconciliation"].annotation is cm.MDAMRReconciliationConfig
    assert strategy_fields["concentration_guard"].annotation is cm.MDAMRConcentrationGuardConfig
    assert strategy_fields["progress_tracking"].annotation is cm.MDAMRProgressTrackingConfig
    assert strategy_fields["setup_quality"].annotation is cm.MDAMRSetupQualityConfig
    assert strategy_fields["hold_quality"].annotation is cm.MDAMRHoldQualityConfig
    assert strategy_fields["context_validity"].annotation is cm.MDAMRContextValidityConfig
    assert strategy_fields["entry_anchor_persistence"].annotation is cm.MDAMREntryAnchorPersistenceConfig
    assert strategy_fields["optuna"].annotation is cm.MDAMROptunaConfig
    assert _annotation_includes(
        strategy_fields["assets"].annotation,
        cm.MDAMRAssetConfig,
    )
    assert _annotation_includes(
        strategy_fields["objective"].annotation,
        cm.StrategyObjectiveConfig,
    )


def test_md_amr_rebuild_seam_accepts_execution_objective_and_regime_tpsl_blocks() -> None:
    cfg = cm.MDAMRStrategyConfig(
        enabled=True,
        type="md_amr_v1_2",
        description="contract test",
        timeframe_sec=900,
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
        execution={"entry_order_type": "LIMIT", "entry_tif": "GTX"},
        safety_gates={"enabled": False},
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
        assets={
            "BTCUSDT": {
                "enabled": True,
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

    asset = cfg.assets["BTCUSDT"]
    assert type(cfg.execution) is cm.StrategyExecutionConfig
    assert type(cfg.objective) is cm.StrategyObjectiveConfig
    assert type(asset) is cm.MDAMRAssetConfig
    assert asset.allowed_regimes == ["FLAT_LOW"]
    assert type(asset.exit) is cm.MDAMRExitConfig
    assert type(asset.exit.regime_tpsl) is cm.RegimeTpSlConfig


def test_current_aurora_config_loads_md_amr_extraction_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    md_amr = cfg.strategies.md_amr

    assert type(md_amr) is cm.MDAMRStrategyConfig
    assert type(md_amr.weights) is cm.MDAMRWeightsConfig
    assert type(md_amr.execution) is cm.StrategyExecutionConfig
    assert type(md_amr.safety_gates) is cm.SafetyGatesConfig
    assert type(md_amr.llm_gate) is cm.MDAMRLLMGateConfig
    assert type(md_amr.reconciliation) is cm.MDAMRReconciliationConfig
    assert type(md_amr.concentration_guard) is cm.MDAMRConcentrationGuardConfig
    assert type(md_amr.progress_tracking) is cm.MDAMRProgressTrackingConfig
    assert type(md_amr.setup_quality) is cm.MDAMRSetupQualityConfig
    assert type(md_amr.hold_quality) is cm.MDAMRHoldQualityConfig
    assert type(md_amr.context_validity) is cm.MDAMRContextValidityConfig
    assert type(
        md_amr.entry_anchor_persistence) is cm.MDAMREntryAnchorPersistenceConfig
    assert type(md_amr.optuna) is cm.MDAMROptunaConfig
    assert type(md_amr.objective) is cm.StrategyObjectiveConfig
    assert md_amr.execution.entry_order_type == "LIMIT"
    assert md_amr.llm_gate.block_ttl_sec == 14400
    assert md_amr.reconciliation.interval_sec == 300
    assert md_amr.concentration_guard.max_simultaneous_entries_per_bar == 2

    assert md_amr.assets
    first_asset = next(iter(md_amr.assets.values()))
    assert type(first_asset) is cm.MDAMRAssetConfig
    if first_asset.exit is not None:
        assert type(first_asset.exit) is cm.MDAMRExitConfig
        if first_asset.exit.regime_tpsl is not None:
            assert type(first_asset.exit.regime_tpsl) is cm.RegimeTpSlConfig


def test_md_amr_runtime_import_smoke() -> None:
    handler_mod = importlib.import_module(
        "apps.reference.domains.decision_making.md_amr_handler"
    )
    plugin_mod = importlib.import_module(
        "apps.reference.domains.strategies.plugins.md_amr"
    )
    registry_mod = importlib.import_module(
        "apps.reference.domains.strategies.registry"
    )

    assert handler_mod.MDAMRStrategyConfig is cm.MDAMRStrategyConfig
    assert plugin_mod.MDAMRHandler is handler_mod.MDAMRHandler
    assert hasattr(registry_mod, "StrategyRuntime")


def test_md_amr_yaml_contract_fails_closed_on_unknown_asset_regime(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    md_amr_path = cfg_dir / "strategies" / "md_amr.yaml"
    md_amr_data = yaml.safe_load(md_amr_path.read_text(encoding="utf-8"))
    _symbol, asset = _first_asset(md_amr_data)
    asset["allowed_regimes"] = ["FLAT_UP"]
    _write_yaml(md_amr_path, md_amr_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "allowed_regimes" in message
    assert "FLAT_UP" in message
    assert "Unknown md_amr allowed_regimes value" in message


def test_md_amr_yaml_contract_fails_closed_on_forbidden_asset_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    md_amr_path = cfg_dir / "strategies" / "md_amr.yaml"
    md_amr_data = yaml.safe_load(md_amr_path.read_text(encoding="utf-8"))
    _symbol, asset = _first_asset(md_amr_data)
    asset["unexpected_pkg2_asset_field"] = True
    _write_yaml(md_amr_path, md_amr_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg2_asset_field" in message
    assert "extra inputs are not permitted" in message.lower()
