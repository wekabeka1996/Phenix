import pytest
from unittest.mock import MagicMock, ANY
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from vfoundation.core.protocol import Message

class MockConfig:
    def __init__(self):
        self.trading = MagicMock()
        self.trading.execution = MagicMock()
        self.trading.execution.manage = MagicMock()
        self.trading.execution.manage.brackets = MagicMock()
        self.trading.execution.manage.brackets.enable = True
        self.trading.execution.manage.brackets.sl = MagicMock()
        self.trading.execution.manage.brackets.sl.fixed_bps = 50
        self.trading.execution.manage.brackets.tp = MagicMock()
        self.trading.execution.manage.brackets.tp.fixed_bps = 100
        self.trading.execution.manage.brackets.offset_bps = 5
        self.trading.execution.manage.auto = True # Enable auto manage
        self.trading.symbol = "BTCUSDT"
        self.trading.decision = MagicMock()
        self.trading.decision.bar_gating = None
        self.trading.instruments = {"BTCUSDT": MagicMock(tick_size="0.1")}

class MockLedger:
    def __init__(self):
        self.orders = {}
    
    def get_order(self, order_id):
        return self.orders.get(order_id)
    
    def get_position(self, symbol):
        return {"net_qty": 1.0, "avg_price": 50000.0} # Long position

    def get_active_orders(self, symbol):
        return []

@pytest.fixture
def manage_fsm():
    config = MockConfig()
    # ManageFlowFSM only takes config
    fsm = ManageFlowFSM(config=config)
    return fsm

def test_oco_placement_on_fill(manage_fsm):
    """Test that TP/SL brackets are placed when an entry order is filled."""
    
    # Simulate a FILL event for an entry order
    fill_event = Message(
        op="EVT",
        verb="FILL",
        src="exchange",
        dst="execution_position",
        pld={
            "order_id": "entry_order_1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "fill_price": 50000.0,
            "fill_qty": 1.0,
            "client_order_id": "entry_order_1",
            "qty": 1.0,
            "price": 50000.0
        }
    )
    
    # Mock the ledger to return the order details
    # manage_fsm.ledger.orders["entry_order_1"] = { ... } # Removed as ledger is not used

    # Handle the event
    result = manage_fsm.handle(fill_event)
    
    # We expect a DEC message with BATCH verb
    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "BATCH"
    
    messages = result.pld.get("messages", [])
    assert len(messages) == 2
    
    sl_order = messages[0]
    tp_order = messages[1]
    
    assert sl_order["verb"] == "PLACE_ORDER"
    assert "SL bracket" in sl_order["why"]
    
    assert tp_order["verb"] == "PLACE_ORDER"
    assert "TP bracket" in tp_order["why"]
    assert tp_order["pld"]["order_type"] == "TAKE_PROFIT_MARKET"
