from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from tests.domains.execution_position.conftest import FakeBus, fsm_config


def _make_fsm() -> ExecPosFSM:
    cfg = fsm_config.__wrapped__() if hasattr(fsm_config, "__wrapped__") else fsm_config()
    bus = FakeBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)
        fsm.order_guardian = mock_guardian
    return fsm


def test_price_ctx_stop_price_extraction():
    fsm = _make_fsm()
    captured = {}

    def _capture(msg):
        captured["msg"] = msg
        return None

    fsm.handle = MagicMock(side_effect=_capture)

    payload = {
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
        "price_ctx": {"stop_price": "90.0"},
        "idempotent_key": "test-idem",
    }

    msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="rid-ctx-1",
        pld=payload,
    )

    fsm._on_trade_intent_proposed(msg)

    assert "msg" in captured
    cmd = captured["msg"]
    assert cmd.op == "CMD"
    assert cmd.verb == "OPEN"
    assert cmd.pld.get("stop_price") == "90.0"
