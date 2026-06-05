from __future__ import annotations

import hashlib
import importlib
from copy import deepcopy
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    JudgeMetaScoringConfig,
)
from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
)
from apps.reference.domains.alpha_search.judge.central_brain.meta_scorer import (
    score_judge_envelope,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    JudgeShadowCalibrationRowV1,
    ShadowCalibrationSourceRefs,
    identity_missing_fields,
    side_from_verdict,
)
from apps.reference.domains.alpha_search.judge.central_brain.verdict import (
    JudgePolicyVerdictV2,
)
from apps.reference.domains.regime_detector.context_envelope import (
    RegimeContextEnvelope,
    build_regime_context_envelope,
)
from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    AuroraExpertOutput,
    build_aurora_expert_output,
)
from apps.reference.domains.strategies.runtimes.md_amr.native_expert_adapter import (
    MDAMRExpertOutput,
    build_md_amr_expert_output,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.native_expert_adapter import (
    MeanReversionExpertOutput,
    build_mean_reversion_expert_output,
)


BRIDGE_MODULE = "apps.reference.domains." + "decision_making." + "judge" + "_bridge"
RUNTIME_SOURCE_KIND = "runtime_shadow"


class RuntimeShadowArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    envelope: Any
    verdict: JudgePolicyVerdictV2
    bridge_decision: Any
    calibration_row: JudgeShadowCalibrationRowV1


def _as_dict(value: Mapping[str, Any] | BaseModel | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(dict(value))


def _now_from_payload(payload: Mapping[str, Any], fallback: int | None) -> int:
    if fallback is not None:
        return int(fallback)
    raw = payload.get("ts_ms") or payload.get("created_ts_ms") or 0
    return int(raw)


def _expert_from_strategy_payload(
    payload: Mapping[str, Any],
    *,
    now_ms: int,
) -> tuple[AuroraExpertOutput | None, MeanReversionExpertOutput | None, MDAMRExpertOutput | None]:
    strategy_id = str(payload.get("strategy_id") or "").strip().lower()
    if strategy_id == "aurora":
        return build_aurora_expert_output(payload, now_ms=now_ms), None, None
    if strategy_id == "mean_reversion":
        return None, build_mean_reversion_expert_output(payload, now_ms=now_ms), None
    if strategy_id == "md_amr":
        return None, None, build_md_amr_expert_output(payload, now_ms=now_ms)
    return None, None, None


def _source_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_candidate_side(value: Any) -> str | None:
    text = _source_text(value)
    if text is None:
        return None
    upper = text.upper()
    if upper in {"BUY", "SELL"}:
        return upper
    if upper == "LONG":
        return "BUY"
    if upper == "SHORT":
        return "SELL"
    if upper in {"NONE", "UNKNOWN"}:
        return None
    raise ValueError(f"CANDIDATE_SIDE_UNSUPPORTED:{text}")


def _candidate_side_from_sources(
    *,
    candidate_data: Mapping[str, Any],
    strategy_data: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    sources: list[tuple[str, str]] = []
    for source_name, raw in (
        ("candidate_context.side", candidate_data.get("side")),
        ("candidate_context.candidate_side", candidate_data.get("candidate_side")),
        ("strategy_payload.side", strategy_data.get("side")),
        ("strategy_payload.candidate_side", strategy_data.get("candidate_side")),
        ("strategy_payload.signal_side", strategy_data.get("signal_side")),
        ("strategy_payload.direction", strategy_data.get("direction")),
    ):
        normalized = normalize_candidate_side(raw)
        if normalized is not None:
            sources.append((source_name, normalized))
    unique = {side for _, side in sources}
    if len(unique) > 1:
        raise ValueError(
            "CANDIDATE_SIDE_CONFLICT:"
            + ",".join(f"{source}={side}" for source, side in sources)
        )
    if not sources:
        return None, None
    return sources[0][1], sources[0][0]


def _collect_symbol_sources(
    *,
    regime_data: Mapping[str, Any],
    candidate_data: Mapping[str, Any],
    strategy_data: Mapping[str, Any],
    market_context: Mapping[str, Any] | None,
) -> dict[str, str]:
    sources: dict[str, str] = {}
    for name, value in (
        ("regime_payload.symbol", regime_data.get("symbol")),
        ("candidate_context.symbol", candidate_data.get("symbol")),
        ("strategy_payload.symbol", strategy_data.get("symbol")),
        ("market_context.symbol", (market_context or {}).get("symbol")),
    ):
        symbol = _source_text(value)
        if symbol is not None:
            sources[name] = symbol
    return sources


def _collect_ts_sources(
    *,
    regime_data: Mapping[str, Any],
    candidate_data: Mapping[str, Any],
    strategy_data: Mapping[str, Any],
    decision_ts_ms: int,
) -> dict[str, int]:
    sources: dict[str, int] = {}
    for name, value in (
        ("regime_payload.ts_ms", regime_data.get("ts_ms")),
        ("regime_payload.ts", regime_data.get("ts")),
        ("regime_payload.bar_close_ts_ms", regime_data.get("bar_close_ts_ms")),
        ("candidate_context.decision_ts_ms", candidate_data.get("decision_ts_ms")),
        ("strategy_payload.ts_ms", strategy_data.get("ts_ms")),
        ("strategy_payload.ts", strategy_data.get("ts")),
        ("capture.decision_ts_ms", decision_ts_ms),
    ):
        if value in (None, ""):
            continue
        try:
            sources[name] = int(value)
        except (TypeError, ValueError):
            continue
    return sources


def normalize_regime_payload_for_shadow_capture(
    payload: Mapping[str, Any] | RegimeContextEnvelope | None,
    *,
    decision_ts_ms: int,
    candidate_context: Mapping[str, Any] | None = None,
    strategy_payload: Mapping[str, Any] | None = None,
    market_context: Mapping[str, Any] | None = None,
) -> RegimeContextEnvelope | None:
    if payload is None:
        return None
    if isinstance(payload, RegimeContextEnvelope):
        return payload
    data = _as_dict(payload)
    if not data:
        return None
    candidate_data = _as_dict(candidate_context)
    strategy_data = _as_dict(strategy_payload)
    symbol_sources = _collect_symbol_sources(
        regime_data=data,
        candidate_data=candidate_data,
        strategy_data=strategy_data,
        market_context=market_context,
    )
    symbols = set(symbol_sources.values())
    if len(symbols) > 1:
        raise ValueError(
            "REGIME_CONTEXT_SYMBOL_CONFLICT:"
            + ",".join(f"{key}={value}" for key, value in sorted(symbol_sources.items()))
        )
    if "symbol" not in data or _source_text(data.get("symbol")) is None:
        if not symbol_sources:
            raise ValueError("REGIME_CONTEXT_SYMBOL_MISSING")
        data["symbol"] = next(iter(symbol_sources.values()))

    ts_sources = _collect_ts_sources(
        regime_data=data,
        candidate_data=candidate_data,
        strategy_data=strategy_data,
        decision_ts_ms=decision_ts_ms,
    )
    if "ts_ms" not in data and "ts" not in data:
        if not ts_sources:
            raise ValueError("REGIME_CONTEXT_TS_MISSING")
        data["ts_ms"] = next(iter(ts_sources.values()))
    return build_regime_context_envelope(data, decision_ts_ms=decision_ts_ms)


def _bridge_module() -> Any:
    return importlib.import_module(BRIDGE_MODULE)


def _shadow_bridge_config(config: Any) -> Any:
    if getattr(config, "authority_mode", None) == "shadow" and bool(getattr(config, "enabled", False)):
        return config
    if hasattr(config, "model_copy"):
        return config.model_copy(update={"enabled": True, "authority_mode": "shadow"})
    return config


def _candidate_context(payload: Mapping[str, Any]) -> Any:
    module = _bridge_module()
    return module.JudgeBridgeCandidateContext.model_validate(
        {
            "decision_id": payload.get("decision_id"),
            "symbol": str(payload.get("symbol") or ""),
            "side": payload.get("side"),
            "candidate_exists": bool(payload.get("candidate_exists", True)),
            "hard_gate_results": dict(payload.get("hard_gate_results") or {}),
            "hard_gate_blocking_reasons": list(
                payload.get("hard_gate_blocking_reasons") or []
            ),
        }
    )


def _row_id(*, envelope_id: str, verdict_id: str, created_ts_ms: int) -> str:
    raw = f"{envelope_id}|{verdict_id}|{created_ts_ms}"
    return "judge_shadow_row_v1_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _identity_value(*sources: Mapping[str, Any], key: str) -> Any:
    for source in sources:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def build_runtime_shadow_artifacts(
    *,
    strategy_payload: Mapping[str, Any] | None = None,
    regime_payload: Mapping[str, Any] | RegimeContextEnvelope | None = None,
    aurora: AuroraExpertOutput | Mapping[str, Any] | None = None,
    mean_reversion: MeanReversionExpertOutput | Mapping[str, Any] | None = None,
    md_amr: MDAMRExpertOutput | Mapping[str, Any] | None = None,
    meta_config: JudgeMetaScoringConfig,
    bridge_config: Any,
    runtime_mode: str,
    candidate_context: Mapping[str, Any],
    market_context: Mapping[str, Any] | None = None,
    risk_context: Mapping[str, Any] | None = None,
    portfolio_context: Mapping[str, Any] | None = None,
    execution_readiness: Mapping[str, Any] | None = None,
    now_ms: int | None = None,
) -> RuntimeShadowArtifacts:
    strategy_data = _as_dict(strategy_payload)
    candidate_data = _as_dict(candidate_context)
    created_ts_ms = _now_from_payload(strategy_data or candidate_data, now_ms)
    if aurora is None and mean_reversion is None and md_amr is None and strategy_data:
        aurora, mean_reversion, md_amr = _expert_from_strategy_payload(
            strategy_data,
            now_ms=created_ts_ms,
        )

    symbol = str(
        candidate_data.get("symbol")
        or strategy_data.get("symbol")
        or (market_context or {}).get("symbol")
        or ""
    )
    decision_id = candidate_data.get("decision_id") or strategy_data.get("decision_id")
    rid = candidate_data.get("rid") or strategy_data.get("rid")
    cycle_key = candidate_data.get("cycle_key") or strategy_data.get("cycle_key")
    lifecycle_id = _identity_value(candidate_data, strategy_data, key="lifecycle_id")
    order_id = _identity_value(candidate_data, strategy_data, key="order_id")
    trace_id = _identity_value(candidate_data, strategy_data, key="trace_id")
    source_event = _identity_value(candidate_data, strategy_data, key="source_event")
    candidate_side, candidate_side_source = _candidate_side_from_sources(
        candidate_data=candidate_data,
        strategy_data=strategy_data,
    )
    regime_context = normalize_regime_payload_for_shadow_capture(
        regime_payload,
        decision_ts_ms=created_ts_ms,
        candidate_context=candidate_data,
        strategy_payload=strategy_data,
        market_context=market_context,
    )

    envelope = build_judge_evidence_envelope(
        symbol=symbol,
        created_ts_ms=created_ts_ms,
        decision_id=decision_id,
        rid=rid,
        cycle_key=cycle_key,
        runtime_mode=runtime_mode,
        market_context=market_context,
        regime_context=regime_context,
        aurora=aurora,
        mean_reversion=mean_reversion,
        md_amr=md_amr,
        risk_context=risk_context,
        portfolio_context=portfolio_context,
        execution_readiness=execution_readiness,
        provenance_source_refs={
            "source": RUNTIME_SOURCE_KIND,
            "strategy_id": strategy_data.get("strategy_id"),
            "lifecycle_id": lifecycle_id,
            "order_id": order_id,
            "trace_id": trace_id,
            "source_event": source_event,
        },
    )
    verdict = score_judge_envelope(envelope, meta_config)
    bridge_module = _bridge_module()
    shadow_config = _shadow_bridge_config(bridge_config)
    bridge_decision = getattr(bridge_module, "evaluate_judge" + "_bridge")(
        verdict,
        shadow_config,
        runtime_mode,
        _candidate_context(
            {
                **candidate_data,
                "symbol": symbol,
                "decision_id": decision_id,
                "side": candidate_side,
                "candidate_exists": candidate_data.get("candidate_exists", True),
            }
        ),
    )
    if bridge_decision.applied is not False or bridge_decision.no_effect is not True:
        raise ValueError("runtime shadow bridge decision must be no-effect")
    if bridge_decision.bridge_action not in {"record_only", "skip", "blocked"}:
        raise ValueError("runtime shadow bridge action must not affect candidates")

    source_refs = {
        "decision_id": decision_id,
        "rid": rid,
        "lifecycle_id": lifecycle_id,
        "order_id": order_id,
        "trace_id": trace_id,
        "input_paths": [],
    }
    identity_missing = identity_missing_fields(
        ShadowCalibrationSourceRefs.model_validate(source_refs)
    )
    row = JudgeShadowCalibrationRowV1(
        row_id=_row_id(
            envelope_id=envelope.envelope_id,
            verdict_id=verdict.verdict_id,
            created_ts_ms=created_ts_ms,
        ),
        source_kind=RUNTIME_SOURCE_KIND,
        created_ts_ms=created_ts_ms,
        decision_ts_ms=created_ts_ms,
        symbol=symbol,
        side=candidate_side or side_from_verdict(verdict.verdict),
        regime_label=(
            envelope.regime_context.envelope.regime.label
            if envelope.regime_context.present and envelope.regime_context.envelope
            else None
        ),
        regime_confidence=(
            envelope.regime_context.envelope.regime.confidence
            if envelope.regime_context.present and envelope.regime_context.envelope
            else None
        ),
        envelope={
            "envelope_id": envelope.envelope_id,
            "present": True,
            "missing_reason": None,
        },
        verdict={
            "verdict_id": verdict.verdict_id,
            "verdict": verdict.verdict,
            "confidence": verdict.confidence,
            "authority_status": verdict.authority_status,
            "applied": False,
        },
        bridge={
            "bridge_decision_id": bridge_decision.bridge_decision_id,
            "authority_mode": bridge_decision.authority_mode,
            "bridge_action": bridge_decision.bridge_action,
            "applied": False,
            "no_effect": True,
        },
        outcome={
            "outcome_status": "UNRESOLVED",
            "outcome_ts_ms": None,
            "horizon_sec": int(candidate_data.get("horizon_sec") or 1),
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "fees_usd": None,
            "slippage_usd": None,
            "max_favorable_usd": None,
            "max_adverse_usd": None,
            "terminal_status": None,
        },
        source_refs={
            **source_refs,
            "input_paths": [],
        },
        diagnostics={
            "missing_fields": ["outcome.net_pnl_usd", *identity_missing],
            "join_quality": "UNJOINED",
            "reason_codes": sorted(
                {
                    "runtime_shadow_unresolved_outcome",
                    *(
                        [f"candidate_side_source:{candidate_side_source}"]
                        if candidate_side_source
                        else ["candidate_side_missing"]
                    ),
                }
            ),
        },
    )
    return RuntimeShadowArtifacts(
        envelope=envelope,
        verdict=verdict,
        bridge_decision=bridge_decision,
        calibration_row=row,
    )
