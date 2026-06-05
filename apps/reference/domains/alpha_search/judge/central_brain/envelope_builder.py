from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Mapping

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    BUILDER_VERSION,
    SCHEMA_VERSION,
    DisagreementMap,
    ExecutionReadinessBlock,
    FreshnessMissingnessMap,
    HistoricalSurfaceEvidenceBlock,
    JudgeEvidenceEnvelopeV2,
    MarketContext,
    PortfolioContextBlock,
    RegimeContextBlock,
    RiskContextBlock,
    StrategyOpinions,
    EnvelopeProvenanceV2,
)
from apps.reference.domains.regime_detector.context_envelope import (
    RegimeContextEnvelope,
)
from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    AuroraExpertOutput,
)
from apps.reference.domains.strategies.runtimes.md_amr.native_expert_adapter import (
    MDAMRExpertOutput,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.native_expert_adapter import (
    MeanReversionExpertOutput,
)


SOURCE_CONTRACT_VERSION = "1.0.0"
MISSING_REASON_NOT_SUPPLIED = "not_supplied"


def _as_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(value))


def _validate_optional(value: Any, model: type[Any]) -> Any:
    if value is None:
        return None
    if isinstance(value, model):
        return value
    if isinstance(value, Mapping):
        return model.model_validate(_as_dict(value))
    raise TypeError(f"expected {model.__name__}, mapping, or None")


def _deterministic_envelope_id(
    *,
    symbol: str,
    created_ts_ms: int,
    question_type: str,
    decision_id: str | None,
    rid: str | None,
) -> str:
    identity = "|".join(
        [
            symbol,
            str(created_ts_ms),
            question_type,
            decision_id or "",
            rid or "",
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"judge_env_v2_{digest}"


def normalize_strategy_opinions(
    *,
    aurora: AuroraExpertOutput | Mapping[str, Any] | None = None,
    mean_reversion: MeanReversionExpertOutput | Mapping[str, Any] | None = None,
    md_amr: MDAMRExpertOutput | Mapping[str, Any] | None = None,
) -> StrategyOpinions:
    return StrategyOpinions(
        aurora=_validate_optional(aurora, AuroraExpertOutput),
        mean_reversion=_validate_optional(mean_reversion, MeanReversionExpertOutput),
        md_amr=_validate_optional(md_amr, MDAMRExpertOutput),
    )


def build_empty_risk_context(
    missing_reason: str = MISSING_REASON_NOT_SUPPLIED,
) -> RiskContextBlock:
    return RiskContextBlock(present=False, missing_reason=missing_reason)


def build_empty_portfolio_context(
    missing_reason: str = MISSING_REASON_NOT_SUPPLIED,
) -> PortfolioContextBlock:
    return PortfolioContextBlock(present=False, missing_reason=missing_reason)


def build_empty_execution_readiness(
    missing_reason: str = MISSING_REASON_NOT_SUPPLIED,
) -> ExecutionReadinessBlock:
    return ExecutionReadinessBlock(
        present=False,
        blocking_reasons=[],
        missing_reason=missing_reason,
    )


def build_empty_historical_surface_evidence(
    missing_reason: str = MISSING_REASON_NOT_SUPPLIED,
) -> HistoricalSurfaceEvidenceBlock:
    return HistoricalSurfaceEvidenceBlock(
        present=False,
        missing_reason=missing_reason,
    )


def _normalize_regime_context(
    regime_context: RegimeContextEnvelope | Mapping[str, Any] | RegimeContextBlock | None,
) -> RegimeContextBlock:
    if regime_context is None:
        return RegimeContextBlock(
            present=False,
            envelope=None,
            missing_reason=MISSING_REASON_NOT_SUPPLIED,
        )
    if isinstance(regime_context, RegimeContextBlock):
        return regime_context
    envelope = _validate_optional(regime_context, RegimeContextEnvelope)
    return RegimeContextBlock(present=True, envelope=envelope, missing_reason=None)


def _normalize_market_context(
    market_context: MarketContext | Mapping[str, Any] | None,
    *,
    symbol: str,
    created_ts_ms: int,
) -> MarketContext:
    if isinstance(market_context, MarketContext):
        return market_context
    if isinstance(market_context, Mapping):
        return MarketContext.model_validate(_as_dict(market_context))
    return MarketContext(
        symbol=symbol,
        ts_ms=created_ts_ms,
        data_freshness_state="UNKNOWN",
        source_refs={"missing_reason": "market_context_not_supplied"},
    )


def _normalize_block(value: Any, model: type[Any], empty_builder: Any) -> Any:
    if value is None:
        return empty_builder()
    if isinstance(value, model):
        return value
    if isinstance(value, Mapping):
        return model.model_validate(_as_dict(value))
    raise TypeError(f"expected {model.__name__}, mapping, or None")


def build_freshness_missingness_map(
    *,
    market_context_supplied: bool,
    regime_context: RegimeContextBlock,
    strategy_opinions: StrategyOpinions,
    risk_context: RiskContextBlock,
    portfolio_context: PortfolioContextBlock,
    execution_readiness: ExecutionReadinessBlock,
    historical_surface_evidence: HistoricalSurfaceEvidenceBlock,
) -> FreshnessMissingnessMap:
    per_block = {
        "market_context": "PRESENT" if market_context_supplied else "MISSING",
        "regime_context": "PRESENT" if regime_context.present else "MISSING",
        "aurora": "PRESENT" if strategy_opinions.aurora is not None else "MISSING",
        "mean_reversion": (
            "PRESENT" if strategy_opinions.mean_reversion is not None else "MISSING"
        ),
        "md_amr": "PRESENT" if strategy_opinions.md_amr is not None else "MISSING",
        "risk_context": "PRESENT" if risk_context.present else "MISSING",
        "portfolio_context": "PRESENT" if portfolio_context.present else "MISSING",
        "execution_readiness": (
            "PRESENT" if execution_readiness.present else "MISSING"
        ),
        "historical_surface_evidence": (
            "PRESENT" if historical_surface_evidence.present else "MISSING"
        ),
    }
    per_field: dict[str, str] = {}
    if not market_context_supplied:
        per_field["market_context"] = "MISSING"
    if not regime_context.present:
        per_field["regime_context"] = regime_context.missing_reason or "MISSING"
    elif regime_context.envelope is not None:
        per_field.update(
            {
                f"regime_context.{key}": value
                for key, value in regime_context.envelope.missingness.per_field.items()
            }
        )
    experts = {
        "aurora": strategy_opinions.aurora,
        "mean_reversion": strategy_opinions.mean_reversion,
        "md_amr": strategy_opinions.md_amr,
    }
    for expert_id, expert in experts.items():
        if expert is None:
            per_field[expert_id] = "MISSING"
            continue
        per_field.update(
            {
                f"{expert_id}.{key}": value
                for key, value in expert.missingness.per_field.items()
            }
        )
    for block_name, block in (
        ("risk_context", risk_context),
        ("portfolio_context", portfolio_context),
        ("execution_readiness", execution_readiness),
        ("historical_surface_evidence", historical_surface_evidence),
    ):
        if not block.present:
            per_field[block_name] = block.missing_reason or "MISSING"
    return FreshnessMissingnessMap(per_block=per_block, per_field=per_field)


def build_disagreement_map(
    strategy_opinions: StrategyOpinions,
) -> DisagreementMap:
    experts = {
        "aurora": strategy_opinions.aurora,
        "mean_reversion": strategy_opinions.mean_reversion,
        "md_amr": strategy_opinions.md_amr,
    }
    present = {name: expert for name, expert in experts.items() if expert is not None}
    side_opinions = {
        name: str(expert.side_opinion)
        for name, expert in present.items()
    }
    confidence_by_expert = {
        name: expert.confidence
        for name, expert in present.items()
    }
    directional = {
        name: side
        for name, side in side_opinions.items()
        if side in {"BUY", "SELL"}
    }
    notes: list[str] = []
    if not present:
        return DisagreementMap(
            side_opinions=side_opinions,
            confidence_by_expert=confidence_by_expert,
            agreement_state="NO_EXPERTS",
            notes=["no_strategy_opinions_present"],
        )
    if not directional:
        return DisagreementMap(
            side_opinions=side_opinions,
            confidence_by_expert=confidence_by_expert,
            agreement_state="UNKNOWN",
            notes=["no_directional_strategy_opinions"],
        )
    sides = set(directional.values())
    if len(directional) == 1:
        state = "SINGLE_EXPERT"
    elif sides == {"BUY"}:
        state = "AGREE_LONG"
    elif sides == {"SELL"}:
        state = "AGREE_SHORT"
    else:
        state = "DISAGREE"
        notes.append("conflicting_buy_sell_opinions")
    return DisagreementMap(
        side_opinions=side_opinions,
        confidence_by_expert=confidence_by_expert,
        agreement_state=state,
        notes=notes,
    )


def build_judge_evidence_envelope(
    *,
    symbol: str,
    created_ts_ms: int,
    question_type: str = "entry",
    envelope_id: str | None = None,
    cycle_key: str | None = None,
    decision_id: str | None = None,
    rid: str | None = None,
    runtime_mode: str | None = None,
    market_context: MarketContext | Mapping[str, Any] | None = None,
    regime_context: RegimeContextEnvelope | Mapping[str, Any] | RegimeContextBlock | None = None,
    aurora: AuroraExpertOutput | Mapping[str, Any] | None = None,
    mean_reversion: MeanReversionExpertOutput | Mapping[str, Any] | None = None,
    md_amr: MDAMRExpertOutput | Mapping[str, Any] | None = None,
    risk_context: RiskContextBlock | Mapping[str, Any] | None = None,
    portfolio_context: PortfolioContextBlock | Mapping[str, Any] | None = None,
    execution_readiness: ExecutionReadinessBlock | Mapping[str, Any] | None = None,
    historical_surface_evidence: HistoricalSurfaceEvidenceBlock | Mapping[str, Any] | None = None,
    provenance_source_refs: Mapping[str, Any] | None = None,
) -> JudgeEvidenceEnvelopeV2:
    market_context_supplied = market_context is not None
    normalized_market_context = _normalize_market_context(
        market_context,
        symbol=symbol,
        created_ts_ms=created_ts_ms,
    )
    normalized_regime_context = _normalize_regime_context(regime_context)
    strategy_opinions = normalize_strategy_opinions(
        aurora=aurora,
        mean_reversion=mean_reversion,
        md_amr=md_amr,
    )
    normalized_risk_context = _normalize_block(
        risk_context,
        RiskContextBlock,
        build_empty_risk_context,
    )
    normalized_portfolio_context = _normalize_block(
        portfolio_context,
        PortfolioContextBlock,
        build_empty_portfolio_context,
    )
    normalized_execution_readiness = _normalize_block(
        execution_readiness,
        ExecutionReadinessBlock,
        build_empty_execution_readiness,
    )
    normalized_historical_surface_evidence = _normalize_block(
        historical_surface_evidence,
        HistoricalSurfaceEvidenceBlock,
        build_empty_historical_surface_evidence,
    )
    effective_envelope_id = envelope_id or _deterministic_envelope_id(
        symbol=symbol,
        created_ts_ms=created_ts_ms,
        question_type=question_type,
        decision_id=decision_id,
        rid=rid,
    )
    input_contract_versions = {
        "judge_evidence_envelope": SCHEMA_VERSION,
    }
    if strategy_opinions.aurora is not None:
        input_contract_versions["aurora_expert_output"] = SOURCE_CONTRACT_VERSION
    if strategy_opinions.mean_reversion is not None:
        input_contract_versions["mean_reversion_expert_output"] = (
            SOURCE_CONTRACT_VERSION
        )
    if strategy_opinions.md_amr is not None:
        input_contract_versions["md_amr_expert_output"] = SOURCE_CONTRACT_VERSION
    if normalized_regime_context.present:
        input_contract_versions["regime_context_envelope"] = SOURCE_CONTRACT_VERSION

    return JudgeEvidenceEnvelopeV2(
        envelope_id=effective_envelope_id,
        created_ts_ms=created_ts_ms,
        cycle_key=cycle_key,
        decision_id=decision_id,
        rid=rid,
        symbol=symbol,
        question_type=question_type,  # type: ignore[arg-type]
        runtime_mode=runtime_mode,
        market_context=normalized_market_context,
        regime_context=normalized_regime_context,
        strategy_opinions=strategy_opinions,
        risk_context=normalized_risk_context,
        portfolio_context=normalized_portfolio_context,
        execution_readiness=normalized_execution_readiness,
        historical_surface_evidence=normalized_historical_surface_evidence,
        freshness_missingness_map=build_freshness_missingness_map(
            market_context_supplied=market_context_supplied,
            regime_context=normalized_regime_context,
            strategy_opinions=strategy_opinions,
            risk_context=normalized_risk_context,
            portfolio_context=normalized_portfolio_context,
            execution_readiness=normalized_execution_readiness,
            historical_surface_evidence=normalized_historical_surface_evidence,
        ),
        disagreement_map=build_disagreement_map(strategy_opinions),
        provenance=EnvelopeProvenanceV2(
            input_contract_versions=input_contract_versions,
            builder_version=BUILDER_VERSION,
            source_refs=deepcopy(dict(provenance_source_refs or {})),
        ),
    )
