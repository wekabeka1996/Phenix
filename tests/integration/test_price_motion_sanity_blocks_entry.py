from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal
from unittest.mock import MagicMock, patch


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


def _mk_dm():
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    fsm = FakeFSM()
    opened = []

    def bridge_to_cmd_open(event):
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
    dm.intents_blocked_total = 0
    dm.intents_seen_total = 0
    dm.alert_manager = None
    dm.last_alert_check_time = 0.0
    dm._per_symbol_regimes = {}

    dm.config = MagicMock()
    dm.config.domains.decision_making.directional_sanity.enabled = False
    dm.config.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
    dm.config.domains.decision_making.directional_sanity.min_confidence = 0.0
    dm.config.domains.decision_making.directional_sanity.consecutive_bars = 2

    dm.config.domains.decision_making.price_motion_sanity.enabled = True
    dm.config.domains.decision_making.price_motion_sanity.k_vol = 2.0
    dm.config.domains.decision_making.price_motion_sanity.flash_window_sec = 10
    dm.config.domains.decision_making.price_motion_sanity.bleed_window_sec = 300
    dm.config.domains.decision_making.price_motion_sanity.flash_threshold_norm = 1.0
    dm.config.domains.decision_making.price_motion_sanity.bleed_threshold_norm = 0.7
    dm.config.domains.decision_making.price_motion_sanity.require_bleed_ready = True

    return dm, fsm, opened


def test_price_motion_bleed_blocks_long_entry_and_emits_trace():
    dm, fsm, opened = _mk_dm()

    symbol = "SOLUSDT"
    dm.symbol_states = {
        symbol: {
            "_delta_price_hist": deque([], maxlen=20),
            "features": {
                "price_motion": {
                    "pm_norm_10s": 0.0,
                    "pm_norm_60s": 0.0,
                    "pm_norm_300s": -0.95,
                    "vol_pct_10s": 0.01,
                    "vol_pct_60s": 0.01,
                    "vol_pct_300s": 0.01,
                }
            },
        }
    }

    dm._propose_trade_intent(
        symbol=symbol,
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.9"],
        rid="rid-sol-bleed-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_000,
    )

    assert opened == []
    traces = [e for e in fsm.emitted if e[0] == "EVT:DECISION_TRACE_EMITTED"]
    assert traces, "Expected EVT:DECISION_TRACE_EMITTED on gate DENY"
    payload = traces[-1][1] or {}
    assert payload.get("deny_reason") == "NRR-030"


def test_price_motion_flash_blocks_long_entry_and_emits_trace():
    dm, fsm, opened = _mk_dm()

    symbol = "SOLUSDT"
    dm.symbol_states = {
        symbol: {
            "_delta_price_hist": deque([], maxlen=20),
            "features": {
                "price_motion": {
                    "pm_norm_10s": -1.0,
                    "pm_norm_60s": 0.0,
                    "pm_norm_300s": 0.0,
                    "vol_pct_10s": 0.01,
                    "vol_pct_60s": 0.01,
                    "vol_pct_300s": 0.01,
                }
            },
        }
    }

    dm._propose_trade_intent(
        symbol=symbol,
        side="BUY",
        qty=Decimal("1"),
        price=Decimal("100"),
        why_chain=["signal_score=0.9"],
        rid="rid-sol-flash-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_000,
    )

    assert opened == []
    traces = [e for e in fsm.emitted if e[0] == "EVT:DECISION_TRACE_EMITTED"]
    assert traces, "Expected EVT:DECISION_TRACE_EMITTED on gate DENY"
    payload = traces[-1][1] or {}
    assert payload.get("deny_reason") == "NRR-029"

