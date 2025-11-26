import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketService, BracketState, BracketRulesConfig, BracketPlan
from apps.reference.domains.execution_position.algo_order_index import AlgoOrderUpdate


@pytest.fixture
def adapter():
    config = MagicMock()
    config.trading.trading_env = "test"
    adapter = BinanceExecutionAdapter(config=config, shadow_mode=True)
    adapter.fsm_core = MagicMock()
    return adapter


def test_adapter_emits_algo_update_event(adapter):
    """Test that _handle_algo_update emits EVT:ALGO_ORDER_UPDATED."""
    # Mock payload from WS
    msg = {
        "e": "ALGO_UPDATE",
        "s": "BTCUSDT",
        "a": {
            "c": "client_algo_123",
            "i": 999,
            "s": "FILLED",
            "S": "BUY",
            "o": "STOP_MARKET",
            "l": "0.1",
            "z": "0.1",
        },
        "E": 1234567890
    }

    adapter._handle_algo_update(msg)

    # Verify emit called
    adapter.fsm_core.emit.assert_called_once()
    args, _ = adapter.fsm_core.emit.call_args
    event_name, payload, reason = args

    assert event_name == "EVT:ALGO_ORDER_UPDATED"
    assert payload["client_algo_order_id"] == "client_algo_123"
    assert payload["status"] == "FILLED"
    assert payload["symbol"] == "BTCUSDT"
    assert reason == "WS_ALGO_UPDATE"


def test_bracket_service_on_algo_order_filled():
    """Test that on_algo_order_filled calls evaluate."""
    service = BracketService(aggregator=MagicMock(), guardian=MagicMock())

    # Mock evaluate
    service.evaluate = MagicMock(return_value=BracketPlan(
        symbol="BTCUSDT",
        side="LONG",
        state=MagicMock(),
        actions=[],
        severity="INFO",
        why="mock_eval"
    ))

    update = AlgoOrderUpdate(
        algo_order_id="999",
        client_algo_order_id="client_123",
        symbol="BTCUSDT",
        side="BUY",
        algo_type="STOP_MARKET",
        status="FILLED",
        last_executed_qty=Decimal("0.1"),
        cumulative_filled_qty=Decimal("0.1"),
        transaction_time=1234567890
    )

    state = MagicMock(spec=BracketState)
    cfg = BracketRulesConfig()

    plan = service.on_algo_order_filled(update, state, cfg, rid="test_rid")

    service.evaluate.assert_called_once_with(state, cfg, rid="test_rid")
    assert plan.why == "mock_eval"
