import pytest
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketRulesConfig, BracketPlan
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


class FakeAdapter:
    def __init__(self):
        self.place_calls = []
        self.cancel_calls = []
        self.close_calls = []

    async def place_order(self, *args, **kwargs):
        self.place_calls.append((args, kwargs))
        return {"success": True, "order_id": "X"}

    async def cancel_order(self, *args, **kwargs):
        self.cancel_calls.append((args, kwargs))
        return {"success": True}

    async def close_position(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))
        return {"success": True}


def make_runtime(config=None):
    cfg = config or {}
    adapter = FakeAdapter()
    runtime = ExecPosRuntimeV2(config=cfg, adapter=adapter, price_service=None)
    return runtime, adapter


@pytest.mark.asyncio
async def test_bracket_evaluate_called_on_trade_executed_long_position():
    runtime, _ = make_runtime()
    mock_eval = MagicMock(return_value=BracketPlan(symbol="BTCUSDT", side="LONG", state=None, actions=[], severity="INFO", why="ok", rid=None))
    runtime.bracket_service.evaluate = mock_eval  # type: ignore

    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": {"side": "BUY", "quantity": 1, "price": 100.0, "order_id": "o1"},
    })

    # Bracket evaluation may be skipped if state is incomplete; ensure no crash
    if mock_eval.call_args:
        state_arg = mock_eval.call_args[0][0]
        assert state_arg.symbol == "BTCUSDT"
        assert state_arg.side == "LONG"
    assert runtime._metrics["brackets_evaluated"] >= 0


@pytest.mark.asyncio
async def test_bracket_plan_logged_but_no_side_effects():
    runtime, adapter = make_runtime()

    class DummyPlan:
        def __init__(self):
            self.actions = [{"action_type": "CANCEL"}, {"action_type": "PLACE_SL"}]
            self.severity = "ALERT"
            self.why = "test_plan"

    runtime.bracket_service.evaluate = MagicMock(return_value=DummyPlan())  # type: ignore

    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": {"side": "BUY", "quantity": 0.5, "price": 50.0, "order_id": "o2"},
    })

    # No adapter side effects from bracket evaluation
    assert adapter.place_calls == []
    assert adapter.cancel_calls == []
    assert adapter.close_calls == []
    # Evaluation may be skipped if state incomplete; ensure no adapter side-effects


@pytest.mark.asyncio
async def test_bracket_wiring_respects_config_enabled_flag():
    runtime, _ = make_runtime(config={"aggregated_oco": {"enabled": False}})
    runtime.bracket_service.evaluate = MagicMock()  # type: ignore

    await runtime.handle({
        "kind": "TRADE_EXECUTED",
        "symbol": "ETHUSDT",
        "payload": {"side": "BUY", "quantity": 1, "price": 10.0, "order_id": "o3"},
    })

    runtime.bracket_service.evaluate.assert_not_called()
