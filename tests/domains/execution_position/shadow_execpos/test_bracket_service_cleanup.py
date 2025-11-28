import pytest
from decimal import Decimal
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketService, OrderView, BracketAction
)

@pytest.fixture
def service():
    return BracketService(aggregator=None, guardian=None)

def test_plan_orphan_cleanup_cancels_reduce_only_orders(service):
    orders = [
        OrderView(
            order_id="1", client_order_id="c1", symbol="BTCUSDT", side="SELL",
            order_type="STOP_MARKET", qty=Decimal("1.0"), reduce_only=True
        ),
        OrderView(
            order_id="2", client_order_id="c2", symbol="BTCUSDT", side="SELL",
            order_type="TAKE_PROFIT_MARKET", qty=Decimal("1.0"), reduce_only=True
        ),
        OrderView(
            order_id="3", client_order_id="c3", symbol="BTCUSDT", side="BUY",
            order_type="LIMIT", qty=Decimal("1.0"), reduce_only=False
        ),
    ]

    plan = service.plan_orphan_cleanup("BTCUSDT", orders)

    assert len(plan.actions) == 2
    assert plan.actions[0].action_type == "CANCEL"
    assert plan.actions[0].order_id == "1"
    assert plan.actions[0].reason_code == "ORPHAN_CLEANUP"

    assert plan.actions[1].action_type == "CANCEL"
    assert plan.actions[1].order_id == "2"

def test_plan_reverse_cleanup_cancels_old_side_brackets(service):
    # Reverse LONG -> SHORT. Old exit side is SELL.
    orders = [
        OrderView( # Old SL (SELL) - Should Cancel
            order_id="1", client_order_id="c1", symbol="BTCUSDT", side="SELL",
            order_type="STOP_MARKET", qty=Decimal("1.0"), reduce_only=True
        ),
        OrderView( # New SL (BUY) - Should Keep
            order_id="2", client_order_id="c2", symbol="BTCUSDT", side="BUY",
            order_type="STOP_MARKET", qty=Decimal("1.0"), reduce_only=True
        ),
        OrderView( # Entry Order - Should Keep
            order_id="3", client_order_id="c3", symbol="BTCUSDT", side="BUY",
            order_type="LIMIT", qty=Decimal("1.0"), reduce_only=False
        ),
    ]

    plan = service.plan_reverse_cleanup("BTCUSDT", "LONG", "SHORT", orders)

    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == "CANCEL"
    assert plan.actions[0].order_id == "1"
    assert plan.actions[0].reason_code == "REVERSE_CLEANUP"
