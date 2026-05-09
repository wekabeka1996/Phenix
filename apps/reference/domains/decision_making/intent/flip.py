"""Flip orchestration for opposite-side opens and same-side pyramiding checks.

This helper owns the local flip gate used by DecisionMaking/StrategyGateway.
Its responsibilities are intentionally narrow:

- inspect current position state for the symbol;
- distinguish same-side add vs. true opposite-side flip;
- enforce per-strategy position_mode on same-side intents;
- optionally require stronger opposite signals via per-symbol hysteresis;
- emit the close-and-retry side effects for proven flips.

The actual position queries, trade-intent proposal, deferred-event emission, and
FSM access remain injected from the DecisionMaking facade so this module does
not silently invent alternative execution or retry behavior.
"""

import decimal
import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock

OPPOSITE_ENTRY_REQUIRES_EXPLICIT_FLIP_CONTRACT = (
    "OPPOSITE_ENTRY_REQUIRES_EXPLICIT_FLIP_CONTRACT"
)


class FlipOrchestrator:
    """
    Flip gate and close-orchestration helper for DecisionMaking.

    Return contract:
    - ``None`` means the current OPEN may continue downstream.
    - non-``None`` means the current OPEN must not proceed as-is.

    Some non-``None`` outcomes are pure gate decisions (for example
    ``ANTI_PYRAMIDING_BLOCK``), while flip-close outcomes also emit
    ``EVT:INTENT_DEFERRED`` before returning control to the caller.
    """

    def __init__(
        self,
        clock: "Clock",
        config: "AuroraConfig",
        fsm: Any,
        get_position_state: Callable[[str], str],
        get_portfolio_position_qty_signed: Callable[[str], tuple],
        get_flip_config: Callable[[str], tuple],
        propose_trade_intent: Callable,
        emit_intent_deferred_v1: Callable,
        logger: logging.Logger,
    ) -> None:
        self._clock = clock
        self.config = config
        self._fsm = fsm
        self._get_position_state = get_position_state
        self._get_portfolio_position_qty_signed = get_portfolio_position_qty_signed
        self._get_flip_config = get_flip_config
        self._propose_trade_intent = propose_trade_intent
        self._emit_intent_deferred_v1 = emit_intent_deferred_v1
        self.logger = logger

    # -- Utility ------------------------------------------------------------

    def is_flip(self, symbol: str, intent_side: str, position_state: str = None) -> bool:
        """Return ``True`` only for known opposite-side position vs intent pairs.

        ``UNKNOWN`` remains caller-managed fail-closed state; this helper only
        answers the narrower question of whether a non-flat known position is on
        the opposite side of the requested OPEN.
        """
        if not position_state:
            position_state = self._get_position_state(symbol)

        if position_state == "FLAT" or position_state == "UNKNOWN":
            return False

        intent_side = intent_side.upper()
        if position_state == "LONG" and intent_side == "SELL":
            return True
        if position_state == "SHORT" and intent_side == "BUY":
            return True

        return False

    def is_same_side_position(self, position_side: str | None, intent_side: str) -> bool:
        """Check if intent side is same as current position side (pyramiding)."""
        if not position_side:
            return False
        return position_side == intent_side

    def generate_flip_retry_key(self, symbol: str, side: str, seed: str | None = None) -> str:
        """Generate a correlation key shared by flip close and deferred retry.

        A caller-provided seed keeps the retry key stable across the close and
        deferred-open parts of the same flip transaction; ad hoc callers fall
        back to the current clock timestamp.
        """
        if seed:
            return f"flip:{symbol}:{side}:{seed}"
        ts_ms = self._clock.now_ms()
        return f"flip:{symbol}:{side}:{ts_ms}"

    def resolve_position_mode(self, *, symbol: str, source: str) -> str | None:
        """Resolve per-symbol position_mode for the emitting strategy.

        SSOT: strategies.<strategy_id>.assets.<SYMBOL>.position_mode

        Returns ``None`` on missing, invalid, or unreadable config so the caller
        can fail closed instead of silently defaulting to STRICT or DYNAMIC.
        """
        try:
            strategies = getattr(self.config, "strategies", None)
            strat_cfg = getattr(strategies, str(source),
                                None) if strategies is not None else None
            assets = getattr(strat_cfg, "assets",
                             None) if strat_cfg is not None else None
            asset_cfg = assets.get(symbol) if isinstance(
                assets, dict) else None
            mode_raw = getattr(asset_cfg, "position_mode",
                               None) if asset_cfg is not None else None
            if mode_raw is None:
                return None
            mode = str(mode_raw).upper()
            if mode in {"STRICT", "DYNAMIC"}:
                return mode
            return None
        except Exception:
            return None

    # -- Reduce-Only Close --------------------------------------------------

    def emit_reduce_only_close(
        self,
        symbol: str,
        reason: str,
        rid: str,
        *,
        strategy_id: str,
        strategy_trace: dict | None = None,
    ) -> bool:
        """Emit the canonical reduce-only close intent for a flip.

        The close direction and absolute quantity are derived from the current
        signed portfolio position. Fail-closed behavior is deliberate here:
        missing, unparsable, or effectively zero quantity means no close intent
        is emitted and the caller gets ``False``.

        IMPORTANT: the originating ``strategy_id`` must be preserved so the
        normal trade-intent/arbitration pipeline evaluates the close under the
        strategy that owns the position.
        """
        qty_signed, curr_pos = self._get_portfolio_position_qty_signed(symbol)
        if qty_signed is None:
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: CLOSE qty missing/invalid in portfolio; skip emit (pos={curr_pos})"
            )
            return False

        try:
            tol = decimal.Decimal("1e-9")
        except Exception:
            tol = decimal.Decimal(str(1e-9))

        if abs(qty_signed) < tol:
            return False

        close_side = "SELL" if qty_signed > 0 else "BUY"
        qty_abs = abs(qty_signed)
        if qty_abs <= 0:
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: CLOSE qty invalid/zero; skip emit (qty_signed={qty_signed})"
            )
            return False

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Emitting CLOSE {close_side} {qty_abs} (reduce_only)"
        )

        # Canonical flip-close path goes through the regular intent pipeline so
        # downstream bridge/execution logic sees an ordinary reduce-only intent.
        self._propose_trade_intent(
            symbol=symbol,
            side=close_side,
            qty=decimal.Decimal(str(qty_abs)),
            price=decimal.Decimal("0"),
            why_chain=["flip_orchestration_close", reason],
            rid=rid,
            reduce_only=True,
            strategy_id=str(strategy_id),
            strategy_trace=strategy_trace,
        )
        return True

    # -- Main Flip Orchestration --------------------------------------------

    def handle_flip_orchestration(
        self,
        symbol: str,
        intent_side: str,
        original_pld: Dict[str, Any],
        source: str = "aurora",
    ) -> Optional[str]:
        """
        Evaluate an OPEN against current position state and flip rules.

        Strict sequential contract:
        1. ``UNKNOWN`` -> fail closed for the caller.
        2. ``FLAT`` -> allow current OPEN.
        3. same-side position -> apply ``position_mode`` anti-pyramiding rules.
        4. opposite-side position -> optionally require hysteresis, then emit a
           reduce-only close and defer the new OPEN for retry.

        Return value is a reason string understood by the caller as "current
        OPEN did not proceed". For flip-close outcomes this method also emits a
        deferred retry envelope before returning.
        """
        # Flip config is mandatory SSOT for active instruments even if the final
        # branch turns out to be FLAT or a same-side block.
        flip_enabled, flip_mult = self._get_flip_config(symbol)

        pos_state = self._get_position_state(symbol)

        if pos_state == "UNKNOWN":
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: State UNKNOWN, fail-closed (NRR-PORTFOLIO-UNKNOWN)"
            )
            return "NRR-PORTFOLIO-UNKNOWN"

        if pos_state == "FLAT":
            self.logger.debug(
                f"[{symbol}] FLIP_ORCHESTRATION: FLAT, allowing OPEN {intent_side}")
            return None

        is_flip_detected = self.is_flip(symbol, intent_side, pos_state)

        if not is_flip_detected:
            position_mode = self.resolve_position_mode(
                symbol=symbol, source=source)
            if position_mode is None:
                self.logger.error(
                    f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - position_mode missing/invalid "
                    f"(expected strategies.{source}.assets.{symbol}.position_mode)"
                )
                return "CONFIG_POSITION_MODE_INVALID"
            if position_mode == "DYNAMIC":
                self.logger.info(
                    f"[{symbol}] FLIP_ORCHESTRATION: Same-side pyramiding allowed (position_mode=DYNAMIC)"
                )
                return None
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - Same-side pyramiding not allowed "
                f"(state={pos_state}, intent={intent_side})"
            )
            return "ANTI_PYRAMIDING_BLOCK"

        if not flip_enabled:
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - opposite-side OPEN requires explicit flip contract "
                f"(state={pos_state}, intent={intent_side}, flip_enabled={flip_enabled})"
            )
            return OPPOSITE_ENTRY_REQUIRES_EXPLICIT_FLIP_CONTRACT

        # Hysteresis only runs when the signal payload carries concrete score and
        # threshold evidence. Missing fields do not get synthetic defaults here.
        if flip_enabled and flip_mult > 1.0:
            try:
                score = float(original_pld.get("signal_score")) if original_pld.get(
                    "signal_score") is not None else None
                thr_buy = float(original_pld.get("thr_buy")) if original_pld.get(
                    "thr_buy") is not None else None
                thr_sell = float(original_pld.get("thr_sell")) if original_pld.get(
                    "thr_sell") is not None else None
            except Exception:
                score, thr_buy, thr_sell = None, None, None

            if score is not None and thr_buy is not None and thr_sell is not None:
                if str(intent_side).lower() == "buy":
                    required = thr_buy * flip_mult
                    if score < required:
                        self.logger.info(
                            f"[{symbol}] FLIP_ORCHESTRATION: HYSTERESIS_BLOCK (BUY) "
                            f"score={score:.4f} < required={required:.4f} (thr_buy={thr_buy:.4f}, mult={flip_mult})"
                        )
                        return "FLIP_HYSTERESIS_BLOCK"
                elif str(intent_side).lower() == "sell":
                    required = thr_sell * flip_mult
                    if score > -required:
                        self.logger.info(
                            f"[{symbol}] FLIP_ORCHESTRATION: HYSTERESIS_BLOCK (SELL) "
                            f"score={score:.4f} > -required={-required:.4f} (thr_sell={thr_sell:.4f}, mult={flip_mult})"
                        )
                        return "FLIP_HYSTERESIS_BLOCK"

        # Emit Reduce-Only Close
        rid = original_pld.get("rid") or f"flip-{int(self._clock.now_sec())}"
        close_emitted = self.emit_reduce_only_close(
            symbol,
            "flip_orchestration",
            f"{rid}-close",
            strategy_id=str(source),
        )

        # Schedule Retry (Defer Open)
        retry_key = self.generate_flip_retry_key(symbol, intent_side, seed=rid)
        now_ms = self._clock.now_ms()

        stale_ttl_sec = self.config.domains.position_tracking.positions_stale_ttl_sec
        if stale_ttl_sec is None:
            raise ValueError(
                "domains.position_tracking.positions_stale_ttl_sec is required (SSOT)")
        next_allowed_ts = now_ms + int(stale_ttl_sec * 1000)

        original_payload_min = dict(original_pld) if isinstance(
            original_pld, dict) else {}
        original_payload_min["symbol"] = symbol
        original_payload_min["side"] = intent_side
        original_payload_min["strategy_id"] = original_payload_min.get(
            "strategy_id") or source
        original_payload_min["rid"] = original_payload_min.get(
            "rid") or f"flip_{retry_key}"
        # Deferred signals re-enter StrategyGateway, which expects the v7
        # readiness contract to be present in payload_min.
        original_payload_min["readiness"] = {"warmup_ok": True}

        original_event = {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "payload_min": original_payload_min,
        }

        why_chain_raw = original_pld.get("why_chain")
        why_chain = why_chain_raw.copy() if isinstance(why_chain_raw, list) else []
        why_chain.extend(["opposite_position_exists"])
        if close_emitted:
            why_chain.append("flip_close_emitted")
        else:
            why_chain.append("flip_close_skipped_invalid_qty")

        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason="FLIP_CLOSE_PENDING" if close_emitted else "NRR-FLIP-CLOSE-QTY-INVALID",
            retry_key=retry_key,
            next_allowed_ts=next_allowed_ts,
            original_event_name=original_event["event_name"],
            original_payload_min=original_event["payload_min"],
            attempt=1,
            max_attempts=5,
            why_chain=why_chain,
            context=f"flip_orchestration_{source}",
        )

        return "FLIP_CLOSE_PENDING" if close_emitted else "NRR-FLIP-CLOSE-QTY-INVALID"

    # -- Initiate Flip Close ------------------------------------------------

    def initiate_flip_close(
        self,
        symbol: str,
        intent_side: str,
        original_pld: Dict[str, Any],
        source: str,
    ) -> str:
        """
        Compatibility helper that emits ``CMD:CLOSE`` then defers the OPEN.

        This is the command-oriented alternative to ``emit_reduce_only_close``.
        It asks the FSM to close immediately, then schedules the original OPEN
        for retry using the same stale-portfolio TTL contract as the canonical
        reduce-only path.

        Returns:
            ``FLIP_CLOSE_PENDING``. The current OPEN never continues inline.
        """
        retry_key = self.generate_flip_retry_key(
            symbol, intent_side, seed=original_pld.get("rid"))
        now_ms = self._clock.now_ms()

        stale_ttl_sec = self.config.domains.position_tracking.positions_stale_ttl_sec
        if stale_ttl_sec is None:
            raise ValueError(
                "domains.position_tracking.positions_stale_ttl_sec is required (SSOT)")
        next_allowed_ts = now_ms + int(stale_ttl_sec * 1000)

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Initiating flip - closing opposite position, "
            f"deferring {intent_side} OPEN (retry_key={retry_key})"
        )

        close_pld = {
            "symbol": symbol,
            "reason": "FLIP_CLOSE",
            "retry_key": retry_key,
            "rid": original_pld["rid"] if "rid" in original_pld else f"flip_close_{retry_key}",
        }

        self._fsm.emit("CMD:CLOSE", close_pld)

        original_payload_min = dict(original_pld) if isinstance(
            original_pld, dict) else {}
        original_payload_min["symbol"] = symbol
        original_payload_min["side"] = intent_side
        original_payload_min["strategy_id"] = original_payload_min.get(
            "strategy_id") or source
        original_payload_min["rid"] = original_payload_min.get(
            "rid") or f"flip_{retry_key}"
        # Deferred signals re-enter StrategyGateway, which expects the v7
        # readiness contract to be present in payload_min.
        original_payload_min["readiness"] = {"warmup_ok": True}

        original_event = {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "payload_min": original_payload_min,
        }

        why_chain_raw = original_pld.get("why_chain")
        why_chain = why_chain_raw.copy() if isinstance(why_chain_raw, list) else []
        why_chain.extend(["opposite_position_exists", "flip_close_emitted"])

        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason="FLIP_CLOSE_PENDING",
            retry_key=retry_key,
            next_allowed_ts=next_allowed_ts,
            original_event_name=original_event["event_name"],
            original_payload_min=original_event["payload_min"],
            attempt=1,
            max_attempts=5,
            why_chain=why_chain,
            context=f"flip_orchestration_{source}",
        )

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Emitted CMD:CLOSE + INTENT_DEFERRED "
            f"(next_allowed_ts={next_allowed_ts}, retry_key={retry_key})"
        )

        return "FLIP_CLOSE_PENDING"
