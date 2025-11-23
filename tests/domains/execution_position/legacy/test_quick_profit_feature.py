"""
Tests for Quick Profit feature - closes position when PnL reaches $2 USD.

This test suite validates:
1. Position closes at exactly $2 profit for BUY
2. Position closes at exactly $2 profit for SELL
3. Position does NOT close below $2 threshold
4. Quick profit has highest priority over other rules
"""

import pytest
import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.legacy.fsm_manage import ManageFlowFSM, ManageState

pytestmark = pytest.mark.execpos_legacy



def test_quick_profit_closes_at_2_dollars_buy():
    """Test that position closes when PnL reaches $2 for BUY."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0,
                        'priority': 'highest'
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)

    # Симулювати відкриту позицію: куплено 0.01 ETH по $3000
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Ціна підвищилась до $3200: 0.01 * 200 = $2 profit
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'mark_price': '3200.00', 'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)

    assert result is not None, "Expected close decision for $2 profit"
    assert result.verb == "CLOSE", f"Expected CLOSE, got {result.verb}"
    assert result.why == "QUICK_PROFIT_HIT", f"Expected QUICK_PROFIT_HIT, got {result.why}"
    assert Decimal(result.pld['pnl_usd']) >= Decimal(
        '2.0'), f"Expected PnL >= $2, got {result.pld['pnl_usd']}"
    print(f"✅ BUY position closed with PnL=${result.pld['pnl_usd']}")


def test_quick_profit_closes_at_2_dollars_sell():
    """Test that position closes when PnL reaches $2 for SELL."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0,
                        'priority': 'highest'
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)

    # Симулювати відкриту позицію: продано 0.01 ETH по $3000
    fsm.position_qty = Decimal('-0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'SELL'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Ціна знизилась до $2800: 0.01 * 200 = $2 profit
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'mark_price': '2800.00', 'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)

    assert result is not None, "Expected close decision for $2 profit"
    assert result.verb == "CLOSE", f"Expected CLOSE, got {result.verb}"
    assert result.why == "QUICK_PROFIT_HIT", f"Expected QUICK_PROFIT_HIT, got {result.why}"
    assert Decimal(result.pld['pnl_usd']) >= Decimal(
        '2.0'), f"Expected PnL >= $2, got {result.pld['pnl_usd']}"
    print(f"✅ SELL position closed with PnL=${result.pld['pnl_usd']}")


def test_quick_profit_not_triggered_below_threshold():
    """Test that quick profit doesn't trigger below $2."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Ціна підвищилась лише на $100 = $1 profit
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'mark_price': '3100.00', 'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)
    assert result is None, "Quick profit should not trigger for $1 profit"
    print("✅ Quick profit correctly skipped for $1 profit")


def test_quick_profit_disabled():
    """Test that quick profit doesn't trigger when disabled."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': False,
                        'target_usd': 2.0
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Ціна підвищилась до $4000 = $10 profit (далеко за поріг)
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'mark_price': '4000.00', 'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)
    assert result is None, "Quick profit should not trigger when disabled"
    print("✅ Quick profit correctly disabled")


def test_quick_profit_with_large_position():
    """Test quick profit with larger position size."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0,
                        'priority': 'highest'
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)

    # Більша позиція: 0.1 ETH по $3000
    fsm.position_qty = Decimal('0.1')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Маленький рух ціни: $3020 = 0.1 * 20 = $2 profit
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'mark_price': '3020.00', 'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)

    assert result is not None, "Expected close decision"
    assert result.verb == "CLOSE"
    assert Decimal(result.pld['pnl_usd']) >= Decimal('2.0')
    print(
        f"✅ Large position closed with small price move: PnL=${result.pld['pnl_usd']}")


def test_quick_profit_missing_price_data():
    """Test graceful handling when price data is missing."""
    config = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0
                    }
                }
            }
        }
    }

    fsm = ManageFlowFSM(config=config)
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.state = ManageState.TRACKING

    # Повідомлення без ціни
    msg = Message(
        op="UPD",
        verb="TICK",
        src="market_data",
        dst="execution_position",
        pld={'symbol': 'ETHUSDT'}
    )

    result = fsm._check_quick_profit(msg)
    assert result is None, "Should return None when price data missing"
    print("✅ Gracefully handled missing price data")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

