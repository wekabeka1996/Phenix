from __future__ import annotations

import time
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any, Callable

import pytest
pytestmark = pytest.mark.skip(reason="Refactoring: AuroraBridge class deleted")

from vfoundation.core.protocol import Message


pytest_plugins = ("tests.domains.execution_position.conftest",)


class LoopbackFSM:
    """Minimal synchronous event bus: emit() immediately calls listeners."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[Message], None]]] = defaultdict(list)
        self.emitted: list[tuple[str, dict[str, Any], str | None, Any]] = []
        self.order_index = None

    def listen(self, event_name: str, handler: Callable[[Message], None]) -> None:
        self._listeners[event_name].append(handler)

    def emit(self, event_name: str, payload=None, why=None, data_ref=None, **_kwargs) -> None:
        pld = payload or {}
        self.emitted.append((event_name, pld, why, data_ref))

        op, verb = (event_name.split(":", 1) + [""])[:2]
        msg = Message(
            op=op,
            verb=verb,
            src="loopback_fsm",
            dst="*",
            pld=pld,
            why=why,
            data_ref=[] if data_ref is None else data_ref,
        )
        for handler in list(self._listeners.get(event_name, [])):
            handler(msg)


def _has_emitted(fsm: LoopbackFSM, event_name: str) -> bool:
    return any(evt == event_name for (evt, _pld, _why, _ref) in fsm.emitted)


def _emitted_payloads(fsm: LoopbackFSM, event_name: str) -> list[dict[str, Any]]:
    return [pld for (evt, pld, _why, _ref) in fsm.emitted if evt == event_name]


def test_e2e_sol_downtrend_blocks_long_before_trade_intent(monkeypatch, fsm_harness):
    """True chain wiring: DM emits → Bridge listens → ExecPos handles.

    Assertion: DirectionalSanity DENY stops before EVT:TRADE_INTENT_PROPOSED,
    thus no CMD:OPEN / DEC:OPEN in the system.
    """

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.decision_making.core.facade import DecisionMaking
    import apps.reference.main as main_mod

    execpos_fsm, _bus, _cfg = fsm_harness

    # Patch runtime globals used by AuroraBridge._dispatch_open()
    monkeypatch.setattr(main_mod, "execution_position", execpos_fsm, raising=False)

    config = ConfigLoader().load_config(is_live_execution=False)

    fsm = LoopbackFSM()

    # Bring up real AuroraBridge and register it as the module global instance
    bridge = main_mod.AuroraBridge(fsm=fsm, config=config)
    monkeypatch.setattr(main_mod, "_bridge_instance", bridge, raising=False)

    # Make portfolio "fresh" so Bridge wouldn't defer if an intent were emitted.
    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:PORTFOLIO_STATE_UPDATED",
        payload={
            "positions_last_ts_ms": now_ms,
            "equity_free_usdt": "10000",
            "open_positions_margin_usd": "0",
            "positions": [],
        },
        why="test_portfolio_fresh",
    )

    dm = DecisionMaking(fsm=fsm, config=config)

    # Enable DirectionalSanity for the test (SSOT strict model, but runtime is mutable)
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.5
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 2
    # Disable price_motion_sanity for this directional-only E2E test.
    dm.config.domains.decision_making.price_motion_sanity.enabled = False

    # Provide a confirmed DOWN trend via delta_price history.
    dm.symbol_states["SOLUSDT"]["_delta_price_hist"] = deque([-1.0, -0.9, -0.8], maxlen=20)
    dm._per_symbol_regimes["SOLUSDT"] = {"regime": "BEAR_TREND", "confidence": 1.0}

    # Attempt to open LONG in a confirmed downtrend.
    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.12"],
        rid="rid-sol-e2e-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=now_ms,
    )

    assert _has_emitted(fsm, "EVT:DECISION_TRACE_EMITTED"), "Expected forensic trace event on DENY"
    assert not _has_emitted(
        fsm, "EVT:TRADE_INTENT_PROPOSED"
    ), "Expected NO trade intent emission when downtrend blocks LONG"

    # Strong E2E safety: since no intent emitted, bridge must not be able to open.
    assert not _has_emitted(fsm, "CMD:OPEN"), "Expected no CMD:OPEN in blocked scenario"
    assert not _has_emitted(fsm, "DEC:OPEN"), "Expected no DEC:OPEN in blocked scenario"

    traces = _emitted_payloads(fsm, "EVT:DECISION_TRACE_EMITTED")
    assert traces, "Missing DECISION_TRACE payload"
    last = traces[-1]
    assert last.get("symbol") == "SOLUSDT"
    assert last.get("intent_side") == "LONG"
    assert last.get("gate_outcome") == "DENY"
    assert last.get("deny_reason") == "NRR-027"
