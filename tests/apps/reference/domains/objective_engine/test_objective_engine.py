import pytest
from pydantic import ValidationError

from apps.reference.config_models import (
    ObjectiveComponentConfig,
    ObjectiveEngineDomainConfig,
    StrategyObjectiveConfig,
    StrategyObjectiveGateConfig,
    StrategyObjectiveMultiplierConfig,
    StrategyObjectiveRegimeProfile,
)
from apps.reference.domains.objective_engine.engine import evaluate_objective
from apps.reference.domains.objective_engine.types import (
    ObjectiveBehaviorInput,
    ObjectiveExecutionInput,
    ObjectiveExposureInput,
    ObjectiveInput,
    ObjectiveMarketInput,
    ObjectiveSignalInput,
    ObjectiveStructureInput,
)


@pytest.fixture
def base_domain_config() -> ObjectiveEngineDomainConfig:
    return ObjectiveEngineDomainConfig(
        enabled=True,
        data_requirements={
            "require_arce": False,
            "require_portfolio": False,
            "require_execution": False,
            "strict_fail_closed": True,
        },
        explainability={
            "enabled": False,
            "emit_subcomponents": False,
            "emit_normalization_stats": False,
        },
        components={
            "cost": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "alpha_fee": 1.0,
                    "alpha_slippage": 0.7,
                    "alpha_spread": 0.3,
                    "base_fee_bps": 4.0,
                    "slippage_from_spread_ratio": 0.5,
                },
            ),
            "risk": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "phi_inventory": 1.0,
                    "phi_overflow": 3.0,
                    "phi_volatility": 0.5,
                },
            ),
            "edge": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "omega_rr": 0.9,
                    "omega_threshold_margin": 0.8,
                    "phi_stop_distance": 0.2,
                    "phi_rr_consistency": 0.2,
                },
            ),
            "execution": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "omega_liquidity": 0.8,
                    "phi_spread_drag": 0.4,
                    "phi_notional_pressure": 0.3,
                },
            ),
            "information": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "phi_staleness": 0.15,
                    "omega_regime_confidence": 0.7,
                    "omega_readiness": 0.5,
                },
            ),
            "behavior": ObjectiveComponentConfig(
                enabled=True,
                normalization=None,
                parameters={
                    "phi_cancel_replace": 0.2,
                    "phi_blocked_intents": 0.15,
                    "phi_reentry": 0.1,
                    "window_sec": 3600,
                },
            ),
        },
    )


@pytest.fixture
def base_strategy_config() -> StrategyObjectiveConfig:
    return StrategyObjectiveConfig(
        enabled=True,
        regimes={
            "TREND_UP": StrategyObjectiveRegimeProfile(
                weights={
                    "cost": 1.0,
                    "risk": 1.1,
                    "edge": 1.2,
                    "execution": 0.9,
                    "information": 0.8,
                    "behavior": 0.7,
                },
                multiplier=StrategyObjectiveMultiplierConfig(
                    m_min=0.15,
                    m_max=1.35,
                    lambda_scale=1.0,
                    penalty_center=0.0,
                    penalty_scale=1.0,
                ),
                gate=StrategyObjectiveGateConfig(
                    min_objective_score=0.2,
                    enforcement_mode="OBSERVE",
                ),
            )
        },
    )


def _base_input(**overrides) -> ObjectiveInput:
    signal = {
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "signal_score": 0.75,
        "signal_direction": 1,
        "regime": "TREND_UP",
        "regime_age_sec": 120.0,
        "regime_confidence": 0.8,
        "readiness_completeness": 1.0,
    }
    market = {
        "price": 100_000.0,
        "atr": 1_250.0,
        "spread_bps": 1.5,
        "liquidity_state": 1.2,
        "volatility_state": 0.6,
    }
    structure = {
        "threshold_margin": 0.35,
        "rr_expected": 1.8,
        "tp_dist_atr": 1.2,
        "stop_dist_atr": 0.67,
    }
    exposure = {
        "current_exposure_usd": 2_000.0,
        "projected_exposure_usd": 3_000.0,
        "max_exposure_usd": 10_000.0,
    }
    behavior = {
        "recent_cancel_replace_count": 0,
        "recent_blocked_intent_count": 0,
        "recent_reentry_count": 0,
    }
    execution = {
        "expected_fee_bps": 4.0,
        "expected_slippage_bps": 1.0,
    }

    for key, value in overrides.items():
        if key in {"signal", "market", "structure", "exposure", "behavior", "execution"}:
            locals()[key].update(value)
        else:
            raise AssertionError(f"unknown override bucket: {key}")

    return ObjectiveInput(
        signal=ObjectiveSignalInput(**signal),
        market=ObjectiveMarketInput(**market),
        structure=ObjectiveStructureInput(**structure),
        exposure=ObjectiveExposureInput(**exposure),
        behavior=ObjectiveBehaviorInput(**behavior),
        execution=ObjectiveExecutionInput(**execution),
    )


def test_evaluate_objective_disabled(base_domain_config: ObjectiveEngineDomainConfig, base_strategy_config: StrategyObjectiveConfig) -> None:
    base_domain_config.enabled = False

    score = evaluate_objective(
        _base_input(),
        base_domain_config,
        base_strategy_config,
    )

    assert score.objective_score == pytest.approx(0.75)
    assert score.multiplier == pytest.approx(1.0)
    assert score.is_blocked is False


def test_evaluate_objective_missing_regime_fails_closed(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    with pytest.raises(ValueError, match="missing objective regime profile: UNKNOWN"):
        evaluate_objective(
            _base_input(signal={"regime": "UNKNOWN"}),
            base_domain_config,
            base_strategy_config,
        )


def test_evaluate_objective_weight_mismatch_fails_closed(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    base_strategy_config.regimes["TREND_UP"].weights.pop("behavior")

    with pytest.raises(ValueError, match="objective regime profile weight mismatch"):
        evaluate_objective(
            _base_input(),
            base_domain_config,
            base_strategy_config,
        )


def test_evaluate_objective_cost_and_risk_penalties_are_negative(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    score = evaluate_objective(
        _base_input(
            market={"spread_bps": 9.0, "volatility_state": 2.0},
            exposure={"current_exposure_usd": 8_000.0,
                      "projected_exposure_usd": 12_000.0},
            execution={"expected_fee_bps": 5.0, "expected_slippage_bps": 4.0},
        ),
        base_domain_config,
        base_strategy_config,
    )

    assert score.components["cost"] < 0.0
    assert score.components["risk"] < 0.0
    assert score.raw_metrics["fee_drag"] < 0.0
    assert score.raw_metrics["spread_drag"] < 0.0


def test_evaluate_objective_edge_and_execution_components_reward_quality(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    score = evaluate_objective(
        _base_input(
            structure={
                "threshold_margin": 0.8,
                "rr_expected": 2.2,
                "tp_dist_atr": 1.6,
                "stop_dist_atr": 0.6,
            },
            market={"spread_bps": 0.5, "liquidity_state": 2.0},
        ),
        base_domain_config,
        base_strategy_config,
    )

    assert score.components["edge"] > 0.0
    assert score.components["execution"] > 0.0


def test_evaluate_objective_behavior_penalty_reduces_score(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    score = evaluate_objective(
        _base_input(
            behavior={
                "recent_cancel_replace_count": 8,
                "recent_blocked_intent_count": 6,
                "recent_reentry_count": 5,
            }
        ),
        base_domain_config,
        base_strategy_config,
    )

    assert score.components["behavior"] < 0.0
    assert score.multiplier < 1.0


def test_evaluate_objective_gate_blocks_low_quality_entry(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    base_strategy_config.regimes["TREND_UP"].gate.enforcement_mode = "GATE"
    base_strategy_config.regimes["TREND_UP"].gate.min_objective_score = 0.4

    score = evaluate_objective(
        _base_input(
            signal={"signal_score": 0.42},
            market={"spread_bps": 12.0, "liquidity_state": 0.2,
                    "volatility_state": 2.5},
            exposure={"current_exposure_usd": 9_000.0,
                      "projected_exposure_usd": 14_000.0},
            behavior={
                "recent_cancel_replace_count": 10,
                "recent_blocked_intent_count": 8,
                "recent_reentry_count": 7,
            },
            execution={"expected_fee_bps": 8.0, "expected_slippage_bps": 8.0},
        ),
        base_domain_config,
        base_strategy_config,
    )

    assert score.objective_score < 0.4
    assert score.is_blocked is True
    assert score.block_reason is not None
    assert "SCORE_BELOW_GATE" in score.block_reason


def test_evaluate_objective_never_flips_signal_side(
    base_domain_config: ObjectiveEngineDomainConfig,
    base_strategy_config: StrategyObjectiveConfig,
) -> None:
    score = evaluate_objective(
        _base_input(
            signal={
                "signal_score": -0.8,
                "signal_direction": -1,
            }
        ),
        base_domain_config,
        base_strategy_config,
    )

    assert score.objective_score < 0.0
    assert score.multiplier >= 0.0


def test_objective_input_validation_fails_on_missing_nested_fields() -> None:
    with pytest.raises(ValidationError):
        ObjectiveInput(
            signal=ObjectiveSignalInput(
                strategy_id="aurora",
                symbol="BTCUSDT",
                signal_score=0.5,
                signal_direction=1,
                regime="TREND_UP",
                regime_age_sec=0.0,
                regime_confidence=0.8,
                readiness_completeness=1.0,
            ),
            market=ObjectiveMarketInput(
                price=100_000.0,
                atr=1_000.0,
                spread_bps=1.0,
                liquidity_state=1.0,
                volatility_state=1.0,
            ),
            structure=ObjectiveStructureInput(
                threshold_margin=0.2,
                rr_expected=1.5,
                tp_dist_atr=1.0,
                stop_dist_atr=0.5,
            ),
            exposure=ObjectiveExposureInput(
                current_exposure_usd=1_000.0,
                projected_exposure_usd=2_000.0,
                max_exposure_usd=5_000.0,
            ),
            behavior=ObjectiveBehaviorInput(
                recent_cancel_replace_count=0,
                recent_blocked_intent_count=0,
                recent_reentry_count=0,
            ),
            execution=ObjectiveExecutionInput(
                expected_fee_bps=-1.0,
                expected_slippage_bps=0.0,
            ),
        )
