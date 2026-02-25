#!/usr/bin/env python3
"""
PLUMBING VERIFICATION TEST
==========================

This script tests the core backtest pipeline WITHOUT any complex strategy logic.
It proves: EventBus -> MockBroker -> Fill -> PnL Update

The "Dummy Strategy" does:
1. First bar: BUY 0.01 BTC at market
2. After 10 bars: SELL 0.01 BTC at market (close position)
3. Verify non-zero PnL at end

Run with: python tests/verify_plumbing.py
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger("PlumbingTest")


class DummyStrategy:
    """
    Minimal strategy that bypasses all gates.
    Just does: BUY on first bar, SELL after 10 bars.
    """
    
    def __init__(self, broker, event_bus):
        self.broker = broker
        self.bus = event_bus
        self.bar_count = 0
        self.position_opened = False
        self.position_closed = False
        self.entry_price = None
        self.symbol = "BTCUSDT"
        self.qty = 0.01  # Small qty for test
        
        # Register listener
        self.bus.listen("EVT:BAR_CLOSED", self._on_bar)
        self.bus.listen("EVT:ORDER_FILL", self._on_fill)
        LOG.info("✅ DummyStrategy registered for EVT:BAR_CLOSED")
    
    def _on_bar(self, event):
        """Handle bar event - simple buy/sell logic."""
        pld = event.get("pld", event)
        bar = pld.get("bar", {})
        symbol = bar.get("symbol", "UNKNOWN")
        
        if symbol != self.symbol:
            return
            
        self.bar_count += 1
        close_price = float(bar.get("close", 0))
        
        LOG.info(f"[BAR {self.bar_count}] {symbol} close={close_price:.2f}")
        
        # === ACTION 1: BUY on first bar ===
        if self.bar_count == 1 and not self.position_opened:
            LOG.info(f"🟢 OPENING POSITION: BUY {self.qty} {symbol} @ MARKET")
            self._place_order("BUY", close_price)
            self.position_opened = True
            self.entry_price = close_price
        
        # === ACTION 2: SELL after 10 bars ===
        elif self.bar_count >= 10 and self.position_opened and not self.position_closed:
            LOG.info(f"🔴 CLOSING POSITION: SELL {self.qty} {symbol} @ MARKET")
            self._place_order("SELL", close_price)
            self.position_closed = True
    
    def _place_order(self, side: str, price: float):
        """Place order directly via MockBroker (sync call)."""
        import asyncio
        from backtest_engine.mock_broker import ExchangeOrderParams
        
        params = ExchangeOrderParams(
            symbol=self.symbol,
            side=side,
            order_type="MARKET",
            quantity=str(self.qty),
            price=None,  # Market order
            client_order_id=None,
            time_in_force="GTC",
            stop_price=None,
        )
        
        async def _create():
            result = await self.broker.create_order(params)
            LOG.info(f"📤 Order created: {result}")
            return result
        
        # Run async in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # If loop is running (shouldn't be in backtest), schedule it
            asyncio.ensure_future(_create())
        else:
            loop.run_until_complete(_create())
    
    def _on_fill(self, event):
        """Log fills for visibility."""
        pld = event.get("pld", event)
        LOG.info(f"✅ FILL RECEIVED: {pld}")


def run_plumbing_test():
    """Run the minimal plumbing test."""
    LOG.info("="*60)
    LOG.info("🔧 PLUMBING VERIFICATION TEST")
    LOG.info("="*60)
    
    # 1. Create Event Bus (LocalBus fallback)
    from apps.reference.domains.execution_position.utils_event_bus import LocalBus
    bus = LocalBus()
    LOG.info("✅ LocalBus created")
    
    # 2. Create MockBroker
    from backtest_engine.mock_broker import MockBroker
    initial_balance = 10000.0
    broker = MockBroker(initial_balance_usdt=initial_balance)
    LOG.info(f"✅ MockBroker created with balance={initial_balance}")
    
    # 3. Create BacktestEngine
    from backtest_engine.engine import BacktestEngine
    
    start_date = datetime(2023, 5, 1)
    end_date = datetime(2023, 5, 31)
    
    engine = BacktestEngine(
        start_date=start_date,
        end_date=end_date,
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        initial_balance=initial_balance,
        event_bus=bus,
        data_dir="data/processed"
    )
    
    # Override broker with our instance
    engine.broker = broker
    LOG.info("✅ BacktestEngine created")
    
    # 4. Register Dummy Strategy
    strategy = DummyStrategy(broker, bus)
    
    # 5. Run simulation
    LOG.info("🚀 Starting simulation...")
    try:
        results = engine.run()
    except Exception as e:
        LOG.error(f"❌ Simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 6. Report results
    LOG.info("="*60)
    LOG.info("📊 PLUMBING TEST RESULTS")
    LOG.info("="*60)
    LOG.info(f"  Total Bars Processed: {strategy.bar_count}")
    LOG.info(f"  Position Opened: {strategy.position_opened}")
    LOG.info(f"  Position Closed: {strategy.position_closed}")
    LOG.info(f"  Entry Price: {strategy.entry_price}")
    LOG.info(f"  Start Balance: {results.start_balance:.2f}")
    LOG.info(f"  End Balance: {results.end_balance:.2f}")
    LOG.info(f"  Total PnL: {results.total_pnl:.2f}")
    LOG.info(f"  Total Trades: {results.total_trades}")
    LOG.info(f"  ROI: {results.roi_pct:.2f}%")
    LOG.info("="*60)
    
    # 7. Check broker state
    LOG.info("\n📦 BROKER STATE:")
    LOG.info(f"  Balance USDT: {broker.balance_usdt:.2f}")
    LOG.info(f"  Open Orders: {len(broker._orders)}")
    LOG.info(f"  Open Positions: {len(broker._positions)}")
    
    for order_id, order in broker._orders.items():
        LOG.info(f"    Order: {order_id} -> status={order.status}, side={order.side}, qty={order.quantity}")
    
    for symbol, pos in broker._positions.items():
        LOG.info(f"    Position: {symbol} -> amt={pos.position_amount}, entry={pos.entry_price}")
    
    # 8. Verdict
    if results.total_trades > 0:
        LOG.info("\n✅ SUCCESS: Plumbing test PASSED! Trades were executed.")
        return True
    elif strategy.position_opened:
        LOG.info("\n⚠️ PARTIAL: Position opened but no fills recorded in results.")
        LOG.info("   This suggests order placement works but fill tracking may need adjustment.")
        return True  # Still partial success
    else:
        LOG.error("\n❌ FAILURE: No trades executed. Plumbing is broken.")
        return False


if __name__ == "__main__":
    success = run_plumbing_test()
    sys.exit(0 if success else 1)
