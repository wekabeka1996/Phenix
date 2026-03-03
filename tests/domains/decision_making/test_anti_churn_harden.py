"""ANTI-CHURN-HARDEN-001 tests.

Focus:
- Asymmetric regime inertia (risk-off immediate, risk-on delayed)
- Same severity transitions must NOT freeze (immediate update)
- Monotonic timing is used for interval checks (wall time must not affect confirm windows)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


class SplitClock:
    """A controllable clock with independent wall and monotonic time."""

    def __init__(self, *, wall_start: float = 1700000000.0, mono_start: float = 0.0):
        self._wall = float(wall_start)
        self._mono = float(mono_start)

    def time(self) -> float:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def advance_wall(self, sec: float) -> None:
        self._wall += float(sec)

    def advance_mono(self, sec: float) -> None:
        self._mono += float(sec)


def _make_handler(clock: SplitClock, *, confirm_window_sec: float = 90.0) -> AuroraHandler:
    cfg = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(
                    signal_threshold=0.1,
                    side_bias_window_sec=420,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    direction_strength_scoring=None,
                    signals=SimpleNamespace(
                        normalize_signals_mode="signed_v2",
                        enable_new_metrics=True,
                        delta_price_cap_pct=0.02,
                    ),
                    anti_churn=SimpleNamespace(
                        enabled=True,
                        regime_inertia=SimpleNamespace(
                            confirm_window_sec=confirm_window_sec,
                            confirm_window_same_severity_sec=5.0,
                            immediate_risk_off=True,
                            severity_map={
                                "TREND_UP": 20,
                                "TREND_DOWN": 20,
                                "FLAT_LOW": 50,
                            },
                        ),
                        cost_gate=SimpleNamespace(
                            enabled=True,
                            fees_are_round_trip=False,
                            min_rv_bps_factor=1.5,
                            default_cost_bps=4.0,
                            vol_lookback_sec=60,
                        ),
                        time_multipliers={"DEFAULT": 1.0},
                    ),
                ),
                assets={
                    "BTCUSDT": SimpleNamespace(
                        enabled=True,
                        fees_bps=1.0,
                        execution=SimpleNamespace(max_slippage_bps=0),
                    )
                },
            )
        )
    )

    return AuroraHandler(
        config=cfg,
        emit_fn=MagicMock(),
        wall_time_fn=clock.time,
        monotonic_fn=clock.monotonic,
    )


def _emit_regime(handler: AuroraHandler, clock: SplitClock, regime: str) -> None:
    handler.on_regime_detected(
        {
            "symbol": "BTCUSDT",
            "regime": regime,
            "confidence": 0.9,
            "ts_ms": int(clock.time() * 1000),
        }
    )


def test_risk_off_immediate_effective_update():
    """Risk-Off: TREND_UP(20) -> FLAT_LOW(50) must update effective immediately."""
    clock = SplitClock()
    handler = _make_handler(clock, confirm_window_sec=90.0)

    _emit_regime(handler, clock, "TREND_UP")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "TREND_UP"

    clock.advance_mono(1)
    clock.advance_wall(1)
    _emit_regime(handler, clock, "FLAT_LOW")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"


def test_risk_on_delayed_by_confirm_window():
    """Risk-On: FLAT_LOW(50) -> TREND_UP(20) must wait confirm_window_sec."""
    clock = SplitClock()
    handler = _make_handler(clock, confirm_window_sec=10.0)

    _emit_regime(handler, clock, "FLAT_LOW")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"

    clock.advance_mono(1)
    clock.advance_wall(1)
    _emit_regime(handler, clock, "TREND_UP")
    # Still not confirmed
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"

    clock.advance_mono(10)
    clock.advance_wall(10)
    # Re-emit same raw to trigger evaluation
    _emit_regime(handler, clock, "TREND_UP")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "TREND_UP"


def test_same_severity_immediate_no_freeze():
    """Same severity uses small buffer (prevents flicker)."""
    clock = SplitClock()
    handler = _make_handler(clock, confirm_window_sec=90.0)

    _emit_regime(handler, clock, "TREND_UP")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "TREND_UP"

    clock.advance_mono(1)
    clock.advance_wall(1)
    _emit_regime(handler, clock, "TREND_DOWN")
    # Not yet confirmed (buffer=5s)
    assert handler._symbol_states["BTCUSDT"].regime_effective == "TREND_UP"

    clock.advance_mono(5)
    clock.advance_wall(5)
    _emit_regime(handler, clock, "TREND_DOWN")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "TREND_DOWN"


@pytest.mark.skip(reason="LEGACY: _check_cost_gate not implemented in AuroraHandler. TODO: CFG-COST-GATE-01")
def test_round_trip_fee_adjustment_and_source_telemetry():
    """If fees_are_round_trip is False, handler doubles fees for safety and reports telemetry."""
    clock = SplitClock()
    handler = _make_handler(clock, confirm_window_sec=10.0)

    _emit_regime(handler, clock, "TREND_UP")

    blocked, metrics = handler._check_cost_gate(
        symbol="BTCUSDT",
        features={
            "rv_bps": 100.0,
            "spread_bps": 1.0,
        },
    )
    assert blocked is False
    # fees_bps=1.0 from config; doubled to 2.0 because fees_are_round_trip=False
    assert metrics["fees_bps"] == 1.0
    assert metrics["fees_component_bps"] == 2.0
    assert metrics["is_round_trip_adjusted"] is True
    assert metrics["cost_bps"] == 3.0  # 1.0 spread + 2.0 fees
    assert metrics["cost_bps_source"] == "components"


def test_monotonicity_confirm_window_ignores_wall_time_jumps():
    """If wall time jumps forward but monotonic does not, confirm window must NOT pass."""
    clock = SplitClock()
    handler = _make_handler(clock, confirm_window_sec=10.0)

    _emit_regime(handler, clock, "FLAT_LOW")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"

    # Raw improves to TREND_UP; confirm window starts.
    clock.advance_mono(1)
    clock.advance_wall(1)
    _emit_regime(handler, clock, "TREND_UP")
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"

    # Wall time jumps massively; monotonic barely moves.
    clock.advance_wall(10_000)
    clock.advance_mono(1)
    _emit_regime(handler, clock, "TREND_UP")

    # Still not confirmed because monotonic advanced only ~2s total.
    assert handler._symbol_states["BTCUSDT"].regime_effective == "FLAT_LOW"
