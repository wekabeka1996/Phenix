from decimal import Decimal

from apps.reference.config_models import BracketsConfig, SLConfig, TPConfig
from apps.reference.domains.execution_position.flows.manage.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from vfoundation.core.protocol import Message


def _entry_fill_message(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-entry-fill",
        why="test_entry_fill",
        pld={
            "symbol": symbol,
            "orderId": "entry-order-1",
            "clientOrderId": "ENTRY-1",
            "client_order_id": "ENTRY-1",
            "side": "BUY",
            "qty": "0.10",
            "quantity": "0.10",
            "price": "1000",
        },
    )


def _sl_fill_message(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-entry-fill:SL",
        why="test_sl_fill",
        pld={
            "symbol": symbol,
            "orderId": "child-sl-order-1",
            "clientOrderId": "algo-sl-1",
            "client_order_id": "algo-sl-1",
            "side": "SELL",
            "qty": "0.10",
            "quantity": "0.10",
            "price": "990",
            "order_type": "STOP_MARKET",
            "reduceOnly": True,
            "closePosition": True,
            "close_reason": "SL",
        },
    )


def test_entry_fill_preserves_presynced_primary_bracket_identity(fsm_config):
    manage = ManageFlowFSM(config=fsm_config)
    manage.set_bracket_ids(
        sl_order_id="1000001",
        tp_order_id="1000002",
        sl_algo_client_id="algo-sl-1",
        tp_algo_client_id="algo-tp-1",
    )

    entry_result = manage.handle(_entry_fill_message())

    assert entry_result is None
    assert manage.state == ManageState.BRACKETS_PLACED
    assert manage.entry_order_id == "entry-order-1"
    assert manage.entry_client_order_id == "ENTRY-1"
    assert manage.position_qty == Decimal("0.10")
    assert manage.sl_order_id == "1000001"
    assert manage.tp_order_id == "1000002"
    assert manage.sl_algo_client_id == "algo-sl-1"
    assert manage.tp_algo_client_id == "algo-tp-1"

    exit_result = manage.handle(_sl_fill_message())

    assert exit_result is not None
    assert exit_result.op == "DEC"
    assert exit_result.verb == "CANCEL_ORDER"
    assert exit_result.pld["orderId"] == "1000002"
    assert manage.state == ManageState.FLAT
    assert manage.has_active_lifecycle() is False
    assert manage.symbol is None
    assert manage.position_qty is None
    assert manage.sl_order_id is None
    assert manage.tp_order_id is None
    assert manage.sl_algo_client_id is None
    assert manage.tp_algo_client_id is None


def test_entry_fill_still_clears_legacy_phantom_bracket_ids(fsm_config):
    manage = ManageFlowFSM(config=fsm_config)
    manage.sl_order_id = "SL-stale-1"
    manage.tp_order_id = "TP-stale-1"

    result = manage.handle(_entry_fill_message())

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "BATCH"
    assert manage.state == ManageState.BRACKETS_PENDING
    assert manage.sl_order_id is None
    assert manage.tp_order_id != "TP-stale-1"
    assert manage.tp_order_id is not None
    assert manage.sl_algo_client_id is None
    assert manage.tp_algo_client_id is None


def test_entry_fill_uses_typed_brackets_config_without_stale_enable_field(
    fsm_config,
):
    fsm_config.trading.execution.manage.brackets = BracketsConfig(
        sl=SLConfig(fixed_bps=40),
        tp=TPConfig(fixed_bps=80),
        oco_emulation=True,
        offset_bps=5,
    )
    manage = ManageFlowFSM(config=fsm_config)

    result = manage.handle(_entry_fill_message())

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "BATCH"
    assert manage.state == ManageState.BRACKETS_PENDING
    assert manage.entry_order_id == "entry-order-1"
    assert manage.entry_client_order_id == "ENTRY-1"
    assert manage.position_qty == Decimal("0.10")
