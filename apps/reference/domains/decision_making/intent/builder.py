"""IntentBuilder for the execution-critical trade-intent boundary.

This helper owns the post-gate path after safety checks returned ALLOW:
- warmup and one-open-order re-checks
- order-policy and TTL resolution
- trade_intent payload assembly
- WAL persistence and FSM emission
- side-channel observability (trace, lifecycle, order logger)

It deliberately consumes upstream sizing/price decisions instead of
recomputing them here.
"""

import asyncio
import decimal
import json
import logging
import threading
import uuid
from typing import Any, Callable, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from vfoundation.core.protocol import truncate_why
from vfoundation.dr import wal
from apps.reference.utils.accessors import aget
from apps.reference.telemetry.metrics import inc_decision_blocked, inc_decision_deferred
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.regime_confidence_audit import (
    emit_regime_decision_audit,
)
from apps.reference.domains.decision_making.authority_bridge import NeocortexAuthorityBridge
from apps.reference.domains.decision_making.contracts.schemas_decision_blocked import DecisionBlockedPayload
from apps.reference.domains.decision_making.intent.builder_policy import resolve_order_policy as resolve_order_policy_impl
from apps.reference.domains.decision_making.intent.truth_artifacts import write_decision_blocked
from apps.reference.domains.decision_making.intent.builder_validators import (
    normalize_trade_inputs,
    resolve_kelly_metadata,
    resolve_risk_budgets,
    resolve_tca_preferences,
    sanitize_tpsl_payload,
)
from apps.reference.domains.decision_making.intent.payload_assembler import (
    build_decision_trace_payload,
    build_order_intent_log_entry,
    build_trade_intent_payload,
)
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)

try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock
    from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult


class IntentBuilder:
    """Build, validate, and emit TRADE_INTENT_PROPOSED events.

    Receives a ``SafetyGateResult`` (ALLOW) and executes the remaining
    pre-flight checks, order-policy validation, payload construction,
    WAL persistence, and FSM emission.
    """

    def __init__(
        self,
        *,
        fsm: Any,
        clock: "Clock",
        config: "AuroraConfig",
        tca_prefs: Any,
        risk_budgets: Any,
        safe_decimal_fn: Callable,
        check_strategy_arbitration_fn: Callable,
        warmup_gate_fn: Callable,
        emit_rejected_fn: Callable,
        record_blocked_fn: Callable[[str], None],
        record_accepted_fn: Callable[[str], None],
        emit_deferred_fn: Callable,
        get_side_bias_params_fn: Callable,
        side_intent_window: dict,
        logger: logging.Logger,
        authority_bridge: Optional[NeocortexAuthorityBridge] = None,
        authority_deadline_budget_ms: int = 20,
        shadow_emit_fn: Optional[Callable[[
            str, dict[str, Any], str], None]] = None,
        causal_state_snapshot_fn: Optional[Callable[..., Any]] = None,
        get_regime_epoch_ref_fn: Optional[Callable[[
            str], Optional[str]]] = None,
    ) -> None:
        self._fsm = fsm
        self._clock = clock
        self.config = config
        self._tca_prefs = tca_prefs
        self._risk_budgets = risk_budgets
        self._safe_decimal = safe_decimal_fn
        self._check_strategy_arbitration = check_strategy_arbitration_fn
        self._warmup_gate = warmup_gate_fn
        self._emit_rejected = emit_rejected_fn
        self._record_blocked = record_blocked_fn
        self._record_accepted = record_accepted_fn
        self._emit_deferred = emit_deferred_fn
        self._get_side_bias_params = get_side_bias_params_fn
        self._authority_bridge = authority_bridge
        self._authority_deadline_budget_ms = max(
            1, int(authority_deadline_budget_ms))
        self._shadow_emit = shadow_emit_fn
        self._causal_state_snapshot_fn = causal_state_snapshot_fn
        self._get_regime_epoch_ref = get_regime_epoch_ref_fn or (
            lambda _symbol: None)
        self._side_intent_window = side_intent_window
        self.logger = logger
        self.seq_counter: int = 0

    # -- helpers ---------------------------------------------------------------

    def _get_strict(self, obj: Any, key: str, err_msg: str) -> Any:
        """Read a required field from a dict or object and fail on None."""
        if isinstance(obj, dict):
            val = obj[key] if key in obj else None
        else:
            val = aget(obj, key, None)
        if val is None:
            raise ValueError(err_msg)
        return val

    def _reject(self, *, symbol: str, strategy_id: str, side: str, rid: str,
                reason_code: str, context: str, why_chain: list) -> None:
        """Emit the canonical reject event for builder-local contract failures."""
        self._emit_rejected(
            symbol=symbol, strategy_id=str(strategy_id), side=str(side),
            rid=str(rid), reason_code=reason_code, reason="DECISION",
            context=context,
            why_chain=(why_chain if isinstance(why_chain, list) else []),
        )
        self._record_blocked(symbol)

    def _runtime_order_index(self) -> Any:
        """Return the current OrderIndex handle when the FSM exposes one."""
        return getattr(self._fsm, "order_index", None)

    def _run_coroutine_sync(self, coro: Any) -> Any:
        """Run the authority coroutine from the synchronous builder hot path."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}
        completed = threading.Event()

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(coro)
            except BaseException as exc:
                error_box["error"] = exc
            finally:
                completed.set()

        threading.Thread(
            target=_runner,
            name="decision-making-authority-bridge",
            daemon=True,
        ).start()
        completed.wait()

        if "error" in error_box:
            raise error_box["error"]
        return result_box.get("value")

    def _proposed_action(self, *, side: str, reduce_only: bool) -> str:
        side_upper = str(side).upper()
        if reduce_only:
            return "CLOSE_SHORT" if side_upper == "BUY" else "CLOSE_LONG"
        return "OPEN_LONG" if side_upper == "BUY" else "OPEN_SHORT"

    def _build_control_decision_request(
        self,
        *,
        symbol: str,
        rid: str,
        proposed_action: str,
        decision_basis_ts: int,
        causal_state_snapshot: Optional[dict[str, Any]] = None,
    ) -> tuple[ControlDecisionRequest, int]:
        decision_ts_ms = self._clock.now_ms()
        request = ControlDecisionRequest(
            decision_id=str(uuid.uuid4()),
            rid=str(rid),
            symbol=str(symbol),
            proposed_action=str(proposed_action),
            deadline_ms=decision_ts_ms + self._authority_deadline_budget_ms,
            decision_basis_ts=int(decision_basis_ts),
            causal_state_snapshot=causal_state_snapshot or {},
        )
        return request, decision_ts_ms

    def _fallback_control_decision_response(
        self,
        *,
        request: ControlDecisionRequest,
        fallback_reason: str,
    ) -> ControlDecisionResponse:
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.FALLBACK,
            apply_result=None,
            fallback_reason=str(fallback_reason),
            ttl_ms=0,
        )

    def _build_runtime_authority_context(
        self,
        *,
        request: ControlDecisionRequest,
        response: ControlDecisionResponse,
    ) -> dict[str, Any]:
        authority_mode = getattr(response, "enforcement_mode", None)
        if authority_mode is None:
            bridge_mode = getattr(self._authority_bridge,
                                  "authority_mode", None)
            if bridge_mode is not None:
                authority_mode = getattr(bridge_mode, "value", bridge_mode)
        if authority_mode is None:
            authority_mode = getattr(
                self._authority_bridge, "_enforcement_mode", None)

        authority_mode_text = str(authority_mode or "unknown").strip().lower()
        if authority_mode_text == "enforce":
            authority_mode_text = "gated"

        apply_result = response.apply_result
        if apply_result is None and response.action == ControlDecisionAction.FALLBACK:
            apply_result = "FALLBACK_BASELINE"

        action = response.model_action or response.action
        return {
            "decision_id": request.decision_id,
            "authority_mode": authority_mode_text or "unknown",
            "action": action.value.lower(),
            "apply_result": apply_result,
            "fallback_reason": response.fallback_reason,
            "idempotent_key": request.decision_id,
        }

    def _snapshot_has_nan(self, value: Any) -> bool:
        if isinstance(value, float):
            return value != value
        if isinstance(value, dict):
            return any(self._snapshot_has_nan(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(self._snapshot_has_nan(item) for item in value)
        return False

    def _resolve_causal_state_snapshot(
        self,
        *,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        reduce_only: bool,
        rid: str,
        strategy_id: str,
        proposed_action: str,
        decision_ts_ms: int,
        decision_basis_ts: int,
        sg: "SafetyGateResult",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot: dict[str, Any] = {}
        flags: dict[str, Any] = {
            "snapshot_missing": True,
            "supports_counterfactual_join": False,
            "snapshot_provider_configured": self._causal_state_snapshot_fn is not None,
            "has_nan": False,
            "is_stale": True,
        }
        if self._causal_state_snapshot_fn is None:
            return snapshot, flags

        try:
            provided = self._causal_state_snapshot_fn(
                symbol=symbol,
                side=side,
                qty=qty,
                reduce_only=reduce_only,
                rid=rid,
                strategy_id=strategy_id,
                proposed_action=proposed_action,
                decision_ts_ms=decision_ts_ms,
                decision_basis_ts=decision_basis_ts,
                sg=sg,
            )
        except Exception:
            self.logger.warning(
                "[%s] Failed to build causal state snapshot rid=%s",
                symbol,
                rid,
                exc_info=True,
            )
            flags["snapshot_provider_error"] = True
            return {}, flags

        provider_flags: dict[str, Any] = {}
        if isinstance(provided, tuple):
            raw_snapshot, raw_flags = provided
            if isinstance(raw_snapshot, dict):
                snapshot = dict(raw_snapshot)
            if isinstance(raw_flags, dict):
                provider_flags = dict(raw_flags)
        elif isinstance(provided, dict):
            snapshot = dict(provided)

        flags.update(provider_flags)
        snapshot_ts_ms = snapshot.get("tick_ts_ms") or snapshot.get(
            "feature_event_ts_ms") or snapshot.get("ts_ms")
        try:
            snapshot_ts_ms = int(
                snapshot_ts_ms) if snapshot_ts_ms is not None else None
        except (TypeError, ValueError):
            snapshot_ts_ms = None

        flags["snapshot_missing"] = not bool(snapshot)
        flags["has_nan"] = self._snapshot_has_nan(snapshot)
        flags["is_stale"] = snapshot_ts_ms is None or snapshot_ts_ms < int(
            decision_basis_ts)
        return snapshot, flags

    def _emit_shadow_neocortex_decision_logged(
        self,
        *,
        request: ControlDecisionRequest,
        decision_ts_ms: int,
        response: ControlDecisionResponse,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        reduce_only: bool,
        rid: str,
        strategy_id: str,
        proposed_action: str,
        decision_basis_ts: int,
        sg: "SafetyGateResult",
        authority_context: Optional[dict[str, Any]] = None,
        causal_state_snapshot: Optional[dict[str, Any]] = None,
        data_quality_flags: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._shadow_emit is None:
            return
        if getattr(response, "shadow_logged", False):
            return

        if causal_state_snapshot is None or data_quality_flags is None:
            snapshot, flags = self._resolve_causal_state_snapshot(
                symbol=symbol,
                side=side,
                qty=qty,
                reduce_only=reduce_only,
                rid=rid,
                strategy_id=strategy_id,
                proposed_action=proposed_action,
                decision_ts_ms=decision_ts_ms,
                decision_basis_ts=decision_basis_ts,
                sg=sg,
            )
        else:
            snapshot = dict(causal_state_snapshot)
            flags = dict(data_quality_flags)
        action = response.model_action or response.action
        response_ts_ms = int(
            getattr(response, "returned_at_ms", decision_ts_ms))
        authority_mode = None
        apply_result = getattr(response, "apply_result", None)
        if authority_context is not None:
            authority_mode = authority_context.get("authority_mode")
            apply_result = authority_context.get("apply_result", apply_result)
        if authority_mode is None:
            authority_mode = getattr(response, "enforcement_mode", None)
        if authority_mode is None:
            authority_mode = getattr(
                self._authority_bridge, "_enforcement_mode", None)
        if authority_mode is not None:
            flags.setdefault("authority_mode", str(authority_mode).lower())
        payload = {
            "decision_id": request.decision_id,
            "rid": request.rid,
            "symbol": symbol,
            "decision_ts_ms": response_ts_ms,
            "request_ts_ms": int(decision_ts_ms),
            "response_ts_ms": response_ts_ms,
            "decision_basis_ts": int(decision_basis_ts),
            "authority_mode": authority_mode,
            "apply_result": apply_result,
            "action": action.value,
            "causal_state_snapshot": snapshot,
            "fallback_reason": response.fallback_reason,
            "data_quality_flags": flags,
        }
        try:
            self._shadow_emit(
                "SHADOW:NEOCORTEX_DECISION_LOGGED",
                payload,
                "neocortex_decision_logged",
            )
        except Exception:
            self.logger.warning(
                "[%s] Failed to emit SHADOW:NEOCORTEX_DECISION_LOGGED rid=%s",
                symbol,
                rid,
                exc_info=True,
            )

    async def _request_authority(
        self,
        *,
        request: ControlDecisionRequest,
        decision_ts_ms: int,
    ) -> tuple[ControlDecisionRequest, int, ControlDecisionResponse]:
        timeout_ms = max(1, request.deadline_ms - decision_ts_ms)
        response = await self._authority_bridge.request_authority(
            request,
            timeout_ms=timeout_ms,
        )
        return request, decision_ts_ms, response

    def _request_authority_sync(
        self,
        *,
        symbol: str,
        rid: str,
        proposed_action: str,
        decision_basis_ts: int,
        causal_state_snapshot: Optional[dict[str, Any]] = None,
    ) -> tuple[ControlDecisionRequest, int, ControlDecisionResponse]:
        request, decision_ts_ms = self._build_control_decision_request(
            symbol=symbol,
            rid=rid,
            proposed_action=proposed_action,
            decision_basis_ts=decision_basis_ts,
            causal_state_snapshot=causal_state_snapshot,
        )
        if self._authority_bridge is None:
            return (
                request,
                decision_ts_ms,
                self._fallback_control_decision_response(
                    request=request,
                    fallback_reason="AI_OFFLINE",
                ),
            )
        try:
            return self._run_coroutine_sync(
                self._request_authority(
                    request=request,
                    decision_ts_ms=decision_ts_ms,
                )
            )
        except Exception as exc:
            self.logger.error(
                "[%s] Neocortex authority bridge failed rid=%s: %s",
                symbol,
                rid,
                exc,
                exc_info=True,
            )
            return (
                request,
                decision_ts_ms,
                self._fallback_control_decision_response(
                    request=request,
                    fallback_reason="TIMEOUT_OR_ERROR",
                ),
            )

    def _emit_neocortex_veto(
        self,
        *,
        symbol: str,
        rid: str,
        why_chain: list,
        proposed_action: str,
        decision_basis_ts: int,
        response: ControlDecisionResponse,
    ) -> None:
        reason_code = "NEOCORTEX_VETO"
        ts_ms = self._clock.now_ms()
        self.logger.warning(
            "[%s] NEOCORTEX_VETO rid=%s proposed_action=%s result=%s",
            symbol,
            rid,
            proposed_action,
            response.apply_result or "BLOCK",
        )

        try:
            blocked_payload = write_decision_blocked(
                symbol=symbol,
                reason_code=reason_code,
                reason="Neocortex vetoed the proposed trade",
                path="decision_making.intent.builder:neocortex_authority",
                why="neocortex veto",
                stage="intent_builder",
                src="decision_making",
                ts_ms=ts_ms,
                rid=str(rid),
                why_chain=why_chain,
                details={
                    "decision_id": response.decision_id,
                    "proposed_action": proposed_action,
                    "decision_basis_ts": int(decision_basis_ts),
                    "apply_result": response.apply_result,
                    "fallback_reason": response.fallback_reason,
                    "ttl_ms": int(response.ttl_ms),
                },
            )
            payload_obj = DecisionBlockedPayload.model_validate(
                blocked_payload)
            self._fsm.emit(
                "EVT:DECISION_BLOCKED",
                payload=payload_obj.model_dump(),
                why=f"decision_blocked:{reason_code}",
                data_ref=why_chain,
            )
            inc_decision_blocked(stage="intent_builder",
                                 reason_code=reason_code)
        except Exception:
            self.logger.error(
                "[%s] Failed to emit DECISION_BLOCKED for Neocortex veto rid=%s",
                symbol,
                rid,
                exc_info=True,
            )
        finally:
            self._record_blocked(symbol)

    def _cancel_entry_reservation(self, order_index: Any, rid: str) -> None:
        """Release a pending ENTRY_INTENT placeholder after a pre-emit failure."""
        if order_index is None:
            return
        try:
            order_index.cancel_reservation(str(rid))
        except Exception as exc:
            self.logger.warning(
                "[IntentBuilder] Failed to cancel reservation rid=%s: %s",
                rid,
                exc,
            )

    # -- main entry point ------------------------------------------------------

    def build_and_emit(
        self,
        *,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        price: decimal.Decimal,
        why_chain: list,
        rid: str,
        reduce_only: bool,
        strategy_id: str,
        decision_ts_ms: Optional[int],
        stop_price: Optional[str],
        target_price: Optional[str],
        entry_plan_trace: Optional[dict],
        tf_sec: Optional[int],
        max_slippage_bps: Optional[int],
        max_latency_ms: Optional[int],
        risk_score: Optional[float],
        tpsl_owner_ctx: Optional[dict] = None,
        strategy_trace: Optional[dict] = None,
        authority_context: Optional[dict[str, Any]] = None,
        normalize_mode: str = "signed_v2",
        sg: "SafetyGateResult",
    ) -> None:
        """Build and emit a TRADE_INTENT_PROPOSED event.

        Execution order matters here: the builder performs the last contract
        checks, persists the proposal to WAL, emits it through the FSM, and
        only then commits arbitration/post-emit bookkeeping.
        """
        intent_side = sg.intent_side
        trace_ts_ms = sg.trace_ts_ms
        order_index = None
        reservation_active = False

        def _release_entry_reservation() -> None:
            nonlocal reservation_active
            if not reservation_active:
                return
            self._cancel_entry_reservation(order_index, rid)
            reservation_active = False

        # ── Pre-flight: warmup re-check ────────────────────────
        if self._warmup_gate(
            symbol=symbol, rid=rid, reduce_only=reduce_only,
            context="decision_making:_propose_trade_intent",
        ):
            return

        # ── CAS guard (ENTRY only) ─────────────────────────────
        if not reduce_only:
            try:
                order_index = self._runtime_order_index()
                if order_index:
                    if not order_index.try_reserve_entry(symbol, rid):
                        now_ms = self._clock.now_ms()
                        retry_key = f"order_in_flight:{symbol}:{rid}"
                        self.logger.info(
                            f"[{symbol}] TRADE_INTENT_DEFERRED: NRR-ORDER-IN-FLIGHT"
                        )
                        inc_decision_deferred("NRR-ORDER-IN-FLIGHT", symbol)
                        self._emit_deferred(
                            symbol=symbol, reason="NRR-ORDER-IN-FLIGHT",
                            retry_key=retry_key, next_allowed_ts=now_ms + 1000,
                            original_event_name="EVT:TRADE_INTENT_PROPOSED",
                            original_payload_min={
                                "symbol": symbol, "side": side,
                                "rid": rid, "strategy_id": strategy_id,
                            },
                            attempt=1, max_attempts=3,
                            why_chain=(why_chain or []) + ["order_in_flight"],
                            context="decision_making:one_open_order_guard",
                        )
                        self._record_blocked(symbol)
                        return
                    reservation_active = True
            except Exception as e:
                self.logger.error(
                    f"[{symbol}] OrderIndex access failed: {e}", exc_info=True)
                self._emit_deferred(
                    symbol=symbol,
                    reason="NRR-ORDER-INDEX-FAIL",
                    retry_key=f"order_index_fail:{symbol}:{rid}",
                    next_allowed_ts=self._clock.now_ms() + 1000,
                    original_event_name="EVT:TRADE_INTENT_PROPOSED",
                    original_payload_min={
                        "symbol": symbol,
                        "side": side,
                        "rid": rid,
                        "strategy_id": strategy_id,
                    },
                    attempt=1,
                    max_attempts=3,
                    why_chain=(why_chain or []) + ["order_index_failure"],
                    context="decision_making:order_index_failure",
                )
                self._record_blocked(symbol)
                return

        # ── Decimal conversion (after guards) ──────────────────
        try:
            normalized_inputs = normalize_trade_inputs(qty=qty, price=price)
            qty = normalized_inputs.qty
            price = normalized_inputs.price
        except Exception as _e:
            self.logger.error(
                f"[{symbol}] Invalid qty/price: qty={qty!r} price={price!r}: {_e}")
            self._record_blocked(symbol)
            _release_entry_reservation()
            return

        # ── TCA prefs ──────────────────────────────────────────
        try:
            tca_prefs = resolve_tca_preferences(
                tca_prefs=self._tca_prefs,
                max_slippage_bps=max_slippage_bps,
                max_latency_ms=max_latency_ms,
                get_strict=self._get_strict,
            )
        except ValueError as e:
            self.logger.error(f"TCA Config Block: {e}")
            _release_entry_reservation()
            return

        # ── Risk budgets ───────────────────────────────────────
        try:
            risk_budgets = resolve_risk_budgets(
                risk_budgets=self._risk_budgets,
                get_strict=self._get_strict,
            )
        except ValueError as e:
            self.logger.error(f"RiskBudget Config Block: {e}")
            _release_entry_reservation()
            return

        # ── Order policy resolution ────────────────────────────
        order_type, tif, valid_for_ms = self._resolve_order_policy(
            symbol=symbol, strategy_id=strategy_id, side=side, rid=rid,
            tf_sec=tf_sec, reduce_only=reduce_only, why_chain=why_chain,
        )
        if order_type is None:
            _release_entry_reservation()
            return  # rejection already emitted

        # ── SL/TP sanitization ─────────────────────────────────
        tpsl_payload = sanitize_tpsl_payload(
            stop_price=stop_price,
            target_price=target_price,
            safe_decimal_fn=self._safe_decimal,
            tpsl_owner_ctx=tpsl_owner_ctx,
        )
        regime_provenance = getattr(sg, "regime_provenance", None)
        try:
            kelly_metadata = resolve_kelly_metadata(
                config=self.config,
                strategy_id=str(strategy_id),
            )
        except ValueError as e:
            self.logger.error(f"[{symbol}] Kelly metadata config block: {e}")
            self._record_blocked(symbol)
            _release_entry_reservation()
            return

        # ── Payload assembly ───────────────────────────────────
        trade_intent = build_trade_intent_payload(
            symbol=symbol,
            side=side,
            strategy_id=str(strategy_id),
            rid=str(rid),
            qty=qty,
            price=price,
            reduce_only=reduce_only,
            order_type=order_type,
            tif=tif,
            max_slippage_bps=tca_prefs.max_slippage_bps,
            max_latency_ms=tca_prefs.max_latency_ms,
            maker_preference=tca_prefs.maker_preference,
            risk_score=risk_score,
            trade_cvar95_max_bps=risk_budgets.trade_cvar95_max_bps,
            session_cvar95_max_bps=risk_budgets.session_cvar95_max_bps,
            p=kelly_metadata.p,
            payoff_ratio_r=kelly_metadata.payoff_ratio_r,
            kelly_fraction=kelly_metadata.kelly_fraction,
            kelly_provenance=kelly_metadata.provenance,
            valid_for_ms=valid_for_ms,
            why_chain=why_chain,
            stop_price=tpsl_payload.stop_price,
            target_price=tpsl_payload.target_price,
            entry_plan_trace=entry_plan_trace,
            regime=sg.regime,
            regime_confidence=sg.regime_confidence,
            resolved_min_regime_confidence=getattr(
                sg, "resolved_min_regime_confidence", None),
            threshold_applied=getattr(sg, "threshold_applied", None),
            threshold_verdict=getattr(sg, "threshold_verdict", None),
            threshold_reason=getattr(sg, "threshold_reason", None),
            regime_confidence_gate_verdict=getattr(
                sg, "regime_confidence_gate_verdict", None),
            regime_provenance=regime_provenance,
            regime_epoch_ref=self._get_regime_epoch_ref(symbol),
            tpsl_owner_ctx=tpsl_payload.owner_ctx,
            strategy_trace=strategy_trace,
            authority_context=authority_context,
        )

        # ── Arbitration pre-check ──────────────────────────────
        commit = self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=False)
        if not commit["allowed"]:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: Arbitration rejected: {commit['reason']}")
            self._record_blocked(symbol)
            _release_entry_reservation()
            return

        if authority_context is None and self._authority_bridge is not None:
            proposed_action = self._proposed_action(
                side=side, reduce_only=reduce_only)
            decision_basis_ts_value = int(
                decision_ts_ms or trace_ts_ms or self._clock.now_ms())
            causal_snapshot, causal_flags = self._resolve_causal_state_snapshot(
                symbol=symbol,
                side=side,
                qty=qty,
                reduce_only=reduce_only,
                rid=str(rid),
                strategy_id=str(strategy_id),
                proposed_action=proposed_action,
                decision_ts_ms=self._clock.now_ms(),
                decision_basis_ts=decision_basis_ts_value,
                sg=sg,
            )
            decision_request, authority_decision_ts_ms, authority_response = self._request_authority_sync(
                symbol=symbol,
                rid=str(rid),
                proposed_action=proposed_action,
                decision_basis_ts=decision_basis_ts_value,
                causal_state_snapshot=causal_snapshot,
            )
            authority_context = self._build_runtime_authority_context(
                request=decision_request,
                response=authority_response,
            )
            self._emit_shadow_neocortex_decision_logged(
                request=decision_request,
                decision_ts_ms=authority_decision_ts_ms,
                response=authority_response,
                symbol=symbol,
                side=side,
                qty=qty,
                reduce_only=reduce_only,
                rid=str(rid),
                strategy_id=str(strategy_id),
                proposed_action=proposed_action,
                decision_basis_ts=decision_basis_ts_value,
                sg=sg,
                authority_context=authority_context,
                causal_state_snapshot=causal_snapshot,
                data_quality_flags=causal_flags,
            )
            if authority_response.action == ControlDecisionAction.BLOCK:
                self._emit_neocortex_veto(
                    symbol=symbol,
                    rid=str(rid),
                    why_chain=why_chain,
                    proposed_action=proposed_action,
                    decision_basis_ts=decision_basis_ts_value,
                    response=authority_response,
                )
                _release_entry_reservation()
                return
            if authority_response.action == ControlDecisionAction.FALLBACK:
                self.logger.warning(
                    "[%s] Neocortex authority fallback rid=%s reason=%s",
                    symbol,
                    rid,
                    authority_response.fallback_reason,
                )
            trade_intent["authority_context"] = authority_context
        try:
            emit_regime_decision_audit(
                logger=self.logger,
                symbol=str(symbol),
                rid=str(rid),
                lifecycle_id=str(trade_intent["idempotent_key"]),
                strategy_id=str(strategy_id),
                sg=sg,
                outcome="ALLOW",
            )
        except Exception:
            self.logger.debug(
                "REGIME_AUDIT decision emit failed in IntentBuilder",
                exc_info=True,
            )

        # ── Forensic trace ─────────────────────────────────────
        trace_payload = build_decision_trace_payload(
            rid=str(rid),
            symbol=symbol,
            strategy_id=str(strategy_id),
            trace_ts_ms=trace_ts_ms,
            intent_side=intent_side,
            order_side=str(side),
            lifecycle_id=str(trade_intent["idempotent_key"]),
            sg=sg,
            strategy_trace=strategy_trace if isinstance(
                strategy_trace, dict) else None,
            regime_provenance=regime_provenance,
            tpsl_owner_ctx=tpsl_payload.owner_ctx,
            tf_sec=tf_sec,
        )
        if tpsl_payload.owner_ctx is not None:
            self.logger.info(
                "[%s] TPSL_OWNER_INTENT intended=%s final=%s reason=%s",
                symbol,
                tpsl_payload.owner_ctx.get("intended_owner"),
                tpsl_payload.owner_ctx.get("final_owner"),
                tpsl_payload.owner_ctx.get("owner_loss_reason"),
            )
        try:
            self._fsm.emit("EVT:DECISION_TRACE_EMITTED", payload=trace_payload,
                           why="decision_trace", data_ref=why_chain)
        except Exception as emit_e:
            self.logger.error(
                f"[{symbol}] OBSERVABILITY: EVT:DECISION_TRACE_EMITTED emit failed. "
                f"RID={rid}. reason={emit_e}"
            )

        # ── Record accepted ────────────────────────────────────
        try:
            self._record_accepted(symbol)
        except Exception as e:
            self.logger.warning(
                f"Failed to record accepted intent metrics: {e}")

        # ── WAL + FSM emit ─────────────────────────────────────
        # Arbitration is committed only after both durability and boundary emit
        # succeeded, so a failed append/emit must leave the arbitration window
        # unpoisoned for the competing strategy.
        try:
            intent_evt = Message(
                op="EVT", verb="TRADE_INTENT_PROPOSED", src="decision_making",
                dst="execution_position", rid=str(rid), pld=trade_intent,
                why=truncate_why("trade_intent") or "trade_intent",
                data_ref=[str(x) for x in why_chain] if isinstance(
                    why_chain, list) else [],
                intent="PROPOSAL",
            )
            res = wal.append(intent_evt.model_dump())
            if res is None:
                self.logger.error(
                    f"[{symbol}] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID={rid}")
                _release_entry_reservation()
                return
        except Exception as wal_e:
            self.logger.warning(
                f"Failed to write TRADE_INTENT_PROPOSED to WAL: {wal_e}")
            _release_entry_reservation()
            return

        try:
            self._fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload=trade_intent,
                           why="trade_intent", data_ref=why_chain)
        except Exception as emit_e:
            self.logger.error(
                f"[{symbol}] CRITICAL: FSM EMIT FAILED for EVT:TRADE_INTENT_PROPOSED. "
                f"RID={rid}. reason={emit_e}")
            _release_entry_reservation()
            return

        # ── Arbitration final commit ───────────────────────────
        reservation_active = False
        self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=True)

        # ── Lifecycle logger ───────────────────────────────────
        if _trade_lifecycle is not None:
            try:
                _trade_lifecycle.on_intent(
                    rid=str(rid), symbol=symbol, side=intent_side,
                    regime=str(sg.regime) if sg.regime else "",
                    confidence=float(
                        sg.regime_confidence) if sg.regime_confidence is not None else None,
                    regime_provenance=regime_provenance if isinstance(
                        regime_provenance, dict) else None,
                    signal_score=float(
                        sg.signal_score) if sg.signal_score is not None else None,
                    strategy_id=str(strategy_id), entry_type=order_type,
                )
            except Exception:
                pass

        # ── TAP LOG ────────────────────────────────────────────
        log_entry = {
            "symbol": symbol, "tf_sec": None,
            "bar_end_ts_ms": trace_ts_ms,
            "bar_id": f"{symbol}:intent:{trace_ts_ms}",
            "seq": self.seq_counter, "source": "dm_intent_emitted",
            "why": "intent_proposed",
        }
        print(json.dumps(log_entry), flush=True)
        self.seq_counter += 1

        # ── Side-bias bookkeeping ──────────────────────────────
        try:
            if not reduce_only:
                if symbol not in self._side_intent_window:
                    self._side_intent_window[symbol] = {
                        "buys": [], "sells": []}
                window_data = self._side_intent_window[symbol]
                now_sec = self._clock.now_sec()
                _, bias_window_sec, _, _ = self._get_side_bias_params(symbol)
                window_data["buys"] = [
                    ts for ts in window_data["buys"] if now_sec - ts < bias_window_sec]
                window_data["sells"] = [
                    ts for ts in window_data["sells"] if now_sec - ts < bias_window_sec]
                if intent_side == "LONG":
                    window_data["buys"].append(now_sec)
                elif intent_side == "SHORT":
                    window_data["sells"].append(now_sec)
        except Exception:
            pass

        # ── OrderLogger ────────────────────────────────────────
        # lifecycle_id mirrors idempotent_key at the top level so downstream
        # execution/order forensics can correlate the proposal without digging
        # through metadata.
        order_logger.write(
            build_order_intent_log_entry(
                rid=rid,
                lifecycle_id=trade_intent["idempotent_key"],
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=side,
                qty=qty,
                price=price,
                sg=sg,
                regime_provenance=regime_provenance,
                normalize_mode=normalize_mode,
            )
        )

    # -- Order policy resolution -----------------------------------------------

    def _resolve_order_policy(
        self,
        *,
        symbol: str,
        strategy_id: str,
        side: str,
        rid: str,
        tf_sec: Optional[int],
        reduce_only: bool,
        why_chain: list,
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Resolve order_type, tif, valid_for_ms.  Returns (None, ..., ...) on rejection."""
        return resolve_order_policy_impl(
            config=self.config,
            reject_fn=self._reject,
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            rid=rid,
            tf_sec=tf_sec,
            reduce_only=reduce_only,
            why_chain=why_chain,
        )
