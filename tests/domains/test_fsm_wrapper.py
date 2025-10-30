import asyncio
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


def test_execposfsm_routes_and_wal_append(monkeypatch):
    # Capture wal.append calls
    appended = {}

    def fake_append(d):
        appended["called"] = True
        appended["data"] = d

    monkeypatch.setattr("vfoundation.dr.wal.append", fake_append)

    # Create FSM in shadow mode to avoid adapter initialization
    cfg = {"trading": {"execution": {}}}
    exec_fsm = ExecPosFSM(cfg, fsm=None, shadow_mode=True)

    # Send CMD OPEN routed to OpenFlowFSM via ExecPosFSM
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="exec",
        rid="rx1",
        pld={"symbol": "ETHUSDT", "side": "BUY", "qty": 1, "price_ref": 20},
    )
    res = exec_fsm.handle(msg)
    # DEC should be returned and wal.append should be called
    assert res is not None
    assert appended.get("called", False) is True
    assert isinstance(appended.get("data"), dict)


def test_hydrate_missing_symbol_logs(monkeypatch):
    cfg = {}
    exec_fsm = ExecPosFSM(cfg, fsm=None, shadow_mode=True)
    # Should not raise
    exec_fsm.hydrate({})
