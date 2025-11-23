import time

import pytest
import time
from decimal import Decimal

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.legacy.fsm_manage import ManageFlowFSM, ManageState

pytestmark = pytest.mark.execpos_legacy



def test_quick_profit_closes_at_2_dollars_buy():
    cfg = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0,
                        'priority': 'highest'
                    },
                    'auto': True
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)
    # Hydrate with opened position
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    msg = Message(op='UPD', verb='TICK', src='test', dst='execution_position', pld={
                  'mark_price': '3200.00', 'symbol': 'ETHUSDT'})
    res = fsm.handle(msg)
    assert res is not None
    assert res.verb == 'CLOSE'
    assert res.why == 'QUICK_PROFIT_HIT'
    assert Decimal(res.pld['pnl_usd']) >= Decimal('2.0')


def test_quick_profit_disabled_does_not_close():
    cfg = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': False,
                        'target_usd': 2.0,
                    },
                    'auto': True
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    msg = Message(op='UPD', verb='TICK', src='test', dst='execution_position', pld={
                  'mark_price': '3200.00', 'symbol': 'ETHUSDT'})
    res = fsm.handle(msg)
    # Quick profit disabled should not emit a CLOSE decision; other rules may still fire (e.g., trail/adjust)
    assert res is not None
    assert res.verb != 'CLOSE'


def test_quick_profit_closes_at_2_dollars_sell():
    cfg = {
        'trading': {
            'execution': {
                'manage': {
                    'quick_profit': {
                        'enabled': True,
                        'target_usd': 2.0,
                        'priority': 'highest'
                    },
                    'auto': True
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)
    # SELL position: entry 3000, current price 2800 -> 200 move * 0.01 = $2
    fsm.position_qty = Decimal('-0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'SELL'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    msg = Message(op='UPD', verb='TICK', src='test', dst='execution_position', pld={
                  'mark_price': '2800.00', 'symbol': 'ETHUSDT'})
    res = fsm.handle(msg)
    assert res is not None
    assert res.verb == 'CLOSE'
    assert res.why == 'QUICK_PROFIT_HIT'
    assert Decimal(res.pld['pnl_usd']) >= Decimal('2.0')

