import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState


class DummyPriceService:
    def __init__(self, mark=None, last=None):
        self.mark = mark
        self.last = last

    def get_current(self, symbol, working_type="MARK", ttl_ms=250):
        # simple sync return
        return type("Q", (), {"mark": self.mark, "last": self.last, "mid": None, "ts": 0, "source": "MARK"})()


def test_quick_profit_uses_price_service_and_closes():
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

    fsm = ManageFlowFSM(
        config=config, price_service=DummyPriceService(mark=3200.0))

    # position opened
    fsm.position_qty = Decimal('0.01')
    fsm.position_entry_price = Decimal('3000.00')
    fsm.position_side = 'BUY'
    fsm.symbol = 'ETHUSDT'
    fsm.state = ManageState.TRACKING

    # Message without any price data should be okay because price service is available
    msg = Message(op="UPD", verb="TICK", src="market_data",
                  dst="execution_position", pld={'symbol': 'ETHUSDT'})

    result = fsm._check_quick_profit(msg)

    assert result is not None
    assert result.verb == 'CLOSE'
    assert result.why == 'QUICK_PROFIT_HIT'


if __name__ == '__main__':
    pytest.main([__file__, '-q'])
