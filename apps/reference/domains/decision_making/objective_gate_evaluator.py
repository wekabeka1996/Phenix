"""Shared objective-gate evaluator.

Centralises the duplicated enablement → precondition → build → evaluate →
result-wrap flow that was copy-pasted across aurora_decision, mean_reversion_handler,
and md_amr_handler.

Owns evaluation only.  Blocked / fail-closed emission, metric increments, timestamp
appends, and payload mutation stay local to each handler.
"""
from __future__ import annotations

import decimal
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, Literal, Mapping

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult
from apps.reference.domains.decision_making.position_queries import PositionQueries
from apps.reference.domains.objective_engine.adapters import (
    build_behavior_input,
    build_execution_input,
    build_exposure_input,
    build_market_input,
    build_objective_input,
    build_signal_input,
    build_structure_input,
    build_structure_input_from_prices,
    compute_projected_order_notional,
    compute_readiness_completeness,
)
from apps.reference.domains.objective_engine.engine import evaluate_objective


class ObjectiveGateStatus(str, Enum):
    DISABLED = "DISABLED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    GATE_BLOCKED = "GATE_BLOCKED"
    PASSED = "PASSED"
    EVALUATION_ERROR = "EVALUATION_ERROR"


@dataclass(frozen=True)
class ObjectiveSignalAdapter:
    signal_score: float
    signal_direction: Literal[-1, 1]
    regime_name: str
    regime_ts_ms: int
    regime_confidence: float
    readiness_source: Mapping[str, Any]
    active_threshold: float


@dataclass(frozen=True)
class ObjectiveStructureAdapter:
    mode: Literal["entry_plan", "price_ctx"]
    entry_plan: EntryPlanResult | None = None
    entry_price: decimal.Decimal | None = None
    stop_price: decimal.Decimal | None = None
    target_price: decimal.Decimal | None = None
    atr: decimal.Decimal | None = None


@dataclass(frozen=True)
class ObjectiveSizingAdapter:
    side: str
    entry_price: decimal.Decimal
    features_payload: Mapping[str, Any]
    margin_pct_mult: decimal.Decimal | None = None


@dataclass(frozen=True)
class ObjectiveBehaviorAdapter:
    now_ms: int
    cancel_replace_ts_ms: Deque[int]
    blocked_intent_ts_ms: Deque[int]
    reentry_ts_ms: Deque[int]


@dataclass(frozen=True)
class ObjectiveGateRequest:
    strategy_id: str
    symbol: str
    config: AuroraConfig
    domain_cfg: Any  # ObjectiveEngineDomainConfig | None
    strategy_cfg: Any  # StrategyObjectiveConfig | None
    market_features: Mapping[str, Any]
    signal: ObjectiveSignalAdapter
    structure: ObjectiveStructureAdapter
    sizing: ObjectiveSizingAdapter
    behavior: ObjectiveBehaviorAdapter
    portfolio: Mapping[str, Any] | None
    exposure_summary: Mapping[str, Any] | None
    position_queries: PositionQueries | None


@dataclass(frozen=True)
class ObjectiveGateResult:
    status: ObjectiveGateStatus
    objective_score: Any | None = None  # ObjectiveScore
    trace_payload: Mapping[str, Any] | None = None
    precondition_code: str | None = None
    error: str | None = None


def _check_enablement(req: ObjectiveGateRequest) -> bool:
    domain_cfg = req.domain_cfg
    strategy_cfg = req.strategy_cfg
    if domain_cfg is None or strategy_cfg is None:
        return False
    if not bool(getattr(domain_cfg, "enabled", False)):
        return False
    if not bool(getattr(strategy_cfg, "enabled", False)):
        return False
    return True


def _check_preconditions(req: ObjectiveGateRequest) -> str | None:
    """Return a precondition code string if any prerequisite is missing, else None."""
    domain_cfg = req.domain_cfg
    cost_cfg = domain_cfg.components.get("cost")
    behavior_cfg = domain_cfg.components.get("behavior")

    if cost_cfg is None or not cost_cfg.enabled:
        return "OBJECTIVE_COMPONENT_MISSING:cost"
    if behavior_cfg is None or not behavior_cfg.enabled:
        return "OBJECTIVE_COMPONENT_MISSING:behavior"
    if not isinstance(req.portfolio, dict):
        return "OBJECTIVE_PORTFOLIO_MISSING"
    if not isinstance(req.exposure_summary, dict):
        return "OBJECTIVE_EXPOSURE_SUMMARY_MISSING"
    if not req.signal.regime_name:
        return "OBJECTIVE_REGIME_MISSING"
    if req.signal.regime_ts_ms <= 0:
        return "OBJECTIVE_REGIME_TS_MISSING"

    # Structure-mode–specific preconditions
    if req.structure.mode == "entry_plan":
        if req.structure.entry_plan is None:
            return "OBJECTIVE_ENTRY_PLAN_MISSING"
    else:
        if (req.structure.entry_price is None
                or req.structure.stop_price is None
                or req.structure.target_price is None):
            return "OBJECTIVE_PRICE_CTX_MISSING"
        if req.structure.atr is None or req.structure.atr <= 0:
            return "OBJECTIVE_ATR_MISSING"

    return None


def evaluate_objective_gate(request: ObjectiveGateRequest) -> ObjectiveGateResult:
    """Run the shared enablement → precondition → evaluate flow.

    Returns a typed result; the caller keeps responsibility for emission,
    metric increments, timestamp appends, and payload mutation.
    """
    # 1. Enablement
    if not _check_enablement(request):
        return ObjectiveGateResult(status=ObjectiveGateStatus.DISABLED)

    # 2. Preconditions
    precondition_code = _check_preconditions(request)
    if precondition_code is not None:
        return ObjectiveGateResult(
            status=ObjectiveGateStatus.PRECONDITION_FAILED,
            precondition_code=precondition_code,
        )

    # 3. Build inputs and evaluate
    try:
        domain_cfg = request.domain_cfg
        strategy_cfg = request.strategy_cfg
        cost_cfg = domain_cfg.components["cost"]
        behavior_cfg = domain_cfg.components["behavior"]

        # Market
        objective_market = build_market_input(
            features=dict(request.market_features))

        # Signal
        readiness_completeness = compute_readiness_completeness(
            request.signal.readiness_source)
        signal_input = build_signal_input(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            signal_score=request.signal.signal_score,
            signal_direction=request.signal.signal_direction,
            regime=request.signal.regime_name,
            regime_age_sec=max(0.0, float(
                (request.behavior.now_ms - request.signal.regime_ts_ms) / 1000.0)),
            regime_confidence=request.signal.regime_confidence,
            readiness_completeness=readiness_completeness,
        )

        # Structure
        if request.structure.mode == "entry_plan":
            structure_input = build_structure_input(
                signal_score=request.signal.signal_score,
                active_threshold=request.signal.active_threshold,
                entry_plan=request.structure.entry_plan,
            )
        else:
            structure_input = build_structure_input_from_prices(
                signal_score=request.signal.signal_score,
                active_threshold=request.signal.active_threshold,
                entry_price=request.structure.entry_price,
                stop_price=request.structure.stop_price,
                target_price=request.structure.target_price,
                atr=request.structure.atr,
            )

        # Projected notional
        projected_notional_usd = compute_projected_order_notional(
            symbol=request.symbol,
            side=request.sizing.side,
            entry_price=request.sizing.entry_price,
            position_queries=request.position_queries,
            portfolio=request.portfolio,
            features_payload=dict(
                request.sizing.features_payload) if request.sizing.features_payload else {},
            margin_pct_mult=request.sizing.margin_pct_mult,
        )

        # Exposure
        exposure_input = build_exposure_input(
            config=request.config,
            portfolio=request.portfolio,
            exposure_summary=request.exposure_summary,
            projected_order_notional_usd=projected_notional_usd,
        )

        # Behavior (NOTE: prunes the passed deques — existing mutation)
        behavior_input = build_behavior_input(
            now_ms=request.behavior.now_ms,
            window_sec=float(behavior_cfg.parameters["window_sec"]),
            cancel_replace_ts_ms=request.behavior.cancel_replace_ts_ms,
            blocked_intent_ts_ms=request.behavior.blocked_intent_ts_ms,
            reentry_ts_ms=request.behavior.reentry_ts_ms,
        )

        # Execution
        execution_input = build_execution_input(
            expected_fee_bps=float(cost_cfg.parameters["base_fee_bps"]),
            expected_slippage_bps=objective_market.spread_bps
            * float(cost_cfg.parameters["slippage_from_spread_ratio"]),
        )

        # Assemble
        obj_input = build_objective_input(
            signal=signal_input,
            market=objective_market,
            structure=structure_input,
            exposure=exposure_input,
            behavior=behavior_input,
            execution=execution_input,
        )

        # Evaluate
        obj_score = evaluate_objective(obj_input, domain_cfg, strategy_cfg)

        # 4. Wrap result
        trace_payload = obj_score.trace.model_dump()
        if obj_score.is_blocked:
            return ObjectiveGateResult(
                status=ObjectiveGateStatus.GATE_BLOCKED,
                objective_score=obj_score,
                trace_payload=trace_payload,
            )
        return ObjectiveGateResult(
            status=ObjectiveGateStatus.PASSED,
            objective_score=obj_score,
            trace_payload=trace_payload,
        )

    except Exception as exc:
        return ObjectiveGateResult(
            status=ObjectiveGateStatus.EVALUATION_ERROR,
            error=str(exc),
        )
