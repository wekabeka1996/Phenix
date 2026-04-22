from __future__ import annotations

import json
from pathlib import Path

import yaml

from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    EnvelopeProvenance,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
)
from apps.reference.domains.alpha_search.judge.review.cli import EXIT_SUCCESS, main
from apps.reference.domains.alpha_search.judge.review.config_schema_validator import (
    validate_review_config_file,
)
from apps.reference.domains.alpha_search.judge.review.engine import run_review
from apps.reference.domains.alpha_search.judge.review.report_writer import (
    write_csv_rows,
    write_markdown_summary,
    write_review_bundle,
)
from apps.reference.domains.alpha_search.judge.simulator.cli import (
    load_simulator_config,
    run_from_config,
)


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, payloads: list[dict]) -> None:
    lines = [json.dumps(payload) for payload in payloads]
    path.write_text("\n".join(lines) +
                    ("\n" if lines else ""), encoding="utf-8")


def _make_expert_output(
    *,
    expert_id: str,
    entry_verdict: str,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
    confidence: float,
) -> ExpertOutput:
    signal_direction = "NEUTRAL"
    if entry_verdict == "OPEN_LONG":
        signal_direction = "LONG"
    elif entry_verdict == "OPEN_SHORT":
        signal_direction = "SHORT"
    return ExpertOutput(
        expert_id=expert_id,
        expert_version="1.0.0",
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=ts_ms,
        entry_verdict=entry_verdict,
        confidence=confidence,
        signal_direction=signal_direction,
        reasoning=["test"],
    )


def _make_chamber(
    *,
    chamber_id: str,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
    expert_outputs: list[ExpertOutput],
    consensus_direction: str | None,
    consensus_strength: float,
    admissibility: str,
) -> ChamberAggregate:
    responding_count = len(
        [eo for eo in expert_outputs if eo.confidence >
            0.0 and eo.entry_verdict != "UNKNOWN"]
    )
    return ChamberAggregate(
        chamber_id=chamber_id,
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=ts_ms,
        verdict_scope="ENTRY",
        expert_outputs=expert_outputs,
        expert_count=len(expert_outputs),
        responding_count=responding_count,
        abstaining_count=len(expert_outputs) - responding_count,
        consensus_direction=consensus_direction,
        consensus_strength=consensus_strength,
        admissibility=admissibility,
    )


def _make_envelope(
    *,
    envelope_id: str,
    strategy_id: str,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
    regime: str,
    regime_confidence: float,
    chamber: ChamberAggregate,
) -> JudgeEvidenceEnvelope:
    return JudgeEvidenceEnvelope(
        envelope_id=envelope_id,
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=ts_ms,
        verdict_scope="ENTRY",
        chamber_aggregate=chamber,
        strategy_id=strategy_id,
        regime=regime,
        regime_confidence=regime_confidence,
        features_ref=f"bar:{symbol}:{tf_sec}:{ts_ms}",
        freshness_deadline_ms=ts_ms + 30000,
        provenance=EnvelopeProvenance(
            cortex_version="phase4_shadow_v1",
            assembly_source="review-test",
        ),
    )


def _make_verdict(
    *,
    verdict_id: str,
    envelope_id: str,
    chamber_id: str,
    strategy_id: str,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
    entry_verdict: str,
    confidence: float,
) -> JudgeVerdict:
    return JudgeVerdict(
        verdict_id=verdict_id,
        envelope_id=envelope_id,
        chamber_id=chamber_id,
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=ts_ms,
        verdict_scope="ENTRY",
        entry_verdict=entry_verdict,
        suppression_reason=(
            "manual_block" if entry_verdict == "SUPPRESS" else None),
        confidence=confidence,
        reasoning=["test"],
        dissent_noted=False,
        authority_mode="shadow",
        applied=False,
        strategy_id=strategy_id,
    )


def _write_simulator_config(
    path: Path,
    *,
    judge_logs_path: Path,
    outcome_data_path: Path,
    calibration_dataset_path: Path,
    summary_report_path: Path,
) -> None:
    _write_yaml(
        path,
        {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": str(judge_logs_path),
                "outcome_data_path": str(outcome_data_path),
                "calibration_dataset_path": str(calibration_dataset_path),
                "summary_report_path": str(summary_report_path),
                "fee_per_cycle_bps": 25.0,
                "slippage_pct": 0.1,
            }
        },
    )


def _write_review_config(
    path: Path,
    *,
    simulator_config_path: Path,
    output_dir: Path,
    segment_dimensions: list[str] | None = None,
) -> None:
    _write_yaml(
        path,
        {
            "judge_review": {
                "enabled": False,
                "judge_simulator_config_path": str(simulator_config_path),
                "output_dir": str(output_dir),
                "segment_dimensions": segment_dimensions or [
                    "symbol",
                    "regime",
                    "source_file",
                ],
                "confidence_bucket_edges": [0.0, 0.25, 0.5, 0.75, 1.0],
            }
        },
    )


def _prepare_full_evidence_fixture(tmp_path: Path) -> tuple[Path, Path]:
    judge_logs_dir = tmp_path / "judge_logs"
    judge_logs_dir.mkdir(parents=True, exist_ok=True)
    outcome_path = tmp_path / "outcomes.json"
    calibration_path = tmp_path / "phase5_calibration.jsonl"
    summary_path = tmp_path / "phase5_summary_report.json"
    simulator_config_path = tmp_path / "judge_simulator.yaml"
    review_config_path = tmp_path / "judge_review.yaml"

    records = [
        {
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1712000000000,
            "matched_trade": True,
            "entry_price": 100.0,
            "exit_price": 110.0,
            "exit_ts_ms": 1712000005000,
        },
        {
            "strategy_id": "aurora",
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1712000001000,
            "matched_trade": False,
        },
        {
            "strategy_id": "aurora",
            "symbol": "BNBUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1712000002000,
            "matched_trade": True,
            "entry_price": 100.0,
            "exit_price": 90.0,
            "exit_ts_ms": 1712000007000,
        },
    ]
    _write_json(outcome_path, {"schema_version": "1", "outcomes": records})

    btc_experts = [
        _make_expert_output(
            expert_id="signal",
            entry_verdict="OPEN_LONG",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1712000000000,
            confidence=0.82,
        )
    ]
    eth_experts = [
        _make_expert_output(
            expert_id="signal",
            entry_verdict="UNKNOWN",
            symbol="ETHUSDT",
            tf_sec=300,
            ts_ms=1712000001000,
            confidence=0.2,
        )
    ]
    bnb_experts = [
        _make_expert_output(
            expert_id="signal",
            entry_verdict="OPEN_SHORT",
            symbol="BNBUSDT",
            tf_sec=300,
            ts_ms=1712000002000,
            confidence=0.91,
        )
    ]

    btc_chamber = _make_chamber(
        chamber_id="ch-btc",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000000,
        expert_outputs=btc_experts,
        consensus_direction="LONG",
        consensus_strength=0.82,
        admissibility="ADMISSIBLE",
    )
    eth_chamber = _make_chamber(
        chamber_id="ch-eth",
        symbol="ETHUSDT",
        tf_sec=300,
        ts_ms=1712000001000,
        expert_outputs=eth_experts,
        consensus_direction=None,
        consensus_strength=0.0,
        admissibility="QUORUM_INSUFFICIENT",
    )
    bnb_chamber = _make_chamber(
        chamber_id="ch-bnb",
        symbol="BNBUSDT",
        tf_sec=300,
        ts_ms=1712000002000,
        expert_outputs=bnb_experts,
        consensus_direction="SHORT",
        consensus_strength=0.91,
        admissibility="ADMISSIBLE",
    )

    _write_jsonl(
        judge_logs_dir / "chamber_shadow.jsonl",
        [
            btc_chamber.model_dump(mode="json"),
            eth_chamber.model_dump(mode="json"),
            bnb_chamber.model_dump(mode="json"),
        ],
    )

    _write_jsonl(
        judge_logs_dir / "envelope_shadow.jsonl",
        [
            _make_envelope(
                envelope_id="env-btc",
                strategy_id="aurora",
                symbol="BTCUSDT",
                tf_sec=300,
                ts_ms=1712000000000,
                regime="TREND_UP",
                regime_confidence=0.78,
                chamber=btc_chamber,
            ).model_dump(mode="json"),
            _make_envelope(
                envelope_id="env-eth",
                strategy_id="aurora",
                symbol="ETHUSDT",
                tf_sec=300,
                ts_ms=1712000001000,
                regime="TREND_DOWN",
                regime_confidence=0.66,
                chamber=eth_chamber,
            ).model_dump(mode="json"),
            _make_envelope(
                envelope_id="env-bnb",
                strategy_id="aurora",
                symbol="BNBUSDT",
                tf_sec=300,
                ts_ms=1712000002000,
                regime="TREND_DOWN",
                regime_confidence=0.91,
                chamber=bnb_chamber,
            ).model_dump(mode="json"),
        ],
    )

    _write_jsonl(
        judge_logs_dir / "verdict_shadow.jsonl",
        [
            _make_verdict(
                verdict_id="v-btc",
                envelope_id="env-btc",
                chamber_id="ch-btc",
                strategy_id="aurora",
                symbol="BTCUSDT",
                tf_sec=300,
                ts_ms=1712000000000,
                entry_verdict="OPEN_LONG",
                confidence=0.82,
            ).model_dump(mode="json"),
            _make_verdict(
                verdict_id="v-eth",
                envelope_id="env-eth",
                chamber_id="ch-eth",
                strategy_id="aurora",
                symbol="ETHUSDT",
                tf_sec=300,
                ts_ms=1712000001000,
                entry_verdict="UNKNOWN",
                confidence=0.2,
            ).model_dump(mode="json"),
            _make_verdict(
                verdict_id="v-bnb",
                envelope_id="env-bnb",
                chamber_id="ch-bnb",
                strategy_id="aurora",
                symbol="BNBUSDT",
                tf_sec=300,
                ts_ms=1712000002000,
                entry_verdict="SUPPRESS",
                confidence=0.91,
            ).model_dump(mode="json"),
        ],
    )

    _write_simulator_config(
        simulator_config_path,
        judge_logs_path=judge_logs_dir,
        outcome_data_path=outcome_path,
        calibration_dataset_path=calibration_path,
        summary_report_path=summary_path,
    )
    _write_review_config(
        review_config_path,
        simulator_config_path=simulator_config_path,
        output_dir=tmp_path / "judge_review_artifacts",
    )
    run_from_config(load_simulator_config(simulator_config_path))
    return simulator_config_path, review_config_path


def _prepare_partial_fixture(tmp_path: Path) -> Path:
    judge_logs_dir = tmp_path / "judge_logs"
    judge_logs_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = judge_logs_dir / "verdict_shadow.jsonl"
    outcome_path = tmp_path / "outcomes.json"
    simulator_config_path = tmp_path / "judge_simulator.yaml"
    review_config_path = tmp_path / "judge_review.yaml"

    _write_json(
        outcome_path,
        {
            "schema_version": "1",
            "outcomes": [
                {
                    "strategy_id": "aurora",
                    "symbol": "SOLUSDT",
                    "tf_sec": 300,
                    "bar_close_ts": 1712001000000,
                    "matched_trade": True,
                    "entry_price": 50.0,
                    "exit_price": 45.0,
                    "exit_ts_ms": 1712001005000,
                }
            ],
        },
    )
    _write_jsonl(
        verdict_path,
        [
            _make_verdict(
                verdict_id="v-sol",
                envelope_id="env-sol",
                chamber_id="ch-sol",
                strategy_id="aurora",
                symbol="SOLUSDT",
                tf_sec=300,
                ts_ms=1712001000000,
                entry_verdict="OPEN_SHORT",
                confidence=0.88,
            ).model_dump(mode="json")
        ],
    )
    _write_simulator_config(
        simulator_config_path,
        judge_logs_path=judge_logs_dir,
        outcome_data_path=outcome_path,
        calibration_dataset_path=tmp_path / "phase5_calibration.jsonl",
        summary_report_path=tmp_path / "phase5_summary_report.json",
    )
    _write_review_config(
        review_config_path,
        simulator_config_path=simulator_config_path,
        output_dir=tmp_path / "judge_review_artifacts",
    )
    return review_config_path


def test_run_review_generates_bundle_with_segmented_outputs(tmp_path: Path):
    _, review_config_path = _prepare_full_evidence_fixture(tmp_path)
    config = validate_review_config_file(review_config_path)

    result = run_review(config)
    bundle = dict(result["bundle"])

    assert bundle["no_automatic_promotion_verdict"] is True
    assert "promotion_verdict" not in bundle
    assert bundle["input_coverage"]["entry_verdict_count"] == 3
    assert bundle["baseline_availability"]["incumbent_only"]["status"] == "unavailable"
    assert any(row["segment_type"] ==
               "symbol" for row in result["comparison_rows"])
    assert any(row["segment_type"] ==
               "regime" for row in result["comparison_rows"])
    assert any(row["suppress_count"] >=
               1 for row in result["suppression_rows"])
    assert any(row["surface"] ==
               "entry_chamber" for row in result["surface_rows"])


def test_run_review_marks_partial_input_coverage_without_chamber_or_envelope(tmp_path: Path):
    review_config_path = _prepare_partial_fixture(tmp_path)
    config = validate_review_config_file(review_config_path)

    result = run_review(config)
    bundle = dict(result["bundle"])

    assert "chamber_comparison_unavailable" in bundle["not_enough_evidence_flags"]
    assert "regime_segmentation_unavailable" in bundle["not_enough_evidence_flags"]
    assert bundle["review_surface_support"]["entry_chamber"]["status"] == "insufficient"
    assert bundle["input_coverage"]["matched_count"] == 1


def test_cli_writes_artifacts_and_preserves_no_promotion_boundary(tmp_path: Path):
    _, review_config_path = _prepare_full_evidence_fixture(tmp_path)

    exit_code = main(["--config", str(review_config_path)])

    assert exit_code == EXIT_SUCCESS
    output_dir = tmp_path / "judge_review_artifacts"
    bundle_path = output_dir / "review_bundle.json"
    summary_path = output_dir / "review_summary.md"
    assert bundle_path.is_file()
    assert summary_path.is_file()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["no_automatic_promotion_verdict"] is True
    assert "promotion_verdict" not in bundle
    assert "This tooling does not produce a promotion verdict." in summary_path.read_text(
        encoding="utf-8")

    fieldnames = result_fieldnames = {
        "comparison_rows": [
            "segment_type",
            "segment_value",
            "entry_verdict_count",
            "matched_outcome_count",
            "chamber_only_available_count",
            "final_judge_available_count",
            "incumbent_available",
            "null_baseline_available_count",
            "final_avg_modeled_net_return",
            "chamber_avg_modeled_net_return",
            "null_baseline_avg_modeled_net_return",
            "final_minus_chamber_avg_modeled_net_return",
            "final_minus_null_avg_modeled_net_return",
            "final_vs_chamber_action_diff_count",
            "final_vs_chamber_action_same_count",
            "final_vs_chamber_avg_confidence_delta",
            "final_unknown_count",
            "final_suppress_count",
        ],
        "suppression_rows": [
            "segment_type",
            "segment_value",
            "entry_verdict_count",
            "unknown_count",
            "unknown_rate",
            "unknown_total_opportunity_cost",
            "unknown_avg_opportunity_cost",
            "suppress_count",
            "suppress_rate",
            "suppress_total_opportunity_cost",
            "suppress_avg_opportunity_cost",
            "no_entry_count",
            "chamber_inadmissible_count",
            "chamber_quorum_insufficient_count",
        ],
        "disagreement_rows": [
            "segment_type",
            "segment_value",
            "verdict_action",
            "optimal_action",
            "count",
            "avg_cost_of_disagreement",
            "total_cost_of_disagreement",
            "avg_confidence",
            "dissent_noted_rate",
        ],
        "calibration_rows": [
            "segment_type",
            "segment_value",
            "confidence_bucket",
            "record_count",
            "avg_confidence",
            "avg_net_return",
            "correct_entry_count",
            "incorrect_entry_count",
            "correct_abstain_count",
            "missed_opportunity_count",
            "inconclusive_count",
            "disagreement_count",
        ],
        "surface_rows": ["surface", "status", "observed_count", "note"],
    }
    # Smoke-write through the public writer surface using the already generated bundle.
    bundle_out = tmp_path / "writer_smoke" / "bundle.json"
    write_review_bundle(bundle, bundle_out)
    write_markdown_summary(summary_path.read_text(
        encoding="utf-8"), tmp_path / "writer_smoke" / "summary.md")
    write_csv_rows([], tmp_path / "writer_smoke" / "surface.csv",
                   fieldnames=result_fieldnames["surface_rows"])
    assert bundle_out.is_file()
