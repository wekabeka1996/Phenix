"""
Intent routing for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Routes TRADE_INTENT_PROPOSED events to CMD:OPEN/CMD:CLOSE flows,
and handles TRADE_INTENT_REJECTED logging.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)


class IntentRouter:
    """Routes trade intents to execution flows (OPEN/CLOSE)."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def on_trade_intent_proposed(self, msg: "Message") -> None:
        """
        Handle TRADE_INTENT_PROPOSED event from DecisionMaking directly (SSOT).

        Routes:
        - Normal Intents -> CMD:OPEN
        - Reduce-Only Intents -> CMD:CLOSE
        - Failures -> EVT:TRADE_INTENT_REJECTED
        """
        from vfoundation.core.fsm_emit_compat import Message

        try:
            pld = msg.pld or {}
            symbol = pld.get("instrument") or pld.get("symbol")
            if not symbol:
                LOG.error(f"TRADE_INTENT_PROPOSED missing symbol/instrument: keys={list(pld.keys())}")
                return
            strategy_id = pld.get("strategy") or pld.get("strategy_id")
            intent_rid = str(pld.get("rid") or msg.rid or "unknown")

            self._fsm.log_adapter.log_trade_intent(
                rid=intent_rid,
                symbol=symbol,
                side=pld.get("side", ""),
                qty=pld.get("order", {}).get("qty"),
                price=pld.get("order", {}).get("price"),
                features=pld.get("features"),
                risk_score=pld.get("risk_budget", {}).get("trade_cvar95_max_bps")
            )

            order_info = pld.get("order", {})
            reduce_only = (
                pld.get("reduce_only")
                or order_info.get("reduce_only")
                or order_info.get("reduceOnly")
            )

            result: Optional[Message] = None

            if reduce_only:
                cmd_close = Message(
                    op="CMD",
                    verb="CLOSE",
                    src="execution_position",
                    dst="execution_position",
                    rid=intent_rid,
                    pld={
                        "symbol": symbol,
                        "reason": pld.get("reason") or "intent_reduce_only",
                        "idempotent_key": pld.get("idempotent_key"),
                        "retry_key": pld.get("retry_key"),
                    },
                    why=f"intent_reduce_only:{intent_rid}",
                    data_ref=msg.data_ref
                )
                LOG.info(f"[{symbol}] Processing TRADE_INTENT (reduce_only) -> CMD:CLOSE")
                result = self._fsm.handle(cmd_close)

            else:
                tca_budget = pld.get("tca_budget") or {}
                risk_ctx = pld.get("risk_context") or {}
                slippage_limit = tca_budget.get("max_slippage_bps")
                latency_limit = tca_budget.get("max_latency_ms")
                maker_pref = tca_budget.get("maker_preference")
                risk_score = risk_ctx.get("risk_score")
                cvar_budget = risk_ctx.get("trade_cvar95_bps")

                LOG.info(
                    f"[{symbol}] Intent Metadata: Strategy={strategy_id} "
                    f"TCA={{slippage={slippage_limit}bps, latency={latency_limit}ms, maker={maker_pref}}} "
                    f"Risk={{score={risk_score}, cvar={cvar_budget}bps}}"
                )

                order_type = order_info.get("order_type")
                if not order_type:
                    raise ValueError("NRR-INTENT-MISSING-ORDER_TYPE: Strategy must provide explicit order_type (LIMIT/MARKET)")

                price = str(order_info.get("price")) if order_info.get("price") else None
                tif = order_info.get("tif")

                if order_type == "LIMIT":
                    if not price:
                        raise ValueError("NRR-INTENT-MISSING-PRICE: LIMIT order requires price")
                    if not tif:
                        raise ValueError("NRR-INTENT-MISSING-TIF: LIMIT order requires tif (GTC/GTX/IOC/FOK)")
                elif order_type == "MARKET":
                    if tif:
                        raise ValueError(f"NRR-INTENT-INVALID-TIF: MARKET order must not have tif (got {tif})")

                stop_price_raw = self._fsm._resolve_price(pld, "stop_price")
                target_price_raw = self._fsm._resolve_price(pld, "target_price")

                cmd_payload = {
                    "symbol": symbol,
                    "side": pld.get("side"),
                    "qty": str(order_info.get("qty")),
                    "order_type": order_type,
                    "price": price,
                    "tif": tif,
                    "stop_price": stop_price_raw,
                    "target_price": target_price_raw,
                    "rid": intent_rid,
                    "valid_for_ms": pld.get("valid_for_ms"),
                    "idempotent_key": pld.get("idempotent_key"),
                    "price_ref": str(order_info.get("price_ref")) if order_info.get("price_ref") else None,
                    "strategy": strategy_id,
                }

                cmd_metadata: Dict[str, Any] = {}
                if strategy_id:
                    cmd_metadata["strategy_id"] = str(strategy_id)
                if isinstance(tca_budget, dict) and tca_budget:
                    cmd_metadata["tca_budget"] = dict(tca_budget)
                if isinstance(risk_ctx, dict) and risk_ctx:
                    cmd_metadata["risk_context"] = dict(risk_ctx)
                if cmd_metadata:
                    cmd_payload["metadata"] = cmd_metadata

                cmd_open = Message(
                    op="CMD",
                    verb="OPEN",
                    src="execution_position",
                    dst="execution_position",
                    rid=intent_rid,
                    pld=cmd_payload,
                    why=f"intent_execution:{intent_rid}",
                    data_ref=msg.data_ref
                )

                LOG.info(f"[{symbol}] Processing TRADE_INTENT -> CMD:OPEN (qty={cmd_payload['qty']} side={cmd_payload.get('side')} type={order_type})")
                result = self._fsm.handle(cmd_open)

            # Handle Result
            if result:
                LOG.info(f"[{symbol}] TRADE_INTENT processed: {result.op}:{result.verb}")

                if hasattr(self._fsm, "bus"):
                    out_pld = dict(result.pld or {})
                    out_pld.setdefault("rid", result.rid)
                    self._fsm.bus.emit(
                        f"{result.op}:{result.verb}",
                        out_pld,
                        result.why,
                        result.data_ref
                    )

                if result.op == "ERR":
                    LOG.warning(f"[{symbol}] Execution Rejected: {result.why}")
                    reject_evt = Message(
                        op="EVT",
                        verb="TRADE_INTENT_REJECTED",
                        src="execution_position",
                        dst="*",
                        rid=intent_rid,
                        pld={
                            "symbol": symbol,
                            "reason": result.why,
                            "original_verification_key": pld.get("idempotent_key"),
                            "rid": intent_rid,
                        },
                        why="execution_rejected",
                        data_ref=msg.data_ref,
                    )
                    if hasattr(self._fsm, "bus"):
                        self._fsm.bus.emit(
                            "EVT:TRADE_INTENT_REJECTED",
                            reject_evt.pld,
                            reject_evt.why,
                            reject_evt.data_ref
                        )
            else:
                LOG.warning(f"[{symbol}] TRADE_INTENT processed but no result returned from handle()")
                if hasattr(self._fsm, "bus"):
                    self._fsm.bus.emit(
                        "EVT:TRADE_INTENT_REJECTED",
                        {"symbol": symbol, "reason": "internal_error_no_result", "rid": intent_rid},
                        "execution_no_result",
                        msg.data_ref,
                    )

        except Exception as e:
            LOG.error(f"Failed to process TRADE_INTENT_PROPOSED: {e}", exc_info=True)
            if hasattr(self._fsm, "bus"):
                try:
                    pld = msg.pld or {}
                    symbol = pld.get("instrument") or pld.get("symbol") or "unknown"
                    self._fsm.bus.emit(
                        "EVT:TRADE_INTENT_REJECTED",
                        {
                            "symbol": symbol,
                            "reason": f"EXCEPTION: {str(e)}",
                            "error_type": type(e).__name__,
                            "rid": str(pld.get("rid") or msg.rid or "unknown"),
                        },
                        "execution_exception",
                        msg.data_ref,
                    )
                except Exception as emit_e:
                    LOG.error(f"Failed to emit exception rejection: {emit_e}")

    def on_trade_intent_rejected(self, msg: "Message") -> None:
        """
        Handle TRADE_INTENT_REJECTED event from DecisionMaking.
        Logs the rejection to aurora_trades.log for comprehensive audit trail.
        """
        try:
            pld = msg.pld or {}
            symbol = pld.get("instrument") or pld.get("symbol")
            if not symbol:
                return

            self._fsm.log_adapter.log_guard_rejection(
                rid=msg.rid or "unknown",
                symbol=symbol,
                side=pld.get("side", "unknown"),
                guard_type=pld.get("reason", "DECISION_REJECT"),
                reason=pld.get("context") or pld.get("details", "") or "Strategy rejection",
                strategy_id=pld.get("strategy_id")
            )
        except Exception as e:
            LOG.error(f"Failed to process TRADE_INTENT_REJECTED: {e}")
