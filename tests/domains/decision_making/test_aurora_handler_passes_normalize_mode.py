from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_aurora_handler_passes_normalize_mode_signed_v2() -> None:
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
    from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult

    symbol = "BTCUSDT"

    config = SimpleNamespace(
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
                    signals=SimpleNamespace(
                        normalize_signals_mode="signed_v2",
                        enable_new_metrics=True,
                        delta_price_cap_pct=0.02,
                    ),
                ),
                assets={
                    symbol: SimpleNamespace(
                        enabled=True,
                        position_mode="STRICT",
                        weights={"delta_price": 1.0},
                        feature_neutrals={"delta_price": 0.0},
                        essential_features=["delta_price"],
                    )
                },
            )
        )
    )

    emit_fn = MagicMock()
    handler = AuroraHandler(config=config, emit_fn=emit_fn)

    # Bypass liveness guard (fail-closed if heartbeat missing)
    state = handler._symbol_states[symbol]
    state.last_regime_heartbeat_ms = int(handler.monotonic_fn() * 1000)
    state.regime = "DEFAULT"

    fake_kernel = MagicMock()
    fake_kernel.compute.return_value = ScoringResult(
        score=Decimal("0"),
        side="",
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        deferred=True,
        defer_reason="TEST",
    )
    handler.scoring_kernel_cls = fake_kernel

    cmd = {
        "symbol": symbol,
        "tf_sec": 300,
        "bar_close_ts": int(time.time() * 1000),
        "features": {"price": "100", "delta_price": "0.0"},
        "warmup": {"full_ready": True, "ready": {"delta_price": True}},
        "rid": "r1",
    }

    with patch(
        "apps.reference.domains.decision_making.aurora_handler.write_trade_intent_rejected",
        lambda *_args, **_kwargs: None,
    ):
        handler.on_process_strategy(cmd)

    _args, kwargs = fake_kernel.compute.call_args
    assert kwargs["normalize_mode"] == "signed_v2"

