import time
from unittest.mock import MagicMock

import pytest

from vfoundation.core.protocol import Message


@pytest.fixture
def mock_fsm():
    fsm = MagicMock()
    fsm.emitted_events = []

    def track_emit(event_name, payload, why=None, data_ref=None):
        fsm.emitted_events.append({"event": event_name, "payload": payload})

    fsm.emit = MagicMock(side_effect=track_emit)
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def base_config():
    return {
        "trading": {
            "decision": {"mode": "standard"},
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "mean_reversion_1m": {
                "enabled": True,
                "emit_trade_intent_directly": False,
                "assets": {"DOGEUSDT": {"enabled": True}},
            },
        },
        "domains": {
            "decision_making": {
                "risk_skew": {"max_skew_sec": 5, "max_defer_count": 3, "defer_cooldown_sec": 1}
            }
        },
    }


def _mr_signal_event(*, symbol: str, side: str, rid: str):
    return Message(
        op="EVT",
        verb="MR_SIGNAL_PRODUCED",
        src="mr_handler",
        dst="decision_making",
        pld={
            "strategy_id": "MR",
            "symbol": symbol,
            "ts": int(time.time() * 1000),
            "side": side,
            "confidence": 0.8,
            "qty_hint": "100.0",
            "why_chain": ["unit_test"],
            "cooldown_class": "mr_entry",
            "price_ctx": {"entry_price": "0.08"},
            "flat_regime": "FLAT_NORMAL",
            "rid": rid,
            "position_size_usd": 100.0,
        },
    )


def _assert_v1_defer_payload(payload: dict):
    assert payload.get("retry_key")
    assert isinstance(payload.get("retry_key"), str)
    assert payload.get("next_allowed_ts") is not None
    assert payload.get("original_event") is not None
    assert payload.get("retry_policy") is not None
    assert payload["original_event"]["payload_min"]["symbol"]
    assert payload["original_event"]["payload_min"]["side"]


def test_risk_not_ready_defers_as_v1(mock_fsm, base_config):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking(config=base_config, fsm=mock_fsm)
    dm._on_mr_signal_gateway(_mr_signal_event(symbol="DOGEUSDT", side="BUY", rid="rid-risk-missing"))

    deferred = [e for e in mock_fsm.emitted_events if e["event"] == "EVT:INTENT_DEFERRED"]
    assert len(deferred) == 1
    assert deferred[0]["payload"]["reason"] == "NRR-DATA-NOT-READY"
    _assert_v1_defer_payload(deferred[0]["payload"])


def test_portfolio_unknown_defers_as_v1(mock_fsm, base_config):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking(config=base_config, fsm=mock_fsm)
    now_ms = int(time.time() * 1000)

    dm.symbol_states["DOGEUSDT"]["risk"] = {
        "ts": now_ms,
        "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
    }
    dm.symbol_states["DOGEUSDT"]["features"] = {"ts": now_ms}
    dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
    dm.latest_portfolio = None

    dm._on_mr_signal_gateway(_mr_signal_event(symbol="DOGEUSDT", side="BUY", rid="rid-portfolio-unknown"))

    deferred = [e for e in mock_fsm.emitted_events if e["event"] == "EVT:INTENT_DEFERRED"]
    assert len(deferred) == 1
    assert deferred[0]["payload"]["reason"] == "NRR-PORTFOLIO-UNKNOWN"
    _assert_v1_defer_payload(deferred[0]["payload"])


def test_risk_skew_defers_as_v1(mock_fsm, base_config):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    dm = DecisionMaking(config=base_config, fsm=mock_fsm)
    now_ms = int(time.time() * 1000)

    dm.symbol_states["DOGEUSDT"]["risk"] = {
        "ts": now_ms - 10_000,
        "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.3},
    }
    dm.symbol_states["DOGEUSDT"]["features"] = {"ts": now_ms}
    dm._per_symbol_regimes = {"DOGEUSDT": {"regime": "FLAT_NORMAL"}}
    dm.latest_portfolio = {"positions": []}

    dm._on_mr_signal_gateway(_mr_signal_event(symbol="DOGEUSDT", side="BUY", rid="rid-risk-skew"))

    deferred = [e for e in mock_fsm.emitted_events if e["event"] == "EVT:INTENT_DEFERRED"]
    assert len(deferred) == 1
    assert deferred[0]["payload"]["reason"] == "NRR-RISK-STALE"
    _assert_v1_defer_payload(deferred[0]["payload"])

