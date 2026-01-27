from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_warmup_only_from_cmd_process_strategy() -> None:
    handler = AuroraHandler(config=_make_config(), emit_fn=MagicMock())
    state = handler._symbol_states["BTCUSDT"]

    handler.on_regime_detected(
        {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "warmup": {"full_ready": True, "ticks_seen": 100},
        }
    )
    assert state.warmup_full_ready is False

    handler.on_features_data_only(
        {
            "symbol": "BTCUSDT",
            "warmup": {"full_ready": True, "ticks_seen": 100},
        }
    )
    assert state.warmup_full_ready is False

    handler.on_process_strategy(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1705000000000,
            "features": {"price": 100.0},
            "warmup": {"full_ready": True},
        }
    )
    assert state.warmup_full_ready is True