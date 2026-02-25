"""
IntentEmitter — Rejection/defer emission, alert monitoring, and regime flip handling.

Extracted from decision_making.py (Phase 14A decomposition).
Manages intent lifecycle events: deferred, rejected, blocked/accepted counting.

LOC budget: <=500 (Constitution S3).
"""

import decimal
import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from .trade_intent_reject_wal import write_trade_intent_rejected

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


class IntentEmitter:
    """
    Emission helpers for trade intent lifecycle events.

    Owns blocked/seen counters and alert-checking logic.
    FSM and propose_trade_intent are injected from the facade.
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
    ) -> None:
        self._fsm = fsm
        self._clock = clock
        self.config = config
        self.alert_manager = alert_manager
        self._get_portfolio = get_portfolio
        self._propose_trade_intent = propose_trade_intent
        self.logger = logger

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
        now_ms = self._clock.now_ms()
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
            "reason": reason,
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
        self._fsm.emit("EVT:INTENT_DEFERRED", payload, why=f"intent_deferred:{reason}")

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
        """Emit + persist an explicit rejection event so blocks are observable."""
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

            self._fsm.emit("EVT:TRADE_INTENT_REJECTED", payload, why=f"intent_rejected:{reason_code}")
        except Exception:
            return

    # -- Retry Scheduling --------------------------------------------------

    def schedule_open_retry(self, symbol: str, original_context: dict, cooldown_ms: int, reason: str) -> None:
        """Emit EVT:INTENT_DEFERRED to schedule retry after close."""
        next_ts = self._clock.now_ms() + cooldown_ms

        payload = {
            "retry_key": f"flip-{symbol}-{int(self._clock.now_sec())}",
            "symbol": symbol,
            "reason": reason,
            "next_allowed_ts": next_ts,
            "attempt": 1,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:TRADE_INTENT_PROPOSED",
                "payload_min": original_context,
            },
            "created_ts": self._clock.now_ms(),
            "why_chain": ["flip_orchestration_defer"],
        }

        self.logger.info(f"[{symbol}] FLIP_ORCHESTRATION: Deferring OPEN until {next_ts} (reason: {reason})")
        self._fsm.emit("EVT:INTENT_DEFERRED", payload, why=f"intent_deferred:{reason}")

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

    # -- Regime Flip Handling ----------------------------------------------

    def handle_regime_flip(self, symbol: str, regime_data: Any) -> None:
        """
        Check if new regime conflicts with existing position and close if needed.
        Enforces 'Immediate Closure' on regime flips.
        """
        try:
            regime = regime_data.get("regime") if isinstance(regime_data, dict) else str(regime_data)

            portfolio = self._get_portfolio()
            if not portfolio:
                return

            pos_list = portfolio["positions"] if "positions" in portfolio else []
            curr_pos = next((p for p in pos_list if p.get("symbol") == symbol), None)

            if not curr_pos:
                return

            qty_val = float(curr_pos["positionAmt"] if "positionAmt" in curr_pos else 0)
            if abs(qty_val) < 1e-9:
                return

            is_long = qty_val > 0

            should_close = False
            reason = ""

            if regime == "BULL_TREND" and not is_long:
                should_close = True
                reason = f"Short position in BULL_TREND"
            elif regime == "BEAR_TREND" and is_long:
                should_close = True
                reason = f"Long position in BEAR_TREND"
            elif regime == "UNCERTAIN":
                should_close = True
                reason = f"Position in UNCERTAIN regime"

            if should_close:
                self.logger.warning(f"[{symbol}] REGIME FLIP ENFORCEMENT: {reason}. Closing {qty_val}.")

                close_side = "SELL" if is_long else "BUY"
                price = decimal.Decimal("0")
                why_chain = ["regime_flip_enforcement", regime]
                rid = f"rf-{int(self._clock.now_sec())}"

                self._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(abs(qty_val))),
                    price=price,
                    why_chain=why_chain,
                    rid=rid,
                    reduce_only=True,
                )
        except Exception as e:
            self.logger.warning(f"[{symbol}] Error in _handle_regime_flip: {e}")
