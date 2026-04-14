"""
Intent routing for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Routes TRADE_INTENT_PROPOSED events to CMD:OPEN/CMD:CLOSE flows,
and handles TRADE_INTENT_REJECTED logging.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from apps.reference.domains.execution_position.trade_intent_reject_contracts import (
    emit_canonical_trade_intent_rejected_event,
)
from apps.reference.domains.execution_position.trade_intent_open_intake import (
    INTENT_OPEN_INTAKE_CONTRACT,
    TradeIntentOpenIntakeError,
    parse_trade_intent_open_intake,
)

if TYPE_CHECKING:
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)


class IntentRouter:
    """Routes trade intents to execution flows (OPEN/CLOSE)."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def _mark_intent_routed(
        self,
        *,
        rid: str,
        symbol: str,
        route: str,
        strategy_id: str | None,
        side: str | None,
    ) -> None:
        audit = getattr(self._fsm, "_intent_boundary_audit", None)
        if audit is None:
            return
        audit.mark_routed(
            rid=rid,
            symbol=symbol,
            route=route,
            strategy_id=strategy_id,
            side=side,
        )

    def _emit_typed_open_intake_reject(
        self,
        *,
        symbol: str,
        intent_rid: str,
        error: TradeIntentOpenIntakeError,
        data_ref: Any,
    ) -> None:
        if not hasattr(self._fsm, "bus"):
            return
        emit_canonical_trade_intent_rejected_event(
            fsm=self._fsm.bus,
            payload={
                "ts_ms": int(time.time() * 1000),
                "symbol": symbol,
                "reason_code": error.reason_code,
                "stage": "EXECUTION",
                "why": error.why[:240],
                "details": {
                    "rid": intent_rid,
                    "execution_intake_contract": INTENT_OPEN_INTAKE_CONTRACT,
                    "execution_intake_stage": "typed_open_intake",
                },
            },
            rid=intent_rid,
            src="execution_position",
            why="execution_typed_open_intake_rejected",
            logger=LOG,
            lifecycle=getattr(self._fsm, "_trade_lifecycle", None),
            write_wal=bool(
                getattr(self._fsm, "_emit_trade_intent_reject_wal", False)),
            fallback_symbol=symbol,
            fallback_reason_code=error.reason_code,
            fallback_stage="EXECUTION",
            fallback_why=error.why[:240],
            data_ref=list(data_ref or []),
        )

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
            # Router still reads early context for logging and reject fallback,
            # but non-reduce_only open normalization is owned by the typed intake.
            symbol = pld.get("instrument") or pld.get("symbol")
            if not symbol:
                LOG.error(
                    f"TRADE_INTENT_PROPOSED missing symbol/instrument: keys={list(pld.keys())}")
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
                risk_score=pld.get("risk_budget", {}).get(
                    "trade_cvar95_max_bps")
            )

            order_info = pld.get("order", {})
            # Route split remains router-owned. The typed intake governs only
            # the bounded non-reduce_only open seam.
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
                        "qty": order_info.get("qty"),
                        "trace": pld.get("trace"),
                    },
                    why=f"intent_reduce_only:{intent_rid}",
                    data_ref=msg.data_ref
                )
                LOG.info(
                    f"[{symbol}] Processing TRADE_INTENT (reduce_only) -> CMD:CLOSE")
                self._mark_intent_routed(
                    rid=intent_rid,
                    symbol=str(symbol),
                    route="CMD:CLOSE",
                    strategy_id=str(strategy_id) if strategy_id else None,
                    side=pld.get("side"),
                )
                result = self._fsm.handle(cmd_close)

            else:
                try:
                    intake = parse_trade_intent_open_intake(
                        pld,
                        fallback_rid=intent_rid,
                    )
                except TradeIntentOpenIntakeError as intake_error:
                    LOG.warning(
                        "[%s] Typed open intake rejected rid=%s contract=%s why=%s",
                        symbol,
                        intent_rid,
                        INTENT_OPEN_INTAKE_CONTRACT,
                        intake_error.why,
                    )
                    self._emit_typed_open_intake_reject(
                        symbol=str(symbol),
                        intent_rid=intent_rid,
                        error=intake_error,
                        data_ref=msg.data_ref,
                    )
                    return

                tca_budget = intake.tca_budget or {}
                risk_ctx = intake.risk_context or {}
                slippage_limit = tca_budget.get("max_slippage_bps")
                latency_limit = tca_budget.get("max_latency_ms")
                maker_pref = tca_budget.get("maker_preference")
                risk_score = risk_ctx.get("risk_score")
                cvar_budget = risk_ctx.get("trade_cvar95_bps")

                LOG.info(
                    f"[{intake.symbol}] Intent Metadata: Strategy={intake.strategy_id} "
                    f"TCA={{slippage={slippage_limit}bps, latency={latency_limit}ms, maker={maker_pref}}} "
                    f"Risk={{score={risk_score}, cvar={cvar_budget}bps}}"
                )

                cmd_payload = intake.to_cmd_open_payload()
                symbol = intake.symbol
                strategy_id = intake.strategy_id

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

                LOG.info(
                    f"[{symbol}] Processing TRADE_INTENT -> CMD:OPEN "
                    f"(qty={cmd_payload['qty']} side={cmd_payload.get('side')} "
                    f"type={cmd_payload.get('order_type')} contract={INTENT_OPEN_INTAKE_CONTRACT})")
                self._mark_intent_routed(
                    rid=intent_rid,
                    symbol=str(symbol),
                    route="CMD:OPEN",
                    strategy_id=str(strategy_id) if strategy_id else None,
                    side=pld.get("side"),
                )
                result = self._fsm.handle(cmd_open)

            # Handle Result
            if result:
                LOG.info(
                    f"[{symbol}] TRADE_INTENT processed: {result.op}:{result.verb}")

                if result.op == "EVT" and result.verb == "TRADE_INTENT_REJECTED":
                    emit_canonical_trade_intent_rejected_event(
                        fsm=self._fsm.bus,
                        payload=result.pld or {},
                        rid=result.rid or intent_rid,
                        src="execution_position",
                        why=result.why or "execution_rejected",
                        logger=LOG,
                        lifecycle=getattr(self._fsm, "_trade_lifecycle", None),
                        write_wal=bool(
                            getattr(self._fsm, "_emit_trade_intent_reject_wal", False)),
                        fallback_symbol=symbol,
                        fallback_reason_code="NRR-EXECUTION-REJECTED",
                        fallback_stage="EXECUTION",
                        fallback_why=result.why or "execution_rejected",
                        data_ref=list(result.data_ref or []),
                    )
                elif hasattr(self._fsm, "bus"):
                    out_pld = dict(result.pld or {})
                    self._fsm.bus.emit(
                        f"{result.op}:{result.verb}",
                        out_pld,
                        result.why,
                        result.data_ref,
                        rid=result.rid,
                    )

                if result.op == "ERR":
                    LOG.warning(f"[{symbol}] Execution Rejected: {result.why}")
                    if hasattr(self._fsm, "bus"):
                        emit_canonical_trade_intent_rejected_event(
                            fsm=self._fsm.bus,
                            payload={
                                "ts_ms": int(time.time() * 1000),
                                "symbol": symbol,
                                "reason_code": "NRR-EXECUTION-REJECTED",
                                "stage": "EXECUTION",
                                "why": result.why[:240] if result.why else "execution_rejected",
                                "details": {
                                    "original_verification_key": pld.get("idempotent_key"),
                                    "rid": intent_rid,
                                },
                            },
                            rid=intent_rid,
                            src="execution_position",
                            why="execution_rejected",
                            logger=LOG,
                            lifecycle=getattr(
                                self._fsm, "_trade_lifecycle", None),
                            write_wal=bool(
                                getattr(self._fsm, "_emit_trade_intent_reject_wal", False)),
                            fallback_symbol=symbol,
                            fallback_reason_code="NRR-EXECUTION-REJECTED",
                            fallback_stage="EXECUTION",
                            fallback_why=result.why[:240] if result.why else "execution_rejected",
                            data_ref=list(msg.data_ref or []),
                        )
            else:
                LOG.warning(
                    f"[{symbol}] TRADE_INTENT processed but no result returned from handle()")
                if hasattr(self._fsm, "bus"):
                    emit_canonical_trade_intent_rejected_event(
                        fsm=self._fsm.bus,
                        payload={
                            "ts_ms": int(time.time() * 1000),
                            "symbol": symbol,
                            "reason_code": "NRR-EXECUTION-INTERNAL-ERROR",
                            "stage": "EXECUTION",
                            "why": "execution_no_result",
                            "details": {
                                "rid": intent_rid
                            }
                        },
                        rid=intent_rid,
                        src="execution_position",
                        why="execution_no_result",
                        logger=LOG,
                        lifecycle=getattr(self._fsm, "_trade_lifecycle", None),
                        write_wal=bool(
                            getattr(self._fsm, "_emit_trade_intent_reject_wal", False)),
                        fallback_symbol=symbol,
                        fallback_reason_code="NRR-EXECUTION-INTERNAL-ERROR",
                        fallback_stage="EXECUTION",
                        fallback_why="execution_no_result",
                        data_ref=list(msg.data_ref or []),
                    )

        except Exception as e:
            LOG.error(
                f"Failed to process TRADE_INTENT_PROPOSED: {e}", exc_info=True)
            if hasattr(self._fsm, "bus"):
                try:
                    pld = msg.pld or {}
                    symbol = pld.get("instrument") or pld.get(
                        "symbol") or "unknown"
                    intent_rid = str(pld.get("rid") or msg.rid or "unknown")
                    emit_canonical_trade_intent_rejected_event(
                        fsm=self._fsm.bus,
                        payload={
                            "ts_ms": int(time.time() * 1000),
                            "symbol": symbol,
                            "reason_code": "NRR-EXECUTION-EXCEPTION",
                            "stage": "EXECUTION",
                            "why": f"EXCEPTION: {str(e)}"[:240],
                            "details": {
                                "error_type": type(e).__name__,
                                "rid": intent_rid,
                            }
                        },
                        rid=intent_rid,
                        src="execution_position",
                        why="execution_exception",
                        logger=LOG,
                        lifecycle=getattr(self._fsm, "_trade_lifecycle", None),
                        write_wal=bool(
                            getattr(self._fsm, "_emit_trade_intent_reject_wal", False)),
                        fallback_symbol=symbol,
                        fallback_reason_code="NRR-EXECUTION-EXCEPTION",
                        fallback_stage="EXECUTION",
                        fallback_why=f"EXCEPTION: {str(e)}"[:240],
                        data_ref=list(msg.data_ref or []),
                    )
                except Exception as emit_e:
                    LOG.error(f"Failed to emit exception rejection: {emit_e}")

    # ---------------------------------------------------------------
    # External LLM intake  (CMD:EXTERNAL_OPEN_REQUEST_V1)
    # ---------------------------------------------------------------

    def on_external_open_request(self, msg: "Message") -> None:
        """
        Handle CMD:EXTERNAL_OPEN_REQUEST_V1 from shadow_telemetry mapper.

        Validates external-specific fields, resolves valid_for_ms,
        builds CMD:OPEN Message, and delegates to existing handle() chain.
        Never emits EVT:TRADE_INTENT_REJECTED — uses dedicated reject verb.
        """
        from vfoundation.core.fsm_emit_compat import Message

        pld = msg.pld or {}
        symbol = pld.get("symbol") or "unknown"
        intent_id = pld.get("intent_id")
        rid = str(pld.get("rid")
                  or msg.rid or f"ext-{int(time.time() * 1000)}")

        try:
            # GATE 1: intent_id must be present (forensic traceability)
            if not intent_id:
                self._emit_external_rejection(
                    reason_code="NRR-EXT-MISSING-INTENT-ID",
                    symbol=symbol, intent_id=None, rid=rid,
                    reason_text="intent_id absent from external request",
                    data_ref=msg.data_ref,
                )
                return

            # GATE 2: source must be "external_llm" (fail-closed)
            if pld.get("source") != "external_llm":
                self._emit_external_rejection(
                    reason_code="NRR-EXT-SOURCE-INVALID",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text=f"source={pld.get('source')!r} != 'external_llm'",
                    data_ref=msg.data_ref,
                )
                return

            # GATE 3: order_type must be LIMIT (v1 policy)
            if pld.get("order_type") != "LIMIT":
                self._emit_external_rejection(
                    reason_code="NRR-EXT-ORDER-TYPE-NOT-LIMIT",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text=f"order_type={pld.get('order_type')!r} not LIMIT",
                    data_ref=msg.data_ref,
                )
                return

            # GATE 4: tif must be present (no silent GTC fallback)
            tif = pld.get("tif")
            if not tif or tif not in ("GTC", "GTX", "IOC", "FOK"):
                self._emit_external_rejection(
                    reason_code="NRR-EXT-MISSING-TIF",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text=f"tif={tif!r} missing or invalid",
                    data_ref=msg.data_ref,
                )
                return

            # GATE 5: price must be present (LIMIT v1 requires it)
            price = pld.get("price")
            if not price:
                self._emit_external_rejection(
                    reason_code="NRR-EXT-MISSING-PRICE",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text="price absent for LIMIT order",
                    data_ref=msg.data_ref,
                )
                return

            # GATE 6: resolve valid_for_ms — explicit precedence, separate reject codes
            valid_for_ms = pld.get("valid_for_ms")
            if valid_for_ms is not None:
                if valid_for_ms < 1000:
                    self._emit_external_rejection(
                        reason_code="NRR-EXT-MISSING-VALID-FOR-MS",
                        symbol=symbol, intent_id=intent_id, rid=rid,
                        reason_text=f"request valid_for_ms={valid_for_ms} < 1000",
                        data_ref=msg.data_ref,
                    )
                    return
            else:
                try:
                    config_ttl = self._fsm.config.strategies.llm_microstructure.pending_entry_ttl_ms
                except (AttributeError, KeyError):
                    self._emit_external_rejection(
                        reason_code="NRR-EXT-CONFIG-MISSING",
                        symbol=symbol, intent_id=intent_id, rid=rid,
                        reason_text="llm_microstructure.pending_entry_ttl_ms unreachable",
                        data_ref=msg.data_ref,
                    )
                    return
                if config_ttl is not None and config_ttl >= 1000:
                    valid_for_ms = config_ttl
                elif config_ttl is not None:
                    self._emit_external_rejection(
                        reason_code="NRR-EXT-CONFIG-INVALID",
                        symbol=symbol, intent_id=intent_id, rid=rid,
                        reason_text=f"pending_entry_ttl_ms={config_ttl} < 1000",
                        data_ref=msg.data_ref,
                    )
                    return
                else:
                    self._emit_external_rejection(
                        reason_code="NRR-EXT-MISSING-VALID-FOR-MS",
                        symbol=symbol, intent_id=intent_id, rid=rid,
                        reason_text="no valid_for_ms in request and config default is None",
                        data_ref=msg.data_ref,
                    )
                    return

            # Build CMD:OPEN payload (same shape CmdOpenPayload expects)
            cmd_payload: Dict[str, Any] = {
                "rid": rid,
                "symbol": symbol,
                "side": pld.get("side"),
                "qty": pld.get("qty"),
                "order_type": "LIMIT",
                "price": price,
                "tif": tif,
                "valid_for_ms": valid_for_ms,
                "stop_price": pld.get("stop_price"),
                "target_price": pld.get("target_price"),
                "idempotent_key": pld.get("idempotent_key"),
                "price_ref": price,
                "strategy": "llm_microstructure",
                "regime": None,
                "regime_confidence": None,
                "regime_provenance": None,
                "metadata": {
                    "strategy_id": "llm_microstructure",
                    "source": "external_llm",
                    "source_intent_id": intent_id,
                    "snapshot_ref": pld.get("snapshot_ref"),
                    "why_short": pld.get("why_short"),
                },
            }

            cmd_open = Message(
                op="CMD",
                verb="OPEN",
                src="execution_position",
                dst="execution_position",
                rid=rid,
                pld=cmd_payload,
                why=f"external_open_request:{rid}",
                data_ref=msg.data_ref,
            )

            LOG.info(
                "[%s] External open request -> CMD:OPEN (intent_id=%s rid=%s qty=%s side=%s)",
                symbol, intent_id, rid, pld.get("qty"), pld.get("side"),
            )
            self._mark_intent_routed(
                rid=rid,
                symbol=str(symbol),
                route="CMD:OPEN",
                strategy_id="llm_microstructure",
                side=pld.get("side"),
            )
            result = self._fsm.handle(cmd_open)

            # Route result to bus (same pattern as on_trade_intent_proposed)
            if result:
                LOG.info("[%s] External open request processed: %s:%s",
                         symbol, result.op, result.verb)

                if hasattr(self._fsm, "bus"):
                    out_pld = dict(result.pld or {})
                    self._fsm.bus.emit(
                        f"{result.op}:{result.verb}",
                        out_pld,
                        result.why,
                        result.data_ref,
                        rid=result.rid,
                    )

                if result.op == "ERR":
                    LOG.warning(
                        "[%s] External open rejected by EP guard: %s", symbol, result.why)
                    self._emit_external_rejection(
                        reason_code="NRR-EXECUTION-REJECTED",
                        symbol=symbol, intent_id=intent_id, rid=rid,
                        reason_text=result.why[:240] if result.why else "execution_rejected",
                        details={"rid": rid, "idempotent_key": pld.get(
                            "idempotent_key")},
                        data_ref=msg.data_ref,
                    )
            else:
                LOG.warning(
                    "[%s] External open processed but no result from handle()", symbol)
                self._emit_external_rejection(
                    reason_code="NRR-EXECUTION-INTERNAL-ERROR",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text="execution_no_result",
                    data_ref=msg.data_ref,
                )

        except Exception as e:
            LOG.error(
                "Failed to process CMD:EXTERNAL_OPEN_REQUEST_V1: %s", e, exc_info=True)
            try:
                self._emit_external_rejection(
                    reason_code="NRR-EXECUTION-EXCEPTION",
                    symbol=symbol, intent_id=intent_id, rid=rid,
                    reason_text=f"EXCEPTION: {str(e)}"[:240],
                    details={"error_type": type(e).__name__, "rid": rid},
                    data_ref=msg.data_ref,
                )
            except Exception as emit_e:
                LOG.error(
                    "Failed to emit external exception rejection: %s", emit_e)

    def _emit_external_rejection(
        self,
        *,
        reason_code: str,
        symbol: str,
        intent_id: Optional[str],
        rid: str,
        reason_text: str,
        details: Optional[Dict[str, Any]] = None,
        data_ref: Any = None,
    ) -> None:
        """Emit EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1 — never EVT:TRADE_INTENT_REJECTED."""
        LOG.warning(
            "EXTERNAL_OPEN_REJECTED: %s symbol=%s intent_id=%s rid=%s reason=%s",
            reason_code, symbol, intent_id, rid, reason_text,
        )
        if hasattr(self._fsm, "bus"):
            self._fsm.bus.emit(
                "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",
                {
                    "ts_ms": int(time.time() * 1000),
                    "rid": rid,
                    "intent_id": intent_id,
                    "symbol": symbol,
                    "reason_code": reason_code,
                    "reason_text": str(reason_text)[:240],
                    "source": "external_llm",
                    "strategy": "llm_microstructure",
                    "stage": "EXTERNAL_INTAKE",
                    "details": details,
                },
                f"external_reject:{reason_code}",
                data_ref,
            )

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
                guard_type=pld.get("reason_code") or pld.get(
                    "reason") or "DECISION_REJECT",
                reason=pld.get("why") or pld.get("context") or pld.get(
                    "details", "") or "Strategy rejection",
                strategy_id=pld.get("strategy_id")
            )
        except Exception as e:
            LOG.error(f"Failed to process TRADE_INTENT_REJECTED: {e}")
