"""
FSMP-P1-T02: Manage Flow FSM for execution_position domain.

States: FLAT|OPENED  TRACKING  EMIT_DEC_ADJUST  TRACKING
Rules: per-instrument trailing_stop, max_hold_time, TP1/TP2 partial exit
Output: DEC:ADJUST(tpWARN, slWARN, move_to_beWARN)

Shadow-mode: decisions only, no live modifications.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from enum import Enum

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from typing import Callable, Dict, Any, Optional, Union

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.bracket_math import compute_bracket_targets
from apps.reference.domains.execution_position.contracts import TPSLValidationRules
from apps.reference.config_models import AuroraConfig, AuroraInstrumentConfig
from apps.reference.utils.accessors import aget, dget
from apps.reference.domains.execution_position.utils import (
    classify_client_order_id,
    generate_client_order_id,
    quantize_stop_price,
    coerce_exchange_bool,
)
from apps.reference.telemetry.shadow_journal import (
    get_shadow_journal,
    snapshot_manage_flow_state,
)

LOG = logging.getLogger(__name__)


try:
    from apps.reference.telemetry.metrics import inc_manage_skipped
except ImportError:

    def inc_manage_skipped() -> None:
        pass


class ManageState(str, Enum):
    """FSM states for manage flow."""

    FLAT = "FLAT"
    OPENED = "OPENED"
    TRACKING = "TRACKING"
    BRACKETS_PENDING = "BRACKETS_PENDING"
    BRACKETS_PLACED = "BRACKETS_PLACED"
    EMIT_DEC_ADJUST = "EMIT_DEC_ADJUST"
    ERROR = "ERROR"
    EMERGENCY = "EMERGENCY"
    WAIT_MODE = "WAIT_MODE"


class ManageFlowFSM:
    """
    Manage Flow FSM: tracks open positions and manages brackets/trailing stops.

    FAIL-CLOSED POLICY: No fallback to global config!
    All symbols MUST have explicit config in strategies.aurora.assets.<SYM>.
    Missing config  ValueError (system crash, not silent fallback).

    Rules execute on EVT:PARTIAL_FILL|FILL|UPD:*.
    """

    def __init__(
        self,
        config: Optional[AuroraConfig] = None,
    ):
        self.state = ManageState.FLAT

        # Position tracking
        # Phase 0: track symbol for per-instrument config
        self.symbol: Optional[str] = None
        self.position_qty: Optional[Decimal] = None
        self.position_entry_price: Optional[Decimal] = None
        self.position_open_ts: float = 0.0
        self.position_side: Optional[str] = None  # 'BUY' or 'SELL'
        self.entry_order_id: Optional[str] = None
        self.entry_client_order_id: Optional[str] = None

        # Bracket orders tracking
        self.sl_order_id: Optional[str] = None
        self.tp_order_id: Optional[str] = None
        self.tp1_order_id: Optional[str] = None
        self.tp2_order_id: Optional[str] = None
        # Binance algo child correlation: clientAlgoId from placement response
        # becomes the child order's clientOrderId in WS ORDER_TRADE_UPDATE fills.
        self.sl_algo_client_id: Optional[str] = None
        self.tp_algo_client_id: Optional[str] = None

        # Intent data (injected via set_intent_prices)
        self._intent_sl_price: Optional[Decimal] = None
        self._intent_tp_price: Optional[Decimal] = None

        self.sl_price: Optional[Decimal] = None
        self.tp_price: Optional[Decimal] = None  # TP1 price (primary)

        # Phase A2: TP1/TP2 partial exit support
        self.tp2_order_id: Optional[str] = None
        self.tp1_price: Optional[Decimal] = None
        self.tp2_price: Optional[Decimal] = None
        self.partial_exit_pct: Optional[float] = None  # e.g., 0.7 = 70% at TP1

        # Phase A3: Trailing stop tracking
        self.trailing_activated: bool = False
        self.last_trailing_ts: float = 0.0
        # High-water mark for trailing
        self.peak_price: Optional[Decimal] = None

        # PHASE A2: Anti-race flag - prevents bracket placement during CLOSE
        self._closing_position: bool = False
        self._closing_position_ts: float = 0.0

        if isinstance(config, dict):
            raise TypeError(
                "ManageFlowFSM requires typed AuroraConfig, got dict")
        if config is None:
            raise ValueError(
                f"CRITICAL: {self.__class__.__name__} requires valid AuroraConfig. "
                "Refusing to start with empty defaults."
            )
        self.config = config

        # Extract commonly used configs for easier access
        self._manage_cfg = self.config.trading.execution.manage if self.config.trading.execution else None

        # Emergency/WaitMode configuration - SSOT: trading.execution.manage.emergency
        self._bar_ms = 15 * 60 * 1000
        aurora = getattr(self.config.strategies, "aurora", None)
        if aurora is not None and aurora.decision.bar_gating:
            self._bar_ms = aurora.decision.bar_gating.bar_ms

        # FAIL-CLOSED: wait_mode_bars must come from config
        if self._manage_cfg and self._manage_cfg.emergency:
            emergency_cfg = self._manage_cfg.emergency
            self._wait_mode_bars = int(emergency_cfg.wait_mode_bars)
        else:
            # Emergency disabled - set default for disabled state
            self._wait_mode_bars = 2

        self._wait_mode_until_ts: int = 0

        # Anti-race window (ms)  SSOT: trading.execution.anti_race_close_ms (FAIL-CLOSED)
        if not (self.config.trading and self.config.trading.execution):
            raise ValueError(
                "trading.execution config is required for ManageFlowFSM. "
                "Check trading.yaml has trading.execution section."
            )
        cfg_val = getattr(self.config.trading.execution,
                          "anti_race_close_ms", None)
        if cfg_val is None:
            raise ValueError(
                "trading.execution.anti_race_close_ms is required. "
                "Check trading.yaml has anti_race_close_ms value."
            )
        self._anti_race_close_ms = int(cfg_val)

        # Auto-manage flag
        self._auto_manage_enabled = False
        if self._manage_cfg:
            self._auto_manage_enabled = self._manage_cfg.auto

        # Log configuration status
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"ManageFlowFSM initialized: auto_manage_enabled={self._auto_manage_enabled}")

        self._metrics: Dict[str, int] = {
            "fsm_adjust_decisions_total": 0,
            "fsm_bracket_orders_placed": 0,
            "fsm_trailing_adjustments": 0,
            "fsm_max_hold_timeouts": 0,
            "fsm_partial_exits_total": 0,
            "fsm_errors_total": 0,
        }
        self._observability_hook: Optional[Callable[[
            str, Dict[str, Any]], None]] = None
        self._shadow_journal: Optional[Any] = None

    def set_shadow_journal(self, journal: Any) -> None:
        self._shadow_journal = journal

    # =========================================================================
    # Phase 0: Per-Instrument Aurora Configuration Helpers
    # =========================================================================

    def _get_aurora_instr_cfg(self, symbol: Optional[str] = None) -> Optional[AuroraInstrumentConfig]:
        """
        Get per-instrument Aurora configuration for current or specified symbol.

        Fallback chain:
        1. self.symbol (from position tracking)
        2. Passed symbol argument
        3. Return None if no symbol available

        Supports both Pydantic config and legacy dict format for consistency
        with DecisionMaking._get_aurora_instrument_cfg().

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            AuroraInstrumentConfig or None if not configured
        """
        target_symbol = symbol or self.symbol
        if not target_symbol:
            return None

        if not self.config:
            return None

        aurora = getattr(self.config.strategies, "aurora", None)
        if aurora is None:
            return None

        return aurora.assets.get(target_symbol)

    def _get_exit_param(self, param: str, default: Any, symbol: Optional[str] = None) -> Any:
        """
        Get exit parameter from per-instrument config ONLY.

        FAIL-CLOSED: No fallback to global config. If not configured, returns None.
        Caller must handle None appropriately (usually by raising ValueError).

        Args:
            param: Parameter name (e.g., 'sl_pct', 'max_hold_sec')
            default: Default value if not found (DEPRECATED - should not be used)
            symbol: Optional symbol override

        Returns:
            Parameter value from per-instrument config or None
        """
        # FAIL-CLOSED: Only per-instrument config, no global fallback
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        if instr_cfg is not None and instr_cfg.exit is not None:
            try:
                value = getattr(instr_cfg.exit, param)
                if value is not None:
                    return value
            except AttributeError:
                pass

        # No fallback - return None and let caller decide (usually: crash)
        return None

    def _get_take_profit_params(
        self, symbol: Optional[str] = None
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Get TP1/TP2 parameters from per-instrument config.

        Returns (tp_low_ratio, tp_high_ratio, partial_exit_pct) for symbol.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            Tuple of (tp_low_ratio, tp_high_ratio, partial_exit_pct).
            Any value may be None if not configured.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        tp = aget(instr_cfg, "take_profit",
                  None) if instr_cfg is not None else None
        if tp is not None:
            return (
                aget(tp, "tp_low_ratio", None),
                aget(tp, "tp_high_ratio", None),
                aget(tp, "partial_exit_pct", None),
            )
        return None, None, None

    def set_intent_prices(self, sl_price: Union[str, float, Decimal], tp_price: Optional[Union[str, float, Decimal]] = None) -> None:
        """
        Inject specific TP/SL prices from TradeIntent (Strategy calculation).
        Called by ExecPosFSM before bracket placement.
        """
        try:
            if sl_price:
                self._intent_sl_price = Decimal(str(sl_price))
            if tp_price:
                self._intent_tp_price = Decimal(str(tp_price))
            LOG.info(
                f"SET_INTENT_PRICES: SL={self._intent_sl_price}, TP={self._intent_tp_price}")
        except Exception as e:
            LOG.error(f"Failed to set intent prices: {e}")

    def _get_trailing_stop_params(
        self, symbol: Optional[str] = None
    ) -> tuple[bool, Optional[float], Optional[float], int]:
        """
        Get trailing stop parameters from per-instrument config ONLY.

        FAIL-CLOSED: No fallback to global config. If not configured, returns disabled.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            Tuple of (enabled, activation_pct, trail_pct, min_update_interval_sec).
            Returns (False, None, None, 5) if not configured (trailing disabled).
        """
        # FAIL-CLOSED: Only per-instrument config
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        ts = aget(instr_cfg, "trailing_stop",
                  None) if instr_cfg is not None else None
        if ts is not None:
            return (
                bool(ts.enabled),
                aget(ts, "activation_pct", None),
                aget(ts, "trail_pct", None),
                int(aget(ts, "min_update_interval_sec", 5) or 5),
            )

        # No config = trailing disabled (fail-safe for optional feature)
        return False, None, None, 5

    def _get_max_hold_sec(self, symbol: Optional[str] = None) -> Optional[int]:
        """
        Get max hold time from per-instrument exit config.

        Phase A4: Returns max_hold_sec for forced position exit.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            max_hold_sec or None if not configured.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        exit_cfg = aget(instr_cfg, "exit",
                        None) if instr_cfg is not None else None
        if exit_cfg is not None:
            return aget(exit_cfg, "max_hold_sec", None)
        return None

    def _check_max_hold_time(self, msg: Message, elapsed_sec: float) -> Optional[Message]:
        """
        Check if position exceeded max hold time and should be closed.

        Phase A4: Per-instrument max_hold_sec watchdog.
        Forces market close when position held too long.

        Args:
            msg: Current message for context
            elapsed_sec: Seconds since position open

        Returns:
            DEC:CLOSE message if timeout, None otherwise.
        """
        max_hold_sec = self._get_max_hold_sec(self.symbol)
        if max_hold_sec is None:
            return None

        if elapsed_sec >= max_hold_sec:
            self._metrics["fsm_max_hold_timeouts"] = int(
                self._metrics["fsm_max_hold_timeouts"]) + 1
            msg_pld = msg.pld or {}

            # Emit close message (canonical verb used by ExecPosFSM + drift monitor)
            return Message(
                op="DEC",
                verb="CLOSE",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                why=f"max_hold_timeout_{int(elapsed_sec)}s_reduce_only",
                pld={
                    "symbol": self.symbol or (msg_pld["symbol"] if "symbol" in msg_pld else ""),
                    "side": self._get_opposite_side(),
                    "qty": str(self.position_qty),
                    "reduce_only": True,
                    "reason": "MAX_HOLD_TIME_EXCEEDED",
                    "elapsed_sec": elapsed_sec,
                    "max_hold_sec": max_hold_sec,
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else [],
            )

        return None

    def set_bracket_ids(
        self,
        sl_order_id: Optional[str],
        tp_order_id: Optional[str],
        sl_algo_client_id: Optional[str] = None,
        tp_algo_client_id: Optional[str] = None,
    ) -> None:
        """
        Directly set bracket IDs from ExecPosFSM after placement.

        This ensures ManageFlowFSM has accurate bracket tracking for OCO emulation,
        even if ORDER_UPDATED WebSocket events are delayed or missed.

        Args:
            sl_order_id: Stop-loss order ID from exchange (algoId normalized to orderId)
            tp_order_id: Take-profit order ID from exchange (algoId normalized to orderId)
            sl_algo_client_id: Binance clientAlgoId for SL (becomes child clientOrderId in WS fills)
            tp_algo_client_id: Binance clientAlgoId for TP (becomes child clientOrderId in WS fills)
        """
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        self.sl_algo_client_id = sl_algo_client_id
        self.tp_algo_client_id = tp_algo_client_id
        # Log synchronization for debugging
        LOG.debug(
            "Synced bracket IDs: SL=%s (algo_cid=%s), TP=%s (algo_cid=%s)",
            sl_order_id, sl_algo_client_id, tp_order_id, tp_algo_client_id,
        )

    def has_active_lifecycle(self) -> bool:
        """Return True when local execution state still owns a lifecycle for the symbol.

        Contract:
        - state != FLAT is authoritative: always True.
        - _closing_position flag: always True (mid-close race condition guard).
        - position_qty: direct evidence of an open position.
        - Bracket IDs (sl_order_id, tp_order_id, etc.) are only counted as active
          lifecycle evidence when accompanied by entry-side evidence (entry_order_id
          or position_entry_price). Bracket-only metadata injected by health-check
          paths on a FLAT FSM is NOT sufficient to constitute an active lifecycle.
        """
        if self.state != ManageState.FLAT:
            return True
        if self._closing_position:
            return True
        if self.position_qty not in (None, Decimal("0")):
            return True
        # Entry-side evidence is independently sufficient to constitute an active lifecycle.
        # Health-check brackets placed while FLAT are NOT sufficient without entry evidence.
        # This separation prevents bracket-only IDs from blocking new valid open intents.
        has_entry_evidence = bool(
            self.position_entry_price
            or self.entry_order_id
            or self.entry_client_order_id
        )
        if has_entry_evidence:
            return True
        # Bracket IDs (sl/tp) without any entry evidence = health-check artifact, not lifecycle.
        return False

    def _client_order_id_from_payload(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("clientOrderId") or payload.get("client_order_id") or "")

    def set_observability_hook(
        self,
        hook: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> None:
        self._observability_hook = hook

    def _emit_observability(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._observability_hook is None:
            return
        try:
            self._observability_hook(topic, payload)
        except Exception as exc:
            LOG.debug(
                "ManageFlowFSM observability emit failed for %s: %s", topic, exc)

    def _now_ms(self) -> int:
        return int(get_clock().now_sec() * 1000)

    def _clear_lifecycle_tracking(self, *, reason: str, clear_symbol: bool) -> None:
        LOG.info(
            "[ManageFlowFSM] clearing lifecycle tracking reason=%s symbol=%s state=%s",
            reason,
            self.symbol,
            self.state.value,
        )
        if clear_symbol:
            self.symbol = None
        self.position_qty = None
        self.position_entry_price = None
        self.position_open_ts = 0.0
        self.position_side = None
        self.entry_order_id = None
        self.entry_client_order_id = None
        self.sl_order_id = None
        self.tp_order_id = None
        self.tp1_order_id = None
        self.tp2_order_id = None
        self.sl_algo_client_id = None
        self.tp_algo_client_id = None
        self._intent_sl_price = None
        self._intent_tp_price = None
        self.sl_price = None
        self.tp_price = None
        self.tp1_price = None
        self.tp2_price = None
        self.partial_exit_pct = None
        self.trailing_activated = False
        self.last_trailing_ts = 0.0
        self.peak_price = None
        self._closing_position = False
        self._closing_position_ts = 0.0

    def _normalize_client_order_id(self, client_order_id: str) -> str:
        return str(client_order_id or "").strip().upper()

    def _is_exit_fill_payload(self, payload: Dict[str, Any]) -> bool:
        order_type = str(
            payload.get("order_type") or (
                payload["type"] if "type" in payload else "")
        ).strip().upper()
        bracket_role = str(
            payload.get("bracket_role") or payload.get("close_reason") or ""
        ).strip().upper()
        close_position = (
            coerce_exchange_bool(payload.get("closePosition"))
            or coerce_exchange_bool(payload.get("cp"))
        )
        is_reduce_only = coerce_exchange_bool(payload.get("reduceOnly"))
        return bool(
            order_type in ["TAKE_PROFIT_MARKET", "STOP_MARKET"]
            or bracket_role in {"SL", "TP", "TP1", "TP2"}
            or close_position
            or is_reduce_only
        )

    def _matches_tracked_entry(self, order_id: Optional[str], client_order_id: str) -> bool:
        return bool(
            (order_id and self.entry_order_id and str(
                order_id) == str(self.entry_order_id))
            or (client_order_id and self.entry_client_order_id and client_order_id == str(self.entry_client_order_id))
        )

    def _matches_tracked_bracket(
        self,
        order_id: Optional[str],
        client_order_id: str,
    ) -> bool:
        return any(
            self._matches_order_identity(
                order_id, client_order_id, tracked_id, prefix)
            for tracked_id, prefix in (
                (self.sl_order_id, "SL-"),
                (self.tp1_order_id, "TP1-"),
                (self.tp2_order_id, "TP2-"),
                (self.tp_order_id, "TP-"),
            )
        )

    def _matches_order_identity(
        self,
        order_id: Optional[str],
        client_order_id: str,
        tracked_id: Optional[str],
        prefix: str,
    ) -> bool:
        matched, _ = self._match_order_identity_detail(
            order_id,
            client_order_id,
            tracked_id,
            prefix,
        )
        return matched

    def _match_order_identity_detail(
        self,
        order_id: Optional[str],
        client_order_id: str,
        tracked_id: Optional[str],
        prefix: str,
    ) -> tuple[bool, str]:
        client_upper = self._normalize_client_order_id(client_order_id)
        tracked = str(tracked_id or "")
        if order_id and tracked and str(order_id) == tracked:
            return True, "exchange_order_id_exact"
        if tracked and client_order_id == tracked:
            return True, "client_order_id_exact"
        if client_upper.startswith(prefix):
            return True, "client_order_id_prefix"
        return False, "no_match"

    def _local_expected_ids_snapshot(self) -> Dict[str, Optional[str]]:
        return {
            "entry_order_id": self.entry_order_id,
            "entry_client_order_id": self.entry_client_order_id,
            "sl_order_id": self.sl_order_id,
            "tp_order_id": self.tp_order_id,
            "tp1_order_id": self.tp1_order_id,
            "tp2_order_id": self.tp2_order_id,
        }

    def _resolve_bracket_match(
        self,
        order_id: Optional[str],
        client_order_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, bool, str]:
        for role, tracked_id, prefix in (
            ("SL", self.sl_order_id, "SL-"),
            ("TP1", self.tp1_order_id, "TP1-"),
            ("TP2", self.tp2_order_id, "TP2-"),
            ("TP", self.tp_order_id, "TP-"),
        ):
            matched, basis = self._match_order_identity_detail(
                order_id,
                client_order_id,
                tracked_id,
                prefix,
            )
            if matched:
                return role, True, f"matched_{role.lower()}_{basis}"

        # Algo child correlation: when Binance triggers an algo order, the child
        # order's clientOrderId equals the parent's clientAlgoId. Match against
        # the stored algo client IDs from bracket placement responses.
        if client_order_id:
            for role, algo_cid in (
                ("SL", getattr(self, "sl_algo_client_id", None)),
                ("TP", getattr(self, "tp_algo_client_id", None)),
            ):
                if algo_cid and str(client_order_id) == str(algo_cid):
                    return role, True, f"matched_{role.lower()}_algo_client_id"

        explicit_tracked_id = str(
            (payload or {}).get("tracked_bracket_order_id") or ""
        ).strip()
        explicit_role = str((payload or {}).get(
            "bracket_role") or "").strip().upper()
        if explicit_tracked_id:
            for role, tracked_id in (
                ("SL", self.sl_order_id),
                ("TP1", self.tp1_order_id),
                ("TP2", self.tp2_order_id),
                ("TP", self.tp_order_id),
            ):
                if not tracked_id or str(tracked_id) != explicit_tracked_id:
                    continue
                if explicit_role and explicit_role not in {role, "TP"}:
                    continue
                if explicit_role == "TP" and not role.startswith("TP"):
                    continue
                return role, True, f"matched_{role.lower()}_tracked_bracket_hint"
        return "UNKNOWN", False, "no_tracked_bracket_match"

    def _emit_guard_blocked_event(self, msg: Message, reason: str) -> None:
        payload = {
            "ts_ms": self._now_ms(),
            "symbol": (msg.pld or {}).get("symbol") or self.symbol,
            "rid": msg.rid,
            "block_reason": reason,
            "reason": reason,
            "current_local_state": self.state.value,
            "local_manage_state": self.state.value,
            "why": f"execution:{reason}",
        }
        self._emit_observability("EVT:EXECUTION_GUARD_BLOCKED", payload)

    def _emit_exit_match_observability(
        self,
        msg: Message,
        *,
        order_id: Optional[str],
        client_order_id: str,
        inferred_role: str,
        matched: bool,
        match_reason: str,
        local_expected_ids: Dict[str, Optional[str]],
        local_state_before: str,
        local_state_after: str,
        position_qty_before: Optional[Decimal],
    ) -> None:
        payload = {
            "ts_ms": self._now_ms(),
            "symbol": (msg.pld or {}).get("symbol") or self.symbol,
            "rid": msg.rid,
            "event_type": msg.verb,
            "incoming_order_id": order_id,
            "incoming_client_order_id": client_order_id,
            "normalized_client_order_id": self._normalize_client_order_id(client_order_id),
            "inferred_role": inferred_role,
            "local_expected_ids": local_expected_ids,
            "local_expected_ids_after": self._local_expected_ids_snapshot(),
            "matched": matched,
            "match_reason": match_reason,
            "local_state_before": local_state_before,
            "local_state_after": local_state_after,
            "position_qty_before": str(position_qty_before) if position_qty_before is not None else None,
            "position_qty_after": str(self.position_qty) if self.position_qty is not None else None,
            "why": "execution:exit_match_attempted",
        }
        self._emit_observability("EVT:EXIT_MATCH_ATTEMPTED", payload)
        if not matched:
            fail_payload = {
                "ts_ms": payload["ts_ms"],
                "symbol": payload["symbol"],
                "rid": payload["rid"],
                "event_type": msg.verb,
                "incoming_order_id": order_id,
                "incoming_client_order_id": client_order_id,
                "normalized_client_order_id": payload["normalized_client_order_id"],
                "inferred_role": inferred_role,
                "local_expected_ids": local_expected_ids,
                "local_state_before": local_state_before,
                "local_state_after": local_state_after,
                "mismatch_reason": match_reason,
                "why": "execution:exit_match_failed",
            }
            self._emit_observability("EVT:EXIT_MATCH_FAILED", fail_payload)

    def _emit_manage_guard_fail(self, msg: Message, reason: str) -> Message:
        return Message(
            op="ERR",
            verb=msg.verb,
            src="execution_position",
            dst=msg.src,
            rid=msg.rid,
            why="MANAGE_GUARD_FAIL",
            pld={
                "symbol": (msg.pld or {}).get("symbol"),
                "reason": reason,
                "block_reason": reason,
                "current_local_state": self.state.value,
                "local_manage_state": self.state.value,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],
        )

    def _should_route_pending_fill_to_check_rules(self, msg: Message) -> bool:
        """Route only deferred-path exit-like fills through the bracket handler.

        BRACKETS_PENDING is intentionally narrow: we do not open the full rule path
        for generic pending-state traffic. The only additional routing we allow here
        is for fills that are already identifiable as bracket/exit lifecycle events.
        """
        if self.state != ManageState.BRACKETS_PENDING:
            return False
        if msg.verb not in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
            return False

        pld = msg.pld or {}
        order_id = pld.get("orderId")
        client_order_id = self._client_order_id_from_payload(pld)
        return self._is_exit_fill_payload(pld) or self._matches_tracked_bracket(
            order_id,
            client_order_id,
        )

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:ADJUST if rules trigger.

        Args:
            msg: EVT:PARTIAL_FILL|FILL|UPD:* with payload: symbol, qty, price, etc.

        Returns:
            DEC:ADJUST if rules trigger, None otherwise.
        """
        journal = get_shadow_journal(self)
        before = snapshot_manage_flow_state(
            self) if journal is not None else None
        result: Optional[Message] = None
        try:
            if not self._auto_manage_enabled:
                inc_manage_skipped()
                pld_symbol = msg.pld.get("symbol") if isinstance(
                    msg.pld, dict) else None
                result = Message(
                    op="EVT",
                    verb="MANAGE_SKIPPED",
                    src="execution_position",
                    dst="any",
                    rid=aget(msg, "rid", None) or "",
                    why="manage_disabled",
                    pld={
                        "symbol": pld_symbol,
                        "reason": "auto_manage_disabled",
                    },
                    data_ref=msg.data_ref.copy() if msg.data_ref else [],
                )
                return result

            if msg.op not in ("EVT", "UPD"):
                return None

            try:
                pld = msg.pld or {}
                ts_value = pld.get("ts") if isinstance(pld, dict) else None
                now_ts = int(ts_value) if ts_value else get_clock().now_ms()
            except (ValueError, TypeError, AttributeError) as e:
                LOG.debug(f"Failed to parse timestamp from message: {e}")
                now_ts = get_clock().now_ms()

            if self.state == ManageState.WAIT_MODE:
                if now_ts < self._wait_mode_until_ts:
                    pld_symbol = msg.pld.get("symbol") if isinstance(
                        msg.pld, dict) else None
                    result = Message(
                        op="EVT",
                        verb="MANAGE_SKIPPED",
                        src="execution_position",
                        dst="any",
                        rid=aget(msg, "rid", None) or "",
                        why="wait_mode_active",
                        pld={"symbol": pld_symbol, "reason": "wait_mode"},
                        data_ref=msg.data_ref.copy() if msg.data_ref else [],
                    )
                    return result
                self.state = ManageState.TRACKING

            if self.state == ManageState.FLAT and msg.verb in (
                "PARTIAL_FILL",
                "FILL",
                "TRADE_EXECUTED",
            ):
                pld = msg.pld or {}
                order_type = pld.get("order_type") or (
                    pld["type"] if "type" in pld else "")
                close_position = (
                    coerce_exchange_bool(pld.get("closePosition"))
                    or coerce_exchange_bool(pld.get("cp"))
                )
                is_reduce_only = coerce_exchange_bool(pld.get("reduceOnly"))

                LOG.debug(
                    f"FILL event in FLAT: verb={msg.verb}, "
                    f"type={order_type}, closePos={close_position}, reduceOnly={is_reduce_only}, "
                    f"pld_keys={list(pld.keys())}"
                )

                is_exit_order = self._is_exit_fill_payload(pld)

                if is_exit_order:
                    LOG.info(
                        f"EXIT fill detected ({order_type}), position closing, NOT placing brackets")
                    self._clear_lifecycle_tracking(
                        reason="flat_exit_fill",
                        clear_symbol=True,
                    )
                    self.state = ManageState.FLAT
                    return None

                if self._closing_position:
                    self._closing_position = False
                    LOG.info("[BRK] ENTRY detected  closing_flag=False")

                LOG.info(f"ENTRY fill - creating position from {msg.verb}")
                self._on_fill(msg)
                self.state = ManageState.BRACKETS_PENDING
                LOG.info(f"Position opened, placing brackets on {msg.verb}")
                result = self._place_brackets(msg)
                return result

            if self.state in (
                ManageState.OPENED,
                ManageState.TRACKING,
                ManageState.BRACKETS_PENDING,
                ManageState.BRACKETS_PLACED,
                ManageState.EMIT_DEC_ADJUST,
                ManageState.ERROR,
                ManageState.EMERGENCY,
            ) and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
                pld = msg.pld or {}
                order_id = pld.get("orderId")
                client_order_id = self._client_order_id_from_payload(pld)
                if (
                    (order_id or client_order_id)
                    and
                    not self._is_exit_fill_payload(pld)
                    and not self._matches_tracked_entry(order_id, client_order_id)
                    and not self._matches_tracked_bracket(order_id, client_order_id)
                ):
                    LOG.error(
                        "[ManageFlowFSM] blocking entry-like fill over active lifecycle: "
                        f"state={self.state.value} symbol={pld.get('symbol')} order_id={order_id}"
                    )
                    self._emit_guard_blocked_event(
                        msg,
                        "stale_local_lifecycle_conflict",
                    )
                    result = self._emit_manage_guard_fail(
                        msg,
                        "stale_local_lifecycle_conflict",
                    )
                    return result

            if self.state == ManageState.BRACKETS_PENDING and msg.verb == "ORDER_UPDATED":
                result = self._on_bracket_placed(msg)
                return result

            if self._should_route_pending_fill_to_check_rules(msg):
                result = self._check_rules(msg)
                return result

            if self.state in (ManageState.TRACKING, ManageState.BRACKETS_PLACED):
                result = self._check_rules(msg)
                return result

            return None
        finally:
            if journal is not None:
                after = snapshot_manage_flow_state(self)
                if result is not None:
                    # OUTPUT record: authoritative state-change record
                    journal.record_transition(
                        event_name=f"{result.op}:{result.verb}",
                        source_component="execution_position.fsm_manage",
                        source_path="execution:manage_flow_output",
                        event_origin_type="execution",
                        truth_owner="ManageFlowFSM",
                        payload=result.pld or {},
                        rid=getattr(result, "rid", None) or getattr(
                            msg, "rid", None),
                        before=before,
                        after=after,
                        notes=[f"input={msg.op}:{msg.verb}"],
                    )
                # INPUT record: triggering event context only (no transition window)
                notes = ["record_role=input"]
                if result is not None:
                    notes.append(f"result={result.op}:{result.verb}")
                journal.record_transition(
                    event_name=f"{msg.op}:{msg.verb}",
                    source_component="execution_position.fsm_manage",
                    source_path="execution:manage_flow_input",
                    event_origin_type="execution",
                    truth_owner="ManageFlowFSM",
                    payload=msg.pld or {},
                    rid=getattr(msg, "rid", None),
                    before=None,
                    after=None,
                    notes=notes,
                )

    def _on_fill(self, msg: Message):
        """Update position state on fill event."""
        try:
            pld = msg.pld or {}
            qty = Decimal(str(pld["qty"] if "qty" in pld else 0))
            price = Decimal(str(pld["price"] if "price" in pld else 0))
            side = pld.get("side")  # BUY or SELL
            # Phase 0: extract symbol from fill event
            symbol = pld.get("symbol")
            order_id = pld.get("orderId")
            client_order_id = self._client_order_id_from_payload(pld)

            if self.position_qty is None:
                self.position_qty = qty
                self.position_entry_price = price
                self.position_side = side
                self.symbol = symbol  # Phase 0: track symbol for per-instrument config
                self.position_open_ts = get_clock().now_sec()
                self.entry_order_id = str(order_id) if order_id else None
                self.entry_client_order_id = client_order_id or None
            else:
                # Average down (stub logic)
                total_qty = self.position_qty + qty
                entry_price = (
                    self.position_entry_price
                    if self.position_entry_price is not None
                    else Decimal("0")
                )
                avg_price = (self.position_qty * entry_price +
                             qty * price) / total_qty
                self.position_qty = total_qty
                self.position_entry_price = avg_price
                # Keep original side for position
                if self.entry_order_id is None and order_id:
                    self.entry_order_id = str(order_id)
                if self.entry_client_order_id is None and client_order_id:
                    self.entry_client_order_id = client_order_id

        except (ValueError, TypeError, KeyError) as e:
            LOG.warning(f"Failed to process fill event: {e}")
            self._metrics["fsm_errors_total"] += 1

    def _place_brackets(self, msg: Message) -> Optional[Message]:
        """Place SL and TP bracket orders after position opens."""

        # PHASE A2: Anti-race check - skip if position is closing
        if self._closing_position:
            elapsed_s = get_clock().now_sec() - self._closing_position_ts
            # configurable anti-race window
            if elapsed_s < (self._anti_race_close_ms / 1000.0):
                # Position close still in progress, skip bracket placement
                LOG.info(
                    f"[BRK] skip:closing_flag elapsed={elapsed_s:.3f}s (<{self._anti_race_close_ms/1000.0:.1f}s)")
                self.state = ManageState.TRACKING
                return None
            else:
                # Timeout: assume close finished, clear flag
                self._closing_position = False
                LOG.info(
                    f"[BRK] clearing closing_flag after {elapsed_s:.3f}s")

        # HOTFIX: PHASE A1 - Dedup check + clear phantom IDs
        # Note: Full REST dedup (openOrders check) should be done at async level (fsm.py)
        # Here we do local dedup: if IDs are set but we're in FLAT->ENTRY transition,
        # clear them (they're phantoms from previous trade)
        # DO THIS BEFORE _should_place_brackets() check so IDs are always cleared

        if self.sl_order_id or self.tp_order_id or self.tp1_order_id or self.tp2_order_id:
            # Local IDs present - likely phantoms if we're placing new brackets
            LOG.info(
                f"[BRK] local bracket IDs present (SL={self.sl_order_id}, TP={self.tp_order_id}, "
                f"TP1={self.tp1_order_id}, TP2={self.tp2_order_id})  clearing phantoms")
            self.sl_order_id = None
            self.tp_order_id = None
            self.tp1_order_id = None
            self.tp2_order_id = None
            self.sl_algo_client_id = None
            self.tp_algo_client_id = None

        if not self._should_place_brackets():
            self.state = ManageState.TRACKING
            return None

        try:
            # Calculate bracket prices (Phase A2: returns sl, tp1, tp2)
            sl_price, tp1_price, tp2_price = self._calculate_bracket_prices()
            if sl_price is None or tp1_price is None:
                self.state = ManageState.TRACKING
                return None

            self.sl_price = sl_price
            self.tp1_price = tp1_price
            self.tp2_price = tp2_price
            self.tp_price = tp1_price  # Backward compat: legacy single TP = TP1

            # === VALIDATION PHASE: Check SL/TP prices before submission ===
            # Get current mark price (use entry price as proxy if not available)
            current_mark = self.position_entry_price
            if current_mark is None:
                self.state = ManageState.TRACKING
                return None

            # Convert BUY/SELL to LONG/SHORT for validation
            validation_side = "LONG" if self.position_side == "BUY" else "SHORT" if self.position_side == "SELL" else self.position_side or "LONG"

            # Validate SL price
            is_sl_valid, sl_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=sl_price,
                is_take_profit=False,
            )
            if not is_sl_valid:
                cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                self._metrics["fsm_bracket_validation_failed"] = cur + 1
                self.state = ManageState.TRACKING
                return None

            # Validate TP1 price
            is_tp1_valid, tp1_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=tp1_price,
                is_take_profit=True,
            )
            if not is_tp1_valid:
                cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                self._metrics["fsm_bracket_validation_failed"] = cur + 1
                self.state = ManageState.TRACKING
                return None

            # Validate TP2 price if present
            if tp2_price is not None:
                is_tp2_valid, tp2_reason = TPSLValidationRules.validate_stop_price_for_side(
                    position_side=validation_side,
                    current_mark=current_mark,
                    stop_price=tp2_price,
                    is_take_profit=True,
                )
                if not is_tp2_valid:
                    cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                    self._metrics["fsm_bracket_validation_failed"] = cur + 1
                    self.state = ManageState.TRACKING
                    return None

            # === SAFETY OFFSET PHASE: Apply offset to avoid -2021 errors ===
            # Read offset_bps from config (FAIL-CLOSED: no default)
            if not self._manage_cfg or not self._manage_cfg.brackets:
                raise ValueError(
                    "trading.execution.manage.brackets is required for bracket safety offset (offset_bps). "
                    "No fallback/default is allowed."
                )
            offset_bps = self._manage_cfg.brackets.offset_bps

            # CFG-INSTRUMENTS-STEP-03-EXECUTION-PRECISION:
            # Get tick_size from canonical config.instruments
            symbol = msg.pld.get("symbol") or self.symbol
            if not symbol:
                raise ValueError(
                    "symbol is required to compute TP/SL safety offsets (tick_size lookup). "
                    "No fallback/default is allowed."
                )
            if not getattr(self.config, "instruments", None) or symbol not in self.config.instruments:
                raise ValueError(
                    f"instruments.{symbol}.tick_size is required for bracket price quantization/offsets. "
                    "No fallback/default is allowed."
                )
            tick_size = self.config.instruments[symbol].tick_size

            # Apply offset to SL (move it AWAY from entry to be safer)
            sl_offset = TPSLValidationRules.add_safety_offset(
                sl_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                sl_price = sl_price - sl_offset
            else:
                sl_price = sl_price + sl_offset

            # Apply offset to TP1 (move it AWAY from entry to be safer)
            tp1_offset = TPSLValidationRules.add_safety_offset(
                tp1_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                tp1_price = tp1_price + tp1_offset
            else:
                tp1_price = tp1_price - tp1_offset

            # Apply offset to TP2 if present
            if tp2_price is not None:
                tp2_offset = TPSLValidationRules.add_safety_offset(
                    tp2_price, tick_size, offset_bps)
                if self.position_side == "BUY":
                    tp2_price = tp2_price + tp2_offset
                else:
                    tp2_price = tp2_price - tp2_offset

            # Update stored prices
            self.sl_price = sl_price
            self.tp1_price = tp1_price
            self.tp2_price = tp2_price
            self.tp_price = tp1_price  # Backward compat
            cur = self._metrics["fsm_bracket_offset_applied"] if "fsm_bracket_offset_applied" in self._metrics else 0
            self._metrics["fsm_bracket_offset_applied"] = cur + 1

            # === QUANTITY CALCULATION: TP1 partial, TP2 remainder ===
            total_qty = self.position_qty
            if tp2_price is not None and self.partial_exit_pct is not None:
                # Phase A2: Split qty between TP1 (partial) and TP2 (remainder)
                partial_pct = Decimal(str(self.partial_exit_pct))
                tp1_qty = (
                    total_qty * partial_pct).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
                tp2_qty = total_qty - tp1_qty
            else:
                # Single TP mode: all qty on TP1
                tp1_qty = total_qty
                tp2_qty = Decimal("0")

            # Generate unique client order IDs  FIX-4015: use hash-based IDs (32 chars)
            idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = generate_client_order_id(
                "SL", symbol, idempotent_key=idem_base)
            tp1_client_id = generate_client_order_id(
                "TP1", symbol, idempotent_key=idem_base)
            tp2_client_id = generate_client_order_id(
                "TP2", symbol, idempotent_key=idem_base)

            # === EMISSION PHASE: Place validated bracket orders ===
            orders = []

            # Emit SL order (full qty)
            sl_order = self._emit_place_order(
                msg,
                sl_client_id,
                "STOP_MARKET",
                self._get_opposite_side(),
                str(total_qty),
                str(sl_price),
                "SL bracket",
            )
            orders.append(sl_order.model_dump())

            # Emit TP1 order
            tp1_order = self._emit_place_order(
                msg,
                tp1_client_id,
                "TAKE_PROFIT_MARKET",
                self._get_opposite_side(),
                str(tp1_qty),
                str(tp1_price),
                "TP1 bracket (partial)" if tp2_price else "TP bracket",
            )
            orders.append(tp1_order.model_dump())
            self.tp1_order_id = tp1_client_id

            # Emit TP2 order if configured
            if tp2_price is not None and tp2_qty > Decimal("0"):
                tp2_order = self._emit_place_order(
                    msg,
                    tp2_client_id,
                    "TAKE_PROFIT_MARKET",
                    self._get_opposite_side(),
                    str(tp2_qty),
                    str(tp2_price),
                    "TP2 bracket (remainder)",
                )
                orders.append(tp2_order.model_dump())
                self.tp2_order_id = tp2_client_id
                self._metrics["fsm_bracket_orders_placed"] += 3
            else:
                self._metrics["fsm_bracket_orders_placed"] += 2

            # Backward compat: set legacy tp_order_id to TP1
            self.tp_order_id = tp1_client_id

            # Return BATCH message with all orders
            return Message(
                op="DEC",
                verb="BATCH",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                why="place_brackets_batch",
                pld={
                    "messages": orders
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else []
            )

        except (ValueError, TypeError, KeyError) as e:
            LOG.warning(f"Failed to place brackets: {e}")
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        if self._manage_cfg and self._manage_cfg.brackets:
            return self._manage_cfg.brackets.enable
        return False

    def _calculate_bracket_prices(
        self
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Calculate SL, TP1, TP2 prices for current position.

        FAIL-CLOSED POLICY: No fallback! All symbols MUST have explicit config.
        Returns (sl_price, tp1_price, tp2_price).
        TP2 may be None if not configured (single TP mode).

        Priority chain:
        1. Intent Injection: self._intent_sl_price (from Strategy calculation)
        2. Config Lookup: strategies.aurora.assets.<SYMBOL>.exit.sl_pct (REQUIRED)
        3. TP: self._intent_tp_price or strategies.aurora.assets.<SYMBOL>.take_profit.tp_low_ratio (REQUIRED)

        Raises:
            ValueError: If sl_pct or tp_low_ratio not configured for symbol.
        """
        if self.position_entry_price is None or self.position_side is None:
            return None, None, None

        # PHASE A2 FIX: Prioritize injected intent prices (Strategy calculation)
        if self._intent_sl_price:
            LOG.info(
                f"USING_INTENT_SL for calculation: {self._intent_sl_price}")
            sl_price = self._intent_sl_price
            # Consume it
            self._intent_sl_price = None

            # If we have SL, check for TP
            tp1_price = None
            if self._intent_tp_price:
                LOG.info(
                    f"USING_INTENT_TP for calculation: {self._intent_tp_price}")
                tp1_price = self._intent_tp_price
                self._intent_tp_price = None

            # Return early with strategy values (quantized)
            return self._quantize_prices(self.symbol, sl_price, tp1_price, None)

        entry_price = self.position_entry_price
        symbol = self.symbol  # Phase 0: use tracked symbol

        # ========== Get per-instrument config ==========
        sl_pct: Optional[float] = None
        tp_low_ratio: Optional[float] = None
        tp_high_ratio: Optional[float] = None
        partial_exit_pct: Optional[float] = None

        instr_cfg = self._get_aurora_instr_cfg(symbol)
        LOG.info(
            f"BRACKET_CALC [{symbol}]: instr_cfg={'found' if instr_cfg else 'NONE'}")
        if instr_cfg is not None:
            # Get exit config (SL)
            exit_cfg = aget(instr_cfg, "exit", None)
            LOG.info(
                f"BRACKET_CALC [{symbol}]: exit_cfg={'found' if exit_cfg else 'NONE'}")
            if exit_cfg is not None:
                sl_pct = aget(exit_cfg, "sl_pct", None)
                LOG.info(f"BRACKET_CALC [{symbol}]: sl_pct={sl_pct}")
            # Get take_profit config (TP1/TP2)
            tp_low_ratio, tp_high_ratio, partial_exit_pct = self._get_take_profit_params(
                symbol)
            LOG.info(
                f"BRACKET_CALC [{symbol}]: tp_low={tp_low_ratio}, tp_high={tp_high_ratio}")

        # Store partial_exit_pct for bracket placement
        self.partial_exit_pct = partial_exit_pct

        # ========== Calculate SL price ==========
        # FAIL-CLOSED: No fallback! If sl_pct not configured, crash explicitly
        if sl_pct is None:
            raise ValueError(
                f"FAIL-CLOSED: sl_pct not configured for {symbol}. "
                f"Add 'exit.sl_pct' to config/aurora/strategies/aurora.yaml for this symbol. "
                f"No fallback allowed - explicit config required."
            )
        fallback_targets = compute_bracket_targets(
            reference_price=entry_price,
            position_side=self.position_side,
            sl_pct=sl_pct,
            tp_low_ratio=tp_low_ratio,
            tp_high_ratio=tp_high_ratio,
        )
        sl_price = fallback_targets.sl_price
        LOG.info(
            f"BRACKET_CALC [{symbol}]: Using per-symbol sl_pct={sl_pct}, SL={sl_price}")

        # ========== Calculate TP1/TP2 prices ==========
        # FAIL-CLOSED: No fallback! If tp_low_ratio not configured, crash explicitly
        if tp_low_ratio is None:
            raise ValueError(
                f"FAIL-CLOSED: tp_low_ratio not configured for {symbol}. "
                f"Add 'take_profit.tp_low_ratio' to config/aurora/strategies/aurora.yaml for this symbol. "
                f"No fallback allowed - explicit config required."
            )

        tp1_price = fallback_targets.tp1_price
        tp2_price = fallback_targets.tp2_price

        # ========== Quantize prices to tick_size ==========
        sl_price, tp1_price, tp2_price = self._quantize_prices(
            symbol, sl_price, tp1_price, tp2_price)

        return sl_price, tp1_price, tp2_price

    # NOTE: _calculate_sl_from_bps and _calculate_tp_from_bps REMOVED
    # FAIL-CLOSED policy: No fallback to bps. Config must be explicit.

    def _quantize_prices(
        self,
        symbol: Optional[str],
        sl_price: Optional[Decimal],
        tp1_price: Optional[Decimal],
        tp2_price: Optional[Decimal],
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Quantize prices to tick_size from instruments SSOT (FAIL-CLOSED: no fallback)."""
        if not symbol:
            raise ValueError(
                "symbol is required for price quantization (tick_size lookup)")
        if not getattr(self.config, "instruments", None) or symbol not in self.config.instruments:
            raise ValueError(
                f"instruments.{symbol}.tick_size is required for price quantization")

        tick_size_dec = self.config.instruments[symbol].tick_size
        if tick_size_dec <= 0:
            raise ValueError(
                f"instruments.{symbol}.tick_size must be > 0, got {tick_size_dec}")

        # FIX-1111: side-aware rounding  bracket orders are always the opposite side
        # BUY position  SELL brackets  FLOOR (avoid trigger too early)
        # SELL position  BUY brackets  CEIL (avoid trigger too early)
        bracket_side = self._get_opposite_side() if self.position_side else "SELL"
        tick_size_float = float(tick_size_dec)

        if sl_price is not None:
            sl_price = Decimal(str(quantize_stop_price(
                float(sl_price), tick_size_float, side=bracket_side)))
        if tp1_price is not None:
            tp1_price = Decimal(str(quantize_stop_price(
                float(tp1_price), tick_size_float, side=bracket_side)))
        if tp2_price is not None:
            tp2_price = Decimal(str(quantize_stop_price(
                float(tp2_price), tick_size_float, side=bracket_side)))

        return sl_price, tp1_price, tp2_price

    def _get_opposite_side(self) -> str:
        """Get opposite side for closing position."""
        return "SELL" if self.position_side == "BUY" else "BUY"

    def _emit_place_order(
        self,
        msg: Message,
        client_id: str,
        order_type: str,
        side: str,
        qty: str,
        price: str,
        why: str,
    ) -> Message:
        """Emit DEC:PLACE_ORDER for bracket."""

        # Get workingType and priceProtect from config
        working_type = "MARK_PRICE"  # Default
        price_protect = False  # Default

        if self._manage_cfg and self._manage_cfg.brackets:
            brackets = self._manage_cfg.brackets
            if hasattr(brackets, 'working_type_default'):
                working_type = brackets.working_type_default
            if hasattr(brackets, 'price_protect'):
                price_protect = brackets.price_protect

        # Build payload
        msg_pld = msg.pld or {}
        payload = {
            "symbol": msg_pld["symbol"] if "symbol" in msg_pld else "",
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "price": price if order_type == "LIMIT" else None,
            "stopPrice": price if order_type not in ("LIMIT", "MARKET") else None,
            "reduceOnly": True,
            "newClientOrderId": client_id,
            "workingType": working_type,
            "priceProtect": price_protect,
        }

        # For STOP_MARKET/TAKE_PROFIT_MARKET with closePosition=true, don't send qty
        if order_type not in ("LIMIT", "MARKET") and order_type != "STOP_LOSS" and bool(aget(self, "closePosition", False)):
            # Remove qty for close-position orders (Binance manages qty automatically)
            payload.pop("qty", None)

        return Message(
            op="DEC",
            verb="PLACE_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=client_id,
            pld=payload,
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

    def _on_bracket_placed(self, msg: Message) -> Optional[Message]:
        """Handle bracket order placement confirmation."""
        pld = msg.pld or {}
        client_order_id = pld.get("clientOrderId")
        order_id = pld.get("orderId")

        if client_order_id and order_id:
            role = classify_client_order_id(client_order_id)
            if role in {"SL", "BHSL"}:
                self.sl_order_id = order_id
            elif role == "TP1":
                self.tp1_order_id = order_id
                self.tp_order_id = order_id
            elif role == "TP2":
                self.tp2_order_id = order_id
                if not self.tp_order_id:
                    self.tp_order_id = order_id
            elif role in {"TP", "BHTP"}:
                self.tp_order_id = order_id

            # Check if both brackets are placed
            if self.sl_order_id and (self.tp_order_id or self.tp1_order_id or self.tp2_order_id):
                self.state = ManageState.BRACKETS_PLACED
                LOG.info(
                    "Both brackets placed: SL=%s, TP=%s, TP1=%s, TP2=%s",
                    self.sl_order_id,
                    self.tp_order_id,
                    self.tp1_order_id,
                    self.tp2_order_id,
                )

        return None

    def _check_rules(self, msg: Message) -> Optional[Message]:
        """
        Check management rules: brackets, trailing stop, max hold time.

        FAIL-CLOSED: Uses per-instrument config ONLY. No global fallback.
        Missing config will raise ValueError on bracket calculation.

        Returns:
            DEC:PLACE_ORDER, DEC:CANCEL_ORDER, or DEC:ADJUST if rule triggers, None otherwise.
        """
        if self.position_qty is None or self.position_entry_price is None:
            return None

        try:
            # Emergency protection - SSOT: trading.execution.manage.emergency (FAIL-CLOSED)
            emergency_enabled = False
            emergency_sl_bps = 100  # Will be overwritten if emergency enabled

            if self._manage_cfg and self._manage_cfg.emergency:
                em_cfg = self._manage_cfg.emergency
                emergency_enabled = bool(em_cfg.enabled)
                # FAIL-CLOSED: if emergency enabled, emergency_sl_bps must be configured
                if emergency_enabled:
                    emergency_sl_bps = int(em_cfg.emergency_sl_bps)

            if emergency_enabled and msg.op == "UPD" and msg.verb == "MARKET_DATA":
                pld = msg.pld or {}
                cur = pld.get("price")
                if cur is not None and self.position_entry_price:
                    current_price_dec = Decimal(str(cur))
                    sl_em_bps = Decimal(str(emergency_sl_bps))
                    adverse = (self.position_entry_price - current_price_dec) if (
                        self.position_side == "BUY") else (current_price_dec - self.position_entry_price)
                    if adverse > 0:
                        adverse_bps = (
                            adverse / self.position_entry_price) * Decimal("10000")
                        if adverse_bps >= sl_em_bps:
                            # Move to WAIT_MODE for configured number of bars
                            try:
                                now_ts = int((msg.pld or {}).get("ts")) if (
                                    msg.pld or {}).get("ts") else get_clock().now_ms()
                            except Exception:
                                now_ts = get_clock().now_ms()
                            # Direct access (fail-closed: missing emergency config  crash)
                            if not hasattr(self, "_bar_ms") or not hasattr(self, "_wait_mode_bars"):
                                raise ValueError(
                                    "CRITICAL: Emergency mode activated but _bar_ms/_wait_mode_bars not configured. "
                                    "Cannot determine wait period (fail-closed)."
                                )
                            bar_index = now_ts // self._bar_ms
                            self._wait_mode_until_ts = (
                                bar_index + self._wait_mode_bars) * self._bar_ms
                            self.state = ManageState.WAIT_MODE
                            new_sl = (self.position_entry_price * (Decimal("1") - sl_em_bps / Decimal("10000"))) if self.position_side == "BUY" else (
                                self.position_entry_price * (Decimal("1") + sl_em_bps / Decimal("10000")))
                            emergency_symbol = (
                                (msg.pld or {}).get(
                                    "symbol") or self.symbol or ""
                            )
                            emergency_idem = (
                                f"{aget(msg, 'rid', '')}_{int(self.position_open_ts)}_emergency"
                            )
                            return self._emit_place_order(
                                msg,
                                client_id=generate_client_order_id(
                                    "SL",
                                    emergency_symbol,
                                    idempotent_key=emergency_idem,
                                ),
                                order_type="STOP_MARKET",
                                side=self.position_side or "",
                                qty=str(self.position_qty),
                                price=str(new_sl),
                                why="emergency_stop_activate",
                            )
            # Handle bracket fills (OCO emulation)
            if msg.verb in ("TRADE_EXECUTED", "ORDER_UPDATED"):
                bracket_action = self._handle_bracket_fill(msg)
                if bracket_action:
                    return bracket_action

            # Handle trailing stop (per-instrument config)
            if msg.op == "UPD" and msg.verb == "MARKET_DATA":
                trailing_action = self._check_trailing_stop(msg)
                if trailing_action:
                    return trailing_action

            now = get_clock().now_sec()
            elapsed = now - self.position_open_ts

            # Phase A4: Max hold time watchdog (per-instrument config)
            max_hold_action = self._check_max_hold_time(msg, elapsed)
            if max_hold_action:
                return max_hold_action

        except (ValueError, TypeError, KeyError, ArithmeticError) as e:
            LOG.warning(f"Error in _check_rules: {e}")
            self._metrics["fsm_errors_total"] += 1

        return None

    def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
        """
        Handle SL/TP bracket fills and perform OCO emulation.

        Phase A2: Supports TP1/TP2 partial exit:
        - TP1 fill: reduces position_qty by partial_exit_pct, keeps TP2 and adjusts SL
        - TP2 fill: closes remaining position, cancels SL
        - SL fill: cancels all remaining TP orders
        """
        pld = msg.pld or {}
        order_id = pld.get("orderId")
        client_order_id = self._client_order_id_from_payload(pld)

        if not order_id:
            return None

        local_state_before = self.state.value
        position_qty_before = self.position_qty
        expected_ids_before = self._local_expected_ids_snapshot()
        inferred_role, matched, match_reason = self._resolve_bracket_match(
            order_id,
            client_order_id,
            pld,
        )
        should_trace_exit_match = self._is_exit_fill_payload(pld) or matched

        oco_enabled = False
        if self._manage_cfg and self._manage_cfg.brackets:
            oco_enabled = self._manage_cfg.brackets.oco_emulation

        # === SL FILLED ===
        if matched and inferred_role == "SL":
            LOG.info(f"[ManageFlowFSM] SL filled: {order_id}")
            decisions = []

            # Cancel all TP orders (OCO emulation)
            if oco_enabled:
                if self.tp1_order_id:
                    decisions.append(self._emit_cancel_order(
                        msg, self.tp1_order_id, "OCO_SL_filled_tp1"))
                if self.tp2_order_id:
                    decisions.append(self._emit_cancel_order(
                        msg, self.tp2_order_id, "OCO_SL_filled_tp2"))
                # Legacy fallback
                elif self.tp_order_id and self.tp_order_id != self.tp1_order_id:
                    decisions.append(self._emit_cancel_order(
                        msg, self.tp_order_id, "OCO_SL_filled"))

            # Clear all bracket tracking
            self._clear_lifecycle_tracking(
                reason="sl_filled",
                clear_symbol=True,
            )
            self.state = ManageState.FLAT

            # Return first cancel decision (others handled in next cycle)
            result = decisions[0] if decisions else None
            if should_trace_exit_match:
                self._emit_exit_match_observability(
                    msg,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    inferred_role="SL",
                    matched=True,
                    match_reason=match_reason,
                    local_expected_ids=expected_ids_before,
                    local_state_before=local_state_before,
                    local_state_after=self.state.value,
                    position_qty_before=position_qty_before,
                )
            return result

        # === TP1 FILLED (partial exit) ===
        if matched and inferred_role == "TP1":
            LOG.info(f"[ManageFlowFSM] TP1 filled (partial exit): {order_id}")

            # Update position qty (reduce by partial_exit_pct)
            if self.position_qty and self.partial_exit_pct:
                filled_pct = Decimal(str(self.partial_exit_pct))
                filled_qty = self.position_qty * filled_pct
                self.position_qty = self.position_qty - filled_qty
                LOG.info(
                    f"[ManageFlowFSM] Position reduced: filled={filled_qty}, remaining={self.position_qty}")
                self._metrics["fsm_partial_exits_total"] = int(
                    self._metrics["fsm_partial_exits_total"]) + 1

            # Clear TP1, keep TP2 as "runner"
            self.tp1_order_id = None

            # If no TP2 configured, this was single-TP mode - cancel SL
            if not self.tp2_order_id and oco_enabled and self.sl_order_id:
                LOG.info(
                    f"[ManageFlowFSM] Single TP mode, cancelling SL: {self.sl_order_id}")
                decision = self._emit_cancel_order(
                    msg, self.sl_order_id, "OCO_TP1_filled_no_tp2")
                self.sl_order_id = None
                self.tp_order_id = None
                self.sl_algo_client_id = None
                self.tp_algo_client_id = None
                if should_trace_exit_match:
                    self._emit_exit_match_observability(
                        msg,
                        order_id=order_id,
                        client_order_id=client_order_id,
                        inferred_role="TP1",
                        matched=True,
                        match_reason=match_reason,
                        local_expected_ids=expected_ids_before,
                        local_state_before=local_state_before,
                        local_state_after=self.state.value,
                        position_qty_before=position_qty_before,
                    )
                return decision

            # TODO: Consider adjusting SL to breakeven after TP1 (optional feature)
            if should_trace_exit_match:
                self._emit_exit_match_observability(
                    msg,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    inferred_role="TP1",
                    matched=True,
                    match_reason=match_reason,
                    local_expected_ids=expected_ids_before,
                    local_state_before=local_state_before,
                    local_state_after=self.state.value,
                    position_qty_before=position_qty_before,
                )
            return None

        # === TP2 FILLED (remainder/runner) ===
        if matched and inferred_role == "TP2":
            LOG.info(f"[ManageFlowFSM] TP2 filled (runner closed): {order_id}")
            decision = None

            # Cancel SL (OCO emulation) - position fully closed
            if oco_enabled and self.sl_order_id:
                LOG.info(
                    f"[ManageFlowFSM] TP2 filled, cancelling SL: {self.sl_order_id}")
                decision = self._emit_cancel_order(
                    msg, self.sl_order_id, "OCO_TP2_filled")

            # Clear all bracket tracking
            self._clear_lifecycle_tracking(
                reason="tp2_filled",
                clear_symbol=True,
            )
            self.state = ManageState.FLAT

            if should_trace_exit_match:
                self._emit_exit_match_observability(
                    msg,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    inferred_role="TP2",
                    matched=True,
                    match_reason=match_reason,
                    local_expected_ids=expected_ids_before,
                    local_state_before=local_state_before,
                    local_state_after=self.state.value,
                    position_qty_before=position_qty_before,
                )
            return decision

        # === Legacy TP (backward compat) ===
        if matched and inferred_role == "TP":
            LOG.info(f"[ManageFlowFSM] Legacy TP filled: {order_id}")
            decision = None

            if oco_enabled and self.sl_order_id:
                decision = self._emit_cancel_order(
                    msg, self.sl_order_id, "OCO_TP_filled")

            self._clear_lifecycle_tracking(
                reason="tp_filled",
                clear_symbol=True,
            )
            self.state = ManageState.FLAT
            if should_trace_exit_match:
                self._emit_exit_match_observability(
                    msg,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    inferred_role="TP",
                    matched=True,
                    match_reason=match_reason,
                    local_expected_ids=expected_ids_before,
                    local_state_before=local_state_before,
                    local_state_after=self.state.value,
                    position_qty_before=position_qty_before,
                )
            return decision

        if should_trace_exit_match:
            self._emit_exit_match_observability(
                msg,
                order_id=order_id,
                client_order_id=client_order_id,
                inferred_role=inferred_role,
                matched=matched,
                match_reason=match_reason,
                local_expected_ids=expected_ids_before,
                local_state_before=local_state_before,
                local_state_after=self.state.value,
                position_qty_before=position_qty_before,
            )
        return None

    def _check_trailing_stop(self, msg: Message) -> Optional[Message]:
        """
        Check and adjust trailing stop if conditions met.

        Uses per-instrument trailing_stop config ONLY (no global fallback).
        If not configured for symbol, trailing is disabled (fail-safe).
        Implements high-water mark trailing with CANCEL+NEW flow.
        """
        # Get trailing params from per-instrument config (no global fallback)
        enabled, activation_pct, trail_pct, min_update_sec = self._get_trailing_stop_params(
            self.symbol)

        if not enabled or not self.sl_order_id:
            return None

        try:
            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None

            current_price_dec = Decimal(str(current_price))
            now = get_clock().now_sec()

            # Update peak price (high-water mark)
            if self.peak_price is None:
                self.peak_price = current_price_dec
            elif self.position_side == "BUY" and current_price_dec > self.peak_price:
                self.peak_price = current_price_dec
            elif self.position_side == "SELL" and current_price_dec < self.peak_price:
                self.peak_price = current_price_dec

            # Check activation condition
            # SSOT: Per-instrument config OR global trailing defaults from system.yaml
            if not self.trailing_activated and self.position_entry_price:
                # FAIL-CLOSED: activation_pct must be configured (per-instrument or global)
                if activation_pct is None:
                    # Try global trailing defaults
                    if self.config.trailing and self.config.trailing.activation_pct is not None:
                        activation_pct = self.config.trailing.activation_pct
                    else:
                        raise ValueError(
                            f"activation_pct not configured for {self.symbol} and no global trailing defaults. "
                            "Configure per-instrument trailing_stop.activation_pct or system.yaml trailing.activation_pct"
                        )

                if self.position_side == "BUY":
                    activation_threshold = self.position_entry_price * (
                        Decimal("1") + Decimal(str(activation_pct))
                    )
                    if current_price_dec >= activation_threshold:
                        self.trailing_activated = True
                        self.peak_price = current_price_dec
                    else:
                        return None
                elif self.position_side == "SELL":
                    activation_threshold = self.position_entry_price * (
                        Decimal("1") - Decimal(str(activation_pct))
                    )
                    if current_price_dec <= activation_threshold:
                        self.trailing_activated = True
                        self.peak_price = current_price_dec
                    else:
                        return None

            # Rate limit: minimum interval between updates
            if now - self.last_trailing_ts < min_update_sec:
                return None

            # Calculate new SL price based on trail_pct from peak
            # FAIL-CLOSED: trail_pct must be configured (per-instrument or global)
            if trail_pct is None:
                # Try global trailing defaults
                if self.config.trailing and self.config.trailing.trail_pct is not None:
                    trail_pct = self.config.trailing.trail_pct
                else:
                    raise ValueError(
                        f"trail_pct not configured for {self.symbol} and no global trailing defaults. "
                        "Configure per-instrument trailing_stop.trail_pct or system.yaml trailing.trail_pct"
                    )

            trail_pct_dec = Decimal(str(trail_pct))

            if self.position_side == "BUY" and self.sl_price and self.peak_price:
                # BUY: SL trails below peak
                new_sl_price = self.peak_price * (Decimal("1") - trail_pct_dec)
                # Only update if new SL is higher (tighter)
                if new_sl_price > self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

            elif self.position_side == "SELL" and self.sl_price and self.peak_price:
                # SELL: SL trails above peak (peak is low point)
                new_sl_price = self.peak_price * (Decimal("1") + trail_pct_dec)
                # Only update if new SL is lower (tighter)
                if new_sl_price < self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

        except (ValueError, TypeError, KeyError, ArithmeticError) as e:
            LOG.warning(f"Trailing stop check failed: {e}")
            self._metrics["fsm_errors_total"] += 1

        return None

    def _adjust_trailing_stop(self, msg: Message, new_sl_price: Decimal) -> Message:
        """
        Adjust trailing stop by cancelling old and placing new.

        Phase A3: CANCEL+NEW flow for trailing stop modification.
        """
        self.last_trailing_ts = get_clock().now_sec()
        self.sl_price = new_sl_price
        self._metrics["fsm_trailing_adjustments"] += 1

        # Cancel old SL
        cancel_msg = self._emit_cancel_order(
            msg, self.sl_order_id or "", "trailing_adjust")

        # FIX-4015: use hash-based ID for trailing stop (32 chars)
        _trail_sym = (msg.pld or {}).get("symbol") or self.symbol or ""
        _trail_idem = f"{msg.rid}_{int(self.position_open_ts)}_trail_{int(get_clock().now_sec())}"
        new_client_id = generate_client_order_id(
            "SL", _trail_sym, idempotent_key=_trail_idem)

        # Use opposite side for SL order (to close position)
        new_sl_msg = self._emit_place_order(
            msg,
            new_client_id,
            "STOP_MARKET",
            self._get_opposite_side(),
            str(self.position_qty),
            str(new_sl_price),
            "trailing_stop_adjust",
        )

        # Update SL order ID to new one
        self.sl_order_id = new_client_id

        # Return cancel first - new order will be placed on next cycle
        return cancel_msg

    def _emit_cancel_order(self, msg: Message, order_id: str, why: str) -> Message:
        """Emit DEC:CANCEL_ORDER with symbol included for adapter call."""
        msg_pld = msg.pld or {}
        symbol = msg_pld["symbol"] if "symbol" in msg_pld else ""
        return Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"cancel_{order_id}_{int(get_clock().now_sec())}",
            pld={
                "orderId": order_id,
                "symbol": symbol,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

    def _emit_adjust(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:ADJUST with stub rules."""
        self.state = ManageState.EMIT_DEC_ADJUST
        self._metrics["fsm_adjust_decisions_total"] += 1

        dec = Message(
            op="DEC",
            verb="ADJUST",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(get_clock().now_sec())}",
            pld=details,
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

        # Return to TRACKING
        self.state = ManageState.TRACKING
        return dec

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def hydrate(self, state_data: Dict[str, Any]) -> None:
        """
        Restore FSM state from persisted data.

        Args:
            state_data: Dictionary containing position and bracket state
        """
        try:
            # Validate required fields
            if "qty" not in state_data:
                self.state = ManageState.ERROR
                return

            # Restore symbol (critical for fail-closed config lookup)
            self.symbol = state_data.get("symbol")

            # Restore position data
            qty_value = state_data.get("qty")
            entry_price_value = state_data.get("entry_price")
            self.position_qty = Decimal(str(qty_value)) if qty_value else None
            self.position_entry_price = Decimal(
                str(entry_price_value)) if entry_price_value else None
            self.position_side = state_data.get("side")
            self.position_open_ts = float(
                state_data["open_ts"] if "open_ts" in state_data else 0)

            # Restore bracket data
            self.sl_order_id = state_data.get("sl_order_id")
            self.tp_order_id = state_data.get("tp_order_id")

            # Set appropriate state based on what data is available
            if self.position_qty and self.position_qty != 0:
                if self.sl_order_id:
                    self.state = ManageState.BRACKETS_PLACED
                else:
                    self.state = ManageState.TRACKING
            else:
                self.state = ManageState.FLAT

        except (ValueError, TypeError, KeyError) as e:
            LOG.error(f"Failed to hydrate ManageFlowFSM: {e}")
            self.state = ManageState.ERROR

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = ManageState.FLAT
        self._clear_lifecycle_tracking(reason="reset", clear_symbol=True)
