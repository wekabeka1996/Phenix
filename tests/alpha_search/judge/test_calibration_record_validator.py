"""PKG-4.PRE tests for the CalibrationRecordModel has_disagreement semantic repair.

Root cause: build_calibration_records() computed has_disagreement via a
verdict_id-based set lookup.  Production judge logs emit verdicts for the same
ts_ms on multiple timeframes (180 / 300 / 900 s) sharing the same verdict_id
format (vrd_entry_{SYMBOL}_{ts_ms}).  When one timeframe produced a
disagreement the verdict_id entered the set and contaminated has_disagreement
for sibling timeframes that had no disagreement — causing the
CalibrationRecordModel validator to raise.

Fix: compute has_disagreement directly as entry_verdict != optimal_action (the
same formula the validator uses), independent of any disagreements list.
"""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Optional

import pytest

from apps.reference.domains.alpha_search.judge.simulator.calibration_dataset_writer import (
    CalibrationRecordModel,
    build_calibration_records,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.simulator.simulator_engine import (
    CorrelatedVerdictOutcome,
    CorrelationKey,
    OutcomeRecord,
    VerdictRecord,
    run_simulation,
)

ROOT = Path(__file__).resolve().parents[3]
SSOT_PATH = ROOT / "config" / "judge_simulator.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg() -> SimulatorConfig:
    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    return SimulatorConfig(**raw["judge_simulator"])


def _key(symbol: str, tf_sec: int, bar_close_ts: int) -> CorrelationKey:
    return CorrelationKey(
        strategy_id="aurora",
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=bar_close_ts,
    )


def _verdict(vid: str, key: CorrelationKey, entry_verdict: str,
             confidence: float = 0.7) -> VerdictRecord:
    return VerdictRecord(
        verdict_id=vid,
        correlation_key=key,
        entry_verdict=entry_verdict,
        confidence=confidence,
        dissent_noted=False,
    )


def _outcome(key: CorrelationKey, matched_trade: bool,
             entry_price: float | None = None,
             exit_price: float | None = None) -> OutcomeRecord:
    return OutcomeRecord(
        correlation_key=key,
        matched_trade=matched_trade,
        entry_price=entry_price,
        exit_price=exit_price,
        exit_ts_ms=None,
    )


def _corr(verdict: VerdictRecord, outcome: OutcomeRecord | None,
          net_return: float | None = None) -> CorrelatedVerdictOutcome:
    return CorrelatedVerdictOutcome(
        verdict=verdict,
        outcome=outcome,
        net_return=net_return,
    )


# ---------------------------------------------------------------------------
# T1 — Reproduce the multi-tf verdict_id contamination failure
# ---------------------------------------------------------------------------

def test_1_reproduces_has_disagreement_failure_case():
    """
    verdict_id is the same for tf_sec=180 and tf_sec=300 (same ts_ms, different
    timeframe).  The tf=180 correlation produces optimal_action=NO_ENTRY
    (disagreement).  The tf=300 correlation produces optimal_action=OPEN_LONG
    (no disagreement).  After the fix, the tf=300 record must have
    has_disagreement=False even though the shared verdict_id was in the
    disagreement set under the old scheme.
    """
    ts_ms = 1779069599999  # satisfies bar-close for tf 180, 300, 900
    vid = "vrd_entry_1000PEPEUSDT_1779069599999"
    cfg = _cfg()

    # tf=180 — no fill → optimal=NO_ENTRY → disagreement for OPEN_LONG
    key_180 = _key("1000PEPEUSDT", 180, ts_ms)
    v_180 = _verdict(vid, key_180, "OPEN_LONG")
    o_180 = _outcome(key_180, matched_trade=False)
    c_180 = _corr(v_180, o_180)

    # tf=300 — TP hit, profitable → optimal=OPEN_LONG → no disagreement
    key_300 = _key("1000PEPEUSDT", 300, ts_ms)
    v_300 = _verdict(vid, key_300, "OPEN_LONG")
    o_300 = _outcome(key_300, matched_trade=True,
                     entry_price=100.0, exit_price=105.0)
    c_300 = _corr(v_300, o_300, net_return=0.04)

    records = build_calibration_records(
        correlations=[c_180, c_300],
        disagreements=[],
        config=cfg,
    )
    assert len(records) == 2

    rec_180 = next(r for r in records if r["tf_sec"] == 180)
    rec_300 = next(r for r in records if r["tf_sec"] == 300)

    # tf=180: no fill → optimal=NO_ENTRY → OPEN_LONG != NO_ENTRY → disagreement
    assert rec_180["has_disagreement"] is True
    assert rec_180["cohort"] == "MISSED_OPPORTUNITY" or rec_180["cohort"] == "INCORRECT_ENTRY"

    # tf=300: TP hit profitable → optimal=OPEN_LONG → OPEN_LONG == OPEN_LONG → no disagreement
    assert rec_300["has_disagreement"] is False
    assert rec_300["cohort"] == "CORRECT_ENTRY"


# ---------------------------------------------------------------------------
# T2 — has_disagreement=True when entry_verdict differs from optimal_action
# ---------------------------------------------------------------------------

def test_2_has_disagreement_true_when_verdict_differs_from_optimal_action():
    cfg = _cfg()
    ts_ms = 1779054479999
    key = _key("BTCUSDT", 180, ts_ms)
    # OPEN_LONG verdict but price fell → optimal=NO_ENTRY (or OPEN_SHORT)
    v = _verdict("v1", key, "OPEN_LONG")
    o = _outcome(key, matched_trade=False)  # no fill → optimal=NO_ENTRY
    records = build_calibration_records(
        correlations=[_corr(v, o)], disagreements=[], config=cfg,
    )
    assert len(records) == 1
    assert records[0]["has_disagreement"] is True
    assert records[0]["entry_verdict"] == "OPEN_LONG"
    assert records[0]["optimal_action"] == "NO_ENTRY"


# ---------------------------------------------------------------------------
# T3 — has_disagreement=False when entry_verdict matches optimal_action
# ---------------------------------------------------------------------------

def test_3_has_disagreement_false_when_verdict_matches_optimal_action():
    cfg = _cfg()
    ts_ms = 1779054479999
    key = _key("BTCUSDT", 180, ts_ms)
    # OPEN_LONG verdict, profitable TP hit → optimal=OPEN_LONG
    v = _verdict("v2", key, "OPEN_LONG")
    o = _outcome(key, matched_trade=True,
                 entry_price=60000.0, exit_price=65000.0)
    records = build_calibration_records(
        correlations=[_corr(v, o, net_return=0.07)], disagreements=[], config=cfg,
    )
    assert len(records) == 1
    assert records[0]["has_disagreement"] is False
    assert records[0]["cohort"] == "CORRECT_ENTRY"


# ---------------------------------------------------------------------------
# T4 — No-fill and timeout semantics are explicit
# ---------------------------------------------------------------------------

def test_4_no_fill_or_timeout_semantics_are_explicit():
    cfg = _cfg()
    ts_ms = 1779054479999
    key = _key("SOLUSDT", 300, ts_ms)
    # No fill → matched_trade=False → optimal=NO_ENTRY; OPEN_SHORT disagrees
    v = _verdict("v3", key, "OPEN_SHORT")
    o = _outcome(key, matched_trade=False)
    records = build_calibration_records(
        correlations=[_corr(v, o)], disagreements=[], config=cfg,
    )
    assert len(records) == 1
    r = records[0]
    assert r["matched_trade"] is False
    assert r["optimal_action"] == "NO_ENTRY"
    assert r["has_disagreement"] is True  # OPEN_SHORT != NO_ENTRY
    assert r["cohort"] == "INCORRECT_ENTRY"


# ---------------------------------------------------------------------------
# T5 — SUPPRESS and NO_ENTRY semantics are explicit
# ---------------------------------------------------------------------------

def test_5_suppress_or_no_entry_semantics_are_explicit():
    cfg = _cfg()
    ts_ms = 1779054479999

    # SUPPRESS verdict → has_disagreement always False
    key_s = _key("ETHUSDT", 180, ts_ms)
    v_s = _verdict("v_s", key_s, "SUPPRESS")
    o_s = _outcome(key_s, matched_trade=False)
    records_s = build_calibration_records(
        correlations=[_corr(v_s, o_s)], disagreements=[], config=cfg,
    )
    assert records_s[0]["has_disagreement"] is False
    assert records_s[0]["cohort"] == "INCONCLUSIVE"

    # NO_ENTRY verdict with matching optimal (both NO_ENTRY) → False
    key_n = _key("ETHUSDT", 300, ts_ms)
    v_n = _verdict("v_n", key_n, "NO_ENTRY")
    o_n = _outcome(key_n, matched_trade=False)
    records_n = build_calibration_records(
        correlations=[_corr(v_n, o_n)], disagreements=[], config=cfg,
    )
    assert records_n[0]["has_disagreement"] is False
    assert records_n[0]["optimal_action"] == "NO_ENTRY"
    assert records_n[0]["cohort"] == "CORRECT_ABSTAIN"


# ---------------------------------------------------------------------------
# T6 — CalibrationRecordModel rejects inconsistent builder output
# ---------------------------------------------------------------------------

def test_6_calibration_record_model_rejects_inconsistent_builder_output():
    """Validator must reject entry_verdict=OPEN_LONG / optimal=OPEN_LONG / has_disagreement=True."""
    with pytest.raises(Exception, match="has_disagreement"):
        CalibrationRecordModel(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=180,
            bar_close_ts=1779054479999,
            verdict_id="vrd_test",
            entry_verdict="OPEN_LONG",
            confidence=0.6,
            dissent_noted=False,
            matched_trade=True,
            raw_return=0.04,
            fee_cost=0.0025,
            slippage_cost=0.001,
            net_return=0.036,
            optimal_action="OPEN_LONG",
            has_disagreement=True,  # wrong — should be False
            cohort="CORRECT_ENTRY",
        )


# ---------------------------------------------------------------------------
# T7 — Builder outputs validator-consistent records for mixed correlations
# ---------------------------------------------------------------------------

def test_7_calibration_builder_outputs_validator_consistent_records():
    """All records from build_calibration_records() must pass model_validate."""
    cfg = _cfg()
    ts_ms = 1779054479999

    correlations = [
        # OPEN_LONG, TP hit profitable
        _corr(
            _verdict("v_ol_tp", _key("BTCUSDT", 180, ts_ms), "OPEN_LONG"),
            _outcome(_key("BTCUSDT", 180, ts_ms), True, 60000.0, 65000.0),
            net_return=0.07,
        ),
        # OPEN_SHORT, no fill
        _corr(
            _verdict("v_os_nf", _key("ETHUSDT", 300, ts_ms), "OPEN_SHORT"),
            _outcome(_key("ETHUSDT", 300, ts_ms), False),
        ),
        # NO_ENTRY, no fill (both optimal=NO_ENTRY)
        _corr(
            _verdict("v_ne", _key("SOLUSDT", 900, ts_ms), "NO_ENTRY"),
            _outcome(_key("SOLUSDT", 900, ts_ms), False),
        ),
        # SUPPRESS
        _corr(
            _verdict("v_sup", _key("DOGEUSDT", 180, ts_ms), "SUPPRESS"),
            _outcome(_key("DOGEUSDT", 180, ts_ms), False),
        ),
    ]

    records = build_calibration_records(
        correlations=correlations, disagreements=[], config=cfg,
    )
    assert len(records) == 4
    for record in records:
        CalibrationRecordModel.model_validate(record)  # must not raise


# ---------------------------------------------------------------------------
# T8 — Simulator CLI smoke: run_simulation() completes without exception
# ---------------------------------------------------------------------------

def test_8_simulator_cli_smoke_runs_past_calibration_dataset_build():
    """run_simulation() against real data must complete and produce non-empty
    calibration_records.  This was the primary PKG-4.PRE blocker."""
    cfg = _cfg()
    result = run_simulation(cfg)

    assert result.calibration_records, "calibration_records must be non-empty"
    # Every record must pass model_validate (builder/validator consistency)
    for record in result.calibration_records:
        CalibrationRecordModel.model_validate(record)


# ---------------------------------------------------------------------------
# T9 — Existing PKG-1/2/3 tests not referenced here but run in regression
# (This test just confirms the import chain is intact.)
# ---------------------------------------------------------------------------

def test_9_calibration_record_model_accepts_all_cohort_variants():
    """
    Confirm all five cohort values are accepted when entry_verdict/optimal_action
    are set consistently.  Guards against any future CalibrationCohort literal drift.
    """
    base = dict(
        strategy_id="aurora", symbol="BTCUSDT", tf_sec=180,
        bar_close_ts=1779054479999, verdict_id="v_ok", confidence=0.5,
        dissent_noted=False, matched_trade=False,
        raw_return=None, fee_cost=None, slippage_cost=None, net_return=None,
    )

    cases = [
        # (entry_verdict, optimal_action, has_disagreement, cohort)
        ("OPEN_LONG", "OPEN_LONG", False, "CORRECT_ENTRY"),
        ("OPEN_LONG", "NO_ENTRY", True, "INCORRECT_ENTRY"),
        ("NO_ENTRY", "NO_ENTRY", False, "CORRECT_ABSTAIN"),
        ("NO_ENTRY", "OPEN_LONG", True, "MISSED_OPPORTUNITY"),
        ("SUPPRESS", "NO_ENTRY", False, "INCONCLUSIVE"),
    ]
    for entry_verdict, optimal_action, has_disagreement, cohort in cases:
        # For non-actionable suppress verdict, economics must be None
        rec = {
            **base,
            "entry_verdict": entry_verdict,
            "optimal_action": optimal_action,
            "has_disagreement": has_disagreement,
            "cohort": cohort,
        }
        CalibrationRecordModel.model_validate(rec)  # must not raise
