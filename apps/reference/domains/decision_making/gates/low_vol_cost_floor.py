from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from apps.reference.shared.decision_primitives.score_lineage import (
    LOW_VOL_DIRECTION_CONFIDENCE_THRESHOLD_FAMILY,
    find_score_lineage_record,
    get_score_field_contract,
    is_normalized_confidence_scale,
    is_signed_score_scale,
)


_SIGNED_DIRECTION_CONFIDENCE_SOURCES = frozenset(
    {"signal_score", "final_score"})
_DIRECTION_CONFIDENCE_FAILURE_REASONS = frozenset(
    {
        "direction_confidence_missing",
        "missing_direction_confidence_source",
        "unsupported_direction_confidence_source",
        "non_side_aware_direction_confidence",
        "invalid_direction_confidence_value",
        "direction_confidence_below_threshold",
        "judge_confidence_no_live_producer",
        "direction_confidence_scale_unknown",
        "signed_score_not_allowed_as_direction_confidence",
    }
)
_NRR062_TESTNET_SEGMENT_OVERRIDE_NAME = "LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL"
_NRR062_TESTNET_SEGMENT_OVERRIDE_MODES = frozenset(
    {"testnet", "hybrid_live_data_testnet_exec"}
)


@dataclass(frozen=True, slots=True)
class LowVolCostFloorEvaluation:
    active: bool
    gate_mode: str
    block: bool
    threshold_failed: bool
    reason: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DirectionConfidenceResolution:
    value: float | None
    source: str
    is_present: bool
    is_supported_source: bool
    is_side_aware: bool
    side_scope: str | None
    failure_reason: str | None
    scale: str | None = None
    selected_stage: str | None = None
    authority_status: str | None = None
    compatibility_alias_used: bool = False
    raw_value: float | None = None
    normalized_value_if_any: float | None = None
    lineage_backed: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedLowVolThreshold:
    value: float
    source: str
    strategy_id: str | None
    symbol: str | None
    regime_key: str


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _to_optional_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _resolve_regime_threshold(mapping: Mapping[str, float], regime: str | None) -> float:
    if regime is not None and regime in mapping:
        return float(mapping[regime])
    return float(mapping["DEFAULT"])


def _resolve_low_vol_threshold(
    *,
    mapping: Mapping[str, float],
    overrides_by_strategy_symbol: Mapping[str, Mapping[str, Mapping[str, float]]] | None,
    strategy_id: str | None,
    symbol: str | None,
    regime: str | None,
) -> ResolvedLowVolThreshold:
    normalized_strategy_id = str(
        strategy_id).strip() if strategy_id is not None else ""
    normalized_symbol = str(symbol).strip(
    ).upper() if symbol is not None else ""
    if (
        overrides_by_strategy_symbol
        and normalized_strategy_id
        and normalized_symbol
    ):
        strategy_overrides = overrides_by_strategy_symbol.get(
            normalized_strategy_id)
        if strategy_overrides is not None:
            symbol_mapping = strategy_overrides.get(normalized_symbol)
            if symbol_mapping is not None:
                regime_key = regime if regime is not None and regime in symbol_mapping else "DEFAULT"
                return ResolvedLowVolThreshold(
                    value=_resolve_regime_threshold(symbol_mapping, regime),
                    source="strategy_symbol_override",
                    strategy_id=normalized_strategy_id,
                    symbol=normalized_symbol,
                    regime_key=regime_key,
                )
    regime_key = regime if regime is not None and regime in mapping else "DEFAULT"
    return ResolvedLowVolThreshold(
        value=_resolve_regime_threshold(mapping, regime),
        source="global_regime",
        strategy_id=None,
        symbol=None,
        regime_key=regime_key,
    )


def _resolve_gate_mode(*, enabled: bool, trading_mode: str, enforce_in_modes: list[str], observe_only_in_modes: list[str]) -> str:
    if not enabled:
        return "disabled"
    if trading_mode in enforce_in_modes:
        return "enforced"
    if trading_mode in observe_only_in_modes:
        return "observe_only"
    return "disabled"


def _normalize_side_scope(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"BUY", "LONG", "1", "+1"}:
        return "BUY"
    if text in {"SELL", "SHORT", "-1"}:
        return "SELL"
    return None


def _resolve_source_lineage_record(*, trace: Mapping[str, Any], source: str) -> Mapping[str, Any] | None:
    return find_score_lineage_record(trace, source)


def _resolve_source_contract(source: str):
    return get_score_field_contract(source)


def _resolve_source_scale(*, trace: Mapping[str, Any], source: str) -> str | None:
    lineage_record = _resolve_source_lineage_record(trace=trace, source=source)
    if lineage_record is not None and lineage_record.get("scale") is not None:
        return str(lineage_record.get("scale"))
    contract = _resolve_source_contract(source)
    if contract is not None:
        return contract.scale
    return None


def _resolve_source_authority_status(*, trace: Mapping[str, Any], source: str) -> str | None:
    lineage_record = _resolve_source_lineage_record(trace=trace, source=source)
    if lineage_record is not None and lineage_record.get("live_authority_status") is not None:
        return str(lineage_record.get("live_authority_status"))
    contract = _resolve_source_contract(source)
    if contract is not None:
        return contract.live_authority_status
    return None


def _resolve_source_stage(*, trace: Mapping[str, Any], source: str) -> str | None:
    lineage_record = _resolve_source_lineage_record(trace=trace, source=source)
    if lineage_record is not None and lineage_record.get("consumer_stage") is not None:
        return str(lineage_record.get("consumer_stage"))
    return None


def _resolve_source_compatibility_alias_used(*, trace: Mapping[str, Any], source: str) -> bool:
    lineage_record = _resolve_source_lineage_record(trace=trace, source=source)
    return bool(lineage_record is not None and lineage_record.get("compatibility_alias_for"))


def _resolve_source_lineage_backed(*, trace: Mapping[str, Any], source: str) -> bool:
    return _resolve_source_lineage_record(trace=trace, source=source) is not None


def _resolve_source_value(*, trace: Mapping[str, Any], source: str) -> Any:
    lineage_record = _resolve_source_lineage_record(trace=trace, source=source)
    raw_value = lineage_record.get(
        "value") if lineage_record is not None else trace.get(source)
    objective = trace.get("objective")
    if raw_value is None and source == "final_score" and isinstance(objective, Mapping):
        raw_value = objective.get("final_score", objective.get("score"))
    if raw_value is None and source == "judge_confidence" and isinstance(objective, Mapping):
        raw_value = objective.get("judge_confidence")
    return raw_value


def _resolve_source_side_scope(*, trace: Mapping[str, Any], source: str) -> str | None:
    objective = trace.get("objective")
    candidates: list[Any] = [
        trace.get(f"{source}_side_scope"),
        trace.get(f"{source}_side"),
    ]
    if source == "final_score" and isinstance(objective, Mapping):
        candidates.extend(
            [
                objective.get("final_score_side_scope"),
                objective.get("side"),
            ]
        )
    if source == "judge_confidence" and isinstance(objective, Mapping):
        candidates.extend(
            [
                objective.get("judge_confidence_side_scope"),
                objective.get("judge_confidence_side"),
            ]
        )
    for candidate in candidates:
        side_scope = _normalize_side_scope(candidate)
        if side_scope is not None:
            return side_scope
    return None


def _resolve_signed_direction_confidence(
    *,
    raw_value: Any,
    source: str,
    proposed_side: str,
    scale: str | None,
    selected_stage: str | None,
    authority_status: str | None,
    compatibility_alias_used: bool,
    lineage_backed: bool,
) -> DirectionConfidenceResolution:
    numeric = _coerce_decimal(raw_value)
    if numeric is None:
        return DirectionConfidenceResolution(
            value=None,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=True,
            side_scope=None,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            lineage_backed=lineage_backed,
        )
    signed_value = float(numeric)
    magnitude = abs(signed_value)
    if signed_value == 0.0 or magnitude > 1.0:
        return DirectionConfidenceResolution(
            value=None,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=True,
            side_scope=None,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            raw_value=signed_value,
            lineage_backed=lineage_backed,
        )
    side_scope = "BUY" if signed_value > 0 else "SELL"
    if side_scope != proposed_side:
        return DirectionConfidenceResolution(
            value=None,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=True,
            side_scope=side_scope,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            raw_value=signed_value,
            lineage_backed=lineage_backed,
        )
    return DirectionConfidenceResolution(
        value=magnitude,
        source=source,
        is_present=True,
        is_supported_source=True,
        is_side_aware=True,
        side_scope=side_scope,
        failure_reason=None,
        scale=scale,
        selected_stage=selected_stage,
        authority_status=authority_status,
        compatibility_alias_used=compatibility_alias_used,
        raw_value=signed_value,
        lineage_backed=lineage_backed,
    )


def _resolve_unsigned_direction_confidence(
    *,
    raw_value: Any,
    source: str,
    proposed_side: str,
    raw_side_scope: Any,
    scale: str | None,
    selected_stage: str | None,
    authority_status: str | None,
    compatibility_alias_used: bool,
    lineage_backed: bool,
) -> DirectionConfidenceResolution:
    side_scope = _normalize_side_scope(raw_side_scope)
    numeric = _coerce_decimal(raw_value)
    if numeric is None:
        return DirectionConfidenceResolution(
            value=None,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=side_scope is not None,
            side_scope=side_scope,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            lineage_backed=lineage_backed,
        )
    value = float(numeric)
    if value < 0.0 or value > 1.0:
        return DirectionConfidenceResolution(
            value=None,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=side_scope is not None,
            side_scope=side_scope,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            raw_value=value,
            lineage_backed=lineage_backed,
        )
    if side_scope is None:
        return DirectionConfidenceResolution(
            value=value,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=False,
            side_scope=None,
            failure_reason="non_side_aware_direction_confidence",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            raw_value=value,
            normalized_value_if_any=value,
            lineage_backed=lineage_backed,
        )
    if side_scope != proposed_side:
        return DirectionConfidenceResolution(
            value=value,
            source=source,
            is_present=True,
            is_supported_source=True,
            is_side_aware=True,
            side_scope=side_scope,
            failure_reason="invalid_direction_confidence_value",
            scale=scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            raw_value=value,
            normalized_value_if_any=value,
            lineage_backed=lineage_backed,
        )
    return DirectionConfidenceResolution(
        value=value,
        source=source,
        is_present=True,
        is_supported_source=True,
        is_side_aware=True,
        side_scope=side_scope,
        failure_reason=None,
        scale=scale,
        selected_stage=selected_stage,
        authority_status=authority_status,
        compatibility_alias_used=compatibility_alias_used,
        raw_value=value,
        normalized_value_if_any=value,
        lineage_backed=lineage_backed,
    )


def _resolve_direction_confidence(
    *,
    strategy_trace: Mapping[str, Any] | None,
    allowed_sources: list[str],
    side: str,
    signal_score: float | None,
    judge_confidence_live_producer_required: bool = False,
) -> DirectionConfidenceResolution:
    trace = strategy_trace if isinstance(strategy_trace, Mapping) else {}
    proposed_side = _normalize_side_scope(side)
    if proposed_side is None:
        return DirectionConfidenceResolution(
            value=None,
            source="unavailable",
            is_present=False,
            is_supported_source=False,
            is_side_aware=False,
            side_scope=None,
            failure_reason="invalid_direction_confidence_value",
        )

    def _build_resolution_for_source(
        *,
        source_name: str,
        raw_value: Any,
        raw_side_scope: Any,
    ) -> DirectionConfidenceResolution:
        source_scale = _resolve_source_scale(trace=trace, source=source_name)
        selected_stage = _resolve_source_stage(trace=trace, source=source_name)
        authority_status = _resolve_source_authority_status(
            trace=trace, source=source_name
        )
        compatibility_alias_used = _resolve_source_compatibility_alias_used(
            trace=trace, source=source_name
        )
        lineage_backed = _resolve_source_lineage_backed(
            trace=trace, source=source_name)
        if is_signed_score_scale(source_scale):
            return _resolve_signed_direction_confidence(
                raw_value=raw_value,
                source=source_name,
                proposed_side=proposed_side,
                scale=source_scale,
                selected_stage=selected_stage,
                authority_status=authority_status,
                compatibility_alias_used=compatibility_alias_used,
                lineage_backed=lineage_backed,
            )
        if is_normalized_confidence_scale(source_scale):
            return _resolve_unsigned_direction_confidence(
                raw_value=raw_value,
                source=source_name,
                proposed_side=proposed_side,
                raw_side_scope=raw_side_scope,
                scale=source_scale,
                selected_stage=selected_stage,
                authority_status=authority_status,
                compatibility_alias_used=compatibility_alias_used,
                lineage_backed=lineage_backed,
            )
        return DirectionConfidenceResolution(
            value=None,
            source=source_name,
            is_present=raw_value is not None,
            is_supported_source=True,
            is_side_aware=False,
            side_scope=_normalize_side_scope(raw_side_scope),
            failure_reason="direction_confidence_scale_unknown",
            scale=source_scale,
            selected_stage=selected_stage,
            authority_status=authority_status,
            compatibility_alias_used=compatibility_alias_used,
            lineage_backed=lineage_backed,
        )

    explicit_source = trace.get("direction_confidence_source")
    explicit_value = trace.get("direction_confidence")
    explicit_side_scope = trace.get("direction_confidence_side_scope")
    explicit_requested = (
        explicit_source is not None
        or explicit_value is not None
        or explicit_side_scope is not None
    )
    if explicit_requested:
        source_name = str(explicit_source).strip(
        ) if explicit_source is not None else "unavailable"
        if explicit_source is None:
            return DirectionConfidenceResolution(
                value=None,
                source="unavailable",
                is_present=explicit_value is not None,
                is_supported_source=False,
                is_side_aware=False,
                side_scope=_normalize_side_scope(explicit_side_scope),
                failure_reason="missing_direction_confidence_source",
            )
        if source_name not in set(allowed_sources):
            return DirectionConfidenceResolution(
                value=None,
                source=source_name,
                is_present=explicit_value is not None,
                is_supported_source=False,
                is_side_aware=False,
                side_scope=_normalize_side_scope(explicit_side_scope),
                failure_reason="unsupported_direction_confidence_source",
            )
        if explicit_value is None:
            return DirectionConfidenceResolution(
                value=None,
                source=source_name,
                is_present=False,
                is_supported_source=True,
                is_side_aware=False,
                side_scope=_normalize_side_scope(explicit_side_scope),
                failure_reason="direction_confidence_missing",
            )
        return _build_resolution_for_source(
            raw_value=explicit_value,
            source_name=source_name,
            raw_side_scope=explicit_side_scope,
        )

    for source in allowed_sources:
        if source == "signal_score" and signal_score is not None:
            return _build_resolution_for_source(
                raw_value=signal_score,
                source_name=source,
                raw_side_scope=None,
            )
        raw_value = _resolve_source_value(trace=trace, source=source)
        if raw_value is None:
            continue
        if source == "judge_confidence" and judge_confidence_live_producer_required:
            if trace.get("judge_confidence_live_producer_proof") is not True:
                return DirectionConfidenceResolution(
                    value=None,
                    source=source,
                    is_present=True,
                    is_supported_source=True,
                    is_side_aware=False,
                    side_scope=None,
                    failure_reason="judge_confidence_no_live_producer",
                    scale=_resolve_source_scale(trace=trace, source=source),
                    selected_stage=_resolve_source_stage(
                        trace=trace, source=source),
                    authority_status=_resolve_source_authority_status(
                        trace=trace, source=source),
                    compatibility_alias_used=_resolve_source_compatibility_alias_used(
                        trace=trace, source=source),
                    lineage_backed=_resolve_source_lineage_backed(
                        trace=trace, source=source),
                )
        return _build_resolution_for_source(
            raw_value=raw_value,
            source_name=source,
            raw_side_scope=_resolve_source_side_scope(
                trace=trace, source=source),
        )
    return DirectionConfidenceResolution(
        value=None,
        source="unavailable",
        is_present=False,
        is_supported_source=False,
        is_side_aware=False,
        side_scope=None,
        failure_reason="direction_confidence_missing",
    )


def _resolve_direction_confidence_reason(
    *,
    direction_failure_reason: str | None,
    violations: list[str],
) -> tuple[str | None, str | None]:
    if direction_failure_reason == "signed_score_not_allowed_as_direction_confidence":
        return (
            "LOW_VOL_DIRECTION_CONFIDENCE_CONTRACT_BLOCKED",
            direction_failure_reason,
        )
    if direction_failure_reason in _DIRECTION_CONFIDENCE_FAILURE_REASONS:
        return "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED", direction_failure_reason
    if "direction_confidence_below_threshold" in violations:
        return (
            "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED",
            "direction_confidence_below_threshold",
        )
    return None, None


def _resolve_direction_confidence_scale(resolution: DirectionConfidenceResolution) -> str:
    if resolution.source in _SIGNED_DIRECTION_CONFIDENCE_SOURCES:
        return "raw_signed_score"
    if resolution.source in {"strategy_confidence", "judge_confidence"}:
        return "normalized_confidence"
    return "unknown"


def _resolve_direction_confidence_status(
    *,
    direction_resolution: DirectionConfidenceResolution,
    direction_passed: bool,
    side_match: bool | None,
) -> str:
    failure_reason = direction_resolution.failure_reason
    if failure_reason in {
        "direction_confidence_missing",
        "missing_direction_confidence_source",
        "unsupported_direction_confidence_source",
    } or not direction_resolution.is_present:
        return "missing"
    if failure_reason == "invalid_direction_confidence_value":
        if side_match is False:
            return "wrong_side"
        return "invalid_range"
    if failure_reason == "non_side_aware_direction_confidence":
        return "wrong_side"
    if failure_reason == "signed_score_not_allowed_as_direction_confidence":
        return "contract_mismatch"
    if direction_passed:
        return "present_passed"
    return "present_below_threshold"


def _is_nrr062_testnet_short_direction_only_candidate(
    *,
    trading_mode: str,
    gate_mode: str,
    regime: str | None,
    side: str,
    direction_confidence_source: str,
    direction_confidence_scale: str,
    threshold_family: str,
    regime_confidence: float | None,
    resolved_min_regime_confidence: float | None,
    direction_confidence: float | None,
    resolved_min_direction_confidence: float | None,
    actual_tp_bps: Decimal | None,
    required_gross_tp_bps: Decimal | None,
    tp_fee_coverage_ratio: Decimal | None,
    min_tp_fee_coverage: float,
    rr_ratio: Decimal | None,
    min_rr: float,
    violations: list[str],
) -> bool:
    normalized_mode = str(trading_mode).strip()
    normalized_side = _normalize_side_scope(side)

    if normalized_mode not in _NRR062_TESTNET_SEGMENT_OVERRIDE_MODES:
        return False
    if gate_mode != "enforced":
        return False
    if regime != "LOW_VOLATILITY":
        return False
    if normalized_side != "SELL":
        return False
    if direction_confidence_source != "signal_score":
        return False
    if direction_confidence_scale != "raw_signed_score":
        return False
    if threshold_family != "raw_signed_score":
        return False
    if regime_confidence is None or resolved_min_regime_confidence is None:
        return False
    if float(regime_confidence) < float(resolved_min_regime_confidence):
        return False
    if direction_confidence is None or resolved_min_direction_confidence is None:
        return False
    if float(direction_confidence) >= float(resolved_min_direction_confidence):
        return False
    if actual_tp_bps is None or required_gross_tp_bps is None:
        return False
    if actual_tp_bps <= 0 or required_gross_tp_bps <= 0:
        return False
    if actual_tp_bps < required_gross_tp_bps:
        return False
    if tp_fee_coverage_ratio is None or tp_fee_coverage_ratio < Decimal(str(min_tp_fee_coverage)):
        return False
    if rr_ratio is None or rr_ratio < Decimal(str(min_rr)):
        return False
    if list(violations) != ["direction_confidence_below_threshold"]:
        return False
    return True


def _compute_tp_sl_bps(*, side: str, entry_price: Decimal, target_price: Decimal, stop_price: Decimal) -> tuple[Decimal | None, Decimal | None]:
    if entry_price <= 0:
        return None, None
    scale = Decimal("10000")
    if str(side).upper() == "BUY":
        actual_tp = (target_price - entry_price) / entry_price * scale
        actual_sl = (entry_price - stop_price) / entry_price * scale
    else:
        actual_tp = (entry_price - target_price) / entry_price * scale
        actual_sl = (stop_price - entry_price) / entry_price * scale
    return actual_tp, actual_sl


def _mapping_get_path(mapping: Mapping[str, Any] | None, path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_present_mapping_value(mapping: Mapping[str, Any] | None, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _mapping_get_path(mapping, path)
        if value is not None:
            return value
    return None


def _extract_observation_float(mapping: Mapping[str, Any] | None, *paths: tuple[str, ...]) -> float | None:
    return _to_optional_float(
        _coerce_decimal(_first_present_mapping_value(mapping, *paths))
    )


def _build_low_vol_observation_blocks(
    *,
    strategy_trace: Mapping[str, Any] | None,
    gate_cfg: Any,
    regime: str | None,
    regime_confidence: float | None,
    side: str,
    signal_score: float | None,
    strategy_id: str | None,
    symbol: str | None,
    trading_mode: str,
    gate_mode: str,
    direction_resolution: DirectionConfidenceResolution,
    resolved_regime_threshold: ResolvedLowVolThreshold,
    resolved_direction_threshold: ResolvedLowVolThreshold,
    entry_decimal: Decimal | None,
    target_decimal: Decimal | None,
    stop_decimal: Decimal | None,
    geometry_missing: bool,
    actual_tp_bps: Decimal | None,
    actual_sl_bps: Decimal | None,
    round_trip_fee_bps: Decimal,
    slippage_buffer_bps: Decimal,
    required_gross_tp_bps: Decimal,
    target_net_fee_multiple: Decimal,
    tp_fee_coverage_ratio: Decimal | None,
    rr_ratio: Decimal | None,
    expected_net_if_tp_bps: Decimal | None,
    expected_net_if_sl_bps: Decimal | None,
    threshold_failed: bool,
    violations: list[str],
    warnings: list[str],
    threshold_family: str = "unknown",
) -> dict[str, Any]:
    trace = strategy_trace if isinstance(strategy_trace, Mapping) else {}
    objective = _mapping_get_path(trace, ("objective",))
    objective_present = isinstance(objective, Mapping)
    observed_signal_score = _to_optional_float(
        _coerce_decimal(_resolve_source_value(
            trace=trace, source="signal_score"))
    )
    if observed_signal_score is None and signal_score is not None:
        observed_signal_score = signal_score

    final_score = _extract_observation_float(
        trace,
        ("final_score",),
        ("objective", "final_score"),
    )
    objective_score = _extract_observation_float(
        trace,
        ("score",),
        ("objective", "score"),
    )
    score_threshold = _extract_observation_float(
        trace,
        ("threshold",),
        ("active_threshold",),
        ("objective", "threshold"),
        ("objective", "active_threshold"),
        ("objective", "structure", "threshold"),
        ("objective", "structure", "active_threshold"),
    )
    score_margin = _extract_observation_float(
        trace,
        ("score_margin",),
        ("objective", "score_margin"),
        ("objective", "threshold_margin"),
        ("objective", "structure", "threshold_margin"),
    )
    judge_confidence = _extract_observation_float(
        trace,
        ("judge_confidence",),
        ("objective", "judge_confidence"),
    )
    strategy_confidence = _extract_observation_float(
        trace,
        ("strategy_confidence",),
        ("objective", "strategy_confidence"),
    )
    strategy_confidence_candidate = _extract_observation_float(
        trace,
        ("strategy_confidence_candidate",),
    )
    strategy_confidence_side_scope = _normalize_side_scope(
        trace.get("strategy_confidence_side_scope")
    )
    model_confidence = _extract_observation_float(
        trace,
        ("confidence",),
        ("model_confidence",),
        ("objective", "confidence"),
        ("objective", "model_confidence"),
    )
    final_score_raw = _extract_observation_float(
        trace,
        ("final_score_raw",),
        ("final_score",),
        ("objective", "final_score"),
    )
    judge_confidence_candidate = _extract_observation_float(
        trace,
        ("judge_confidence_candidate",),
        ("judge_confidence",),
        ("objective", "judge_confidence"),
    )
    active_threshold = _extract_observation_float(
        trace,
        ("active_threshold",),
        ("threshold",),
        ("objective", "threshold"),
        ("objective", "active_threshold"),
    )
    aurora_pillar_confidence_candidate = _extract_observation_float(
        trace,
        ("aurora_pillar_confidence_candidate",),
    )
    aurora_threshold_factor = _extract_observation_float(
        trace,
        ("aurora_threshold_factor",),
    )
    aurora_raw_score_to_threshold_ratio = _extract_observation_float(
        trace,
        ("aurora_raw_score_to_threshold_ratio",),
    )
    features_ts_ms = _extract_observation_float(
        trace,
        ("features_ts_ms",),
    )
    detector_event = _mapping_get_path(trace, ("detector_event",))
    detector_event_bar_close_ts_ms = _extract_observation_float(
        trace,
        ("detector_event", "bar_close_ts_ms"),
        ("bar_close_ts",),
    )
    decision_id = trace.get("decision_id")
    cycle_key = trace.get("cycle_key")

    pm_norm_10s = _extract_observation_float(
        trace,
        ("pm_norm_10s",),
        ("price_motion", "pm_norm_10s"),
        ("objective", "pm_norm_10s"),
    )
    pm_norm_60s = _extract_observation_float(
        trace,
        ("pm_norm_60s",),
        ("price_motion", "pm_norm_60s"),
        ("objective", "pm_norm_60s"),
    )
    pm_norm_300s = _extract_observation_float(
        trace,
        ("pm_norm_300s",),
        ("price_motion", "pm_norm_300s"),
        ("objective", "pm_norm_300s"),
    )
    vol_pct_10s = _extract_observation_float(
        trace,
        ("vol_pct_10s",),
        ("price_motion", "vol_pct_10s"),
        ("objective", "vol_pct_10s"),
    )
    vol_pct_60s = _extract_observation_float(
        trace,
        ("vol_pct_60s",),
        ("price_motion", "vol_pct_60s"),
        ("objective", "vol_pct_60s"),
    )
    vol_pct_300s = _extract_observation_float(
        trace,
        ("vol_pct_300s",),
        ("price_motion", "vol_pct_300s"),
        ("objective", "vol_pct_300s"),
    )
    ret_60s = _extract_observation_float(
        trace,
        ("ret_60s",),
        ("price_motion", "ret_60s"),
        ("analysis_payload", "ret_60s"),
        ("features", "ret_60s"),
        ("objective", "ret_60s"),
    )
    ret_300s = _extract_observation_float(
        trace,
        ("ret_300s",),
        ("price_motion", "ret_300s"),
        ("analysis_payload", "ret_300s"),
        ("features", "ret_300s"),
        ("objective", "ret_300s"),
    )
    spread_bps = _extract_observation_float(
        trace,
        ("spread_bps",),
        ("market", "spread_bps"),
        ("objective", "spread_bps"),
        ("objective", "market", "spread_bps"),
    )
    liquidity_kappa = _extract_observation_float(
        trace,
        ("liquidity_kappa",),
        ("market", "liquidity_kappa"),
        ("objective", "liquidity_kappa"),
        ("objective", "market", "liquidity_kappa"),
    )
    absorption = _extract_observation_float(
        trace,
        ("absorption",),
        ("market", "absorption"),
        ("objective", "absorption"),
        ("objective", "market", "absorption"),
    )

    direction_confidence = direction_resolution.value
    geometry_valid = bool(
        actual_tp_bps is not None
        and actual_sl_bps is not None
        and actual_tp_bps > 0
        and actual_sl_bps > 0
    )
    regime_passed = regime_confidence is not None and float(
        regime_confidence) >= resolved_regime_threshold.value
    direction_passed = (
        direction_resolution.failure_reason is None
        and direction_confidence is not None
        and float(direction_confidence) >= resolved_direction_threshold.value
    )
    proposed_side = _normalize_side_scope(side)
    direction_confidence_selected_scale = _resolve_direction_confidence_scale(
        direction_resolution
    )
    direction_confidence_selected_value = (
        direction_resolution.normalized_value_if_any
        if direction_resolution.normalized_value_if_any is not None
        else direction_resolution.raw_value
    )
    direction_confidence_selected_source = direction_resolution.source
    direction_confidence_side_match = (
        None
        if direction_resolution.side_scope is None or proposed_side is None
        else direction_resolution.side_scope == proposed_side
    )
    direction_confidence_required_threshold = resolved_direction_threshold.value
    direction_confidence_threshold_source = resolved_direction_threshold.source
    direction_confidence_margin = None
    _effective_dc_value = (
        direction_resolution.normalized_value_if_any
        if direction_resolution.normalized_value_if_any is not None
        else direction_resolution.value
    )
    if _effective_dc_value is not None:
        direction_confidence_margin = (
            _effective_dc_value
            - direction_confidence_required_threshold
        )
    confidence_resolution_status = _resolve_direction_confidence_status(
        direction_resolution=direction_resolution,
        direction_passed=direction_passed,
        side_match=direction_confidence_side_match,
    )
    tp_meets_required_gross = actual_tp_bps is not None and actual_tp_bps >= required_gross_tp_bps
    tp_fee_coverage_passed = (
        tp_fee_coverage_ratio is not None
        and tp_fee_coverage_ratio >= Decimal(str(gate_cfg.thresholds.min_tp_fee_coverage))
    )
    rr_passed = rr_ratio is not None and rr_ratio >= Decimal(
        str(gate_cfg.thresholds.min_rr))

    score_context = {
        "signal_score": observed_signal_score,
        "final_score": final_score,
        "objective_score": objective_score,
        "score_threshold": score_threshold,
        "score_margin": score_margin,
        "judge_confidence": judge_confidence,
        "strategy_confidence": strategy_confidence,
        "model_confidence": model_confidence,
        "active_threshold": active_threshold,
        "missing": {
            "signal_score": observed_signal_score is None,
            "final_score": final_score is None,
            "objective_score": objective_score is None,
            "score_threshold": score_threshold is None,
            "score_margin": score_margin is None,
            "judge_confidence": judge_confidence is None,
            "strategy_confidence": strategy_confidence is None,
            "model_confidence": model_confidence is None,
        },
    }
    price_motion_context = {
        "pm_norm_10s": pm_norm_10s,
        "pm_norm_60s": pm_norm_60s,
        "pm_norm_300s": pm_norm_300s,
        "vol_pct_10s": vol_pct_10s,
        "vol_pct_60s": vol_pct_60s,
        "vol_pct_300s": vol_pct_300s,
        "ret_60s": ret_60s,
        "ret_300s": ret_300s,
        "missing": {
            "pm_norm_10s": pm_norm_10s is None,
            "pm_norm_60s": pm_norm_60s is None,
            "pm_norm_300s": pm_norm_300s is None,
            "vol_pct_10s": vol_pct_10s is None,
            "vol_pct_60s": vol_pct_60s is None,
            "vol_pct_300s": vol_pct_300s is None,
            "ret_60s": ret_60s is None,
            "ret_300s": ret_300s is None,
        },
    }
    liquidity_context = {
        "spread_bps": spread_bps,
        "liquidity_kappa": liquidity_kappa,
        "absorption": absorption,
        "missing": {
            "spread_bps": spread_bps is None,
            "liquidity_kappa": liquidity_kappa is None,
            "absorption": absorption is None,
        },
    }
    thresholds = {
        "min_regime_confidence": resolved_regime_threshold.value,
        "min_direction_confidence": resolved_direction_threshold.value,
        "required_gross_tp_bps": float(required_gross_tp_bps),
        "min_tp_fee_coverage": float(gate_cfg.thresholds.min_tp_fee_coverage),
        "min_rr": float(gate_cfg.thresholds.min_rr),
        "round_trip_fee_bps": float(round_trip_fee_bps),
        "slippage_buffer_bps": float(slippage_buffer_bps),
        "target_net_fee_multiple": float(target_net_fee_multiple),
    }
    subcondition_verdicts = {
        "regime_confidence_passed": regime_passed,
        "direction_confidence_passed": direction_passed,
        "geometry_available": not geometry_missing,
        "geometry_valid": geometry_valid,
        "actual_tp_meets_required_gross_tp": tp_meets_required_gross,
        "tp_fee_coverage_passed": tp_fee_coverage_passed,
        "rr_passed": rr_passed,
        "threshold_failed": threshold_failed,
    }
    provenance_context = {
        "evaluated": True,
        "evaluation_stage": "post_safety_gate",
        "strategy_trace_present": bool(trace),
        "objective_present": objective_present,
        "decision_id": str(decision_id) if decision_id is not None else None,
        "cycle_key": str(cycle_key) if cycle_key is not None else None,
        "strategy_id": str(strategy_id) if strategy_id is not None else None,
        "symbol": str(symbol).upper() if symbol is not None else None,
        "trading_mode": str(trading_mode),
        "gate_mode": gate_mode,
        "regime": regime,
        "side": _normalize_side_scope(side),
        "features_ts_ms": features_ts_ms,
        "detector_event": {
            "bar_close_ts_ms": detector_event_bar_close_ts_ms,
        },
        "direction_confidence_allowed_sources": list(gate_cfg.direction_confidence.allowed_sources),
        "resolved_regime_threshold": {
            "value": resolved_regime_threshold.value,
            "source": resolved_regime_threshold.source,
            "strategy_id": resolved_regime_threshold.strategy_id,
            "symbol": resolved_regime_threshold.symbol,
            "regime_key": resolved_regime_threshold.regime_key,
        },
        "resolved_direction_threshold": {
            "value": resolved_direction_threshold.value,
            "source": resolved_direction_threshold.source,
            "strategy_id": resolved_direction_threshold.strategy_id,
            "symbol": resolved_direction_threshold.symbol,
            "regime_key": resolved_direction_threshold.regime_key,
        },
    }
    missing_inputs = {
        "entry_price": entry_decimal is None,
        "target_price": target_decimal is None,
        "stop_price": stop_decimal is None,
        "regime_confidence": regime_confidence is None,
        "direction_confidence": direction_confidence is None,
        "signal_score": observed_signal_score is None,
        "pm_norm_60s": price_motion_context["missing"]["pm_norm_60s"],
        "pm_norm_300s": price_motion_context["missing"]["pm_norm_300s"],
        "ret_60s": price_motion_context["missing"]["ret_60s"],
        "ret_300s": price_motion_context["missing"]["ret_300s"],
        "vol_pct_300s": price_motion_context["missing"]["vol_pct_300s"],
        "spread_bps": liquidity_context["missing"]["spread_bps"],
        "liquidity_kappa": liquidity_context["missing"]["liquidity_kappa"],
        "absorption": liquidity_context["missing"]["absorption"],
        "final_score": score_context["missing"]["final_score"],
        "objective_score": score_context["missing"]["objective_score"],
        "score_threshold": score_context["missing"]["score_threshold"],
        "score_margin": score_context["missing"]["score_margin"],
        "judge_confidence": score_context["missing"]["judge_confidence"],
        "strategy_confidence": score_context["missing"]["strategy_confidence"],
        "model_confidence": score_context["missing"]["model_confidence"],
    }
    missing_allowed_sources: list[str] = []
    for source in gate_cfg.direction_confidence.allowed_sources:
        if source == "signal_score" and observed_signal_score is None:
            missing_allowed_sources.append(source)
        elif source == "final_score" and final_score is None:
            missing_allowed_sources.append(source)
        elif source == "judge_confidence" and judge_confidence is None:
            missing_allowed_sources.append(source)
        elif source == "strategy_confidence" and strategy_confidence is None:
            missing_allowed_sources.append(source)

    return {
        "evaluated": True,
        "evaluation_stage": "post_safety_gate",
        "geometry_available": not geometry_missing,
        "geometry_valid": geometry_valid,
        "missing_inputs": missing_inputs,
        "score_context": score_context,
        "price_motion_context": price_motion_context,
        "liquidity_context": liquidity_context,
        "thresholds": thresholds,
        "subcondition_verdicts": subcondition_verdicts,
        "provenance_context": provenance_context,
        "economics_context": {
            "entry_price": _to_optional_float(entry_decimal),
            "target_price": _to_optional_float(target_decimal),
            "stop_price": _to_optional_float(stop_decimal),
            "actual_tp_bps": _to_optional_float(actual_tp_bps),
            "actual_sl_bps": _to_optional_float(actual_sl_bps),
            "expected_net_if_tp_bps": _to_optional_float(expected_net_if_tp_bps),
            "expected_net_if_sl_bps": _to_optional_float(expected_net_if_sl_bps),
            "tp_fee_coverage_ratio": _to_optional_float(tp_fee_coverage_ratio),
            "rr_ratio": _to_optional_float(rr_ratio),
            "required_gross_tp_bps": float(required_gross_tp_bps),
            "round_trip_fee_bps": float(round_trip_fee_bps),
            "slippage_buffer_bps": float(slippage_buffer_bps),
        },
        "direction_confidence_context": {
            "value": direction_confidence,
            "source": direction_resolution.source,
            "side_scope": direction_resolution.side_scope,
            "present": direction_resolution.is_present,
            "supported_source": direction_resolution.is_supported_source,
            "is_side_aware": direction_resolution.is_side_aware,
            "failure_reason": direction_resolution.failure_reason,
            "required": bool(gate_cfg.direction_confidence.required),
            "missing_policy": str(gate_cfg.direction_confidence.missing_policy),
            "threshold": resolved_direction_threshold.value,
            "threshold_family": threshold_family,
            "normalization_applied": threshold_family == "raw_signed_score",
            "passed": direction_passed,
        },
        "direction_confidence_selection": {
            "selected_source": direction_confidence_selected_source,
            "selected_scale": direction_confidence_selected_scale,
            "raw_value": direction_resolution.raw_value,
            "normalized_value_if_any": direction_resolution.normalized_value_if_any,
            "threshold_family": threshold_family,
            "threshold_value": direction_confidence_required_threshold,
            "threshold_source": direction_confidence_threshold_source,
            "selected_stage": direction_resolution.selected_stage,
            "authority_status": direction_resolution.authority_status,
            "side_scope": direction_resolution.side_scope,
            "compatibility_alias_used": direction_resolution.compatibility_alias_used,
        },
        "direction_confidence_selected_value": direction_confidence_selected_value,
        "direction_confidence_selected_source": direction_confidence_selected_source,
        "direction_confidence_selected_scale": direction_confidence_selected_scale,
        "direction_confidence_required_threshold": direction_confidence_required_threshold,
        "direction_confidence_threshold_source": direction_confidence_threshold_source,
        "direction_confidence_margin": direction_confidence_margin,
        "direction_confidence_side_match": direction_confidence_side_match,
        "proposed_side": proposed_side,
        "signal_score_raw": observed_signal_score,
        "signal_score_abs": None if observed_signal_score is None else abs(observed_signal_score),
        "strategy_confidence_candidate": strategy_confidence_candidate,
        "strategy_confidence_side_scope": strategy_confidence_side_scope,
        "final_score_raw": final_score_raw,
        "judge_confidence_candidate": judge_confidence_candidate,
        "active_allowed_sources": list(gate_cfg.direction_confidence.allowed_sources),
        "missing_allowed_sources": missing_allowed_sources,
        "missing_source_list": missing_allowed_sources,
        "confidence_resolution_status": confidence_resolution_status,
        "aurora_pillar_confidence_candidate": aurora_pillar_confidence_candidate,
        "aurora_threshold_factor": aurora_threshold_factor,
        "aurora_raw_score_to_threshold_ratio": aurora_raw_score_to_threshold_ratio,
        "decision_id": str(decision_id) if decision_id is not None else None,
        "cycle_key": str(cycle_key) if cycle_key is not None else None,
        "features_ts_ms": features_ts_ms,
        "detector_event": detector_event if isinstance(detector_event, Mapping) else {
            "bar_close_ts_ms": detector_event_bar_close_ts_ms,
        },
        "observation_summary": {
            "threshold_failed": threshold_failed,
            "violations": list(violations),
            "warnings": list(warnings),
        },
    }


def evaluate_low_vol_cost_floor_gate(
    *,
    gate_cfg: Any,
    trading_mode: str,
    regime: str | None,
    regime_confidence: float | None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    side: str,
    entry_price: Any,
    target_price: Any,
    stop_price: Any,
    strategy_trace: Mapping[str, Any] | None,
    signal_score: float | None,
    reduce_only: bool = False,
) -> LowVolCostFloorEvaluation:
    gate_mode = _resolve_gate_mode(
        enabled=bool(gate_cfg.enabled),
        trading_mode=str(trading_mode),
        enforce_in_modes=list(gate_cfg.enforce_in_modes),
        observe_only_in_modes=list(gate_cfg.observe_only_in_modes),
    )
    active = (
        not reduce_only
        and regime is not None
        and regime in set(gate_cfg.regimes)
        and gate_mode != "disabled"
    )
    if not active:
        return LowVolCostFloorEvaluation(
            active=False,
            gate_mode=gate_mode,
            block=False,
            threshold_failed=False,
            reason="LOW_VOL_COST_FLOOR_DISABLED",
            details={
                "trading_mode": str(trading_mode),
                "gate_mode": gate_mode,
                "regime": regime,
                "threshold_failed": False,
                "violations": [],
                "warnings": [],
            },
        )

    entry_decimal = _coerce_decimal(entry_price)
    target_decimal = _coerce_decimal(target_price)
    stop_decimal = _coerce_decimal(stop_price)

    round_trip_fee_bps = Decimal(
        str(gate_cfg.fee.open_fee_bps)) + Decimal(str(gate_cfg.fee.close_fee_bps))
    slippage_buffer_bps = Decimal(str(gate_cfg.slippage.buffer_bps))
    target_net_fee_multiple = Decimal(
        str(gate_cfg.thresholds.target_net_fee_multiple))
    required_gross_tp_bps = round_trip_fee_bps * \
        (Decimal("1") + target_net_fee_multiple) + slippage_buffer_bps

    resolved_regime_threshold = _resolve_low_vol_threshold(
        mapping=gate_cfg.thresholds.min_regime_confidence_by_regime,
        overrides_by_strategy_symbol=getattr(
            gate_cfg.thresholds,
            "min_regime_confidence_overrides_by_strategy_symbol",
            None,
        ),
        strategy_id=strategy_id,
        symbol=symbol,
        regime=regime,
    )
    resolved_min_regime_confidence = resolved_regime_threshold.value
    direction_resolution = _resolve_direction_confidence(
        strategy_trace=strategy_trace,
        allowed_sources=(
            list(gate_cfg.direction_confidence.raw_signed_score_sources)
            + list(gate_cfg.direction_confidence.normalized_confidence_sources)
        ),
        side=side,
        signal_score=signal_score,
        judge_confidence_live_producer_required=bool(
            gate_cfg.direction_confidence.judge_confidence_live_producer_required
        ),
    )
    direction_confidence = direction_resolution.value
    direction_confidence_source = direction_resolution.source
    direction_confidence_scale = _resolve_direction_confidence_scale(
        direction_resolution)
    _raw_resolution_scale = str(direction_resolution.scale or "unknown")

    # Route threshold resolution by source scale family.
    if is_signed_score_scale(_raw_resolution_scale):
        _raw_map = getattr(gate_cfg.thresholds, "min_raw_score_by_regime", None) \
            or gate_cfg.thresholds.min_direction_confidence_by_regime
        _raw_overrides = getattr(
            gate_cfg.thresholds, "min_raw_score_overrides_by_strategy_symbol", None)
        resolved_direction_threshold = _resolve_low_vol_threshold(
            mapping=_raw_map,
            overrides_by_strategy_symbol=_raw_overrides,
            strategy_id=strategy_id,
            symbol=symbol,
            regime=regime,
        )
        threshold_family = "raw_signed_score"
    elif is_normalized_confidence_scale(_raw_resolution_scale):
        _norm_map = getattr(gate_cfg.thresholds, "min_normalized_confidence_by_regime", None) \
            or gate_cfg.thresholds.min_direction_confidence_by_regime
        _norm_overrides = getattr(
            gate_cfg.thresholds, "min_normalized_confidence_overrides_by_strategy_symbol", None)
        resolved_direction_threshold = _resolve_low_vol_threshold(
            mapping=_norm_map,
            overrides_by_strategy_symbol=_norm_overrides,
            strategy_id=strategy_id,
            symbol=symbol,
            regime=regime,
        )
        threshold_family = "normalized_confidence"
    else:
        # Unknown scale — fall back to legacy mapping; gate will append violation below.
        resolved_direction_threshold = _resolve_low_vol_threshold(
            mapping=gate_cfg.thresholds.min_direction_confidence_by_regime,
            overrides_by_strategy_symbol=getattr(
                gate_cfg.thresholds, "min_direction_confidence_overrides_by_strategy_symbol", None
            ),
            strategy_id=strategy_id,
            symbol=symbol,
            regime=regime,
        )
        threshold_family = "unknown"
    resolved_min_direction_confidence = resolved_direction_threshold.value

    actual_tp_bps: Decimal | None = None
    actual_sl_bps: Decimal | None = None
    tp_fee_coverage_ratio: Decimal | None = None
    rr_ratio: Decimal | None = None
    expected_net_if_tp_bps: Decimal | None = None
    expected_net_if_sl_bps: Decimal | None = None
    violations: list[str] = []
    warnings: list[str] = []

    geometry_missing = entry_decimal is None or target_decimal is None or stop_decimal is None
    if geometry_missing:
        geometry_policy = str(gate_cfg.geometry.missing_policy)
        if bool(gate_cfg.geometry.require_tpsl):
            if geometry_policy == "fail_closed":
                violations.append("geometry_missing")
            elif geometry_policy == "warn_and_allow":
                warnings.append(
                    "LOW_VOL_COST_FLOOR_UNSCORABLE:geometry_missing")
        elif geometry_policy == "warn_and_allow":
            warnings.append("LOW_VOL_COST_FLOOR_UNSCORABLE:geometry_missing")
    else:
        actual_tp_bps, actual_sl_bps = _compute_tp_sl_bps(
            side=side,
            entry_price=entry_decimal,
            target_price=target_decimal,
            stop_price=stop_decimal,
        )
        if actual_tp_bps is None or actual_sl_bps is None or actual_tp_bps <= 0 or actual_sl_bps <= 0:
            geometry_policy = str(gate_cfg.geometry.missing_policy)
            if geometry_policy == "fail_closed":
                violations.append("geometry_invalid")
            elif geometry_policy == "warn_and_allow":
                warnings.append(
                    "LOW_VOL_COST_FLOOR_UNSCORABLE:geometry_invalid")
        else:
            tp_fee_coverage_ratio = actual_tp_bps / \
                round_trip_fee_bps if round_trip_fee_bps > 0 else None
            rr_ratio = actual_tp_bps / actual_sl_bps if actual_sl_bps > 0 else None
            expected_net_if_tp_bps = actual_tp_bps - \
                round_trip_fee_bps - slippage_buffer_bps
            expected_net_if_sl_bps = - \
                (actual_sl_bps + round_trip_fee_bps + slippage_buffer_bps)
            if regime_confidence is None or float(regime_confidence) < resolved_min_regime_confidence:
                violations.append("regime_confidence_below_threshold")
            if direction_resolution.failure_reason is not None:
                direction_policy = str(
                    gate_cfg.direction_confidence.missing_policy)
                if bool(gate_cfg.direction_confidence.required):
                    if direction_policy == "fail_closed":
                        violations.append(direction_resolution.failure_reason)
                    elif direction_policy == "warn_and_allow":
                        warnings.append(
                            f"LOW_VOL_COST_FLOOR_UNSCORABLE:{direction_resolution.failure_reason}")
                elif direction_policy == "warn_and_allow":
                    warnings.append(
                        f"LOW_VOL_COST_FLOOR_UNSCORABLE:{direction_resolution.failure_reason}")
            elif threshold_family == "unknown":
                violations.append("direction_confidence_scale_unknown")
            elif float(direction_confidence) < resolved_min_direction_confidence:
                violations.append("direction_confidence_below_threshold")
            if actual_tp_bps < required_gross_tp_bps:
                violations.append("actual_tp_bps_below_required_gross_tp")
            if tp_fee_coverage_ratio is not None and tp_fee_coverage_ratio < Decimal(str(gate_cfg.thresholds.min_tp_fee_coverage)):
                violations.append("tp_fee_coverage_below_min")
            if rr_ratio is not None and rr_ratio < Decimal(str(gate_cfg.thresholds.min_rr)):
                violations.append("rr_ratio_below_min")

    direction_confidence_reason, direction_confidence_failure_reason = _resolve_direction_confidence_reason(
        direction_failure_reason=direction_resolution.failure_reason,
        violations=violations,
    )
    threshold_failed = bool(violations)
    original_gate_reason = "LOW_VOL_COST_FLOOR_BLOCKED" if threshold_failed and gate_mode == "enforced" else (
        "LOW_VOL_COST_FLOOR_OBSERVED" if gate_mode == "observe_only" else "LOW_VOL_COST_FLOOR_PASS"
    )
    original_reason = direction_confidence_reason or original_gate_reason
    nrr062_segment_override_applied = _is_nrr062_testnet_short_direction_only_candidate(
        trading_mode=str(trading_mode),
        gate_mode=gate_mode,
        regime=regime,
        side=side,
        direction_confidence_source=direction_confidence_source,
        direction_confidence_scale=direction_confidence_scale,
        threshold_family=threshold_family,
        regime_confidence=regime_confidence,
        resolved_min_regime_confidence=resolved_min_regime_confidence,
        direction_confidence=direction_confidence,
        resolved_min_direction_confidence=resolved_min_direction_confidence,
        actual_tp_bps=actual_tp_bps,
        required_gross_tp_bps=required_gross_tp_bps,
        tp_fee_coverage_ratio=tp_fee_coverage_ratio,
        min_tp_fee_coverage=float(gate_cfg.thresholds.min_tp_fee_coverage),
        rr_ratio=rr_ratio,
        min_rr=float(gate_cfg.thresholds.min_rr),
        violations=violations,
    )
    block = threshold_failed and gate_mode == "enforced" and not nrr062_segment_override_applied
    gate_reason = "LOW_VOL_COST_FLOOR_BLOCKED" if block else (
        "LOW_VOL_COST_FLOOR_OBSERVED" if gate_mode == "observe_only" else "LOW_VOL_COST_FLOOR_PASS"
    )
    reason = (
        "LOW_VOL_COST_FLOOR_SEGMENT_OVERRIDE_ALLOW"
        if nrr062_segment_override_applied
        else original_reason
    )
    observation_blocks = _build_low_vol_observation_blocks(
        strategy_trace=strategy_trace,
        gate_cfg=gate_cfg,
        regime=regime,
        regime_confidence=regime_confidence,
        side=side,
        signal_score=signal_score,
        strategy_id=strategy_id,
        symbol=symbol,
        trading_mode=str(trading_mode),
        gate_mode=gate_mode,
        direction_resolution=direction_resolution,
        resolved_regime_threshold=resolved_regime_threshold,
        resolved_direction_threshold=resolved_direction_threshold,
        entry_decimal=entry_decimal,
        target_decimal=target_decimal,
        stop_decimal=stop_decimal,
        geometry_missing=geometry_missing,
        actual_tp_bps=actual_tp_bps,
        actual_sl_bps=actual_sl_bps,
        round_trip_fee_bps=round_trip_fee_bps,
        slippage_buffer_bps=slippage_buffer_bps,
        required_gross_tp_bps=required_gross_tp_bps,
        target_net_fee_multiple=target_net_fee_multiple,
        tp_fee_coverage_ratio=tp_fee_coverage_ratio,
        rr_ratio=rr_ratio,
        expected_net_if_tp_bps=expected_net_if_tp_bps,
        expected_net_if_sl_bps=expected_net_if_sl_bps,
        threshold_failed=threshold_failed,
        violations=violations,
        warnings=warnings,
        threshold_family=threshold_family,
    )
    return LowVolCostFloorEvaluation(
        active=True,
        gate_mode=gate_mode,
        block=block,
        threshold_failed=threshold_failed,
        reason=gate_reason,
        details={
            "reason": reason,
            "gate_reason": gate_reason,
            "regime": regime,
            "regime_confidence": regime_confidence,
            "resolved_min_regime_confidence": resolved_min_regime_confidence,
            "resolved_min_regime_confidence_source": resolved_regime_threshold.source,
            "resolved_min_regime_confidence_strategy_id": resolved_regime_threshold.strategy_id,
            "resolved_min_regime_confidence_symbol": resolved_regime_threshold.symbol,
            "resolved_min_regime_confidence_regime_key": resolved_regime_threshold.regime_key,
            "side": _normalize_side_scope(side),
            "direction_confidence": direction_confidence,
            "direction_confidence_source": direction_confidence_source,
            "direction_confidence_side_scope": direction_resolution.side_scope,
            "direction_confidence_is_side_aware": direction_resolution.is_side_aware,
            "direction_confidence_supported_source": direction_resolution.is_supported_source,
            "direction_confidence_required": bool(gate_cfg.direction_confidence.required),
            "direction_confidence_missing_policy": str(gate_cfg.direction_confidence.missing_policy),
            "direction_confidence_failure_reason": direction_confidence_failure_reason,
            "direction_confidence_reason": direction_confidence_reason,
            "direction_confidence_threshold_family": threshold_family,
            "resolved_min_direction_confidence": resolved_min_direction_confidence,
            "resolved_min_direction_confidence_source": resolved_direction_threshold.source,
            "resolved_min_direction_confidence_strategy_id": resolved_direction_threshold.strategy_id,
            "resolved_min_direction_confidence_symbol": resolved_direction_threshold.symbol,
            "resolved_min_direction_confidence_regime_key": resolved_direction_threshold.regime_key,
            "entry_price": _to_optional_float(entry_decimal),
            "target_price": _to_optional_float(target_decimal),
            "stop_price": _to_optional_float(stop_decimal),
            "actual_tp_bps": _to_optional_float(actual_tp_bps),
            "actual_sl_bps": _to_optional_float(actual_sl_bps),
            "round_trip_fee_bps": float(round_trip_fee_bps),
            "required_gross_tp_bps": float(required_gross_tp_bps),
            "target_net_fee_multiple": float(target_net_fee_multiple),
            "tp_fee_coverage_ratio": _to_optional_float(tp_fee_coverage_ratio),
            "rr_ratio": _to_optional_float(rr_ratio),
            "expected_net_if_tp_bps": _to_optional_float(expected_net_if_tp_bps),
            "expected_net_if_sl_bps": _to_optional_float(expected_net_if_sl_bps),
            "trading_mode": str(trading_mode),
            "strategy_id": str(strategy_id) if strategy_id is not None else None,
            "symbol": str(symbol).upper() if symbol is not None else None,
            "gate_mode": gate_mode,
            "nrr062_segment_override_applied": nrr062_segment_override_applied,
            "nrr062_segment_override_name": _NRR062_TESTNET_SEGMENT_OVERRIDE_NAME
            if nrr062_segment_override_applied else None,
            "nrr062_segment_override_no_production": nrr062_segment_override_applied,
            "original_nrr062_reason": original_gate_reason if nrr062_segment_override_applied else None,
            "original_low_vol_reason": original_reason if nrr062_segment_override_applied else None,
            "original_direction_confidence": direction_confidence if nrr062_segment_override_applied else None,
            "original_regime_confidence": regime_confidence if nrr062_segment_override_applied else None,
            "selected_source": direction_confidence_source,
            "selected_scale": direction_confidence_scale,
            "threshold_family": threshold_family,
            "would_block": threshold_failed and gate_mode == "observe_only",
            "would_block_direction_confidence": gate_mode == "observe_only"
            and direction_confidence_reason is not None,
            "threshold_failed": threshold_failed,
            "violations": list(violations),
            "warnings": list(warnings),
            **observation_blocks,
        },
    )
