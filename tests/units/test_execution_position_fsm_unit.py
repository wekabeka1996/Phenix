import time
import types

import pytest

from apps.reference.domains.execution_position import fsm as fsm_mod


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


def test_get_or_create_flows_and_accessors():
    # patch the flow classes so ExecPosFSM creates our dummies
    monkey = pytest.MonkeyPatch()
    monkey.setattr(fsm_mod, "OpenFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "ManageFlowFSM", DummyFlow)
    monkey.setattr(fsm_mod, "CloseFlowFSM", DummyFlow)

    try:

        class Cfg:
            pass

        cfg = Cfg()
        cfg.trading = {
            "execution": {"cooldown_ms": 1000, "guard_enabled": True},
            "instruments": {},
        }
        f = fsm_mod.ExecPosFSM(config=cfg, fsm=DummyFSM(), shadow_mode=True)

        # ExecPosFSM (vfoundation variant) exposes flow instances as attributes
        of = f.open_flow
        mf = f.manage_flow
        cf = f.close_flow

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

        class Cfg:
            pass

        cfg = Cfg()
        cfg.trading = {
            "execution": {"cooldown_ms": 1000, "guard_enabled": True},
            "instruments": {},
        }
        f = fsm_mod.ExecPosFSM(config=cfg, fsm=DummyFSM(), shadow_mode=True)

        # message without symbol -> warning path, returns None
        m_no_sym = DummyMsg(pld={})
        assert f.handle(m_no_sym) is None

        # message with symbol and OPEN -> routed to OpenFlowFSM.handle
        m = DummyMsg(pld={"symbol": "BTCUSDT"}, verb="OPEN")
        result = f.handle(m)
        # our DummyFlow.handle returns None, but should have been called
        of = f.open_flow
        assert of.called_handle is True
        assert result is None
    finally:
        monkey.undo()
