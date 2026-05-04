"""Close/cancel execution helper for execution_position.

This module owns the imperative side of DEC:CLOSE, DEC:CANCEL_ORDER, and the
generic DEC:PLACE_ORDER path used by manage/auxiliary flows.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.shadow_journal import get_shadow_journal
from ...guardian.cancel_submission_adapter import (
    CANCEL_SUBMISSION_CONTRACT,
    CANCEL_SUBMISSION_PATH,
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
    build_cancel_submission_trace_ref,
)
from .close_submission_adapter import (
    CLOSE_SUBMISSION_CONTRACT,
    CLOSE_SUBMISSION_PATH,
    CloseSubmissionAdapterError,
    CloseSubmissionPayload,
    build_close_submission_trace_ref,
)
from apps.reference.domains.execution_position.telemetry.close_shadow_comparison import (
    build_close_boundary_comparison,
    build_close_submission_comparison,
    build_close_submission_reject_comparison,
    build_close_truth_gate_comparison,
    emit_close_shadow_comparison,
)
from .tracked_close_teardown_cancel_bridge import (
    TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT,
    TRACKED_CLOSE_TEARDOWN_CANCEL_PATH,
    TrackedCloseTeardownCancelBridgeError,
    TrackedCloseTeardownCancelRequest,
    adapt_tracked_close_teardown_to_dec_cancel,
    build_tracked_close_teardown_cancel_trace_ref,
)
from .reconcile_close_cancel_bridge import (
    RECONCILE_CLOSE_CANCEL_CONTRACT,
    RECONCILE_CLOSE_CANCEL_PATH,
    ReconcileCloseCancelBridgeError,
    ReconcileCloseCancelRequest,
    adapt_reconcile_close_to_dec_cancel,
    build_reconcile_close_cancel_trace_ref,
)
from apps.reference.domains.execution_position.utils import (
    classify_client_order_id,
    coerce_exchange_bool,
    generate_client_order_id,
)

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.close_executor"
)


class _ClosePositionTruthClassification(str, Enum):
    GENUINELY_FLAT = "GENUINELY_FLAT"
    POSITION_TRUTH_UNRESOLVED = "POSITION_TRUTH_UNRESOLVED"
    POSITION_PRESENT_AND_SUBMITTABLE = "POSITION_PRESENT_AND_SUBMITTABLE"


@dataclass(frozen=True)
class _ClosePositionTruthResolution:
    classification: _ClosePositionTruthClassification
    position_amt: Optional[Decimal] = None
    reason: Optional[str] = None


class CloseExecutor:
    """Execute cancel, close, and generic auxiliary order verbs."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    @staticmethod
    def _response_value(response: Any, *keys: str) -> Any:
        if isinstance(response, dict):
            for key in keys:
                if key in response:
                    return response.get(key)
            return None
        for key in keys:
            if hasattr(response, key):
                return getattr(response, key)
        return None

    @staticmethod
    def _canonical_auxiliary_bracket_role(
        client_order_id: Optional[str],
    ) -> Optional[str]:
        role = classify_client_order_id(client_order_id)
        if role in {"SL", "BHSL"}:
            return "SL"
        if role in {"TP", "TP1", "TP2", "BHTP"}:
            return "TP"
        return None

    def _runtime_order_index(self) -> Any:
        direct_index = getattr(self._fsm, "order_index", None)
        if direct_index is not None:
            return direct_index
        return getattr(getattr(self._fsm, "fsm", None), "order_index", None)

    @staticmethod
    def _position_policy_context(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        candidate = payload.get("policy_context")
        if not isinstance(candidate, dict):
            return None
        if str(candidate.get("policy_source") or "") != "position_policy_sidecar":
            return None
        return dict(candidate)

    def _emit_position_policy_close_state(
        self,
        payload: dict[str, Any],
        *,
        request_state: str,
        why: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        context = self._position_policy_context(payload)
        if context is None:
            return
        context.setdefault("symbol", payload.get("symbol"))
        context.setdefault("trace_id", context.get("source_trace_id"))
        self._fsm._emit_position_policy_close_request_state(
            context,
            request_state=request_state,
            why=why,
            extra=extra,
        )

    @staticmethod
    def _manage_flow_allows_bracket_sync(manage_flow: Any) -> bool:
        state = getattr(manage_flow, "state", None)
        state_value = getattr(state, "value", state)
        return str(state_value or "").strip().upper() not in {"", "FLAT"}

    def _resolve_auxiliary_parent_order_id(
        self,
        *,
        symbol: str,
        payload: dict[str, Any],
        manage_flow: Any,
    ) -> str:
        explicit_parent = str(
            payload.get("parent_order_id") or payload.get(
                "entry_order_id") or ""
        ).strip()
        if explicit_parent:
            return explicit_parent

        tracked_entry_order_id = str(
            getattr(manage_flow, "entry_order_id", "") or ""
        ).strip()
        if tracked_entry_order_id:
            return tracked_entry_order_id

        fallback_parent = f"auxiliary:{str(symbol or '').strip().upper()}"
        LOG.warning(
            "Auxiliary bracket registration missing parent entry order for %s; using %s",
            symbol,
            fallback_parent,
        )
        return fallback_parent

    def _register_auxiliary_bracket_order(
        self,
        *,
        decision: "Message",
        payload: dict[str, Any],
        symbol: str,
        side: Any,
        order_type: Any,
        client_order_id: str,
        response: Any,
    ) -> bool:
        bracket_role = self._canonical_auxiliary_bracket_role(client_order_id)
        if bracket_role is None:
            return False

        exchange_order_id = str(
            self._response_value(response, "orderId", "order_id") or ""
        ).strip()
        if not exchange_order_id:
            LOG.error(
                "PLACE_ORDER bracket registration missing exchange order id for %s client_order_id=%s",
                symbol,
                client_order_id,
            )
            return False

        client_algo_id = str(
            self._response_value(response, "clientAlgoId",
                                 "client_algo_id") or ""
        ).strip()

        self._fsm._set_symbol_bracket_order(
            symbol,
            order_role=bracket_role,
            order_id=exchange_order_id,
        )

        order_index = self._runtime_order_index()
        if order_index is None:
            LOG.warning(
                "Auxiliary bracket accepted without OrderIndex available for %s client_order_id=%s",
                symbol,
                client_order_id,
            )
        else:
            rid_for_index = str(getattr(decision, "rid", "")
                                or exchange_order_id)
            idem_key = str(
                payload.get("idempotent_key")
                or getattr(decision, "idempotent_key", None)
                or client_order_id
                or rid_for_index
            )
            primary_client_order_id = client_algo_id or client_order_id
            try:
                order_index.register_bracket_child(
                    rid=rid_for_index,
                    idempotent_key=idem_key,
                    clientOrderId=primary_client_order_id,
                    exchangeOrderId=exchange_order_id,
                    symbol=symbol,
                    side=str(side).upper() if side else "",
                    order_type=str(order_type),
                    order_kind=bracket_role,
                )
            except Exception as exc:
                LOG.error(
                    "Auxiliary bracket OrderIndex registration failed for %s %s/%s: %s",
                    symbol,
                    primary_client_order_id,
                    exchange_order_id,
                    exc,
                )

            if client_algo_id and client_algo_id != client_order_id:
                try:
                    order_index.register_bracket_child(
                        rid=rid_for_index,
                        idempotent_key=idem_key,
                        clientOrderId=client_order_id,
                        exchangeOrderId=exchange_order_id,
                        symbol=symbol,
                        side=str(side).upper() if side else "",
                        order_type=str(order_type),
                        order_kind=bracket_role,
                    )
                except Exception as exc:
                    LOG.debug(
                        "Auxiliary bracket secondary OrderIndex registration skipped for %s %s/%s: %s",
                        symbol,
                        client_order_id,
                        exchange_order_id,
                        exc,
                    )

        manage_flow = self._fsm.manage_flows.get(symbol)
        parent_order_id = self._resolve_auxiliary_parent_order_id(
            symbol=symbol,
            payload=payload,
            manage_flow=manage_flow,
        )

        guardian = getattr(self._fsm, "order_guardian", None)
        if guardian is None:
            LOG.warning(
                "Auxiliary bracket accepted without OrderGuardian available for %s client_order_id=%s",
                symbol,
                client_order_id,
            )
        else:
            guardian.register_bracket(
                symbol=symbol,
                parent_order_id=parent_order_id,
                order_id=exchange_order_id,
                client_order_id=client_order_id,
                kind=bracket_role,
                corr_id=getattr(decision, "corr_id", None),
                rid=getattr(decision, "rid", None),
            )

        if manage_flow is not None and self._manage_flow_allows_bracket_sync(manage_flow):
            brackets = self._fsm._symbol_brackets.get(symbol, {})
            current_sl_order_id = brackets.get("sl_order_id")
            current_tp_order_id = brackets.get("tp_order_id")
            current_sl_algo_client_id = (
                getattr(manage_flow, "sl_algo_client_id", None)
                if current_sl_order_id and bracket_role != "SL"
                else None
            )
            current_tp_algo_client_id = (
                getattr(manage_flow, "tp_algo_client_id", None)
                if current_tp_order_id and bracket_role != "TP"
                else None
            )
            if bracket_role == "SL":
                current_sl_algo_client_id = client_algo_id or None
            else:
                current_tp_algo_client_id = client_algo_id or None

            manage_flow.set_bracket_ids(
                sl_order_id=current_sl_order_id,
                tp_order_id=current_tp_order_id,
                sl_algo_client_id=current_sl_algo_client_id,
                tp_algo_client_id=current_tp_algo_client_id,
            )

        return True

    async def _record_auxiliary_bracket_failure(
        self,
        *,
        decision: "Message",
        payload: dict[str, Any],
        symbol: str,
        side: Any,
        qty: Any,
        client_order_id: Optional[str],
        reason: str,
    ) -> None:
        bracket_role = self._canonical_auxiliary_bracket_role(client_order_id)
        if bracket_role is None:
            return
        manage_flow = self._fsm.manage_flows.get(symbol)
        handler = getattr(
            self._fsm, "_handle_bracket_protection_missing", None)
        if callable(handler):
            await handler(
                symbol=symbol,
                source_path="CloseExecutor.execute_place_order",
                failure_class="adapter_rejection",
                reason=reason,
                why_code="BRACKET_AUXILIARY_ADAPTER_REJECTION",
                rid=getattr(decision, "rid", None),
                side=side,
                qty=qty,
                entry_order_id=payload.get("parent_order_id")
                or payload.get("entry_order_id")
                or getattr(manage_flow, "entry_order_id", None),
                entry_client_order_id=getattr(
                    manage_flow, "entry_client_order_id", None),
                live_position_proven=bool(
                    manage_flow is not None
                    and self._manage_flow_allows_bracket_sync(manage_flow)
                ),
            )
            return
        emit = getattr(self._fsm, "_emit_execution_bus_event", None)
        if callable(emit):
            emit(
                "EVT:BRACKET_PLACEMENT_FAILED",
                {
                    "ts_ms": get_clock().now_ms(),
                    "symbol": symbol,
                    "source_path": "CloseExecutor.execute_place_order",
                    "failure_class": "adapter_rejection",
                    "reason": reason,
                    "why_code": "BRACKET_AUXILIARY_ADAPTER_REJECTION",
                    "remediation_action": "force_reduce_only_close",
                    "rid": getattr(decision, "rid", None),
                    "side": side,
                    "qty": str(qty) if qty is not None else None,
                    "entry_order_id": payload.get("parent_order_id")
                    or payload.get("entry_order_id")
                    or getattr(manage_flow, "entry_order_id", None),
                    "entry_client_order_id": getattr(
                        manage_flow, "entry_client_order_id", None),
                    "why": "execution:bracket_placement_failed",
                },
            )

    async def execute_cancel_order(self, decision: "Message") -> Any:
        """Cancel a specific order for the symbol in the decision payload.

        Phase 6 Package 4 seam: the typed ``CancelSubmissionPayload`` is the
        single runtime normalization owner for ``DEC:CANCEL_ORDER -> adapter
        cancellation``. Upstream producers may still emit the legacy dual-key
        payload (``order_id`` / ``orderId``); this intake canonicalizes and
        fails closed on drift, then delegates to the unchanged downstream
        bridge ``ExecPosFSM._cancel_order``.
        """
        pld = decision.pld or {}
        rid = getattr(decision, "rid", None)
        try:
            submission = CancelSubmissionPayload.from_dec_cancel(payload=pld)
        except CancelSubmissionAdapterError as exc:
            reject_ref = build_cancel_submission_trace_ref(
                status="reject",
                reason="adapter_validation",
            )
            # Fail-closed: do NOT invoke the downstream cancel bridge on
            # malformed intake. Make the reject explicitly observable instead
            # of the previous silent-return.
            existing_refs = list(getattr(decision, "data_ref", None) or [])
            if reject_ref not in existing_refs:
                existing_refs.append(reject_ref)
                try:
                    decision.data_ref = existing_refs
                except Exception:
                    pass
            LOG.error(
                "CANCEL_SUBMISSION_REJECT: contract=%s path=%s rid=%s reason=%s details=%s",
                CANCEL_SUBMISSION_CONTRACT,
                CANCEL_SUBMISSION_PATH,
                rid,
                "adapter_validation",
                exc,
            )
            try:
                order_logger.write({
                    "rid": str(rid or ""),
                    "event_type": "ORDER_CANCELLATION_FAILED",
                    "symbol": str(pld.get("symbol") or "_UNKNOWN_"),
                    "source_fsm": "CloseExecutor",
                    "why": f"cancel_submission_reject:{reject_ref}",
                })
            except Exception:
                # Observability path must never shadow the seam reject.
                pass
            return None

        success_ref = build_cancel_submission_trace_ref(status="success")
        existing_refs = list(getattr(decision, "data_ref", None) or [])
        if success_ref not in existing_refs:
            existing_refs.append(success_ref)
            try:
                decision.data_ref = existing_refs
            except Exception:
                pass
        LOG.info(
            "CANCEL_SUBMISSION_SUCCESS: contract=%s path=%s rid=%s symbol=%s order_id=%s",
            CANCEL_SUBMISSION_CONTRACT,
            CANCEL_SUBMISSION_PATH,
            rid,
            submission.symbol,
            submission.order_id,
        )
        result = await self._fsm._cancel_order(submission.symbol, submission.order_id)
        LOG.info(
            f"Cancelled order {submission.order_id} for {submission.symbol}")
        return result

    @staticmethod
    def _tracked_close_teardown_requests(
        brackets: dict[str, Any],
    ) -> list[tuple[Literal["SL", "TP"], str]]:
        tracked: list[tuple[Literal["SL", "TP"], str]] = []
        sl_order_id = str(brackets.get("sl_order_id") or "").strip()
        if sl_order_id:
            tracked.append(("SL", sl_order_id))
        tp_order_id = str(brackets.get("tp_order_id") or "").strip()
        if tp_order_id:
            tracked.append(("TP", tp_order_id))
        return tracked

    @staticmethod
    def _append_trace_ref(target: "Message", ref: str) -> None:
        refs = list(getattr(target, "data_ref", None) or [])
        if ref not in refs:
            refs.append(ref)
            try:
                target.data_ref = refs
            except Exception:
                pass

    def _build_close_submit_boundary_payload(
        self,
        *,
        event_type: str,
        trace_kind: str,
        why: str,
        rid: str,
        decision: "Message",
        submission: CloseSubmissionPayload,
        outcome: Optional[str] = None,
        adapter_response: Any = None,
        error: Exception | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "contract": CLOSE_SUBMISSION_CONTRACT,
            "path": CLOSE_SUBMISSION_PATH,
            "partial_close": submission.partial_close,
            "trace_kind": trace_kind,
        }
        if outcome is not None:
            metadata["outcome"] = outcome
        if error is not None:
            metadata["exception_class"] = type(error).__name__
            metadata["exception_message"] = str(error)
            exchange_code = getattr(error, "binance_code", None)
            if exchange_code is None:
                exchange_code = getattr(error, "code", None)
            if exchange_code is not None:
                metadata["exchange_code"] = exchange_code

        payload: dict[str, Any] = {
            "rid": rid,
            "event_type": event_type,
            "symbol": submission.symbol,
            "side": submission.side,
            "quantity": float(submission.quantity),
            "client_order_id": submission.client_order_id,
            "source_fsm": "CloseExecutor",
            "order_kind": "CLOSE",
            "order_type": "MARKET",
            "why": why,
            "timestamp": get_clock().now_ms(),
            "data_ref": list(getattr(decision, "data_ref", None) or []),
            "metadata": metadata,
        }
        if adapter_response is not None:
            payload["adapter_response"] = adapter_response
        return payload

    def _log_close_submission_reject(
        self,
        *,
        decision: "Message",
        partial_close: bool,
        reason: str,
        details: Any,
    ) -> None:
        reject_ref = build_close_submission_trace_ref(
            status="reject",
            partial_close=partial_close,
            reason=reason,
        )
        self._append_trace_ref(decision, reject_ref)
        LOG.error(
            "CLOSE_SUBMISSION_REJECT: contract=%s path=%s rid=%s reason=%s details=%s",
            CLOSE_SUBMISSION_CONTRACT,
            CLOSE_SUBMISSION_PATH,
            getattr(decision, "rid", None),
            reason,
            details,
        )
        journal = get_shadow_journal(self)
        if journal is not None:
            try:
                comparison = build_close_submission_reject_comparison(
                    decision=decision,
                    partial_close=partial_close,
                    reason=reason,
                    detail=str(details),
                )
                emit_close_shadow_comparison(
                    journal=journal,
                    comparison=comparison,
                    event_name="EVT:CLOSE_SHADOW_SUBMISSION_REJECT",
                    source_component="apps.reference.domains.execution_position.close_executor",
                    source_path="execution:close_shadow_submission_reject",
                    event_origin_type="execution",
                    truth_owner="CloseExecutor",
                    rid=getattr(decision, "rid", None),
                    payload=decision.pld or {},
                    notes=["stage=submission", "comparison_outcome=reject"],
                )
            except Exception:
                LOG.warning(
                    "CLOSE_SHADOW_SUBMISSION_REJECT_COMPARE_FAILURE: rid=%s",
                    getattr(decision, "rid", None),
                    exc_info=True,
                )

    async def _submit_close_order(
        self,
        *,
        decision: "Message",
        submission: CloseSubmissionPayload,
    ) -> Any:
        rid = getattr(decision, "rid", None) or "manual-close"

        def _write_boundary_row(
            event_type: str,
            *,
            trace_kind: str,
            why: str,
            outcome: Optional[str] = None,
            adapter_response: Any = None,
            error: Exception | None = None,
        ) -> None:
            payload = self._build_close_submit_boundary_payload(
                event_type=event_type,
                trace_kind=trace_kind,
                why=why,
                rid=rid,
                decision=decision,
                submission=submission,
                outcome=outcome,
                adapter_response=adapter_response,
                error=error,
            )

            try:
                order_logger.write(payload)
            except Exception:
                LOG.warning(
                    "Failed to write close submit boundary row: rid=%s event_type=%s",
                    rid,
                    event_type,
                    exc_info=True,
                )

        _write_boundary_row(
            "ORDER_INTENT",
            trace_kind="CLOSE_SUBMIT_ATTEMPT",
            why="close_submit_attempt",
        )
        journal = get_shadow_journal(self)
        if journal is not None:
            try:
                boundary_payload = self._build_close_submit_boundary_payload(
                    event_type="ORDER_INTENT",
                    trace_kind="CLOSE_SUBMIT_ATTEMPT",
                    why="close_submit_attempt",
                    rid=rid,
                    decision=decision,
                    submission=submission,
                )
                comparison = build_close_boundary_comparison(
                    decision=decision,
                    submission=submission,
                    boundary_payload=boundary_payload,
                    trace_kind="CLOSE_SUBMIT_ATTEMPT",
                )
                emit_close_shadow_comparison(
                    journal=journal,
                    comparison=comparison,
                    event_name="EVT:CLOSE_SHADOW_SUBMIT_BOUNDARY",
                    source_component="apps.reference.domains.execution_position.close_executor",
                    source_path="execution:close_shadow_submit_boundary",
                    event_origin_type="execution",
                    truth_owner="CloseExecutor",
                    rid=rid,
                    payload=boundary_payload,
                    notes=["stage=submit_boundary", "comparison_outcome=match"],
                )
            except Exception:
                LOG.warning(
                    "CLOSE_SHADOW_SUBMIT_BOUNDARY_COMPARE_FAILURE: rid=%s",
                    rid,
                    exc_info=True,
                )
        try:
            response = await self._fsm.adapter.place_market_reduce_only(
                submission.symbol,
                submission.side,
                submission.quantity,
                new_client_order_id=submission.client_order_id,
            )
        except Exception as exc:
            _write_boundary_row(
                "ORDER_REJECTED",
                trace_kind="CLOSE_SUBMIT_OUTCOME",
                why="close_submit_rejected",
                outcome="rejected",
                error=exc,
            )
            raise

        _write_boundary_row(
            "ORDER_PLACED",
            trace_kind="CLOSE_SUBMIT_OUTCOME",
            why="close_submit_returned_without_exception",
            outcome="submitted",
            adapter_response=response,
        )
        return response

    def _parse_requested_close_qty(
        self,
        *,
        decision: "Message",
        symbol: str,
    ) -> tuple[Optional[Decimal], bool]:
        pld = decision.pld or {}
        requested_close_qty_raw = pld.get("qty")
        if requested_close_qty_raw is None:
            return None, False

        if isinstance(requested_close_qty_raw, str):
            raw_text = requested_close_qty_raw.strip()
            if raw_text == "":
                return None, False
            if raw_text in {"0", "0.0", "0.00"}:
                return None, False
        elif requested_close_qty_raw == 0:
            return None, False

        try:
            requested_close_qty = Decimal(str(requested_close_qty_raw))
        except (InvalidOperation, TypeError, ValueError) as exc:
            self._log_close_submission_reject(
                decision=decision,
                partial_close=True,
                reason="invalid_requested_qty",
                details=f"symbol={symbol} qty={requested_close_qty_raw!r} error={exc}",
            )
            journal = get_shadow_journal(self)
            if journal is not None:
                try:
                    comparison = build_close_submission_reject_comparison(
                        decision=decision,
                        partial_close=True,
                        reason="invalid_requested_qty",
                        detail=f"symbol={symbol} qty={requested_close_qty_raw!r} error={exc}",
                    )
                    emit_close_shadow_comparison(
                        journal=journal,
                        comparison=comparison,
                        event_name="EVT:CLOSE_SHADOW_SUBMISSION_REJECT",
                        source_component="apps.reference.domains.execution_position.close_executor",
                        source_path="execution:close_shadow_submission_reject",
                        event_origin_type="execution",
                        truth_owner="CloseExecutor",
                        rid=getattr(decision, "rid", None),
                        payload=decision.pld or {},
                        notes=["stage=submission", "comparison_outcome=reject"],
                    )
                except Exception:
                    LOG.warning(
                        "CLOSE_SHADOW_SUBMISSION_REJECT_COMPARE_FAILURE: rid=%s",
                        getattr(decision, "rid", None),
                        exc_info=True,
                    )
            return None, True

        if not requested_close_qty.is_finite() or requested_close_qty <= 0:
            self._log_close_submission_reject(
                decision=decision,
                partial_close=True,
                reason="invalid_requested_qty",
                details=f"symbol={symbol} qty={requested_close_qty_raw!r}",
            )
            journal = get_shadow_journal(self)
            if journal is not None:
                try:
                    comparison = build_close_submission_reject_comparison(
                        decision=decision,
                        partial_close=True,
                        reason="invalid_requested_qty",
                        detail=f"symbol={symbol} qty={requested_close_qty_raw!r}",
                    )
                    emit_close_shadow_comparison(
                        journal=journal,
                        comparison=comparison,
                        event_name="EVT:CLOSE_SHADOW_SUBMISSION_REJECT",
                        source_component="apps.reference.domains.execution_position.close_executor",
                        source_path="execution:close_shadow_submission_reject",
                        event_origin_type="execution",
                        truth_owner="CloseExecutor",
                        rid=getattr(decision, "rid", None),
                        payload=decision.pld or {},
                        notes=["stage=submission", "comparison_outcome=reject"],
                    )
                except Exception:
                    LOG.warning(
                        "CLOSE_SHADOW_SUBMISSION_REJECT_COMPARE_FAILURE: rid=%s",
                        getattr(decision, "rid", None),
                        exc_info=True,
                    )
            return None, True

        return requested_close_qty, False

    @staticmethod
    def _tracked_teardown_log_failure(
        *,
        decision: "Message",
        symbol: str,
        bracket_type: str,
        order_id: str,
        reason: str,
        error_text: str | None = None,
    ) -> None:
        payload = {
            "rid": getattr(decision, "rid", None) or "manual-close",
            "event_type": "ORDER_CANCELLATION_FAILED",
            "symbol": symbol,
            "order_id": order_id,
            "bracket_type": bracket_type,
            "reason": reason,
            "timestamp": get_clock().now_ms(),
        }
        if error_text is not None:
            payload["error"] = error_text
        order_logger.write(payload)

    @staticmethod
    def _tracked_teardown_log_success(
        *,
        decision: "Message",
        symbol: str,
        bracket_type: str,
        order_id: str,
        reason: str,
        adapter_response: Any,
    ) -> None:
        order_logger.write({
            "rid": getattr(decision, "rid", None) or "manual-close",
            "event_type": "ORDER_CANCELLED",
            "symbol": symbol,
            "order_id": order_id,
            "bracket_type": bracket_type,
            "reason": reason,
            "adapter_response": adapter_response,
            "timestamp": get_clock().now_ms(),
        })

    @staticmethod
    def _reconcile_cancel_log_failure(
        *,
        decision: "Message",
        symbol: str,
        order_type: str,
        order_id: str,
        reason: str,
        error_text: str | None = None,
    ) -> None:
        payload = {
            "rid": getattr(decision, "rid", None) or "manual-close",
            "event_type": "ORDER_CANCELLATION_FAILED",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "reason": reason,
            "timestamp": get_clock().now_ms(),
        }
        if error_text is not None:
            payload["error"] = error_text
        order_logger.write(payload)

    @staticmethod
    def _reconcile_cancel_log_success(
        *,
        decision: "Message",
        symbol: str,
        order_type: str,
        order_id: str,
        reason: str,
        adapter_response: Any,
    ) -> None:
        order_logger.write({
            "rid": getattr(decision, "rid", None) or "manual-close",
            "event_type": "ORDER_CANCELLED",
            "symbol": symbol,
            "order_id": order_id,
            "order_type": order_type,
            "reason": reason,
            "adapter_response": adapter_response,
            "timestamp": get_clock().now_ms(),
        })

    async def _execute_tracked_close_teardown(
        self,
        *,
        decision: "Message",
        symbol: str,
        tracked_requests: list[tuple[Literal["SL", "TP"], str]],
    ) -> None:
        if not tracked_requests:
            return

        cancel_tasks: list[tuple[TrackedCloseTeardownCancelRequest, Any]] = []
        for bracket_type, order_id in tracked_requests:
            try:
                request, cancel_decision = adapt_tracked_close_teardown_to_dec_cancel(
                    decision,
                    symbol=symbol,
                    order_id=order_id,
                    bracket_type=bracket_type,
                )
            except TrackedCloseTeardownCancelBridgeError as exc:
                reject_ref = build_tracked_close_teardown_cancel_trace_ref(
                    status="reject",
                    bracket_type=bracket_type,
                    reason="bridge_validation",
                )
                self._append_trace_ref(decision, reject_ref)
                LOG.error(
                    "TRACKED_CLOSE_TEARDOWN_REJECT: contract=%s path=%s rid=%s symbol=%s bracket_type=%s order_id=%s reason=%s details=%s",
                    TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT,
                    TRACKED_CLOSE_TEARDOWN_CANCEL_PATH,
                    getattr(decision, "rid", None),
                    symbol,
                    bracket_type,
                    order_id,
                    "bridge_validation",
                    exc,
                )
                self._tracked_teardown_log_failure(
                    decision=decision,
                    symbol=symbol,
                    bracket_type=bracket_type,
                    order_id=str(order_id),
                    reason="tracked_close_teardown_bridge_reject",
                    error_text=str(exc),
                )
                continue

            self._append_trace_ref(decision, build_tracked_close_teardown_cancel_trace_ref(
                status="success",
                bracket_type=request.bracket_type,
            ))
            LOG.info(
                "TRACKED_CLOSE_TEARDOWN_SUCCESS: contract=%s path=%s rid=%s symbol=%s bracket_type=%s order_id=%s",
                TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT,
                TRACKED_CLOSE_TEARDOWN_CANCEL_PATH,
                getattr(decision, "rid", None),
                request.symbol,
                request.bracket_type,
                request.order_id,
            )
            cancel_tasks.append(
                (request, self.execute_cancel_order(cancel_decision)))

        if not cancel_tasks:
            return

        results = await asyncio.gather(
            *[task for _, task in cancel_tasks],
            return_exceptions=True,
        )
        for (request, result) in zip([req for req, _ in cancel_tasks], results):
            bracket_type = request.bracket_type
            order_id = request.order_id
            if isinstance(result, Exception):
                if self._fsm._is_unknown_order_error(result):
                    LOG.info(
                        "%s tracked bracket %s already absent (-2011) for %s",
                        bracket_type,
                        order_id,
                        symbol,
                    )
                    self._tracked_teardown_log_success(
                        decision=decision,
                        symbol=symbol,
                        bracket_type=bracket_type,
                        order_id=order_id,
                        reason="close_cancel_idempotent",
                        adapter_response={
                            "status": "UNKNOWN_ORDER_ALREADY_ABSENT"},
                    )
                else:
                    LOG.warning(
                        "Failed tracked teardown cancel for %s bracket %s on %s: %s",
                        bracket_type,
                        order_id,
                        symbol,
                        result,
                    )
                    self._tracked_teardown_log_failure(
                        decision=decision,
                        symbol=symbol,
                        bracket_type=bracket_type,
                        order_id=order_id,
                        reason="close_cancel_exception",
                        error_text=str(result),
                    )
            elif result is None:
                LOG.warning(
                    "Tracked teardown cancel rejected before downstream execution for %s bracket %s on %s",
                    bracket_type,
                    order_id,
                    symbol,
                )
                self._tracked_teardown_log_failure(
                    decision=decision,
                    symbol=symbol,
                    bracket_type=bracket_type,
                    order_id=order_id,
                    reason="tracked_close_teardown_cancel_reject",
                )
            elif self._fsm._is_cancel_success_response(result):
                LOG.info(
                    "Cancelled %s tracked bracket %s for %s",
                    bracket_type,
                    order_id,
                    symbol,
                )
                self._tracked_teardown_log_success(
                    decision=decision,
                    symbol=symbol,
                    bracket_type=bracket_type,
                    order_id=order_id,
                    reason="manual_close",
                    adapter_response=result,
                )
            else:
                cancel_status = self._fsm._cancel_status_str(result)
                LOG.warning(
                    "Tracked teardown cancel rejected for %s bracket %s on %s: status=%s",
                    bracket_type,
                    order_id,
                    symbol,
                    cancel_status,
                )
                self._tracked_teardown_log_failure(
                    decision=decision,
                    symbol=symbol,
                    bracket_type=bracket_type,
                    order_id=order_id,
                    reason="tracked_close_teardown_cancel_status_reject",
                    error_text=cancel_status,
                )

    async def _execute_reconcile_close_cancels(
        self,
        *,
        decision: "Message",
        symbol: str,
        cancelable_orders: list[tuple[str, str]],
    ) -> int:
        if not cancelable_orders:
            return 0

        cancel_tasks: list[tuple[ReconcileCloseCancelRequest, Any]] = []
        for order_type, order_id in cancelable_orders:
            try:
                request, cancel_decision = adapt_reconcile_close_to_dec_cancel(
                    decision,
                    symbol=symbol,
                    order_id=order_id,
                    order_type=order_type,
                )
            except ReconcileCloseCancelBridgeError as exc:
                reject_ref = build_reconcile_close_cancel_trace_ref(
                    status="reject",
                    order_type=str(order_type or "UNKNOWN").upper(),
                    reason="bridge_validation",
                )
                self._append_trace_ref(decision, reject_ref)
                LOG.error(
                    "RECONCILE_CLOSE_CANCEL_REJECT: contract=%s path=%s rid=%s symbol=%s order_type=%s order_id=%s reason=%s details=%s",
                    RECONCILE_CLOSE_CANCEL_CONTRACT,
                    RECONCILE_CLOSE_CANCEL_PATH,
                    getattr(decision, "rid", None),
                    symbol,
                    order_type,
                    order_id,
                    "bridge_validation",
                    exc,
                )
                self._reconcile_cancel_log_failure(
                    decision=decision,
                    symbol=symbol,
                    order_type=str(order_type or ""),
                    order_id=str(order_id or ""),
                    reason="reconcile_close_cancel_bridge_reject",
                    error_text=str(exc),
                )
                continue

            self._append_trace_ref(
                decision,
                build_reconcile_close_cancel_trace_ref(
                    status="success",
                    order_type=request.order_type,
                ),
            )
            LOG.info(
                "RECONCILE_CLOSE_CANCEL_SUCCESS: contract=%s path=%s rid=%s symbol=%s order_type=%s order_id=%s",
                RECONCILE_CLOSE_CANCEL_CONTRACT,
                RECONCILE_CLOSE_CANCEL_PATH,
                getattr(decision, "rid", None),
                request.symbol,
                request.order_type,
                request.order_id,
            )
            cancel_tasks.append(
                (request, self.execute_cancel_order(cancel_decision)))

        if not cancel_tasks:
            return 0

        reconciled_cancelled = 0
        results = await asyncio.gather(
            *[task for _, task in cancel_tasks],
            return_exceptions=True,
        )
        for request, result in zip([req for req, _ in cancel_tasks], results):
            order_type = request.order_type
            order_id = request.order_id
            if isinstance(result, Exception):
                if self._fsm._is_unknown_order_error(result):
                    LOG.info(
                        "[DEC:CLOSE RECONCILE] %s %s already gone for %s (-2011)",
                        order_type,
                        order_id,
                        symbol,
                    )
                    reconciled_cancelled += 1
                    self._reconcile_cancel_log_success(
                        decision=decision,
                        symbol=symbol,
                        order_type=order_type,
                        order_id=order_id,
                        reason="reconcile_cancel_idempotent",
                        adapter_response={
                            "status": "UNKNOWN_ORDER_ALREADY_ABSENT"},
                    )
                else:
                    LOG.warning(
                        "[DEC:CLOSE RECONCILE] Failed to cancel %s %s for %s: %s",
                        order_type,
                        order_id,
                        symbol,
                        result,
                    )
                    self._fsm._orphan_metrics["errors"] += 1
                    self._reconcile_cancel_log_failure(
                        decision=decision,
                        symbol=symbol,
                        order_type=order_type,
                        order_id=order_id,
                        reason="reconcile_cancel_exception",
                        error_text=str(result),
                    )
            elif result is None:
                LOG.warning(
                    "[DEC:CLOSE RECONCILE] Cancel rejected before downstream execution for %s %s on %s",
                    order_type,
                    order_id,
                    symbol,
                )
                self._fsm._orphan_metrics["errors"] += 1
                self._reconcile_cancel_log_failure(
                    decision=decision,
                    symbol=symbol,
                    order_type=order_type,
                    order_id=order_id,
                    reason="reconcile_cancel_reject",
                )
            elif self._fsm._is_cancel_success_response(result):
                LOG.info(
                    "[DEC:CLOSE RECONCILE] Cancelled %s %s for %s",
                    order_type,
                    order_id,
                    symbol,
                )
                self._fsm._orphan_metrics["reconcile_cancelled"] += 1
                reconciled_cancelled += 1
                self._reconcile_cancel_log_success(
                    decision=decision,
                    symbol=symbol,
                    order_type=order_type,
                    order_id=order_id,
                    reason="reconcile_cancel",
                    adapter_response=result,
                )
            else:
                status = self._fsm._cancel_status_str(result)
                LOG.warning(
                    "[DEC:CLOSE RECONCILE] Cancel response unexpected for %s %s on %s (status=%s)",
                    order_type,
                    order_id,
                    symbol,
                    status,
                )
                self._fsm._orphan_metrics["errors"] += 1
                self._reconcile_cancel_log_failure(
                    decision=decision,
                    symbol=symbol,
                    order_type=order_type,
                    order_id=order_id,
                    reason="reconcile_cancel_status_reject",
                    error_text=status,
                )

        return reconciled_cancelled

    def _build_close_submission(
        self,
        *,
        decision: "Message",
        symbol: str,
        position_amt: Decimal,
        requested_qty: Optional[Decimal],
    ) -> Optional[CloseSubmissionPayload]:
        """Phase 6 Package 5 seam intake for DEC:CLOSE -> adapter submission.

        Single runtime normalization owner for close-submission derivation.
        On success attaches the success trace ref to ``decision.data_ref`` and
        returns the typed payload. On validation failure returns ``None``
        after attaching the reject trace ref and emitting a structured
        reject log line; callers must abort without invoking the adapter.
        """
        pld = decision.pld or {}
        rid = getattr(decision, "rid", None)
        idem_key = str(
            pld.get("idempotent_key") or rid or "manual-close"
        )
        reject_hint_partial = requested_qty is not None
        try:
            submission = CloseSubmissionPayload.from_dec_close(
                symbol=symbol,
                position_amt=position_amt,
                requested_qty=requested_qty,
                idempotent_key=idem_key,
            )
        except CloseSubmissionAdapterError as exc:
            self._log_close_submission_reject(
                decision=decision,
                partial_close=reject_hint_partial,
                reason="adapter_validation",
                details=exc,
            )
            return None

        success_ref = build_close_submission_trace_ref(
            status="success",
            partial_close=submission.partial_close,
        )
        self._append_trace_ref(decision, success_ref)
        journal = get_shadow_journal(self)
        if journal is not None:
            try:
                comparison = build_close_submission_comparison(
                    decision=decision,
                    submission=submission,
                    position_amt=position_amt,
                    requested_qty=requested_qty,
                )
                emit_close_shadow_comparison(
                    journal=journal,
                    comparison=comparison,
                    event_name="EVT:CLOSE_SHADOW_SUBMISSION",
                    source_component="apps.reference.domains.execution_position.close_executor",
                    source_path="execution:close_shadow_submission",
                    event_origin_type="execution",
                    truth_owner="CloseExecutor",
                    rid=rid,
                    payload=submission.model_dump(),
                    notes=["stage=submission", "comparison_outcome=match"],
                )
            except Exception:
                LOG.warning(
                    "CLOSE_SHADOW_SUBMISSION_COMPARE_FAILURE: rid=%s",
                    rid,
                    exc_info=True,
                )
        LOG.info(
            "CLOSE_SUBMISSION_SUCCESS: contract=%s path=%s rid=%s symbol=%s side=%s qty=%s partial=%s",
            CLOSE_SUBMISSION_CONTRACT,
            CLOSE_SUBMISSION_PATH,
            rid,
            submission.symbol,
            submission.side,
            submission.quantity,
            submission.partial_close,
        )
        return submission

    async def _resolve_close_position_truth(
        self,
        *,
        symbol: str,
    ) -> _ClosePositionTruthResolution:
        symbol_upper = str(symbol or "").strip().upper()
        try:
            positions = await self._fsm.adapter.get_open_positions()
            positions_list = [
                p.to_dict() if hasattr(p, "to_dict") else (
                    p.__dict__ if not isinstance(p, dict) else p
                )
                for p in positions
            ]
        except Exception:
            return _ClosePositionTruthResolution(
                classification=(
                    _ClosePositionTruthClassification
                    .POSITION_TRUTH_UNRESOLVED
                ),
                reason="read_failed",
            )

        for pos in positions_list:
            if not isinstance(pos, dict):
                return _ClosePositionTruthResolution(
                    classification=(
                        _ClosePositionTruthClassification
                        .POSITION_TRUTH_UNRESOLVED
                    ),
                    reason="unreadable_position_payload",
                )
            if str(pos.get("symbol") or "").strip().upper() != symbol_upper:
                continue
            raw_amt = pos.get("positionAmt")
            try:
                amt = Decimal(str(raw_amt))
            except (InvalidOperation, TypeError, ValueError):
                return _ClosePositionTruthResolution(
                    classification=(
                        _ClosePositionTruthClassification
                        .POSITION_TRUTH_UNRESOLVED
                    ),
                    reason="position_amt_unreadable",
                )
            if abs(amt) < Decimal("1e-10"):
                return _ClosePositionTruthResolution(
                    classification=(
                        _ClosePositionTruthClassification.GENUINELY_FLAT
                    ),
                    position_amt=Decimal("0"),
                    reason="matched_zero_position",
                )
            return _ClosePositionTruthResolution(
                classification=(
                    _ClosePositionTruthClassification
                    .POSITION_PRESENT_AND_SUBMITTABLE
                ),
                position_amt=amt,
                reason="matched_live_position",
            )

        return _ClosePositionTruthResolution(
            classification=_ClosePositionTruthClassification.GENUINELY_FLAT,
            position_amt=Decimal("0"),
            reason="missing_symbol",
        )

    async def execute_close(self, decision: "Message") -> None:
        """Execute CLOSE/CLOSE_POSITION with bracket cleanup and reconcile passes.

        A smaller requested qty takes the early partial-close branch and returns
        before the full-close teardown/reconcile path below.
        """
        pld = decision.pld or {}
        symbol = pld.get("symbol")
        if not symbol:
            LOG.error("DEC:CLOSE missing symbol; cannot execute")
            return

        requested_close_qty, requested_close_qty_rejected = (
            self._parse_requested_close_qty(
                decision=decision,
                symbol=symbol,
            )
        )
        if requested_close_qty_rejected:
            return

        if requested_close_qty is not None:
            truth = await self._resolve_close_position_truth(symbol=symbol)
            if truth.classification is (
                _ClosePositionTruthClassification
                .POSITION_TRUTH_UNRESOLVED
            ):
                LOG.warning(
                    "Close position truth unresolved for %s during partial close; failing closed",
                    symbol,
                )
                self._emit_position_policy_close_state(
                    pld,
                    request_state="execution_noop",
                    why=(
                        "position_policy_sidecar:"
                        "execution_noop_position_truth_unresolved"
                    ),
                    extra={
                        "execution_result": "position_truth_unresolved",
                        "close_cmd_rid": getattr(decision, "rid", None),
                    },
                )
                journal = get_shadow_journal(self)
                if journal is not None:
                    try:
                        comparison = build_close_truth_gate_comparison(
                            symbol=symbol,
                            truth=truth,
                            close_cmd_rid=getattr(decision, "rid", None),
                            requested_qty=requested_close_qty,
                            detail="partial_close:position_truth_unresolved",
                        )
                        emit_close_shadow_comparison(
                            journal=journal,
                            comparison=comparison,
                            event_name="EVT:CLOSE_SHADOW_TRUTH_GATE",
                            source_component="apps.reference.domains.execution_position.close_executor",
                            source_path="execution:close_shadow_truth_gate",
                            event_origin_type="execution",
                            truth_owner="CloseExecutor",
                            rid=getattr(decision, "rid", None),
                            payload={
                                "symbol": symbol,
                                "close_cmd_rid": getattr(decision, "rid", None),
                            },
                            notes=[
                                "stage=truth_gate",
                                "comparison_outcome=reject",
                            ],
                        )
                    except Exception:
                        LOG.warning(
                            "CLOSE_SHADOW_TRUTH_GATE_COMPARE_FAILURE: rid=%s",
                            getattr(decision, "rid", None),
                            exc_info=True,
                        )
                return

            amt = truth.position_amt or Decimal("0")
            if truth.classification is (
                _ClosePositionTruthClassification.GENUINELY_FLAT
            ):
                LOG.info(f"No open position to close for {symbol}")
                self._emit_position_policy_close_state(
                    pld,
                    request_state="execution_noop",
                    why="position_policy_sidecar:execution_noop",
                    extra={
                        "execution_result": "no_live_net_position",
                        "close_cmd_rid": getattr(decision, "rid", None),
                    },
                )
                self._fsm._clear_symbol_brackets(symbol)
                self._fsm._persist_restore_artifact_snapshot(
                    trigger="close_executor:no_position_partial",
                    allow_empty=True,
                )
                journal = get_shadow_journal(self)
                if journal is not None:
                    try:
                        comparison = build_close_truth_gate_comparison(
                            symbol=symbol,
                            truth=truth,
                            close_cmd_rid=getattr(decision, "rid", None),
                            requested_qty=requested_close_qty,
                            detail="partial_close:no_live_net_position",
                        )
                        emit_close_shadow_comparison(
                            journal=journal,
                            comparison=comparison,
                            event_name="EVT:CLOSE_SHADOW_TRUTH_GATE",
                            source_component="apps.reference.domains.execution_position.close_executor",
                            source_path="execution:close_shadow_truth_gate",
                            event_origin_type="execution",
                            truth_owner="CloseExecutor",
                            rid=getattr(decision, "rid", None),
                            payload={
                                "symbol": symbol,
                                "close_cmd_rid": getattr(decision, "rid", None),
                            },
                            notes=[
                                "stage=truth_gate",
                                "comparison_outcome=reject",
                            ],
                        )
                    except Exception:
                        LOG.warning(
                            "CLOSE_SHADOW_TRUTH_GATE_COMPARE_FAILURE: rid=%s",
                            getattr(decision, "rid", None),
                            exc_info=True,
                        )
                return

            position_qty = abs(amt)
            if Decimal("0") < requested_close_qty < position_qty:
                submission = self._build_close_submission(
                    decision=decision,
                    symbol=symbol,
                    position_amt=amt,
                    requested_qty=requested_close_qty,
                )
                if submission is None:
                    return
                await self._submit_close_order(
                    decision=decision,
                    submission=submission,
                )
                self._emit_position_policy_close_state(
                    pld,
                    request_state="execution_submitted",
                    why="position_policy_sidecar:execution_submitted",
                    extra={
                        "close_cmd_rid": getattr(decision, "rid", None),
                        "execution_client_order_id": submission.client_order_id,
                        "execution_close_side": submission.side,
                        "execution_close_qty": submission.quantity,
                        "partial_close": True,
                    },
                )
                LOG.info(
                    "Partial close executed for %s: side=%s qty=%s",
                    submission.symbol,
                    submission.side,
                    submission.quantity,
                )
                lifecycle_cfg = self._fsm.config.domains.execution_position.order_lifecycle
                await get_clock().sleep_ms(lifecycle_cfg.fill_settlement_delay_ms)
                try:
                    await self._fsm.order_guardian.reconcile_symbol(symbol, decision.rid)
                except Exception as e:
                    LOG.warning(
                        f"Partial close reconcile failed for {symbol}: {e}")
                close_elapsed_ms = int(get_clock().now_sec(
                ) * 1000 - decision.ts) if decision.ts else 0
                self._fsm._emit_observability_event("DEC_CLOSE_COMPLETED", {
                    "symbol": symbol,
                    "elapsed_ms": close_elapsed_ms,
                    "orphans_cancelled": 0,
                    "partial_close": True,
                    "requested_qty": submission.quantity,
                })
                return

        # Mark the symbol as closing before bracket teardown so concurrent manage
        # flows do not race in and recreate auxiliary orders mid-close.
        manage = self._fsm.manage_flows.get(symbol)
        if manage:
            manage._closing_position = True
            manage._closing_position_ts = get_clock().now_sec()
            LOG.info(
                f"🔒 [PHASE A2] Set closing flag for {symbol} to prevent bracket race")

        # First cancel only the locally tracked bracket IDs through the
        # bounded internal teardown bridge, which then reuses the Package 4
        # typed DEC:CANCEL_ORDER intake.
        br = (
            self._fsm._symbol_brackets[symbol]
            if symbol in self._fsm._symbol_brackets
            else {}
        )
        tracked_requests = self._tracked_close_teardown_requests(br)
        await self._execute_tracked_close_teardown(
            decision=decision,
            symbol=symbol,
            tracked_requests=tracked_requests,
        )

        # Re-read the exchange position after bracket cancellation so the close
        # order uses current on-exchange size rather than cached intent state.
        truth = await self._resolve_close_position_truth(symbol=symbol)
        if truth.classification is (
            _ClosePositionTruthClassification.POSITION_TRUTH_UNRESOLVED
        ):
            LOG.warning(
                "Close position truth unresolved for %s after tracked teardown; failing closed",
                symbol,
            )
            self._emit_position_policy_close_state(
                pld,
                request_state="execution_noop",
                why=(
                    "position_policy_sidecar:"
                    "execution_noop_position_truth_unresolved"
                ),
                extra={
                    "execution_result": "position_truth_unresolved",
                    "close_cmd_rid": getattr(decision, "rid", None),
                },
            )
            if manage:
                manage._closing_position = False
                manage._closing_position_ts = 0.0
            journal = get_shadow_journal(self)
            if journal is not None:
                try:
                    comparison = build_close_truth_gate_comparison(
                        symbol=symbol,
                        truth=truth,
                        close_cmd_rid=getattr(decision, "rid", None),
                        requested_qty=None,
                        detail="full_close:position_truth_unresolved",
                    )
                    emit_close_shadow_comparison(
                        journal=journal,
                        comparison=comparison,
                        event_name="EVT:CLOSE_SHADOW_TRUTH_GATE",
                        source_component="apps.reference.domains.execution_position.close_executor",
                        source_path="execution:close_shadow_truth_gate",
                        event_origin_type="execution",
                        truth_owner="CloseExecutor",
                        rid=getattr(decision, "rid", None),
                        payload={
                            "symbol": symbol,
                            "close_cmd_rid": getattr(decision, "rid", None),
                        },
                        notes=[
                            "stage=truth_gate",
                            "comparison_outcome=reject",
                        ],
                    )
                except Exception:
                    LOG.warning(
                        "CLOSE_SHADOW_TRUTH_GATE_COMPARE_FAILURE: rid=%s",
                        getattr(decision, "rid", None),
                        exc_info=True,
                    )
            return

        amt = truth.position_amt or Decimal("0")
        if truth.classification is _ClosePositionTruthClassification.GENUINELY_FLAT:
            LOG.info(f"No open position to close for {symbol}")
            self._emit_position_policy_close_state(
                pld,
                request_state="execution_noop",
                why="position_policy_sidecar:execution_noop",
                extra={
                    "execution_result": "no_live_net_position",
                    "close_cmd_rid": getattr(decision, "rid", None),
                },
            )
            self._fsm._clear_symbol_brackets(symbol)
            self._fsm._persist_restore_artifact_snapshot(
                trigger="close_executor:no_position_full",
                allow_empty=True,
            )
            journal = get_shadow_journal(self)
            if journal is not None:
                try:
                    comparison = build_close_truth_gate_comparison(
                        symbol=symbol,
                        truth=truth,
                        close_cmd_rid=getattr(decision, "rid", None),
                        requested_qty=None,
                        detail="full_close:no_live_net_position",
                    )
                    emit_close_shadow_comparison(
                        journal=journal,
                        comparison=comparison,
                        event_name="EVT:CLOSE_SHADOW_TRUTH_GATE",
                        source_component="apps.reference.domains.execution_position.close_executor",
                        source_path="execution:close_shadow_truth_gate",
                        event_origin_type="execution",
                        truth_owner="CloseExecutor",
                        rid=getattr(decision, "rid", None),
                        payload={
                            "symbol": symbol,
                            "close_cmd_rid": getattr(decision, "rid", None),
                        },
                        notes=[
                            "stage=truth_gate",
                            "comparison_outcome=reject",
                        ],
                    )
                except Exception:
                    LOG.warning(
                        "CLOSE_SHADOW_TRUTH_GATE_COMPARE_FAILURE: rid=%s",
                        getattr(decision, "rid", None),
                        exc_info=True,
                    )
            if manage:
                manage._closing_position = False
                manage._closing_position_ts = 0.0
            return
        close_side = "SELL" if amt > 0 else "BUY"
        close_qty = str(abs(amt))
        submission = self._build_close_submission(
            decision=decision,
            symbol=symbol,
            position_amt=amt,
            requested_qty=None,
        )
        if submission is None:
            # DEF-E07: _closing_position was set at the top of this flow. Failing to
            # clear it here would leave the position permanently stuck in "closing" state,
            # blocking all future manage/open flows for this symbol.
            if manage:
                manage._closing_position = False
                manage._closing_position_ts = 0.0
                LOG.warning(
                    "DEF-E07: cleared _closing_position for %s after build_close_submission returned None",
                    symbol,
                )
            return
        close_side = submission.side
        close_qty = submission.quantity
        close_id = submission.client_order_id
        await self._submit_close_order(
            decision=decision,
            submission=submission,
        )
        self._emit_position_policy_close_state(
            pld,
            request_state="execution_submitted",
            why="position_policy_sidecar:execution_submitted",
            extra={
                "close_cmd_rid": getattr(decision, "rid", None),
                "execution_client_order_id": close_id,
                "execution_close_side": close_side,
                "execution_close_qty": close_qty,
                "partial_close": False,
            },
        )
        LOG.info(
            f"Close executed for {symbol}: side={close_side} qty={close_qty}")
        self._fsm._clear_symbol_brackets(symbol)
        self._fsm._persist_restore_artifact_snapshot(
            trigger="close_executor:close_executed",
            allow_empty=True,
        )

        # Allow exchange-side settlement to catch up before orphan cleanup.
        lifecycle_cfg = self._fsm.config.domains.execution_position.order_lifecycle
        await get_clock().sleep_ms(lifecycle_cfg.position_close_cleanup_delay_ms)

        # Second-pass reconcile scans open orders for any remaining reduce-only
        # auxiliaries, not just the bracket IDs that were tracked in memory.
        LOG.info(f"🔄 [DEC:CLOSE RECONCILE] Starting sync cleanup for {symbol}")
        try:
            open_orders = await self._fsm.adapter.get_open_orders(symbol)
            open_orders_list = [
                o.to_dict() if hasattr(o, 'to_dict') else (
                    o.__dict__ if not isinstance(o, dict) else o)
                for o in open_orders
            ]
            cancelable_orders: list[tuple[str, str]] = []
            for o in open_orders_list:
                otype = (o.get("type") or "").upper()
                reduce_only = coerce_exchange_bool(o.get("reduceOnly"))
                close_pos = coerce_exchange_bool(o.get("closePosition"))
                if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                    oid = o.get("orderId")
                    cancelable_orders.append((otype, oid))

            if cancelable_orders:
                reconciled_cancelled = await self._execute_reconcile_close_cancels(
                    decision=decision,
                    symbol=symbol,
                    cancelable_orders=cancelable_orders,
                )
                self._fsm._emit_observability_event("RECONCILE_CANCELLED", {
                    "symbol": symbol,
                    "order_count": len(cancelable_orders),
                    "metric": self._fsm._orphan_metrics["reconcile_cancelled"],
                    "reconcile_cancelled_now": reconciled_cancelled,
                })
            else:
                LOG.info(
                    f"✅ [DEC:CLOSE RECONCILE] No orphaned brackets found for {symbol}")
        except Exception as e:
            LOG.warning(
                f"⚠️ [DEC:CLOSE RECONCILE] Error during cleanup for {symbol}: {e}")
            self._fsm._orphan_metrics["errors"] += 1

        await self._fsm.order_guardian.cleanup_orphans()
        await self._fsm.order_guardian.reconcile_symbol(symbol, decision.rid)

        # Clear closing flag
        manage = self._fsm.manage_flows.get(symbol)
        if manage:
            manage._closing_position = False
            manage._closing_position_ts = 0.0
            LOG.info(
                f"🔓 [PHASE A2] Cleared closing flag for {symbol} - CLOSE complete")

        close_elapsed_ms = int(get_clock().now_sec() *
                               1000 - decision.ts) if decision.ts else 0
        self._fsm._emit_observability_event("DEC_CLOSE_COMPLETED", {
            "symbol": symbol, "elapsed_ms": close_elapsed_ms,
            "orphans_cancelled": self._fsm._orphan_metrics["reconcile_cancelled"]
        })

    async def execute_place_order(self, decision: "Message") -> None:
        """Submit a generic auxiliary order from an internal DEC:PLACE_ORDER."""

        pld = decision.pld or {}
        symbol = pld.get("symbol")
        side = pld.get("side")
        qty = pld.get("qty")
        order_type = pld["order_type"] if "order_type" in pld else "LIMIT"
        price = pld.get("price")
        stop_price = pld.get("stopPrice")
        client_id = pld.get("newClientOrderId")
        reduce_only = pld["reduceOnly"] if "reduceOnly" in pld else False

        LOG.info(
            f"Executing PLACE_ORDER: {symbol} {side} {order_type} {qty} @ {price}/{stop_price}")

        try:
            resp = None
            if order_type == "STOP_MARKET" and hasattr(self._fsm.adapter, "place_stop_market_close_position"):
                resp = await self._fsm.adapter.place_stop_market_close_position(
                    symbol, side, str(stop_price), new_client_order_id=client_id)
            elif order_type == "TAKE_PROFIT_MARKET" and hasattr(self._fsm.adapter, "place_take_profit_market_close_position"):
                resp = await self._fsm.adapter.place_take_profit_market_close_position(
                    symbol, side, str(stop_price), new_client_order_id=client_id)
            elif order_type == "LIMIT" and reduce_only and hasattr(self._fsm.adapter, "place_limit_reduce_only"):
                resp = await self._fsm.adapter.place_limit_reduce_only(
                    symbol, side, str(price), qty, new_client_order_id=client_id)
            else:
                if hasattr(self._fsm.adapter, "place_order"):
                    resp = await self._fsm.adapter.place_order(decision)
                else:
                    LOG.error(
                        f"Unsupported order type for PLACE_ORDER: {order_type}")
                    await self._record_auxiliary_bracket_failure(
                        decision=decision,
                        payload=pld,
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        client_order_id=client_id,
                        reason=f"unsupported_order_type:{order_type}",
                    )
                    return

            LOG.info(f"✅ PLACE_ORDER success: {resp}")

            if client_id and resp:
                exchange_order_id = str(
                    self._response_value(resp, "orderId", "order_id") or ""
                ).strip()
                bracket_role = self._canonical_auxiliary_bracket_role(
                    client_id)

                if bracket_role is not None:
                    if self._register_auxiliary_bracket_order(
                        decision=decision,
                        payload=pld,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        client_order_id=client_id,
                        response=resp,
                    ):
                        self._fsm._persist_restore_artifact_snapshot(
                            trigger="close_executor:aux_bracket_registered",
                            allow_empty=True,
                        )
                else:
                    order_index = self._runtime_order_index()
                    if order_index is not None and exchange_order_id:
                        try:
                            rid_for_index = str(
                                getattr(decision, "rid",
                                        "") or exchange_order_id
                            )
                            idem_key = str(
                                pld.get("idempotent_key")
                                or getattr(decision, "idempotent_key", None)
                                or client_id
                                or rid_for_index
                            )
                            order_index.upsert_from_open(
                                rid=rid_for_index,
                                idempotent_key=idem_key,
                                clientOrderId=client_id,
                                symbol=symbol,
                                side=str(side).upper() if side else "",
                                order_type=str(order_type),
                            )
                            order_index.attach_exchange_id(
                                clientOrderId=client_id,
                                exchangeOrderId=exchange_order_id,
                            )
                        except Exception as exc:
                            LOG.error(
                                "Auxiliary order reference registration failed for %s %s/%s: %s",
                                symbol,
                                client_id,
                                exchange_order_id,
                                exc,
                            )

                    order_type_upper = str(order_type).upper()
                    if order_type_upper in {"STOP_MARKET", "TAKE_PROFIT_MARKET"} or reduce_only:
                        LOG.warning(
                            "PLACE_ORDER accepted noncanonical auxiliary client_order_id without bracket registration: %s %s %s",
                            symbol,
                            client_id,
                            order_type_upper,
                        )

        except Exception as e:
            LOG.error(f"❌ PLACE_ORDER failed: {e}")
            await self._record_auxiliary_bracket_failure(
                decision=decision,
                payload=pld,
                symbol=symbol,
                side=side,
                qty=qty,
                client_order_id=client_id,
                reason=str(e),
            )
