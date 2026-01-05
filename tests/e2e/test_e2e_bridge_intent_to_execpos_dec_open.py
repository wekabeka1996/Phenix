from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable

import pytest

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


def test_e2e_trade_intent_proposed_leads_to_execpos_dec_open(monkeypatch, fsm_harness):
    """Smoke E2E: if intent exists, real bridge produces DEC:OPEN via real ExecPosFSM."""

    from apps.reference.config_loader import ConfigLoader
    import apps.reference.main as main_mod

    execpos_fsm, _bus, _cfg = fsm_harness

    # ExecPosFSM passes its own internal portfolio_state into ExposureGuard.can_open().
    # Seed that internal state and notify ExposureGuard to avoid fail-closed EQUITY_UNKNOWN.
    portfolio_state = {
        "positions_last_ts_ms": 9999999999999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    execpos_fsm._latest_portfolio_state = dict(portfolio_state)
    execpos_fsm.exposure_guard.on_portfolio(dict(portfolio_state))

    # Make sure leverage defaults exist for reserve/can_open path.
    _cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}

    # Patch runtime globals used by AuroraBridge._dispatch_open()
    monkeypatch.setattr(main_mod, "execution_position", execpos_fsm, raising=False)

    config = ConfigLoader().load_config(is_live_execution=False)

    # Ensure capacity gate has required per-instrument execution fields.
    spec = (config.instruments or {}).get("BTCUSDT") if hasattr(config, "instruments") else None
    exec_cfg = getattr(spec, "execution", None) if spec is not None else None
    if exec_cfg is not None:
        if getattr(exec_cfg, "target_leverage", None) in (None, ""):
            setattr(exec_cfg, "target_leverage", 20)
        if getattr(exec_cfg, "max_notional_utilization", None) in (None, ""):
            setattr(exec_cfg, "max_notional_utilization", 1.0)

    fsm = LoopbackFSM()

    bridge = main_mod.AuroraBridge(fsm=fsm, config=config)
    monkeypatch.setattr(main_mod, "_bridge_instance", bridge, raising=False)

    # Make portfolio "fresh" and equity positive so bridge gates pass.
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

    # Emit trade intent that matches typical DM shape (no order_type on purpose).
    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload={
            "rid": "RID-E2E-INTENT-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "qty": str(Decimal("0.01")),
                "price": str(Decimal("1000")),
                "price_ref": str(Decimal("1000")),
                "reduce_only": False,
            },
            "idempotent_key": "K-E2E-INTENT-1",
            "why": ["e2e_intent"],
        },
        why="e2e_intent",
        data_ref=["e2e_intent"],
    )

    assert _has_emitted(fsm, "DEC:OPEN"), "Expected DEC:OPEN from ExecPosFSM via bridge"
