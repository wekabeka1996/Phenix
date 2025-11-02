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

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        # Subscribe to events
        self.fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)
        self.fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", self.on_account_update)
        self.fsm.listen("EVT:BALANCE_UPDATE_RECEIVED", self.on_balance_update)

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
                "rid": event.rid,
                "timestamp": time.time(),
            }
            wal_hash = wal.append(event_dict)
            if wal_hash is None:
                # WAL write failed due to lock timeout
                self.logger.critical(
                    f"CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL (lock timeout). "
                    f"Halting processing for safety. RID={event.rid}"
                )
                return
            self.logger.debug(
                f"WAL: Appended TRADE_EXECUTED to WAL with hash={wal_hash[:8]}..."
            )
        except Exception as e:
            # Any WAL write failure is critical - we cannot process without durability guarantee
            self.logger.critical(
                f"CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL. "
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
        fees = _d(payload.get("fees", 0))
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
                "rid": event.rid,
                "timestamp": time.time(),
            }
            wal_hash = wal.append(event_dict)
            if wal_hash is None:
                # WAL write failed due to lock timeout
                self.logger.critical(
                    f"CRITICAL: Failed to write EVT:ACCOUNT_UPDATE_RECEIVED to WAL (lock timeout). "
                    f"Halting processing for safety. RID={event.rid}"
                )
                return
            self.logger.debug(
                f"WAL: Appended ACCOUNT_UPDATE_RECEIVED to WAL with hash={wal_hash[:8]}..."
            )
        except Exception as e:
            # Any WAL write failure is critical - we cannot process without durability guarantee
            self.logger.critical(
                f"CRITICAL: Failed to write EVT:ACCOUNT_UPDATE_RECEIVED to WAL. "
                f"Halting processing for safety. RID={event.rid}, Error: {e}"
            )
            return
        # --- END WAL INTEGRATION ---

        payload = event.pld

        # Update equity from account data
        total_wallet_balance = _d(payload.get("totalWalletBalance", 0))
        total_unrealized_profit = _d(payload.get("totalUnrealizedProfit", 0))
        total_cross_wallet_balance = _d(
            payload.get(
                "totalCrossWalletBalance",
                total_wallet_balance - total_unrealized_profit,
            )
        )

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
                    f"[STATE_SYNC] Realized PnL recalculated: "
                    f"${old_realized_pnl} → ${self._realized_pnl} "
                    f"(cross_balance=${total_cross_wallet_balance}, initial=${self._initial_balance})"
                )

        # Update positions from account data
        account_positions = payload.get("positions", [])
        for pos in account_positions:
            symbol = pos["symbol"]
            quantity = _d(pos.get("positionAmt", 0))
            if abs(quantity) > decimal.Decimal("1e-9"):  # Only track non-zero positions
                self._positions[symbol] = {
                    "quantity": quantity,
                    "avg_price": _d(pos.get("entryPrice", 0)),
                    "venues": ["binance"],  # Assume Binance venue
                }
            else:
                # Remove flat positions
                self._positions.pop(symbol, None)

        # Calculate open positions notional (EXP-FIX: Portfolio Notional Hard Gate)
        open_positions_usd = self._calculate_open_positions_notional()
        # EXP-LEVERAGE-001: Calculate margin used with positionRisk data if available
        open_positions_margin_usd = self._calc_margin_used_usd(
            account_positions)
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
                _d(payload.get("totalUnrealizedProfit", 0))
            ),  # Preserve Decimal precision as string
            "available_balance": str(
                _d(payload.get("maxWithdrawAmount", self._equity))
            ),  # Available margin for new positions
            "positions": self._get_positions_snapshot(),
            "open_positions_usd": str(
                open_positions_usd
            ),  # EXP-FIX: Notional for exposure gate
            "open_positions_margin_usd": str(
                open_positions_margin_usd
            ),  # EXP-LEVERAGE-001: Margin for exposure gate
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
        assets = payload.get("assets", [])
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
        equity_free_usdt = _d(usdt_asset.get("balance", "0"))

        # Compute cross equity (total wallet balance including unrealized P&L)
        if account_data:
            # From ACCOUNT_UPDATE: use totalCrossWalletBalance + totalUnrealizedProfit
            equity_cross_usdt = _d(
                account_data.get("totalCrossWalletBalance", "0")
            ) + _d(account_data.get("totalUnrealizedProfit", "0"))
            equity_ts = account_data.get("updateTime", int(time.time() * 1000))
            why = "equity_from_account_update"
        else:
            # From BALANCE_UPDATE: use crossWalletBalance + crossUnPnl
            equity_cross_usdt = _d(usdt_asset.get("crossWalletBalance", "0")) + _d(
                usdt_asset.get("crossUnPnl", "0")
            )
            equity_ts = usdt_asset.get("updateTime", int(time.time() * 1000))
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
        existing = self._positions.get(
            symbol,
            {
                "quantity": decimal.Decimal("0"),
                "avg_price": decimal.Decimal("0"),
                "venues": [],
            },
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

    def _calculate_unrealized_pnl(self) -> decimal.Decimal:
        """
        Calculate total unrealized P&L for all positions.

        Note: This is a simplified calculation since we don't have current market prices
        in the position tracking domain. In production, this should be calculated using
        current mark prices from market data.

        Returns:
            decimal.Decimal: Total unrealized P&L
        """
        # For now, return 0 since we don't have current market prices
        # In production, this would be: sum((current_price - avg_entry_price) * quantity for each position)
        return decimal.Decimal("0")

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

            if quantity > decimal.Decimal("1e-9") and entry_price > decimal.Decimal(
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

        if positions:
            # Use positionRisk data if available
            for p in positions:
                # Extract notional: try positionRisk fields first, fallback to calculation
                notional = _d(p.get("notional") or (
                    _d(p.get("positionAmt", "0")) *
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
                    f"Position margin for {p.get('symbol', 'unknown')}: notional={notional}, lev={lev}, margin={margin}"
                )
        else:
            # Fallback to internal position data with leverage from config
            leverage_config = self.config.get("trading", {}).get(
                "execution", {}).get("exposure", {}).get("leverage_defaults", {})
            default_leverage = decimal.Decimal(
                str(leverage_config.get("__default__", "20")))

            for symbol, position in self._positions.items():
                quantity = abs(position["quantity"])
                entry_price = position["avg_price"]

                if quantity > decimal.Decimal("1e-9") and entry_price > decimal.Decimal("0"):
                    # Calculate notional
                    position_notional = quantity * entry_price

                    # Get leverage for this symbol
                    symbol_leverage = decimal.Decimal(
                        str(leverage_config.get(symbol, default_leverage)))
                    if symbol_leverage <= 0:
                        symbol_leverage = decimal.Decimal("1")

                    # Calculate margin
                    margin = position_notional / symbol_leverage
                    total_margin += margin

                    self.logger.debug(
                        f"Position margin for {symbol}: notional={position_notional}, lev={symbol_leverage}, margin={margin}"
                    )

        # Round to 2 decimal places for consistency
        return total_margin.quantize(decimal.Decimal("0.01"))

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """Returns a copy of the internal positions dictionary."""
        return self._positions.copy()

    def _get_positions_snapshot(self) -> List[Dict[str, Any]]:
        """
        Get current positions snapshot in the format expected by portfolio_state_v1.json.
        """
        positions = []
        for symbol, position in self._positions.items():
            if abs(position["quantity"]) > decimal.Decimal(
                "1e-9"
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
                "1e-9"
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
        snapshot = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "state_hash": f"sha256:{state_hash}",
            "state": state_data,
            "metadata": {
                "worker_id": self.config.get("system", {}).get("worker_id", "unknown"),
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
            state_hash_field = snapshot_data.get("state_hash", "")
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
            for symbol, pos in state_to_load.get("positions", {}).items():
                try:
                    qty = decimal.Decimal(str(pos.get("qty", "0")))
                    avg_price = decimal.Decimal(str(pos.get("avg_price", "0")))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    self.logger.error(
                        f"Invalid numeric in snapshot for {symbol}: {e}")
                    return False

                positions_loaded[symbol] = {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "venues": pos.get("venues", []),
                }

            # Restore portfolio/equity if present
            portfolio = state_to_load.get("portfolio", {})
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

            self.logger.info(
                f"Successfully loaded state from snapshot created at {snapshot_data.get('timestamp_utc', 'unknown')}. "
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
