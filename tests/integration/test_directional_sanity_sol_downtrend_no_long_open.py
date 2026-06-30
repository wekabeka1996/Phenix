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
    from apps.reference.domains.decision_making.core.facade import DecisionMaking

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
    dm._clock = MagicMock()
    dm._clock.now_ms.return_value = 1700000000000
    dm.symbol_states = {"SOLUSDT": {"_delta_price_hist": deque([-1.0, -0.9, -0.8], maxlen=20)}}
    dm._per_symbol_regimes = {"SOLUSDT": {"regime": "BEAR_TREND", "confidence": 1.0}}

    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0
    dm._record_blocked_intent = lambda sym: None
    dm._emit_trade_intent_rejected = lambda **_k: None

    dm.config = MagicMock()
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.5
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.hard_veto_consecutive_bars = 2
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


def test_single_bar_uptick_does_not_hard_block_short_when_veto_requires_two_bars():
    from apps.reference.domains.decision_making.core.facade import DecisionMaking

    fsm = FakeFSM()

    class _Builder:
        def build_and_emit(self, **kwargs):
            sg = kwargs["sg"]
            fsm.emit(
                "EVT:DECISION_TRACE_EMITTED",
                payload={
                    "gate_outcome": "ALLOW",
                    "trend_dir": sg.trend_dir,
                    "trend_run_length": sg.trend_run_length,
                    "why": sg.why_short,
                },
                why="decision_trace",
            )
            fsm.emit(
                "EVT:TRADE_INTENT_PROPOSED",
                payload={"instrument": kwargs["symbol"], "side": kwargs["side"]},
                why="trade_intent",
            )

    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)

    dm.logger = MagicMock()
    dm.fsm = fsm
    dm._clock = MagicMock()
    dm._clock.now_ms.return_value = 1700000000000
    dm.symbol_states = {"ETHUSDT": {"_delta_price_hist": deque([0.53], maxlen=20)}}
    dm._per_symbol_regimes = {"ETHUSDT": {"regime": "LOW_VOLATILITY", "confidence": 0.6191}}

    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0
    dm.normalize_signals_mode = "strict"
    dm._builder = _Builder()
    dm._record_blocked_intent = lambda sym: None
    dm._emit_trade_intent_rejected = lambda **_k: None

    dm.config = MagicMock()
    dm.config.trading_mode = "live"
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.min_regime_confidence = 0.42
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 1
    dm.config.domains.decision_making.directional_sanity.hard_veto_consecutive_bars = 2
    dm.config.domains.decision_making.price_motion_sanity.enabled = False
    dm.config.domains.decision_making.low_vol_cost_floor_gate = MagicMock(enabled=False)

    dm._propose_trade_intent(
        symbol="ETHUSDT",
        side="SELL",
        qty=Decimal("1"),
        price=Decimal("2150"),
        why_chain=["signal_score=-0.1693"],
        rid="rid-eth-soft-short-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    intents = [e for e in fsm.emitted if e[0] == "EVT:TRADE_INTENT_PROPOSED"]
    assert intents, "Expected SELL intent to pass when only one positive delta bar exists"

    traces = [e for e in fsm.emitted if e[0] == "EVT:DECISION_TRACE_EMITTED"]
    assert traces, "Expected forensic trace emission for allowed intent"
    payload = traces[-1][1] or {}
    assert payload.get("gate_outcome") == "ALLOW"
    assert payload.get("trend_dir") == "UP"
    assert payload.get("trend_run_length") == 1
    assert "countertrend short soft" in (payload.get("why") or "")


def test_btc_two_bar_uptick_still_blocks_short_when_veto_requires_two_bars():
    from apps.reference.domains.decision_making.core.facade import DecisionMaking

    fsm = FakeFSM()

    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)

    dm.logger = MagicMock()
    dm.fsm = fsm
    dm._clock = MagicMock()
    dm._clock.now_ms.return_value = 1700000000000
    dm.symbol_states = {"BTCUSDT": {"_delta_price_hist": deque([5.2, 18.5], maxlen=20)}}
    dm._per_symbol_regimes = {"BTCUSDT": {"regime": "LOW_VOLATILITY", "confidence": 0.6111}}

    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0
    dm._record_blocked_intent = lambda sym: None
    dm._emit_trade_intent_rejected = lambda **_k: None

    dm.config = MagicMock()
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.min_regime_confidence = 0.42
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 1
    dm.config.domains.decision_making.directional_sanity.hard_veto_consecutive_bars = 2
    dm.config.domains.decision_making.price_motion_sanity.enabled = False

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="SELL",
        qty=Decimal("0.1"),
        price=Decimal("70335"),
        why_chain=["signal_score=-0.1413"],
        rid="rid-btc-hard-short-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    intents = [e for e in fsm.emitted if e[0] == "EVT:TRADE_INTENT_PROPOSED"]
    assert intents == [], "Expected BTC SELL to remain blocked after two-bar uptick confirmation"

    traces = [e for e in fsm.emitted if e[0] == "EVT:DECISION_TRACE_EMITTED"]
    assert traces, "Expected forensic trace emission for denied BTC intent"
    payload = traces[-1][1] or {}
    assert payload.get("gate_outcome") == "DENY"
    assert payload.get("trend_dir") == "UP"
    assert payload.get("trend_run_length") == 2
    assert payload.get("deny_reason") == "NRR-027"
