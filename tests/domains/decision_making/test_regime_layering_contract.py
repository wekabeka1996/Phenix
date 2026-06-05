from decimal import Decimal
from types import SimpleNamespace

from apps.reference.core.time.clock import MockClock
from apps.reference.domains.decision_making.intent.emitter import IntentEmitter


def _emitter(portfolio):
    emitted = []

    def _propose_trade_intent(**kwargs):
        emitted.append(kwargs)

    def _emit_reduce_only_close(*, symbol, reason, rid, strategy_id):
        curr_pos = next(
            (p for p in portfolio.get("positions", []) if p.get("symbol") == symbol),
            None,
        )
        if curr_pos is None:
            return False

        position_amt = Decimal(str(curr_pos.get("positionAmt", "0")))
        if position_amt == Decimal("0"):
            return False

        emitted.append(
            {
                "symbol": symbol,
                "side": "SELL" if position_amt > 0 else "BUY",
                "qty": abs(position_amt),
                "reduce_only": True,
                "strategy_id": strategy_id,
                "rid": rid,
                "reason": reason,
            }
        )
        return True

    emitter = IntentEmitter(
        fsm=SimpleNamespace(emit=lambda *args, **kwargs: None),
        clock=MockClock(start_ms=1_700_000_000_000),
        config=SimpleNamespace(),
        alert_manager=None,
        get_portfolio=lambda: portfolio,
        propose_trade_intent=_propose_trade_intent,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        emit_reduce_only_close_fn=_emit_reduce_only_close,
        registry_lookup_fn=lambda _symbol: ["aurora"],
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
