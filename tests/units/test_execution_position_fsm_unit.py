import time
import types

import pytest

from apps.reference.domains.execution_position import fsm as fsm_mod
from vfoundation.core.adapters.base import ExchangeOrderResponse


class DummyFlow:
    def __init__(self, *args, **kwargs):
        self.called_handle = False
        self.hydrated_with = None

    def handle(self, msg):
        self.called_handle = True
        # Return falsy to avoid ExecPosFSM trying to read .op
        return None

    def hydrate(self, data):
        self.hydrated_with = data

    def get_metrics(self):
        return {"dummy": 1}


class DummyFSM:
    def emit(self, *a, **k):
        pass


class DummyMsg:
    def __init__(self, op="EVT", verb="OPEN", pld=None):
        self.op = op
        self.verb = verb
        self.pld = pld
        self.dst = "exec"
        self.rid = "rid"

    def model_dump(self):
        return {
            "op": self.op,
            "verb": self.verb,
            "pld": self.pld,
            "dst": self.dst,
            "rid": self.rid,
        }


def test_get_or_create_flows_and_accessors():
    # patch the flow classes so ExecPosFSM creates our dummies
    monkey = pytest.MonkeyPatch()
    monkey.setattr(fsm_mod, "OpenFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "ManageFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "CloseFlowFSM", DummyFlow)

    try:

        cfg = {
            "trading": {
                "execution": {"cooldown_ms": 1000, "guard_enabled": True, "exposure": {}},
                "instruments": {},
            }
        }
        f = fsm_mod.ExecPosFSM(config=cfg, fsm=DummyFSM(), shadow_mode=True)

        # ExecPosFSM (vfoundation variant) exposes flow instances as attributes
        of = f.open_flow("BTCUSDT")
        mf = f.manage_flow("BTCUSDT")
        cf = f.close_flow("BTCUSDT")

        assert isinstance(of, DummyFlow)
        assert isinstance(mf, DummyFlow)
        assert isinstance(cf, DummyFlow)

        # basic observability attributes exist
        assert hasattr(f, "log_adapter")
        assert hasattr(f, "metrics_collector")
    finally:
        monkey.undo()


def test_handle_routes_to_open_flow_and_missing_symbol():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(fsm_mod, "OpenFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "ManageFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "CloseFlowFSM", DummyFlow)

    try:

        cfg = {
            "trading": {
                "execution": {"cooldown_ms": 1000, "guard_enabled": True, "exposure": {}},
                "instruments": {},
            }
        }
        f = fsm_mod.ExecPosFSM(config=cfg, fsm=DummyFSM(), shadow_mode=True)

        # message without symbol -> warning path, returns None
        m_no_sym = DummyMsg(pld={})
        assert f.handle(m_no_sym) is None

        # message with symbol and OPEN -> routed to OpenFlowFSM.handle
        m = DummyMsg(pld={"symbol": "BTCUSDT"}, verb="OPEN")
        result = f.handle(m)
        # our DummyFlow.handle returns None, but should have been called
        of = f.open_flow("BTCUSDT")
        assert of.called_handle is True
        assert result is None
    finally:
        monkey.undo()


@pytest.mark.asyncio
async def test_update_portfolio_after_timeout_cancellation():
    """Test that portfolio state is reset after successful timeout cancellation."""
    from unittest.mock import AsyncMock, MagicMock, patch
    import asyncio

    # Create FSM instance
    cfg = {
        "trading": {
            "execution": {"cooldown_ms": 1000, "guard_enabled": True, "exposure": {}},
            "instruments": {},
        }
    }

    # Mock FSM
    mock_fsm = MagicMock()

    f = fsm_mod.ExecPosFSM(config=cfg, fsm=mock_fsm, shadow_mode=True)

    # Set initial portfolio state
    f._latest_portfolio_state = {
        "positions_count": 1,
        "open_positions_usd": "1000.0",
        "last_updated": 1000
    }

    # Mock emit_compat
    with patch('vfoundation.core.fsm_emit_compat.emit_compat', new_callable=AsyncMock) as mock_emit_compat:
        # Call the method
        await f._update_portfolio_after_timeout_cancellation("BTCUSDT")

        # Verify emit_compat was called
        assert mock_emit_compat.called
        call_args = mock_emit_compat.call_args
        fsm_arg, msg_arg = call_args[0]  # First two positional arguments

        assert fsm_arg == mock_fsm
        assert msg_arg.op == "EVT"
        assert msg_arg.verb == "PORTFOLIO_STATE_UPDATED"
        assert msg_arg.src == "execution_position"
        assert msg_arg.dst == "decision_making"
        assert msg_arg.pld["symbol"] == "BTCUSDT"
        assert msg_arg.pld["reason"] == "timeout_cancellation"
        assert msg_arg.pld["portfolio_state"]["positions_count"] == 0
        assert msg_arg.pld["portfolio_state"]["open_positions_usd"] == "0"


def test_cancel_success_response_handles_exchange_order_response():
    """Ensure ExchangeOrderResponse is treated as successful cancel payload."""
    response = ExchangeOrderResponse(
        order_id="1",
        client_order_id="cid",
        symbol="BTCUSDT",
        side="SELL",
        quantity="0.1",
        filled_qty="0",
        price="0",
        status="CANCELED",
        timestamp_ms=0,
    )
    assert fsm_mod.ExecPosFSM._is_cancel_success_response(response) is True
