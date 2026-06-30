import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.domains.decision_making as domain_dm
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")
ARTIFACT = (
    Path(__file__).resolve().parent
    / "_artifacts"
    / "decision_making_contract.generated.json"
)


@pytest.fixture(scope="module")
def frozen_manifest() -> dict[str, Any]:
    assert ARTIFACT.exists(), (
        f"Frozen decision_making contract not found at {ARTIFACT}. "
        "Regenerate only when the roadmap explicitly authorizes a package contract update."
    )
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _serialize_default(field_info: Any) -> str:
    if field_info.is_required():
        return repr("<required>")

    default = field_info.default
    if isinstance(default, list):
        return "list"
    if isinstance(default, dict):
        return "dict"
    if isinstance(default, set):
        return type(default).__name__
    return repr(default)


def _serialize_default_factory(field_info: Any) -> str | None:
    if field_info.default_factory is None:
        return None
    return field_info.default_factory.__name__


def _assert_model_contract(model_cls: type, snapshot: dict[str, Any]) -> None:
    fields = model_cls.model_fields

    assert model_cls.model_config.get("extra") == snapshot["extra"]
    assert set(fields) == set(snapshot["fields"])

    for field_name, expected in snapshot["fields"].items():
        field_info = fields[field_name]
        assert field_info.is_required() is expected["required"], (
            f"{model_cls.__name__}.{field_name} required drift"
        )
        assert _serialize_default(field_info) == expected["default"], (
            f"{model_cls.__name__}.{field_name} default drift"
        )
        assert _serialize_default_factory(field_info) == expected["default_factory"], (
            f"{model_cls.__name__}.{field_name} default_factory drift"
        )


def test_decision_making_facade_reexports_are_exact_identity(
    frozen_manifest: dict[str, Any],
) -> None:
    for name in frozen_manifest:
        assert getattr(cm, name) is getattr(domain_dm, name)


def test_decision_making_extraction_preserves_field_contract(
    frozen_manifest: dict[str, Any],
) -> None:
    for name, snapshot in frozen_manifest.items():
        _assert_model_contract(getattr(cm, name), snapshot)


def test_current_aurora_config_loads_decision_making_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    domains = yaml.safe_load(
        (CONFIG_DIR / "domains.yaml").read_text(encoding="utf-8"))
    expected_max_regime_confidence_by_regime = (
        domains["decision_making"]["directional_sanity"]["max_regime_confidence_by_regime"]
    )
    low_vol_thresholds = domains["decision_making"]["low_vol_cost_floor_gate"]["thresholds"]

    dm_domain = cfg.domains.decision_making
    assert dm_domain.entry_plan.enabled is True
    assert dm_domain.entry_plan.atr_period == 14
    assert dm_domain.entry_plan.entry_k_atr == 0.3
    assert dm_domain.entry_plan.sl_k_atr == 1.5
    assert dm_domain.entry_plan.tp_k_atr == 2.0
    assert dm_domain.entry_plan.structural_stop_enabled is False
    assert dm_domain.entry_plan.min_stop_bps == 15
    assert dm_domain.flip.enabled is False
    assert dm_domain.risk_skew.max_skew_sec == 5
    assert dm_domain.arming.require_regime_warmup is True
    assert dm_domain.directional_sanity.min_regime_confidence == 0.35
    assert dm_domain.directional_sanity.min_regime_confidence_by_regime == {
        "DEFAULT": 0.35,
        "TREND_UP": 0.20,
        "TREND_DOWN": 0.20,
    }
    assert dm_domain.directional_sanity.max_regime_confidence_by_regime == expected_max_regime_confidence_by_regime
    assert dm_domain.low_vol_cost_floor_gate.enabled is False
    assert dm_domain.low_vol_cost_floor_gate.decision_chain_enabled is False
    assert dm_domain.low_vol_cost_floor_gate.enforce_in_modes == [
        "testnet",
        "hybrid_live_data_testnet_exec",
    ]
    assert dm_domain.low_vol_cost_floor_gate.observe_only_in_modes == [
        "live",
        "production",
    ]
    assert dm_domain.low_vol_cost_floor_gate.thresholds.min_regime_confidence_by_regime == low_vol_thresholds[
        "min_regime_confidence_by_regime"]
    assert dm_domain.low_vol_cost_floor_gate.thresholds.min_regime_confidence_overrides_by_strategy_symbol == low_vol_thresholds[
        "min_regime_confidence_overrides_by_strategy_symbol"]
    assert dm_domain.low_vol_cost_floor_gate.thresholds.min_direction_confidence_by_regime == low_vol_thresholds[
        "min_direction_confidence_by_regime"]
    assert dm_domain.low_vol_cost_floor_gate.thresholds.min_direction_confidence_overrides_by_strategy_symbol == low_vol_thresholds[
        "min_direction_confidence_overrides_by_strategy_symbol"]
    assert dm_domain.low_vol_cost_floor_gate.direction_confidence.required is True
    assert dm_domain.low_vol_cost_floor_gate.direction_confidence.missing_policy == "fail_closed"
    assert set(dm_domain.low_vol_cost_floor_gate.direction_confidence.allowed_sources) == {
        "strategy_confidence",
        "signal_score",
        "final_score",
    }
    assert dm_domain.price_motion_sanity.pm_norm_clip_abs == 10.0
    assert dm_domain.neocortex_enforcement_mode == "shadow"
    assert set(dm_domain.degraded_context_contracts_by_strategy) == {
        "aurora",
        "mean_reversion",
        "md_amr",
        "alpha_ta_ensemble",
    }

    fe = cfg.domains.feature_engineering
    assert fe.readiness_registry is not None
    assert "macro_resid" in fe.readiness_registry.declared_keys
    assert fe.warmup is not None
    assert fe.warmup.enforcement_mode == "fail_fast"
    assert fe.warmup.degraded_allowed_strategies == ["md_amr"]

    aurora = cfg.strategies.aurora
    assert aurora.safety_gates.enabled is True
    assert aurora.safety_gates.system_stress_policy == "attenuate"
    assert aurora.safety_gates.stress_attenuation_factor == 0.5
    assert aurora.safety_gates.regime_confidence is not None
    assert aurora.safety_gates.regime_confidence.max_by_symbol_regime_side is not None
    eth_side_override = aurora.safety_gates.regime_confidence.max_by_symbol_regime_side[
        "ETHUSDT"]["TREND_DOWN"]
    assert eth_side_override.BUY is None
    assert eth_side_override.SELL == domain_dm.RegimeConfidenceMaxSideOverrideConfig(
        enabled=False,
        threshold=None,
    )
    assert aurora.safety_gates.regime_confidence.min_by_regime is None
    assert aurora.safety_gates.regime_confidence.min_by_symbol is None
    assert aurora.safety_gates.regime_confidence.max_by_regime is None
    assert aurora.safety_gates.regime_confidence.max_by_symbol is None
    assert aurora.safety_gates.regime_confidence.max_by_regime_side is None
    assert "DOGEUSDT" not in aurora.safety_gates.regime_confidence.max_by_symbol_regime_side
    assert cfg.strategies.md_amr.safety_gates.regime_confidence is None
    assert cfg.strategies.mean_reversion.safety_gates.regime_confidence is None
    assert cfg.strategies.llm_microstructure.safety_gates.regime_confidence is None
    assert dm_domain.directional_sanity.nrr026_enabled is True
    assert aurora.assets["XRPUSDT"].enabled is True

    decision = aurora.decision
    assert decision.testnet is not None
    assert decision.testnet.signal_threshold == 0.162
    assert decision.production is not None
    assert decision.production.signal_threshold == 0.162
    assert decision.signal_threshold == 0.162
    assert decision.mean_reversion is None
    assert decision.scoring_version == "quadratic"
    assert decision.decision_geometry is not None
    assert decision.decision_geometry.admission_mode == "linear"
    assert decision.decision_geometry.sizing_mode == "soft_power"
    assert decision.scoring_engine is not None
    assert decision.scoring_engine.shield_enabled is True
    assert decision.scoring_engine.danger_zone_shield.vol_threshold == 0.98
    assert (
        decision.scoring_engine.context_shield.regime_multipliers["HIGH_VOLATILITY"]
        == 0.85
    )
    assert decision.scoring_engine.memory_shield.unknown_threshold == 10
    assert decision.holding_period is not None
    assert decision.holding_period.enabled is True
    assert decision.holding_period.min_duration_sec == 900
    assert decision.gates is not None
    assert decision.gates.enabled is True
    assert decision.gates.anti_flat_sigma == 0.48
    assert decision.gates.motion_window_sec == 300

    assert cfg.instruments["SOLUSDT"].flip.enabled is True
    assert cfg.instruments["SOLUSDT"].flip.hysteresis_mult == 1.3
    assert cfg.instruments["BTCUSDT"].flip.enabled is True
    assert cfg.instruments["BTCUSDT"].flip.hysteresis_mult == 3.0


def test_directional_sanity_accepts_optional_per_regime_confidence_thresholds() -> None:
    cfg = domain_dm.DirectionalSanityConfig(
        enabled=True,
        min_abs_delta_price=0.0,
        min_confidence=0.0,
        min_regime_confidence=0.45,
        min_regime_confidence_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.52},
        hard_veto_consecutive_bars=2,
        consecutive_bars=1,
    )

    assert cfg.min_regime_confidence_by_regime == {
        "DEFAULT": 0.45,
        "TREND_UP": 0.52,
    }


def test_directional_sanity_accepts_optional_max_per_regime_confidence_thresholds() -> None:
    cfg = domain_dm.DirectionalSanityConfig(
        enabled=True,
        min_abs_delta_price=0.0,
        min_confidence=0.0,
        min_regime_confidence=0.45,
        min_regime_confidence_by_regime={"DEFAULT": 0.45, "TREND_UP": 0.52},
        max_regime_confidence_by_regime={"TREND_UP": 0.70, "TREND_DOWN": 0.65},
        hard_veto_consecutive_bars=2,
        consecutive_bars=1,
    )

    assert cfg.max_regime_confidence_by_regime == {
        "TREND_UP": 0.70,
        "TREND_DOWN": 0.65,
    }


def test_variant_b2_pre_restart_hardening_and_size_rebalance_contract() -> None:
    cfg = ConfigLoader(config_dir=CONFIG_DIR).load_config()

    aurora = cfg.strategies.aurora
    decision = aurora.decision
    dm_domain = cfg.domains.decision_making
    sidecar = cfg.domains.execution_position.position_policy_sidecar

    assert sidecar.mode.value == "enable"
    assert dm_domain.directional_sanity.nrr026_enabled is True

    assert decision.exit is not None
    assert decision.exit.signal_exit_enabled is False

    pyramiding = decision.pyramiding_policy
    assert pyramiding is not None
    assert pyramiding.enabled is True
    assert pyramiding.mode == "testnet_enforced"
    assert pyramiding.order_type == "LIMIT"
    assert pyramiding.max_adds_per_lifecycle == 1
    assert pyramiding.rules is not None
    assert len(pyramiding.rules) == 1
    rule = pyramiding.rules[0]
    assert rule.enabled is True
    assert rule.regimes == ["LOW_VOLATILITY"]
    assert rule.sides == ["SELL"]
    assert rule.symbols is None

    assert aurora.assets["BNBUSDT"].enabled is True
    assert aurora.assets["XRPUSDT"].enabled is True
    assert aurora.assets["SOLUSDT"].signal_threshold.enabled is True

    eth_side_override = aurora.safety_gates.regime_confidence.max_by_symbol_regime_side[
        "ETHUSDT"]["TREND_DOWN"]
    assert eth_side_override.BUY is None
    assert eth_side_override.SELL == domain_dm.RegimeConfidenceMaxSideOverrideConfig(
        enabled=False,
        threshold=None,
    )
    assert "DOGEUSDT" not in aurora.safety_gates.regime_confidence.max_by_symbol_regime_side
    assert "BNBUSDT" not in aurora.safety_gates.regime_confidence.max_by_symbol_regime_side
    assert "BTCUSDT" not in aurora.safety_gates.regime_confidence.max_by_symbol_regime_side

    enabled_assets = {
        symbol: asset
        for symbol, asset in aurora.assets.items()
        if asset.enabled
    }
    assert all(
        getattr(asset.position_mode, "value", asset.position_mode) == "STRICT"
        for asset in enabled_assets.values()
    )
    assert all(
        "MEAN_REVERSION" in list(asset.allowed_regimes or [])
        for asset in enabled_assets.values()
    )

    assert aurora.assets["BTCUSDT"].regime_sizing["LOW_VOLATILITY"] == 1.05
    assert aurora.assets["BTCUSDT"].regime_sizing["TREND_DOWN"] == 1.95
    assert aurora.assets["DOGEUSDT"].regime_sizing["TREND_DOWN"] == 1.625
    assert aurora.assets["ETHUSDT"].regime_sizing["TREND_UP"] == 1.3


def test_safety_gates_accepts_optional_strategy_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "min_by_regime": {
                "DEFAULT": 0.45,
                "TREND_UP": 0.65,
                "TREND_DOWN": 0.65,
            }
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.min_by_regime == {
        "DEFAULT": 0.45,
        "TREND_UP": 0.65,
        "TREND_DOWN": 0.65,
    }


def test_safety_gates_accepts_optional_strategy_symbol_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "min_by_regime": {
                "DEFAULT": 0.45,
                "TREND_UP": 0.65,
            },
            "min_by_symbol": {
                "XRPUSDT": {
                    "DEFAULT": 0.675,
                    "TREND_UP": 0.975,
                },
                "BTCUSDT": {
                    "DEFAULT": 0.55,
                    "TREND_UP": 0.70,
                },
            },
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.min_by_symbol == {
        "XRPUSDT": {
            "DEFAULT": 0.675,
            "TREND_UP": 0.975,
        },
        "BTCUSDT": {
            "DEFAULT": 0.55,
            "TREND_UP": 0.70,
        },
    }


def test_safety_gates_accepts_side_aware_strategy_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "min_by_regime_side": {
                "TREND_DOWN": {
                    "SELL": 0.62,
                }
            },
            "max_by_regime_side": {
                "TREND_DOWN": {
                    "SELL": {
                        "enabled": False,
                    }
                }
            },
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.min_by_regime_side is not None
    assert cfg.regime_confidence.min_by_regime_side["TREND_DOWN"].SELL == 0.62
    assert cfg.regime_confidence.max_by_regime_side is not None
    assert cfg.regime_confidence.max_by_regime_side["TREND_DOWN"].SELL is not None
    assert cfg.regime_confidence.max_by_regime_side["TREND_DOWN"].SELL.enabled is False


def test_safety_gates_accepts_side_aware_strategy_symbol_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "min_by_symbol_regime_side": {
                "ETHUSDT": {
                    "TREND_DOWN": {
                        "SELL": 0.79,
                    }
                }
            },
            "max_by_symbol_regime_side": {
                "ETHUSDT": {
                    "TREND_DOWN": {
                        "SELL": {
                            "enabled": True,
                            "threshold": 0.95,
                        }
                    }
                }
            },
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.min_by_symbol_regime_side is not None
    assert cfg.regime_confidence.min_by_symbol_regime_side["ETHUSDT"]["TREND_DOWN"].SELL == 0.79
    assert cfg.regime_confidence.max_by_symbol_regime_side is not None
    assert cfg.regime_confidence.max_by_symbol_regime_side["ETHUSDT"]["TREND_DOWN"].SELL is not None
    assert cfg.regime_confidence.max_by_symbol_regime_side[
        "ETHUSDT"]["TREND_DOWN"].SELL.threshold == 0.95


def test_safety_gates_accepts_optional_strategy_max_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "max_by_regime": {"TREND_UP": 0.70, "TREND_DOWN": 0.65}
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.max_by_regime == {
        "TREND_UP": 0.70,
        "TREND_DOWN": 0.65,
    }


def test_safety_gates_accepts_optional_strategy_symbol_max_regime_confidence_thresholds() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "max_by_symbol": {
                "XRPUSDT": {
                    "TREND_UP": 0.35,
                    "TREND_DOWN": 0.34,
                },
                "BTCUSDT": {
                    "TREND_UP": 0.70,
                },
            },
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.max_by_symbol == {
        "XRPUSDT": {
            "TREND_UP": 0.35,
            "TREND_DOWN": 0.34,
        },
        "BTCUSDT": {
            "TREND_UP": 0.70,
        },
    }


def test_safety_gates_rejects_symbol_thresholds_without_default() -> None:
    with pytest.raises(ValidationError, match="DEFAULT"):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={
                "min_by_symbol": {
                    "XRPUSDT": {
                        "TREND_UP": 0.975,
                    }
                }
            },
        )


def test_safety_gates_accepts_partial_max_thresholds_without_default() -> None:
    cfg = domain_dm.SafetyGatesConfig(
        enabled=True,
        system_stress_policy="off",
        stress_attenuation_factor=0.5,
        regime_confidence={
            "max_by_regime": {
                "TREND_UP": 0.975,
                "TREND_DOWN": 0.88,
            }
        },
    )

    assert cfg.regime_confidence is not None
    assert cfg.regime_confidence.max_by_regime == {
        "TREND_UP": 0.975,
        "TREND_DOWN": 0.88,
    }


def test_safety_gates_rejects_side_aware_default_regime_key() -> None:
    with pytest.raises(ValidationError, match="DEFAULT\\+side is not supported|unsupported"):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={
                "min_by_regime_side": {
                    "DEFAULT": {
                        "SELL": 0.62,
                    }
                }
            },
        )


def test_safety_gates_rejects_unknown_side_label_for_side_aware_thresholds() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={
                "min_by_regime_side": {
                    "TREND_DOWN": {
                        "SHORT": 0.62,
                    }
                }
            },
        )


def test_safety_gates_rejects_explicit_null_side_max_override() -> None:
    with pytest.raises(ValidationError, match="explicit null"):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={
                "max_by_symbol_regime_side": {
                    "ETHUSDT": {
                        "TREND_DOWN": {
                            "SELL": None,
                        }
                    }
                }
            },
        )


def test_safety_gates_rejects_invalid_side_aware_band_configuration() -> None:
    with pytest.raises(ValidationError, match="must be >= min threshold"):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={
                "min_by_symbol_regime_side": {
                    "ETHUSDT": {
                        "TREND_DOWN": {
                            "SELL": 0.82,
                        }
                    }
                },
                "max_by_symbol_regime_side": {
                    "ETHUSDT": {
                        "TREND_DOWN": {
                            "SELL": {
                                "enabled": True,
                                "threshold": 0.79,
                            }
                        }
                    }
                },
            },
        )


def test_directional_sanity_rejects_invalid_band_configuration() -> None:
    with pytest.raises(ValidationError, match="must be >= min threshold"):
        domain_dm.DirectionalSanityConfig(
            enabled=True,
            min_abs_delta_price=0.0,
            min_confidence=0.0,
            min_regime_confidence=0.60,
            min_regime_confidence_by_regime={
                "DEFAULT": 0.60, "TREND_UP": 0.75},
            max_regime_confidence_by_regime={
                "DEFAULT": 0.45, "TREND_UP": 0.70},
            hard_veto_consecutive_bars=2,
            consecutive_bars=1,
        )


def test_low_vol_cost_floor_gate_accepts_explicit_contract() -> None:
    cfg = domain_dm.LowVolCostFloorGateConfig(
        enabled=True,
        enforce_in_modes=["testnet", "hybrid_live_data_testnet_exec"],
        observe_only_in_modes=["live", "production"],
        regimes=["LOW_VOLATILITY"],
        fee={"open_fee_bps": 4.0, "close_fee_bps": 4.0,
             "fee_source": "explicit_config"},
        slippage={"buffer_bps": 2.0, "source": "explicit_config"},
        thresholds={
            "target_net_fee_multiple": 2.0,
            "min_tp_fee_coverage": 3.0,
            "min_rr": 1.2,
            "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
            "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.51},
            "min_regime_confidence_overrides_by_strategy_symbol": {
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45},
                },
            },
            "min_direction_confidence_overrides_by_strategy_symbol": {
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59},
                },
            },
        },
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        geometry={"require_tpsl": True, "missing_policy": "fail_closed"},
    )

    assert cfg.regimes == ["LOW_VOLATILITY"]
    assert cfg.decision_chain_enabled is True
    assert cfg.thresholds.min_regime_confidence_by_regime["LOW_VOLATILITY"] == 0.39
    assert cfg.thresholds.min_direction_confidence_overrides_by_strategy_symbol == {
        "aurora": {
            "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59},
        },
    }


def test_low_vol_cost_floor_gate_rejects_missing_low_volatility_threshold() -> None:
    with pytest.raises(ValidationError, match="LOW_VOLATILITY"):
        domain_dm.LowVolCostFloorGateConfig(
            enabled=True,
            enforce_in_modes=["testnet"],
            observe_only_in_modes=["live"],
            regimes=["LOW_VOLATILITY"],
            fee={"open_fee_bps": 4.0, "close_fee_bps": 4.0,
                 "fee_source": "explicit_config"},
            slippage={"buffer_bps": 2.0, "source": "explicit_config"},
            thresholds={
                "target_net_fee_multiple": 2.0,
                "min_tp_fee_coverage": 3.0,
                "min_rr": 1.2,
                "min_regime_confidence_by_regime": {"DEFAULT": 0.45},
                "min_direction_confidence_by_regime": {"DEFAULT": 0.55},
            },
            direction_confidence={
                "required": True,
                "raw_signed_score_sources": ["signal_score"],
                "normalized_confidence_sources": [],
                "judge_confidence_live_producer_required": False,
                "missing_policy": "fail_closed",
            },
            geometry={"require_tpsl": True, "missing_policy": "fail_closed"},
        )


def test_low_vol_cost_floor_gate_rejects_invalid_direction_confidence_missing_policy() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        domain_dm.LowVolCostFloorGateConfig(
            enabled=True,
            enforce_in_modes=["testnet"],
            observe_only_in_modes=["live"],
            regimes=["LOW_VOLATILITY"],
            fee={"open_fee_bps": 4.0, "close_fee_bps": 4.0,
                 "fee_source": "explicit_config"},
            slippage={"buffer_bps": 2.0, "source": "explicit_config"},
            thresholds={
                "target_net_fee_multiple": 2.0,
                "min_tp_fee_coverage": 3.0,
                "min_rr": 1.2,
                "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
                "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.51},
            },
            direction_confidence={
                "required": True,
                "raw_signed_score_sources": ["signal_score"],
                "normalized_confidence_sources": [],
                "judge_confidence_live_producer_required": False,
                "missing_policy": "hard_fail",
            },
            geometry={"require_tpsl": True, "missing_policy": "fail_closed"},
        )


def test_low_vol_cost_floor_gate_rejects_noncanonical_strategy_symbol_threshold_override() -> None:
    with pytest.raises(ValidationError, match="canonical uppercase"):
        domain_dm.LowVolCostFloorGateConfig(
            enabled=True,
            enforce_in_modes=["testnet"],
            observe_only_in_modes=["live"],
            regimes=["LOW_VOLATILITY"],
            fee={"open_fee_bps": 4.0, "close_fee_bps": 4.0,
                 "fee_source": "explicit_config"},
            slippage={"buffer_bps": 2.0, "source": "explicit_config"},
            thresholds={
                "target_net_fee_multiple": 2.0,
                "min_tp_fee_coverage": 3.0,
                "min_rr": 1.2,
                "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
                "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.51},
                "min_direction_confidence_overrides_by_strategy_symbol": {
                    "aurora": {
                        "xrpusdt": {"DEFAULT": 0.825, "LOW_VOLATILITY": 0.93},
                    },
                },
            },
            direction_confidence={
                "required": True,
                "raw_signed_score_sources": ["signal_score"],
                "normalized_confidence_sources": [],
                "judge_confidence_live_producer_required": False,
                "missing_policy": "fail_closed",
            },
            geometry={"require_tpsl": True, "missing_policy": "fail_closed"},
        )


@pytest.mark.parametrize(
    ("min_by_regime", "message"),
    [
        ({"TREND_UP": 0.65}, "DEFAULT"),
        ({"DEFAULT": 0.45, "trend_up": 0.65}, "canonical uppercase"),
        ({"DEFAULT": 0.45, "TRAND_UP": 0.65}, "unsupported"),
        ({"DEFAULT": 0.45, "SIDEWAYS": 0.65}, "unsupported"),
        ({"DEFAULT": -0.01}, r"\[0.0, 1.0\]"),
        ({"DEFAULT": 1.01}, r"\[0.0, 1.0\]"),
    ],
)
def test_safety_gates_rejects_invalid_strategy_regime_confidence_thresholds(
    min_by_regime: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        domain_dm.SafetyGatesConfig(
            enabled=True,
            system_stress_policy="off",
            stress_attenuation_factor=0.5,
            regime_confidence={"min_by_regime": min_by_regime},
        )


@pytest.mark.parametrize(
    ("strategy_file", "strategy_key", "attribute_name"),
    [
        ("aurora.yaml", "aurora", "aurora"),
        ("md_amr.yaml", "md_amr", "md_amr"),
        ("mean_reversion.yaml", "mean_reversion", "mean_reversion"),
        ("llm_microstructure.yaml", "llm_microstructure", "llm_microstructure"),
    ],
)
def test_strategy_profiles_parse_optional_regime_confidence_override_block(
    tmp_path: Path,
    strategy_file: str,
    strategy_key: str,
    attribute_name: str,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    strategy_path = cfg_dir / "strategies" / strategy_file
    strategy = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    strategy[strategy_key]["safety_gates"]["regime_confidence"] = {
        "min_by_regime": {"DEFAULT": 0.45, "TREND_UP": 0.65}
    }
    strategy_path.write_text(
        yaml.safe_dump(strategy, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loaded = ConfigLoader(config_dir=cfg_dir).load_config()
    strategy_cfg = getattr(loaded.strategies, attribute_name)

    assert strategy_cfg.safety_gates.regime_confidence is not None
    assert strategy_cfg.safety_gates.regime_confidence.min_by_regime == {
        "DEFAULT": 0.45,
        "TREND_UP": 0.65,
    }


def test_directional_sanity_rejects_per_regime_thresholds_without_default() -> None:
    with pytest.raises(ValidationError, match="DEFAULT"):
        domain_dm.DirectionalSanityConfig(
            enabled=True,
            min_abs_delta_price=0.0,
            min_confidence=0.0,
            min_regime_confidence=0.45,
            min_regime_confidence_by_regime={"TREND_UP": 0.52},
            hard_veto_consecutive_bars=2,
            consecutive_bars=1,
        )


def test_directional_sanity_rejects_noncanonical_per_regime_threshold_keys() -> None:
    with pytest.raises(ValidationError, match="canonical uppercase"):
        domain_dm.DirectionalSanityConfig(
            enabled=True,
            min_abs_delta_price=0.0,
            min_confidence=0.0,
            min_regime_confidence=0.45,
            min_regime_confidence_by_regime={
                "DEFAULT": 0.45, "trend_up": 0.52},
            hard_veto_consecutive_bars=2,
            consecutive_bars=1,
        )


def test_decision_making_yaml_contract_fails_closed_on_forbidden_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["unexpected_pkg7_field"] = True
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg7_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_decision_making_yaml_contract_fails_closed_on_invalid_decision_geometry(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    strategy_path = cfg_dir / "strategies" / "aurora.yaml"
    strategy = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    strategy["aurora"]["decision"]["decision_geometry"]["admission_mode"] = "soft_power"
    strategy_path.write_text(
        yaml.safe_dump(strategy, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "admission_power" in message
    assert "soft_power" in message


def test_decision_making_yaml_contract_fails_closed_on_invalid_low_vol_cost_floor_modes(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["decision_making"]["low_vol_cost_floor_gate"]["observe_only_in_modes"] = [
        "live",
        "testnet",
    ]
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "must not overlap" in str(exc_info.value)


def test_decision_making_yaml_contract_fails_closed_on_missing_low_vol_threshold(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    del domains["decision_making"]["low_vol_cost_floor_gate"]["thresholds"]["min_regime_confidence_by_regime"]["LOW_VOLATILITY"]
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "LOW_VOLATILITY" in str(exc_info.value)


def test_decision_making_yaml_contract_fails_closed_on_missing_flip_hysteresis(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    instruments_path = cfg_dir / "instruments.yaml"
    instruments = yaml.safe_load(instruments_path.read_text(encoding="utf-8"))
    del instruments["instruments"]["BTCUSDT"]["flip"]["hysteresis_mult"]
    instruments_path.write_text(
        yaml.safe_dump(instruments, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "hysteresis_mult" in message
    assert "field required" in message.lower()
