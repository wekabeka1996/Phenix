"""
Tests for MockBroker Realism Features (Backtest Hardening)

Tests the following hardening logic:
1. SL Priority: Stop-loss executes BEFORE take-profit in same-bar conflicts
2. Trade-Through: Limit orders require price to trade THROUGH limit (not touch)
3. Slippage: Market orders incur configurable slippage
4. Volume Cap: Orders capped at % of bar volume
"""

import sys
import os
import asyncio
import pytest
from decimal import Decimal

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_engine.mock_broker import MockBroker
from vfoundation.core.adapters.base import ExchangeOrderParams


class TestSLPriority:
    """Test SL Priority: STOP_MARKET executes before TAKE_PROFIT_MARKET."""

    @pytest.mark.asyncio
    async def test_sl_triggers_before_tp_same_bar(self):
        """
        When both SL and TP could trigger in the same bar, SL should execute first
        and TP should be cancelled (worst-case assumption).
        """
        broker = MockBroker(initial_balance_usdt=10000.0, slippage_bps=0.0)
        
        # Create a LONG position first
        entry_params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="1.0"
        )
        await broker.create_order(entry_params)
        broker.process_data({"symbol": "BTCUSDT", "close": 100.0, "volume": 1000})
        
        # Place SL at 95 and TP at 110
        sl_params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity="0",
            close_position=True,
            stop_price="95.0"
        )
        tp_params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity="0",
            close_position=True,
            stop_price="110.0"
        )
        sl_resp = await broker.create_order(sl_params)
        tp_resp = await broker.create_order(tp_params)
        
        # Volatile bar: Low=90 (triggers SL at 95), High=115 (triggers TP at 110)
        # SL should win due to priority
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "open": 100.0,
            "high": 115.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000
        })
        
        # SL should have filled
        assert len(fills) == 1
        assert fills[0]["side"] == "SELL"
        
        # TP should be cancelled
        tp_order = broker._orders.get(tp_resp.order_id)
        assert tp_order is not None
        assert tp_order.status == "CANCELED"


class TestTradeThrough:
    """Test Trade-Through: Limit orders require price to trade THROUGH limit."""

    @pytest.mark.asyncio
    async def test_limit_buy_no_fill_at_touch(self):
        """
        Limit BUY at 100 should NOT fill when low == 100 (touch only).
        With fill_probability_at_touch=0.0 (default), no fill should occur.
        """
        broker = MockBroker(
            initial_balance_usdt=10000.0,
            fill_probability_at_touch=0.0  # Conservative: no fill at touch
        )
        
        # Place Limit BUY at 100
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1.0",
            price="100.0"
        )
        await broker.create_order(params)
        
        # Bar touches but doesn't trade through: low == 100 exactly
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "high": 102.0,
            "low": 100.0,  # Touch, not trade-through
            "close": 101.0,
            "volume": 1000
        })
        
        # Should NOT fill
        assert len(fills) == 0
        orders = await broker.get_open_orders("BTCUSDT")
        assert len(orders) == 1  # Order still open

    @pytest.mark.asyncio
    async def test_limit_buy_fills_on_trade_through(self):
        """
        Limit BUY at 100 should fill when low < 100 (trade-through).
        """
        broker = MockBroker(initial_balance_usdt=10000.0)
        
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1.0",
            price="100.0"
        )
        await broker.create_order(params)
        
        # Bar trades through: low = 99 < 100
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "high": 102.0,
            "low": 99.0,  # Trade-through
            "close": 101.0,
            "volume": 1000
        })
        
        # Should fill
        assert len(fills) == 1
        assert float(fills[0]["price"]) == 100.0  # Filled at limit price


class TestSlippage:
    """Test Slippage: Market orders incur configurable slippage."""

    @pytest.mark.asyncio
    async def test_market_buy_slippage(self):
        """
        Market BUY should be penalized by slippage (pay more).
        """
        broker = MockBroker(
            initial_balance_usdt=10000.0,
            slippage_bps=10.0  # 10 bps = 0.1%
        )
        
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="1.0"
        )
        await broker.create_order(params)
        
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "close": 100.0,
            "volume": 1000
        })
        
        # Fill price should be 100 * (1 + 0.001) = 100.1
        assert len(fills) == 1
        assert float(fills[0]["price"]) == pytest.approx(100.1, rel=1e-6)

    @pytest.mark.asyncio
    async def test_market_sell_slippage(self):
        """
        Market SELL should be penalized by slippage (receive less).
        """
        broker = MockBroker(
            initial_balance_usdt=10000.0,
            slippage_bps=10.0  # 10 bps = 0.1%
        )
        
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            quantity="1.0"
        )
        await broker.create_order(params)
        
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "close": 100.0,
            "volume": 1000
        })
        
        # Fill price should be 100 * (1 - 0.001) = 99.9
        assert len(fills) == 1
        assert float(fills[0]["price"]) == pytest.approx(99.9, rel=1e-6)

    @pytest.mark.asyncio
    async def test_per_symbol_slippage(self):
        """
        Per-symbol slippage override should be respected.
        """
        broker = MockBroker(
            initial_balance_usdt=10000.0,
            slippage_bps=2.0,  # Default 2 bps
            slippage_map={"DOGEUSDT": 10.0}  # DOGE gets 10 bps
        )
        
        params = ExchangeOrderParams(
            symbol="DOGEUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="1000.0"
        )
        await broker.create_order(params)
        
        fills = broker.process_data({
            "symbol": "DOGEUSDT",
            "close": 0.10,
            "volume": 100000
        })
        
        # Fill price should be 0.10 * (1 + 0.001) = 0.1001
        assert len(fills) == 1
        assert float(fills[0]["price"]) == pytest.approx(0.1001, rel=1e-6)


class TestVolumeCap:
    """Test Volume Cap: Orders capped at % of bar volume."""

    @pytest.mark.asyncio
    async def test_volume_cap_reduces_fill_quantity(self):
        """
        Large order should be capped at max_volume_participation % of bar volume.
        """
        broker = MockBroker(
            initial_balance_usdt=100000.0,
            max_volume_participation=0.05,  # 5%
            slippage_bps=0.0
        )
        
        # Try to buy 100 BTC
        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="100.0"
        )
        await broker.create_order(params)
        
        # Bar only has 500 BTC volume, 5% = 25 BTC max
        fills = broker.process_data({
            "symbol": "BTCUSDT",
            "close": 100.0,
            "volume": 500.0
        })
        
        # Fill quantity should be capped at 25
        assert len(fills) == 1
        assert float(fills[0]["quantity"]) == 25.0


class TestStressExecutionParams:
    """Stress overrides should affect execution and PnL."""

    @pytest.mark.asyncio
    async def test_applied_stress_params_exposed(self):
        broker = MockBroker(
            initial_balance_usdt=10000.0,
            fee_mult=1.3,
            slippage_bps=6.0,
            latency_ms=150,
            funding_bps_per_day=8.0,
        )
        params = broker.applied_stress_params
        assert float(params["fee_mult"]) == pytest.approx(1.3, rel=1e-6)
        assert int(params["latency_ms"]) == 150
        assert float(params["funding_bps_per_day"]) == pytest.approx(8.0, rel=1e-6)

    @pytest.mark.asyncio
    async def test_funding_changes_pnl_with_open_position(self):
        broker_base = MockBroker(initial_balance_usdt=10000.0, slippage_bps=0.0, funding_bps_per_day=0.0)
        broker_funding = MockBroker(initial_balance_usdt=10000.0, slippage_bps=0.0, funding_bps_per_day=10.0)

        open_params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="1.0",
        )

        await broker_base.create_order(open_params)
        await broker_funding.create_order(open_params)

        bar1 = {"symbol": "BTCUSDT", "close": 100.0, "volume": 1000.0, "ts": 1704067200000}
        bar2 = {"symbol": "BTCUSDT", "close": 100.0, "volume": 1000.0, "ts": 1704067500000}
        broker_base.process_data(bar1)
        broker_funding.process_data(bar1)
        broker_base.process_data(bar2)
        broker_funding.process_data(bar2)

        assert broker_funding.balance_usdt < broker_base.balance_usdt
        assert len(broker_funding.funding_ledger) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
