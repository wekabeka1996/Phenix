import decimal
from unittest.mock import MagicMock


def test_flip_orchestration_close_uses_originating_strategy_id():
    """
    Regression test:
    Flip Orchestration MUST emit reduce-only CLOSE using the originating strategy_id.

    Otherwise, the close intent can be blocked by strategies_registry arbitration
    when a symbol is assigned to a different strategy (e.g. BTCUSDT assigned to
    mean_reversion), leaving a position stuck and backtests with only 1 trade.
    """
    from apps.reference.domains.decision_making.core.facade import DecisionMaking
    from apps.reference.domains.decision_making.intent.flip import FlipOrchestrator

    dm = DecisionMaking.__new__(DecisionMaking)  # avoid full init
    dm.latest_portfolio = {
        "positions": [
            # Short position -> CLOSE should be BUY reduce_only
            {"symbol": "BTCUSDT", "positionAmt": "-0.186"},
        ]
    }
    dm.logger = MagicMock()

    captured = {}

    def _propose_trade_intent(**kwargs):
        captured.update(kwargs)

    def _get_portfolio_position_qty_signed(symbol: str):
        portfolio = dm.latest_portfolio or {}
        positions = portfolio.get("positions", []) if isinstance(portfolio, dict) else []
        if not isinstance(positions, list):
            return None, "UNKNOWN"
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            if str(pos.get("symbol", "")).upper() != symbol.upper():
                continue
            raw_qty = pos.get("positionAmt")
            try:
                qty = decimal.Decimal(str(raw_qty))
            except Exception:
                return None, "UNKNOWN"
            if qty > 0:
                return qty, "LONG"
            if qty < 0:
                return qty, "SHORT"
            return decimal.Decimal("0"), "FLAT"
        return decimal.Decimal("0"), "FLAT"

    dm._propose_trade_intent = _propose_trade_intent  # type: ignore[attr-defined]
    dm._emit_reduce_only_close = DecisionMaking._emit_reduce_only_close.__get__(dm)  # type: ignore[misc]
    dm._flip = FlipOrchestrator(
        clock=MagicMock(now_ms=lambda: 0, now_sec=lambda: 0.0),
        config=MagicMock(),
        fsm=MagicMock(),
        get_position_state=MagicMock(return_value="UNKNOWN"),
        get_portfolio_position_qty_signed=_get_portfolio_position_qty_signed,
        get_flip_config=MagicMock(return_value=(True, 1.0)),
        propose_trade_intent=dm._propose_trade_intent,
        emit_intent_deferred_v1=MagicMock(),
        logger=dm.logger,
    )

    ok = dm._emit_reduce_only_close("BTCUSDT", "flip_orchestration", "rid-close-1", strategy_id="mean_reversion")
    assert ok is True
    assert captured["symbol"] == "BTCUSDT"
    assert captured["side"] == "BUY"
    assert decimal.Decimal(str(captured["qty"])) == decimal.Decimal("0.186")
    assert captured["reduce_only"] is True
    assert captured["strategy_id"] == "mean_reversion"

