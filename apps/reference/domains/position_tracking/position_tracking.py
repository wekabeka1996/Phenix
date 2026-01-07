"""
PositionTracking domain component.

Tracks positions, calculates P&L, and emits EVT:PORTFOLIO_STATE_UPDATED events.
"""

import decimal
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from vfoundation.dr import wal  # WAL module for disaster recovery
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_contract import ConfigContractError
from apps.reference.domain_config import DomainConfigResolver

# Import AlertManager for manual intervention alerts
try:
    from apps.reference.telemetry.alerts import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    AlertManager = None  # type: ignore

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


logger = logging.getLogger(__name__)


def _d(value: Any, default: decimal.Decimal = decimal.Decimal("0")) -> decimal.Decimal:
    """
    Safe Decimal parsing function.

    Converts value to Decimal safely, returning default on failure.
    """
    try:
        if isinstance(value, decimal.Decimal):
            return value
        return decimal.Decimal(str(value))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return default


class PositionTracking:
    """
    Position tracking component that processes trades and calculates portfolio state.

    Subscribes to EVT:TRADE_EXECUTED and emits EVT:PORTFOLIO_STATE_UPDATED.
    """

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        self.fsm = fsm
        if isinstance(config, dict):
            raise TypeError("PositionTracking requires AuroraConfig, got dict")
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        # Subscribe to events
        self.fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)
        self.fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", self.on_account_update)
        self.fsm.listen("EVT:BALANCE_UPDATE_RECEIVED", self.on_balance_update)

        # P1: Optional subscription to EVT:MARKET_TICK_RECEIVED for real-time mark prices
        domain_cfg = DomainConfigResolver(self.config).get_position_tracking()
        self._market_tick_subscription_enabled = bool(domain_cfg.enable_market_tick_subscription)
        if self._market_tick_subscription_enabled:
            self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)
            self.logger.info("Market tick subscription enabled for real-time unrealized PnL")

        # Initialize AlertManager for manual intervention alerts
        self.alert_manager: Optional[AlertManager] = None
        if ALERT_MANAGER_AVAILABLE:
            try:
                self.alert_manager = AlertManager(
                    config=config, logger=self.logger)
                self.logger.info(
                    "AlertManager initialized in PositionTracking")
            except Exception as e:
                self.logger.warning(f"Failed to initialize AlertManager: {e}")

        # State tracking
        # symbol -> position data
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._realized_pnl: decimal.Decimal = decimal.Decimal("0")
        self._equity: decimal.Decimal = decimal.Decimal(
            "0"
        )  # Will be loaded from account
        self._initial_balance: Optional[decimal.Decimal] = (
            None  # Initial wallet balance (AURORA_STATE_SYNC_V1)
        )
        
        # Market prices cache for unrealized PnL calculation
        # symbol -> {"mark_price": Decimal, "ts_ms": int}
        self._mark_prices: Dict[str, Dict[str, Any]] = {}
        self._mark_price_stale_ms: int = 5000  # 5 seconds staleness threshold

        # Manual intervention metrics
        self.manual_intervention_detected_total = 0

        # Load precision parameters from canonical domains config
        precision = domain_cfg.precision
        self.quantity_min_threshold = decimal.Decimal(str(precision.quantity_min_threshold))
        self.flat_position_threshold = decimal.Decimal(str(precision.flat_position_threshold))
        self.decimal_places = int(precision.decimal_places)

    def on_market_tick(self, event: Message) -> None:
        """
        Handle incoming market tick event to update mark price cache.

        P1: Updates cached mark prices for unrealized PnL calculation.

        Args:
            event: FSM event with market tick payload
        """
        try:
            payload = event.pld
            symbol = payload.get("symbol")
            
            # Use mid price as mark price approximation
            # In production, this could come from a dedicated mark price stream
            mid_price = payload.get("mid") or payload.get("price")
            ts = payload.get("ts") or int(time.time() * 1000)

            if symbol and mid_price:
                mark_price = _d(mid_price)
                if mark_price > decimal.Decimal("0"):
                    self.update_mark_price(symbol, mark_price, ts_ms=ts)
        except Exception as e:
            self.logger.warning(f"Error processing market tick: {e}")

    def start(self) -> None:
        """Start the position tracking component and emit initial portfolio state."""
        # Emit initial portfolio state with zero positions
        positions_last_ts_ms = int(time.time() * 1000)

        portfolio_payload = {
            "ts": positions_last_ts_ms,
            "equity": "0",  # No equity data yet
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "available_balance": "0",
            "positions": [],  # Empty positions list
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            # EXP-DIRECTION: Initial zero margin by side
            "positions_by_side": {
                "long_margin": "0",
                "short_margin": "0"
            },
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        self.logger.info("Emitting initial EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why="Initial portfolio state with no positions.",
        )

    def on_trade_executed(self, event: Message) -> None:
        """
        Handle incoming trade executed event and update portfolio state.

        Args:
            event: FSM event with trade payload
        """
        self.logger.info("Handling EVT:TRADE_EXECUTED...")

        # --- WAL INTEGRATION (FSMP-RESILIENCE-T03-A) ---
        # Write event to WAL BEFORE processing to ensure disaster recovery
        try:
            event_dict = {
                "op": event.op,
                "verb": event.verb,
                "pld": event.pld,
                "src": event.src,
                "dst": event.dst,
                # Convert RID to string for JSON serialization
                "rid": str(event.rid),
                "timestamp": time.time(),
            }
            wal_hash = wal.append(event_dict)
            if wal_hash is None:
                # WAL write failed due to lock timeout
                self.logger.critical(
                    "CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL "
                    f"(lock timeout). Halting processing for safety. RID={event.rid}"
                )
                return
            self.logger.debug(
                f"WAL: Appended TRADE_EXECUTED to WAL with hash={wal_hash[:8]}..."
            )
        except Exception as e:
            # Any WAL write failure is critical - we cannot process without durability guarantee
            self.logger.critical(
                "CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL. "
                f"Halting processing for safety. RID={event.rid}, Error: {e}"
            )
            return
        # --- END WAL INTEGRATION ---

        payload = event.pld

        # Extract required fields from payload
        symbol = payload["symbol"]
        side = payload["side"]
        price = _d(payload["price"])
        quantity = _d(payload["quantity"])
        ts = payload["ts"]
        fees = _d(payload.get("fees"))
        venue = payload["venue"]

        # Convert side to quantity sign
        if side == "buy":
            qty = abs(quantity)
        elif side == "sell":
            qty = -abs(quantity)
        else:
            raise ValueError(f"Invalid side: {side}")

        # Update position and calculate P&L
        self._update_position(symbol, qty, price, fees, venue)

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used (backward compatible)
        open_positions_margin_usd = self._calc_margin_used_usd([])
        # EXP-DIRECTION: Calculate margin by side
        margin_by_side = self._calculate_margin_by_side([])
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event
        portfolio_payload = {
            "ts": ts,
            # Preserve Decimal precision as string
            "equity": str(self._equity),
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": str(
                self._calculate_unrealized_pnl()
            ),  # Preserve Decimal precision as string
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        # Emit portfolio state updated event
        self.logger.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=f"Portfolio updated after trade execution for {symbol}.",
        )

        self.logger.info(f"Emitted portfolio update after trade for {symbol}.")

    def on_account_update(self, event: Message) -> None:
        """
        Handle incoming account update event from Binance API.

        Args:
            event: FSM event with account payload
        """
        self.logger.info("Handling EVT:ACCOUNT_UPDATE_RECEIVED...")

        # --- WAL INTEGRATION (FSMP-RESILIENCE-T03-A) ---
        # Write event to WAL BEFORE processing to ensure disaster recovery
        try:
            event_dict = {
                "op": event.op,
                "verb": event.verb,
                "pld": event.pld,
                "src": event.src,
                "dst": event.dst,
                # Convert RID to string for JSON serialization
                "rid": str(event.rid),
                "timestamp": time.time(),
            }
            wal_hash = wal.append(event_dict)
            if wal_hash is None:
                # WAL write failed due to lock timeout
                self.logger.critical(
                    "CRITICAL: Failed to write EVT:ACCOUNT_UPDATE_RECEIVED to WAL "
                    "(lock timeout). Halting processing for safety. RID={event.rid}"
                )
                return
            self.logger.debug(
                f"WAL: Appended ACCOUNT_UPDATE_RECEIVED to WAL with hash={wal_hash[:8]}..."
            )
        except Exception as e:
            # Any WAL write failure is critical - we cannot process without durability guarantee
            self.logger.critical(
                "CRITICAL: Failed to write EVT:ACCOUNT_UPDATE_RECEIVED to WAL. "
                f"Halting processing for safety. RID={event.rid}, Error: {e}"
            )
            return
        # --- END WAL INTEGRATION ---

        payload = event.pld

        # Update equity from account data
        total_wallet_balance = _d(payload.get("totalWalletBalance"))
        total_unrealized_profit = _d(payload.get("totalUnrealizedProfit"))
        if "totalCrossWalletBalance" in payload:
            total_cross_wallet_balance = _d(payload.get("totalCrossWalletBalance"))
        else:
            total_cross_wallet_balance = total_wallet_balance - total_unrealized_profit

        self._equity = total_wallet_balance

        # === AURORA_STATE_SYNC_V1: Recalculate realized_pnl from ACCOUNT_UPDATE ===
        # totalCrossWalletBalance = balance without unrealized PnL
        # realized_pnl = totalCrossWalletBalance - initial_balance
        if self._initial_balance is None:
            # First account update - set initial balance
            self._initial_balance = total_cross_wallet_balance
            self._realized_pnl = decimal.Decimal("0")
            self.logger.info(
                f"[STATE_SYNC] Initial balance set: ${self._initial_balance}"
            )
        else:
            # Recalculate realized_pnl from cross wallet balance
            old_realized_pnl = self._realized_pnl
            self._realized_pnl = total_cross_wallet_balance - self._initial_balance

            if old_realized_pnl != self._realized_pnl:
                self.logger.debug(
                    "[STATE_SYNC] Realized PnL recalculated: "
                    f"${old_realized_pnl} → ${self._realized_pnl} "
                    f"(cross_balance=${total_cross_wallet_balance}, initial=${self._initial_balance})"
                )

        # Update positions from account data
        account_positions = payload.get("positions")
        if account_positions is None:
            account_positions = []

        self.logger.info(
            f"📊 SYNC: Received {len(account_positions)} positions from Binance")

        # Track which symbols are in Binance vs our internal state
        binance_symbols = set()

        for pos in account_positions:
            symbol = pos["symbol"]
            quantity = _d(pos.get("positionAmt"))
            binance_symbols.add(symbol)

            if abs(quantity) > self.quantity_min_threshold:  # Only track non-zero positions
                prev = self._positions[symbol] if symbol in self._positions else {}
                old_qty = prev["quantity"] if "quantity" in prev else decimal.Decimal("0")
                self._positions[symbol] = {
                    "quantity": quantity,
                    "avg_price": _d(pos.get("entryPrice")),
                    "venues": ["binance"],  # Assume Binance venue
                }
                if old_qty != quantity:
                    self.logger.info(
                        f"📈 SYNC: {symbol} position updated: {old_qty} → {quantity}")
            else:
                # Remove flat positions
                if symbol in self._positions:
                    self.logger.info(
                        f"📉 SYNC: {symbol} position closed (removed from tracking)")
                self._positions.pop(symbol, None)

        # Check for positions in our state that are NOT in Binance (manual close)
        our_symbols = set(self._positions.keys())
        manually_closed = our_symbols - binance_symbols

        if manually_closed:
            self.logger.warning(
                f"⚠️  SYNC: Detected manually closed positions: {manually_closed}")

            # Increment manual intervention metric
            self.manual_intervention_detected_total += len(manually_closed)

            # Send alerts for each manually closed position
            for symbol in manually_closed:
                position_details = self._positions[symbol] if symbol in self._positions else {}

                # Alert via AlertManager if available
                if self.alert_manager:
                    self.alert_manager.check_manual_intervention(
                        symbol=symbol,
                        position_details=position_details
                    )

                self.logger.info(
                    f"🧹 SYNC: Removing {symbol} from internal state (closed manually)")
                self._positions.pop(symbol, None)

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used with positionRisk data if available
        open_positions_margin_usd = self._calc_margin_used_usd(
            account_positions)
        # EXP-DIRECTION: Calculate margin by side for directional ratio checks
        margin_by_side = self._calculate_margin_by_side(account_positions)
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event with real account data
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            "equity": str(self._equity),  # Legacy field for compatibility
            # EXP-FIX: Always include equity_free_usdt
            "equity_free_usdt": str(self._equity),
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": str(
                _d(payload.get("totalUnrealizedProfit"))
            ),  # Preserve Decimal precision as string
            "available_balance": str(
                _d(payload["maxWithdrawAmount"] if "maxWithdrawAmount" in payload else self._equity)
            ),  # Available margin for new positions
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        # Add additional equity fields if USDT present in balance data (from account update)
        # Note: account updates may not include full asset list, so equity computation might be limited
        if "assets" in payload:
            equity_data = self._compute_equity_from_balance(
                payload["assets"], payload)
            if equity_data:
                portfolio_payload.update(
                    {
                        "equity_cross_usdt": equity_data["equity_cross_usdt"],
                        "equity_ts": equity_data["equity_ts"],
                    }
                )

        self.logger.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why="Portfolio updated from Binance account data.",
        )

        self.logger.info(
            f"Updated portfolio from account: equity={self._equity}, positions={len(self._positions)}"
        )

    def on_balance_update(self, event: Message) -> None:
        """
        Handle incoming balance update event from Binance API.

        Args:
            event: FSM event with balance payload
        """
        self.logger.info("Handling EVT:BALANCE_UPDATE_RECEIVED...")
        payload = event.pld

        # Balance updates provide asset balances, but equity is tracked via account updates
        # We can use this for additional validation or logging
        assets = payload.get("assets")
        if assets is None:
            assets = []
        self.logger.info(
            f"Balance update received: {len(assets)} assets with balance > 0"
        )

        # Compute equity metrics for USDT-M futures
        equity_data = self._compute_equity_from_balance(assets)
        if not equity_data:
            self.logger.warning(
                "Skipping portfolio update: no USDT in balance data")
            return

        # Update internal equity state
        self._equity = decimal.Decimal(equity_data["equity_free_usdt"])

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used (fallback to config leverage)
        open_positions_margin_usd = self._calc_margin_used_usd([])
        # EXP-DIRECTION: Calculate margin by side
        margin_by_side = self._calculate_margin_by_side([])
        positions_last_ts_ms = int(time.time() * 1000)

        # Emit portfolio state updated event with equity fields for DecisionMaking
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            # Legacy field for compatibility
            "equity": equity_data["equity_free_usdt"],
            "equity_free_usdt": equity_data["equity_free_usdt"],
            "equity_cross_usdt": equity_data["equity_cross_usdt"],
            "equity_ts": equity_data["equity_ts"],
            "realized_pnl": str(
                self._realized_pnl
            ),  # Preserve Decimal precision as string
            "unrealized_pnl": "0",  # Not available in balance update
            "available_balance": equity_data["equity_free_usdt"],
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
            # EXP-DIRECTION: Per-side margin for directional checks
            "positions_by_side": {
                "long_margin": str(margin_by_side["long_margin"]),
                "short_margin": str(margin_by_side["short_margin"])
            },
            # EXP-FIX: Timestamp for staleness check
            "positions_last_ts_ms": positions_last_ts_ms,
        }

        self.logger.info(
            "✅ Emitting EVT:PORTFOLIO_STATE_UPDATED from balance update..."
        )
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=equity_data["why"],
        )

    def _compute_equity_from_balance(
        self,
        assets: List[Dict[str, Any]],
        account_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute equity metrics for USDT-M futures account.

        Args:
            assets: List of asset balances from BALANCE_UPDATE
            account_data: Optional account data from ACCOUNT_UPDATE

        Returns:
            Dict with equity_free_usdt, equity_cross_usdt, equity_ts, why or None if USDT not present
        """
        # Find USDT asset
        usdt_asset = next(
            (a for a in assets if a.get("asset") == "USDT"), None)
        if not usdt_asset:
            self.logger.warning(
                "Skipping equity computation: USDT not present in balance data"
            )
            return None

        # Compute free equity (available for new positions)
        equity_free_usdt = _d(usdt_asset.get("balance"))

        # Compute cross equity (total wallet balance including unrealized P&L)
        if account_data:
            # From ACCOUNT_UPDATE: use totalCrossWalletBalance + totalUnrealizedProfit
            equity_cross_usdt = _d(account_data.get("totalCrossWalletBalance")) + _d(account_data.get("totalUnrealizedProfit"))
            equity_ts = account_data["updateTime"] if "updateTime" in account_data else int(time.time() * 1000)
            why = "equity_from_account_update"
        else:
            # From BALANCE_UPDATE: use crossWalletBalance + crossUnPnl
            equity_cross_usdt = _d(usdt_asset.get("crossWalletBalance")) + _d(usdt_asset.get("crossUnPnl"))
            equity_ts = usdt_asset["updateTime"] if "updateTime" in usdt_asset else int(time.time() * 1000)
            why = "equity_from_balance_update"

        return {
            "equity_free_usdt": str(equity_free_usdt),
            "equity_cross_usdt": str(equity_cross_usdt),
            "equity_ts": equity_ts,
            "why": why,
        }

    def _update_position(
        self,
        symbol: str,
        quantity: decimal.Decimal,
        price: decimal.Decimal,
        fees: decimal.Decimal,
        venue: str,
    ) -> None:
        """
        Update position for a symbol and calculate realized P&L.

        Based on aurora/positions/ logic adapted for FSM events.
        """
        existing = (
            self._positions[symbol]
            if symbol in self._positions
            else {"quantity": decimal.Decimal("0"), "avg_price": decimal.Decimal("0"), "venues": []}
        )

        pos_qty = existing["quantity"]
        avg_px = existing["avg_price"]

        # Determine position sign based on existing position (+1 long, -1 short)
        pos_sign = (
            decimal.Decimal("1")
            if pos_qty > decimal.Decimal("0")
            else decimal.Decimal("-1")
            if pos_qty < decimal.Decimal("0")
            else decimal.Decimal("0")
        )

        # Realized PnL accrues only when trade reduces/offsets existing position
        realized_delta = decimal.Decimal("0")
        if pos_sign != decimal.Decimal("0") and quantity * pos_qty < decimal.Decimal(
            "0"
        ):
            closed_qty = min(abs(pos_qty), abs(quantity))
            # sign * qty_closed * (fill_px - avg_entry_px) - fees
            realized_delta = pos_sign * closed_qty * (price - avg_px) - fees

        # Update realized P&L
        self._realized_pnl += realized_delta

        # Update position quantity and average entry price
        new_qty = pos_qty + quantity
        if abs(new_qty) < decimal.Decimal("1e-12"):
            # Flat position resets avg price
            new_avg = decimal.Decimal("0")
            venues = [venue]
        else:
            # Weighted average for same-side accumulation; if crossing through zero,
            # the new avg becomes current trade price for the residual side.
            if pos_qty == decimal.Decimal("0") or (
                pos_qty * quantity > decimal.Decimal("0")
            ):
                # Same-side accumulation: recompute weighted average
                new_avg = (pos_qty * avg_px + quantity * price) / new_qty
            else:
                # Opposite-side trade
                if abs(quantity) < abs(pos_qty):
                    # Partial close: keep prior average for remaining open qty
                    new_avg = avg_px
                elif abs(quantity) == abs(pos_qty):
                    # Fully closed handled by flat branch above, but keep consistency
                    new_avg = decimal.Decimal("0")
                else:
                    # Crossed through zero (flip): new position avg is current fill price
                    new_avg = price

            # Update venues list
            existing_venues = existing["venues"]
            venues = list(set(existing_venues + [venue]))

        # Update position
        self._positions[symbol] = {
            "quantity": new_qty,
            "avg_price": new_avg,
            "venues": venues,
        }

    def _calculate_unrealized_pnl(self, positions: Optional[List[Dict[str, Any]]] = None) -> decimal.Decimal:
        """
        Calculate total unrealized P&L for all positions.

        Uses mark prices from:
        1. positionRisk API data (if provided) - contains markPrice per position
        2. Cached mark prices from EVT:MARKET_TICK_RECEIVED (if subscribed)
        3. Falls back to entry price if no mark price available (returns 0 PnL)

        Formula: unrealized_pnl = Σ((mark_price - entry_price) * quantity)
        - For LONG (qty > 0): profit when mark_price > entry_price
        - For SHORT (qty < 0): profit when mark_price < entry_price

        Args:
            positions: Optional list of position dicts from positionRisk API
                       containing 'markPrice', 'entryPrice', 'positionAmt'

        Returns:
            decimal.Decimal: Total unrealized P&L
        """
        total_unrealized_pnl = decimal.Decimal("0")
        now_ms = int(time.time() * 1000)

        if positions:
            # Use positionRisk API data (most accurate)
            for p in positions:
                symbol = p.get("symbol")
                if symbol is None:
                    symbol = "unknown"
                position_amt = _d(p.get("positionAmt"))
                entry_price = _d(p.get("entryPrice"))
                mark_price = _d(p.get("markPrice"))

                if abs(position_amt) > self.quantity_min_threshold and mark_price > decimal.Decimal("0"):
                    # unrealized_pnl = (mark_price - entry_price) * position_amt
                    position_pnl = (mark_price - entry_price) * position_amt
                    total_unrealized_pnl += position_pnl

                    self.logger.debug(
                        f"Unrealized PnL for {symbol}: mark={mark_price}, entry={entry_price}, "
                        f"qty={position_amt}, pnl={position_pnl}"
                    )
        else:
            # Fallback to internal positions with cached mark prices
            for symbol, position in self._positions.items():
                quantity = position["quantity"]
                entry_price = position["avg_price"]

                if abs(quantity) <= self.quantity_min_threshold:
                    continue

                # Try to get mark price from cache
                mark_price_data = self._mark_prices[symbol] if symbol in self._mark_prices else {}
                mark_price = _d(mark_price_data.get("mark_price"))
                mark_ts = mark_price_data["ts_ms"] if "ts_ms" in mark_price_data else 0

                # Check if mark price is fresh enough
                if mark_price > decimal.Decimal("0") and (now_ms - mark_ts) < self._mark_price_stale_ms:
                    position_pnl = (mark_price - entry_price) * quantity
                    total_unrealized_pnl += position_pnl

                    self.logger.debug(
                        f"Unrealized PnL for {symbol}: mark={mark_price}, entry={entry_price}, "
                        f"qty={quantity}, pnl={position_pnl} (from cache)"
                    )
                else:
                    # No fresh mark price available - PnL for this position is 0
                    self.logger.debug(
                        f"No fresh mark price for {symbol}, unrealized PnL = 0"
                    )

        return total_unrealized_pnl.quantize(decimal.Decimal("0.01"))

    def update_mark_price(self, symbol: str, mark_price: decimal.Decimal, ts_ms: Optional[int] = None) -> None:
        """
        Update cached mark price for a symbol.

        Called externally when EVT:MARKET_TICK_RECEIVED is received.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            mark_price: Current mark/mid price
            ts_ms: Timestamp in milliseconds (defaults to current time)
        """
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)

        self._mark_prices[symbol] = {
            "mark_price": mark_price,
            "ts_ms": ts_ms,
        }
        self.logger.debug(f"Updated mark price for {symbol}: {mark_price} @ {ts_ms}")

    def _calculate_open_positions_notional(self) -> decimal.Decimal:
        """
        Calculate total notional value of open positions in USD.

        EXP-FIX: Used by exposure gate to ensure portfolio positions are accounted for.
        Returns sum of abs(positionAmt) * markPrice for all positions.
        """
        total_notional = decimal.Decimal("0")

        # For now, use entry price as approximation since we don't have mark prices
        # In production, this should use current mark prices from market data
        for symbol, position in self._positions.items():
            quantity = abs(position["quantity"])
            entry_price = position["avg_price"]

            if quantity > self.quantity_min_threshold and entry_price > decimal.Decimal(
                "0"
            ):
                position_notional = quantity * entry_price
                total_notional += position_notional
                self.logger.debug(
                    f"Position notional for {symbol}: {position_notional} USD"
                )

        # Round to 2 decimal places for consistency
        return total_notional.quantize(decimal.Decimal("0.01"))

    def _calc_margin_used_usd(self, positions: list[dict]) -> decimal.Decimal:
        """
        Calculate total margin used by open positions in USD.

        EXP-LEVERAGE-001: Margin-based exposure calculation with leverage.
        If positions list is provided (from positionRisk API), use it.
        Otherwise, fallback to internal position data with leverage from config.
        """
        total_margin = decimal.Decimal("0")

        # FIX-AUDITED-ISSUES-01 (Part A): Differentiate explicit empty list (FLAT) from missing (FALLBACK)
        if positions is not None:
            # Explicit API data available (even if empty)
            
            # 1. Sync internal state to API snapshot
            # If positions is empty list, this correctly clears internal positions.
            # If populated, we should ideally sync them, but for now we prioritize preventing 'ghosts' on empty.
            if len(positions) == 0:
                self._positions.clear()
            
            # Use positionRisk data if available
            self.logger.info(
                f"💚 _calc_margin_used_usd() USING API: {len(positions)} positions from /fapi/v2/positionRisk")
            for p in positions:
                # Extract notional: try positionRisk fields first, fallback to calculation
                notional = _d(p.get("notional") or (
                    _d(p.get("positionAmt")) *
                    _d(p.get("markPrice") or p.get("entryPrice") or "0")
                ))

                # Extract leverage: try positionRisk field, fallback to default
                lev = _d(p.get("leverage") or "1")
                if lev <= 0:
                    lev = decimal.Decimal("1")

                # Calculate margin for this position
                margin = abs(notional) / lev
                total_margin += margin

                self.logger.debug(
                    f"Position margin for {(p.get('symbol') if p.get('symbol') is not None else 'unknown')}: notional={notional}, lev={lev}, margin={margin}"
                )
        else:
            # Fallback to internal position data with leverage from config
            self.logger.warning(
                f"🔴 _calc_margin_used_usd() FALLBACK MODE: API returned empty, using {len(self._positions)} internal positions from self._positions")
            self.logger.warning(
                f"   Internal positions: {list(self._positions.keys())}")
            
            # EXP-LEVERAGE-002: Use centralized leverage extraction
            leverage_config = self._get_leverage_config()

            # EXP-LEVERAGE-002: Use unified default resolution (__default__ first, then "default")
            default_leverage_val = self._resolve_default_leverage(leverage_config)
            default_leverage = decimal.Decimal(str(default_leverage_val))

            for symbol, position in self._positions.items():
                quantity = abs(position["quantity"])
                entry_price = position["avg_price"]

                if quantity > self.quantity_min_threshold and entry_price > decimal.Decimal("0"):
                    # Calculate notional
                    position_notional = quantity * entry_price

                    # EXP-LEVERAGE-002: Use unified symbol leverage resolution
                    symbol_leverage = self._resolve_symbol_leverage(
                        leverage_config, symbol, default_leverage
                    )

                    # Calculate margin
                    margin = position_notional / symbol_leverage
                    total_margin += margin

                    self.logger.debug(
                        f"Position margin for {symbol}: notional={position_notional}, lev={symbol_leverage}, margin={margin}"
                    )

        # Round to 2 decimal places for consistency
        self.logger.info(
            f"📊 _calc_margin_used_usd() TOTAL: {total_margin.quantize(decimal.Decimal('0.01'))} USD (API={len(positions) if positions is not None else 'FALLBACK'})")
        return total_margin.quantize(decimal.Decimal("0.01"))

    def _calculate_margin_by_side(self, positions: list[dict]) -> dict:
        """
        Calculate margin used by long and short positions separately.

        EXP-DIRECTION: Per-side margin calculation for directional ratio checks.

        Returns:
            Dict with 'long_margin' and 'short_margin' keys (as Decimal).
        """
        long_margin = decimal.Decimal("0")
        short_margin = decimal.Decimal("0")

        if positions:
            # Use positionRisk data if available
            for p in positions:
                # Extract notional
                notional = _d(p.get("notional") or (
                    _d(p.get("positionAmt")) *
                    _d(p.get("markPrice") or p.get("entryPrice") or "0")
                ))

                # Extract leverage
                lev = _d(p.get("leverage") or "1")
                if lev <= 0:
                    lev = decimal.Decimal("1")

                # Calculate margin for this position
                margin = abs(notional) / lev

                # Determine side from positionAmt sign
                amount = _d(p.get("positionAmt"))
                if amount > 0:
                    long_margin += margin
                elif amount < 0:
                    short_margin += margin
        else:
            # EXP-LEVERAGE-002: Use centralized leverage extraction
            leverage_config = self._get_leverage_config()
            default_leverage_val = self._resolve_default_leverage(leverage_config)
            default_leverage = decimal.Decimal(str(default_leverage_val))

            for symbol, position in self._positions.items():
                quantity = position["quantity"]
                entry_price = position["avg_price"]

                if abs(quantity) > self.quantity_min_threshold and entry_price > decimal.Decimal("0"):
                    # Calculate notional
                    position_notional = abs(quantity) * entry_price

                    # EXP-LEVERAGE-002: Use unified symbol leverage resolution
                    symbol_leverage = self._resolve_symbol_leverage(
                        leverage_config, symbol, default_leverage
                    )

                    # Calculate margin
                    margin = position_notional / symbol_leverage

                    # Determine side
                    if quantity > 0:
                        long_margin += margin
                    else:
                        short_margin += margin

        return {
            "long_margin": long_margin.quantize(decimal.Decimal("0.01")),
            "short_margin": short_margin.quantize(decimal.Decimal("0.01"))
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get position tracking metrics for monitoring."""
        return {
            "manual_intervention_detected_total": self.manual_intervention_detected_total,
            "positions_tracked": len(self._positions),
            "equity_usd": float(self._equity),
            "realized_pnl_usd": float(self._realized_pnl)
        }

    def _get_leverage_config(self) -> Any:
        """
        Extract leverage_defaults config from strict typed config.

        EXP-LEVERAGE-002: Centralized leverage config extraction (fail-closed).
        """
        exec_cfg = self.config.trading.execution
        if exec_cfg is None or exec_cfg.exposure is None:
            raise ConfigContractError(path="trading.execution.exposure", why="Missing exposure config (leverage_defaults).")
        return exec_cfg.exposure.leverage_defaults

    def _resolve_default_leverage(self, leverage_config: Any) -> str:
        """
        Resolve default leverage value from config.

        EXP-LEVERAGE-002: Unified default leverage resolution.
        Checks keys in order: __default__ (config_models.py standard) -> default (legacy) -> "20" (fallback)

        Args:
            leverage_config: Dict or Pydantic model with leverage values

        Returns:
            str: Default leverage value (e.g., "125" or "20")
        """
        DEFAULT_FALLBACK = "20"

        if not isinstance(leverage_config, dict):
            raise ConfigContractError(path="trading.execution.exposure.leverage_defaults", why="Expected dict leverage_defaults")

        # Check __default__ first (config_models.py standard), then "default" (legacy)
        val = leverage_config.get("__default__")
        if val is not None:
            return str(val)
        val = leverage_config.get("default")
        if val is not None:
            return str(val)

        return DEFAULT_FALLBACK

    def _resolve_symbol_leverage(
        self, leverage_config: Any, symbol: str, default_leverage: decimal.Decimal
    ) -> decimal.Decimal:
        """
        Resolve leverage for a specific symbol.

        EXP-LEVERAGE-002: Unified symbol leverage resolution.

        Args:
            leverage_config: Dict or Pydantic model with leverage values
            symbol: Trading symbol (e.g., 'BTCUSDT')
            default_leverage: Fallback leverage value

        Returns:
            decimal.Decimal: Leverage value >= 1
        """
        symbol_leverage_val = None

        if not isinstance(leverage_config, dict):
            raise ConfigContractError(path="trading.execution.exposure.leverage_defaults", why="Expected dict leverage_defaults")
        symbol_leverage_val = leverage_config.get(symbol)

        if symbol_leverage_val is not None:
            try:
                symbol_leverage = decimal.Decimal(str(symbol_leverage_val))
                return max(symbol_leverage, decimal.Decimal("1"))
            except (decimal.InvalidOperation, ValueError):
                pass

        return max(default_leverage, decimal.Decimal("1"))

    def _get_positions_snapshot(self) -> List[Dict[str, Any]]:
        """
        Get current positions snapshot in the format expected by portfolio_state_v1.json.
        """
        positions = []
        for symbol, position in self._positions.items():
            if abs(position["quantity"]) > decimal.Decimal(
                str(self.quantity_min_threshold)
            ):  # Only include non-zero positions
                positions.append(
                    {
                        "symbol": symbol,
                        "net_position": str(
                            position["quantity"]
                        ),  # Preserve Decimal precision as string
                        "avg_entry_price": str(
                            position["avg_price"]
                        ),  # Preserve Decimal precision as string
                        "venues": position["venues"],
                    }
                )
        return positions

    def get_snapshot(self) -> dict:
        """
        Serializes the current state of the position_tracking domain for DR purposes.

        Returns a snapshot compliant with snapshot_v1.schema.json for disaster recovery.
        All numeric values are preserved as Decimal-encoded strings to maintain precision.

        Returns:
            dict: DR snapshot with domain state, hash, and metadata
        """
        # Build positions dictionary with Decimal precision preservation
        positions_state = {}
        for symbol, position in self._positions.items():
            if abs(position["quantity"]) > decimal.Decimal(
                str(self.quantity_min_threshold)
            ):  # Only include non-zero positions
                qty = position["quantity"]
                positions_state[symbol] = {
                    "qty": str(qty),
                    "avg_price": str(position["avg_price"]),
                    "side": "long" if qty > 0 else "short",
                    "unrealized_pnl": "0.0",  # Placeholder - would need current market price
                }

        # Build portfolio state with precision preservation
        portfolio_state = {
            "equity": str(self._equity),
            # Simplified calculation
            "balance": str(self._equity - self._realized_pnl),
            "margin_used": "0.0",  # Placeholder - would need real margin calculation
        }

        # Complete state object
        state_data = {"positions": positions_state,
                      "portfolio": portfolio_state}
        # Compute state hash for integrity verification
        state_str = json.dumps(state_data, sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()

        # Build snapshot with metadata
        # NOTE: worker_id is legacy metadata and is not part of the typed config contract.
        worker_id = "unknown"

        snapshot = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "state_hash": f"sha256:{state_hash}",
            "state": state_data,
            "metadata": {
                "worker_id": worker_id,
                "positions_count": len(positions_state),
                "sequence_number": int(
                    time.time() * 1000
                ),  # Use timestamp as sequence for now
            },
        }

        self.logger.info(
            f"DR Snapshot created: {len(positions_state)} positions, "
            f"equity={self._equity}, hash={state_hash[:16]}..."
        )

        return snapshot

    def load_snapshot(self, snapshot_data: dict) -> bool:
        """
        Loads the domain's state from a snapshot dictionary.

        Verifies integrity using the provided state_hash and restores positions
        and portfolio values. Numeric strings are converted back to Decimal to
        preserve precision.

        Args:
            snapshot_data: Snapshot dictionary produced by `get_snapshot()`.

        Returns:
            bool: True if load succeeded, False otherwise.
        """
        try:
            state_to_load = snapshot_data["state"]
            state_hash_field = snapshot_data["state_hash"] if "state_hash" in snapshot_data else ""
            expected_hash = (
                state_hash_field.split(":")[-1] if state_hash_field else None
            )

            # Verify integrity
            state_str = json.dumps(state_to_load, sort_keys=True)
            actual_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()

            if expected_hash and actual_hash != expected_hash:
                self.logger.error(
                    f"Snapshot integrity check failed! Expected hash {expected_hash}, got {actual_hash}."
                )
                return False

            # Restore positions (convert strings back to Decimal)
            positions_loaded: Dict[str, Dict[str, Any]] = {}
            positions_block = state_to_load["positions"] if "positions" in state_to_load else {}
            for symbol, pos in positions_block.items():
                try:
                    qty_raw = pos["qty"] if "qty" in pos else "0"
                    avg_price_raw = pos["avg_price"] if "avg_price" in pos else "0"
                    qty = decimal.Decimal(str(qty_raw))
                    avg_price = decimal.Decimal(str(avg_price_raw))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    self.logger.error(
                        f"Invalid numeric in snapshot for {symbol}: {e}")
                    return False

                positions_loaded[symbol] = {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "venues": pos["venues"] if "venues" in pos else [],
                }

            # Restore portfolio/equity if present
            portfolio = state_to_load["portfolio"] if "portfolio" in state_to_load else {}
            equity_str = portfolio.get("equity")
            balance_str = portfolio.get("balance")

            if equity_str is not None:
                try:
                    self._equity = decimal.Decimal(str(equity_str))
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.error("Invalid equity value in snapshot")
                    return False

            # Try to reconstruct realized pnl if balance provided: realized = equity - balance
            if balance_str is not None:
                try:
                    balance_dec = decimal.Decimal(str(balance_str))
                    # realized_pnl = equity - balance
                    self._realized_pnl = self._equity - balance_dec
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.warning(
                        "Invalid balance value in snapshot; leaving realized_pnl unchanged"
                    )

            # Apply restored positions
            self._positions = positions_loaded

            snapshot_ts = snapshot_data["timestamp_utc"] if "timestamp_utc" in snapshot_data else "unknown"
            self.logger.info(
                f"Successfully loaded state from snapshot created at {snapshot_ts}. "
                f"Restored {len(self._positions)} positions."
            )

            return True

        except KeyError as e:
            self.logger.critical(
                f"Failed to load snapshot due to missing key: {e}")
            return False
        except (TypeError, json.JSONDecodeError) as e:
            self.logger.critical(
                f"Failed to load snapshot due to invalid format: {e}")
            return False

    def stop(self) -> None:
        """Stop the position tracking component."""
        self.logger.info("PositionTracking stopped")
