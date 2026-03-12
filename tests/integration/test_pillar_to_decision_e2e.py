from types import SimpleNamespace

import pytest

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


def _build_handler():
    cfg = get_config().model_copy(deep=True)
    cfg.strategies.aurora.decision.scoring_version = "quadratic"

    emitted: list[tuple[str, dict]] = []

    def emit_fn(event_name: str, payload: dict) -> None:
        emitted.append((event_name, payload))

    handler = AuroraHandler(
        config=cfg,
        emit_fn=emit_fn,
        monotonic_fn=lambda: 1_700_000_000.0,
        wall_time_fn=lambda: 1_700_000_000.0,
    )
    handler._basis_required_bars_override = 0
    # This test validates CMD -> kernel -> signal wiring, not entry gate behavior.
    handler.execution_gate = None
    handler.on_regime_detected(
        {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 1.0,
            "ts_ms": 1_700_000_000_000,
            "last_update_ts_ms": 1_700_000_000_000,
        }
    )
    return handler, emitted


def test_cmd_process_strategy_emits_quadratic_signal(monkeypatch):
    """Current architecture: CMD:PROCESS_STRATEGY should emit STRATEGY_SIGNAL with quadratic psi."""
    handler, emitted = _build_handler()

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.aurora_handler.quantize_exposure",
        lambda **_: SimpleNamespace(
            qty="0.001",
            notional="120.0",
            margin_required="12.0",
            reject_reason=None,
        ),
    )

    handler.on_process_strategy(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "bar": {
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50000.0",
                "volume": "100.0",
            },
            "features": {
                "pillar_sum": 0.8,
                "pillar_contribs": {"operator": 0.2},
                "price": "50000.0",
                "atr": "100.0",
                "volatility": {"atr_14": 100.0},
                "liquidity": {"kappa": 0.9},
                "liquidity_kappa": 0.9,
                "regime": "TREND_UP",
                "bar_close_ts": 1_700_000_000_000,
            },
            "warmup": {
                "full_ready": True,
                "ready": {"liquidity_kappa": True, "spread_bps": True},
            },
            "rid": "RID-QUADRATIC-OK",
        }
    )

    produced = [p for name, p in emitted if name == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert produced, "Aurora should emit EVT:STRATEGY_SIGNAL_PRODUCED for valid quadratic CMD"

    payload = produced[-1]
    psi = payload["scoring"]["psi_vector"]

    assert payload["side"] == "BUY"
    assert psi["scoring_engine"] == "quadratic_v1"
    assert psi["s_linear"] == pytest.approx(0.8)
    assert psi["final_exposure"] == pytest.approx(0.64, abs=1e-6)


def test_cmd_process_strategy_missing_pillar_sum_blocks_fail_closed():
    """Current architecture must fail-closed when pillar_sum is absent (no signal emission)."""
    handler, emitted = _build_handler()

    handler.on_process_strategy(
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1_700_000_000_000,
            "bar": {
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50000.0",
                "volume": "100.0",
            },
            "features": {
                "price": "50000.0",
                "atr": "100.0",
                "volatility": {"atr_14": 100.0},
                "liquidity": {"kappa": 0.9},
                "liquidity_kappa": 0.9,
                "regime": "TREND_UP",
                "bar_close_ts": 1_700_000_000_000,
            },
            "warmup": {
                "full_ready": True,
                "ready": {"liquidity_kappa": True, "spread_bps": True},
            },
            "rid": "RID-QUADRATIC-BLOCKED",
        }
    )

    produced = [p for name, p in emitted if name == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    blocked = [p for name, p in emitted if name == "EVT:STRATEGY_DECISION_BLOCKED"]

    assert not produced, "Signal must not be emitted when pillar_sum is missing"
    assert blocked, "Fail-closed path must emit EVT:STRATEGY_DECISION_BLOCKED"
    assert blocked[-1]["reason_code"] == "AURORA_KERNEL_DEFERRED"
    assert blocked[-1]["details"]["defer_reason"] == "PILLAR_WARMUP"
