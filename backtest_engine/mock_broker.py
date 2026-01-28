"""
Mock Broker Module
==================

Provides a "Digital Twin" of the exchange for backtesting.
Implements the AbstractExchangeAdapter interface using in-memory state.
"""

import logging
import uuid
import time
import random
from typing import Any, Dict, List, Optional

from vfoundation.core.adapters.base import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)

# Import clock abstraction for consistent time in backtest
try:
    from apps.reference.core.time import get_clock
except ImportError:
    # Fallback: use wall-clock if import fails
    class _FallbackClock:
        def now_ms(self) -> int:
            return int(time.time() * 1000)
    def get_clock():
        return _FallbackClock()

LOG = logging.getLogger(__name__)


class MockBroker(AbstractExchangeAdapter):
    """
    In-memory simulation of an exchange broker.
    
    Features:
    - Order Book management (LIMIT, MARKET, STOP)
    - Position tracking (Avg Price, Size, PnL)
    - Account Balance management
    - Commission simulation
    - Latency simulation (optional - currently 0ms)
    
    Realism Features (Hardening):
    - SL Priority: Stop-loss orders execute BEFORE take-profit in same-bar conflicts
    - Trade-Through: Limit orders require price to trade THROUGH limit (not just touch)
    - Slippage: Market orders incur configurable slippage (default 2 bps)
    - Volume Cap: Orders capped at % of bar volume (default 5%)
    """

    def __init__(
        self,
        initial_balance_usdt: float = 10000.0,
        commission_maker: float = 0.0002,
        commission_taker: float = 0.0004,
        leverage_map: Optional[Dict[str, int]] = None,
        # Realism parameters (Backtest Hardening)
        slippage_bps: float = 2.0,  # Default 2 bps slippage for market orders
        slippage_map: Optional[Dict[str, float]] = None,  # Per-symbol slippage override
        fill_probability_at_touch: float = 0.0,  # Probability of fill when price == limit (0.0 = conservative)
        max_volume_participation: float = 0.05,  # Max 5% of bar volume per order
    ):
        self.initial_balance = initial_balance_usdt
        self.balance_usdt = initial_balance_usdt
        self.commission_maker = commission_maker
        self.commission_taker = commission_taker
        # Leverage map from config (symbol -> leverage), default 20x for all
        self.leverage_map = leverage_map or {"__default__": 20}

        # Exchange-like attributes expected by ExecPosFSM safety checks/logging.
        self.base_url = "mock://backtest"

        # Optional backrefs (wired by BacktestExecPosFSM wrapper)
        self.exec_fsm: Any | None = None
        self.fsm_core: Any | None = None
        
        # Realism parameters (Backtest Hardening)
        self._slippage_bps = slippage_bps
        self._slippage_map = slippage_map or {}
        self._fill_probability_at_touch = fill_probability_at_touch
        self._max_volume_participation = max_volume_participation
        
        # State
        self._orders: Dict[str, ExchangeOrderResponse] = {} # order_id -> Order
        self._order_meta: Dict[str, Dict[str, Any]] = {}  # order_id -> metadata (type/reduceOnly/stopPrice/avgPrice...)
        self._positions: Dict[str, ExchangePosition] = {} # symbol -> Position
        self._client_order_map: Dict[str, str] = {} # client_order_id -> order_id
        self._fills: List[Dict[str, Any]] = []
        self._pending_acks: List[str] = []
        
        # Trade PnL tracking for Win Rate calculation
        self._trade_pnl_history: List[float] = []  # realized PnL per closed trade
        
        # Equity history for Max Drawdown calculation  
        self._equity_history: List[float] = [initial_balance_usdt]
        
        # Market Data State (Last seen price)
        self._last_prices: Dict[str, float] = {}
        
        # Cancelled orders tracking (for SL priority logic)
        self._cancelled_this_bar: set[str] = set()

    # --- Realism Helpers ---
    
    def _get_slippage(self, symbol: str) -> float:
        """Get slippage multiplier for symbol. Returns 0.0002 for 2 bps."""
        bps = self._slippage_map.get(symbol, self._slippage_bps)
        return bps / 10000.0
    
    def _check_volume_cap(self, qty: float, bar_volume: float) -> float:
        """Cap order quantity to max % of bar volume."""
        if bar_volume <= 0 or self._max_volume_participation <= 0:
            return qty
        max_qty = bar_volume * self._max_volume_participation
        return min(qty, max_qty)

    # --- Market Simulation Methods ---

    def process_data(self, candle_or_tick: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Matching Engine: Process incoming market data and fill orders.
        
        HARDENING (Worst-Case Execution):
        1. SL Priority: STOP_MARKET orders checked BEFORE TAKE_PROFIT_MARKET
        2. Trade-Through: Limit orders require price to trade THROUGH limit (not touch)
        3. Slippage: Market orders incur configurable slippage
        4. Volume Cap: Orders capped at % of bar volume
        
        Args:
            candle_or_tick: Dictionary containing 'symbol', 'open', 'high', 'low', 'close', 'volume' OR 'price'.
                            
        Returns:
            List of fill event payloads (dicts) for any orders filled during this step.
        """
        fills = []
        symbol = candle_or_tick.get('symbol')
        if not symbol:
            return []

        # Reset per-bar tracking
        self._cancelled_this_bar.clear()

        # Determine price points for matching
        current_price = float(candle_or_tick.get('close', candle_or_tick.get('price', 0)))
        high_price = float(candle_or_tick.get('high', current_price))
        low_price = float(candle_or_tick.get('low', current_price))
        bar_volume = float(candle_or_tick.get('volume', 0))
        
        self._last_prices[symbol] = current_price
        
        # Collect active orders for this symbol
        active_orders = [
            (oid, self._orders[oid])
            for oid in list(self._orders.keys())
            if self._orders[oid].symbol == symbol and self._orders[oid].status == "ACCEPTED"
        ]
        
        # --- PHASE 1: Identify SL and TP orders ---
        sl_orders = []  # STOP_MARKET
        tp_orders = []  # TAKE_PROFIT_MARKET
        other_orders = []  # LIMIT, MARKET, etc.
        
        for oid, order in active_orders:
            meta = self._order_meta.get(oid, {})
            order_type = str(meta.get("type") or "").upper()
            if order_type == "STOP_MARKET":
                sl_orders.append((oid, order, meta))
            elif order_type == "TAKE_PROFIT_MARKET":
                tp_orders.append((oid, order, meta))
            else:
                other_orders.append((oid, order, meta))
        
        # --- PHASE 2: Process SL FIRST (Worst-Case Assumption) ---
        for oid, order, meta in sl_orders:
            if oid in self._cancelled_this_bar:
                continue
            fill_result = self._try_fill_order(
                oid, order, meta, current_price, high_price, low_price, bar_volume
            )
            if fill_result:
                fills.append(fill_result)
                # Cancel related TP orders for same position (SL wins)
                self._cancel_related_bracket_orders(symbol, oid, tp_orders)
        
        # --- PHASE 3: Process TP (only if SL didn't trigger) ---
        for oid, order, meta in tp_orders:
            if oid in self._cancelled_this_bar:
                continue
            fill_result = self._try_fill_order(
                oid, order, meta, current_price, high_price, low_price, bar_volume
            )
            if fill_result:
                fills.append(fill_result)
        
        # --- PHASE 4: Process other orders (LIMIT, MARKET) ---
        for oid, order, meta in other_orders:
            if oid in self._cancelled_this_bar:
                continue
            fill_result = self._try_fill_order(
                oid, order, meta, current_price, high_price, low_price, bar_volume
            )
            if fill_result:
                fills.append(fill_result)

        return fills

    def _try_fill_order(
        self,
        order_id: str,
        order: ExchangeOrderResponse,
        meta: Dict[str, Any],
        current_price: float,
        high_price: float,
        low_price: float,
        bar_volume: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to fill a single order with hardened matching logic.
        
        Returns fill event dict if filled, None otherwise.
        """
        filled = False
        fill_price = current_price
        role = "TAKER"
        symbol = order.symbol

        try:
            qty = float(order.quantity)
            limit_price = float(order.price) if order.price else None
            stop_price = float(meta.get("stopPrice")) if meta.get("stopPrice") is not None else None
        except Exception:
            return None
            
        if qty <= 0 and bool(meta.get("closePosition")):
            try:
                pos = self._positions.get(symbol)
                if pos is None:
                    return None
                qty = abs(float(pos.position_amount))
                if qty <= 0:
                    return None
            except Exception:
                return None

        side = order.side.upper()
        order_type = str(meta.get("type") or "").upper()
        if not order_type:
            order_type = "LIMIT" if limit_price is not None else "MARKET"
        
        # --- LIMIT: Trade-Through Logic ---
        if order_type == "LIMIT" and limit_price is not None:
            if side == "BUY":
                # Trade-Through: low must be BELOW limit (not equal)
                if low_price < limit_price:
                    filled = True
                    fill_price = limit_price
                    role = "MAKER"
                # Touch: probability-based fill
                elif low_price == limit_price and random.random() < self._fill_probability_at_touch:
                    filled = True
                    fill_price = limit_price
                    role = "MAKER"
            elif side == "SELL":
                # Trade-Through: high must be ABOVE limit (not equal)
                if high_price > limit_price:
                    filled = True
                    fill_price = limit_price
                    role = "MAKER"
                # Touch: probability-based fill
                elif high_price == limit_price and random.random() < self._fill_probability_at_touch:
                    filled = True
                    fill_price = limit_price
                    role = "MAKER"
                    
        # --- MARKET: Apply Slippage ---
        elif order_type == "MARKET":
            filled = True
            slippage = self._get_slippage(symbol)
            if side == "BUY":
                fill_price = current_price * (1 + slippage)
            else:
                fill_price = current_price * (1 - slippage)
            role = "TAKER"
            
        # --- STOP_MARKET (SL) ---
        elif order_type == "STOP_MARKET" and stop_price is not None:
            if side == "SELL" and low_price <= stop_price:
                filled = True
            elif side == "BUY" and high_price >= stop_price:
                filled = True
            if filled:
                # Apply slippage to stop execution price
                slippage = self._get_slippage(symbol)
                if side == "BUY":
                    fill_price = current_price * (1 + slippage)
                else:
                    fill_price = current_price * (1 - slippage)
                role = "TAKER"
                
        # --- TAKE_PROFIT_MARKET (TP) ---
        elif order_type == "TAKE_PROFIT_MARKET" and stop_price is not None:
            if side == "SELL" and high_price >= stop_price:
                filled = True
            elif side == "BUY" and low_price <= stop_price:
                filled = True
            if filled:
                # Apply slippage to TP execution price
                slippage = self._get_slippage(symbol)
                if side == "BUY":
                    fill_price = current_price * (1 + slippage)
                else:
                    fill_price = current_price * (1 - slippage)
                role = "TAKER"

        if not filled:
            return None
            
        # Apply volume participation cap
        if bar_volume > 0:
            qty = self._check_volume_cap(qty, bar_volume)
            if qty <= 0:
                LOG.debug(f"[MockBroker] Order {order_id} skipped: volume cap exceeded")
                return None

        return self._execute_fill(order_id, fill_price, qty, role, side, symbol)

    def _cancel_related_bracket_orders(
        self,
        symbol: str,
        triggered_order_id: str,
        tp_orders: List[tuple],
    ) -> None:
        """
        Cancel related TP orders when SL triggers (SL Priority rule).
        
        In bracket orders (entry + SL + TP), when SL fills, TP should be cancelled.
        """
        for oid, order, meta in tp_orders:
            if order.symbol == symbol and oid != triggered_order_id:
                if oid not in self._cancelled_this_bar:
                    self._orders[oid].status = "CANCELED"
                    self._cancelled_this_bar.add(oid)
                    LOG.debug(f"[MockBroker] Cancelled TP {oid} due to SL priority")

    def _order_to_dict(self, order_id: str) -> Dict[str, Any]:
        """Convert internal order record to exchange-like dict (Binance-ish keys)."""
        order = self._orders[order_id]
        meta = self._order_meta.get(order_id, {})
        out = order.to_dict()
        out.update(
            {
                "type": meta.get("type") or ("LIMIT" if order.price is not None else "MARKET"),
                "timeInForce": meta.get("timeInForce", "GTC"),
                "reduceOnly": bool(meta.get("reduceOnly", False)),
                "closePosition": bool(meta.get("closePosition", False)),
            }
        )
        if meta.get("stopPrice") is not None:
            out["stopPrice"] = str(meta.get("stopPrice"))
        if meta.get("avgPrice") is not None:
            out["avgPrice"] = str(meta.get("avgPrice"))
        return out

    def _lookup_rid(self, *, order_id: str, client_order_id: Optional[str]) -> Optional[str]:
        """Best-effort correlation lookup for fill/ack payloads (keeps ExecPosFSM caches working)."""
        try:
            idx = getattr(self.fsm_core, "order_index", None)
            if idx is None:
                return None

            ref = None
            try:
                ref = idx.get(exchangeOrderId=str(order_id))
            except Exception:
                ref = None
            if ref is None and client_order_id:
                try:
                    ref = idx.get(clientOrderId=str(client_order_id))
                except Exception:
                    ref = None
            if ref is None:
                return None
            return getattr(ref, "rid", None) or (ref.get("rid") if isinstance(ref, dict) else None)
        except Exception:
            return None

    def _emit_order_ack(self, *, order_id: str) -> None:
        """Emit EVT:ORDER_ACK on attached event bus if available (no network, local only)."""
        if not self.fsm_core or not hasattr(self.fsm_core, "emit"):
            return
        try:
            d = self._order_to_dict(order_id)
            rid = self._lookup_rid(order_id=order_id, client_order_id=d.get("clientOrderId"))
            if rid:
                d["rid"] = rid
            self.fsm_core.emit("EVT:ORDER_ACK", d, "mock_ack")
        except Exception:
            pass

    def flush_acks(self) -> None:
        """Emit any pending ACK events from the engine thread (keeps watchdog ordering sane)."""
        if not self._pending_acks:
            return
        pending = self._pending_acks
        self._pending_acks = []
        for oid in pending:
            self._emit_order_ack(order_id=oid)

    async def get_order(self, symbol: str, order_id: str | int) -> Optional[Dict[str, Any]]:
        """Async order lookup for OrderTimeoutWatchdog REST polling hooks."""
        oid = str(order_id)
        order = self._orders.get(oid)
        if order is None:
            return None
        if symbol and order.symbol != symbol:
            return None
        return self._order_to_dict(oid)


    def _execute_fill(self, order_id: str, price: float, qty: float, role: str, side: str, symbol: str) -> Dict[str, Any]:
        """Execute the trade: update order status, position, and balance. Returns fill payload."""
        order = self._orders[order_id]
        order.status = "FILLED"
        order.filled_qty = str(qty)
        self._order_meta.setdefault(order_id, {})["avgPrice"] = price
        # order.avg_price = str(price) # Response doesn't have avg_price field in basic generic? 
        # Base ExchangeOrderResponse typically expects 'price' to be the requested price.
        # But for 'FILLED', the adapter often returns the fill avg price in some fields?
        # The base dataclass has 'price: Optional[str]'. We leave it as requested price or update?
        # Usually 'price' in response is the Limit Price.
        
        # Calculate Fees
        value = price * qty
        fee_rate = self.commission_maker if role == "MAKER" else self.commission_taker
        fee = value * fee_rate
        self.balance_usdt -= fee
        
        LOG.debug(f"[MockBroker] FIllED {side} {symbol} {qty} @ {price}. Fee: {fee:.4f}")

        # Update Position
        pos_side = "LONG" if side == "BUY" else "SHORT"
        
        # Basic Netting Mode (Single Position per Symbol - 'BOTH' side simplified or Hedge)
        # Assuming Hedge Mode for consistency with Adapter? 
        # Our adapter supports "positionSide" param.
        # Let's verify 'ExchangeOrderParams'. It has 'position_side'.
        
        # For simplicity in Phase 1: We assume Net Mode if position_side not provided, 
        # or respect Hedge if provided. But 'side' in Position is computed from amt.
        
        # Let's simplify: Maintain one position per symbol.
        if symbol not in self._positions:
            self._positions[symbol] = ExchangePosition(
                symbol=symbol,
                position_side="BOTH",
                side="FLAT",
                position_amount="0",
                entry_price="0",
                mark_price=str(price),
                unrealized_profit="0",
                leverage=self.leverage_map.get(symbol, self.leverage_map.get("__default__", 20)),  # Use config leverage
                margin_type="CROSS",
                isolated_margin=0.0,
                update_time_ms=get_clock().now_ms()  # Use simulated clock
            )

        pos = self._positions[symbol]
        curr_amt = float(pos.position_amount)
        curr_entry = float(pos.entry_price)
        
        # Direction
        qty_signed = qty if side == "BUY" else -qty
        new_amt = curr_amt + qty_signed
        
        # Update Average Entry Price
        if curr_amt == 0:
            new_entry = price
        elif (curr_amt > 0 and qty_signed > 0) or (curr_amt < 0 and qty_signed < 0):
            # Increasing position -> Weighted Average
            total_cost = (abs(curr_amt) * curr_entry) + (qty * price)
            new_entry = total_cost / abs(new_amt)
        elif (curr_amt > 0 and qty_signed < 0) or (curr_amt < 0 and qty_signed > 0):
            # Reducing position -> Entry price stays same (realizing PnL)
            new_entry = curr_entry
            # Calc Realized PnL to update balance
            closed_qty = min(abs(curr_amt), abs(qty_signed))
            pnl = (price - curr_entry) * closed_qty if curr_amt > 0 else (curr_entry - price) * closed_qty
            self.balance_usdt += pnl
            LOG.debug(f"[MockBroker] Realized PnL: {pnl:.4f}")
            
            # Track trade PnL for Win Rate calculation
            self._trade_pnl_history.append(pnl)
            
            # Update equity history for Drawdown tracking
            self._equity_history.append(self.balance_usdt)
            
            # If flipping position
            if (curr_amt > 0 and new_amt < 0) or (curr_amt < 0 and new_amt > 0):
                # Remainder is new position at new price
                new_entry = price
        else:
            new_entry = price # Should not happen

        # Update Position Object
        pos.position_amount = str(new_amt)
        pos.entry_price = str(new_entry) if new_amt != 0 else "0"
        pos.side = "LONG" if new_amt > 0 else ("SHORT" if new_amt < 0 else "FLAT")
        pos.update_time_ms = get_clock().now_ms()  # Use simulated clock
        
        # Clean up zero positions? Or keep as Flat
        if new_amt == 0:
            pos.side = "FLAT"

        payload: Dict[str, Any] = {
            "orderId": str(order_id),
            "symbol": symbol,
            "side": side,
            "quantity": str(qty),
            "price": str(price),
            "filled_qty": str(qty),
            "fee": str(fee),
            "fee_asset": "USDT",
            "role": role,
            "timestamp": get_clock().now_ms(),  # Use simulated clock
            "clientOrderId": order.client_order_id,
            "status": "FILLED",
        }
        rid = self._lookup_rid(order_id=str(order_id), client_order_id=order.client_order_id)
        if rid:
            payload["rid"] = rid

        self._fills.append(payload)
        return payload


    # --- Interface Implementation ---

    async def create_order(self, params: ExchangeOrderParams) -> ExchangeOrderResponse:
        order_id = str(uuid.uuid4())
        
        # Validation simulation
        if params.quantity and float(params.quantity) <= 0 and not bool(params.close_position):
             raise ValueError("Quantity must be positive")
             
        # Store order
        # We need to store 'stop_price' if it exists, but ExchangeOrderResponse structure is fixed.
        # We will abuse 'reason' or subclass if strictly needed, but better handling -> separate internal store?
        # For strict matching, we'll store params separately? 
        # Actually I can just add attributes dynamically to the object in Python.
        
        response = ExchangeOrderResponse(
            order_id=order_id,
            client_order_id=params.client_order_id,
            symbol=params.symbol,
            side=params.side,
            quantity=params.quantity,
            filled_qty="0",
            price=params.price,
            status="ACCEPTED", # New
            timestamp_ms=get_clock().now_ms(),  # Use simulated clock
            reason=None
        )

        self._orders[order_id] = response
        self._order_meta[order_id] = {
            "type": str(params.order_type).upper(),
            "timeInForce": str(params.time_in_force).upper() if params.time_in_force else "GTC",
            "reduceOnly": bool(params.reduce_only),
            "closePosition": bool(params.close_position),
            "stopPrice": params.stop_price,
            "avgPrice": None,
        }
        if params.client_order_id:
            self._client_order_map[params.client_order_id] = order_id

        # Defer ACK emission so ExecPosFSM can register watchdog tracking first.
        self._pending_acks.append(order_id)

        return response

    async def cancel_order(
        self, symbol: str, order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrderResponse:
        
        target_id = order_id
        if not target_id and client_order_id:
            target_id = self._client_order_map.get(client_order_id)
            
        if not target_id or target_id not in self._orders:
             # Mimic "Order not found" response or error
             # Adapter implementation usually raises or returns CANCELED if not found?
             # Based on BinanceAdapter, it raises error.
             raise Exception(f"Order {target_id} not found")

        order = self._orders[target_id]
        if order.status == "FILLED":
             raise Exception("Order already filled")
             
        order.status = "CANCELED"
        return order

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        active_ids = [oid for oid, o in self._orders.items() if o.status == "ACCEPTED" and (not symbol or o.symbol == symbol)]
        return [self._order_to_dict(oid) for oid in active_ids]

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[ExchangePosition]:
        # Update Unrealized PnL before returning
        result = []
        for sym, pos in self._positions.items():
            if symbol and sym != symbol:
                continue
            
            amt = float(pos.position_amount)
            if amt == 0:
                continue
                
            entry = float(pos.entry_price)
            curr_price = self._last_prices.get(sym, entry)
            
            # Update Mark Price & PnL
            pos.mark_price = str(curr_price)
            pnl = (curr_price - entry) * amt # Valid for Long (Ex: (110 - 100) * 1 = 10) and Short ((90 - 100) * -1 = 10)
            pos.unrealized_profit = str(pnl)
            
            result.append(pos)
        return result

    async def get_mark_price(self, symbol: str, ttl_ms: int = 250) -> float:
        return self._last_prices.get(symbol, 0.0)

    async def get_last_price(self, symbol: str) -> float:
        return self._last_prices.get(symbol, 0.0)

    async def get_account_balance(self) -> List[Dict[str, Any]]:
        # Simulate Binance Balance Response structure
         return [{
            "asset": "USDT",
            "balance": str(self.balance_usdt),
            "crossWalletBalance": str(self.balance_usdt),
            "availableBalance": str(self.balance_usdt) # Simplified (minus margin used)
        }]

    async def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        # Mimic valid exchange info to pass validations
        return {
            "symbols": [{
                 "symbol": symbol,
                 "status": "TRADING",
                 "baseAsset": symbol.replace("USDT", ""),
                 "quoteAsset": "USDT",
                 "filters": [
                     {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                     {"filterType": "PRICE_FILTER", "tickSize": "0.01"}
                 ]
            }]
        }

    async def quantize_quantity(self, symbol: str, qty: Any) -> str:
        # Simple string formatting for now
        return f"{float(qty):.3f}" 

    # --- ExecPosFSM-facing "BinanceAdapter-like" helpers (offline) ---

    def track_order(self, entry_resp: Dict[str, Any]) -> None:
        """No-op in backtest; watchdog + process_data drive fills."""
        return

    async def place_market_entry(
        self,
        symbol: str,
        side: str,
        quantity: str,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=str(quantity),
                client_order_id=new_client_order_id,
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_limit_entry(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        *,
        time_in_force: str = "GTC",
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=str(quantity),
                price=str(price),
                time_in_force=str(time_in_force),
                client_order_id=new_client_order_id,
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_market_reduce_only(
        self,
        symbol: str,
        side: str,
        quantity: str,
        *,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=str(quantity),
                reduce_only=True,
                client_order_id=new_client_order_id,
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        *,
        time_in_force: str = "GTC",
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=str(quantity),
                price=str(price),
                time_in_force=str(time_in_force),
                reduce_only=True,
                client_order_id=new_client_order_id,
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        *,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="STOP_MARKET",
                quantity="0",
                close_position=True,
                client_order_id=new_client_order_id,
                stop_price=str(stop_price),
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_take_profit_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        *,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resp = await self.create_order(
            ExchangeOrderParams(
                symbol=symbol,
                side=side,
                order_type="TAKE_PROFIT_MARKET",
                quantity="0",
                close_position=True,
                client_order_id=new_client_order_id,
                stop_price=str(stop_price),
            )
        )
        return self._order_to_dict(resp.order_id)

    async def place_order(self, msg: Any) -> Dict[str, Any]:
        """Legacy adapter hook used by ExecPosFSM for generic PLACE_ORDER."""
        pld = getattr(msg, "pld", None) or {}
        symbol = pld.get("symbol")
        side = pld.get("side")
        qty = pld.get("qty") or pld.get("quantity") or "0"
        order_type = str(pld.get("order_type") or pld.get("type") or "LIMIT").upper()
        price = pld.get("price")
        stop_price = pld.get("stopPrice") or pld.get("stop_price")
        client_id = pld.get("newClientOrderId") or pld.get("clientOrderId")
        reduce_only = bool(pld.get("reduceOnly") or pld.get("reduce_only"))
        close_position = bool(pld.get("closePosition") or pld.get("close_position"))
        tif = str(pld.get("timeInForce") or pld.get("tif") or "GTC")

        if not symbol or not side:
            raise ValueError("MockBroker.place_order requires symbol and side")

        if order_type == "MARKET":
            if reduce_only:
                return await self.place_market_reduce_only(symbol, side, str(qty), new_client_order_id=client_id)
            return await self.place_market_entry(symbol, side, str(qty), client_id)

        if order_type == "LIMIT":
            if price is None:
                raise ValueError("LIMIT requires price")
            if reduce_only:
                return await self.place_limit_reduce_only(symbol, side, str(price), str(qty), time_in_force=tif, new_client_order_id=client_id)
            return await self.place_limit_entry(symbol, side, str(price), str(qty), time_in_force=tif, new_client_order_id=client_id)

        if order_type == "STOP_MARKET":
            if stop_price is None:
                raise ValueError("STOP_MARKET requires stopPrice")
            return await self.place_stop_market_close_position(symbol, side, str(stop_price), new_client_order_id=client_id)

        if order_type == "TAKE_PROFIT_MARKET":
            if stop_price is None:
                raise ValueError("TAKE_PROFIT_MARKET requires stopPrice")
            return await self.place_take_profit_market_close_position(symbol, side, str(stop_price), new_client_order_id=client_id)

        raise ValueError(f"Unsupported order_type: {order_type}")

    async def aclose(self) -> None:
        pass
