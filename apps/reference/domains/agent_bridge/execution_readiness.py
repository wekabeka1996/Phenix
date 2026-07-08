from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Optional

from .contracts import (
    ExecutionReadinessSnapshotV0,
    FilterParityAcknowledgementV0,
    MechanicalInvariant,
)
from .capabilities import build_execution_capability_descriptors


RUNTIME_REF = "aurora://execution-position/runtime#readiness"
FILTER_REF = "aurora://execution-position/runtime#exchange-filter-cache"
INSPECTOR_REF = "agent-bridge://execution-readiness/allowlist-v0"


def _invariant(
    name: str,
    status: str,
    detail: str,
    *,
    source: str,
    observed_ts_ms: Optional[int],
    raw_ref: Optional[str] = None,
) -> MechanicalInvariant:
    return MechanicalInvariant(
        name=name,
        status=status,
        detail=detail,
        evidence_source=source,
        source_ts_ms=observed_ts_ms,
        raw_ref=raw_ref,
    )


def build_execution_readiness_snapshot(
    *,
    runtime: Any | None,
    symbols: Iterable[str],
    produced_ts_ms: int,
    trace_available: bool,
    public_exchange_info: Any | None = None,
    filter_parity_acknowledgements: Optional[list[FilterParityAcknowledgementV0]] = None,
) -> ExecutionReadinessSnapshotV0:
    """Inspect a strict allowlist of read-only ExecPosFSM state.

    This function deliberately never reads adapter credentials, calls adapter
    methods, refreshes filters, reconciles state, or invokes an executor.
    """

    normalized = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))
    capability_descriptors, constraint_summary, readiness_summary = (
        build_execution_capability_descriptors(
            runtime=runtime,
            symbols=normalized,
            produced_ts_ms=produced_ts_ms,
            public_exchange_info=public_exchange_info,
        )
    )
    if runtime is None:
        missing = [
            _invariant(name, "missing", "ExecutionPosition runtime is not imported in this API process.", source=RUNTIME_REF, observed_ts_ms=None, raw_ref=RUNTIME_REF)
            for name in (
                "testnet_only_or_mode",
                "no_order_execution_isolation",
                "exchange_filter_readiness",
                "precision_minimum_constraints",
                "reduce_only_close_protect",
                "duplicate_idempotency_protection",
                "lifecycle_reconciliation",
                "bracket_ownership",
                "trace_correlation_identity",
            )
        ]
        missing.append(
            _invariant(
                "secret_isolation",
                "ready",
                "The readiness inspector uses an explicit allowlist and does not read secret-bearing adapter attributes.",
                source=INSPECTOR_REF,
                observed_ts_ms=produced_ts_ms,
                raw_ref=INSPECTOR_REF,
            )
        )
        return ExecutionReadinessSnapshotV0(
            produced_ts_ms=produced_ts_ms,
            runtime_available=False,
            symbols=normalized,
            invariants=missing,
            capability_descriptors=capability_descriptors,
            constraint_summary=constraint_summary,
            readiness_summary=readiness_summary,
            filter_parity_acknowledgements=filter_parity_acknowledgements or [],
        )

    shadow_mode = bool(getattr(runtime, "shadow_mode", False))
    live_execution = bool(getattr(runtime, "is_live_execution", False))
    adapter = getattr(runtime, "adapter", None)
    no_order_mode = bool(getattr(runtime, "no_order_observation_mode", False))
    no_order_safe = no_order_mode and shadow_mode and not live_execution and adapter is None
    if no_order_mode:
        mode_status = "ready" if no_order_safe else "degraded"
    else:
        mode_status = "ready" if shadow_mode or adapter is not None else "degraded"
    mode_detail = (
        f"Runtime flags observed: no_order_observation={str(no_order_mode).lower()}, "
        f"shadow_mode={str(shadow_mode).lower()}, "
        f"live_execution={str(live_execution).lower()}, adapter_present={str(adapter is not None).lower()}."
    )
    isolation_status = "ready" if no_order_safe else "unknown" if not no_order_mode else "degraded"
    isolation_detail = (
        "Runtime-owned observation profile is active with shadow mode, no live execution, "
        "no exchange adapter, and consequential bus listeners omitted. "
        f"Blocked action count={int(getattr(runtime, 'no_order_blocked_action_count', 0))}."
        if no_order_safe
        else "No-order execution isolation is not active in this runtime."
        if not no_order_mode
        else "No-order profile flags are internally inconsistent; readiness remains degraded."
    )

    filter_descriptors = [
        item for item in capability_descriptors
        if item.name == "exchange_filter_constraints"
    ]
    confirmed_filters = sum(
        item.status == "ready" and item.evidence_level == "exchange_confirmed"
        for item in filter_descriptors
    )
    configured_filters = sum(
        item.status == "degraded" and item.evidence_level == "configured_only"
        for item in filter_descriptors
    )
    stale_filters = sum(item.diagnostic_state == "stale_exchange_info" for item in filter_descriptors)
    mismatch_filters = sum(item.diagnostic_state == "parity_mismatch" for item in filter_descriptors)
    filter_status = (
        "ready" if filter_descriptors and confirmed_filters == len(normalized)
        else "degraded" if filter_descriptors and any(item.status in {"ready", "degraded"} for item in filter_descriptors)
        else "missing"
    )
    filter_detail = (
        f"Exchange-confirmed fresh constraints: {confirmed_filters}/{len(normalized)}; "
        f"configured-only constraints: {configured_filters}/{len(normalized)}; "
        f"stale: {stale_filters}; material parity mismatches: {mismatch_filters}."
    )

    precision_descriptors = [
        item for item in capability_descriptors
        if item.name == "precision_minimum_normalization"
    ]
    precision_ready = sum(item.status == "ready" for item in precision_descriptors)
    precision_status = (
        "ready" if precision_descriptors and precision_ready == len(normalized)
        else "degraded" if any(
            item.status in {"ready", "degraded"} for item in precision_descriptors
        )
        else "missing"
    )
    precision_detail = (
        f"Runtime-owned qty/price/minimum normalization is ready for "
        f"{precision_ready}/{len(normalized)} requested symbols."
    )

    reduce_names = {
        "reduce_only_order_parameter",
        "close_path_reduce_only_enforcement",
        "protect_path_reduce_only_enforcement",
    }
    reduce_descriptors = [
        item for item in capability_descriptors if item.name in reduce_names
    ]
    reduce_ready = sum(item.status == "ready" for item in reduce_descriptors)
    reduce_status = (
        "ready" if reduce_ready == len(reduce_names)
        else "degraded" if reduce_ready
        else "missing"
    )
    reduce_detail = (
        f"Explicit runtime-owner reduce-only capabilities ready: "
        f"{reduce_ready}/{len(reduce_names)}; exchange acceptance is not claimed."
    )

    idempotent_helper = getattr(runtime, "_idempotent_cancel_helper", None)
    order_index = getattr(runtime, "order_index", None)
    if order_index is None:
        order_index = getattr(getattr(runtime, "fsm", None), "order_index", None)
    idempotency_status = "ready" if idempotent_helper is not None and order_index is not None else "degraded" if idempotent_helper is not None or order_index is not None else "missing"
    idempotency_detail = f"Runtime idempotent helper present={str(idempotent_helper is not None).lower()}, order index present={str(order_index is not None).lower()}."

    lifecycle_owner = getattr(runtime, "_startup_truth_orchestrator", None)
    manage_flows = getattr(runtime, "manage_flows", None)
    lifecycle_status = "ready" if lifecycle_owner is not None and isinstance(manage_flows, Mapping) else "degraded" if lifecycle_owner is not None else "missing"
    lifecycle_detail = f"Startup truth owner present={str(lifecycle_owner is not None).lower()}, managed symbols={len(manage_flows) if isinstance(manage_flows, Mapping) else 0}."

    bracket_owner = getattr(runtime, "_bracket_ownership", None)
    bracket_links = getattr(runtime, "_symbol_brackets", None)
    bracket_sources = getattr(runtime, "_symbol_bracket_truth_source", None)
    bracket_status = "ready" if bracket_owner is not None and isinstance(bracket_links, Mapping) and isinstance(bracket_sources, Mapping) else "degraded" if bracket_owner is not None else "missing"
    bracket_detail = f"Bracket owner present={str(bracket_owner is not None).lower()}, linked symbols={len(bracket_links) if isinstance(bracket_links, Mapping) else 0}, truth-source symbols={len(bracket_sources) if isinstance(bracket_sources, Mapping) else 0}."

    correlation_store = getattr(runtime, "correlation_store", None)
    trace_status = "ready" if correlation_store is not None and trace_available else "degraded" if correlation_store is not None or trace_available else "missing"
    trace_detail = f"Runtime correlation store present={str(correlation_store is not None).lower()}, recent bounded trace present={str(trace_available).lower()}."

    specs = [
        ("testnet_only_or_mode", mode_status, mode_detail, RUNTIME_REF),
        ("no_order_execution_isolation", isolation_status, isolation_detail, RUNTIME_REF),
        ("exchange_filter_readiness", filter_status, filter_detail, FILTER_REF),
        ("precision_minimum_constraints", precision_status, precision_detail, FILTER_REF),
        ("reduce_only_close_protect", reduce_status, reduce_detail, RUNTIME_REF),
        ("duplicate_idempotency_protection", idempotency_status, idempotency_detail, RUNTIME_REF),
        ("lifecycle_reconciliation", lifecycle_status, lifecycle_detail, RUNTIME_REF),
        ("bracket_ownership", bracket_status, bracket_detail, RUNTIME_REF),
        ("trace_correlation_identity", trace_status, trace_detail, RUNTIME_REF),
    ]
    invariants = [
        _invariant(name, status, detail, source=ref, observed_ts_ms=produced_ts_ms, raw_ref=ref)
        for name, status, detail, ref in specs
    ]
    invariants.append(
        _invariant(
            "secret_isolation",
            "ready",
            "The readiness inspector uses an explicit allowlist and does not read secret-bearing adapter attributes.",
            source=INSPECTOR_REF,
            observed_ts_ms=produced_ts_ms,
            raw_ref=INSPECTOR_REF,
        )
    )
    return ExecutionReadinessSnapshotV0(
        produced_ts_ms=produced_ts_ms,
        runtime_available=True,
        symbols=normalized,
        invariants=invariants,
        capability_descriptors=capability_descriptors,
        constraint_summary=constraint_summary,
        readiness_summary=readiness_summary,
        filter_parity_acknowledgements=filter_parity_acknowledgements or [],
    )
