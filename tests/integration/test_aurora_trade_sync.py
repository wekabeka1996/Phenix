from types import SimpleNamespace
from unittest.mock import MagicMock

from vfoundation.core import FSMCore
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.strategies.plugins.aurora_builtin import _AuroraHandlerWrapper


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


def test_trade_executed_reaches_aurora_handler() -> None:
    fsm = FSMCore()
    handler = AuroraHandler(
        config=_make_config(),
        emit_fn=lambda name, payload: fsm.emit(name, payload, why="test"),
    )
    wrapper = _AuroraHandlerWrapper(handler, fsm)
    wrapper.register()

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.1",
            "price": "100.0",
            "ts": 1705000000000,
            "venue": "test",
        },
        why="test:trade",
    )

    state = handler._symbol_states["BTCUSDT"]
    assert state.position_side == "buy"