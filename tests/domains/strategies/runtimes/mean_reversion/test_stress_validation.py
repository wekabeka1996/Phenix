from __future__ import annotations

from apps.reference.domains.strategies.runtimes.mean_reversion.stress_validation import (
    MRStressConfig,
    build_mr_stress_report,
    promotion_gate_passes,
)


def test_mr_stress_applies_fee_and_slippage_per_trade() -> None:
    reports = build_mr_stress_report(
        [
            {
                "symbol": "BTCUSDT",
                "flat_regime": "FLAT_NORMAL",
                "gross_pnl": 10.0,
                "notional": 1_000.0,
                "spread_bps": 4.0,
            }
        ],
        MRStressConfig(
            fee_multiplier=2.0,
            slippage_spread_fraction=1.0,
            taker_round_trip_fee_bps=5.0,
        ),
    )

    report = reports[0]
    assert report.gross_pnl == 10.0
    assert report.net_pnl == 8.6
    assert report.expectancy == 8.6
    assert report.flat_regime == "FLAT_NORMAL"
    assert report.capital_ready is True


def test_mr_promotion_gate_fails_when_stress_net_expectancy_is_negative() -> None:
    reports = build_mr_stress_report(
        [
            {
                "symbol": "ETHUSDT",
                "regime": "FLAT_HIGH",
                "gross_pnl": 1.0,
                "notional": 1_000.0,
                "spread_bps": 10.0,
            }
        ],
        MRStressConfig(
            fee_multiplier=2.0,
            slippage_spread_fraction=1.0,
            taker_round_trip_fee_bps=10.0,
        ),
    )

    assert reports[0].capital_ready is False
    assert promotion_gate_passes(reports) is False
