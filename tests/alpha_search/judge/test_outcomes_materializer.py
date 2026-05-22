"""PKG-1 tests for the Judge outcomes materializer.

Pins the materializer contract:

  * strict outcomes.json (only 8 allowed fields)
  * one canonical outcome per CorrelationKey
  * duplicate CorrelationKey hard-fails (before write)
  * no future leakage (first eligible candle open > bar_close_ts)
  * future-tail skipped with explicit reason (not silently dropped)
  * does NOT filter on `applied=true`
  * fee/slippage pointers recorded, NOT applied
  * pct_only mode emits no USD ROI; economics-enabled writes USD only to sidecar
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import tools.judge.build_outcomes_from_candles as bom
from tools.judge.build_outcomes_from_candles import (
    Candle,
    CanonicalPlan,
    MaterializerConfig,
    Outcome,
    build_manifest,
    build_outcomes_json,
    candles_in_window,
    load_simulator_config,
    materialize,
    replay_plan_on_candles,
    select_canonical_plan,
    validate_outcomes_json,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    EconomicsConfig,
    SimulatorConfig,
)
from tools.judge.notional import load_instrument_precision_map

ROOT = Path(__file__).resolve().parents[3]
INSTRUMENTS_PATH = ROOT / "config" / "aurora" / "instruments.yaml"
SCHEMA_PATH = (
    ROOT / "apps" / "reference" / "domains" / "alpha_search" / "judge"
    / "simulator" / "schemas" / "outcome_input_v1.json"
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_sim_cfg(economics: EconomicsConfig | None = None) -> SimulatorConfig:
    return SimulatorConfig(
        judge_logs_path="logs/judge_experts",
        outcome_data_path="data/simulator/outcomes.json",
        calibration_dataset_path="artifacts/phase5_calibration.jsonl",
        summary_report_path="artifacts/phase5_summary_report.json",
        fee_per_cycle_bps=25.0,
        slippage_pct=0.1,
        economics=economics,
    )


def _bar_close(open_ms: int, tf_sec: int = 60) -> int:
    tf_ms = tf_sec * 1000
    aligned_open = open_ms - (open_ms % tf_ms)
    return aligned_open + tf_ms - 1


def _make_verdict(
    vid: str, symbol: str, tf_sec: int, bar_close_ts: int, *,
    entry_verdict: str = "OPEN_LONG", applied: bool = False,
    envelope_id: str | None = None,
):
    return {
        "verdict_id": vid,
        "envelope_id": envelope_id or f"env_{vid}",
        "symbol": symbol,
        "tf_sec": tf_sec,
        "ts_ms": bar_close_ts,
        "entry_verdict": entry_verdict,
        "applied": applied,
        "strategy_id": "aurora",
        "schema_version": "1",
    }


def _make_plan(
    pid: str, vid: str, symbol: str, tf_sec: int, ts_ms: int, side: str,
    *, limit_price: float = 100.0, tp_price: float = 110.0, sl_price: float = 95.0,
    actionable: bool = True, suppressed: bool = False, tier: str = "high",
    confidence: float = 0.9,
):
    return {
        "plan_id": pid,
        "source_verdict_id": vid,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "ts_ms": ts_ms,
        "entry_side": side,
        "limit_price": limit_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "actionable": actionable,
        "suppressed": suppressed,
        "confidence_tier": tier,
        "confidence": confidence,
        "schema_version": "1",
    }


def _candle(open_ms: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        open_time_ms=open_ms, open=o, high=h, low=l, close=c,
        close_time_ms=open_ms + 60_000 - 1,
    )


def _build_simple_run(
    tmp_path: Path, *, ent: str = "OPEN_LONG", side: str = "BUY",
    limit: float = 100.0, tp: float = 110.0, sl: float = 95.0,
    candles: list[Candle] | None = None,
    applied: bool = False,
):
    """Smallest viable end-to-end run with one verdict, one plan, deterministic candles."""
    bar_close = _bar_close(1_000_000_000_000, 60)  # 1m bar at arbitrary epoch
    vid = "vrd_1"
    v = _make_verdict(vid, "BTCUSDT", 60, bar_close,
                      entry_verdict=ent, applied=applied)
    p = _make_plan("sep_high_1", vid, "BTCUSDT", 60, bar_close, side,
                   limit_price=limit, tp_price=tp, sl_price=sl)
    cs = candles or [
        # First eligible candle (open > bar_close)
        _candle(bar_close + 1, 100, 111, 99, 110),
    ]
    sim_cfg = _make_sim_cfg()
    mat_cfg = MaterializerConfig(
        horizon_bars=12,
        now_utc_ms=bar_close + 12 * 60_000 + 60_000,  # past horizon
    )
    res = materialize(
        verdicts=[v], shadow_plans={vid: [p]}, envelopes={},
        candles_by_symbol={"BTCUSDT": cs},
        sim_cfg=sim_cfg, mat_cfg=mat_cfg,
    )
    return res, sim_cfg, mat_cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_1_does_not_filter_on_applied_true():
    """Even with applied=false on EVERY verdict (shadow mode), outcomes must be produced."""
    res, _, _ = _build_simple_run(Path("."), applied=False)
    assert res.verdict_total == 1
    assert res.applied_false_count == 1
    assert res.applied_true_count == 0
    assert len(res.outcomes) == 1  # would be 0 if applied=true was filtered


def test_2_ts_ms_bar_close_invariant_required():
    """A verdict whose ts_ms violates the bar-close invariant must be skipped."""
    bad_ts = 1_000_000_000_000  # multiple of 60_000, NOT 60_000-1
    v = _make_verdict("vrd_bad", "BTCUSDT", 60, bad_ts)
    p = _make_plan("p1", "vrd_bad", "BTCUSDT", 60, bad_ts, "BUY")
    res = materialize(
        [v], {"vrd_bad": [p]}, {}, {}, _make_sim_cfg(),
        MaterializerConfig(now_utc_ms=bad_ts + 10_000_000),
    )
    assert len(res.outcomes) == 0
    assert any(s.skip_reason == "invalid_bar_close_ts" for s in res.skipped)


def test_3_one_outcome_per_correlation_key():
    res, _, _ = _build_simple_run(Path("."))
    seen = set()
    for o in res.outcomes:
        key = (o.strategy_id, o.symbol, o.tf_sec, o.bar_close_ts)
        assert key not in seen
        seen.add(key)


def test_4_duplicate_correlation_key_hard_fails(tmp_path, monkeypatch):
    """When two verdicts map to the same CorrelationKey, materializer must surface
    duplicates and the CLI runner must SystemExit(2) BEFORE writing outcomes.json."""
    bar_close = _bar_close(1_000_000_000_000, 60)
    v1 = _make_verdict("vrd_a", "BTCUSDT", 60, bar_close)
    v2 = _make_verdict("vrd_b", "BTCUSDT", 60, bar_close)  # same key
    p1 = _make_plan("pa", "vrd_a", "BTCUSDT", 60, bar_close, "BUY")
    p2 = _make_plan("pb", "vrd_b", "BTCUSDT", 60, bar_close, "BUY")
    cs = [_candle(bar_close + 1, 100, 111, 99, 110)]
    res = materialize(
        [v1, v2], {"vrd_a": [p1], "vrd_b": [p2]}, {},
        {"BTCUSDT": cs}, _make_sim_cfg(),
        MaterializerConfig(now_utc_ms=bar_close + 100_000_000),
    )
    assert len(res.duplicate_correlation_keys) == 1
    # CLI run must SystemExit when duplicates present.
    import argparse
    args = argparse.Namespace(
        judge_log_dir=tmp_path / "jl",
        raw_1m_dir=tmp_path / "r",
        recorder_1m_dir=tmp_path / "rec",
        simulator_config=tmp_path / "cfg.yaml",
        outcomes_path=tmp_path / "out.json",
        manifest_path=tmp_path / "manifest.json",
        skipped_path=tmp_path / "skipped.jsonl",
        diagnostics_path=tmp_path / "diag.jsonl",
        report_path=tmp_path / "report.md",
        horizon_bars=12, fill_model="optimistic_touch",
        now_utc_ms=bar_close + 100_000_000,
        write_report=False, log_level="WARNING",
    )
    (tmp_path / "jl").mkdir()
    args.simulator_config.write_text(
        "judge_simulator:\n"
        "  judge_logs_path: x\n  outcome_data_path: y\n"
        "  calibration_dataset_path: z\n  summary_report_path: w\n"
        "  fee_per_cycle_bps: 25\n  slippage_pct: 0.1\n",
        encoding="utf-8",
    )
    # Monkeypatch loaders so run() uses our synthetic data.
    monkeypatch.setattr(bom, "load_verdicts", lambda d: [v1, v2])
    monkeypatch.setattr(bom, "load_shadow_plans", lambda d: {
                        "vrd_a": [p1], "vrd_b": [p2]})
    monkeypatch.setattr(bom, "load_envelopes", lambda d: {})
    monkeypatch.setattr(bom, "load_raw_binance_candles",
                        lambda d: {"BTCUSDT": cs})
    monkeypatch.setattr(bom, "load_recorder_candles", lambda d: {})
    with pytest.raises(SystemExit) as exc:
        bom.run(args)
    assert exc.value.code == 2
    assert not args.outcomes_path.exists()


def test_5_no_metadata_written_to_outcomes_json():
    """outcomes.json must contain ONLY the 8 schema-allowed fields per outcome."""
    res, _, _ = _build_simple_run(Path("."))
    payload = build_outcomes_json(res.outcomes)
    assert set(payload.keys()) == {"schema_version", "outcomes"}
    allowed = {"strategy_id", "symbol", "tf_sec", "bar_close_ts", "matched_trade",
               "entry_price", "exit_price", "exit_ts_ms"}
    for o in payload["outcomes"]:
        forbidden = set(o.keys()) - allowed
        assert not forbidden, f"forbidden keys leaked into outcomes.json: {forbidden}"


def test_6_outcomes_json_validates_against_schema():
    res, _, _ = _build_simple_run(Path("."))
    payload = build_outcomes_json(res.outcomes)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(payload)
    errors = validate_outcomes_json(payload)
    assert errors == []


def test_7_no_future_leakage_entry_window_starts_after_bar_close():
    """The materializer must REFUSE to consider the decision candle itself for fill/exit."""
    bar_close = _bar_close(1_000_000_000_000, 60)
    # Decision-bar candle (open == bar_close - 59_999) MUST be excluded.
    decision_open = bar_close - 60_000 + 1
    # would fill+TP trivially
    decision_candle = _candle(decision_open, 100, 200, 50, 100)
    eligible = _candle(bar_close + 1, 100, 101, 99, 100)
    p = CanonicalPlan(
        plan_id="p", source_verdict_id="v", symbol="BTCUSDT", tf_sec=60,
        ts_ms=bar_close, entry_side="BUY", limit_price=99.5, tp_price=200.0, sl_price=50.0,
        confidence=1.0, confidence_tier="high",
    )
    window = candles_in_window(
        [decision_candle, eligible], bar_close, bar_close + 12 * 60_000)
    assert decision_candle not in window
    assert window == [eligible]
    r = replay_plan_on_candles(p, window)
    # Must use eligible, not decision; eligible high=101 << tp=200, low=99 > limit? limit=99.5, low=99 → fills
    assert r.matched_trade is True
    # because eligible never reaches tp=200
    assert r.exit_classification != "FILLED_TP"


def test_8_future_tail_skipped_with_explicit_reason():
    """If bar_close + horizon > now, skip with horizon_extends_past_current_time, not silent drop."""
    bar_close = _bar_close(1_000_000_000_000, 60)
    v = _make_verdict("vrd_f", "BTCUSDT", 60, bar_close)
    p = _make_plan("pf", "vrd_f", "BTCUSDT", 60, bar_close, "BUY")
    res = materialize(
        [v], {"vrd_f": [p]}, {}, {"BTCUSDT": []}, _make_sim_cfg(),
        # only 1 bar in, < 12 horizon
        MaterializerConfig(now_utc_ms=bar_close + 60_000),
    )
    assert len(res.outcomes) == 0
    assert any(s.skip_reason ==
               "horizon_extends_past_current_time" for s in res.skipped)


def test_9_no_silent_drop_accounting_identity():
    """outcomes + skipped MUST account for every input verdict (no silent loss)."""
    # Mix: one fills, one wrong verdict, one future-tail, one missing plan.
    bc = _bar_close(1_000_000_000_000, 60)
    v_ok = _make_verdict("v_ok", "BTCUSDT", 60, bc)
    v_ne = _make_verdict("v_ne", "BTCUSDT", 60, bc +
                         60_000, entry_verdict="NO_ENTRY")
    v_ft = _make_verdict("v_ft", "BTCUSDT", 60, bc + 120_000)
    v_mp = _make_verdict("v_mp", "BTCUSDT", 60, bc + 180_000)  # no plan rows
    p_ok = _make_plan("p_ok", "v_ok", "BTCUSDT", 60, bc, "BUY")
    p_ft = _make_plan("p_ft", "v_ft", "BTCUSDT", 60, bc + 120_000, "BUY")
    cs = [_candle(bc + 1, 100, 111, 99, 110)]
    res = materialize(
        [v_ok, v_ne, v_ft, v_mp],
        {"v_ok": [p_ok], "v_ft": [p_ft]}, {},
        {"BTCUSDT": cs}, _make_sim_cfg(),
        # ok-bar runnable, ft-bar future
        MaterializerConfig(now_utc_ms=bc + 60_000 + 1),
    )
    assert res.verdict_total == 4
    assert len(res.outcomes) + len(res.skipped) == 4


def test_10_canonical_plan_selection_deterministic():
    """Same plan set always yields same chosen plan; tier high > medium > low; tiebreak by plan_id."""
    base = dict(symbol="BTCUSDT", tf_sec=60,
                ts_ms=_bar_close(0, 60), side="BUY")
    plans = [
        _make_plan("p_med", "v", **base, tier="medium",
                   confidence=0.9),  # type: ignore[arg-type]
        _make_plan("p_high_b", "v", **base, tier="high", confidence=0.9),
        _make_plan("p_high_a", "v", **base, tier="high", confidence=0.9),
        _make_plan("p_low", "v", **base, tier="low",
                   confidence=0.95, actionable=False),
    ]
    chosen1, _, _ = select_canonical_plan(plans)
    chosen2, _, _ = select_canonical_plan(list(reversed(plans)))
    assert chosen1 is not None and chosen2 is not None
    # tier high + alphabetical tiebreak
    assert chosen1.plan_id == chosen2.plan_id == "p_high_a"


def test_11_no_fill_writes_matched_trade_false():
    bc = _bar_close(1_000_000_000_000, 60)
    # Candle never touches limit (long needs low <= limit).
    cs = [_candle(bc + 1, 200, 210, 199, 205)]  # low=199 > limit=100
    res, _, _ = _build_simple_run(Path("."), candles=cs)
    assert len(res.outcomes) == 1
    o = res.outcomes[0]
    assert o.matched_trade is False
    assert o.entry_price is None and o.exit_price is None and o.exit_ts_ms is None


def test_12_long_tp_hit_generates_exit_price():
    bc = _bar_close(1_000_000_000_000, 60)
    cs = [_candle(bc + 1, 100, 111, 99, 108)]  # fills at 100; tp=110 hits
    res, _, _ = _build_simple_run(Path("."), candles=cs)
    o = res.outcomes[0]
    assert o.matched_trade is True
    assert o.entry_price == 100.0
    assert o.exit_price == 110.0
    # Diagnostic separately records FILLED_TP.
    assert res.diagnostics[0].exit_classification == "FILLED_TP"


def test_13_long_sl_hit_generates_exit_price():
    bc = _bar_close(1_000_000_000_000, 60)
    # Construct: candle has low touching limit (100) and SL (95). To avoid same-candle TP:
    # First candle fills at limit=100, but also low=94 ≤ sl=95 → AMBIGUOUS unless we split.
    # Use two candles: first fills, second hits SL.
    c1 = _candle(bc + 1, 100, 101, 99.5, 100.5)  # fills, neither TP nor SL
    c2 = _candle(bc + 60_001, 100, 100, 94, 96)  # SL hit (95)
    res, _, _ = _build_simple_run(Path("."), candles=[c1, c2])
    o = res.outcomes[0]
    assert o.matched_trade is True
    assert o.entry_price == 100.0
    assert o.exit_price == 95.0
    assert res.diagnostics[0].exit_classification == "FILLED_SL"


def test_14_short_tp_hit_generates_exit_price():
    bc = _bar_close(1_000_000_000_000, 60)
    # SHORT: fills when high >= limit; tp_price < limit, sl_price > limit.
    # high=104 ≥ limit=100 → fill; low=88 ≤ tp=90 → TP; high<sl=105
    cs = [_candle(bc + 1, 100, 104, 88, 90)]
    res, _, _ = _build_simple_run(
        Path("."), ent="OPEN_SHORT", side="SELL",
        limit=100.0, tp=90.0, sl=105.0, candles=cs,
    )
    o = res.outcomes[0]
    assert o.matched_trade is True
    assert o.entry_price == 100.0
    assert o.exit_price == 90.0
    assert res.diagnostics[0].exit_classification == "FILLED_TP"


def test_15_short_sl_hit_generates_exit_price():
    bc = _bar_close(1_000_000_000_000, 60)
    # high=100.5 ≥ limit=100 → fill; neither TP/SL
    c1 = _candle(bc + 1, 100, 100.5, 99.5, 100.2)
    c2 = _candle(bc + 60_001, 100, 106, 100, 105)  # high=106 ≥ sl=105 → SL
    res, _, _ = _build_simple_run(
        Path("."), ent="OPEN_SHORT", side="SELL",
        limit=100.0, tp=90.0, sl=105.0, candles=[c1, c2],
    )
    o = res.outcomes[0]
    assert o.matched_trade is True
    assert o.entry_price == 100.0
    assert o.exit_price == 105.0
    assert res.diagnostics[0].exit_classification == "FILLED_SL"


def test_16_same_candle_tp_sl_ambiguity_recorded_in_sidecar_not_outcomes():
    bc = _bar_close(1_000_000_000_000, 60)
    # First candle fills (low=99 ≤ limit=100) AND hits both tp=110 (high≥110) and sl=95 (low≤95).
    cs = [_candle(bc + 1, 100, 112, 94, 100)]
    res, _, _ = _build_simple_run(Path("."), candles=cs)
    o = res.outcomes[0]
    assert o.matched_trade is True
    # Worst-case policy → SL price (95).
    assert o.exit_price == 95.0
    # outcomes.json carries NO classification field.
    assert "exit_classification" not in o.to_dict()
    # Diagnostic carries it.
    diag = res.diagnostics[0]
    assert diag.exit_classification == "AMBIGUOUS_TP_SL_SAME_CANDLE"
    assert diag.ambiguity_policy == "worst_case"


def test_17_timeout_exits_at_last_horizon_close():
    bc = _bar_close(1_000_000_000_000, 60)
    # Fills bar 1, never hits TP/SL across 3 bars; horizon=3 → timeout.
    c1 = _candle(bc + 1, 100, 101, 99.5, 100.5)
    c2 = _candle(bc + 60_001, 100.5, 100.7, 100.3, 100.5)
    c3 = _candle(bc + 120_001, 100.5, 100.6, 100.4, 100.55)
    sim_cfg = _make_sim_cfg()
    bar_close = bc
    v = _make_verdict("v1", "BTCUSDT", 60, bar_close)
    p = _make_plan("p1", "v1", "BTCUSDT", 60, bar_close, "BUY",
                   limit_price=100.0, tp_price=200.0, sl_price=50.0)
    res = materialize(
        [v], {"v1": [p]}, {}, {"BTCUSDT": [c1, c2, c3]}, sim_cfg,
        MaterializerConfig(horizon_bars=3, now_utc_ms=bc + 10_000_000),
    )
    o = res.outcomes[0]
    assert o.matched_trade is True
    assert o.exit_price == 100.55  # last candle close
    assert o.exit_ts_ms == c3.close_time_ms
    assert res.diagnostics[0].exit_classification == "TIMEOUT"


def test_18_fee_slippage_sources_recorded_in_manifest_not_applied(tmp_path):
    """Manifest must declare fee/slippage source strings and resolved values, but
    the materializer does NOT apply them — entry/exit prices match the raw plan."""
    res, sim_cfg, mat_cfg = _build_simple_run(tmp_path)
    out_path = tmp_path / "outcomes.json"
    write = build_outcomes_json(res.outcomes)
    out_path.write_text(json.dumps(write), encoding="utf-8")
    manifest = build_manifest(
        sim_cfg=sim_cfg, mat_cfg=mat_cfg, result=res,
        sim_config_path=Path("config/judge_simulator.yaml"),
        outcomes_path=out_path, economics_present=False,
    )
    assert manifest["fee_source"].endswith("fee_per_cycle_bps")
    assert manifest["slippage_source"].endswith("slippage_pct")
    assert manifest["fee_per_cycle_bps_value"] == 25.0
    assert manifest["slippage_pct_value"] == 0.1
    assert manifest["fee_slippage_applied_by_materializer"] is False
    # Outcomes prices untouched by fees.
    o = res.outcomes[0]
    assert o.entry_price == 100.0  # exactly the plan limit_price


def test_19_notional_pct_only_mode_records_no_usd_roi(tmp_path):
    res, sim_cfg, mat_cfg = _build_simple_run(tmp_path)
    assert sim_cfg.economics is None
    manifest = build_manifest(
        sim_cfg=sim_cfg, mat_cfg=mat_cfg, result=res,
        sim_config_path=Path("config/judge_simulator.yaml"),
        outcomes_path=tmp_path / "out.json", economics_present=False,
    )
    assert manifest["notional_mode"] == "pct_only"
    assert manifest["notional_pointers"]["fixed_notional_usd"] is None
    assert manifest["notional_resolved"] is None
    # Diagnostics carry no usd ROI / notional sidecar.
    for d in res.diagnostics:
        assert d.notional_sidecar is None
        assert d.roi_usd is None


def test_20_economics_enabled_records_notional_sidecar_only(tmp_path):
    econ = EconomicsConfig(
        notional_usd_per_trade=5000.0,
        leverage_source="instruments_yaml",
    )
    sim_cfg = _make_sim_cfg(economics=econ)
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    bc = _bar_close(1_000_000_000_000, 60)
    v = _make_verdict("v1", "BTCUSDT", 60, bc)
    p = _make_plan("p1", "v1", "BTCUSDT", 60, bc, "BUY",
                   limit_price=60000.0, tp_price=60500.0, sl_price=59500.0)
    cs = [_candle(bc + 1, 60000, 60600, 59900, 60500)]  # fills + TP
    res = materialize(
        [v], {"v1": [p]}, {}, {"BTCUSDT": cs}, sim_cfg,
        MaterializerConfig(now_utc_ms=bc + 10_000_000),
        precision_map=precision,
    )
    # outcomes.json still strict — no notional/qty/leverage/roi fields.
    payload = build_outcomes_json(res.outcomes)
    validate_outcomes_json(payload) == []
    for o in payload["outcomes"]:
        allowed = {"strategy_id", "symbol", "tf_sec", "bar_close_ts",
                   "matched_trade", "entry_price", "exit_price", "exit_ts_ms"}
        assert set(o.keys()) <= allowed
    # Diagnostic carries notional/ROI sidecar.
    d = res.diagnostics[0]
    assert d.notional_sidecar is not None
    assert d.roi_usd is not None
    assert d.roi_usd["roi_usd_absolute"] is not None
    # Manifest reports explicit_usd mode.
    manifest = build_manifest(
        sim_cfg=sim_cfg, mat_cfg=MaterializerConfig(
            now_utc_ms=bc + 10_000_000),
        result=res, sim_config_path=Path("config/judge_simulator.yaml"),
        outcomes_path=tmp_path / "out.json", economics_present=True,
    )
    assert manifest["notional_mode"] == "explicit_usd"
    assert manifest["notional_resolved"]["notional_usd_per_trade"] == 5000.0


def test_21_schema_strict_rejects_extra_fields():
    """Independent guard: if anyone adds a stray field to an outcome dict, schema rejects."""
    res, _, _ = _build_simple_run(Path("."))
    payload = build_outcomes_json(res.outcomes)
    payload["outcomes"][0]["unauthorized_field"] = "leak"
    errors = validate_outcomes_json(payload)
    assert errors, "schema must reject additional properties on outcome rows"


def test_22_materializer_output_deterministic(tmp_path):
    """Same input → byte-identical outcomes.json across two runs."""
    res1, _, _ = _build_simple_run(tmp_path)
    res2, _, _ = _build_simple_run(tmp_path)
    p1 = build_outcomes_json(res1.outcomes)
    p2 = build_outcomes_json(res2.outcomes)
    s1 = json.dumps(p1, sort_keys=True, indent=2)
    s2 = json.dumps(p2, sort_keys=True, indent=2)
    assert s1 == s2
