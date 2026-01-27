import sys
import os
import asyncio
import logging
from unittest import IsolatedAsyncioTestCase

# Add project root to path (robustly)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_engine.mock_broker import MockBroker
from vfoundation.core.adapters.base import ExchangeOrderParams

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class TestMockBroker(IsolatedAsyncioTestCase):
    
    async def test_limit_buy_fill(self):
        broker = MockBroker(initial_balance_usdt=10000.0)
        
        # 1. Place Limit Buy @ 100
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1.0",
            price="100.0"
        )
        response = await broker.create_order(params)
        self.assertEqual(response.status, "ACCEPTED")
        
        # 2. Process Data - High price (No Fill)
        candle_high = {"symbol": "BTCUSDT", "close": 101.0, "high": 102.0, "low": 100.5}
        broker.process_data(candle_high)
        
        orders = await broker.get_open_orders("BTCUSDT")
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["status"], "ACCEPTED")  # MockBroker returns dicts
        
        # 3. Process Data - Low price (Fill)
        candle_low = {"symbol": "BTCUSDT", "close": 99.0, "high": 100.0, "low": 98.0}
        broker.process_data(candle_low)
        
        # Check Fill
        orders = await broker.get_open_orders("BTCUSDT")
        self.assertEqual(len(orders), 0) # No open orders
        
        # Check Position
        positions = await broker.get_open_positions("BTCUSDT")
        self.assertEqual(len(positions), 1)
        self.assertEqual(float(positions[0].position_amount), 1.0)
        self.assertEqual(float(positions[0].entry_price), 100.0) # Filled at Limit Price for Maker
        
        # Check Balance (10000 - 100(cost is not deducted in futures usually, only margin? MockBroker deducted fee)
        # We didn't implement Margin Logic deduction from available balance fully, simply Fee deduction
        # 1.0 BTC * 100.0 = 100.0 Value. Maker Fee = 0.0002. Fee = 0.02
        expected_balance = 10000.0 - 0.02
        self.assertAlmostEqual(broker.balance_usdt, expected_balance)
        
    async def test_market_sell_fill(self):
        broker = MockBroker(initial_balance_usdt=10000.0)
        
        # 1. Place Market Sell
        params = ExchangeOrderParams(
            symbol="ETHUSDT",
            side="SELL",
            order_type="MARKET",
            quantity="5.0"
        )
        await broker.create_order(params)
        
        # 2. Process Data (Instant Fill)
        candle = {"symbol": "ETHUSDT", "close": 2000.0}
        broker.process_data(candle)
        
        # Check Position
        positions = await broker.get_open_positions("ETHUSDT")
        self.assertEqual(float(positions[0].position_amount), -5.0)
        self.assertEqual(float(positions[0].entry_price), 2000.0)
        
        # Fee: 5 * 2000 = 10000 Value. Taker Fee 0.0004 = 4.0
        self.assertAlmostEqual(broker.balance_usdt, 10000.0 - 4.0)

if __name__ == "__main__":
    import unittest
    unittest.main()
