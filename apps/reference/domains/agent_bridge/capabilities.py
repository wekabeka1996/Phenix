"""Read-only execution capability descriptors for Agent Bridge P5."""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from apps.reference.domains.execution_position.contracts import BracketOrderPayload
from apps.reference.domains.execution_position.guards.qty_normalizer import normalize_qty
from apps.reference.domains.execution_position.utils import quantize_stop_price

from .contracts import (
    ExecutionCapabilityDescriptorV0,
    ExecutionReadinessSummaryV0,
    SymbolConstraintSummaryV0,
    ExecutionReadinessSnapshotV0,
)
from .exchange_info import CACHE_REF, PARITY_REF, compare_filter_parity


CONFIG_REF = "aurora://config/instruments#precision"
FILTER_REF = "aurora://execution-position/runtime#exchange-filter-cache"
NORMALIZER_REF = "aurora://execution-position/guards/qty-normalizer"
PRICE_REF = "aurora://execution-position/utils#quantize-stop-price"
CLOSE_REF = "aurora://execution-position/close-executor#reduce-only"
PROTECT_REF = "aurora://execution-position/bracket-manager#reduce-only"
CONTRACT_REF = "aurora://execution-position/contracts#bracket-order-payload"
FILTER_FRESH_MS = 15 * 60 * 1000


def _decimal_text(value: Any, *, allow_zero: bool = False) -> Optional[str]:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or (number < 0 if allow_zero else number <= 0):
        return None
    return format(number, "f")


def _loaded_instrument(runtime: Any, symbol: str) -> Any | None:
    config = getattr(runtime, "config", None)
    instruments = getattr(config, "instruments", None)
    if isinstance(instruments, Mapping):
        return instruments.get(symbol)
    return None


def _runtime_filter(runtime: Any, symbol: str) -> Any | None:
    for name in ("exchange_filter_cache", "_exchange_filter_cache", "filter_cache"):
        cache = getattr(runtime, name, None)
        filters = getattr(cache, "_filters", None) if cache is not None else None
        if isinstance(filters, Mapping) and symbol in filters:
            return filters[symbol]
    return None


def _constraint_values(owner: Any) -> dict[str, Optional[str | bool]]:
    return {
        "tick_size": _decimal_text(getattr(owner, "tick_size", None)),
        "step_size": _decimal_text(getattr(owner, "step_size", None)),
        "min_qty": _decimal_text(getattr(owner, "min_qty", None), allow_zero=True),
        "min_notional": _decimal_text(
            getattr(owner, "min_notional", None), allow_zero=True
        ),
        "max_notional_known": False,
        "max_position_known": False,
    }


def build_execution_capability_descriptors(
    *,
    runtime: Any | None,
    symbols: Iterable[str],
    produced_ts_ms: int,
    public_exchange_info: Any | None = None,
) -> tuple[
    list[ExecutionCapabilityDescriptorV0],
    list[SymbolConstraintSummaryV0],
    ExecutionReadinessSummaryV0,
]:
    """Inspect allowlisted owner state without calling adapters or executors."""

    normalized = list(
        dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip())
    )
    descriptors: list[ExecutionCapabilityDescriptorV0] = []
    summaries: list[SymbolConstraintSummaryV0] = []

    for symbol in normalized:
        runtime_filter = _runtime_filter(runtime, symbol) if runtime is not None else None
        configured = _loaded_instrument(runtime, symbol) if runtime is not None else None
        exchange_row = (
            public_exchange_info.get_symbol(symbol, produced_ts_ms)
            if public_exchange_info is not None
            else None
        )
        parity = compare_filter_parity(symbol, configured, exchange_row)
        exchange_complete = bool(
            exchange_row is not None
            and all(getattr(exchange_row, name, None) is not None for name in (
                "tick_size", "step_size", "min_qty", "min_notional"
            ))
        )
        fresh_public = bool(
            exchange_complete
            and getattr(exchange_row, "freshness", None) == "fresh"
            and getattr(exchange_row, "fetch_status", None) == "ok"
        )
        normalization_owner = runtime_filter or configured
        owner = normalization_owner or exchange_row
        values = _constraint_values(owner) if owner is not None else {}
        core_valid = bool(
            values
            and values.get("tick_size")
            and values.get("step_size")
            and values.get("min_qty") is not None
        )
        minimum_known = bool(values and values.get("min_notional") is not None)
        required_valid = core_valid and minimum_known

        filter_source = str(getattr(runtime_filter, "source", "") or "").lower()
        filter_ts = getattr(runtime_filter, "updated_at_ms", None)
        fresh_exchange = bool(
            runtime_filter is not None
            and filter_source in {"live", "exchange"}
            and isinstance(filter_ts, int)
            and 0 <= produced_ts_ms - filter_ts <= FILTER_FRESH_MS
        )
        diagnostic_state = None
        if fresh_public and configured is not None and parity.severity in {"match", "minor_mismatch"}:
            filter_status = "ready"
            evidence = "exchange_confirmed"
            source = f"public_{getattr(public_exchange_info, 'environment', 'exchange')}"
            freshness = "fresh"
            missing_reason = None
            diagnostic_state = "exchange_confirmed"
            detail = f"Fresh public exchange filters are complete; parity={parity.severity}."
            source_ts = exchange_row.source_ts_ms or exchange_row.fetched_ts_ms
        elif fresh_public and parity.severity == "material_mismatch":
            filter_status = "degraded"
            evidence = "exchange_confirmed"
            source = f"public_{getattr(public_exchange_info, 'environment', 'exchange')}"
            freshness = "fresh"
            missing_reason = "exchange_filter_parity_material_mismatch"
            diagnostic_state = "parity_mismatch"
            detail = "Fresh public exchange filters materially differ from configured constraints."
            source_ts = exchange_row.source_ts_ms or exchange_row.fetched_ts_ms
        elif fresh_public and parity.severity == "configured_missing":
            filter_status = "degraded"
            evidence = "exchange_confirmed"
            source = f"public_{getattr(public_exchange_info, 'environment', 'exchange')}"
            freshness = "fresh"
            missing_reason = "configured_symbol_constraints_missing"
            diagnostic_state = "configured_missing"
            detail = "Fresh public filters exist, but canonical configured constraints are incomplete."
            source_ts = exchange_row.source_ts_ms or exchange_row.fetched_ts_ms
        elif exchange_row is not None and parity.severity == "stale_exchange_info" and configured is not None:
            filter_status = "degraded"
            evidence = "configured_only"
            source = "typed_config_with_stale_public_cache"
            freshness = "stale"
            missing_reason = "public_exchange_info_stale"
            diagnostic_state = "stale_exchange_info"
            detail = "Configured constraints remain available, but public exchange metadata is stale."
            source_ts = exchange_row.source_ts_ms or exchange_row.fetched_ts_ms
        elif exchange_row is not None and parity.severity == "exchange_missing" and configured is not None:
            filter_status = "degraded"
            evidence = "configured_only"
            source = "typed_config"
            freshness = "unknown"
            missing_reason = "public_exchange_required_filter_missing"
            diagnostic_state = "exchange_missing"
            detail = "Configured constraints remain available, but required public filters are missing."
            source_ts = exchange_row.source_ts_ms or exchange_row.fetched_ts_ms
        elif fresh_exchange and required_valid:
            filter_status = "ready"
            evidence = "exchange_confirmed"
            source = filter_source
            freshness = "fresh"
            missing_reason = None
            detail = "Fresh runtime exchange-filter evidence is available."
            source_ts = filter_ts
            diagnostic_state = "exchange_confirmed"
        elif runtime_filter is not None and core_valid:
            filter_status = "degraded"
            evidence = "configured_only" if filter_source == "static" else "runtime_owner"
            source = filter_source or "runtime_cache_unknown_source"
            freshness = "stale" if filter_ts else "unknown"
            missing_reason = (
                "exchange_filter_min_notional_missing"
                if not minimum_known
                else "exchange_filter_not_fresh_confirmed"
            )
            detail = (
                "Runtime filter values are partial; min-notional evidence is unavailable."
                if not minimum_known
                else "Runtime filter values exist, but fresh exchange confirmation is unavailable."
            )
            source_ts = filter_ts
            diagnostic_state = "configured_only"
        elif configured is not None and core_valid:
            filter_status = "degraded"
            evidence = "configured_only"
            source = "typed_config"
            freshness = "unknown"
            missing_reason = (
                "configured_min_notional_missing"
                if not minimum_known
                else "exchange_filter_not_runtime_confirmed"
            )
            detail = (
                "Canonical typed constraints are loaded; exchange parity is not confirmed."
                if minimum_known
                else "Canonical constraints are partial and min-notional is unavailable."
            )
            source_ts = produced_ts_ms
            diagnostic_state = "configured_only"
        else:
            filter_status = "missing"
            evidence = "unavailable"
            source = "missing"
            freshness = "missing"
            missing_reason = "symbol_constraints_unavailable"
            detail = "Neither runtime filters nor canonical symbol constraints are available."
            source_ts = None
            diagnostic_state = "unavailable"

        descriptors.append(
            ExecutionCapabilityDescriptorV0(
                name="exchange_filter_constraints",
                symbol=symbol,
                status=filter_status,
                evidence_level=evidence,
                owner="execution_position.exchange_filter_cache",
                source_ts_ms=source_ts,
                detail=detail,
                constraints=values,
                raw_ref=(CACHE_REF if exchange_row is not None else FILTER_REF if runtime_filter is not None else CONFIG_REF),
                missing_reason=missing_reason,
                diagnostic_state=diagnostic_state,
            )
        )
        missing_fields = [
            name
            for name in ("tick_size", "step_size", "min_qty", "min_notional")
            if not values or values.get(name) is None
        ]
        missing_fields.extend(["max_notional", "max_position"])
        summaries.append(
            SymbolConstraintSummaryV0(
                symbol=symbol,
                status=filter_status,
                evidence_level=evidence,
                filter_source=source,
                source_ts_ms=source_ts,
                freshness=freshness,
                tick_size=values.get("tick_size") if values else None,
                step_size=values.get("step_size") if values else None,
                min_qty=values.get("min_qty") if values else None,
                min_notional=values.get("min_notional") if values else None,
                missing_fields=missing_fields,
                parity=parity.severity,
                field_parity=parity.fields,
                exchange_values=parity.exchange_values,
                parity_ref=PARITY_REF if exchange_row is not None else None,
            )
        )

        normalizer_owner_available = bool(
            runtime is not None
            and normalization_owner is not None
            and core_valid
            and callable(normalize_qty)
            and callable(quantize_stop_price)
        )
        normalizers_ready = normalizer_owner_available and minimum_known
        normalization_status = (
            "ready" if normalizers_ready
            else "degraded" if normalizer_owner_available
            else "missing"
        )
        descriptors.append(
            ExecutionCapabilityDescriptorV0(
                name="precision_minimum_normalization",
                symbol=symbol,
                status=normalization_status,
                evidence_level="runtime_owner" if normalizer_owner_available else "unavailable",
                owner="execution_position.qty_normalizer+price_quantizer",
                source_ts_ms=produced_ts_ms if normalizers_ready else None,
                detail=(
                    "Runtime owner can resolve the symbol, floor quantity to step size, "
                    "quantize price to tick size, and fail closed on min quantity/notional."
                    if normalizers_ready
                    else "Runtime normalizers exist, but a symbol minimum constraint is unavailable."
                    if normalizer_owner_available
                    else "Runtime normalization owner or symbol constraints are unavailable."
                ),
                constraints={
                    "can_normalize_qty": normalizer_owner_available,
                    "can_normalize_price": normalizer_owner_available,
                    "can_check_min_notional": normalizers_ready,
                    "can_resolve_symbol": normalization_owner is not None,
                    "unknown_symbol_fails_closed": True,
                },
                raw_ref=f"{NORMALIZER_REF};{PRICE_REF}",
                missing_reason=(
                    None if normalizers_ready
                    else "min_notional_constraint_unavailable" if normalizer_owner_available
                    else "normalization_owner_unavailable"
                ),
            )
        )

    contract_ready = runtime is not None and "reduce_only" in BracketOrderPayload.model_fields
    close_owner = getattr(runtime, "_close_exec", None) if runtime is not None else None
    protect_owner = getattr(runtime, "_bracket_mgr", None) if runtime is not None else None
    reduce_specs = [
        (
            "reduce_only_order_parameter",
            contract_ready,
            "execution_position.contracts.BracketOrderPayload",
            CONTRACT_REF,
            "Typed bracket request contract explicitly represents reduce_only.",
        ),
        (
            "close_path_reduce_only_enforcement",
            close_owner is not None and callable(getattr(close_owner, "_submit_close_order", None)),
            "execution_position.flows.close.CloseExecutor",
            CLOSE_REF,
            "Runtime CloseExecutor owns a dedicated reduce-only close submission path.",
        ),
        (
            "protect_path_reduce_only_enforcement",
            protect_owner is not None and callable(getattr(protect_owner, "place_brackets_parallel", None)),
            "execution_position.flows.manage.BracketManager",
            PROTECT_REF,
            "Runtime BracketManager owns reduce-only/close-position protection semantics.",
        ),
    ]
    for name, available, owner, ref, ready_detail in reduce_specs:
        descriptors.append(
            ExecutionCapabilityDescriptorV0(
                name=name,
                status="ready" if available else "missing",
                evidence_level="runtime_owner" if available else "unavailable",
                owner=owner,
                source_ts_ms=produced_ts_ms if available else None,
                detail=(
                    ready_detail + " Exchange acceptance is not claimed."
                    if available
                    else "Explicit runtime owner evidence is unavailable."
                ),
                constraints={"exchange_acceptance_confirmed": False},
                raw_ref=ref,
                missing_reason=None if available else "runtime_owner_unavailable",
            )
        )

    counts = {name: 0 for name in ("ready", "degraded", "missing", "unknown")}
    reasons: list[str] = []
    for descriptor in descriptors:
        counts[descriptor.status] += 1
        if descriptor.missing_reason and descriptor.missing_reason not in reasons:
            reasons.append(descriptor.missing_reason)
    summary = ExecutionReadinessSummaryV0(**counts, reasons=reasons[:16])
    return descriptors, summaries, summary


def project_execution_readiness_snapshot(
    snapshot: ExecutionReadinessSnapshotV0,
    symbols: Iterable[str],
) -> ExecutionReadinessSnapshotV0:
    """Project a full runtime publication into a compact requested-symbol view."""

    requested = list(
        dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip())
    )
    allowed = set(requested)
    descriptors = [
        item for item in snapshot.capability_descriptors
        if item.symbol is None or item.symbol in allowed
    ]
    constraints = [item for item in snapshot.constraint_summary if item.symbol in allowed]
    parity_acknowledgements = [
        item for item in snapshot.filter_parity_acknowledgements if item.symbol in allowed
    ]
    counts = {name: 0 for name in ("ready", "degraded", "missing", "unknown")}
    reasons: list[str] = []
    for descriptor in descriptors:
        counts[descriptor.status] += 1
        if descriptor.missing_reason and descriptor.missing_reason not in reasons:
            reasons.append(descriptor.missing_reason)
    summary = ExecutionReadinessSummaryV0(**counts, reasons=reasons[:16])

    invariants = list(snapshot.invariants)
    updates: dict[str, tuple[str, str]] = {}
    filter_items = [item for item in descriptors if item.name == "exchange_filter_constraints"]
    confirmed = sum(
        item.status == "ready" and item.evidence_level == "exchange_confirmed"
        for item in filter_items
    )
    configured = sum(item.evidence_level == "configured_only" for item in filter_items)
    stale = sum(item.diagnostic_state == "stale_exchange_info" for item in filter_items)
    mismatched = sum(item.diagnostic_state == "parity_mismatch" for item in filter_items)
    filter_status = (
        "ready" if filter_items and confirmed == len(requested)
        else "degraded" if any(item.status in {"ready", "degraded"} for item in filter_items)
        else "missing"
    )
    updates["exchange_filter_readiness"] = (
        filter_status,
        f"Exchange-confirmed fresh constraints: {confirmed}/{len(requested)}; "
        f"configured-only constraints: {configured}/{len(requested)}; "
        f"stale: {stale}; material parity mismatches: {mismatched}.",
    )

    precision_items = [
        item for item in descriptors if item.name == "precision_minimum_normalization"
    ]
    precision_ready = sum(item.status == "ready" for item in precision_items)
    precision_status = (
        "ready" if precision_items and precision_ready == len(requested)
        else "degraded" if any(item.status in {"ready", "degraded"} for item in precision_items)
        else "missing"
    )
    updates["precision_minimum_constraints"] = (
        precision_status,
        f"Runtime-owned qty/price/minimum normalization is ready for "
        f"{precision_ready}/{len(requested)} requested symbols.",
    )

    projected_invariants = [
        item.model_copy(update={"status": updates[item.name][0], "detail": updates[item.name][1]})
        if item.name in updates else item
        for item in invariants
    ]
    return snapshot.model_copy(
        update={
            "symbols": requested,
            "invariants": projected_invariants,
            "capability_descriptors": descriptors,
            "constraint_summary": constraints,
            "filter_parity_acknowledgements": parity_acknowledgements,
            "readiness_summary": summary,
        }
    )


__all__ = [
    "build_execution_capability_descriptors",
    "project_execution_readiness_snapshot",
]
