"""Tests for Phase 5 Package 5E summary report writer."""

from __future__ import annotations

import json
import math
from dataclasses import field as dataclass_field
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.simulator.simulator_engine import (
    AccuracyBucket,
    BasicAccuracySummary,
    CorrelatedVerdictOutcome,
    CorrelationKey,
    OutcomeRecord,
    SimulationResult,
    VerdictRecord,
)
from apps.reference.domains.alpha_search.judge.simulator.summary_report_writer import (
    build_summary_report,
    write_summary_report,
)

_SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/simulator/schemas/summary_report_v1.json"
)

_FIXED_TS = 1712000000000


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _key(bar_close_ts: int = 1) -> CorrelationKey:
    return CorrelationKey(
        strategy_id="aurora",
        symbol="BTCUSDT",
        tf_sec=300,
        bar_close_ts=bar_close_ts,
    )


def _verdict(
    verdict_id: str = "v-1",
    entry_verdict: str = "OPEN_LONG",
    bar_close_ts: int = 1,
    confidence: float = 0.8,
    dissent_noted: bool = False,
) -> VerdictRecord:
    return VerdictRecord(
        verdict_id=verdict_id,
        correlation_key=_key(bar_close_ts),
        entry_verdict=entry_verdict,
        confidence=confidence,
        dissent_noted=dissent_noted,
    )


def _outcome(
    bar_close_ts: int = 1,
    matched_trade: bool = True,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
) -> OutcomeRecord:
    return OutcomeRecord(
        correlation_key=_key(bar_close_ts),
        matched_trade=matched_trade,
        entry_price=entry_price,
        exit_price=exit_price,
        exit_ts_ms=bar_close_ts + 5000 if matched_trade else None,
    )


def _corr(
    verdict_id: str = "v-1",
    entry_verdict: str = "OPEN_LONG",
    bar_close_ts: int = 1,
    matched: bool = True,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
    side: str | None = "LONG",
    raw_return: float | None = 0.1,
    fee_cost: float | None = 0.0025,
    slippage_cost: float | None = 0.001,
    net_return: float | None = 0.0965,
) -> CorrelatedVerdictOutcome:
    return CorrelatedVerdictOutcome(
        verdict=_verdict(verdict_id, entry_verdict, bar_close_ts),
        outcome=_outcome(bar_close_ts, matched, entry_price,
                         exit_price) if matched else None,
        side=side,
        entry_price=entry_price if matched and side else None,
        exit_price=exit_price if matched and side else None,
        raw_return=raw_return,
        fee_cost=fee_cost,
        slippage_cost=slippage_cost,
        net_return=net_return,
    )


def _empty_accuracy() -> BasicAccuracySummary:
    return BasicAccuracySummary(
        evaluated_count=0,
        correct_count=0,
        incorrect_count=0,
        skipped_count=0,
        by_verdict={},
    )


def _make_result(
    *,
    correlations: tuple[CorrelatedVerdictOutcome, ...] = (),
    verdict_count: int = 0,
    outcome_count: int = 0,
    matched_count: int = 0,
    unmatched_count: int = 0,
    disagreements: tuple[dict, ...] = (),
    expert_accuracy_records: tuple[dict, ...] = (),
    expert_accuracy_summary: dict | None = None,
    calibration_records: tuple[dict, ...] = (),
) -> SimulationResult:
    if expert_accuracy_summary is None:
        expert_accuracy_summary = {
            "total_count": 0,
            "correct_count": 0,
            "accuracy_rate": None,
            "skipped_count": 0,
            "by_expert": {},
        }
    return SimulationResult(
        total_verdict_records_loaded=verdict_count,
        total_outcome_records_loaded=outcome_count,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        accuracy_summary=_empty_accuracy(),
        correlations=correlations,
        disagreements=disagreements,
        expert_accuracy_records=expert_accuracy_records,
        expert_accuracy_summary=expert_accuracy_summary,
        calibration_records=calibration_records,
    )


# ---------- Schema ----------

class TestSummarySchema:
    def test_schema_compiles(self):
        Draft7Validator.check_schema(_load_schema())


# ---------- build_summary_report ----------

class TestBuildSummaryReport:
    def test_empty_result_produces_valid_report(self):
        result = _make_result()
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        assert report["schema_version"] == "1"
        assert report["generated_at_ms"] == _FIXED_TS
        assert report["input_counts"]["verdict_count"] == 0

    def test_input_counts_correct(self):
        result = _make_result(
            verdict_count=10,
            outcome_count=8,
            matched_count=7,
            unmatched_count=3,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        ic = report["input_counts"]
        assert ic["verdict_count"] == 10
        assert ic["outcome_count"] == 8
        assert ic["matched_count"] == 7
        assert ic["unmatched_count"] == 3

    def test_match_stats_correct(self):
        correlations = (
            _corr("v-1", "OPEN_LONG", 1),
            _corr("v-2", "OPEN_SHORT", 2),
            _corr("v-3", "NO_ENTRY", 3, side=None, raw_return=None,
                  fee_cost=None, slippage_cost=None, net_return=None),
            _corr("v-4", "OPEN_LONG", 4, matched=False, side=None,
                  raw_return=None, fee_cost=None, slippage_cost=None,
                  net_return=None),
        )
        result = _make_result(
            correlations=correlations,
            verdict_count=4,
            outcome_count=3,
            matched_count=3,
            unmatched_count=1,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        ms = report["match_stats"]
        assert ms["match_rate"] == 3 / 4
        assert ms["actionable_matched_count"] == 2
        assert ms["non_actionable_matched_count"] == 1

    def test_match_rate_none_when_no_verdicts(self):
        result = _make_result(verdict_count=0)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert report["match_stats"]["match_rate"] is None

    def test_economics_aggregation_correct(self):
        correlations = (
            _corr("v-1", "OPEN_LONG", 1,
                  raw_return=0.1, net_return=0.0965),
            _corr("v-2", "OPEN_SHORT", 2,
                  raw_return=-0.05, net_return=-0.0535, side="SHORT"),
        )
        result = _make_result(
            correlations=correlations,
            verdict_count=2,
            outcome_count=2,
            matched_count=2,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        econ = report["economics"]
        assert math.isclose(econ["avg_raw_return"], 0.025)
        assert math.isclose(econ["avg_net_return"], 0.0215)
        assert econ["positive_net_count"] == 1
        assert econ["negative_net_count"] == 1

    def test_economics_none_when_no_actionable(self):
        result = _make_result()
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert report["economics"]["avg_raw_return"] is None
        assert report["economics"]["avg_net_return"] is None

    def test_disagreement_stats_correct(self):
        disagreements = (
            {"verdict_id": "v-1", "cost_of_disagreement": 0.05},
            {"verdict_id": "v-2", "cost_of_disagreement": 0.10},
        )
        result = _make_result(
            disagreements=disagreements,
            matched_count=5,
            verdict_count=5,
            outcome_count=5,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        ds = report["disagreement_stats"]
        assert ds["disagreement_count"] == 2
        assert math.isclose(ds["disagreement_rate"], 0.4)
        assert math.isclose(ds["total_cost_of_disagreement"], 0.15)

    def test_disagreement_rate_none_when_no_matched(self):
        result = _make_result(matched_count=0)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert report["disagreement_stats"]["disagreement_rate"] is None

    def test_expert_accuracy_summary_preserved(self):
        expert_summary = {
            "total_count": 4,
            "correct_count": 3,
            "accuracy_rate": 0.75,
            "skipped_count": 1,
            "by_expert": {"e1": {"total": 2, "correct": 2}},
        }
        result = _make_result(expert_accuracy_summary=expert_summary)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        es = report["expert_accuracy_summary"]
        assert es["total_count"] == 4
        assert es["correct_count"] == 3
        assert es["accuracy_rate"] == 0.75

    def test_cohort_stats_correct(self):
        calibration_records = (
            {"cohort": "CORRECT_ENTRY"},
            {"cohort": "CORRECT_ENTRY"},
            {"cohort": "INCORRECT_ENTRY"},
            {"cohort": "CORRECT_ABSTAIN"},
            {"cohort": "MISSED_OPPORTUNITY"},
            {"cohort": "INCONCLUSIVE"},
            {"cohort": "INCONCLUSIVE"},
        )
        result = _make_result(
            calibration_records=calibration_records,
            verdict_count=7,
            matched_count=7,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        cs = report["cohort_stats"]
        assert cs["CORRECT_ENTRY"] == 2
        assert cs["INCORRECT_ENTRY"] == 1
        assert cs["CORRECT_ABSTAIN"] == 1
        assert cs["MISSED_OPPORTUNITY"] == 1
        assert cs["INCONCLUSIVE"] == 2

    def test_cohort_stats_all_zero_when_no_records(self):
        result = _make_result()
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        cs = report["cohort_stats"]
        for label in ("CORRECT_ENTRY", "INCORRECT_ENTRY", "CORRECT_ABSTAIN",
                      "MISSED_OPPORTUNITY", "INCONCLUSIVE"):
            assert cs[label] == 0

    def test_policy_readiness_notes_bounded_informational(self):
        result = _make_result(verdict_count=1, matched_count=1)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        notes = report["policy_readiness_notes"]
        assert isinstance(notes, list)
        assert all(isinstance(n, str) for n in notes)
        assert len(notes) >= 1

    def test_report_validates_against_schema(self):
        result = _make_result(verdict_count=1, matched_count=1)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)

        validator = Draft7Validator(_load_schema())
        errors = list(validator.iter_errors(report))
        assert errors == []

    def test_deterministic_for_same_inputs(self):
        result = _make_result(
            correlations=(
                _corr("v-1", "OPEN_LONG", 1),
                _corr("v-2", "OPEN_SHORT", 2, side="SHORT",
                      raw_return=0.1, net_return=0.0965),
            ),
            verdict_count=2,
            outcome_count=2,
            matched_count=2,
            calibration_records=(
                {"cohort": "CORRECT_ENTRY"},
                {"cohort": "INCORRECT_ENTRY"},
            ),
        )
        r1 = build_summary_report(result, generated_at_ms=_FIXED_TS)
        r2 = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert r1 == r2

    def test_generated_at_ms_uses_wall_clock_when_omitted(self):
        result = _make_result()
        report = build_summary_report(result)
        assert isinstance(report["generated_at_ms"], int)
        assert report["generated_at_ms"] > 0


# ---------- write_summary_report ----------

class TestWriteSummaryReport:
    def _valid_report(self) -> dict:
        result = _make_result(verdict_count=1, matched_count=1)
        return build_summary_report(result, generated_at_ms=_FIXED_TS)

    def test_writes_json_successfully(self, tmp_path: Path):
        report = self._valid_report()
        out = tmp_path / "summary.json"

        path = write_summary_report(report=report, output_path=out)

        assert path == out
        assert path.exists()
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == "1"

    def test_parent_directory_creation(self, tmp_path: Path):
        report = self._valid_report()
        out = tmp_path / "deep" / "nested" / "summary.json"

        path = write_summary_report(report=report, output_path=out)

        assert path.exists()

    def test_invalid_report_rejected_loudly(self, tmp_path: Path):
        out = tmp_path / "summary.json"
        bad_report = {"schema_version": "1"}  # missing required fields

        with pytest.raises(ValueError, match="schema validation"):
            write_summary_report(report=bad_report, output_path=out)

    def test_output_parses_back_as_valid_json(self, tmp_path: Path):
        report = self._valid_report()
        out = tmp_path / "summary.json"
        write_summary_report(report=report, output_path=out)

        parsed = json.loads(out.read_text(encoding="utf-8"))
        validator = Draft7Validator(_load_schema())
        errors = list(validator.iter_errors(parsed))
        assert errors == []

    def test_deterministic_key_ordering(self, tmp_path: Path):
        report = self._valid_report()
        out1 = tmp_path / "s1.json"
        out2 = tmp_path / "s2.json"

        write_summary_report(report=report, output_path=out1)
        write_summary_report(report=report, output_path=out2)

        assert out1.read_text(
            encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_overwrite_existing_file(self, tmp_path: Path):
        report = self._valid_report()
        out = tmp_path / "summary.json"
        out.write_text("{}", encoding="utf-8")

        path = write_summary_report(report=report, output_path=out)

        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == "1"

    def test_directory_target_rejected(self, tmp_path: Path):
        report = self._valid_report()
        with pytest.raises(IsADirectoryError):
            write_summary_report(report=report, output_path=tmp_path)

    def test_wrong_extension_rejected(self, tmp_path: Path):
        report = self._valid_report()
        out = tmp_path / "summary.txt"
        with pytest.raises(ValueError, match=".json extension"):
            write_summary_report(report=report, output_path=out)

    def test_string_input_rejected(self, tmp_path: Path):
        out = tmp_path / "summary.json"
        with pytest.raises(TypeError, match="mapping"):
            write_summary_report(report="not a dict", output_path=out)


# ---------- Policy readiness notes edge cases ----------

class TestPolicyReadinessNotes:
    def test_vacuous_when_no_verdicts(self):
        result = _make_result(verdict_count=0)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert "vacuous" in report["policy_readiness_notes"][0].lower()

    def test_empty_matched_note(self):
        result = _make_result(verdict_count=5, matched_count=0)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert "no matched" in report["policy_readiness_notes"][0].lower()

    def test_low_match_rate_flagged(self):
        result = _make_result(
            verdict_count=10,
            matched_count=3,
            unmatched_count=7,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        notes = " ".join(report["policy_readiness_notes"]).lower()
        assert "low match rate" in notes

    def test_high_disagreement_flagged(self):
        disagreements = tuple(
            {"verdict_id": f"v-{i}", "cost_of_disagreement": 0.01}
            for i in range(4)
        )
        result = _make_result(
            disagreements=disagreements,
            verdict_count=10,
            matched_count=10,
        )
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        notes = " ".join(report["policy_readiness_notes"]).lower()
        assert "disagreement" in notes

    def test_no_anomalies_when_clean(self):
        result = _make_result(verdict_count=10, matched_count=10)
        report = build_summary_report(result, generated_at_ms=_FIXED_TS)
        assert "no anomalies" in report["policy_readiness_notes"][0].lower()
