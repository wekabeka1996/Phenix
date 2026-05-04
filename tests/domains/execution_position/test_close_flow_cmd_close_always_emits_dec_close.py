from vfoundation.core.protocol import Message


def test_close_flow_cmd_close_emits_dec_close_even_when_flat():
    from apps.reference.domains.execution_position.flows.close.fsm_close import CloseFlowFSM, CloseState

    close_flow = CloseFlowFSM()
    assert close_flow.state == CloseState.FLAT

    msg = Message(
        op="CMD",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid="rid-close-test",
        pld={"symbol": "BTCUSDT", "reason": "test"},
        why="test",
    )
    dec = close_flow.handle(msg)

    assert dec is not None
    assert dec.op == "DEC"
    assert dec.verb == "CLOSE"
    assert dec.pld.get("reduce_only") is True
    assert dec.pld.get("symbol") == "BTCUSDT"

