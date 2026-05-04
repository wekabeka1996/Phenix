import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from apps.reference.core.time import get_clock
from vfoundation.core.fsm_emit_compat import Message
from apps.reference.telemetry.trade_lifecycle_logger import (
    EXECUTION_FILL_INGRESS_RECORD_KIND,
    append_trade_lifecycle_record,
)
from ..contract_layer.trade_executed_contracts import normalize_trade_executed_payload

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.fill_ingress_coordinator"
)


class FillIngressCoordinator:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm

    def build_canonical_fill_message(
        self,
        event: Message,
        *,
        fill_source: str,
    ) -> Optional[Message]:
        raw_payload = dict(getattr(event, "pld", None) or {})
        normalized = normalize_trade_executed_payload(
            raw_payload,
            fallback_rid=getattr(event, "rid", None),
            order_index=getattr(self._fsm, "order_index", None),
        )
        symbol = str(
            normalized.get("symbol") or raw_payload.get("symbol") or ""
        ).strip().upper()
        if not symbol:
            LOG.warning(
                "CANONICAL_FILL_INGRESS_SKIPPED: missing symbol for %s payload_keys=%s",
                fill_source,
                sorted(raw_payload.keys()),
            )
            return None

        payload = dict(raw_payload)
        payload.update(normalized)
        payload["symbol"] = symbol

        quantity = payload.get("qty") or payload.get(
            "quantity") or payload.get("last_fill_qty")
        if quantity is not None:
            quantity = str(quantity)
            payload["qty"] = quantity
            payload["quantity"] = quantity

        price = payload.get("price")
        if price is not None:
            payload["price"] = str(price)

        side = payload.get("side")
        if side is not None:
            payload["side"] = str(side).upper()

        order_id = payload.get("orderId") or payload.get("exchangeOrderId")
        if order_id is not None:
            payload["orderId"] = str(order_id)
            payload.setdefault("exchangeOrderId", str(order_id))

        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")
        if client_order_id is not None:
            payload["clientOrderId"] = str(client_order_id)
            payload["client_order_id"] = str(client_order_id)

        rid = payload.get("rid") or getattr(event, "rid", None) or order_id
        if rid is not None:
            payload["rid"] = str(rid)

        now_ms = get_clock().now_ms()
        payload["fill_source"] = fill_source
        payload["canonical_fill_trace_id"] = (
            f"exec-fill:{symbol}:{fill_source}:{payload.get('rid') or order_id or now_ms}:{now_ms}"
        )
        payload.setdefault("event_ts_ms", payload.get(
            "ts_ms") or payload.get("ts") or now_ms)

        event_data = event.model_dump()
        event_data["op"] = "EVT"
        event_data["verb"] = "TRADE_EXECUTED"
        event_data["pld"] = payload
        if rid is not None:
            event_data["rid"] = str(rid)
        return Message(**event_data)

    def missing_fill_activation_fields(self, payload: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        for field in ("symbol", "qty", "price", "side"):
            value = payload.get(field)
            if value in (None, "", "None"):
                missing.append(field)
        return missing

    def append_execution_fill_ingress_record(
        self,
        *,
        canonical_msg: Message,
        trigger_event: str,
        fill_source: str,
        manage_flow_created: bool,
        manage_state_before: str,
        manage_state_after: str,
        result: Optional[Message],
        activation_skipped_reason: Optional[str] = None,
    ) -> None:
        payload = getattr(canonical_msg, "pld", None) or {}
        symbol = str(payload.get("symbol") or "")
        record = {
            "record_kind": EXECUTION_FILL_INGRESS_RECORD_KIND,
            "event_type": "EXECUTION_FILL_INGRESS",
            "ts_ms": get_clock().now_ms(),
            "trigger_event": trigger_event,
            "fill_source": fill_source,
            "canonical_fill_trace_id": payload.get("canonical_fill_trace_id"),
            "rid": payload.get("rid") or getattr(canonical_msg, "rid", None),
            "symbol": symbol,
            "order_id": payload.get("orderId"),
            "client_order_id": payload.get("clientOrderId") or payload.get("client_order_id"),
            "manage_flow_created": manage_flow_created,
            "manage_state_before": manage_state_before or None,
            "manage_state_after": manage_state_after or None,
            "activation_skipped_reason": activation_skipped_reason,
            "result_op": getattr(result, "op", None),
            "result_verb": getattr(result, "verb", None),
            "portfolio_position_signature": (
                self._fsm._get_portfolio_position_signature(
                    symbol) if symbol else None
            ),
            "portfolio_positions_last_ts_ms": (
                (self._fsm._latest_portfolio_state or {}).get("positions_last_ts_ms")
            ),
            "portfolio_position_amt": self._fsm._latest_portfolio_position_amt(symbol),
        }
        append_trade_lifecycle_record(
            {key: value for key, value in record.items() if value is not None},
            log_file=self._fsm._trade_lifecycle_log_path(),
        )

    def handle_canonical_fill_ingress(
        self,
        event: Message,
        *,
        fill_source: str,
        process_result: bool,
    ) -> Optional[Message]:
        canonical_msg = self.build_canonical_fill_message(
            event,
            fill_source=fill_source,
        )
        if canonical_msg is None:
            return None

        payload = getattr(canonical_msg, "pld", None) or {}
        symbol = str(payload.get("symbol") or "")
        missing_fields = self.missing_fill_activation_fields(payload)
        manage_flow = None
        manage_flow_created = False
        manage_state_before = ""

        self._fsm._remember_proven_terminal_close(
            payload,
            trigger_event=getattr(event, "verb", "UNKNOWN"),
        )

        if not missing_fields and symbol:
            manage_flow_created = symbol not in self._fsm.manage_flows
            _, manage_flow, _ = self._fsm._get_or_create_flows(symbol)
            manage_state_before = self._fsm._manage_state_value(manage_flow)

        if fill_source == "trade_executed":
            self._fsm._evt_handlers.on_trade_executed(canonical_msg)

        bookkeeping_msg = canonical_msg
        if fill_source == "trade_executed":
            bookkeeping_data = canonical_msg.model_dump()
            bookkeeping_payload = dict(payload)
            bookkeeping_payload["_skip_trade_lifecycle_on_fill"] = True
            bookkeeping_data["pld"] = bookkeeping_payload
            bookkeeping_msg = Message(**bookkeeping_data)
        self._fsm._evt_handlers.on_order_fill(bookkeeping_msg)

        if missing_fields:
            self.append_execution_fill_ingress_record(
                canonical_msg=canonical_msg,
                trigger_event=getattr(event, "verb", "UNKNOWN"),
                fill_source=fill_source,
                manage_flow_created=False,
                manage_state_before="",
                manage_state_after="",
                result=None,
                activation_skipped_reason="missing_fields:" +
                ",".join(missing_fields),
            )
            return None

        # DUAL-INVOCATION-GUARD: for LIMIT-DEFERRED entries, _pending_brackets is set in
        # open_executor._store_pending_brackets when the LIMIT order was submitted.
        # event_handlers.on_order_fill (called above) already submitted
        # bracket_manager.place_deferred_brackets as an async task (Path B).
        # Without the guard below, manage_flow.handle would call _place_brackets (Path A),
        # causing dual SL/TP submission -> Binance -4130 -> force-close of valid position.
        # Guard: flag manage_flow so _place_brackets is skipped for this fill only.
        if manage_flow is not None:
            _fill_entry_id = str(payload.get("orderId") or "")
            if _fill_entry_id and self._fsm._pending_brackets.get(_fill_entry_id):
                manage_flow._deferred_bracket_entry_id = _fill_entry_id
                LOG.info(
                    "[LIMIT-DEFERRED] Flagging manage_flow to skip _place_brackets "
                    "for entry_order_id=%s: bracket_manager.place_deferred_brackets owns this entry",
                    _fill_entry_id,
                )
        result = manage_flow.handle(
            canonical_msg) if manage_flow is not None else None
        manage_state_after = self._fsm._manage_state_value(manage_flow)

        payload["manage_flow_created"] = manage_flow_created
        payload["manage_state_before"] = manage_state_before
        payload["manage_state_after"] = manage_state_after
        payload["portfolio_position_signature"] = self._fsm._get_portfolio_position_signature(
            symbol)
        payload["portfolio_positions_last_ts_ms"] = (
            (self._fsm._latest_portfolio_state or {}).get("positions_last_ts_ms")
        )
        portfolio_position_amt = self._fsm._latest_portfolio_position_amt(symbol)
        if portfolio_position_amt is not None:
            payload["portfolio_position_amt"] = portfolio_position_amt

        self.append_execution_fill_ingress_record(
            canonical_msg=canonical_msg,
            trigger_event=getattr(event, "verb", "UNKNOWN"),
            fill_source=fill_source,
            manage_flow_created=manage_flow_created,
            manage_state_before=manage_state_before,
            manage_state_after=manage_state_after,
            result=result,
        )

        if self._fsm._position_policy_sidecar is not None and (
            result is None or getattr(result, "op", None) != "ERR"
        ):
            if fill_source == "trade_executed":
                self._fsm._position_policy_sidecar.on_trade_executed(canonical_msg)
            else:
                self._fsm._position_policy_sidecar.on_order_fill(canonical_msg)

        if process_result:
            self._fsm._process_flow_result(result)
        return result
