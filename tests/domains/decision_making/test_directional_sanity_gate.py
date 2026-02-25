from __future__ import annotations

from collections import deque
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def dm_minimal():
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)

    dm.logger = MagicMock()
    dm.fsm = MagicMock()

    dm.symbol_states = {}
    dm._per_symbol_regimes = {}

    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0

    dm.config = MagicMock()
    dm.config.domains.decision_making.directional_sanity.enabled = True
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.5
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.min_regime_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 2
    # Disable price_motion_sanity for these directional-only unit tests.
    dm.config.domains.decision_making.price_motion_sanity.enabled = False

    from apps.reference.core.time.clock import LiveClock
    dm._clock = LiveClock()
    dm._emitter = MagicMock()

    return dm


def _last_trace_payload(dm):
    calls = [
        c
        for c in dm.fsm.emit.call_args_list
        if c.args and c.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]
    assert calls, "Expected EVT:DECISION_TRACE_EMITTED to be emitted"
    return calls[-1].kwargs.get("payload")


def test_trend_down_intent_long_denied(dm_minimal):
    from apps.reference.domains.decision_making.normalized_reject_reasons import (
        NormalizedRejectReasons,
    )

    symbol = "SOLUSDT"
    dm_minimal.symbol_states[symbol] = {"_delta_price_hist": deque([-1.0, -0.8], maxlen=20)}

    dm_minimal._propose_trade_intent(
        symbol=symbol,
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.12"],
        rid="rid-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    payload = _last_trace_payload(dm_minimal)
    assert payload["trend_dir"] == "DOWN"
    assert payload["intent_side"] == "LONG"
    assert payload["gate_outcome"] == "DENY"
    assert payload["deny_reason"] == NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED

    assert not any(
        c.args and c.args[0] == "EVT:TRADE_INTENT_PROPOSED" for c in dm_minimal.fsm.emit.call_args_list
    )


def test_trend_up_intent_short_denied(dm_minimal):
    from apps.reference.domains.decision_making.normalized_reject_reasons import (
        NormalizedRejectReasons,
    )

    symbol = "SOLUSDT"
    dm_minimal.symbol_states[symbol] = {"_delta_price_hist": deque([+1.2, +0.9], maxlen=20)}

    dm_minimal._propose_trade_intent(
        symbol=symbol,
        side="SELL",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.12"],
        rid="rid-2",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    payload = _last_trace_payload(dm_minimal)
    assert payload["trend_dir"] == "UP"
    assert payload["intent_side"] == "SHORT"
    assert payload["gate_outcome"] == "DENY"
    assert payload["deny_reason"] == NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED

    assert not any(
        c.args and c.args[0] == "EVT:TRADE_INTENT_PROPOSED" for c in dm_minimal.fsm.emit.call_args_list
    )


def test_trend_undefined_fail_closed_denied(dm_minimal):
    from apps.reference.domains.decision_making.normalized_reject_reasons import (
        NormalizedRejectReasons,
    )

    symbol = "SOLUSDT"
    # Below min_abs_delta_price=0.5 => UNKNOWN trend => DENY
    dm_minimal.symbol_states[symbol] = {"_delta_price_hist": deque([0.1, 0.2], maxlen=20)}

    dm_minimal._propose_trade_intent(
        symbol=symbol,
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.12"],
        rid="rid-3",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1700000000000,
    )

    payload = _last_trace_payload(dm_minimal)
    assert payload["trend_dir"] == "UNKNOWN"
    assert payload["gate_outcome"] == "DENY"
    assert payload["deny_reason"] == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION

    assert not any(
        c.args and c.args[0] == "EVT:TRADE_INTENT_PROPOSED" for c in dm_minimal.fsm.emit.call_args_list
    )
