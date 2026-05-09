from __future__ import annotations

import json
from pathlib import Path

import SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL as poc03b


def _sample_report() -> str:
    return """# SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT

## Verdict
VALIDATION_PASSED

## Summary
- total atoms: 8
- contexts tested: 2
- contexts skipped due to low support: 1
- total context evaluations: 3

## Context Evaluation Details
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=10 validation_count=11 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-16.461044 validation_net_score=-11.844887
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 8} validation_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 8}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: ETHUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=3 validation_count=3 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  train_net_score=-22.481593 validation_net_score=-2.589772
  train_outcomes={"CLEAN_LOSS": 3} validation_outcomes={"CLEAN_LOSS": 2, "GOOD_DECISION": 1}
  validation_result=CONFIRMED reason=validation_negative_profile
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.50..0.75
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=27.393798 validation_net_score=9.156211
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold

## Top Toxic Candidates
- sample
"""


def test_parse_contexts_counts_empty_validation_outcomes_without_failure() -> None:
    contexts, parser_summary = poc03b.parse_contexts(_sample_report())
    assert len(contexts) == 3
    assert parser_summary["contexts_with_empty_validation_outcomes"] == 1
    assert parser_summary["missing_required_fields"] == 0


def test_apply_stability_filter_marks_policy_too_strict_ready() -> None:
    ctx = {
        "validation_result": "CONFIRMED",
        "verdict": "POLICY_TOO_STRICT_CANDIDATE",
        "train_count": 10,
        "validation_count": 11,
        "train_net_score": -16.0,
        "validation_net_score": -11.0,
        "train_outcomes": {"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 8},
        "validation_outcomes": {"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 8},
    }
    assert poc03b.apply_stability_filter(ctx) == "READY_FOR_COUNTERFACTUAL_SIM"


def test_run_enforces_manifest_and_parse_count_guards(tmp_path: Path) -> None:
    input_report = tmp_path / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
    output_manifest = tmp_path / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    output_report = tmp_path / "SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT.md"
    input_report.write_text(_sample_report(), encoding="utf-8")
    result = poc03b.run(
        input_report=input_report,
        output_manifest=output_manifest,
        output_report=output_report,
    )
    assert result["status"] == "COMPLETED"
    assert result["parser_summary"]["parsed_contexts_total"] == 3
    assert result["manifest_total_contexts"] == 3
    manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert sum(len(items) for items in manifest.values()) == 3
    assert len(manifest["READY_FOR_COUNTERFACTUAL_SIM"]) == 1
    assert len(manifest["PROMISING_LOW_SUPPORT"]) == 1
    assert len(manifest["INCONCLUSIVE_LOW_POWER"]) == 1


def test_run_fails_when_expected_total_mismatches(tmp_path: Path) -> None:
    bad_report = _sample_report().replace("- total context evaluations: 3", "- total context evaluations: 4")
    input_report = tmp_path / "bad.md"
    input_report.write_text(bad_report, encoding="utf-8")
    result = poc03b.run(
        input_report=input_report,
        output_manifest=tmp_path / "manifest.json",
        output_report=tmp_path / "report.md",
    )
    assert result["status"] == "FAILED_CONTEXT_PARSE_COUNT_MISMATCH"
