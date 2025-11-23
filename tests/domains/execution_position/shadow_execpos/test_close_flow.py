from apps.reference.domains.execution_position.shadow_execpos.close_flow import (
    CloseFlowService,
    CloseContext,
    CloseConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


def test_manual_close_full():
    svc = CloseFlowService()
    pos = PositionState(symbol="ETHUSDT", qty=2.0, avg_entry_price=100)

    dec = svc.plan_close(pos, CloseContext(reason="MANUAL"))

    assert dec.action == "CLOSE_FULL"
    assert dec.target_qty == 2.0
    assert dec.reason_code == "MANUAL_CLOSE"


def test_force_close_partial_respects_allow_partial():
    svc = CloseFlowService()
    pos = PositionState(symbol="ETHUSDT", qty=3.0, avg_entry_price=100)
    cfg = CloseConfig(allow_partial=True)

    dec = svc.plan_close(pos, CloseContext(reason="FORCE_RISK", requested_qty=1.5), cfg)

    assert dec.action == "CLOSE_PARTIAL"
    assert dec.target_qty == 1.5
    assert dec.reason_code == "FORCE_CLOSE"


def test_close_noop_when_flat():
    svc = CloseFlowService()
    pos = PositionState(symbol="ETHUSDT", qty=0.0)

    dec = svc.plan_close(pos, CloseContext(reason="MANUAL"))

    assert dec.action == "NOOP"
    assert dec.reason_code == "ALREADY_FLAT"
