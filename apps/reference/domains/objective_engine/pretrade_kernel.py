from __future__ import annotations

import uuid

from apps.reference.config_models import ObjectiveEngineDomainConfig, StrategyObjectiveConfig
from apps.reference.domains.objective_engine.components import (
    evaluate_behavior,
    evaluate_cost,
    evaluate_edge,
    evaluate_execution,
    evaluate_information,
    evaluate_risk,
)
from apps.reference.domains.objective_engine.normalizers import sigmoid_normalize
from apps.reference.domains.objective_engine.types import ObjectiveInput, ObjectiveScore, ObjectiveTrace


def evaluate_pretrade_objective(
    inputs: ObjectiveInput,
    domain_config: ObjectiveEngineDomainConfig,
    strategy_config: StrategyObjectiveConfig,
) -> ObjectiveScore:
    trace_id = str(uuid.uuid4())
    if not domain_config.enabled or not strategy_config.enabled:
        trace = ObjectiveTrace(
            trace_id=trace_id,
            multiplier=1.0,
            objective_score=inputs.signal.signal_score,
        )
        return ObjectiveScore(
            symbol=inputs.signal.symbol,
            original_score=inputs.signal.signal_score,
            objective_score=inputs.signal.signal_score,
            multiplier=1.0,
            trace_id=trace_id,
            trace=trace,
        )

    profile = strategy_config.regimes.get(inputs.signal.regime)
    if profile is None:
        raise ValueError(f"missing objective regime profile: {inputs.signal.regime}")

    enabled_components = {name: cfg for name, cfg in domain_config.components.items() if cfg.enabled}
    if not enabled_components:
        raise ValueError("objective engine enabled without enabled components")

    weight_names = set(profile.weights.keys())
    component_names = set(enabled_components.keys())
    if weight_names != component_names:
        missing = sorted(component_names - weight_names)
        extra = sorted(weight_names - component_names)
        problems: list[str] = []
        if missing:
            problems.append(f"missing_weights={','.join(missing)}")
        if extra:
            problems.append(f"unknown_weights={','.join(extra)}")
        raise ValueError(f"objective regime profile weight mismatch: {';'.join(problems)}")

    raw_metrics: dict[str, float] = {}
    components_eval: dict[str, float] = {}

    cost_cfg = enabled_components.get("cost")
    if cost_cfg is not None:
        score, metrics = evaluate_cost(
            expected_fee_bps=inputs.execution.expected_fee_bps,
            expected_slippage_bps=inputs.execution.expected_slippage_bps,
            spread_bps=inputs.market.spread_bps,
            params=cost_cfg.parameters,
        )
        components_eval["cost"] = score
        raw_metrics.update(metrics)

    risk_cfg = enabled_components.get("risk")
    if risk_cfg is not None:
        score, metrics = evaluate_risk(
            current_exposure_usd=inputs.exposure.current_exposure_usd,
            projected_exposure_usd=inputs.exposure.projected_exposure_usd,
            max_exposure_usd=inputs.exposure.max_exposure_usd,
            volatility_state=inputs.market.volatility_state,
            params=risk_cfg.parameters,
        )
        components_eval["risk"] = score
        raw_metrics.update(metrics)

    edge_cfg = enabled_components.get("edge")
    if edge_cfg is not None:
        score, metrics = evaluate_edge(
            signal_score=inputs.signal.signal_score,
            threshold_margin=inputs.structure.threshold_margin,
            rr_expected=inputs.structure.rr_expected,
            tp_dist_atr=inputs.structure.tp_dist_atr,
            stop_dist_atr=inputs.structure.stop_dist_atr,
            params=edge_cfg.parameters,
        )
        components_eval["edge"] = score
        raw_metrics.update(metrics)

    execution_cfg = enabled_components.get("execution")
    if execution_cfg is not None:
        score, metrics = evaluate_execution(
            spread_bps=inputs.market.spread_bps,
            liquidity_state=inputs.market.liquidity_state,
            projected_exposure_usd=inputs.exposure.projected_exposure_usd,
            max_exposure_usd=inputs.exposure.max_exposure_usd,
            params=execution_cfg.parameters,
        )
        components_eval["execution"] = score
        raw_metrics.update(metrics)

    information_cfg = enabled_components.get("information")
    if information_cfg is not None:
        score, metrics = evaluate_information(
            regime_age_sec=inputs.signal.regime_age_sec,
            regime_confidence=inputs.signal.regime_confidence,
            readiness_completeness=inputs.signal.readiness_completeness,
            params=information_cfg.parameters,
        )
        components_eval["information"] = score
        raw_metrics.update(metrics)

    behavior_cfg = enabled_components.get("behavior")
    if behavior_cfg is not None:
        score, metrics = evaluate_behavior(
            recent_cancel_replace_count=inputs.behavior.recent_cancel_replace_count,
            recent_blocked_intent_count=inputs.behavior.recent_blocked_intent_count,
            recent_reentry_count=inputs.behavior.recent_reentry_count,
            params=behavior_cfg.parameters,
        )
        components_eval["behavior"] = score
        raw_metrics.update(metrics)

    total_penalty = sum(float(profile.weights[name]) * components_eval[name] for name in components_eval)
    mult_cfg = profile.multiplier
    z_value = total_penalty * float(mult_cfg.lambda_scale)
    normalized_penalty = sigmoid_normalize(
        z_value,
        center=float(mult_cfg.penalty_center),
        scale=float(mult_cfg.penalty_scale),
    )
    multiplier = float(mult_cfg.m_min) + normalized_penalty * (float(mult_cfg.m_max) - float(mult_cfg.m_min))
    multiplier = max(float(mult_cfg.m_min), min(multiplier, float(mult_cfg.m_max)))
    objective_score = inputs.signal.signal_score * multiplier

    gate_cfg = profile.gate
    is_blocked = (
        gate_cfg.enforcement_mode == "GATE"
        and inputs.signal.signal_direction != 0
        and abs(objective_score) < float(gate_cfg.min_objective_score)
    )
    block_reason = None
    if is_blocked:
        block_reason = f"SCORE_BELOW_GATE:{abs(objective_score):.4f}<{float(gate_cfg.min_objective_score):.4f}"

    trace = ObjectiveTrace(
        trace_id=trace_id,
        multiplier=multiplier,
        objective_score=objective_score,
        components=components_eval,
        raw_metrics=raw_metrics,
    )
    return ObjectiveScore(
        symbol=inputs.signal.symbol,
        original_score=inputs.signal.signal_score,
        objective_score=objective_score,
        multiplier=multiplier,
        components=components_eval,
        raw_metrics=raw_metrics,
        trace_id=trace_id,
        is_blocked=is_blocked,
        block_reason=block_reason,
        trace=trace,
    )
