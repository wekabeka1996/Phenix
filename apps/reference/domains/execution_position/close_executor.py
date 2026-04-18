"""Close/cancel execution helper for execution_position.

This module owns the imperative side of DEC:CLOSE, DEC:CANCEL_ORDER, and the
generic DEC:PLACE_ORDER path used by manage/auxiliary flows.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.cancel_submission_adapter import (
    CANCEL_SUBMISSION_CONTRACT,
    CANCEL_SUBMISSION_PATH,
    CancelSubmissionAdapterError,
    CancelSubmissionPayload,
    build_cancel_submission_trace_ref,
)
from apps.reference.domains.execution_position.close_submission_adapter import (
    CLOSE_SUBMISSION_CONTRACT,
    CLOSE_SUBMISSION_PATH,
    CloseSubmissionAdapterError,
    CloseSubmissionPayload,
    build_close_submission_trace_ref,
)
from apps.reference.domains.execution_position.utils import (
    classify_client_order_id,
    coerce_exchange_bool,
    generate_client_order_id,
)

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)


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

    async def execute_cancel_order(self, decision: "Message") -> None:
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
            return

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
        await self._fsm._cancel_order(submission.symbol, submission.order_id)
        LOG.info(
            f"Cancelled order {submission.order_id} for {submission.symbol}")

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
            reject_ref = build_close_submission_trace_ref(
                status="reject",
                partial_close=reject_hint_partial,
                reason="adapter_validation",
            )
            existing_refs = list(getattr(decision, "data_ref", None) or [])
            if reject_ref not in existing_refs:
                existing_refs.append(reject_ref)
                try:
                    decision.data_ref = existing_refs
                except Exception:
                    pass
            LOG.error(
                "CLOSE_SUBMISSION_REJECT: contract=%s path=%s rid=%s reason=%s details=%s",
                CLOSE_SUBMISSION_CONTRACT,
                CLOSE_SUBMISSION_PATH,
                rid,
                "adapter_validation",
                exc,
            )
            return None

        success_ref = build_close_submission_trace_ref(
            status="success",
            partial_close=submission.partial_close,
        )
        existing_refs = list(getattr(decision, "data_ref", None) or [])
        if success_ref not in existing_refs:
            existing_refs.append(success_ref)
            try:
                decision.data_ref = existing_refs
            except Exception:
                pass
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

        requested_close_qty: Optional[Decimal] = None
        requested_close_qty_raw = pld.get("qty")
        if requested_close_qty_raw not in (None, "", "0", 0):
            try:
                requested_close_qty = abs(
                    Decimal(str(requested_close_qty_raw)))
            except Exception:
                LOG.warning(
                    "DEC:CLOSE invalid qty=%r for %s; falling back to full close",
                    requested_close_qty_raw,
                    symbol,
                )

        if requested_close_qty is not None:
            try:
                positions = await self._fsm.adapter.get_open_positions()
                positions_list = [
                    p.to_dict() if hasattr(p, "to_dict") else (
                        p.__dict__ if not isinstance(p, dict) else p
                    )
                    for p in positions
                ]
                pos = next(
                    (p for p in positions_list if p.get("symbol") == symbol), None)
            except Exception:
                pos = None

            amt = 0.0
            if pos is not None:
                try:
                    amt = float(pos["positionAmt"]
                                if "positionAmt" in pos else 0)
                except Exception:
                    amt = 0.0
            if abs(amt) < 1e-10:
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
                return

            position_qty = abs(Decimal(str(amt)))
            if Decimal("0") < requested_close_qty < position_qty:
                submission = self._build_close_submission(
                    decision=decision,
                    symbol=symbol,
                    position_amt=Decimal(str(amt)),
                    requested_qty=requested_close_qty,
                )
                if submission is None:
                    return
                await self._fsm.adapter.place_market_reduce_only(
                    submission.symbol,
                    submission.side,
                    submission.quantity,
                    new_client_order_id=submission.client_order_id,
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

        # First cancel the bracket IDs we already track locally.
        br = self._fsm._symbol_brackets[symbol] if symbol in self._fsm._symbol_brackets else {
        }
        tasks = []
        bracket_order_ids = []
        if br.get("sl_order_id"):
            tasks.append(self._fsm._cancel_order(symbol, br["sl_order_id"]))
            bracket_order_ids.append(("SL", br["sl_order_id"]))
        if br.get("tp_order_id"):
            tasks.append(self._fsm._cancel_order(symbol, br["tp_order_id"]))
            bracket_order_ids.append(("TP", br["tp_order_id"]))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (bracket_type, oid), result in zip(bracket_order_ids, results):
                if isinstance(result, Exception):
                    if self._fsm._is_unknown_order_error(result):
                        LOG.info(
                            f"ℹ️ {bracket_type} bracket {oid} already absent (-2011) for {symbol}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "close_cancel_idempotent", "timestamp": get_clock().now_ms()
                        })
                    else:
                        LOG.warning(
                            f"❌ Failed to cancel {bracket_type} bracket {oid} for {symbol}: {result}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLATION_FAILED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "close_cancel_exception", "error": str(result),
                            "timestamp": get_clock().now_ms()
                        })
                else:
                    if self._fsm._is_cancel_success_response(result):
                        LOG.info(
                            f"✅ Cancelled {bracket_type} bracket {oid} for {symbol}")
                        order_logger.write({
                            "rid": decision.rid or "manual-close",
                            "event_type": "ORDER_CANCELLED", "symbol": symbol,
                            "order_id": oid, "bracket_type": bracket_type,
                            "reason": "manual_close", "adapter_response": result,
                            "timestamp": get_clock().now_ms()
                        })
                    else:
                        cancel_status = self._fsm._cancel_status_str(result)
                        LOG.warning(
                            f"❌ Cancel rejected for {bracket_type} bracket {oid}: status={cancel_status}")

        # Re-read the exchange position after bracket cancellation so the close
        # order uses current on-exchange size rather than cached intent state.
        try:
            positions = await self._fsm.adapter.get_open_positions()
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]
            pos = next(
                (p for p in positions_list if p.get("symbol") == symbol), None)
        except Exception:
            pos = None
        amt = 0.0
        if pos is not None:
            try:
                amt = float(pos["positionAmt"] if "positionAmt" in pos else 0)
            except Exception:
                amt = 0.0
        if abs(amt) < 1e-10:
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
            return
        close_side = "SELL" if amt > 0 else "BUY"
        close_qty = str(abs(Decimal(str(amt))))
        submission = self._build_close_submission(
            decision=decision,
            symbol=symbol,
            position_amt=Decimal(str(amt)),
            requested_qty=None,
        )
        if submission is None:
            return
        close_side = submission.side
        close_qty = submission.quantity
        close_id = submission.client_order_id
        await self._fsm.adapter.place_market_reduce_only(
            submission.symbol,
            submission.side,
            submission.quantity,
            new_client_order_id=submission.client_order_id,
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
            cancel_tasks = []
            for o in open_orders_list:
                otype = (o.get("type") or "").upper()
                reduce_only = coerce_exchange_bool(o.get("reduceOnly"))
                close_pos = coerce_exchange_bool(o.get("closePosition"))
                if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                    oid = o.get("orderId")
                    cancel_tasks.append(
                        (otype, oid, self._fsm._cancel_order(symbol, oid)))

            if cancel_tasks:
                results = await asyncio.gather(*[task[2] for task in cancel_tasks], return_exceptions=True)
                for (otype, oid, _), result in zip(cancel_tasks, results):
                    if isinstance(result, Exception):
                        if self._fsm._is_unknown_order_error(result):
                            LOG.info(
                                f"ℹ️ [DEC:CLOSE RECONCILE] {otype} {oid} already gone for {symbol} (-2011)")
                        else:
                            LOG.warning(
                                f"❌ [DEC:CLOSE RECONCILE] Failed to cancel {otype} {oid} for {symbol}: {result}")
                            self._fsm._orphan_metrics["errors"] += 1
                    else:
                        if self._fsm._is_cancel_success_response(result):
                            LOG.info(
                                f"✅ [DEC:CLOSE RECONCILE] Cancelled {otype} {oid} for {symbol}")
                            self._fsm._orphan_metrics["reconcile_cancelled"] += 1
                        else:
                            status = self._fsm._cancel_status_str(result)
                            LOG.warning(
                                f"❌ [DEC:CLOSE RECONCILE] Cancel response unexpected for {otype} {oid} (status={status})")
                            self._fsm._orphan_metrics["errors"] += 1

                self._fsm._emit_observability_event("RECONCILE_CANCELLED", {
                    "symbol": symbol,
                    "order_count": len(cancel_tasks),
                    "metric": self._fsm._orphan_metrics["reconcile_cancelled"]
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
