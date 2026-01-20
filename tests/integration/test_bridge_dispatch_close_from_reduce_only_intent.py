from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skip(reason="Refactoring: AuroraBridge class deleted")

from vfoundation.core.protocol import Message


class _FakeFSM:
    def listen(self, _event: str, _handler: object) -> None:
        return

    def emit(self, _event: str, _payload: dict | None = None, _why: str | None = None, data_ref=None) -> None:  # type: ignore[no-untyped-def]
        return


def test_bridge_dispatch_close_converts_to_cmd_close(monkeypatch):
    from apps.reference import main as main_mod
    from apps.reference.main import AuroraBridge

    captured = []

    class _ExecPos:
        def handle(self, msg: Message):  # type: ignore[no-untyped-def]
            captured.append(msg)
            return None

    monkeypatch.setattr(main_mod, "execution_position", _ExecPos())

    cfg = SimpleNamespace(
        domains=SimpleNamespace(position_tracking=SimpleNamespace(positions_stale_ttl_sec=15)),
        bridge=SimpleNamespace(
            retry_scheduler=SimpleNamespace(
                max_attempts=3,
                min_retry_delay_ms=0,
                backoff_factor=1.0,
                jitter_ms=0,
            )
        ),
        trading=SimpleNamespace(mode="testnet"),
    )

    bridge = AuroraBridge(fsm=_FakeFSM(), config=cfg)  # type: ignore[arg-type]

    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="bridge",
        rid="rid-close-1",
        pld={
            "rid": "rid-close-1",
            "instrument": "BTCUSDT",
            "side": "SELL",
            "order": {"qty": "1.0", "price": "0", "price_ref": "0", "reduce_only": True},
            "idempotent_key": "idem-1",
            "why": ["flip_orchestration_close"],
        },
        why="trade_intent",
        data_ref=["flip_orchestration_close"],
    )

    bridge.on_trade_intent_proposed_sync(intent)

    assert captured, "Expected CMD:CLOSE passed to execution_position.handle"
    cmd = captured[0]
    assert cmd.op == "CMD"
    assert cmd.verb == "CLOSE"
    assert cmd.pld.get("symbol") == "BTCUSDT"
    assert cmd.pld.get("idempotent_key") == "idem-1"
