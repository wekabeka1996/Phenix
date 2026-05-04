from types import SimpleNamespace
from unittest.mock import MagicMock
import decimal

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.shared.decision_primitives.scoring_kernel import ScoringResult


def _make_config():
    return SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(
                    signal_threshold=0.1,
                    side_bias_window_sec=420,
                    side_bias_target_ratio=0.72,
                    side_bias_penalty_factor=0.25,
                    side_bias_min_intents=18,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    direction_strength_scoring=None,
                    signals=None,
                    holding_period=None,
                    reentry_cooldown_sec=None,
                    gates=None,
                    anti_churn=None,
                ),
                assets={"BTCUSDT": SimpleNamespace(enabled=True)},
            )
        )
    )


def _make_handler() -> AuroraHandler:
    return AuroraHandler(config=_make_config(), emit_fn=MagicMock())


def test_entry_timestamp_not_set_on_signal_emission() -> None:
    handler = _make_handler()
    state = handler._symbol_states["BTCUSDT"]

    result = ScoringResult(
        score=decimal.Decimal("0.5"),
        side="buy",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
    )
    handler._emit_signal("BTCUSDT", result, {"price": 100.0}, {})

    assert state.entry_timestamp is None


def test_entry_timestamp_set_on_trade_executed() -> None:
    handler = _make_handler()
    state = handler._symbol_states["BTCUSDT"]

    handler.on_trade_executed(
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.1",
        }
    )

    assert state.entry_timestamp is not None
    assert state.position_side == "buy"


def test_entry_timestamp_cleared_on_opposite_trade() -> None:
    handler = _make_handler()
    state = handler._symbol_states["BTCUSDT"]

    handler.on_trade_executed(
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.1",
        }
    )
    assert state.position_side == "buy"

    handler.on_trade_executed(
        {
            "symbol": "BTCUSDT",
            "side": "sell",
            "quantity": "0.1",
        }
    )

    assert state.entry_timestamp is None
    assert state.position_side == ""
    assert state.last_exit_timestamp is not None