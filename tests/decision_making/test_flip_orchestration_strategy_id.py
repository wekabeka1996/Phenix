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
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

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

    dm._propose_trade_intent = _propose_trade_intent  # type: ignore[attr-defined]
    dm._get_portfolio_position_qty_signed = DecisionMaking._get_portfolio_position_qty_signed.__get__(dm)  # type: ignore[misc]
    dm._emit_reduce_only_close = DecisionMaking._emit_reduce_only_close.__get__(dm)  # type: ignore[misc]

    ok = dm._emit_reduce_only_close("BTCUSDT", "flip_orchestration", "rid-close-1", strategy_id="mean_reversion")
    assert ok is True
    assert captured["symbol"] == "BTCUSDT"
    assert captured["side"] == "BUY"
    assert decimal.Decimal(str(captured["qty"])) == decimal.Decimal("0.186")
    assert captured["reduce_only"] is True
    assert captured["strategy_id"] == "mean_reversion"

