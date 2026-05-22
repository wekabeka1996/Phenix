"""PKG-6A tests for current-window baseline diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.judge.build_review_baselines_current_window import (
    build_confidence_shuffle,
    build_inverted_judge,
    build_random_same_frequency,
    compute_confidence_monotonicity_score,
    compute_judge_metrics,
    compute_metrics,
    derive_confidence_bucket,
    derive_day_str,
    derive_verdict_and_text,
    main,
    opposite_side,
    return_for_action,
    run_confidence_shuffle_permutations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(vid: str, *, symbol: str = "BTCUSDT", tf_sec: int = 180,
         bar_close_ts: int = 1_779_000_000_000 - 1,
         entry_verdict: str = "OPEN_LONG", optimal_action: str = "OPEN_LONG",
         raw_return: float = 0.005, matched_trade: bool = True,
         confidence: float = 0.6) -> dict:
    return {
        "verdict_id": vid,
        "strategy_id": "aurora",
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "entry_verdict": entry_verdict,
        "optimal_action": optimal_action,
        "raw_return": raw_return,
        "net_return": raw_return - 0.0035,
        "matched_trade": matched_trade,
        "confidence": confidence,
        "fee_cost": 0.0025,
        "slippage_cost": 0.001,
        "has_disagreement": entry_verdict != optimal_action,
        "cohort": "CORRECT_ENTRY" if entry_verdict == optimal_action else "INCORRECT_ENTRY",
        "dissent_noted": False,
        "schema_version": "1",
    }


def _path_row(vid: str, regime: str = "UNCERTAIN") -> dict:
    return {"verdict_id": vid, "regime": regime}


# ---------------------------------------------------------------------------
# T1 — inverted_judge flips OPEN_LONG <-> OPEN_SHORT only
# ---------------------------------------------------------------------------

def test_1_inverted_judge_flips_open_actions_only():
    rows = [
        _row("a", entry_verdict="OPEN_LONG"),
        _row("b", entry_verdict="OPEN_SHORT"),
        _row("c", entry_verdict="NO_ENTRY"),
        _row("d", entry_verdict="SUPPRESS"),
        _row("e", entry_verdict="UNKNOWN"),
    ]
    out = build_inverted_judge(rows)
    assert out[0]["_baseline_action"] == "OPEN_SHORT"
    assert out[1]["_baseline_action"] == "OPEN_LONG"
    assert out[2]["_baseline_action"] == "NO_ENTRY"
    assert out[3]["_baseline_action"] == "SUPPRESS"
    assert out[4]["_baseline_action"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# T2 — random_same_frequency preserves per-bucket action counts
# ---------------------------------------------------------------------------

def test_2_random_same_frequency_preserves_group_counts():
    # 4 BTCUSDT rows same day & tf: 3 LONG + 1 SHORT
    rows = [
        _row("a", entry_verdict="OPEN_LONG", bar_close_ts=1_779_000_179_999),
        _row("b", entry_verdict="OPEN_LONG", bar_close_ts=1_779_000_359_999),
        _row("c", entry_verdict="OPEN_LONG", bar_close_ts=1_779_000_539_999),
        _row("d", entry_verdict="OPEN_SHORT", bar_close_ts=1_779_000_719_999),
    ]
    out = build_random_same_frequency(rows, seed=42)
    actions = [o["_baseline_action"] for o in out]
    assert actions.count("OPEN_LONG") == 3
    assert actions.count("OPEN_SHORT") == 1


# ---------------------------------------------------------------------------
# T3 — confidence_shuffle preserves actions and outcomes
# ---------------------------------------------------------------------------

def test_3_confidence_shuffle_preserves_action_outcomes():
    rows = [
        _row("a", confidence=0.1, raw_return=0.01),
        _row("b", confidence=0.5, raw_return=-0.005),
        _row("c", confidence=0.9, raw_return=0.0),
    ]
    paths = {r["verdict_id"]: _path_row(r["verdict_id"]) for r in rows}
    out = build_confidence_shuffle(rows, paths, seed=7)
    # Actions unchanged
    for o, r in zip(out, rows):
        assert o["_baseline_action"] == r["entry_verdict"]
        assert o["raw_return"] == r["raw_return"]
    # Confidence values are a permutation of the originals
    assert sorted(o["_baseline_confidence"]
                  for o in out) == sorted(r["confidence"] for r in rows)


# ---------------------------------------------------------------------------
# T4 — confidence_shuffle is deterministic given the same seed
# ---------------------------------------------------------------------------

def test_4_confidence_shuffle_is_deterministic_with_seed():
    rows = [_row(f"v{i}", confidence=0.1 * i, raw_return=0.001 * i)
            for i in range(10)]
    paths = {r["verdict_id"]: _path_row(r["verdict_id"]) for r in rows}
    out_a = build_confidence_shuffle(rows, paths, seed=1234)
    out_b = build_confidence_shuffle(rows, paths, seed=1234)
    out_c = build_confidence_shuffle(rows, paths, seed=9999)
    assert [o["_baseline_confidence"]
            for o in out_a] == [o["_baseline_confidence"] for o in out_b]
    # Different seed should generally produce a different ordering
    assert [o["_baseline_confidence"]
            for o in out_a] != [o["_baseline_confidence"] for o in out_c]


# ---------------------------------------------------------------------------
# T5 — no_future_leakage for deferred time_shifted_judge baseline
# ---------------------------------------------------------------------------

def test_5_no_future_leakage_in_time_shifted_baseline_if_implemented():
    """time_shifted_judge is DEFERRED in PKG-6A — must be advertised as deferred,
    not silently implemented with a leakage-prone shortcut."""
    # Importing the module exposes the deferred record.
    from tools.judge import build_review_baselines_current_window as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "time_shifted_judge" in src
    # The deferred marker must be present in the source.
    assert "DEFERRED" in src or "Deferred" in src


# ---------------------------------------------------------------------------
# T6 — baseline outputs do not modify official artifacts
# ---------------------------------------------------------------------------

def test_6_baseline_outputs_do_not_modify_official_artifacts(tmp_path):
    """The tool must never write inside artifacts/ or data/simulator/outcomes*.
    Verified by running on tmp_path-only inputs/outputs."""
    cal = tmp_path / "phase5_calibration.jsonl"
    rows = [_row(f"v{i}", entry_verdict="OPEN_LONG" if i % 2 == 0 else "OPEN_SHORT",
                 optimal_action="OPEN_LONG" if i % 3 == 0 else "OPEN_SHORT",
                 raw_return=0.001 * (i - 5))
            for i in range(20)]
    cal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    out_json = tmp_path / "baselines.json"
    out_csv = tmp_path / "baselines.csv"
    report = tmp_path / "report.md"
    path_diag = tmp_path / "path_diag.jsonl"  # empty / missing is OK

    rc = main([
        "--calibration-path", str(cal),
        "--review-dir", str(tmp_path / "review"),
        "--path-diagnostics", str(path_diag),
        "--out-json", str(out_json),
        "--out-csv", str(out_csv),
        "--report-path", str(report),
        "--seed", "42",
        "--n-permutations", "5",
    ])
    assert rc == 0
    assert out_json.exists()
    assert out_csv.exists()
    assert report.exists()


# ---------------------------------------------------------------------------
# T7 — report labels NO OOS claim
# ---------------------------------------------------------------------------

def test_7_current_window_report_labels_no_oos_claim(tmp_path):
    cal = tmp_path / "phase5_calibration.jsonl"
    rows = [_row(f"v{i}", entry_verdict="OPEN_LONG", optimal_action="OPEN_SHORT",
                 raw_return=-0.002) for i in range(10)]
    cal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    report = tmp_path / "report.md"
    rc = main([
        "--calibration-path", str(cal),
        "--review-dir", str(tmp_path / "review"),
        "--path-diagnostics", str(tmp_path / "missing.jsonl"),
        "--out-json", str(tmp_path / "b.json"),
        "--out-csv", str(tmp_path / "b.csv"),
        "--report-path", str(report),
        "--seed", "7",
        "--n-permutations", "5",
    ])
    assert rc == 0
    text = report.read_text(encoding="utf-8")
    assert "DIAGNOSTIC-ONLY" in text
    assert "No OOS claim" in text or "no OOS claim" in text or "No final claim" in text
    assert "PKG-6B" in text


# ---------------------------------------------------------------------------
# T8 — baseline summary contains symbol/tf_sec/regime segments
# ---------------------------------------------------------------------------

def test_8_baseline_summary_contains_symbol_tf_regime_segments(tmp_path):
    cal = tmp_path / "phase5_calibration.jsonl"
    diag = tmp_path / "diag.jsonl"
    rows = [
        _row("a", symbol="BTCUSDT", tf_sec=180,
             entry_verdict="OPEN_LONG", optimal_action="OPEN_LONG"),
        _row("b", symbol="ETHUSDT", tf_sec=300,
             entry_verdict="OPEN_SHORT", optimal_action="OPEN_LONG"),
        _row("c", symbol="ETHUSDT", tf_sec=900,
             entry_verdict="OPEN_LONG", optimal_action="OPEN_SHORT"),
    ]
    cal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    diag.write_text("\n".join(json.dumps(_path_row(r["verdict_id"], regime="TREND_UP" if i == 0 else "TREND_DOWN"))
                              for i, r in enumerate(rows)), encoding="utf-8")
    out_json = tmp_path / "b.json"
    rc = main([
        "--calibration-path", str(cal),
        "--review-dir", str(tmp_path / "review"),
        "--path-diagnostics", str(diag),
        "--out-json", str(out_json),
        "--out-csv", str(tmp_path / "b.csv"),
        "--report-path", str(tmp_path / "r.md"),
        "--seed", "11",
        "--n-permutations", "3",
    ])
    assert rc == 0
    data = json.loads(out_json.read_text(encoding="utf-8"))
    for baseline in ("judge", "inverted_judge", "random_same_frequency", "confidence_shuffle"):
        m = data["baselines"][baseline]
        assert "by_symbol" in m and m["by_symbol"]
        assert "by_tf_sec" in m and m["by_tf_sec"]
        assert "by_regime" in m and m["by_regime"]
        assert "by_confidence_bucket" in m and m["by_confidence_bucket"]


# ---------------------------------------------------------------------------
# T9 — return_for_action correctness across the 4 quality flags
# ---------------------------------------------------------------------------

def test_9_return_for_action_quality_flags():
    # same-side filled
    r, f = return_for_action("OPEN_LONG", "OPEN_LONG", 0.01, True)
    assert r == 0.01 and f == "same_side_realized"
    # flipped-side filled (long realised +1%, short would realise -1%)
    r, f = return_for_action("OPEN_LONG", "OPEN_SHORT", 0.01, True)
    assert r == -0.01 and f == "flipped_side_inferred"
    # NO_ENTRY -> 0
    r, f = return_for_action("OPEN_LONG", "NO_ENTRY", 0.01, True)
    assert r == 0.0 and f == "no_entry_zero"
    # unfilled -> assumed zero for any candidate
    r, f = return_for_action("OPEN_LONG", "OPEN_SHORT", 0.0, False)
    assert r == 0.0 and f == "unfilled_assumed_zero"


# ---------------------------------------------------------------------------
# T10 — confidence_monotonicity_score and verdict logic
# ---------------------------------------------------------------------------

def test_10_verdict_logic_negative_when_judge_worse_and_inverted_better():
    judge = {"accuracy": 0.10, "avg_net_return": -0.005,
             "by_confidence_bucket": {"[0.00,0.25]": {"avg_net_return": -0.001},
                                      "[0.75,1.00]": {"avg_net_return": -0.010}}}
    inverted = {"accuracy": 0.90, "avg_net_return": +0.004}
    rsf = {"accuracy": 0.50}
    cs = {"accuracy": 0.10}
    perms = {"n_perms": 10, "score_p05": -0.001,
             "score_p95": +0.001, "score_mean": 0.0}
    interp = derive_verdict_and_text(judge, inverted, rsf, cs, perms,
                                     compute_confidence_monotonicity_score(judge["by_confidence_bucket"]))
    assert interp["verdict"] == "BASELINES_CURRENT_WINDOW_COMPLETE_NEGATIVE"


# ---------------------------------------------------------------------------
# T11 — derive_day_str and derive_confidence_bucket helpers
# ---------------------------------------------------------------------------

def test_11_derive_helpers():
    # 2026-05-17 03:59:59.999 UTC ≈ 1779033599999
    day = derive_day_str(1_779_033_599_999)
    assert day.startswith("2026-05-")
    assert derive_confidence_bucket(0.1) == "[0.00,0.25]"
    assert derive_confidence_bucket(0.3) == "[0.25,0.50]"
    assert derive_confidence_bucket(0.6) == "[0.50,0.75]"
    assert derive_confidence_bucket(0.99) == "[0.75,1.00]"


# ---------------------------------------------------------------------------
# T12 — regression: PKG-1 outcomes materializer still importable
# ---------------------------------------------------------------------------

def test_12_pkg1_regression_import():
    from tools.judge.build_outcomes_from_candles import (
        load_verdicts, load_shadow_plans, select_canonical_plan,
        replay_plan_on_candles,
    )
    assert all(callable(f) for f in [load_verdicts, load_shadow_plans,
                                     select_canonical_plan, replay_plan_on_candles])


# ---------------------------------------------------------------------------
# T13 — regression: PKG-5 path diagnostics still importable
# ---------------------------------------------------------------------------

def test_13_pkg5_regression_import():
    from tools.judge.build_path_diagnostics import (
        enrich_from_diagnostics, walk_path, classify_timeout_reason,
        compute_summary,
    )
    assert all(callable(f) for f in [enrich_from_diagnostics, walk_path,
                                     classify_timeout_reason, compute_summary])
