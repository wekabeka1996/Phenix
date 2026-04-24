"""IntentEmitter for defer/reject lifecycle events and regime-flip closes.

The helper centralizes three boundary concerns that must stay aligned:
- canonical deferred and rejected event emission
- coarse blocked-vs-seen monitoring for risk-gate alerts
- regime-flip enforcement for reduce-only close paths

It is intentionally thin: it normalizes payloads, persists truth artifacts, and
delegates actual open/close proposals back to injected facade helpers.
"""

import decimal
import logging
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from apps.reference.contracts.runtime_regime_layers import (
    is_structural_regime_payload,
    normalize_structural_regime_label,
)
from apps.reference.domains.decision_making.intent.truth_artifacts import (
    canonicalize_intent_deferred_reason,
    write_intent_deferred,
)
from apps.reference.domains.decision_making.intent.reject_wal import write_trade_intent_rejected

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


class IntentEmitter:
    """Emission helpers for intent lifecycle side effects.

    The facade injects the FSM, portfolio access, and close/open proposal hooks;
    this class keeps only the normalization, persistence, and monitoring logic.
    """

    def __init__(
        self,
        fsm: Any,
        clock: "Clock",
        config: "AuroraConfig",
        alert_manager: Any,
        get_portfolio: Callable[[], Optional[Dict]],
        propose_trade_intent: Callable,
        logger: logging.Logger,
        *,
        emit_reduce_only_close_fn: Optional[Callable] = None,
        registry_lookup_fn: Optional[Callable] = None,
    ) -> None:
        self._fsm = fsm
        self._clock = clock
        self.config = config
        self.alert_manager = alert_manager
        self._get_portfolio = get_portfolio
        self._propose_trade_intent = propose_trade_intent
        self.logger = logger
        # Canonical close path for regime-flip (injected from facade — FlipOrchestrator.emit_reduce_only_close)
        self._emit_reduce_only_close = emit_reduce_only_close_fn
        # Registry owner lookup for strategy resolution (injected from facade — dm._get_registry_owners_for_symbol)
        self._registry_lookup_fn = registry_lookup_fn

        # Counters for risk gate alert monitoring
        self.intents_seen_total: int = 0
        self.intents_blocked_total: int = 0
        self.last_alert_check_time: float = self._clock.now_sec()

    # -- Deferred Emission -------------------------------------------------

    def emit_intent_deferred_v1(
        self,
        *,
        symbol: str,
        reason: str,
        retry_key: str,
        next_allowed_ts: int,
        original_event_name: str,
        original_payload_min: Dict[str, Any],
        attempt: int = 1,
        max_attempts: int = 5,
        why_chain: list[str] | None = None,
        context: str | None = None,
    ) -> None:
        """Emit the canonical INTENT_DEFERRED payload and matching truth row."""
        now_ms = self._clock.now_ms()
        canonical_reason, reason_code, raw_reason = canonicalize_intent_deferred_reason(
            reason
        )
        # Deferred-open retry TTL is strict config: missing SSOT must block the
        # helper rather than silently creating an unbounded retry contract.
        try:
            ttl_ms = int(self.config.strategies.aurora.decision.retry_ttl_ms)
        except AttributeError as e:
            raise ConfigContractError(
                path="strategies.aurora.decision.retry_ttl_ms",
                why=f"Missing required strict config field: {e}",
                symbol=symbol,
            )
        payload: Dict[str, Any] = {
            "retry_key": retry_key,
            "symbol": symbol,
            "reason": canonical_reason,
            "reason_code": reason_code,
            "next_allowed_ts": int(next_allowed_ts),
            "attempt": int(attempt),
            "max_attempts": int(max_attempts),
            "retry_policy": {
                "attempt": int(attempt),
                "max_attempts": int(max_attempts),
                "backoff_ms": max(0, int(next_allowed_ts) - now_ms),
                "ttl_ms": ttl_ms,
            },
            "original_event": {
                "event_name": original_event_name,
                "payload_min": original_payload_min,
            },
            "why_chain": why_chain or [],
            "created_ts": now_ms,
        }
        if context:
            payload["context"] = context
        if raw_reason:
            payload["raw_reason"] = raw_reason
        # Persist the truth artifact before the public FSM emit so forensic WAL
        # rows exist even if the live event path is not observed downstream.
        write_intent_deferred(
            symbol=symbol,
            reason=canonical_reason,
            reason_code=reason_code,
            retry_key=retry_key,
            next_allowed_ts=int(next_allowed_ts),
            attempt=int(attempt),
            max_attempts=int(max_attempts),
            original_event=payload["original_event"],
            src="decision_making",
            ts_ms=now_ms,
            rid=original_payload_min.get("rid"),
            why_chain=why_chain or [],
            context=context,
            retry_policy=payload["retry_policy"],
            raw_reason=raw_reason,
        )
        self._fsm.emit(
            "EVT:INTENT_DEFERRED",
            payload,
            why=f"intent_deferred:{reason_code}",
            data_ref=why_chain or []
        )

    # -- Rejected Emission -------------------------------------------------

    def emit_trade_intent_rejected(
        self,
        *,
        symbol: str,
        strategy_id: str,
        side: str,
        rid: str,
        reason_code: str,
        reason: str,
        context: str,
        why_chain: list[str] | None = None,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """Emit + persist a canonical reject event.

        This helper is intentionally best-effort: the decision loop should not
        crash while trying to report a rejection, even though that means a WAL
        or FSM failure can suppress the reject artifact.
        """
        try:
            ts_ms = self._clock.now_ms()

            stage = str(reason).upper()
            if stage not in ("RISK", "STRATEGY", "DECISION", "EXECUTION"):
                stage = "DECISION"

            payload: Dict[str, Any] = {
                "ts_ms": ts_ms,
                "symbol": symbol,
                "strategy_id": str(strategy_id),
                "side": str(side).lower(),
                "rid": str(rid),
                "reason_code": str(reason_code),
                "stage": stage,
                "why": str(context),
                "context": str(context),
                "why_chain": list(why_chain or []),
            }
            if details:
                payload["details"] = details

            write_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side).lower(),
                rid=str(rid),
                reason_code=str(reason_code),
                stage=stage,  # type: ignore[arg-type]
                why=str(context),
                context=str(context),
                why_chain=list(why_chain or []),
                details=details,
                src="decision_making",
                ts_ms=ts_ms,
            )

            self._fsm.emit(
                "EVT:TRADE_INTENT_REJECTED",
                payload,
                why=f"intent_rejected:{reason_code}",
                data_ref=list(why_chain or [])
            )
        except Exception:
            return

    # -- Retry Scheduling --------------------------------------------------

    def schedule_open_retry(self, symbol: str, original_context: dict, cooldown_ms: int, reason: str) -> None:
        """Emit INTENT_DEFERRED for flip-orchestration reopen attempts."""
        next_ts = self._clock.now_ms() + cooldown_ms

        payload = {
            "retry_key": f"flip-{symbol}-{int(self._clock.now_sec())}",
            "symbol": symbol,
            "next_allowed_ts": next_ts,
            "attempt": 1,
            "max_attempts": int(getattr(self.config.strategies.aurora.decision, "retry_max_count", 3)),
        }

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Deferring OPEN until {next_ts} (reason: {reason})")
        self.emit_intent_deferred_v1(
            symbol=symbol,
            reason=reason,
            retry_key=payload["retry_key"],
            next_allowed_ts=next_ts,
            original_event_name="EVT:TRADE_INTENT_PROPOSED",
            original_payload_min=original_context,
            attempt=1,
            max_attempts=payload["max_attempts"],
            why_chain=["flip_orchestration_defer"],
            context="flip_orchestration_defer",
        )

    # -- Intent Counting ---------------------------------------------------

    def record_blocked_intent(self, symbol: str) -> None:
        """Record a blocked intent and check alert thresholds."""
        self.intents_blocked_total += 1
        self.intents_seen_total += 1
        self.check_and_emit_risk_gate_alert()

    def record_accepted_intent(self, symbol: str) -> None:
        """Record an accepted intent and check alert thresholds."""
        self.intents_seen_total += 1
        self.check_and_emit_risk_gate_alert()

    # -- Risk Gate Alert ---------------------------------------------------

    def check_and_emit_risk_gate_alert(self) -> None:
        """
        Periodically check if blocked intents % exceeds threshold,
        and emit alert via AlertManager if available.
        Check every 10 seconds to avoid excessive calls.
        """
        if not self.alert_manager:
            return

        current_time = self._clock.now_sec()
        if current_time - self.last_alert_check_time < 10.0:
            return

        self.last_alert_check_time = current_time

        risk_gate_cfg = self.config.domains.decision_making.risk_gate
        min_intents = risk_gate_cfg.min_intents_for_check

        if self.intents_seen_total < min_intents:
            return

        # Counters are cumulative over the current process lifetime; this alert
        # is a coarse health signal, not a per-symbol or sliding-window metric.
        blocked_pct = (self.intents_blocked_total /
                       self.intents_seen_total) * 100

        mode = getattr(self.config.trading, "mode", None)
        if mode is None:
            raise ValueError(
                "FAIL-CLOSED: trading.mode is required for risk gate alerts. "
                "Configure trading.mode in trading.yaml (testnet or production)."
            )

        if mode == "testnet":
            threshold_pct = risk_gate_cfg.threshold_pct_testnet
        else:
            threshold_pct = risk_gate_cfg.threshold_pct_production

        if blocked_pct > threshold_pct:
            self.logger.warning(
                f"Risk gate alert: {blocked_pct:.1f}% intents blocked "
                f"({self.intents_blocked_total}/{self.intents_seen_total})"
            )
            try:
                self.alert_manager.check_risk_gate(blocked_pct)
            except Exception as e:
                self.logger.error(f"Error emitting risk gate alert: {e}")

    # -- Strategy Resolution for Close Path --------------------------------

    def resolve_strategy_id_for_close(
        self,
        symbol: str,
        position_context: Optional[Dict],
    ) -> Tuple[Optional[str], bool, str]:
        """Resolve strategy_id for a regime-flip close. Fail-closed if ambiguous.

        Resolution order:
        1. position_context.get("strategy_id") — forward-compat guard only
           (PositionData schema in schemas.py has no strategy_id field currently)
        2. Registry single-owner check — if exactly one strategy assigned to symbol
        3. Fail-closed: return (None, True, reason)

        NOTE: PositionData schema (schemas.py) defines: symbol, positionAmt,
        entryPrice, unRealizedProfit, leverage. No strategy_id field.
        In production, resolution always proceeds to step 2 (registry).

        Returns:
            (strategy_id, is_ambiguous, reason)
            is_ambiguous=True -> caller MUST fail-closed, never default to "aurora"
        """
        # 1. Position-context field (forward-compat; schema currently has no such field)
        if isinstance(position_context, dict):
            strat = position_context.get("strategy_id")
            if strat and str(strat) not in ("", "None", "null"):
                return str(strat), False, "position_field"

        # 2. Registry single-owner resolution (only if exactly one owner)
        if self._registry_lookup_fn is not None:
            try:
                owners = self._registry_lookup_fn(symbol)
                if isinstance(owners, list) and len(owners) == 1:
                    return str(owners[0]), False, "registry_single_owner"
                if isinstance(owners, list) and len(owners) > 1:
                    return None, True, f"registry_multi_owner:{owners}"
            except Exception as e:
                return None, True, f"registry_lookup_error:{e}"

        return None, True, "strategy_unresolvable:no_registry"

    # -- Regime Flip Handling ----------------------------------------------

    def handle_regime_flip(self, symbol: str, regime_data: Any) -> None:
        """
        Check if new regime conflicts with existing position; close via canonical path.

        P0 FIX: Uses canonical emit_reduce_only_close path (not generic entry proposal).
        Resolves strategy_id from registry (fail-closed if ambiguous).
        No silent default to 'aurora' for non-aurora symbols.
        """
        try:
            # Only structural regime updates are allowed to trigger forced close
            # logic; transient/non-structural payloads are ignored here.
            if isinstance(regime_data, dict) and not is_structural_regime_payload(regime_data):
                return
            regime = normalize_structural_regime_label(
                regime_data.get("regime") if isinstance(
                    regime_data, dict) else regime_data
            )

            portfolio = self._get_portfolio()
            if not portfolio:
                return

            pos_list = portfolio["positions"] if "positions" in portfolio else [
            ]
            curr_pos = next(
                (p for p in pos_list if p.get("symbol") == symbol), None)

            if not curr_pos:
                return

            qty_val = float(curr_pos["positionAmt"]
                            if "positionAmt" in curr_pos else 0)
            if abs(qty_val) < 1e-9:
                return

            is_long = qty_val > 0

            should_close = False
            reason = ""

            if regime == "TREND_UP" and not is_long:
                should_close = True
                reason = "Short position in TREND_UP"
            elif regime == "TREND_DOWN" and is_long:
                should_close = True
                reason = "Long position in TREND_DOWN"
            elif regime == "UNCERTAIN":
                should_close = True
                reason = "Position in UNCERTAIN regime"

            if not should_close:
                return

            self.logger.warning(
                f"[{symbol}] REGIME FLIP ENFORCEMENT: {reason}. Closing {qty_val}.")

            rid = f"rf-{int(self._clock.now_sec())}"
            close_side = "SELL" if is_long else "BUY"

            # P0 FIX: Resolve strategy_id explicitly from position context / registry.
            # Fail-closed if ambiguous — never silently default to "aurora".
            strategy_id, is_ambiguous, resolve_reason = self.resolve_strategy_id_for_close(
                symbol=symbol,
                position_context=curr_pos,
            )

            if is_ambiguous or strategy_id is None:
                self.logger.error(
                    f"[{symbol}] REGIME_FLIP_ENFORCEMENT: BLOCKED — strategy_id "
                    f"unresolvable (reason={resolve_reason}). No silent default. Close NOT emitted."
                )
                # Use canonical reject helper: WAL write + FSM emit + telemetry
                self.emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id="UNRESOLVED",
                    side=close_side,
                    rid=rid,
                    reason_code="REGIME_FLIP_STRATEGY_UNRESOLVABLE",
                    reason="DECISION",
                    context=f"regime_flip:strategy_unresolvable:{resolve_reason}",
                    why_chain=["regime_flip_enforcement",
                               regime, resolve_reason],
                )
                return

            # P0 FIX: Use canonical close path (FlipOrchestrator.emit_reduce_only_close).
            # This avoids generic entry proposal semantics and entry TTL contamination.
            if self._emit_reduce_only_close is not None:
                emitted = self._emit_reduce_only_close(
                    symbol=symbol,
                    reason=f"regime_flip_{regime}",
                    rid=rid,
                    strategy_id=strategy_id,
                )
                if not emitted:
                    self.logger.warning(
                        f"[{symbol}] REGIME_FLIP_ENFORCEMENT: emit_reduce_only_close returned False "
                        f"(position qty zero or invalid). strategy_id={strategy_id}"
                    )
            else:
                # Should not occur in production — facade always injects this callable
                self.logger.error(
                    f"[{symbol}] REGIME_FLIP_ENFORCEMENT: emit_reduce_only_close_fn not injected! "
                    f"Falling back to _propose_trade_intent (degraded path). strategy_id={strategy_id}"
                )
                self._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(abs(qty_val))),
                    price=decimal.Decimal("0"),
                    why_chain=["regime_flip_enforcement", regime],
                    rid=rid,
                    reduce_only=True,
                    strategy_id=strategy_id,
                )
        except Exception as e:
            self.logger.warning(f"[{symbol}] Error in handle_regime_flip: {e}")
