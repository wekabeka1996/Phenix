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


class PositionTracking:
    """
    Position tracking component that processes trades and calculates portfolio state.

    Subscribes to EVT:TRADE_EXECUTED and emits EVT:PORTFOLIO_STATE_UPDATED.
    """

    # Підтримувані активи для включення в equity розрахунок
    SUPPORTED_EQUITY_ASSETS = {
        'USDT', 'BUSD', 'BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'DOT', 'LINK', 'UNI'
    }

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # Subscribe to events
        self.fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)
        self.fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", self.on_account_update)
        self.fsm.listen("EVT:BALANCE_UPDATE_RECEIVED", self.on_balance_update)

        # State tracking
        self._positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position data
        self._realized_pnl: decimal.Decimal = decimal.Decimal('0')
        self._total_commissions: decimal.Decimal = decimal.Decimal('0.0')  # NEW: Track total commissions
        self._equity: decimal.Decimal = decimal.Decimal('0')  # Will be loaded from account
        self._initial_balance: Optional[decimal.Decimal] = None  # Initial wallet balance (AURORA_STATE_SYNC_V1)

    def start(self) -> None:
        """Start the position tracking component (subscription already done in __init__)."""
        pass

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
                "timestamp": time.time()
            }
            wal_hash = wal.append(event_dict)
            if wal_hash is None:
                # WAL write failed due to lock timeout
                self.logger.critical(
                    f"CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL (lock timeout). "
                    f"Halting processing for safety. RID={event.rid}"
                )
                return
            self.logger.debug(f"WAL: Appended TRADE_EXECUTED to WAL with hash={wal_hash[:8]}...")
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
        price = decimal.Decimal(str(payload["price"]))
        quantity = decimal.Decimal(str(payload["quantity"]))
        ts = payload["ts"]
        fees = decimal.Decimal(str(payload.get("fees", 0)))
        commission = decimal.Decimal(str(payload.get("commission", payload.get("fees", 0))))  # Use fees if commission not present
        commission_asset = payload.get("commission_asset", "USDT")  # NEW: Extract commission asset
        venue = payload["venue"]

        # Convert side to quantity sign
        if side == "buy":
            qty = abs(quantity)
        elif side == "sell":
            qty = -abs(quantity)
        else:
            raise ValueError(f"Invalid side: {side}")

        # Update position and calculate P&L
        self._update_position(symbol, qty, price, fees, venue, commission)

        # Emit portfolio state updated event
        portfolio_payload = {
            "ts": ts,
            "equity": str(self._equity),  # Preserve Decimal precision as string
            "realized_pnl": str(self._realized_pnl),  # Preserve Decimal precision as string
            "unrealized_pnl": str(self._calculate_unrealized_pnl()),  # Preserve Decimal precision as string
            "total_commissions": str(self._total_commissions),  # NEW: Include total commissions
            "positions": self._get_positions_snapshot()
        }

        # Emit portfolio state updated event
        self.logger.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=f"Portfolio updated after trade execution for {symbol}."
        )

        self.logger.info(f"Emitted portfolio update after trade for {symbol}.")

    def _emit_portfolio_update(self, why: str):
        """Constructs and emits the EVT:PORTFOLIO_STATE_UPDATED event."""
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            "equity": str(self._equity),
            "realized_pnl": str(self._realized_pnl),
            "unrealized_pnl": str(self._calculate_unrealized_pnl()),
            "total_commissions": str(self._total_commissions),
            "positions": self._get_positions_snapshot()
        }
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why=why
        )
        self.logger.info(f"Emitted EVT:PORTFOLIO_STATE_UPDATED because: {why}")

    def on_account_update(self, event: Message) -> None:
        """
        Handles account updates by performing a full state reconciliation.
        This treats the incoming message as the single source of truth for open positions.
        """
        self.logger.info("Handling EVT:ACCOUNT_UPDATE_RECEIVED for full state reconciliation...")
        payload = event.pld
        
        real_positions_from_api = {pos['symbol']: pos for pos in payload.get('positions', [])}
        internal_positions_before_sync = set(self._positions.keys())
        reconciled_positions = {}

        # Rebuild the positions dictionary from the ground truth
        for symbol, pos_data_from_api in real_positions_from_api.items():
            net_position = decimal.Decimal(str(pos_data_from_api.get('positionAmt', '0')))
            if net_position == 0:
                continue # Skip flat positions

            new_position = {
                'net_position': net_position,
                'avg_entry_price': decimal.Decimal(str(pos_data_from_api.get('entryPrice', '0'))),
                'unrealized_pnl': decimal.Decimal(str(pos_data_from_api.get('unRealizedProfit', '0'))),
                'last_update_ts': int(pos_data_from_api.get('updateTime', 0)),
                'venues': []  # Initialize empty venues list for account update positions
            }

            # Preserve realized PnL if the position already existed
            if symbol in self._positions:
                new_position['realized_pnl'] = self._positions[symbol].get('realized_pnl', decimal.Decimal('0'))
            else:
                new_position['realized_pnl'] = decimal.Decimal('0')
            
            reconciled_positions[symbol] = new_position

        # Identify and log ghost positions that were removed
        ghost_positions = internal_positions_before_sync - set(reconciled_positions.keys())
        if ghost_positions:
            self.logger.warning(f"Reconciliation removed {len(ghost_positions)} ghost position(s): {', '.join(ghost_positions)}")

        self._positions = reconciled_positions
        self._equity = decimal.Decimal(str(payload.get('totalWalletBalance', payload.get('wallet_balance', '0'))))
        
        self.logger.info(f"Reconciled portfolio state: equity={self._equity}, open_positions={len(self._positions)}")
        self._emit_portfolio_update("full_sync_from_account_update")

    def on_balance_update(self, event: Message) -> None:
        """
        Handle incoming balance update event from Binance API.

        Args:
            event: FSM event with balance payload
        """
        self.logger.info("Handling EVT:BALANCE_UPDATE_RECEIVED...")
        payload = event.pld

        # Calculate total equity from assets (only supported trading assets)
        assets = payload.get('assets', [])
        supported_assets = [
            asset for asset in assets 
            if asset.get('asset') in self.SUPPORTED_EQUITY_ASSETS
        ]
        total_equity = sum(decimal.Decimal(str(a.get('balance', '0'))) for a in supported_assets)
        self._equity = total_equity  # Update our equity tracking
        
        self.logger.info(f"Balance update received: {len(assets)} total assets, {len(supported_assets)} supported for equity")
        # Log equity calculation breakdown
        if supported_assets:
            self.logger.info("Equity calculation breakdown (supported assets only):")
            for asset in supported_assets:
                asset_name = asset.get('asset', 'UNKNOWN')
                balance = asset.get('balance', '0')
                self.logger.info(f"  {asset_name}: {balance}")
            self.logger.info(f"Total equity: {total_equity}")
        else:
            self.logger.warning("No supported assets found for equity calculation!")
            
        # Log excluded assets for transparency
        excluded_assets = [
            asset for asset in assets 
            if asset.get('asset') not in self.SUPPORTED_EQUITY_ASSETS
        ]
        if excluded_assets:
            self.logger.info("Excluded assets (not supported for trading):")
            for asset in excluded_assets:
                asset_name = asset.get('asset', 'UNKNOWN')
                balance = asset.get('balance', '0')
                self.logger.info(f"  {asset_name}: {balance} (excluded)")
                
        self.logger.info(f"Calculated total equity: ${total_equity}")
        self.logger.info(f"Updated self._equity to: ${self._equity}")

        # Emit portfolio state updated event to initialize DecisionMaking
        # This is important for the first trade decision before any trades are executed
        portfolio_payload = {
            "ts": int(time.time() * 1000),
            "equity": str(self._equity),  # Preserve Decimal precision as string
            "realized_pnl": str(self._realized_pnl),  # Preserve Decimal precision as string
            "unrealized_pnl": "0",
            "available_balance": str(total_equity),
            "positions": self._get_positions_snapshot()
        }

        self.logger.info(f"Portfolio payload equity: {portfolio_payload['equity']}")
        self.logger.info("✅ Emitting EVT:PORTFOLIO_STATE_UPDATED from balance update...")
        self.fsm.emit(
            "EVT:PORTFOLIO_STATE_UPDATED",
            payload=portfolio_payload,
            why="Initial portfolio state from balance update for DecisionMaking"
        )

    def _update_position(self, symbol: str, quantity: decimal.Decimal, price: decimal.Decimal, fees: decimal.Decimal, venue: str, commission: decimal.Decimal = decimal.Decimal('0')) -> None:
        """
        Update position for a symbol and calculate realized P&L.

        Based on aurora/positions/ logic adapted for FSM events.
        """
        existing = self._positions.get(symbol, {
            "net_position": decimal.Decimal('0'),
            "avg_entry_price": decimal.Decimal('0'),
            "venues": []
        })

        pos_qty = existing["net_position"]
        avg_px = existing["avg_entry_price"]

        # Determine position sign based on existing position (+1 long, -1 short)
        pos_sign = decimal.Decimal('1') if pos_qty > decimal.Decimal('0') else decimal.Decimal('-1') if pos_qty < decimal.Decimal('0') else decimal.Decimal('0')

        # Realized PnL accrues only when trade reduces/offsets existing position
        realized_delta = decimal.Decimal('0')
        if pos_sign != decimal.Decimal('0') and quantity * pos_qty < decimal.Decimal('0'):
            closed_qty = min(abs(pos_qty), abs(quantity))
            # sign * qty_closed * (fill_px - avg_entry_px) - fees (keep fees for backward compatibility)
            realized_delta = pos_sign * closed_qty * (price - avg_px) - fees

        # Update realized P&L (subtract commission separately if different from fees)
        if commission != fees:
            self._realized_pnl += (realized_delta - commission)
        else:
            self._realized_pnl += realized_delta
        
        # Accumulate total commissions
        self._total_commissions += commission

        self.logger.info(f"TRADE_PNL: Realized PnL {realized_delta:.4f}, Commission {commission:.4f}, Net PnL {realized_delta - commission:.4f}")

        # Update position quantity and average entry price
        new_qty = pos_qty + quantity
        if abs(new_qty) < decimal.Decimal('1e-12'):
            # Flat position resets avg price
            new_avg = decimal.Decimal('0')
            venues = [venue]
        else:
            # Weighted average for same-side accumulation; if crossing through zero,
            # the new avg becomes current trade price for the residual side.
            if pos_qty == decimal.Decimal('0') or (pos_qty * quantity > decimal.Decimal('0')):
                # Same-side accumulation: recompute weighted average
                new_avg = (pos_qty * avg_px + quantity * price) / new_qty
            else:
                # Opposite-side trade
                if abs(quantity) < abs(pos_qty):
                    # Partial close: keep prior average for remaining open qty
                    new_avg = avg_px
                elif abs(quantity) == abs(pos_qty):
                    # Fully closed handled by flat branch above, but keep consistency
                    new_avg = decimal.Decimal('0')
                else:
                    # Crossed through zero (flip): new position avg is current fill price
                    new_avg = price

            # Update venues list
            existing_venues = existing["venues"]
            venues = list(set(existing_venues + [venue]))

        # Update position
        self._positions[symbol] = {
            "net_position": new_qty,
            "avg_entry_price": new_avg,
            "venues": venues
        }

    def _calculate_unrealized_pnl(self) -> decimal.Decimal:
        """
        Calculate unrealized P&L based on current positions.

        For simplicity, assumes current price = last trade price (stored in position).
        In real implementation, this would use current market prices.
        """
        unrealized = decimal.Decimal('0')
        for symbol, position in self._positions.items():
            # For this simple implementation, assume unrealized P&L is 0
            # In real system, would need current market price
            pass
        return unrealized

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """Returns a copy of the internal positions dictionary."""
        return self._positions.copy()

    def _get_positions_snapshot(self) -> List[Dict[str, Any]]:
        """
        Get current positions snapshot in the format expected by portfolio_state_v1.json.
        """
        positions = []
        for symbol, position in self._positions.items():
            if abs(position["net_position"]) > decimal.Decimal('1e-9'):  # Only include non-zero positions
                positions.append({
                    "symbol": symbol,
                    "net_position": str(position["net_position"]),  # Preserve Decimal precision as string
                    "avg_entry_price": str(position["avg_entry_price"]),  # Preserve Decimal precision as string
                    "venues": position["venues"]
                })
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
            if abs(position["net_position"]) > decimal.Decimal('1e-9'):  # Only include non-zero positions
                qty = position["net_position"]
                positions_state[symbol] = {
                    "net_position": str(qty),
                    "avg_entry_price": str(position["avg_entry_price"]),
                    "side": "long" if qty > 0 else "short",
                    "unrealized_pnl": "0.0"  # Placeholder - would need current market price
                }
        
        # Build portfolio state with precision preservation
        portfolio_state = {
            "equity": str(self._equity),
            "balance": str(self._equity - self._realized_pnl),  # Simplified calculation
            "margin_used": "0.0",  # Placeholder - would need real margin calculation
            "total_commissions": str(self._total_commissions)  # NEW: Include total commissions
        }
        
        # Complete state object
        state_data = {
            "positions": positions_state,
            "portfolio": portfolio_state
        }
        
        # Compute state hash for integrity verification
        state_str = json.dumps(state_data, sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode('utf-8')).hexdigest()
        
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
                "sequence_number": int(time.time() * 1000)  # Use timestamp as sequence for now
            }
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
            state_to_load = snapshot_data['state']
            state_hash_field = snapshot_data.get('state_hash', '')
            expected_hash = state_hash_field.split(':')[-1] if state_hash_field else None

            # Verify integrity
            state_str = json.dumps(state_to_load, sort_keys=True)
            actual_hash = hashlib.sha256(state_str.encode('utf-8')).hexdigest()

            if expected_hash and actual_hash != expected_hash:
                self.logger.error(
                    f"Snapshot integrity check failed! Expected hash {expected_hash}, got {actual_hash}."
                )
                return False

            # Restore positions (convert strings back to Decimal)
            positions_loaded: Dict[str, Dict[str, Any]] = {}
            for symbol, pos in state_to_load.get('positions', {}).items():
                try:
                    qty = decimal.Decimal(str(pos.get('net_position', '0')))
                    avg_price = decimal.Decimal(str(pos.get('avg_entry_price', '0')))
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    self.logger.error(f"Invalid numeric in snapshot for {symbol}: {e}")
                    return False

                positions_loaded[symbol] = {
                    'net_position': qty,
                    'avg_entry_price': avg_price,
                    'venues': pos.get('venues', [])
                }

            # Restore portfolio/equity if present
            portfolio = state_to_load.get('portfolio', {})
            equity_str = portfolio.get('equity')
            balance_str = portfolio.get('balance')
            commissions_str = portfolio.get('total_commissions')  # NEW: Restore total commissions

            if equity_str is not None:
                try:
                    self._equity = decimal.Decimal(str(equity_str))
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.error("Invalid equity value in snapshot")
                    return False

            # Restore total commissions if present
            if commissions_str is not None:
                try:
                    self._total_commissions = decimal.Decimal(str(commissions_str))
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.error("Invalid total_commissions value in snapshot")
                    return False

            # Try to reconstruct realized pnl if balance provided: realized = equity - balance
            if balance_str is not None:
                try:
                    balance_dec = decimal.Decimal(str(balance_str))
                    # realized_pnl = equity - balance
                    self._realized_pnl = self._equity - balance_dec
                except (ValueError, TypeError, decimal.InvalidOperation):
                    self.logger.warning("Invalid balance value in snapshot; leaving realized_pnl unchanged")

            # Apply restored positions
            self._positions = positions_loaded

            self.logger.info(
                f"Successfully loaded state from snapshot created at {snapshot_data.get('timestamp_utc', 'unknown')}. "
                f"Restored {len(self._positions)} positions."
            )

            return True

        except KeyError as e:
            self.logger.critical(f"Failed to load snapshot due to missing key: {e}")
            return False
        except (TypeError, json.JSONDecodeError) as e:
            self.logger.critical(f"Failed to load snapshot due to invalid format: {e}")
            return False

    def stop(self) -> None:
        """Stop the position tracking component."""
        self.logger.info("PositionTracking stopped")
