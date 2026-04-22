from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from tests.domains.execution_position.conftest import FakeBus, fsm_config


def _make_fsm() -> tuple[ExecPosFSM, FakeBus]:
    cfg = fsm_config.__wrapped__() if hasattr(fsm_config, "__wrapped__") else fsm_config()
    bus = FakeBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
        fsm.order_guardian = mock_guardian
    return fsm, bus


def test_trade_intent_uses_payload_rid_for_downstream_trace() -> None:
    fsm, bus = _make_fsm()
    fsm.log_adapter.log_trade_intent = MagicMock()

    captured: dict[str, Message] = {}

    def _capture(cmd: Message) -> Message:
        captured["cmd"] = cmd
        return Message(
            op="DEC",
            verb="OPEN",
            src="execution_position",
            dst="execution_position",
            rid=cmd.rid,
            pld={"symbol": cmd.pld.get("symbol")},
            why="OPEN_OK",
            data_ref=cmd.data_ref,
        )

    fsm.handle = MagicMock(side_effect=_capture)

    intent_rid = "RID-123"
    msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        # Simulate FSMCore-provided rid (not equal to payload rid)
        rid="BUS-RID-999",
        pld={
            "rid": intent_rid,
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "qty": "0.01",
                "price": "100.0",
                "price_ref": "100.0",
                "order_type": "LIMIT",
                "tif": "GTC",
            },
            "valid_for_ms": 60000,
            "idempotent_key": "idem-1",
        },
        why="trade_intent",
        data_ref=["why_a", "why_b"],
    )

    fsm._on_trade_intent_proposed(msg)

    fsm.log_adapter.log_trade_intent.assert_called()
    assert fsm.log_adapter.log_trade_intent.call_args.kwargs["rid"] == intent_rid

    assert "cmd" in captured
    assert captured["cmd"].rid == intent_rid
    assert captured["cmd"].pld.get("rid") == intent_rid

    # Downstream bus emission must preserve rid in the envelope, not mutate DEC:OPEN payload.
    assert bus.events
    topic, args, kwargs = bus.events[0]
    assert topic == "DEC:OPEN"
    assert args and isinstance(args[0], dict)
    assert "rid" not in args[0]
    assert kwargs["rid"] == intent_rid
