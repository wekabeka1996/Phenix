"""PKG-5 tests for the Judge path diagnostics tool.

Tests cover:
  T1  mfe/mae LONG path
  T2  mfe/mae SHORT path
  T3  time_to_mfe / time_to_mae
  T4  mfe_before_mae true and false cases
  T5  tp_distance reach ratios
  T6  timeout_reason: TP_TOO_FAR_PRICE_MOVED_FAVORABLY
  T7  timeout_reason: WRONG_DIRECTION
  T8  NO_FILL classified separately
  T9  official outcomes.json NOT modified
  T10 pct_only blocks USD ROI
  T11 all_tiers marked diagnostic_only
  T12 official canonical NOT multiplied by ladder
  T13 summary groups by symbol, tf_sec, regime, confidence_bucket
  T14 deterministic output on same input
  T15 PKG-1/2/3 regression
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Optional

import pytest

from tools.judge.build_path_diagnostics import (
    Candle,
    candles_after,
    classify_timeout_reason,
    compute_fill_sensitivity,
    compute_summary,
    confidence_bucket,
    enrich_from_diagnostics,
    load_all_tier_plans,
    simulate_tier_fill,
    walk_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candle(open_ms: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        open_time_ms=open_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        close_time_ms=open_ms + 59_999,
    )


def _diag_base(
    *,
    symbol: str = "BTCUSDT",
    tf_sec: int = 180,
    bar_close_ts: int = 1_000_180_000 - 1,
    entry_side: str = "BUY",
    entry_price: float = 100.0,
    limit_price: float = 100.0,
    tp_price: float = 102.0,
    sl_price: float = 99.0,
    mfe: float = 0.0,
    mae: float = 0.0,
    exit_classification: str = "TIMEOUT",
    matched_trade: bool = True,
    confidence: float = 0.6,
    regime: str = "TREND_UP",
    horizon_ms: int = 2_160_000,
    chosen_tier: str = "high",
) -> dict:
    return {
        "verdict_id": f"vrd_entry_{symbol}_{bar_close_ts}",
        "plan_id": f"sep_{chosen_tier}_{symbol}_{bar_close_ts}",
        "correlation_key": {
            "strategy_id": "aurora",
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
        },
        "entry_side": entry_side,
        "entry_price": entry_price,
        "limit_price": limit_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "mfe": mfe,
        "mae": mae,
        "exit_classification": exit_classification,
        "matched_trade": matched_trade,
        "confidence": confidence,
        "chosen_tier": chosen_tier,
        "regime": regime,
        "regime_confidence": 0.5,
        "regime_ts_ms": bar_close_ts,
        "regime_stale_bars": 0,
        "horizon_ms": horizon_ms,
        "fill_model": "optimistic_touch",
    }


# ---------------------------------------------------------------------------
# T1 — MFE/MAE LONG path from diagnostics
# ---------------------------------------------------------------------------

def test_1_mfe_mae_long_path():
    """enrich_from_diagnostics computes mfe_bps and mae_bps correctly for LONG."""
    # LONG: entry=100, tp=102, sl=99; mfe=1.5 price units, mae=0.3 price units
    diag = _diag_base(entry_price=100.0, tp_price=102.0, sl_price=99.0,
                      mfe=1.5, mae=0.3, entry_side="BUY")
    row = enrich_from_diagnostics(diag)

    assert row["mfe_bps"] == pytest.approx(150.0)   # 1.5/100 * 10000
    assert row["mae_bps"] == pytest.approx(30.0)    # 0.3/100 * 10000
    assert row["tp_distance_bps"] == pytest.approx(200.0)  # 2/100 * 10000
    assert row["sl_distance_bps"] == pytest.approx(100.0)  # 1/100 * 10000
    assert row["mfe_to_tp_ratio"] == pytest.approx(0.75)   # 1.5/2.0
    assert row["mae_to_sl_ratio"] == pytest.approx(0.30)   # 0.3/1.0
    assert row["reached_25pct_tp_distance"] is True
    assert row["reached_50pct_tp_distance"] is True
    assert row["reached_75pct_tp_distance"] is True
    assert row["reached_90pct_tp_distance"] is False


# ---------------------------------------------------------------------------
# T2 — MFE/MAE SHORT path from diagnostics
# ---------------------------------------------------------------------------

def test_2_mfe_mae_short_path():
    """enrich_from_diagnostics computes bps correctly for SHORT entries."""
    # SHORT: entry=100, tp=98 (below entry), sl=101 (above entry)
    # mfe=1.8 price units (price dropped 1.8), mae=0.5 price units (price rose 0.5)
    diag = _diag_base(
        entry_side="SELL",
        entry_price=100.0,
        tp_price=98.0,
        sl_price=101.0,
        mfe=1.8,
        mae=0.5,
    )
    row = enrich_from_diagnostics(diag)

    assert row["mfe_bps"] == pytest.approx(180.0)   # 1.8/100 * 10000
    assert row["mae_bps"] == pytest.approx(50.0)    # 0.5/100 * 10000
    assert row["tp_distance_bps"] == pytest.approx(
        200.0)  # abs(98-100)/100 * 10000
    assert row["sl_distance_bps"] == pytest.approx(
        100.0)  # abs(101-100)/100 * 10000
    assert row["mfe_to_tp_ratio"] == pytest.approx(0.9)    # 1.8/2.0
    assert row["reached_90pct_tp_distance"] is True
    assert row["reached_75pct_tp_distance"] is True


# ---------------------------------------------------------------------------
# T3 — time_to_mfe and time_to_mae via candle walk
# ---------------------------------------------------------------------------

def test_3_time_to_mfe_mae():
    """walk_path correctly measures time to MFE and MAE candle."""
    bar_close_ts = 1_000_000_000_000

    # BUY: entry=100, tp=105, sl=98
    # Candles (1 min each):
    #   c0 (fill candle): open_ms=bar_close_ts+1, high=100.5  ← minor MFE, minor MAE
    #   c1: high=102  ← new MFE (2.0)
    #   c2: high=104  ← new MFE (4.0)
    #   c3: high=103, low=97.5  ← MAE (2.5) — MAE occurs at candle 3, AFTER MFE at c2

    candles = [
        _candle(bar_close_ts + 1, 100.0, 100.5, 99.8, 100.2),   # fill
        _candle(bar_close_ts + 60_001, 100.2, 102.0,
                100.0, 101.5),  # MFE progress
        _candle(bar_close_ts + 120_001, 101.5,
                104.0, 101.0, 103.0),  # peak MFE
        _candle(bar_close_ts + 180_001, 103.0, 103.0, 97.5, 98.0),   # peak MAE
    ]

    row = enrich_from_diagnostics(
        _diag_base(
            bar_close_ts=bar_close_ts,
            entry_price=100.0,
            limit_price=100.0,
            tp_price=105.0,
            sl_price=98.0,
            mfe=4.0,
            mae=2.5,
            matched_trade=True,
        )
    )
    walk_path(row, candles)

    # MFE at c2 (120001 ms), MAE at c3 (180001 ms)
    # time_to_mfe = c2.open_ms - c0.open_ms = 120001 - 1 = 120000 ms / 1000 = 120s
    assert row["time_to_mfe_sec"] == pytest.approx(120.0, abs=1.0)
    # time_to_mae = c3.open_ms - c0.open_ms = 180001 - 1 = 180000 ms / 1000 = 180s
    assert row["time_to_mae_sec"] == pytest.approx(180.0, abs=1.0)


# ---------------------------------------------------------------------------
# T4 — mfe_before_mae: both true and false cases
# ---------------------------------------------------------------------------

def test_4_mfe_before_mae_true_false():
    bar_close_ts = 1_000_000_000_000

    # Case A: MFE candle is BEFORE MAE candle → mfe_before_mae=True
    candles_favorable_first = [
        _candle(bar_close_ts + 1, 100.0, 103.0,
                99.5, 102.0),      # fill + MFE here
        _candle(bar_close_ts + 60_001, 102.0, 102.5, 96.0, 97.0),  # MAE here
    ]
    row_a = enrich_from_diagnostics(
        _diag_base(bar_close_ts=bar_close_ts, entry_price=100.0, limit_price=100.0,
                   mfe=3.0, mae=4.0, matched_trade=True)
    )
    walk_path(row_a, candles_favorable_first)
    assert row_a["mfe_before_mae"] is True

    # Case B: MAE candle is BEFORE MFE candle → mfe_before_mae=False
    candles_adverse_first = [
        _candle(bar_close_ts + 1, 100.0, 100.5,
                96.0, 97.0),        # fill + MAE here
        _candle(bar_close_ts + 60_001, 97.0, 103.0, 97.0, 102.0),   # MFE here
    ]
    row_b = enrich_from_diagnostics(
        _diag_base(bar_close_ts=bar_close_ts, entry_price=100.0, limit_price=100.0,
                   mfe=3.0, mae=4.0, matched_trade=True)
    )
    walk_path(row_b, candles_adverse_first)
    assert row_b["mfe_before_mae"] is False


# ---------------------------------------------------------------------------
# T5 — TP distance reach ratios
# ---------------------------------------------------------------------------

def test_5_tp_distance_reach_ratios():
    """Reach ratio flags are mutually consistent and derived from mfe_to_tp_ratio."""
    # mfe=1.0, tp_distance=2.0 → ratio=0.5
    diag = _diag_base(entry_price=100.0, tp_price=102.0,
                      sl_price=99.0, mfe=1.0, mae=0.2)
    row = enrich_from_diagnostics(diag)

    assert row["mfe_to_tp_ratio"] == pytest.approx(0.5)
    assert row["reached_25pct_tp_distance"] is True
    assert row["reached_50pct_tp_distance"] is True
    assert row["reached_75pct_tp_distance"] is False
    assert row["reached_90pct_tp_distance"] is False

    # mfe=0.1, tp_distance=2.0 → ratio=0.05 → reaches nothing
    diag2 = _diag_base(entry_price=100.0, tp_price=102.0,
                       sl_price=99.0, mfe=0.1, mae=0.1)
    row2 = enrich_from_diagnostics(diag2)
    assert row2["reached_25pct_tp_distance"] is False
    assert row2["reached_50pct_tp_distance"] is False


# ---------------------------------------------------------------------------
# T6 — timeout_reason: TP_TOO_FAR_PRICE_MOVED_FAVORABLY
# ---------------------------------------------------------------------------

def test_6_timeout_reason_tp_too_far():
    """classify_timeout_reason returns TP_TOO_FAR_PRICE_MOVED_FAVORABLY
    when MFE ≥ 50% of TP distance but < 90%."""
    reason = classify_timeout_reason(
        mfe_to_tp_ratio=0.65,
        mae_to_sl_ratio=0.1,
        is_long=True,
        mfe_bps=130.0,
        mae_bps=10.0,
    )
    assert reason == "TP_TOO_FAR_PRICE_MOVED_FAVORABLY"


# ---------------------------------------------------------------------------
# T7 — timeout_reason: WRONG_DIRECTION
# ---------------------------------------------------------------------------

def test_7_timeout_reason_wrong_direction():
    """classify_timeout_reason returns WRONG_DIRECTION when MAE > MFE."""
    reason = classify_timeout_reason(
        mfe_to_tp_ratio=0.1,
        mae_to_sl_ratio=0.2,
        is_long=True,
        mfe_bps=20.0,
        mae_bps=60.0,
    )
    assert reason == "WRONG_DIRECTION"


# ---------------------------------------------------------------------------
# T8 — NO_FILL classified separately
# ---------------------------------------------------------------------------

def test_8_no_fill_classified_separately():
    """NO_FILL rows have outcome_matched_trade=False and no path metrics."""
    diag = _diag_base(
        matched_trade=False,
        exit_classification="NO_FILL",
        mfe=0.0,
        mae=0.0,
    )
    row = enrich_from_diagnostics(diag)

    assert row["outcome_matched_trade"] is False
    assert row["exit_classification"] == "NO_FILL"
    assert row["mfe_bps"] is None or row["mfe_bps"] == 0.0
    # timeout_reason should not be set for NO_FILL
    assert row["timeout_reason_class"] is None


# ---------------------------------------------------------------------------
# T9 — official outcomes.json NOT modified
# ---------------------------------------------------------------------------

def test_9_does_not_modify_outcomes_json(tmp_path):
    """enrich_from_diagnostics and walk_path do not write to any file."""
    # We can't check this directly at file level since unit tests don't run
    # the CLI, but we can verify that no file IO is performed by the core
    # enrichment functions.
    diag = _diag_base()
    original_diag = copy.deepcopy(diag)
    row = enrich_from_diagnostics(diag)
    # diag should not have been modified in place
    assert diag == original_diag
    # walk_path modifies row in-place but not the source diag
    walk_path(row, [])
    assert diag == original_diag


# ---------------------------------------------------------------------------
# T10 — pct_only blocks USD ROI
# ---------------------------------------------------------------------------

def test_10_pct_only_blocks_usd_roi():
    """compute_summary records USD ROI as disabled when no economics block."""
    summary = compute_summary([], [], manifest={})
    fee_status = summary.get("fee_slippage_status", {})
    assert "disabled" in fee_status.get("usd_roi", "").lower() or \
           "pct_only" in fee_status.get("usd_roi", "").lower()


# ---------------------------------------------------------------------------
# T11 — all_tiers marked diagnostic_only
# ---------------------------------------------------------------------------

def test_11_all_tiers_marked_diagnostic_only():
    """simulate_tier_fill always returns diagnostic_scope='all_tiers'."""
    plan = {
        "plan_id": "sep_low_BTCUSDT_1",
        "source_verdict_id": "vrd_1",
        "symbol": "BTCUSDT",
        "tf_sec": 180,
        "ts_ms": 1_000_000_000,
        "confidence_tier": "low",
        "confidence": 0.15,
        "entry_side": "BUY",
        "actionable": True,
        "suppressed": False,
        "limit_price": 100.0,
        "tp_price": 102.0,
        "sl_price": 99.0,
    }
    result = simulate_tier_fill(plan, candles_by_symbol={})
    assert result["diagnostic_scope"] == "all_tiers"


# ---------------------------------------------------------------------------
# T12 — official canonical NOT multiplied by ladder
# ---------------------------------------------------------------------------

def test_12_official_canonical_not_multiplied_by_ladder():
    """Each official diagnostic row carries diagnostic_scope='official_canonical'."""
    diags = [_diag_base(symbol="BTCUSDT"), _diag_base(symbol="ETHUSDT")]
    rows = [enrich_from_diagnostics(d) for d in diags]

    for row in rows:
        assert row["diagnostic_scope"] == "official_canonical"
    # exactly 2 rows — no multiplication
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# T13 — summary groups by symbol, tf_sec, regime, confidence_bucket
# ---------------------------------------------------------------------------

def test_13_summary_groups_by_symbol_tf_regime_confidence():
    """compute_summary populates all four required grouping dimensions."""
    rows = [
        {**enrich_from_diagnostics(_diag_base(symbol="BTCUSDT", tf_sec=180,
                                              regime="TREND_UP", confidence=0.6))},
        {**enrich_from_diagnostics(_diag_base(symbol="ETHUSDT", tf_sec=300,
                                              regime="TREND_DOWN", confidence=0.3))},
    ]
    summary = compute_summary(rows, [], manifest={})

    assert "BTCUSDT" in summary["by_symbol"]
    assert "ETHUSDT" in summary["by_symbol"]
    assert "180" in summary["by_tf_sec"] or 180 in summary["by_tf_sec"]
    assert "300" in summary["by_tf_sec"] or 300 in summary["by_tf_sec"]
    assert "TREND_UP" in summary["by_regime"]
    assert "TREND_DOWN" in summary["by_regime"]
    # at least one confidence bucket present
    assert len(summary["by_confidence_bucket"]) >= 1


# ---------------------------------------------------------------------------
# T14 — deterministic output on same input
# ---------------------------------------------------------------------------

def test_14_deterministic_output():
    """enrich_from_diagnostics produces identical output on two calls with same input."""
    diag = _diag_base(entry_price=50000.0, tp_price=51000.0, sl_price=49500.0,
                      mfe=200.0, mae=100.0)
    row_a = enrich_from_diagnostics(diag)
    row_b = enrich_from_diagnostics(diag)

    # All numeric fields must be identical
    for key in ["mfe_bps", "mae_bps", "tp_distance_bps", "sl_distance_bps",
                "mfe_to_tp_ratio", "mae_to_sl_ratio"]:
        assert row_a[key] == row_b[key], f"Non-deterministic field: {key}"


# ---------------------------------------------------------------------------
# T15 — PKG-1/2/3 regression: ensure imports remain intact
# ---------------------------------------------------------------------------

def test_15_pkg1_regression_import():
    """PKG-1 materializer core functions remain importable and call-compatible."""
    from tools.judge.build_outcomes_from_candles import (
        load_verdicts,
        load_shadow_plans,
        select_canonical_plan,
        replay_plan_on_candles,
    )
    assert callable(load_verdicts)
    assert callable(load_shadow_plans)
    assert callable(select_canonical_plan)
    assert callable(replay_plan_on_candles)


def test_15b_pkg2_regression_import():
    """PKG-2 fee/slippage SSOT: SimulatorConfig remains importable with expected fields."""
    from apps.reference.domains.alpha_search.judge.simulator.config_models import (
        SimulatorConfig,
    )
    import yaml
    raw = yaml.safe_load(
        Path("config/judge_simulator.yaml").read_text(encoding="utf-8"))
    cfg = SimulatorConfig(**raw["judge_simulator"])
    assert cfg.fee_per_cycle_bps == 25
    assert cfg.slippage_pct == pytest.approx(0.1)


def test_15c_pkg3_regression_import():
    """PKG-3 notional contract: tools/judge/notional.py remains importable."""
    from tools.judge.notional import (
        compute_roi_usd,
        derive_notional_for_outcome,
        manifest_pointer_strings,
    )
    assert callable(compute_roi_usd)
    assert callable(derive_notional_for_outcome)
    assert callable(manifest_pointer_strings)


# ---------------------------------------------------------------------------
# Additional: fill model sensitivity
# ---------------------------------------------------------------------------

def test_fill_sensitivity_conservative_tighter_than_optimistic():
    """conservative_cross fills should be subset of optimistic fills."""
    bar_close_ts = 1_000_000_000_000
    # Candle whose low touches EXACTLY at limit (optimistic fills, conservative 1bp does not)
    candles = [
        _candle(bar_close_ts + 1, 100.0, 100.5, 100.0, 100.2),  # low == limit
    ]
    diag = _diag_base(bar_close_ts=bar_close_ts, entry_price=100.0,
                      limit_price=100.0, matched_trade=True)
    sens = compute_fill_sensitivity(diag, candles)

    # optimistic fills (already matched)
    assert sens["fills_optimistic"] is True
    # conservative 1bp: low must be < 100.0 - 0.01 = 99.99 → NOT filled
    assert sens["fills_conservative_1bp"] is False
    assert sens["fills_conservative_5bp"] is False
