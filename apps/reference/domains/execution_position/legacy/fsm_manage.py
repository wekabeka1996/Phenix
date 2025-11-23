"""
Legacy ExecPos FSM stack (test-only). Do not use in new runtime code.

DEPRECATED: Legacy Manage Flow FSM for execution_position.

Superseded by ExecPosRuntimeV2 + BracketService apply-plan path.
Kept only for historical/archival tests; not used in production.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from vfoundation.services.price_service import PriceService

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.brackets_config import (
    ResolvedBrackets,
    resolve_brackets_config,
)
from vfoundation.apps.reference.domains.execution_position.bracket_aggregator import (
    AggregatedBracketLevels,
    AggregatedOcoError,
    AggregatedOcoRiskConfig,
    InstrumentPriceConstraints,
    compute_aggregated_brackets,
)
from apps.reference.domains.execution_position.contracts import (
    TPSLValidationRules,
    PositionSide,
    PositionSnapshot,
    canonicalize_position_side,
    canonicalize_position_side_from_qty,
    build_dec_close,
)
from apps.reference.domains.execution_position.utils import (
    build_bracket_client_ids,
    build_client_order_id,
    ClientOrderIntent,
    parse_client_order_id,
)
from apps.reference.domains.execution_position.manage_config import (
    AggregatedOcoConfig,
    ExecutionManageConfig,
    resolve_execution_manage_config,
)
from apps.reference.domains.execution_position.shadow_execpos.gatekeeper import ExecPosGatekeeper


agg_oco_logger = logging.getLogger("agg_oco")
LOG = logging.getLogger(__name__)
LEGACY_OCO_DEPRECATED = True


try:
    from apps.reference.telemetry.metrics import inc_manage_skipped
except ImportError:

    def inc_manage_skipped() -> None:
        pass


class ManageState(str, Enum):
    """FSM states for manage flow."""

    FLAT = "FLAT"
    TRACKING = "TRACKING"
    BRACKETS_PENDING = "BRACKETS_PENDING"
    BRACKETS_PLACED = "BRACKETS_PLACED"
    EMIT_DEC_ADJUST = "EMIT_DEC_ADJUST"
    ERROR = "ERROR"
    WAIT_MODE = "WAIT_MODE"


class ManageFlowFSM:
    """State machine managing bracket placement per symbol."""

    CLIENT_ORDER_ID_MAX_LEN = 36
    CLOSING_FLAG_ENTRY_TOLERANCE_MS = 150
    """
    Manage Flow FSM: tracks open positions and manages brackets/trailing stops.

    Shadow-mode: stub rules (trail/breakeven/time_stop).
    Rules execute on EVT:PARTIAL_FILL|FILL|UPD:*.
    """

    def __init__(
        self,
        trail_pct: float = 0.5,
        breakeven_after_sec: float = 300.0,
        config: Optional[Dict[str, Any]] = None,
        price_service: Optional[PriceService] = None,
        order_guardian: Optional[Any] = None,
        live_position_provider: Optional[Callable[[
        ], Optional[Dict[str, Any]]]] = None,
        symbol: Optional[str] = None,
        rid: Optional[str] = None,
        qty_guard: Optional[ExecPosGatekeeper] = None,
    ):
        LOG.warning("ManageFlowFSM is deprecated; use ExecPosRuntimeV2 + BracketService (shadow_execpos) instead")
        self.state = ManageState.FLAT
        self.trail_pct = trail_pct  # stub: trailing stop %
        self.breakeven_after_sec = breakeven_after_sec  # stub: move to BE after X sec

        # Position tracking
        self.position_qty: Optional[Decimal] = None
        self.position_entry_price: Optional[Decimal] = None
        self.position_open_ts: float = 0.0
        self.position_side: Optional[str] = None  # 'BUY' or 'SELL'
        self.symbol: Optional[str] = symbol
        self.rid: Optional[str] = rid

        # Bracket orders tracking
        self.sl_order_id: Optional[str] = None
        self.tp_order_id: Optional[str] = None
        self.sl_price: Optional[Decimal] = None
        self.tp_price: Optional[Decimal] = None
        self._pending_decisions: Deque[Message] = deque()

        # Trailing stop tracking
        self.trailing_activated: bool = False
        self.last_trailing_ts: float = 0.0

        # PHASE A2: Anti-race flag - prevents bracket placement during CLOSE
        self._closing_position: bool = False
        self._closing_position_ts: float = 0.0

        # Aggregated OCO bookkeeping
        self._aggregated_last_place_ts: int = 0
        self._agg_side: Optional[str] = None

        # Configuration
        self.config = config or {}
        # Optional price service (SSOT) for mark/last/mid retrieval
        self.price_service: Optional[PriceService] = price_service
        self._order_guardian = order_guardian
        self._live_position_provider = live_position_provider
        self._current_bracket_set_id: Optional[str] = None
        self._current_bracket_meta: Optional[Any] = None
        self._pending_bracket_log: Optional[Dict[str, Any]] = None
        self._qty_guard = qty_guard or ExecPosGatekeeper(config=self.config)
        # Emergency/WaitMode configuration
        # Using typed attribute access for Pydantic models
        try:
            if isinstance(self.config, dict):
                bar_gate_cfg = self.config.get("trading", {}).get(
                    "decision", {}).get("bar_gating", {})
                self._bar_ms = int(bar_gate_cfg.get(
                    "bar_ms", 15 * 60 * 1000)) if isinstance(bar_gate_cfg, dict) else 15 * 60 * 1000
            else:
                bar_gate_cfg = self.config.trading.decision.bar_gating if self.config.trading else None
                self._bar_ms = int(bar_gate_cfg.bar_ms) if bar_gate_cfg and hasattr(
                    bar_gate_cfg, 'bar_ms') else 15 * 60 * 1000
        except (AttributeError, TypeError, ValueError):
            self._bar_ms = 15 * 60 * 1000

        manage_cfg = self._manage_config()
        self._wait_mode_bars = manage_cfg.emergency.wait_mode_bars
        self._wait_mode_until_ts: int = 0

        # Anti-race window (ms) configurable via config; default 800ms
        try:
            if hasattr(self.config, 'execution') and self.config.execution:
                self._anti_race_close_ms = int(
                    getattr(self.config.execution, 'anti_race_close_ms', 800))
            elif hasattr(self.config, 'trading') and self.config.trading:
                exec_cfg = getattr(self.config.trading, 'execution', None)
                self._anti_race_close_ms = int(
                    getattr(exec_cfg, 'anti_race_close_ms', 800)) if exec_cfg else 800
            elif isinstance(self.config, dict):
                self._anti_race_close_ms = int(
                    self.config.get('execution', {}).get('anti_race_close_ms')
                    or self.config.get('trading', {}).get('execution', {}).get('anti_race_close_ms', 800)
                )
            else:
                self._anti_race_close_ms = 800
        except Exception:
            self._anti_race_close_ms = 800

        self._auto_manage_enabled = bool(manage_cfg.auto)

        # Log configuration status
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"ManageFlowFSM initialized: auto_manage_enabled={self._auto_manage_enabled}")

        agg_cfg = getattr(manage_cfg, "brackets", None)
        aggregated_meta = getattr(
            agg_cfg, "aggregated_oco", None) if agg_cfg else None

        self._metrics: Dict[str, int] = {
            "fsm_adjust_decisions_total": 0,
            "fsm_bracket_orders_placed": 0,
            "fsm_trailing_adjustments": 0,
            "fsm_errors_total": 0,
            "agg_entry_price_not_ready": 0,  # EP-STAB-LIVEPOS-FIX-DOCS+OBS
            "agg_entry_price_recovered_from_price_service": 0,
        }
        self._aggregated_only_mode = self._resolve_aggregated_only_mode_flag(
            aggregated_meta
        )
        agg_oco_logger.info(
            "ManageFlowFSM aggregated-only mode", extra={
                "aggregated_only_mode": self._aggregated_only_mode
            }
        )
        qp_cfg = manage_cfg.quick_profit
        self.quick_profit_enabled = qp_cfg.enabled
        self.quick_profit_mode = qp_cfg.mode
        self.quick_profit_target_usd = qp_cfg.target_usd
        self.quick_profit_priority = qp_cfg.priority

    def _manage_config(self) -> ExecutionManageConfig:
        return resolve_execution_manage_config(self.config)

    def _resolve_aggregated_only_mode_flag(self, aggregated_meta: Optional[AggregatedOcoConfig]) -> bool:
        explicit = getattr(aggregated_meta or object(),
                           "aggregated_only_mode", None)
        if explicit is not None:
            return bool(explicit)

        if self._lookup_config_bool(
            (
                ("trading", "execution", "manage", "brackets",
                 "aggregated_oco", "aggregated_only_mode"),
                ("execution", "manage", "brackets",
                 "aggregated_oco", "aggregated_only_mode"),
                ("config_v2", "domains", "execution", "manage",
                 "brackets", "aggregated_oco", "aggregated_only_mode"),
            )
        ):
            return True

        return self._is_manage_mode_aggregated_only()

    def _lookup_config_bool(self, paths: tuple[tuple[str, ...], ...]) -> bool:
        for path in paths:
            raw_value = self._deep_pluck(self.config, *path)
            normalized = self._coerce_optional_bool(raw_value)
            if normalized is not None:
                return normalized
        return False

    def _is_manage_mode_aggregated_only(self) -> bool:
        mode_candidate = self._deep_pluck(
            self.config, "trading", "execution", "manage", "mode"
        )
        if isinstance(mode_candidate, str) and mode_candidate.strip().lower() == "aggregated_only":
            return True

        mode_candidate = self._deep_pluck(
            self.config, "config_v2", "domains", "execution", "manage", "mode"
        )
        return bool(
            isinstance(mode_candidate, str)
            and mode_candidate.strip().lower() == "aggregated_only"
        )

    @staticmethod
    def _coerce_optional_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        try:
            return bool(value)
        except Exception:
            return None

    @staticmethod
    def _deep_pluck(source: Any, *path: str) -> Any:
        current = source
        for key in path:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(key)
                continue
            try:
                current = getattr(current, key)
                continue
            except AttributeError:
                pass
            try:
                current = current[key]  # type: ignore[index]
            except Exception:
                return None
        return current

    def _build_sl_tp_client_ids(self, msg: Message) -> tuple[str, str, str]:
        """Return shared bundle id plus SL/TP variants via shared builder."""

        payload = msg.pld or {}
        symbol = getattr(self, "symbol", None) or payload.get("symbol")
        rid = getattr(msg, "rid", None)
        decision_id = payload.get("orderId") or getattr(msg, "id", None)
        ts_ms = self._extract_fill_timestamp_ms(
            payload) or int(time.time() * 1000)
        entry, sl_meta, tp_meta = build_bracket_client_ids(
            rid=str(rid) if rid else None,
            symbol=str(symbol) if symbol else None,
            decision_id=str(decision_id) if decision_id else None,
            extra="manage_brackets",
            ts_ms=ts_ms,
            max_len=self.CLIENT_ORDER_ID_MAX_LEN,
        )
        bundle_id = entry.bundle_key() or entry.raw
        return bundle_id, sl_meta.raw, tp_meta.raw

    def _extract_fill_timestamp_ms(self, payload: Dict[str, Any]) -> Optional[int]:
        """Extract fill timestamp from payload if available."""
        ts_sources = ("ts", "event_time", "eventTime", "E",
                      "T", "time", "transactTime")
        for key in ts_sources:
            candidate = payload.get(key)
            if candidate is None:
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    def _is_definitely_new_entry(self, msg: Message) -> Tuple[bool, Dict[str, Any]]:
        """Determine if entry fill unquestionably follows the close flag."""
        payload = msg.pld or {}
        fill_ts_ms = self._extract_fill_timestamp_ms(payload)
        closing_ts_ms = int(self._closing_position_ts * 1000)
        symbol = payload.get("symbol") or getattr(self, "symbol", None)
        meta: Dict[str, Any] = {
            "fill_ts_ms": fill_ts_ms,
            "closing_ts_ms": closing_ts_ms,
            "symbol": symbol,
        }

        if not self._closing_position:
            meta["reason"] = "closing_flag_not_set"
            return True, meta

        if closing_ts_ms == 0:
            meta["reason"] = "closing_ts_missing"
            return True, meta

        if fill_ts_ms is None:
            meta["reason"] = "fill_ts_missing"
            return False, meta

        if fill_ts_ms + self.CLOSING_FLAG_ENTRY_TOLERANCE_MS < closing_ts_ms:
            meta["reason"] = "fill_before_closing_flag"
            return False, meta

        meta["reason"] = "fill_after_closing_flag"
        return True, meta

    def _get_live_position_state(self) -> Optional[Dict[str, Any]]:
        provider = getattr(self, "_live_position_provider", None)
        if not callable(provider):
            return None
        try:
            snapshot = provider()
        except Exception:
            logging.getLogger(__name__).error(
                "[BRK][agg] live position provider raised exception",
                extra={
                    "symbol": getattr(self, "symbol", None),
                    "event_type": "LIVE_PROVIDER_EXCEPTION"
                },
                exc_info=True
            )
            return None
        if not snapshot:
            return None
        return snapshot

    def set_bracket_ids(self, sl_order_id: Optional[str], tp_order_id: Optional[str]) -> None:
        """
        Directly set bracket IDs from execution runtime after placement.

        This ensures ManageFlowFSM has accurate bracket tracking for OCO emulation,
        even if ORDER_UPDATED WebSocket events are delayed or missed.

        Args:
            sl_order_id: Stop-loss order ID from exchange (string)
            tp_order_id: Take-profit order ID from exchange (string)
        """
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        # Log synchronization for debugging
        import logging
        LOG = logging.getLogger(__name__)
        symbol = getattr(self, "symbol", None)
        canonical = self._resolve_canonical_position_side()
        agg_side = canonical.value if canonical != PositionSide.FLAT else None
        LOG.debug(
            "✅ Synced bracket IDs",
            extra={
                "symbol": symbol,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "agg_side": agg_side,
            },
        )
        agg_oco_logger.info(
            "AGG_OCO_SYNC_BRACKET_IDS",
            extra={
                "symbol": symbol,
                "side": agg_side,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "pending_log": bool(self._pending_bracket_log),
            },
        )

        should_register = (
            self._order_guardian
            and self._is_aggregated_oco_enabled()
            and (self.sl_order_id or self.tp_order_id)
        )
        if not should_register:
            return

        if self._pending_bracket_log is None:
            self._pending_bracket_log = {
                "action": "sync_from_exec_pos",
                "position_qty_before": str(self.position_qty) if self.position_qty is not None else None,
                "position_qty_after": str(self.position_qty) if self.position_qty is not None else None,
                "avg_price_before": str(self.sl_price) if self.sl_price is not None else None,
                "avg_price_after": str(self.sl_price) if self.sl_price is not None else None,
                "sl_price_before": str(self.sl_price) if self.sl_price is not None else None,
                "sl_price_after": str(self.sl_price) if self.sl_price is not None else None,
                "tp_price_before": str(self.tp_price) if self.tp_price is not None else None,
                "tp_price_after": str(self.tp_price) if self.tp_price is not None else None,
                "why": "agg_sync_from_exec_pos",
                "rid": None,
            }

        self._maybe_register_bracket_set()

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:ADJUST if rules trigger.

        Args:
            msg: EVT:PARTIAL_FILL|FILL|UPD:* with payload: symbol, qty, price, etc.

        Returns:
            DEC:ADJUST if rules trigger, None otherwise.
        """
        # Kill-switch: check if auto-manage is disabled
        if not self._auto_manage_enabled:
            inc_manage_skipped()
            # Emit MANAGE_SKIPPED event for observability
            pld_symbol = msg.pld.get("symbol") if isinstance(
                msg.pld, dict) else None
            return Message(
                op="EVT",
                verb="MANAGE_SKIPPED",
                src="execution_position",
                dst="any",
                rid=getattr(msg, "rid", None) or "",
                why="manage_disabled",
                pld={
                    "symbol": pld_symbol,
                    "reason": "auto_manage_disabled",
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
            )

        if msg.op not in ("EVT", "UPD"):
            return None

        # WAIT_MODE handling: skip actions until TTL expires
        try:
            pld = msg.pld or {}
            ts_value = pld.get("ts") if isinstance(pld, dict) else None
            now_ts = int(ts_value) if ts_value else int(time.time() * 1000)
        except Exception:
            now_ts = int(time.time() * 1000)

        if self.state == ManageState.WAIT_MODE:
            if now_ts < self._wait_mode_until_ts:
                pld_symbol = msg.pld.get("symbol") if isinstance(
                    msg.pld, dict) else None
                return Message(
                    op="EVT",
                    verb="MANAGE_SKIPPED",
                    src="execution_position",
                    dst="any",
                    rid=getattr(msg, "rid", None) or "",
                    why="wait_mode_active",
                    pld={"symbol": pld_symbol, "reason": "wait_mode"},
                    data_ref=msg.data_ref.copy() if msg.data_ref else [],
                )
            else:
                self.state = ManageState.TRACKING

        # State transition: FLAT → BRACKETS_PENDING on PARTIAL_FILL or FILL
        if self.state == ManageState.FLAT and msg.verb in (
            "PARTIAL_FILL",
            "FILL",
            "TRADE_EXECUTED",
        ):
            # 🔍 CRITICAL FIX: Distinguish between ENTRY and EXIT fills
            # If this is an EXIT order (TP/SL), position is CLOSING, not opening!
            pld = msg.pld or {}
            from .contracts import is_exit_order
            is_exit = is_exit_order(pld)

            # 🔍 DIAGNOSTIC: Log all FILL events in FLAT state
            order_type = pld.get("order_type") or pld.get("type", "")
            symbol_ref = pld.get("symbol") or getattr(self, "symbol", None)
            LOG.info(
                "EXEC_POS_MANAGE_FILL_IN_FLAT",
                extra={
                    "symbol": symbol_ref,
                    "verb": msg.verb,
                    "order_type": order_type,
                    "is_exit": bool(is_exit),
                    "pld_keys": list(pld.keys()),
                    "why": "flat_state_fill",
                },
            )

            if is_exit:
                # ⚠️ Position is CLOSING via TP/SL - do NOT create new TP/SL!
                LOG.info(
                    "EXEC_POS_MANAGE_EXIT_FILL_SKIPPED",
                    extra={
                        "symbol": symbol_ref,
                        "order_type": order_type,
                        "why": "exit_fill_in_flat",
                    },
                )
                self.position_qty = None
                self.position_entry_price = None
                self.position_side = None
                self.sl_price = None
                self.tp_price = None
                # Stay in FLAT, return without placing new brackets
                return None
            else:
                # ENTRY fill - position is opening
                if self._closing_position:
                    release_flag, release_meta = self._is_definitely_new_entry(
                        msg)
                    if release_flag:
                        self._closing_position = False
                        LOG.info(
                            "EXEC_POS_MANAGE_CLOSING_FLAG_RELEASED",
                            extra={
                                "symbol": release_meta.get("symbol"),
                                "reason": release_meta.get("reason"),
                                "closing_ts_ms": release_meta.get("closing_ts_ms"),
                                "fill_ts_ms": release_meta.get("fill_ts_ms"),
                                "why": "entry_detected",
                            },
                        )
                    else:
                        LOG.info(
                            "EXEC_POS_MANAGE_CLOSING_FLAG_HELD",
                            extra={
                                "symbol": release_meta.get("symbol"),
                                "reason": release_meta.get("reason"),
                                "closing_ts_ms": release_meta.get("closing_ts_ms"),
                                "fill_ts_ms": release_meta.get("fill_ts_ms"),
                                "why": "closing_flag_guard",
                            },
                        )

                LOG.info(
                    "EXEC_POS_MANAGE_ENTRY_FILL_DETECTED",
                    extra={
                        "symbol": symbol_ref,
                        "verb": msg.verb,
                        "why": "entry_fill",
                    },
                )
                self._on_fill(msg)
                self.state = (
                    ManageState.BRACKETS_PENDING
                )  # Place brackets after position opens
                LOG.info(
                    "EXEC_POS_MANAGE_BRACKETS_PENDING",
                    extra={
                        "symbol": symbol_ref,
                        "verb": msg.verb,
                        "why": "place_brackets_after_entry",
                    },
                )
                # Place bracket orders immediately
                return self._place_brackets(msg)

        # Handle bracket order confirmations
        if self.state == ManageState.BRACKETS_PENDING and msg.verb == "ORDER_UPDATED":
            return self._on_bracket_placed(msg)

        # Check rules in TRACKING/BRACKETS_PLACED states
        if self.state in (ManageState.TRACKING, ManageState.BRACKETS_PLACED):
            return self._check_rules(msg)

        return None

    def _on_fill(self, msg: Message):
        """Update position state on fill event."""
        try:
            pld = msg.pld or {}
            qty_value = (
                pld.get("qty")
                if pld.get("qty") is not None
                else pld.get("quantity")
            )
            qty = Decimal(str(qty_value or 0))
            price = Decimal(str(pld.get("price", 0)))

            # Fallback for missing price (e.g. market order with delayed avgPrice)
            if price <= 0 and self.price_service and getattr(self, 'symbol', None):
                try:
                    quote = self.price_service.get_current(self.symbol)
                    fallback = getattr(quote, 'mark', None) or getattr(
                        quote, 'last', None)
                    if fallback:
                        price = Decimal(str(fallback))
                        import logging
                        logging.getLogger(__name__).warning(
                            f"[ManageFlowFSM] ⚠️ Price missing in fill payload, using PriceService fallback: {price}"
                        )
                except Exception:
                    pass

            side = self._normalize_order_side(pld.get("side"))
            # Persist symbol for later lookups (used by _calculate_bracket_prices, _check_quick_profit etc.)
            try:
                self.symbol = pld.get("symbol") or getattr(
                    self, 'symbol', None)
            except Exception:
                # be defensive; symbol is optional
                pass

            if self.position_qty is None:
                self.position_qty = qty
                self.position_entry_price = price
                self.position_side = side or "BUY"
                self.position_open_ts = time.time()
                canonical = canonicalize_position_side(self.position_side)
                if canonical:
                    self._agg_side = canonical.value
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

        except Exception:
            self._metrics["fsm_errors_total"] += 1

    def _place_brackets(self, msg: Message, reason: str = "entry_fill") -> Optional[Message]:
        if self._aggregated_only_mode:
            if not self._is_aggregated_oco_enabled():
                raise RuntimeError(
                    "aggregated_only_mode requires aggregated_oco to be enabled"
                )
            return self._place_brackets_aggregated(msg, reason=reason)
        if self._is_aggregated_oco_enabled():
            return self._place_brackets_aggregated(msg, reason=reason)
        return self._place_brackets_legacy(msg)

    def _place_brackets_legacy(self, msg: Message) -> Optional[Message]:
        """Place SL and TP bracket orders after position opens."""
        if self._aggregated_only_mode:
            raise RuntimeError(
                "legacy bracket path called while aggregated-only mode is enabled"
            )

        if not self._prepare_for_bracket_placement():
            return None

        try:
            resolved_brackets = resolve_brackets_config(
                self.config, symbol=getattr(self, "symbol", None)
            )

            tick_size = self._resolve_tick_size()
            offset_bps = self._resolve_bracket_offset_bps(
                getattr(resolved_brackets, "offset_bps", None)
            )

            # Calculate bracket prices
            sl_price, tp_price = self._calculate_bracket_prices(
                resolved_brackets,
                tick_size=tick_size,
                offset_bps=offset_bps,
            )
            if sl_price is None or tp_price is None:
                self.state = ManageState.TRACKING
                LOG.warning(
                    "EXEC_POS_MANAGE_BRACKETS_PRICE_MISSING",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "why": "sl_tp_missing",
                    },
                )
                return None

            self.sl_price = sl_price
            self.tp_price = tp_price

            # === VALIDATION PHASE: Check SL/TP prices before submission ===
            # Get current mark price (prefer PriceService if available, fallback to entry price)
            current_mark = self.position_entry_price
            try:
                if self.price_service and getattr(self, 'symbol', None):
                    quote = self.price_service.get_current(
                        getattr(self, 'symbol', None))
                    # Quote may be a PriceQuote dataclass; prefer mark then last
                    q_mark = getattr(quote, 'mark', None)
                    q_last = getattr(quote, 'last', None)
                    if q_mark is not None:
                        current_mark = Decimal(str(q_mark))
                    elif q_last is not None:
                        current_mark = Decimal(str(q_last))
            except Exception:
                # Do not block bracket placement on price service errors
                pass
            if current_mark is None:
                self.state = ManageState.TRACKING
                return None

            # Convert BUY/SELL to LONG/SHORT for validation
            canonical_side = self._resolve_canonical_position_side()
            validation_side = (
                canonical_side.value
                if canonical_side != PositionSide.FLAT
                else (self.position_side or "LONG")
            )
            # Validate SL price
            is_sl_valid, sl_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=sl_price,
                is_take_profit=False,
            )
            if not is_sl_valid:
                self._metrics["fsm_bracket_validation_failed"] = self._metrics.get(
                    "fsm_bracket_validation_failed", 0) + 1
                self.state = ManageState.TRACKING
                LOG.warning(
                    "EXEC_POS_MANAGE_BRACKETS_SL_INVALID",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "reason": str(sl_reason),
                        "why": "sl_validation_failed",
                    },
                )
                return None

            # Validate TP price
            is_tp_valid, tp_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=tp_price,
                is_take_profit=True,
            )
            if not is_tp_valid:
                self._metrics["fsm_bracket_validation_failed"] = self._metrics.get(
                    "fsm_bracket_validation_failed", 0) + 1
                self.state = ManageState.TRACKING
                LOG.warning(
                    "EXEC_POS_MANAGE_BRACKETS_TP_INVALID",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "reason": str(tp_reason),
                        "why": "tp_validation_failed",
                    },
                )
                return None

            # Update stored prices
            self.sl_price = sl_price
            self.tp_price = tp_price
            self._metrics["fsm_bracket_offset_applied"] = self._metrics.get(
                "fsm_bracket_offset_applied", 0) + 1

            # Generate unique client order IDs (≤36 chars)
            _, sl_client_id, tp_client_id = self._build_sl_tp_client_ids(msg)

            # === EMISSION PHASE: Place validated bracket orders ===
            # Emit SL order
            sl_order = self._emit_place_order(
                msg,
                sl_client_id,
                "STOP_MARKET",
                self.position_side or "",
                str(self.position_qty),
                str(sl_price),
                "SL bracket",
            )

            # Emit TP order
            tp_order = self._emit_place_order(
                msg,
                tp_client_id,
                "LIMIT",
                self._get_opposite_side(),
                str(self.position_qty),
                str(tp_price),
                "TP bracket",
            )

            self._queue_decision(tp_order)

            self._metrics["fsm_bracket_orders_placed"] += 2
            return sl_order  # Return first order, second will be handled separately

        except Exception:
            LOG.exception(
                "EXEC_POS_MANAGE_BRACKETS_PLACE_FAILED",
                extra={
                    "symbol": getattr(self, "symbol", None),
                    "why": "legacy_brackets_exception",
                },
            )
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _prepare_for_bracket_placement(self) -> bool:
        """Common guard rails before emitting new bracket orders."""
        # PHASE A2: Anti-race check - skip if position is closing
        if self._closing_position:
            elapsed_s = time.time() - self._closing_position_ts
            if elapsed_s < (self._anti_race_close_ms / 1000.0):
                LOG.info(
                    "EXEC_POS_MANAGE_BRACKETS_SKIP_CLOSING_FLAG",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "elapsed_sec": round(elapsed_s, 4),
                        "anti_race_sec": round(self._anti_race_close_ms / 1000.0, 4),
                        "why": "closing_flag_active",
                    },
                )
                self.state = ManageState.TRACKING
                return False
            self._closing_position = False

        if self.sl_order_id or self.tp_order_id:
            LOG.info(
                "EXEC_POS_MANAGE_BRACKETS_CLEAR_PHANTOMS",
                extra={
                    "symbol": getattr(self, "symbol", None),
                    "sl_order_id": self.sl_order_id,
                    "tp_order_id": self.tp_order_id,
                    "why": "local_ids_present",
                },
            )
            self.sl_order_id = None
            self.tp_order_id = None

        if not self._should_place_brackets():
            self.state = ManageState.TRACKING
            LOG.debug(
                "EXEC_POS_MANAGE_BRACKETS_DISABLED",
                extra={
                    "symbol": getattr(self, "symbol", None),
                    "why": "should_place_false",
                },
            )
            return False

        return True

    def _place_brackets_aggregated(self, msg: Message, reason: str) -> Optional[Message]:
        if not self._prepare_for_bracket_placement():
            return None

        agg_why = self._map_reason_to_agg_why(reason)
        symbol = getattr(self, "symbol", None) or (msg.pld or {}).get("symbol")
        agg_oco_logger.info(
            "AGG_OCO_COMPUTE_BRACKETS_START",
            extra={
                "symbol": symbol,
                "reason": agg_why,
                "position_qty": str(self.position_qty),
                "position_side": self.position_side,
            },
        )
        try:
            levels = self._compute_aggregated_bracket_levels(reason=agg_why)
        except AggregatedOcoError as exc:
            import logging
            LOG = logging.getLogger(__name__)
            LOG.warning(
                "[BRK][agg] failed to compute aggregated brackets: %s", exc)
            self.state = ManageState.TRACKING
            self._metrics["fsm_errors_total"] += 1
            return None
        except Exception:
            agg_oco_logger.exception(
                "AGG_OCO_COMPUTE_FAILED",
                extra={
                    "symbol": symbol,
                    "position_qty": str(self.position_qty),
                    "position_side": self.position_side,
                    "reason": agg_why,
                },
            )
            self.state = ManageState.TRACKING
            self._metrics["fsm_errors_total"] += 1
            return None

        # EP-STAB-LIVEPOS-FIX-AGG: Handle None from _compute_aggregated_bracket_levels
        # (returned when entry_price not ready instead of raising AggregatedOcoError)
        if levels is None:
            self.state = ManageState.TRACKING
            return None

        canonical_side = self._resolve_canonical_position_side()
        if canonical_side == PositionSide.FLAT:
            raise AggregatedOcoError(
                "Cannot place aggregated brackets while flat")

        tick_size = self._resolve_tick_size()
        offset_bps = self._resolve_bracket_offset_bps(None)
        if self.position_entry_price is None:
            raise AggregatedOcoError(
                "position_entry_price is required for bracket placement")

        adjusted_sl, adjusted_tp = self._apply_shared_bracket_math(
            entry_price=self.position_entry_price,
            raw_sl_price=Decimal(str(levels.sl_price)),
            raw_tp_price=Decimal(str(levels.tp_price)),
            tick_size=tick_size,
            offset_bps=offset_bps,
            entry_side=canonical_side,
        )
        levels = AggregatedBracketLevels(
            tp_price=adjusted_tp,
            sl_price=adjusted_sl,
            why=levels.why,
        )

        agg_oco_logger.info(
            "AGG_OCO_COMPUTE_BRACKETS_DONE",
            extra={
                "symbol": symbol,
                "reason": agg_why,
                "sl_price": str(getattr(levels, "sl_price", "")),
                "tp_price": str(getattr(levels, "tp_price", "")),
            },
        )

        return self._place_or_update_bracket_set_from_levels(msg, levels, reason)

    def _place_or_update_bracket_set_from_levels(
        self,
        msg: Message,
        levels,
        reason: str,
    ) -> Optional[Message]:
        if self.position_qty is None:
            self.state = ManageState.TRACKING
            return None

        try:
            agg_side = self._convert_position_side()
        except AggregatedOcoError:
            self.state = ManageState.TRACKING
            return None
        self._agg_side = agg_side

        sl_before = self.sl_price
        tp_before = self.tp_price
        qty_before = self.position_qty
        avg_before = self.position_entry_price
        action = self._map_reason_to_action(reason)

        # Ensure we track the new bracket prices
        self.sl_price = levels.sl_price
        self.tp_price = levels.tp_price
        self.state = ManageState.BRACKETS_PENDING

        self._pending_bracket_log = {
            "action": action,
            "position_qty_before": str(qty_before) if qty_before is not None else None,
            "position_qty_after": str(self.position_qty) if self.position_qty is not None else None,
            "avg_price_before": str(avg_before) if avg_before is not None else None,
            "avg_price_after": str(self.position_entry_price) if self.position_entry_price is not None else None,
            "sl_price_before": str(sl_before) if sl_before is not None else None,
            "sl_price_after": str(levels.sl_price) if levels.sl_price is not None else None,
            "tp_price_before": str(tp_before) if tp_before is not None else None,
            "tp_price_after": str(levels.tp_price) if levels.tp_price is not None else None,
            "why": self._clip_why(levels.why),
            "rid": getattr(msg, "rid", None),
        }

        base_client_id, sl_client_id, tp_client_id = self._build_sl_tp_client_ids(
            msg)
        self._current_bracket_set_id = base_client_id

        symbol = getattr(self, "symbol", None) or (msg.pld or {}).get("symbol")
        qty_value = self._coerce_abs_decimal(self.position_qty)
        guard_price = self._select_guard_price(levels)
        agg_oco_logger.info(
            "AGG_OCO_BEFORE_QTY_GUARD",
            extra={
                "symbol": symbol,
                "position_qty": str(qty_value),
                "guard_price": str(guard_price) if guard_price is not None else None,
                "reason": reason,
            },
        )
        qty_str = self._normalize_reduce_only_qty(
            symbol=symbol,
            qty=qty_value,
            price=guard_price,
            context=reason or "aggregated_brackets",
        )
        if qty_str is None:
            self.state = ManageState.TRACKING
            return None
        opposite_side = self._get_opposite_side()

        sl_order = self._emit_place_order(
            msg,
            sl_client_id,
            "STOP_MARKET",
            opposite_side,
            qty_str,
            str(levels.sl_price),
            levels.why,
        )

        tp_order = self._emit_place_order(
            msg,
            tp_client_id,
            "LIMIT",
            opposite_side,
            qty_str,
            str(levels.tp_price),
            levels.why,
        )
        self._queue_decision(tp_order)

        self._metrics["fsm_bracket_orders_placed"] += 2
        self._aggregated_last_place_ts = int(time.time() * 1000)
        return sl_order

    def _select_guard_price(self, levels) -> Optional[Decimal]:
        if not levels:
            return None
        prices = []
        for price in (getattr(levels, "sl_price", None), getattr(levels, "tp_price", None)):
            if price is None:
                continue
            try:
                prices.append(Decimal(str(price)))
            except (InvalidOperation, ValueError, TypeError):
                continue
        if not prices:
            return None
        return min(prices)

    def _normalize_reduce_only_qty(
        self,
        *,
        symbol: Optional[str],
        qty: Decimal,
        price: Optional[Decimal],
        context: str,
    ) -> Optional[str]:
        if not getattr(self, "_aggregated_only_mode", False):
            return str(qty)
        if not getattr(self, "_qty_guard", None):
            return str(qty)

        try:
            # Use ExecPosGatekeeper logic manually since evaluate() is missing
            # and check_entry() enforces cooldowns which we don't want for exits.
            specs = self._qty_guard._get_instrument_specs(
                symbol) if symbol else {}
            step_size = specs.get("step_size", Decimal("0.000001"))
            min_qty = specs.get("min_qty", Decimal("0.000001"))
            min_notional = specs.get("min_notional", Decimal("5"))

            qty_dec = abs(Decimal(str(qty)))
            rounded = self._qty_guard._round_to_step(qty_dec, step_size)

            if rounded < min_qty:
                return None

            if price is not None:
                price_dec = abs(Decimal(str(price)))
                if rounded * price_dec < min_notional:
                    return None

            return str(rounded)

        except (InvalidOperation, ValueError, TypeError, AttributeError):
            return str(qty)

    def _maybe_register_bracket_set(self) -> None:
        if not (self._order_guardian and self._is_aggregated_oco_enabled()):
            self._pending_bracket_log = None
            return
        if not self.sl_order_id and not self.tp_order_id:
            self._pending_bracket_log = None
            return

        symbol = getattr(self, "symbol", None)
        side = self.position_side
        if not symbol or not side:
            self._pending_bracket_log = None
            return

        agg_side = self._agg_side
        if not agg_side:
            canonical = self._resolve_canonical_position_side()
            if canonical != PositionSide.FLAT:
                agg_side = canonical.value
        if not agg_side:
            self._pending_bracket_log = None
            return

        bracket_set_id = self._current_bracket_set_id or self._build_fallback_bracket_set_id()
        register_extra = {
            "event_type": "AGG_OCO_REGISTER_BRACKET_SET_ATTEMPT",
            "symbol": symbol,
            "side": agg_side,
            "bracket_set_id": bracket_set_id,
            "sl_order_id": self.sl_order_id,
            "tp_order_id": self.tp_order_id,
            "has_pending_log": bool(self._pending_bracket_log),
        }
        agg_oco_logger.info(
            "AGG_OCO_REGISTER_BRACKET_SET_ATTEMPT", extra=register_extra)

        try:
            meta = self._order_guardian.register_bracket_set(
                bracket_set_id=bracket_set_id,
                symbol=symbol,
                side=agg_side,
                sl_order_id=self.sl_order_id,
                tp_order_id=self.tp_order_id,
                created_ts=time.time(),
            )
            self._current_bracket_meta = meta
            agg_oco_logger.info(
                "AGG_OCO_REGISTER_BRACKET_SET_DONE",
                extra={
                    "symbol": symbol,
                    "side": agg_side,
                    "bracket_set_id": getattr(meta, "bracket_set_id", bracket_set_id),
                    "version": getattr(meta, "version", None),
                    "sl_order_id": getattr(meta, "sl_order_id", self.sl_order_id),
                    "tp_order_id": getattr(meta, "tp_order_id", self.tp_order_id),
                },
            )
            self._log_bracket_set_event(meta, self._pending_bracket_log)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[BRK][agg] failed to register bracket set", exc_info=exc
            )
            agg_oco_logger.exception(
                "AGG_OCO_REGISTER_BRACKET_SET_FAILED",
                extra={
                    "symbol": symbol,
                    "side": agg_side,
                    "bracket_set_id": bracket_set_id,
                    "sl_order_id": self.sl_order_id,
                    "tp_order_id": self.tp_order_id,
                },
            )
            self._pending_bracket_log = None

    def _build_fallback_bracket_set_id(self) -> str:
        symbol = getattr(self, "symbol", "unknown") or "unknown"
        side = self.position_side or "SIDELESS"
        return f"{symbol}:{side}:{int(time.time() * 1000)}"

    def _clear_guardian_bracket_set(self, symbol: Optional[str], side: Optional[str]) -> None:
        if not (self._order_guardian and self._is_aggregated_oco_enabled()):
            return
        if not symbol or not side:
            return
        # Aggregated OCO side must already be canonical ("LONG"/"SHORT").
        try:
            self._order_guardian.clear_bracket_set_for_position(
                symbol=symbol,
                side=side,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[BRK][agg] failed to clear bracket set", exc_info=exc
            )

    @staticmethod
    def _map_reason_to_action(reason: Optional[str]) -> str:
        mapping = {
            "entry_fill": "create",
            "scale_in_fill": "recalc_scale_in",
            "partial_close_fill": "recalc_partial",
            "partial_close_unprotected": "recalc_manual_fix",
        }
        if not reason:
            return "create"
        return mapping.get(reason, reason)

    @staticmethod
    def _map_reason_to_agg_why(reason: Optional[str]) -> str:
        normalized = (reason or "").strip()
        mapping = {
            "entry_fill": "agg_first_entry",
            "scale_in_fill": "agg_recalc_scale_in",
            "partial_close_fill": "agg_recalc_partial_close",
            "partial_close_unprotected": "agg_recalc_partial_close",
            "snapshot_entry_fill": "agg_first_entry",
            "snapshot_scale_in": "agg_recalc_scale_in",
            "snapshot_partial_close": "agg_recalc_partial_close",
            "snapshot_recalc": "agg_recalc_partial_close",
        }
        if not normalized:
            return "agg_unknown"
        return mapping.get(normalized, normalized)

    @staticmethod
    def _clip_why(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        return str(value)[:80]

    def _log_bracket_set_event(self, meta: Any, context: Optional[Dict[str, Any]]) -> None:
        if not meta or context is None:
            self._pending_bracket_log = None
            return

        action = context.get("action") or "create"
        if getattr(meta, "version", 0) == 0 and action not in {"cleanup_full_close", "flip_reset"}:
            action = "create"

        extra = {
            "event_type": "AGG_OCO_BRACKET_SET_CHANGED",
            "symbol": getattr(meta, "symbol", None),
            "side": getattr(meta, "side", None),
            "bracket_set_id": getattr(meta, "bracket_set_id", None),
            "version": getattr(meta, "version", None),
            "action": action,
            "position_qty_before": context.get("position_qty_before"),
            "position_qty_after": context.get("position_qty_after"),
            "avg_price_before": context.get("avg_price_before"),
            "avg_price_after": context.get("avg_price_after"),
            "sl_price_before": context.get("sl_price_before"),
            "sl_price_after": context.get("sl_price_after"),
            "tp_price_before": context.get("tp_price_before"),
            "tp_price_after": context.get("tp_price_after"),
            "why": self._clip_why(context.get("why")),
            "rid": context.get("rid"),
        }

        agg_oco_logger.info("Aggregated OCO bracket set changed", extra=extra)
        self._pending_bracket_log = None

    def _ensure_position_entry_price(self, *, reason: str) -> bool:
        """Validate or recover entry price before aggregated bracket computation."""
        if self.position_entry_price is not None and self.position_entry_price > 0:
            return True

        symbol = getattr(self, "symbol", None)

        if self.price_service and symbol:
            try:
                quote = self.price_service.get_current(symbol)
                fallback_price = getattr(quote, "mark", None) or getattr(
                    quote, "last", None)
                if fallback_price is not None:
                    val = Decimal(str(fallback_price))
                    if val > 0:
                        self.position_entry_price = val
                        self._metrics["agg_entry_price_recovered_from_price_service"] = (
                            self._metrics.get(
                                "agg_entry_price_recovered_from_price_service", 0
                            )
                            + 1
                        )
                        agg_oco_logger.info(
                            "AGG_OCO_ENTRY_PRICE_RECOVERED",
                            extra={
                                "symbol": symbol,
                                "price": str(val),
                                "source": "price_service_fallback",
                                "event_type": "AGG_OCO_ENTRY_PRICE_RECOVERED",
                            },
                        )
                        return True
            except Exception as exc:
                agg_oco_logger.warning(
                    "AGG_OCO_ENTRY_PRICE_FALLBACK_FAILED",
                    extra={
                        "symbol": symbol,
                        "error": repr(exc),
                        "event_type": "AGG_OCO_ENTRY_PRICE_FALLBACK_FAILED",
                    },
                )

        self._metrics["agg_entry_price_not_ready"] += 1
        agg_oco_logger.warning(
            "AGG_OCO_ENTRY_PRICE_NOT_READY",
            extra={
                "symbol": symbol,
                "qty": str(self.position_qty) if self.position_qty else None,
                "entry_price": str(self.position_entry_price) if self.position_entry_price is not None else None,
                "side": self.position_side,
                "reason": reason,
                "source": "missing_entry_price_after_fallback",
                "event_type": "AGG_OCO_ENTRY_PRICE_NOT_READY",
            }
        )
        return False

    def _compute_aggregated_bracket_levels(self, *, reason: str):
        # EP-STAB-LIVEPOS-FIX-AGG: Guard against invalid entry_price before calling aggregator
        # If entry_price is None or <= 0, aggregator will fail with "avg_entry_price must be > 0"
        # Instead, log warning and return None to avoid DECISION_EXECUTION_FAILED
        if not self._ensure_position_entry_price(reason=reason):
            # Return None instead of raising error - caller will handle gracefully
            return None

        if self.position_qty is None or self.position_side is None:
            raise AggregatedOcoError("position snapshot is incomplete")

        resolved = resolve_brackets_config(
            self.config, symbol=getattr(self, "symbol", None)
        )

        sl_bps = Decimal(str(resolved.sl_bps))
        tp_bps = Decimal(str(resolved.tp_bps))
        if sl_bps <= 0:
            raise AggregatedOcoError("sl_bps must be > 0 for aggregated OCO")

        sl_pct = sl_bps / Decimal("10000")
        tp_rr = tp_bps / sl_bps if tp_bps > 0 else Decimal("1")

        risk_cfg = AggregatedOcoRiskConfig(
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        constraints = self._get_instrument_constraints()
        side = self._convert_position_side()

        return compute_aggregated_brackets(
            position_amt=abs(self.position_qty),
            avg_entry_price=self.position_entry_price,
            side=side,
            risk_cfg=risk_cfg,
            constraints=constraints,
            why=reason,
        )

    def _resolve_tick_size(self) -> Decimal:
        tick_size = self._lookup_instrument_value("tick_size")
        symbol = getattr(self, "symbol", None)
        if tick_size is None or tick_size <= 0:
            logging.getLogger(__name__).error(
                "EXEC_POS_MANAGE_TICKSIZE_MISSING",
                extra={
                    "symbol": symbol,
                    "rid": self.rid,
                    "event_type": "EXEC_POS_MANAGE_TICKSIZE_MISSING",
                },
            )
            raise ValueError(
                f"tick_size missing for symbol {symbol or 'UNKNOWN'}")
        return tick_size

    def _resolve_bracket_offset_bps(self, fallback: Optional[Decimal]) -> Decimal:
        symbol = getattr(self, "symbol", None)
        offset_candidate = self._lookup_instrument_value("bracket_offset_bps")
        if offset_candidate is None and fallback is not None:
            try:
                offset_candidate = Decimal(str(fallback))
            except (InvalidOperation, TypeError, ValueError):
                offset_candidate = None

        if offset_candidate is None or offset_candidate <= 0:
            default_offset = Decimal("5")
            logging.getLogger(__name__).warning(
                "EXEC_POS_BRACKET_OFFSET_DEFAULT_USED",
                extra={
                    "symbol": symbol,
                    "rid": self.rid,
                    "default_bps": str(default_offset),
                    "event_type": "EXEC_POS_BRACKET_OFFSET_DEFAULT_USED",
                },
            )
            return default_offset

        return Decimal(offset_candidate)

    def _get_instrument_constraints(self) -> InstrumentPriceConstraints:
        tick_size = self._resolve_tick_size()
        min_price = self._lookup_instrument_value("min_price")
        if min_price is None or min_price <= 0:
            min_price = tick_size
        return InstrumentPriceConstraints(
            tick_size=tick_size,
            min_price=min_price,
        )

    def _lookup_instrument_value(self, field: str) -> Optional[Decimal]:
        symbol = getattr(self, "symbol", None)
        if not symbol:
            return None

        trading_cfg = getattr(self.config, "trading", None)
        if trading_cfg:
            instruments = getattr(trading_cfg, "instruments", None)
            if hasattr(instruments, "model_dump"):
                instruments = instruments.model_dump()
            value = self._extract_instrument_field(instruments, symbol, field)
            dec_value = self._coerce_decimal_value(value)
            if dec_value is not None:
                return dec_value

        if isinstance(self.config, dict):
            instruments = self.config.get("trading", {}).get("instruments", {})
            value = self._extract_instrument_field(instruments, symbol, field)
            dec_value = self._coerce_decimal_value(value)
            if dec_value is not None:
                return dec_value

        return None

    @staticmethod
    def _extract_instrument_field(source: Any, symbol: str, field: str) -> Any:
        if not source or symbol not in source:
            return None
        sym_cfg = source.get(symbol)
        if isinstance(sym_cfg, dict):
            return sym_cfg.get(field)
        try:
            return getattr(sym_cfg, field)
        except Exception:
            return None

    @staticmethod
    def _coerce_decimal_value(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_order_side(raw_side: Optional[str]) -> Optional[str]:
        if raw_side is None:
            return None
        normalized = str(raw_side).strip().upper()
        if normalized in {"BUY", "SELL"}:
            return normalized
        canonical = canonicalize_position_side(normalized)
        if canonical == PositionSide.LONG:
            return "BUY"
        if canonical == PositionSide.SHORT:
            return "SELL"
        return None

    def _resolve_canonical_position_side(self) -> PositionSide:
        """Determine canonical position side using agg hints, side strings, or qty."""

        if self._agg_side:
            agg_canonical = canonicalize_position_side(self._agg_side)
            if agg_canonical:
                return agg_canonical

        if self.position_side:
            canonical = canonicalize_position_side(self.position_side)
            if canonical:
                return canonical

        return canonicalize_position_side_from_qty(self.position_qty)

    def _convert_position_side(self) -> str:
        canonical = self._resolve_canonical_position_side()
        if canonical == PositionSide.FLAT:
            raise AggregatedOcoError(
                "Cannot compute aggregated brackets while flat"
            )
        return canonical.value

    def _is_aggregated_oco_enabled(self) -> bool:
        try:
            return bool(self._manage_config().brackets.aggregated_oco.enabled)
        except Exception:
            return False

    def _handle_aggregated_fill_event(self, msg: Message) -> Optional[Message]:
        agg_cfg = self._manage_config().brackets.aggregated_oco
        pld = msg.pld or {}
        symbol = pld.get("symbol") or getattr(self, "symbol", None)

        qty_value = (
            pld.get("qty")
            if pld.get("qty") is not None
            else pld.get("quantity")
        )
        if qty_value is None:
            return None

        try:
            fill_qty = Decimal(str(qty_value))
        except (InvalidOperation, ValueError, TypeError):
            return None

        if fill_qty <= 0:
            return None

        from .contracts import is_exit_order
        is_exit_fill = is_exit_order(pld)

        agg_oco_logger.info(
            "🎯 AGG_FILL_EVENT_ENTRY",
            extra={
                "symbol": getattr(self, "symbol", None),
                "verb": msg.verb,
                "position_qty": str(self.position_qty) if self.position_qty is not None else None,
                "aggregated_only_mode": self._aggregated_only_mode,
                "fill_qty": str(fill_qty),
                "is_exit_fill": is_exit_fill,
            }
        )

        agg_oco_logger.info(
            "AGG_OCO_HANDLE_FILL",
            extra={
                "symbol": symbol,
                "fill_qty": str(fill_qty),
                "fill_price": str(pld.get("price") or pld.get("avg_price") or ""),
                "is_exit_fill": is_exit_fill,
                "source": pld.get("source") or msg.src,
            },
        )

        if self._aggregated_only_mode:
            return self._handle_aggregated_fill_event_aggregated_only(
                msg=msg,
                agg_cfg=agg_cfg,
                fill_qty=fill_qty,
                is_exit_fill=is_exit_fill,
            )

        return self._handle_aggregated_fill_event_default(
            msg=msg,
            agg_cfg=agg_cfg,
            fill_qty=fill_qty,
            is_exit_fill=is_exit_fill,
        )

    def _handle_aggregated_fill_event_default(
        self,
        *,
        msg: Message,
        agg_cfg: AggregatedOcoConfig,
        fill_qty: Decimal,
        is_exit_fill: bool,
    ) -> Optional[Message]:
        if is_exit_fill:
            remaining = self._apply_exit_fill(fill_qty)
            if remaining is None:
                return None

            symbol = getattr(self, "symbol", None)
            canonical = self._resolve_canonical_position_side()
            agg_side = canonical.value if canonical != PositionSide.FLAT else None

            if remaining == 0:
                self._clear_position_state()
                return None

            # Partial close: clear old bracket set metadata before recalc
            self._clear_guardian_bracket_set(symbol, agg_side)

            if agg_cfg.recalc_on_partial_close:
                return self._recalc_aggregated_brackets(msg, reason="partial_close_fill")
            if self._needs_bracket_recalc_after_partial_close(agg_cfg):
                return self._recalc_aggregated_brackets(
                    msg,
                    reason="partial_close_unprotected",
                )
            return None

        was_open = self.position_qty is not None
        self._on_fill(msg)
        if was_open and agg_cfg.recalc_on_scale_in:
            # Scale-in: clear old bracket set metadata before recalc
            symbol = getattr(self, "symbol", None)
            canonical = self._resolve_canonical_position_side()
            agg_side = canonical.value if canonical != PositionSide.FLAT else None
            self._clear_guardian_bracket_set(symbol, agg_side)
            return self._recalc_aggregated_brackets(msg, reason="scale_in_fill")
        return None

    def _handle_aggregated_fill_event_aggregated_only(
        self,
        *,
        msg: Message,
        agg_cfg: AggregatedOcoConfig,
        fill_qty: Decimal,
        is_exit_fill: bool,
    ) -> Optional[Message]:
        agg_oco_logger.info(
            "🎯 AGG_ONLY_HANDLER_ENTRY",
            extra={
                "symbol": getattr(self, "symbol", None),
                "fill_qty": str(fill_qty),
                "is_exit_fill": is_exit_fill,
            }
        )

        raw_snapshot = self._get_live_position_state()
        if raw_snapshot is None:
            agg_oco_logger.error(
                "[BRK][agg] live snapshot missing; falling back to local state",
                extra={
                    "event_type": "AGG_OCO_LIVE_SNAPSHOT_MISSING",
                    "symbol": getattr(self, "symbol", None),
                    "reason": "missing_live_snapshot",
                },
            )
            return self._handle_aggregated_fill_event_default(
                msg=msg,
                agg_cfg=agg_cfg,
                fill_qty=fill_qty,
                is_exit_fill=is_exit_fill,
            )

        # Attempt to parse as active position using unified contract
        snapshot = PositionSnapshot.from_generic_payload(raw_snapshot)

        # Check for zero quantity (FLAT) manually if snapshot is None
        # because PositionSnapshot returns None for zero qty.
        is_flat = False
        if snapshot is None:
            # Check if it's actually zero qty
            q = raw_snapshot.get("qty") or raw_snapshot.get(
                "position_amt") or raw_snapshot.get("position_amount")
            try:
                if q is not None and abs(float(q)) < 1e-8:
                    is_flat = True
            except Exception:
                pass

            if not is_flat:
                # It's invalid or missing data, not just flat
                agg_oco_logger.error(
                    "[BRK][agg] live snapshot unparsable",
                    extra={
                        "event_type": "AGG_OCO_LIVE_SNAPSHOT_INVALID",
                        "symbol": raw_snapshot.get("symbol"),
                        "raw_snapshot": str(raw_snapshot)[:200],
                    },
                )
                return self._handle_aggregated_fill_event_default(
                    msg=msg,
                    agg_cfg=agg_cfg,
                    fill_qty=fill_qty,
                    is_exit_fill=is_exit_fill,
                )

        symbol = raw_snapshot.get("symbol") or getattr(self, "symbol", None)
        if symbol:
            self.symbol = symbol

        # Handle FLAT case
        if is_flat:
            # CRITICAL FIX: If we just got an ENTRY fill, but snapshot says 0,
            # it means snapshot is stale or racing. Do NOT exit silently.
            if not is_exit_fill and fill_qty > 0:
                agg_oco_logger.warning(
                    "[BRK][agg] live snapshot reports flat position BUT entry fill received; forcing fallback",
                    extra={
                        "event_type": "AGG_OCO_SNAPSHOT_STALE_RACE",
                        "symbol": symbol,
                        "fill_qty": str(fill_qty),
                        "snapshot_qty": "0",
                    },
                )
        avg_price_raw = raw_snapshot.get(
            "avg_price") or raw_snapshot.get("entryPrice")
        if avg_price_raw:
            try:
                val = Decimal(str(avg_price_raw))
                if val > 0:
                    self.position_entry_price = val
            except:
                pass

        # EP-STAB-LIVEPOS-FIX-AGG: Fallback for missing entry price in snapshot
        # If snapshot has 0/None price (e.g. REST timeout), try to use fill price or PriceService
        if self.position_entry_price is None or self.position_entry_price <= 0:
            # 1. Try fill price from message
            pld = msg.pld or {}
            fill_price = pld.get("price") or pld.get("avg_price")
            if fill_price:
                try:
                    val = Decimal(str(fill_price))
                    if val > 0:
                        self.position_entry_price = val
                        agg_oco_logger.warning(
                            "[BRK][agg] snapshot missing entry_price; using fill price",
                            extra={"symbol": symbol, "fill_price": str(val)}
                        )
                except:
                    pass

            # 2. Try PriceService mark price if still missing
            if (self.position_entry_price is None or self.position_entry_price <= 0) and self.price_service:
                try:
                    quote = self.price_service.get_current(symbol)
                    mark = getattr(quote, 'mark', None)
                    if mark:
                        val = Decimal(str(mark))
                        if val > 0:
                            self.position_entry_price = val
                            agg_oco_logger.warning(
                                "[BRK][agg] snapshot missing entry_price; using mark price",
                                extra={"symbol": symbol,
                                       "mark_price": str(val)}
                            )
                except:
                    pass

        # Map PositionSide to "BUY"/"SELL" string for FSM compatibility
        self.position_side = "BUY" if snapshot.side == PositionSide.LONG else "SELL"
        self._agg_side = snapshot.side.value

        # Determine reason
        reason = "snapshot_recalc"
        if abs(prev_qty) < 1e-8:
            reason = "snapshot_entry_fill"
        elif snapshot.qty > abs(prev_qty):
            reason = "snapshot_scale_in"
        elif snapshot.qty < abs(prev_qty):
            reason = "snapshot_partial_close"

        agg_oco_logger.info(
            "[BRK][agg] live snapshot recalc",
            extra={
                "event_type": "AGG_OCO_LIVE_SNAPSHOT_RECALC",
                "symbol": symbol,
                "reason": reason,
                "prev_qty": str(prev_qty),
                "new_qty": str(snapshot.qty),
                "snapshot_source": raw_snapshot.get("source"),
                "snapshot_ts": raw_snapshot.get("updated_ts"),
            },
        )

        agg_oco_logger.info(
            "✅ CALLING _compute_aggregated_brackets",
            extra={
                "symbol": symbol,
                "live_qty": str(snapshot.qty),
                "order_side": self.position_side,
            }
        )
        return self._recalc_aggregated_brackets(msg, reason=reason)

    def _needs_bracket_recalc_after_partial_close(self, agg_cfg) -> bool:
        if agg_cfg.allow_unprotected_position:
            return False
        if self.position_qty is None or self.position_qty == 0:
            return False
        # Require both SL and TP ids so Guardian can protect the set.
        return (self.sl_order_id is None) or (self.tp_order_id is None)

    def _apply_exit_fill(self, fill_qty: Decimal) -> Optional[Decimal]:
        if self.position_qty is None:
            return None

        remaining = self.position_qty - abs(fill_qty)
        if remaining <= 0:
            self.position_qty = None
            return Decimal("0")

        self.position_qty = remaining
        return remaining

    def _clear_position_state(self) -> None:
        symbol = getattr(self, "symbol", None)
        canonical = self._resolve_canonical_position_side()
        agg_side = canonical.value if canonical != PositionSide.FLAT else None
        cleanup_context = {
            "action": "cleanup_full_close",
            "position_qty_before": str(self.position_qty) if self.position_qty is not None else None,
            "position_qty_after": "0",
            "avg_price_before": str(self.position_entry_price) if self.position_entry_price is not None else None,
            "avg_price_after": None,
            "sl_price_before": str(self.sl_price) if self.sl_price is not None else None,
            "sl_price_after": None,
            "tp_price_before": str(self.tp_price) if self.tp_price is not None else None,
            "tp_price_after": None,
            "why": self._clip_why("cleanup_full_close"),
            "rid": None,
        }
        self._log_bracket_set_event(
            self._current_bracket_meta, cleanup_context)
        self.position_qty = None
        self.position_entry_price = None
        self.position_side = None
        self.position_open_ts = 0.0
        self.sl_order_id = None
        self.tp_order_id = None
        self.sl_price = None
        self.tp_price = None
        self._current_bracket_set_id = None
        self._current_bracket_meta = None
        self._aggregated_last_place_ts = 0
        self._agg_side = None
        self.state = ManageState.FLAT
        self._clear_guardian_bracket_set(symbol, agg_side)

    def _cancel_active_brackets(self, msg: Message, reason: str) -> None:
        """Cancel currently active SL/TP brackets."""
        if self.sl_order_id:
            self._queue_decision(Message(
                op="DEC",
                verb="CANCEL_ORDER",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                pld={"symbol": getattr(self, "symbol", None),
                     "orderId": self.sl_order_id},
                why=f"{reason}_cancel_sl",
            ))
        if self.tp_order_id:
            self._queue_decision(Message(
                op="DEC",
                verb="CANCEL_ORDER",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                pld={"symbol": getattr(self, "symbol", None),
                     "orderId": self.tp_order_id},
                why=f"{reason}_cancel_tp",
            ))
        # Clear IDs immediately to avoid race conditions in logic
        self.sl_order_id = None
        self.tp_order_id = None

    def _recalc_aggregated_brackets(self, msg: Message, *, reason: str) -> Optional[Message]:
        agg_cfg = self._manage_config().brackets.aggregated_oco
        now_ms = int(time.time() * 1000)
        ttl_ms = max(int(agg_cfg.ttl_protect_new_bracket_ms or 0), 0)

        # FIX: Detect auto-heal context to bypass TTL
        # Auto-heal sends why="watchdog_autoheal_no_sl"
        is_auto_heal = (msg.why == "watchdog_autoheal_no_sl") or (
            "autoheal" in reason)

        if not is_auto_heal and self._aggregated_last_place_ts and ttl_ms > 0:
            elapsed = now_ms - self._aggregated_last_place_ts
            if elapsed < ttl_ms:
                if agg_cfg.allow_unprotected_position or (
                    self.sl_order_id or self.tp_order_id
                ):
                    import logging

                    LOG = logging.getLogger(__name__)
                    LOG.info(
                        "[BRK][agg] skip recalc reason=%s elapsed=%sms ttl=%sms",
                        reason,
                        elapsed,
                        ttl_ms,
                    )
                    return None

        # FIX: Cancel existing brackets before placing new ones to avoid duplication
        if self.sl_order_id or self.tp_order_id:
            self._cancel_active_brackets(msg, reason)

        return self._place_brackets_aggregated(msg, reason=reason)

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        brackets_cfg = self._manage_config().brackets
        return bool(brackets_cfg.enable)

    def _calculate_bracket_prices(
        self,
        resolved: ResolvedBrackets,
        *,
        tick_size: Decimal,
        offset_bps: Decimal,
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculate SL and TP prices based on config and position.

        Supports both NEW and LEGACY config keys:
        - NEW: execution.manage.brackets.sl.fixed_bps, execution.manage.brackets.tp.fixed_bps
        - LEGACY: execution.manage.brackets.stop_loss_bps, take_profit_low_ratio, take_profit_high_ratio

        Fallback chain:
        1. Try new keys (sl.fixed_bps, tp.fixed_bps)
        2. If not found, fallback to legacy keys for backward compatibility
        """
        if self.position_entry_price is None or self.position_side is None:
            return None, None

        try:
            entry_price = self.position_entry_price

            canonical_side = self._resolve_canonical_position_side()
            if canonical_side == PositionSide.FLAT:
                return None, None

            sl_bps = Decimal(str(resolved.sl_bps))
            tp_bps = Decimal(str(resolved.tp_bps))

            if canonical_side == PositionSide.LONG:
                raw_sl = entry_price * \
                    (Decimal("1") - sl_bps / Decimal("10000"))
                raw_tp = entry_price * \
                    (Decimal("1") + tp_bps / Decimal("10000"))
            else:
                raw_sl = entry_price * \
                    (Decimal("1") + sl_bps / Decimal("10000"))
                raw_tp = entry_price * \
                    (Decimal("1") - tp_bps / Decimal("10000"))

            sl_price, tp_price = self._apply_shared_bracket_math(
                entry_price=entry_price,
                raw_sl_price=raw_sl,
                raw_tp_price=raw_tp,
                tick_size=tick_size,
                offset_bps=offset_bps,
                entry_side=canonical_side,
            )

            return sl_price, tp_price
        except (AttributeError, TypeError, ValueError):
            return None, None

    def _apply_shared_bracket_math(
        self,
        *,
        entry_price: Decimal,
        raw_sl_price: Decimal,
        raw_tp_price: Decimal,
        tick_size: Decimal,
        offset_bps: Decimal,
        entry_side: PositionSide,
    ) -> tuple[Decimal, Decimal]:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive for bracket math")
        if tick_size <= 0:
            raise ValueError("tick_size must be positive for bracket math")

        sl_price = self._round_price_to_tick(raw_sl_price, tick_size)
        tp_price = self._round_price_to_tick(raw_tp_price, tick_size)

        entry_side_token = "BUY" if entry_side == PositionSide.LONG else "SELL"

        sl_offset = TPSLValidationRules.add_safety_offset(
            sl_price, tick_size, offset_bps
        )
        tp_offset = TPSLValidationRules.add_safety_offset(
            tp_price, tick_size, offset_bps
        )

        if entry_side_token == "BUY":
            sl_price = sl_price - sl_offset
            tp_price = tp_price + tp_offset
        else:
            sl_price = sl_price + sl_offset
            tp_price = tp_price - tp_offset

        if sl_price <= 0 or tp_price <= 0:
            raise ValueError(
                "Bracket prices must remain positive after adjustments")

        return sl_price, tp_price

    @staticmethod
    def _round_price_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
        ticks = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
        rounded = ticks * tick_size
        if rounded <= 0:
            raise ValueError("Rounded price must be positive")
        return rounded

    def _get_opposite_side(self) -> str:
        """Get opposite side for closing position."""
        canonical = self._resolve_canonical_position_side()
        if canonical == PositionSide.SHORT:
            return "BUY"
        if canonical == PositionSide.LONG:
            return "SELL"
        current = str(self.position_side or "").upper()
        return "SELL" if current == "BUY" else "BUY"

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
        brackets_meta = self._manage_config().brackets
        working_type = brackets_meta.working_type_default or "MARK_PRICE"
        price_protect = bool(brackets_meta.price_protect)

        normalized_order_type = str(order_type or "").upper()
        # Build payload
        payload = {
            "symbol": msg.pld.get("symbol", ""),
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "price": price if normalized_order_type == "LIMIT" else None,
            "stopPrice": price if ("STOP" in normalized_order_type or "TAKE_PROFIT" in normalized_order_type) else None,
            "reduceOnly": True,
            "newClientOrderId": client_id,
            "workingType": working_type,
            "priceProtect": price_protect,
        }

        # For STOP_MARKET/TAKE_PROFIT_MARKET with closePosition=true, don't send qty
        if "STOP" in normalized_order_type and normalized_order_type != "STOP_LOSS" and getattr(self, 'closePosition', False):
            # Remove qty for close-position orders (Binance manages qty automatically)
            payload.pop("qty", None)

        try:
            canonical_side = self._resolve_canonical_position_side()
            if canonical_side and canonical_side != PositionSide.FLAT:
                payload["positionSide"] = canonical_side.value
                payload["position_side"] = canonical_side.value
        except Exception:
            pass

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

    def _queue_decision(self, decision: Optional[Message]) -> None:
        """Buffer secondary decisions so ExecPosFSM can drain them later."""
        if decision is None:
            return
        self._pending_decisions.append(decision)

    def consume_pending_decisions(self) -> List[Message]:
        """Return and clear buffered DEC messages emitted in the same handle pass."""
        if not self._pending_decisions:
            return []
        buffered = list(self._pending_decisions)
        self._pending_decisions.clear()
        return buffered

    def _on_bracket_placed(self, msg: Message) -> Optional[Message]:
        """Handle bracket order placement confirmation."""
        pld = msg.pld or {}
        client_order_id = pld.get("clientOrderId")
        order_id = pld.get("orderId")

        if client_order_id and order_id:
            meta = parse_client_order_id(client_order_id)
            if meta and meta.intent == ClientOrderIntent.STOP_LOSS:
                self.sl_order_id = order_id
            elif meta and meta.intent == ClientOrderIntent.TAKE_PROFIT:
                self.tp_order_id = order_id

            # Check if both brackets are placed
            if self.sl_order_id and self.tp_order_id:
                self.state = ManageState.BRACKETS_PLACED
                LOG.info(
                    "EXEC_POS_MANAGE_BRACKETS_CONFIRMED",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "sl_order_id": self.sl_order_id,
                        "tp_order_id": self.tp_order_id,
                        "why": "both_brackets_ack",
                    },
                )
                self._maybe_register_bracket_set()

        return None

    def _check_quick_profit(self, msg: Message) -> Optional[Message]:
        """PRIORITY CHECK: Close position if quick profit target reached.

        Returns DEC:CLOSE if threshold hit, otherwise None.
        """
        if not self.quick_profit_enabled:
            return None

        if self.position_qty is None or self.position_entry_price is None:
            return None

        try:
            # Prefer PriceService if available
            current_price = None
            try:
                if self.price_service and getattr(self, 'symbol', None):
                    quote = self.price_service.get_current(
                        getattr(self, 'symbol', None))
                    # Prefer mark, then last, then mid
                    current_price = getattr(quote, 'mark', None) or getattr(
                        quote, 'last', None) or getattr(quote, 'mid', None)
            except Exception:
                # On any price service error, fallback to payload
                current_price = None

            if current_price is None:
                pld = msg.pld or {}
                current_price = pld.get('mark_price') or pld.get(
                    'last_price') or pld.get('price')
            if current_price is None:
                return None
            current_price_dec = Decimal(str(current_price))

            if self.position_side == 'BUY':
                pnl_per_unit = current_price_dec - self.position_entry_price
            else:
                pnl_per_unit = self.position_entry_price - current_price_dec

            total_pnl_usd = pnl_per_unit * abs(self.position_qty)
            # If using percentage mode, target may be relative; only fixed_usd supported now
            if total_pnl_usd >= self.quick_profit_target_usd:
                LOG.info(
                    "EXEC_POS_MANAGE_QUICK_PROFIT_HIT",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "pnl_usd": str(total_pnl_usd),
                        "target_usd": str(self.quick_profit_target_usd),
                        "why": "quick_profit_rule",
                    },
                )
                # Emit close decision - do not cancel brackets here; ExecPosFSM will do cleanup
                details = {
                    'rule': 'quick_profit',
                    'pnl_usd': str(total_pnl_usd),
                    'current_price': str(current_price_dec),
                    'target_usd': str(self.quick_profit_target_usd)
                }
                return self._emit_close(msg, 'QUICK_PROFIT_HIT', details)
        except Exception:
            self._metrics['fsm_errors_total'] = self._metrics.get(
                'fsm_errors_total', 0) + 1
        return None

    def _check_rules(self, msg: Message) -> Optional[Message]:
        """
        Check management rules: brackets, trailing stop, breakeven, time_stop.

        Returns:
            DEC:PLACE_ORDER, DEC:CANCEL_ORDER, or DEC:ADJUST if rule triggers, None otherwise.
        """
        if (
            self._is_aggregated_oco_enabled()
            and msg.op == "EVT"
            and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED")
        ):
            agg_decision = self._handle_aggregated_fill_event(msg)
            if agg_decision:
                return agg_decision

        # FIX: Handle legacy close fills (non-aggregated mode) to ensure state reset
        if (
            not self._is_aggregated_oco_enabled()
            and msg.op == "EVT"
            and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED")
        ):
            pld = msg.pld or {}
            from .contracts import is_exit_order
            if is_exit_order(pld):
                qty_value = pld.get("qty") if pld.get(
                    "qty") is not None else pld.get("quantity")
                if qty_value:
                    try:
                        fill_qty = Decimal(str(qty_value))
                        remaining = self._apply_exit_fill(fill_qty)
                        if remaining is not None and remaining <= 0:
                            LOG.info(
                                "EXEC_POS_MANAGE_LEGACY_CLOSE_FILL",
                                extra={
                                    "symbol": getattr(self, "symbol", None),
                                    "why": "legacy_exit_state_reset",
                                },
                            )
                            self._clear_position_state()
                            return None
                    except Exception:
                        pass

        if self.position_qty is None or self.position_entry_price is None:
            return None

        # PRIORITY: Quick profit rule (highest priority)
        try:
            if self.quick_profit_enabled and self.quick_profit_priority == 'highest':
                qp = self._check_quick_profit(msg)
                if qp:
                    return qp
        except Exception:
            # Do not block other rules if quick_profit check fails
            self._metrics['fsm_errors_total'] = self._metrics.get(
                'fsm_errors_total', 0) + 1

        try:
            emergency_cfg = self._manage_config().emergency
            emergency_enabled = emergency_cfg.enabled
            emergency_sl_bps = emergency_cfg.sl_bps
        except Exception:
            emergency_enabled = False
            emergency_sl_bps = Decimal("100")

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
                                msg.pld or {}).get("ts") else int(time.time() * 1000)
                        except Exception:
                            now_ts = int(time.time() * 1000)
                        bar_index = now_ts // getattr(self,
                                                      "_bar_ms", 900000)
                        self._wait_mode_until_ts = (
                            bar_index + getattr(self, "_wait_mode_bars", 2)) * getattr(self, "_bar_ms", 900000)
                        self.state = ManageState.WAIT_MODE
                        new_sl = (self.position_entry_price * (Decimal("1") - sl_em_bps / Decimal("10000"))) if self.position_side == "BUY" else (
                            self.position_entry_price * (Decimal("1") + sl_em_bps / Decimal("10000")))
                        symbol_ref = getattr(self, "symbol", None) or (
                            msg.pld or {}).get("symbol")
                        rid_val = getattr(msg, "rid", None)
                        decision_ref = (msg.pld or {}).get(
                            "orderId") or getattr(msg, "id", None)
                        emergency_meta = build_client_order_id(
                            intent=ClientOrderIntent.STOP_LOSS,
                            rid=str(rid_val) if rid_val else None,
                            symbol=str(symbol_ref) if symbol_ref else None,
                            decision_id=str(
                                decision_ref) if decision_ref else None,
                            extra="emergency_sl",
                            max_len=self.CLIENT_ORDER_ID_MAX_LEN,
                        )
                        emergency_client_id = emergency_meta.raw
                        return self._emit_place_order(
                            msg,
                            client_id=emergency_client_id,
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

        # Handle trailing stop
        if msg.op == "UPD" and msg.verb == "MARKET_DATA":
            trailing_action = self._check_trailing_stop(msg)
            if trailing_action:
                return trailing_action

        try:
            now = time.time()
            elapsed = now - self.position_open_ts

            # Rule 1: Trail (stub: check if current price > entry + trail_pct%)
            pld = msg.pld or {}
            current_price = pld.get("price")
            if current_price is not None:
                current_price_dec = Decimal(str(current_price))
                trail_trigger = self.position_entry_price * (
                    1 + Decimal(str(self.trail_pct / 100))
                )

                if current_price_dec > trail_trigger:
                    return self._emit_adjust(
                        msg,
                        "ADJUST_TRAIL",
                        {"rule": "trail", "trigger_price": str(
                            trail_trigger)},
                    )

            # Rule 2: Breakeven (stub: move SL to BE after X seconds)
            if elapsed > self.breakeven_after_sec:
                return self._emit_adjust(
                    msg, "ADJUST_BE", {
                        "rule": "breakeven", "elapsed_sec": elapsed}
                )

            # Rule 3: Time stop (stub: close after 3600 sec)
            if elapsed > 3600:
                return self._emit_adjust(
                    msg, "ADJUST_TIME", {
                        "rule": "time_stop", "elapsed_sec": elapsed}
                )

        except Exception:
            self._metrics["fsm_errors_total"] += 1

        return None

    def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
        """Handle SL/TP bracket fills and perform OCO emulation."""
        pld = msg.pld or {}
        order_id = pld.get("orderId")

        if not order_id:
            return None

        # Check if this is a bracket fill
        if order_id == self.sl_order_id:
            # SL filled - cancel TP (OCO emulation)
            decision = None
            oco_enabled = bool(self._manage_config().brackets.oco_emulation)

            if self.tp_order_id and oco_enabled:
                LOG.info(
                    "EXEC_POS_MANAGE_OCO_SL_FILLED",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "tp_order_id": self.tp_order_id,
                        "why": "cancel_tp_after_sl",
                    },
                )
                decision = self._emit_cancel_order(
                    msg, self.tp_order_id, "OCO_SL_filled")

            # Always clear the filled order from tracking
            self.sl_order_id = None
            return decision

        elif order_id == self.tp_order_id:
            # TP filled - cancel SL (OCO emulation)
            decision = None
            oco_enabled = bool(self._manage_config().brackets.oco_emulation)

            if self.sl_order_id and oco_enabled:
                LOG.info(
                    "EXEC_POS_MANAGE_OCO_TP_FILLED",
                    extra={
                        "symbol": getattr(self, "symbol", None),
                        "sl_order_id": self.sl_order_id,
                        "why": "cancel_sl_after_tp",
                    },
                )
                decision = self._emit_cancel_order(
                    msg, self.sl_order_id, "OCO_TP_filled")

            # Always clear the filled order from tracking
            self.tp_order_id = None
            return decision

        return None

    def _check_trailing_stop(self, msg: Message) -> Optional[Message]:
        """Check and adjust trailing stop if conditions met."""
        try:
            trailing_cfg = self._manage_config().trailing
            if not trailing_cfg.enabled or not self.sl_order_id:
                return None

            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None

            current_price_dec = Decimal(str(current_price))
            now = time.time()

            # Check activation condition
            if not self.trailing_activated and self.position_entry_price:
                # Get activation_profit_atr_k
                activation_k = float(
                    trailing_cfg.activation_profit_atr_k or 1.0)

                activation_threshold = self.position_entry_price * (
                    1
                    + Decimal(str(activation_k))
                    * Decimal("0.01")  # Simplified ATR
                )
                if (
                    self.position_side == "BUY"
                    and current_price_dec >= activation_threshold
                ):
                    self.trailing_activated = True
                    LOG.info(
                        "EXEC_POS_MANAGE_TRAILING_ACTIVATED",
                        extra={
                            "symbol": getattr(self, "symbol", None),
                            "price": str(current_price_dec),
                            "side": self.position_side,
                            "why": "trail_long_trigger",
                        },
                    )
                elif (
                    self.position_side == "SELL"
                    and current_price_dec <= activation_threshold
                ):
                    self.trailing_activated = True
                    LOG.info(
                        "EXEC_POS_MANAGE_TRAILING_ACTIVATED",
                        extra={
                            "symbol": getattr(self, "symbol", None),
                            "price": str(current_price_dec),
                            "side": self.position_side,
                            "why": "trail_short_trigger",
                        },
                    )
                else:
                    return None

            # Check cooldown
            if now - self.last_trailing_ts < float(trailing_cfg.cooldown_sec or 0.0):
                return None

            # Calculate new SL price
            step_bps = trailing_cfg.step_bps
            if self.position_side == "BUY" and self.sl_price:
                # For long position, trail up
                new_sl_price = max(
                    self.sl_price,
                    current_price_dec * (1 - Decimal(str(step_bps)) / 10000),
                )
                if new_sl_price > self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)
            elif self.position_side == "SELL" and self.sl_price:
                # For short position, trail down
                new_sl_price = min(
                    self.sl_price,
                    current_price_dec * (1 + Decimal(str(step_bps)) / 10000),
                )
                if new_sl_price < self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

        except Exception:
            self._metrics["fsm_errors_total"] += 1

        return None

    def _adjust_trailing_stop(self, msg: Message, new_sl_price: Decimal) -> Message:
        """Adjust trailing stop by cancelling old and placing new."""
        self.last_trailing_ts = time.time()
        self.sl_price = new_sl_price
        self._metrics["fsm_trailing_adjustments"] += 1

        # Cancel old SL
        cancel_msg = self._emit_cancel_order(
            msg, self.sl_order_id or "", "trailing_adjust"

        )

        # Place new SL (will be handled by next message)
        trail_suffix = f"sl_trail_{int(time.time())}"
        symbol_ref = getattr(self, "symbol", None) or (
            msg.pld or {}).get("symbol")
        rid_val = getattr(msg, "rid", None)
        decision_ref = self.sl_order_id or getattr(msg, "id", None)
        trail_meta = build_client_order_id(
            intent=ClientOrderIntent.STOP_LOSS,
            rid=str(rid_val) if rid_val else None,
            symbol=str(symbol_ref) if symbol_ref else None,
            decision_id=str(decision_ref) if decision_ref else None,
            extra=trail_suffix,
            max_len=self.CLIENT_ORDER_ID_MAX_LEN,
        )
        new_client_id = trail_meta.raw

        new_sl_msg = self._emit_place_order(
            msg,
            new_client_id,
            "STOP_MARKET",
            self.position_side or "",
            str(self.position_qty),
            str(new_sl_price),
            "trailing_stop_adjust",
        )
        self._queue_decision(new_sl_msg)

        # For simplicity, return cancel first - new order will be placed on next cycle
        return cancel_msg

    def _emit_cancel_order(self, msg: Message, order_id: str, why: str) -> Message:
        """Emit DEC:CANCEL_ORDER with symbol included for adapter call."""
        symbol = (msg.pld or {}).get("symbol", "")
        return Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"cancel_{order_id}_{int(time.time())}",
            pld={
                "orderId": order_id,
                "symbol": symbol,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

    def _emit_adjust(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:ADJUST with guaranteed symbol in payload."""
        self.state = ManageState.EMIT_DEC_ADJUST
        self._metrics["fsm_adjust_decisions_total"] += 1

        symbol = (msg.pld or {}).get("symbol") or getattr(self, "symbol", None)
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": self.position_side,
        }
        payload.update(details)

        if "qty" not in payload:
            qty_value = self.position_qty
            if qty_value is not None:
                try:
                    payload["qty"] = str(abs(Decimal(str(qty_value))))
                except Exception:
                    payload["qty"] = str(qty_value)
            else:
                payload["qty"] = "0"

        dec = Message(
            op="DEC",
            verb="ADJUST",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
            pld=payload,
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

        # Return to TRACKING
        self.state = ManageState.TRACKING
        return dec

    def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:CLOSE with reduce_only=true and include symbol when available.

        This mirrors CloseFlowFSM._emit_close, but is emitted from ManageFlowFSM.
        """
        self.state = ManageState.EMIT_DEC_ADJUST
        self._metrics["fsm_adjust_decisions_total"] = self._metrics.get(
            "fsm_adjust_decisions_total", 0) + 1

        symbol = (msg.pld or {}).get("symbol") or getattr(self, 'symbol', None)
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": self.position_side,
            "reduce_only": True,
            **details,
        }

        dec = build_dec_close(msg, why, payload=payload)

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

            # Restore position data
            self.position_qty = Decimal(
                str(state_data.get("qty", state_data.get("quantity", 0)))) if state_data.get("qty") or state_data.get("quantity") else None
            self.position_entry_price = Decimal(str(state_data.get(
                "entry_price", 0))) if state_data.get("entry_price") else None
            self.position_side = self._normalize_order_side(
                state_data.get("side")
            )
            self.position_open_ts = float(state_data.get("open_ts", 0))

            # Restore bracket data
            self.sl_order_id = state_data.get("sl_order_id")
            self.tp_order_id = state_data.get("tp_order_id")
            # Restore symbol if present
            try:
                self.symbol = state_data.get(
                    'symbol', getattr(self, 'symbol', None))
            except Exception:
                self.symbol = getattr(self, 'symbol', None)

            # Set appropriate state based on what data is available
            if self.position_qty and self.position_qty != 0:
                if self.sl_order_id:
                    self.state = ManageState.BRACKETS_PLACED
                else:
                    self.state = ManageState.TRACKING
            else:
                self.state = ManageState.FLAT

        except (ValueError, TypeError, KeyError) as e:
            LOG.error(
                "EXEC_POS_MANAGE_HYDRATE_FAILED",
                extra={
                    "rid": rid,
                    "error": str(e),
                    "why": "hydrate_failed",
                },
            )
            self.state = ManageState.ERROR

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = ManageState.FLAT
        self.position_qty = None
        self.position_entry_price = None
        self.position_open_ts = 0.0
        self.position_side = None
        self.sl_order_id = None
        self.tp_order_id = None
        self.sl_price = None
        self.tp_price = None
        self.trailing_activated = False
        self.last_trailing_ts = 0.0
