"""Shadow comparison helpers for the execution_position close contour.

The helpers in this module are read-only. They normalize the incumbent close
submissions, build a shadow projection, and classify the comparison result
without touching live execution or authoritative order logs.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

LOG = logging.getLogger(__name__)

BRIDGE_KEYS = (
    "symbol",
    "reason",
    "qty",
    "reduce_only",
    "idempotent_key",
    "trigger",
    "command_trigger",
    "close_guard_prevalidated",
)
BRIDGE_VALIDATION_KEYS = (
    "validation_classification",
    "reject_reason",
    "reason",
    "idempotent_key",
)
SUBMISSION_KEYS = (
    "symbol",
    "side",
    "quantity",
    "partial_close",
    "client_order_id",
    "idempotent_key",
)
SUBMISSION_VALIDATION_KEYS = (
    "validation_classification",
    "reject_reason",
    "reason",
    "idempotent_key",
)
BOUNDARY_KEYS = (
    "symbol",
    "side",
    "quantity",
    "partial_close",
    "client_order_id",
    "order_kind",
    "order_type",
    "why",
    "trace_kind",
)
BOUNDARY_VALIDATION_KEYS = (
    "validation_classification",
    "reject_reason",
    "reason",
)
TRUTH_GATE_KEYS = (
    "symbol",
    "classification",
    "reason",
    "position_amt",
    "requested_qty",
    "close_cmd_rid",
)
TRUTH_GATE_VALIDATION_KEYS = (
    "validation_classification",
    "reject_reason",
    "reason",
)
STATE_KEYS = (
    "state",
    "position_active",
    "position_open_ts",
    "last_close_reason",
    "last_close_qty",
    "last_close_symbol",
)
BOOL_KEYS = {
    "reduce_only",
    "partial_close",
    "close_guard_prevalidated",
    "position_active",
}
DECIMAL_KEYS = {
    "qty",
    "quantity",
    "position_amt",
    "requested_qty",
    "last_close_qty",
}


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    return text


def _canonical_decimal_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _clean_text(value)
    text = format(dec.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _mapping_from(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        try:
            dumped = asdict(value)
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dict(dumped)
    if hasattr(value, "__dict__"):
        try:
            dumped = dict(vars(value))
        except Exception:
            dumped = None
        if isinstance(dumped, dict) and dumped:
            return dict(dumped)
    for attr in ("model_dump", "dict", "to_dict"):
        candidate = getattr(value, attr, None)
        if callable(candidate):
            try:
                dumped = candidate()
            except Exception:
                continue
            if isinstance(dumped, Mapping):
                return dict(dumped)
    return None


def _project_fields(source: Any, keys: Sequence[str]) -> dict[str, Any]:
    mapping = _mapping_from(source)
    if mapping is None:
        return {}
    projected: dict[str, Any] = {}
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if value is None:
            projected[key] = None
            continue
        if key in BOOL_KEYS:
            projected[key] = bool(value)
            continue
        if key in DECIMAL_KEYS:
            projected[key] = _canonical_decimal_text(value)
            continue
        projected[key] = _clean_text(value)
    return projected


def _classify_mismatch(
    mismatch_fields: Sequence[str],
    *,
    validation_keys: Sequence[str],
    state_keys: Sequence[str],
) -> str:
    if any(field in validation_keys for field in mismatch_fields):
        return "validation_divergence"
    if any(field in state_keys for field in mismatch_fields):
        return "state_divergence"
    return "payload_divergence"


@dataclass(frozen=True)
class CloseShadowComparison:
    stage: str
    comparison_outcome: str
    comparison_classification: Optional[str]
    comparison_keys: tuple[str, ...] = field(default_factory=tuple)
    mismatch_fields: tuple[str, ...] = field(default_factory=tuple)
    incumbent_truth: dict[str, Any] = field(default_factory=dict)
    shadow_truth: dict[str, Any] = field(default_factory=dict)
    state_before: Optional[dict[str, Any]] = None
    state_after: Optional[dict[str, Any]] = None
    context: dict[str, Any] = field(default_factory=dict)
    detail: Optional[str] = None
    instrumentation_failure: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "comparison_outcome": self.comparison_outcome,
            "comparison_classification": self.comparison_classification,
            "comparison_keys": list(self.comparison_keys),
            "mismatch_fields": list(self.mismatch_fields),
            "incumbent_truth": dict(self.incumbent_truth),
            "shadow_truth": dict(self.shadow_truth),
            "context": dict(self.context),
        }
        if self.state_before is not None:
            payload["state_before"] = dict(self.state_before)
        if self.state_after is not None:
            payload["state_after"] = dict(self.state_after)
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.instrumentation_failure is not None:
            payload["instrumentation_failure"] = self.instrumentation_failure
        return payload


def compare_close_projections(
    *,
    stage: str,
    incumbent: Any | None,
    shadow: Any | None,
    comparison_keys: Sequence[str],
    validation_keys: Sequence[str] = (),
    state_keys: Sequence[str] = (),
    expected_outcome: str = "match",
    state_before: Optional[Mapping[str, Any]] = None,
    state_after: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
    detail: Optional[str] = None,
    instrumentation_failure: Optional[str] = None,
) -> CloseShadowComparison:
    if instrumentation_failure is not None:
        return CloseShadowComparison(
            stage=stage,
            comparison_outcome="failure",
            comparison_classification="shadow_instrumentation_failure",
            comparison_keys=tuple(comparison_keys),
            mismatch_fields=(),
            incumbent_truth={},
            shadow_truth={},
            state_before=_mapping_from(state_before),
            state_after=_mapping_from(state_after),
            context=dict(context or {}),
            detail=detail,
            instrumentation_failure=instrumentation_failure,
        )

    incumbent_map = _mapping_from(incumbent)
    shadow_map = _mapping_from(shadow)
    if incumbent_map is None or shadow_map is None:
        return CloseShadowComparison(
            stage=stage,
            comparison_outcome="unavailable",
            comparison_classification="comparison_unavailable",
            comparison_keys=tuple(comparison_keys),
            mismatch_fields=(),
            incumbent_truth=incumbent_map or {},
            shadow_truth=shadow_map or {},
            state_before=_mapping_from(state_before),
            state_after=_mapping_from(state_after),
            context=dict(context or {}),
            detail=detail,
        )

    normalized_incumbent = _project_fields(incumbent_map, comparison_keys)
    normalized_shadow = _project_fields(shadow_map, comparison_keys)
    mismatch_fields = tuple(
        key for key in comparison_keys
        if normalized_incumbent.get(key) != normalized_shadow.get(key)
    )
    if mismatch_fields:
        comparison_classification = _classify_mismatch(
            mismatch_fields,
            validation_keys=validation_keys,
            state_keys=state_keys,
        )
        comparison_outcome = "mismatch"
    else:
        comparison_classification = None
        comparison_outcome = expected_outcome

    return CloseShadowComparison(
        stage=stage,
        comparison_outcome=comparison_outcome,
        comparison_classification=comparison_classification,
        comparison_keys=tuple(comparison_keys),
        mismatch_fields=mismatch_fields,
        incumbent_truth=normalized_incumbent,
        shadow_truth=normalized_shadow,
        state_before=_mapping_from(state_before),
        state_after=_mapping_from(state_after),
        context=dict(context or {}),
        detail=detail,
    )


def _project_close_bridge_truth(message: Any) -> dict[str, Any]:
    payload = _mapping_from(getattr(message, "pld", None))
    payload = payload or {}
    return {
        "symbol": _clean_text(payload.get("symbol")),
        "reason": _clean_text(payload.get("reason") or getattr(message, "why", None)),
        "qty": _canonical_decimal_text(payload.get("qty")),
        "reduce_only": bool(payload.get("reduce_only", True)),
        "idempotent_key": _clean_text(
            payload.get("idempotent_key") or getattr(message, "idempotent_key", None)
        ),
        "trigger": _clean_text(payload.get("trigger") or "CMD:CLOSE"),
        "command_trigger": _clean_text(payload.get("command_trigger")),
        "close_guard_prevalidated": bool(
            payload.get("close_guard_prevalidated", False)
        ),
    }


def _project_close_submission_truth(
    *,
    decision: Any,
    submission: Any,
) -> dict[str, Any]:
    decision_payload = _mapping_from(getattr(decision, "pld", None)) or {}
    submission_map = _mapping_from(submission) or {}
    return {
        "symbol": _clean_text(submission_map.get("symbol") or decision_payload.get("symbol")),
        "side": _clean_text(submission_map.get("side")),
        "quantity": _canonical_decimal_text(submission_map.get("quantity")),
        "partial_close": bool(submission_map.get("partial_close", False)),
        "client_order_id": _clean_text(submission_map.get("client_order_id")),
        "idempotent_key": _clean_text(
            decision_payload.get("idempotent_key") or getattr(decision, "idempotent_key", None)
        ),
    }


def _project_close_boundary_truth(
    *,
    decision: Any,
    boundary_payload: Mapping[str, Any],
) -> dict[str, Any]:
    decision_payload = _mapping_from(getattr(decision, "pld", None)) or {}
    return {
        "symbol": _clean_text(boundary_payload.get("symbol") or decision_payload.get("symbol")),
        "side": _clean_text(boundary_payload.get("side")),
        "quantity": _canonical_decimal_text(boundary_payload.get("quantity")),
        "partial_close": bool(
            boundary_payload.get("metadata", {}).get("partial_close", False)
            if isinstance(boundary_payload.get("metadata"), Mapping)
            else False
        ),
        "client_order_id": _clean_text(boundary_payload.get("client_order_id")),
        "order_kind": _clean_text(boundary_payload.get("order_kind")),
        "order_type": _clean_text(boundary_payload.get("order_type")),
        "why": _clean_text(boundary_payload.get("why")),
        "trace_kind": _clean_text(
            boundary_payload.get("metadata", {}).get("trace_kind")
            if isinstance(boundary_payload.get("metadata"), Mapping)
            else None
        ),
    }


def _project_close_truth_gate_truth(
    *,
    symbol: str,
    classification: Any,
    reason: Any,
    position_amt: Any = None,
    requested_qty: Any = None,
    close_cmd_rid: Any = None,
) -> dict[str, Any]:
    return {
        "symbol": _clean_text(symbol),
        "classification": _clean_text(classification),
        "reason": _clean_text(reason),
        "position_amt": _canonical_decimal_text(position_amt),
        "requested_qty": _canonical_decimal_text(requested_qty),
        "close_cmd_rid": _clean_text(close_cmd_rid),
    }


def build_close_bridge_comparison(
    *,
    msg: Any,
    result: Any | None,
    state_before: Optional[Mapping[str, Any]] = None,
    state_after: Optional[Mapping[str, Any]] = None,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    incumbent = _project_close_bridge_truth(result) if result is not None else None
    shadow = _project_close_bridge_truth(msg)
    return compare_close_projections(
        stage="bridge",
        incumbent=incumbent,
        shadow=shadow,
        comparison_keys=BRIDGE_KEYS,
        validation_keys=BRIDGE_VALIDATION_KEYS,
        state_keys=STATE_KEYS,
        state_before=state_before,
        state_after=state_after,
        context={"source": "CloseFlowFSM"},
        detail=detail,
    )


def build_close_bridge_reject_comparison(
    *,
    msg: Any,
    reason: str,
    state_before: Optional[Mapping[str, Any]] = None,
    state_after: Optional[Mapping[str, Any]] = None,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    projection = _project_close_bridge_truth(msg)
    projection = dict(projection)
    projection["validation_classification"] = "reject"
    projection["reject_reason"] = _clean_text(reason)
    return compare_close_projections(
        stage="bridge_reject",
        incumbent=projection,
        shadow=projection,
        comparison_keys=(
            *BRIDGE_KEYS,
            "validation_classification",
            "reject_reason",
        ),
        validation_keys=BRIDGE_VALIDATION_KEYS,
        state_keys=STATE_KEYS,
        expected_outcome="reject",
        state_before=state_before,
        state_after=state_after,
        context={"source": "CloseFlowFSM"},
        detail=detail,
    )


def build_close_submission_comparison(
    *,
    decision: Any,
    submission: Any,
    position_amt: Any = None,
    requested_qty: Any = None,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    incumbent = _project_close_submission_truth(
        decision=decision,
        submission=submission,
    )
    shadow = _project_close_submission_truth(
        decision=decision,
        submission=submission,
    )
    return compare_close_projections(
        stage="submission",
        incumbent=incumbent,
        shadow=shadow,
        comparison_keys=SUBMISSION_KEYS,
        validation_keys=SUBMISSION_VALIDATION_KEYS,
        expected_outcome="match",
        context={
            "source": "CloseExecutor",
            "position_amt": _canonical_decimal_text(position_amt),
            "requested_qty": _canonical_decimal_text(requested_qty),
        },
        detail=detail,
    )


def build_close_submission_reject_comparison(
    *,
    decision: Any,
    partial_close: bool,
    reason: str,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    decision_payload = _mapping_from(getattr(decision, "pld", None)) or {}
    projection = {
        "symbol": _clean_text(decision_payload.get("symbol")),
        "validation_classification": "reject",
        "reject_reason": _clean_text(reason),
        "partial_close": bool(partial_close),
        "idempotent_key": _clean_text(
            decision_payload.get("idempotent_key") or getattr(decision, "idempotent_key", None)
        ),
    }
    return compare_close_projections(
        stage="submission_reject",
        incumbent=projection,
        shadow=projection,
        comparison_keys=(
            "symbol",
            "validation_classification",
            "reject_reason",
            "partial_close",
            "idempotent_key",
        ),
        validation_keys=SUBMISSION_VALIDATION_KEYS,
        expected_outcome="reject",
        context={"source": "CloseExecutor"},
        detail=detail,
    )


def build_close_boundary_comparison(
    *,
    decision: Any,
    submission: Any,
    boundary_payload: Mapping[str, Any],
    trace_kind: str,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    incumbent = _project_close_boundary_truth(
        decision=decision,
        boundary_payload=boundary_payload,
    )
    shadow = _project_close_boundary_truth(
        decision=decision,
        boundary_payload=boundary_payload,
    )
    return compare_close_projections(
        stage="submit_boundary",
        incumbent=incumbent,
        shadow=shadow,
        comparison_keys=BOUNDARY_KEYS,
        validation_keys=BOUNDARY_VALIDATION_KEYS,
        context={
            "source": "CloseExecutor",
            "trace_kind": trace_kind,
            "client_order_id": _clean_text(
                getattr(submission, "client_order_id", None)
            ),
        },
        detail=detail,
    )


def build_close_truth_gate_comparison(
    *,
    symbol: str,
    truth: Any,
    close_cmd_rid: Any = None,
    requested_qty: Any = None,
    detail: Optional[str] = None,
) -> CloseShadowComparison:
    truth_map = _mapping_from(truth) or {}
    incumbent = _project_close_truth_gate_truth(
        symbol=symbol,
        classification=truth_map.get("classification"),
        reason=truth_map.get("reason"),
        position_amt=truth_map.get("position_amt"),
        requested_qty=requested_qty,
        close_cmd_rid=close_cmd_rid,
    )
    shadow = dict(incumbent)
    return compare_close_projections(
        stage="truth_gate",
        incumbent=incumbent,
        shadow=shadow,
        comparison_keys=TRUTH_GATE_KEYS,
        validation_keys=TRUTH_GATE_VALIDATION_KEYS,
        expected_outcome="reject",
        context={"source": "CloseExecutor"},
        detail=detail,
    )


def emit_close_shadow_comparison(
    *,
    journal: Any,
    comparison: CloseShadowComparison,
    event_name: str,
    source_component: str,
    source_path: str,
    event_origin_type: str,
    truth_owner: str,
    rid: Any = None,
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    payload: Optional[Mapping[str, Any]] = None,
    notes: Optional[list[str]] = None,
) -> None:
    if journal is None:
        return
    try:
        record_comparison = getattr(journal, "record_comparison", None)
        if not callable(record_comparison):
            LOG.debug(
                "Shadow journal does not support comparison records: %s",
                type(journal).__name__,
            )
            return
        record_comparison(
            event_name=event_name,
            source_component=source_component,
            source_path=source_path,
            event_origin_type=event_origin_type,
            truth_owner=truth_owner,
            comparison=comparison,
            rid=str(rid) if rid is not None else None,
            before=dict(before) if isinstance(before, Mapping) else None,
            after=dict(after) if isinstance(after, Mapping) else None,
            payload=dict(payload) if isinstance(payload, Mapping) else None,
            notes=list(notes or []),
        )
    except Exception:
        LOG.warning(
            "Failed to emit close shadow comparison",
            exc_info=True,
        )
