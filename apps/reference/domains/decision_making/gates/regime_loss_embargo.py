"""Decision-making-owned regime loss embargo policy core.

This module centralizes the regime loss embargo business logic:
- stable regime epoch minting/reset
- terminal close evaluation
- fail-closed unresolved-context blocking
- entry-block query/reject context construction
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class RegimeLossEmbargo:
    """Per-symbol embargo policy owned by decision_making."""

    STATE_KEY = "regime_loss_embargo"
    LOSS_LATCHED = "LOSS_LATCHED"
    CAUSAL_CONTEXT_UNPROVEN = "CAUSAL_CONTEXT_UNPROVEN"

    def __init__(
        self,
        *,
        config: Any,
        symbol_states: Dict[str, Dict[str, Any]],
        clock: Any,
        logger: Any,
    ) -> None:
        self._config = config
        self._symbol_states = symbol_states
        self._clock = clock
        self._logger = getattr(logger, "getChild", lambda _name: logger)(
            "regime_loss_embargo"
        )

    def _cfg(self) -> Any:
        return self._config.domains.decision_making.regime_loss_embargo

    def enabled(self) -> bool:
        try:
            return bool(self._cfg().enabled)
        except Exception:
            return False

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _new_state(self) -> Dict[str, Any]:
        return {
            "stable_regime_epoch_ref": None,
            "latched": False,
            "block_reason": None,
            "epoch_ref": None,
            "latched_ts_ms": None,
            "trigger_pnl_net": None,
            "trigger_close_reason": None,
        }

    def _state(self, symbol: str) -> Optional[Dict[str, Any]]:
        symbol_state = self._symbol_states.get(symbol)
        if not isinstance(symbol_state, dict):
            return None
        state = symbol_state.get(self.STATE_KEY)
        return state if isinstance(state, dict) else None

    def _ensure_state(self, symbol: str) -> Dict[str, Any]:
        symbol_state = self._symbol_states.setdefault(symbol, {})
        state = symbol_state.get(self.STATE_KEY)
        if not isinstance(state, dict):
            state = self._new_state()
            symbol_state[self.STATE_KEY] = state
        return state

    def _clear_block(self, state: Dict[str, Any]) -> None:
        state["latched"] = False
        state["block_reason"] = None
        state["epoch_ref"] = None
        state["latched_ts_ms"] = None
        state["trigger_pnl_net"] = None
        state["trigger_close_reason"] = None

    def _set_unproven(
        self,
        state: Dict[str, Any],
        *,
        epoch_ref: Optional[str],
        ts_ms: Optional[int],
    ) -> None:
        state["latched"] = True
        state["block_reason"] = self.CAUSAL_CONTEXT_UNPROVEN
        state["epoch_ref"] = epoch_ref
        state["latched_ts_ms"] = int(
            ts_ms) if ts_ms is not None else self._clock.now_ms()
        state["trigger_pnl_net"] = None
        state["trigger_close_reason"] = None

    def _set_loss_latched(
        self,
        state: Dict[str, Any],
        *,
        epoch_ref: str,
        ts_ms: Optional[int],
        realized_pnl_net: float,
        close_reason: Optional[str],
    ) -> None:
        state["latched"] = True
        state["block_reason"] = self.LOSS_LATCHED
        state["epoch_ref"] = epoch_ref
        state["latched_ts_ms"] = int(
            ts_ms) if ts_ms is not None else self._clock.now_ms()
        state["trigger_pnl_net"] = float(realized_pnl_net)
        state["trigger_close_reason"] = str(
            close_reason) if close_reason is not None else None

    def _is_fee_only_close(
        self,
        *,
        realized_pnl_net: float,
        realized_pnl: Optional[float],
        fees: Optional[float],
    ) -> bool:
        return (
            realized_pnl == 0.0
            and fees is not None
            and fees > 0.0
            and realized_pnl_net < 0.0
        )

    def get_current_epoch_ref(self, symbol: str) -> Optional[str]:
        if not self.enabled():
            return None
        state = self._state(symbol)
        if not state:
            return None
        value = state.get("stable_regime_epoch_ref")
        return str(value) if value else None

    def on_regime(
        self,
        *,
        symbol: str,
        changed: Any,
        bar_close_ts_ms: Optional[int],
        ts_ms: Optional[int],
    ) -> None:
        if not self.enabled():
            return
        state = self._ensure_state(symbol)
        current_epoch_ref = state.get("stable_regime_epoch_ref")
        if current_epoch_ref is not None and not bool(changed):
            return
        epoch_ts_ms = (
            int(bar_close_ts_ms)
            if bar_close_ts_ms is not None
            else int(ts_ms) if ts_ms is not None else self._clock.now_ms()
        )
        new_epoch_ref = f"stable_epoch:{symbol}:{epoch_ts_ms}"
        state["stable_regime_epoch_ref"] = new_epoch_ref
        self._clear_block(state)
        self._logger.info(
            "[%s] REGIME_LOSS_EMBARGO epoch=%s changed=%s",
            symbol,
            new_epoch_ref,
            bool(changed),
        )

    def on_position_closed(
        self,
        *,
        symbol: str,
        entry_regime_epoch_ref: Optional[str],
        close_ts_ms: Optional[int],
        realized_pnl_net: Any,
        realized_pnl: Any = None,
        fees: Any = None,
        close_reason: Optional[str],
    ) -> None:
        if not self.enabled():
            return
        state = self._ensure_state(symbol)
        current_epoch_ref = state.get("stable_regime_epoch_ref")
        pnl_net = self._optional_float(realized_pnl_net)
        if current_epoch_ref in (None, "") or entry_regime_epoch_ref in (None, "") or pnl_net is None:
            self._set_unproven(
                state,
                epoch_ref=str(
                    current_epoch_ref) if current_epoch_ref else None,
                ts_ms=close_ts_ms,
            )
            self._logger.warning(
                "[%s] REGIME_LOSS_EMBARGO unresolved_context current_epoch=%r entry_epoch=%r pnl=%r",
                symbol,
                current_epoch_ref,
                entry_regime_epoch_ref,
                realized_pnl_net,
            )
            return

        gross_pnl = self._optional_float(realized_pnl)
        fees_paid = self._optional_float(fees)
        if (
            str(self._cfg().fee_only_close_policy) == "ignore"
            and self._is_fee_only_close(
                realized_pnl_net=pnl_net,
                realized_pnl=gross_pnl,
                fees=fees_paid,
            )
        ):
            self._logger.info(
                "[%s] REGIME_LOSS_EMBARGO fee_only_ignored pnl_net=%s realized_pnl=%s fees=%s close_reason=%s",
                symbol,
                pnl_net,
                gross_pnl,
                fees_paid,
                close_reason,
            )
            return

        threshold = float(self._cfg().min_loss_threshold_net)
        if pnl_net < (-threshold) and str(entry_regime_epoch_ref) == str(current_epoch_ref):
            self._set_loss_latched(
                state,
                epoch_ref=str(current_epoch_ref),
                ts_ms=close_ts_ms,
                realized_pnl_net=pnl_net,
                close_reason=close_reason,
            )
            self._logger.info(
                "[%s] REGIME_LOSS_EMBARGO loss_latched epoch=%s pnl_net=%s close_reason=%s",
                symbol,
                current_epoch_ref,
                pnl_net,
                close_reason,
            )

    def get_entry_block(self, symbol: str) -> Dict[str, Any]:
        if not self.enabled():
            return {"blocked": False}
        state = self._state(symbol)
        if not state or state.get("stable_regime_epoch_ref") in (None, ""):
            state = self._ensure_state(symbol)
            self._set_unproven(
                state,
                epoch_ref=str(state.get("stable_regime_epoch_ref"))
                if state.get("stable_regime_epoch_ref")
                else None,
                ts_ms=self._clock.now_ms(),
            )
        if not state.get("latched"):
            return {"blocked": False}
        return {
            "blocked": True,
            "block_reason": state.get("block_reason"),
            "epoch_ref": state.get("epoch_ref"),
            "latched_ts_ms": state.get("latched_ts_ms"),
            "trigger_pnl_net": state.get("trigger_pnl_net"),
            "trigger_close_reason": state.get("trigger_close_reason"),
            "details": {
                "block_reason": state.get("block_reason"),
                "epoch_ref": state.get("epoch_ref"),
                "latched_ts_ms": state.get("latched_ts_ms"),
                "trigger_pnl_net": state.get("trigger_pnl_net"),
                "trigger_close_reason": state.get("trigger_close_reason"),
            },
        }


__all__ = ["RegimeLossEmbargo"]
