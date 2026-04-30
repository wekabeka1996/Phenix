from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.forensics.r3_min_regime_confidence_ablation import build_counterfactual_band_report


def test_band_report_counts_band_positions_and_counterfactual_rejections():
    decisions = [
        {
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "regime_used": "TREND_UP",
            "regime_confidence_used": 0.19,
            "threshold_verdict": "BLOCK",
            "deny_reason": "NRR-026",
            "regime_confidence_breach_kind": "below_min",
        },
        {
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "regime_used": "TREND_UP",
            "regime_confidence_used": 0.25,
            "threshold_verdict": "BLOCK",
            "deny_reason": "NRR-026",
            "regime_confidence_breach_kind": "below_min",
        },
        {
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "regime_used": "TREND_DOWN",
            "regime_confidence_used": 0.33,
            "threshold_verdict": "BLOCK",
            "deny_reason": "NRR-063",
            "regime_confidence_breach_kind": "above_max",
        },
        {
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "regime_used": "TREND_DOWN",
            "regime_confidence_used": 0.40,
            "threshold_verdict": "ALLOW",
            "deny_reason": "",
            "regime_confidence_breach_kind": "none",
        },
        {
            "symbol": "BNBUSDT",
            "strategy_id": "aurora",
            "regime_used": "MEAN_REVERSION",
            "regime_confidence_used": 0.31,
            "threshold_verdict": "ALLOW",
            "deny_reason": "",
            "regime_confidence_breach_kind": "none",
        },
    ]

    report = build_counterfactual_band_report(decisions, lower=0.20, upper=0.32)
    totals = report["totals"]

    assert totals["total_inspected"] == 5
    assert totals["below_min"] == 1
    assert totals["inside_band"] == 2
    assert totals["above_max"] == 2
    assert totals["current_nrr_026_within_band"] == 1
    assert totals["currently_allowed_but_would_above_max"] == 1
    assert totals["currently_other_rejected_but_would_first_block_above_max"] == 1
    assert report["by_regime"]["TREND_UP"]["inside_band"] == 1
    assert report["by_regime"]["TREND_DOWN"]["above_max"] == 2
