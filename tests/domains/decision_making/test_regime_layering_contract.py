from decimal import Decimal
from types import SimpleNamespace

from apps.reference.core.time.clock import MockClock
from apps.reference.domains.decision_making.intent.emitter import IntentEmitter


def _emitter(portfolio):
    emitted = []

    def _propose_trade_intent(**kwargs):
        emitted.append(kwargs)

    emitter = IntentEmitter(
        fsm=SimpleNamespace(emit=lambda *args, **kwargs: None),
        clock=MockClock(start_ms=1_700_000_000_000),
        config=SimpleNamespace(),
        alert_manager=None,
        get_portfolio=lambda: portfolio,
        propose_trade_intent=_propose_trade_intent,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    return emitter, emitted


def test_structural_trend_up_closes_short_position() -> None:
    portfolio = {
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "-0.5"},
        ]
    }
    emitter, emitted = _emitter(portfolio)

    emitter.handle_regime_flip(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "regime_layer": "structural",
            "regime_scope": "per_symbol",
        },
    )

    assert len(emitted) == 1
    assert emitted[0]["side"] == "BUY"
    assert emitted[0]["reduce_only"] is True
    assert emitted[0]["qty"] == Decimal("0.5")


def test_non_structural_regime_payload_does_not_trigger_flip() -> None:
    portfolio = {
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "0.5"},
        ]
    }
    emitter, emitted = _emitter(portfolio)

    emitter.handle_regime_flip(
        "BTCUSDT",
        {
            "symbol": "BTCUSDT",
            "regime": "TREND_DOWN",
            "regime_layer": "execution_micro",
            "regime_scope": "global",
        },
    )

    assert emitted == []
