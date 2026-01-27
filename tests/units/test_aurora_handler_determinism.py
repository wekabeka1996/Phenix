from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.core.time import MockClock, reset_clock, set_clock
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


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


def test_monotonic_fn_uses_mock_clock() -> None:
    reset_clock()
    try:
        mock_clock = MockClock(start_ms=1705000000000, start_monotonic=1000.0)
        set_clock(mock_clock)

        handler = AuroraHandler(config=_make_config(), emit_fn=MagicMock())

        mock_clock.advance_sec(10.0)
        assert handler.monotonic_fn() == 1010.0
    finally:
        reset_clock()