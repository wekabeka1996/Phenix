from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class FakeFSM:
    def __init__(self) -> None:
        self._listeners = defaultdict(list)
        self.emitted = []
        self.logger = MagicMock()
        self.order_index = None

    def listen(self, event_name: str, callback):
        self._listeners[event_name].append(callback)

    def emit(self, event_name: str, payload=None, why=None, **kwargs):
        self.emitted.append((event_name, payload, why, kwargs))
        for cb in self._listeners.get(event_name, []):
            evt = MagicMock()
            evt.pld = payload
            evt.why = why
            cb(evt)


def test_synthetic_sol_downtrend_no_cmd_open_long():
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    fsm = FakeFSM()
    opened = []

    def bridge_to_cmd_open(event):
        # Minimal bridge: if intent is BUY -> would open LONG
        side = (event.pld or {}).get("side")
        if str(side).upper() == "BUY":
            fsm.emit("CMD:OPEN", payload={"symbol": (event.pld or {}).get("instrument"), "side": side})

    def on_cmd_open(event):
        opened.append(event.pld)

    fsm.listen("EVT:TRADE_INTENT_PROPOSED", bridge_to_cmd_open)
    fsm.listen("CMD:OPEN", on_cmd_open)

    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)

    dm.logger = MagicMock()
    dm.fsm = fsm
    dm.symbol_states = {"SOLUSDT": {"_delta_price_hist": deque([-1.0, -0.9, -0.8], maxlen=20)}}
    dm._per_symbol_regimes = {"SOLUSDT": {"regime": "BEAR_TREND", "confidence": 1.0}}

    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0

    dm.config = MagicMock()
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.5
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 2
    # Disable price_motion_sanity for this directional-only integration test.
    dm.config.domains.decision_making.price_motion_sanity.enabled = False

    # Attempt to open LONG in downtrend -> should be denied, thus no TRADE_INTENT_PROPOSED and no CMD:OPEN
    dm._propose_trade_intent(
        symbol="SOLUSDT",
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.12"],
        rid="rid-sol-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    assert opened == [], "Expected no CMD:OPEN when downtrend blocks LONG"
