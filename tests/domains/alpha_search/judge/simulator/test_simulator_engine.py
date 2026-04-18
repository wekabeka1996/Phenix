import json
import logging
import math
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    EnvelopeProvenance,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.simulator.simulator_engine import (
    correlate_verdicts_to_outcomes,
    enrich_correlations_with_economics,
    load_outcome_data,
    load_verdict_records,
    run_simulation,
)

_SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/simulator/schemas/outcome_input_v1.json"
)


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _make_verdict(
    *,
    verdict_id: str,
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    entry_verdict: str = "OPEN_LONG",
    confidence: float = 0.8,
    dissent_noted: bool = False,
) -> JudgeVerdict:
    suppression_reason = None
    if entry_verdict == "SUPPRESS":
        suppression_reason = "test-suppressed"

    return JudgeVerdict(
        verdict_id=verdict_id,
        envelope_id=f"env-{verdict_id}",
        chamber_id=f"ch-{verdict_id}",
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=bar_close_ts,
        verdict_scope="ENTRY",
        entry_verdict=entry_verdict,
        suppression_reason=suppression_reason,
        confidence=confidence,
        reasoning=["test"],
        dissent_noted=dissent_noted,
        authority_mode="shadow",
        applied=False,
        strategy_id=strategy_id,
    )


def _make_expert_output(
    *,
    expert_id: str,
    entry_verdict: str,
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    confidence: float = 0.8,
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
        ts_ms=bar_close_ts,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=confidence,
        signal_direction=signal_direction,
        reasoning=["test"],
    )


def _make_envelope(
    *,
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    expert_outputs: list[ExpertOutput] | None = None,
) -> JudgeEvidenceEnvelope:
    if expert_outputs is None:
        expert_outputs = [
            _make_expert_output(
                expert_id="judge.signal_weights_v1",
                entry_verdict="OPEN_LONG",
                symbol=symbol,
                tf_sec=tf_sec,
                bar_close_ts=bar_close_ts,
            )
        ]

    chamber = ChamberAggregate(
        chamber_id=f"ch-{symbol}-{bar_close_ts}",
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=bar_close_ts,
        verdict_scope="ENTRY",
        expert_outputs=expert_outputs,
        expert_count=len(expert_outputs),
        responding_count=len(expert_outputs),
        abstaining_count=0,
        consensus_direction="SPLIT" if len(expert_outputs) > 1 else "LONG",
        consensus_strength=0.5 if len(expert_outputs) > 1 else 0.8,
        admissibility="ADMISSIBLE",
    )
    return JudgeEvidenceEnvelope(
        envelope_id=f"env-{symbol}-{bar_close_ts}",
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=bar_close_ts,
        verdict_scope="ENTRY",
        chamber_aggregate=chamber,
        strategy_id=strategy_id,
        regime=None,
        regime_confidence=None,
        features_ref=f"bar:{symbol}:{tf_sec}:{bar_close_ts}",
        freshness_deadline_ms=bar_close_ts + 30000,
        provenance=EnvelopeProvenance(
            cortex_version="phase4_shadow_v1",
            assembly_source="alpha_search_backtest_plugin",
        ),
    )


def _make_outcome(
    *,
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    matched_trade: bool = True,
    entry_price: float = 100.0,
    exit_price: float = 110.0,
    exit_ts_ms: int = 1712000005000,
) -> dict:
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "matched_trade": matched_trade,
    }
    if matched_trade:
        payload.update(
            {
                "entry_price": entry_price,
                "exit_price": exit_price,
                "exit_ts_ms": exit_ts_ms,
            }
        )
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) +
                    ("\n" if lines else ""), encoding="utf-8")


def _make_config(verdict_path: Path, outcome_path: Path) -> SimulatorConfig:
    return SimulatorConfig(
        enabled=True,
        judge_logs_path=str(verdict_path),
        outcome_data_path=str(outcome_path),
        calibration_dataset_path="artifacts/phase5_calibration.jsonl",
        summary_report_path="artifacts/phase5_summary_report.json",
        fee_per_cycle_bps=25.0,
        slippage_pct=0.1,
    )


class TestOutcomeSchemaAndLoader:
    def test_schema_compiles(self):
        Draft7Validator.check_schema(_load_schema())

    def test_valid_outcome_input_accepted(self, tmp_path: Path):
        outcome_path = tmp_path / "outcomes.json"
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [_make_outcome()],
            },
        )

        outcomes = load_outcome_data(outcome_path)

        assert len(outcomes) == 1
        assert outcomes[0].correlation_key.strategy_id == "aurora"
        assert outcomes[0].correlation_key.bar_close_ts == 1712000000000

    def test_missing_required_identity_field_rejected(self, tmp_path: Path):
        outcome = _make_outcome()
        del outcome["strategy_id"]
        outcome_path = tmp_path / "outcomes.json"
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [outcome],
            },
        )

        with pytest.raises(ValueError, match="schema validation"):
            load_outcome_data(outcome_path)

    def test_malformed_outcome_payload_rejected_cleanly(self, tmp_path: Path):
        outcome_path = tmp_path / "outcomes.json"
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    {
                        "strategy_id": "aurora",
                        "symbol": "BTCUSDT",
                        "tf_sec": 300,
                        "bar_close_ts": 1712000000000,
                        "matched_trade": True,
                        "entry_price": 100.0,
                    }
                ],
            },
        )

        with pytest.raises(ValueError, match="schema validation"):
            load_outcome_data(outcome_path)


class TestVerdictLoader:
    def test_valid_jsonl_parsed(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        verdicts = [
            _make_verdict(verdict_id="v-1").model_dump_json(),
            _make_verdict(verdict_id="v-2",
                          entry_verdict="OPEN_SHORT").model_dump_json(),
        ]
        _write_jsonl(verdict_path, verdicts)

        loaded = load_verdict_records(verdict_path)

        assert len(loaded) == 2
        assert loaded[0].verdict_id == "v-1"
        assert loaded[1].entry_verdict == "OPEN_SHORT"

    def test_malformed_lines_skipped_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        valid_verdict = _make_verdict(verdict_id="v-1").model_dump_json()
        invalid_verdict = json.dumps({"verdict_id": "missing-fields"})
        _write_jsonl(
            verdict_path,
            [
                valid_verdict,
                "{not-json}",
                invalid_verdict,
            ],
        )

        with caplog.at_level(logging.WARNING):
            loaded = load_verdict_records(verdict_path)

        assert len(loaded) == 1
        assert "Skipping malformed verdict JSONL line" in caplog.text
        assert "Skipping invalid verdict payload" in caplog.text

    def test_empty_file_handled_safely(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        _write_jsonl(verdict_path, [])

        loaded = load_verdict_records(verdict_path)

        assert loaded == []


class TestCorrelation:
    def test_exact_key_match_produces_matched_record(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(verdict_path, [_make_verdict(
            verdict_id="v-1").model_dump_json()])
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [_make_outcome()]},
        )

        verdicts = load_verdict_records(verdict_path)
        outcomes = load_outcome_data(outcome_path)
        correlations = correlate_verdicts_to_outcomes(verdicts, outcomes)

        assert len(correlations) == 1
        assert correlations[0].outcome is not None
        assert correlations[0].outcome.correlation_key == correlations[0].verdict.correlation_key

    @pytest.mark.parametrize(
        ("field_name", "field_value"),
        [
            ("strategy_id", "other_strategy"),
            ("symbol", "ETHUSDT"),
            ("tf_sec", 60),
            ("bar_close_ts", 1712000009999),
        ],
    )
    def test_mismatch_by_identity_field_does_not_match(
        self,
        tmp_path: Path,
        field_name: str,
        field_value: object,
    ):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(verdict_path, [_make_verdict(
            verdict_id="v-1").model_dump_json()])
        outcome = _make_outcome()
        outcome[field_name] = field_value
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [outcome]},
        )

        verdicts = load_verdict_records(verdict_path)
        outcomes = load_outcome_data(outcome_path)
        correlations = correlate_verdicts_to_outcomes(verdicts, outcomes)

        assert len(correlations) == 1
        assert correlations[0].outcome is None

    def test_duplicate_verdict_keys_are_handled_deterministically(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [
                _make_verdict(verdict_id="v-1").model_dump_json(),
                _make_verdict(verdict_id="v-2").model_dump_json(),
            ],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [_make_outcome()]},
        )

        verdicts = load_verdict_records(verdict_path)
        outcomes = load_outcome_data(outcome_path)
        with caplog.at_level(logging.WARNING):
            correlations = correlate_verdicts_to_outcomes(verdicts, outcomes)

        assert [correlation.verdict.verdict_id for correlation in correlations] == [
            "v-1", "v-2"]
        assert all(
            correlation.outcome is not None for correlation in correlations)
        assert "Duplicate verdict correlation key encountered" in caplog.text

    def test_duplicate_outcome_keys_are_handled_deterministically(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(verdict_path, [_make_verdict(
            verdict_id="v-1").model_dump_json()])
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(exit_price=110.0),
                    _make_outcome(exit_price=90.0),
                ],
            },
        )

        verdicts = load_verdict_records(verdict_path)
        outcomes = load_outcome_data(outcome_path)
        with caplog.at_level(logging.WARNING):
            correlations = correlate_verdicts_to_outcomes(verdicts, outcomes)

        assert len(correlations) == 1
        assert correlations[0].outcome is not None
        assert correlations[0].outcome.exit_price == 110.0
        assert "Duplicate outcome correlation key encountered" in caplog.text


class TestMetricsAndSimulationResult:
    def test_simulation_result_includes_disagreements_and_expert_accuracy(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        envelope_path = tmp_path / "envelope_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [
                _make_verdict(
                    verdict_id="v-long",
                    entry_verdict="OPEN_LONG",
                    bar_close_ts=1,
                    dissent_noted=True,
                ).model_dump_json()
            ],
        )
        _write_jsonl(
            envelope_path,
            [
                _make_envelope(
                    bar_close_ts=1,
                    expert_outputs=[
                        _make_expert_output(
                            expert_id="judge.signal_weights_v1",
                            entry_verdict="OPEN_LONG",
                            bar_close_ts=1,
                        ),
                        _make_expert_output(
                            expert_id="judge.feature_neutrals_v1",
                            entry_verdict="OPEN_SHORT",
                            bar_close_ts=1,
                        ),
                    ],
                ).model_dump_json()
            ],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(
                        bar_close_ts=1,
                        matched_trade=True,
                        entry_price=100.0,
                        exit_price=90.0,
                    )
                ],
            },
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        assert len(result.disagreements) == 1
        disagreement = result.disagreements[0]
        assert disagreement["verdict_id"] == "v-long"
        assert disagreement["verdict_action"] == "OPEN_LONG"
        assert disagreement["optimal_action"] == "OPEN_SHORT"
        assert disagreement["dissent_noted"] is True
        assert math.isclose(disagreement["cost_of_disagreement"], 0.2)

        assert len(result.expert_accuracy_records) == 2
        assert result.expert_accuracy_records[0]["expert_id"] == "judge.signal_weights_v1"
        assert result.expert_accuracy_records[0]["is_correct"] is False
        assert result.expert_accuracy_records[1]["expert_id"] == "judge.feature_neutrals_v1"
        assert result.expert_accuracy_records[1]["is_correct"] is True

        summary = result.expert_accuracy_summary
        assert summary["total_count"] == 2
        assert summary["correct_count"] == 1
        assert summary["accuracy_rate"] == 0.5
        assert result.correlations[0].net_return is not None
        assert len(result.calibration_records) == 1
        assert result.calibration_records[0]["verdict_id"] == "v-long"
        assert result.calibration_records[0]["optimal_action"] == "OPEN_SHORT"
        assert result.calibration_records[0]["has_disagreement"] is True
        assert result.calibration_records[0]["cohort"] == "INCORRECT_ENTRY"

    def test_simulation_result_includes_empty_expert_accuracy_when_envelope_missing(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-long",
                           bar_close_ts=1).model_dump_json()],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(bar_close_ts=1, matched_trade=True,
                                  entry_price=100.0, exit_price=110.0)
                ],
            },
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        assert result.expert_accuracy_records == ()
        assert result.expert_accuracy_summary["total_count"] == 0
        assert result.expert_accuracy_summary["correct_count"] == 0
        assert result.expert_accuracy_summary["accuracy_rate"] is None
        assert result.expert_accuracy_summary["by_expert"] == {}

    def test_unknown_verdict_does_not_fabricate_disagreement(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-unknown", entry_verdict="UNKNOWN",
                           bar_close_ts=1).model_dump_json()],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(bar_close_ts=1, matched_trade=True,
                                  entry_price=100.0, exit_price=110.0)
                ],
            },
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        assert result.disagreements == ()
        assert result.correlations[0].net_return is None
        assert len(result.calibration_records) == 1
        assert result.calibration_records[0]["cohort"] == "INCONCLUSIVE"

    def test_no_entry_disagreement_record_emitted_when_long_is_optimal(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-no-entry", entry_verdict="NO_ENTRY",
                           bar_close_ts=1).model_dump_json()],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(bar_close_ts=1, matched_trade=True,
                                  entry_price=100.0, exit_price=110.0)
                ],
            },
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        assert len(result.disagreements) == 1
        assert result.disagreements[0]["verdict_action"] == "NO_ENTRY"
        assert result.disagreements[0]["optimal_action"] == "OPEN_LONG"
        assert math.isclose(
            result.disagreements[0]["cost_of_disagreement"], 0.0965)

    def test_matched_open_long_gets_economic_fields(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-long",
                           entry_verdict="OPEN_LONG").model_dump_json()],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [
                _make_outcome(entry_price=100.0, exit_price=110.0)]},
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        correlation = result.correlations[0]
        assert correlation.side == "LONG"
        assert correlation.entry_price == 100.0
        assert correlation.exit_price == 110.0
        assert math.isclose(correlation.raw_return, 0.1)
        assert math.isclose(correlation.fee_cost, 0.0025)
        assert math.isclose(correlation.slippage_cost, 0.001)
        assert math.isclose(correlation.net_return, 0.0965)

    def test_matched_open_short_gets_economic_fields(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-short",
                           entry_verdict="OPEN_SHORT").model_dump_json()],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [
                _make_outcome(entry_price=100.0, exit_price=90.0)]},
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        correlation = result.correlations[0]
        assert correlation.side == "SHORT"
        assert correlation.entry_price == 100.0
        assert correlation.exit_price == 90.0
        assert math.isclose(correlation.raw_return, 0.1)
        assert math.isclose(correlation.fee_cost, 0.0025)
        assert math.isclose(correlation.slippage_cost, 0.001)
        assert math.isclose(correlation.net_return, 0.0965)

    def test_matched_no_entry_does_not_fabricate_economics(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-no-entry",
                           entry_verdict="NO_ENTRY").model_dump_json()],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [_make_outcome(
                matched_trade=True, entry_price=100.0, exit_price=110.0)]},
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        correlation = result.correlations[0]
        assert correlation.outcome is not None
        assert correlation.side is None
        assert correlation.entry_price is None
        assert correlation.exit_price is None
        assert correlation.raw_return is None
        assert correlation.fee_cost is None
        assert correlation.slippage_cost is None
        assert correlation.net_return is None
        assert len(result.calibration_records) == 1
        assert result.calibration_records[0]["raw_return"] is None
        assert result.calibration_records[0]["fee_cost"] is None
        assert result.calibration_records[0]["slippage_cost"] is None
        assert result.calibration_records[0]["net_return"] is None
        assert result.calibration_records[0]["cohort"] == "MISSED_OPPORTUNITY"

    def test_matched_unknown_does_not_fabricate_economics(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-unknown",
                           entry_verdict="UNKNOWN").model_dump_json()],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [_make_outcome(
                matched_trade=True, entry_price=100.0, exit_price=110.0)]},
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        correlation = result.correlations[0]
        assert correlation.outcome is not None
        assert correlation.side is None
        assert correlation.entry_price is None
        assert correlation.exit_price is None
        assert correlation.raw_return is None
        assert correlation.fee_cost is None
        assert correlation.slippage_cost is None
        assert correlation.net_return is None

    def test_unmatched_verdict_remains_unmatched(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [_make_verdict(verdict_id="v-unmatched",
                           entry_verdict="OPEN_LONG").model_dump_json()],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [
                _make_outcome(bar_close_ts=1712000009999)]},
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        correlation = result.correlations[0]
        assert correlation.outcome is None
        assert correlation.net_return is None

    def test_deterministic_behavior_preserved(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [
                _make_verdict(verdict_id="v-1", entry_verdict="OPEN_LONG",
                              bar_close_ts=1).model_dump_json(),
                _make_verdict(verdict_id="v-2", entry_verdict="OPEN_SHORT",
                              bar_close_ts=2).model_dump_json(),
            ],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(bar_close_ts=1, matched_trade=True,
                                  entry_price=100.0, exit_price=110.0),
                    _make_outcome(bar_close_ts=2, matched_trade=True,
                                  entry_price=100.0, exit_price=90.0),
                ],
            },
        )
        config = _make_config(verdict_path, outcome_path)

        first = run_simulation(config)
        second = run_simulation(config)

        assert first == second

    def test_matched_unmatched_counts_and_accuracy_summary(self, tmp_path: Path):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [
                _make_verdict(verdict_id="v-long", entry_verdict="OPEN_LONG",
                              bar_close_ts=1).model_dump_json(),
                _make_verdict(verdict_id="v-short", entry_verdict="OPEN_SHORT",
                              bar_close_ts=2).model_dump_json(),
                _make_verdict(verdict_id="v-no-entry", entry_verdict="NO_ENTRY",
                              bar_close_ts=3).model_dump_json(),
                _make_verdict(verdict_id="v-suppress", entry_verdict="SUPPRESS",
                              bar_close_ts=4).model_dump_json(),
                _make_verdict(verdict_id="v-unmatched",
                              entry_verdict="OPEN_LONG", bar_close_ts=5).model_dump_json(),
            ],
        )
        _write_json(
            outcome_path,
            {
                "schema_version": "1",
                "outcomes": [
                    _make_outcome(bar_close_ts=1, matched_trade=True,
                                  entry_price=100.0, exit_price=110.0),
                    _make_outcome(bar_close_ts=2, matched_trade=True,
                                  entry_price=100.0, exit_price=90.0),
                    _make_outcome(bar_close_ts=3, matched_trade=False),
                    _make_outcome(bar_close_ts=4, matched_trade=True,
                                  entry_price=100.0, exit_price=105.0),
                ],
            },
        )

        result = run_simulation(_make_config(verdict_path, outcome_path))

        assert result.total_verdict_records_loaded == 5
        assert result.total_outcome_records_loaded == 4
        assert result.matched_count == 4
        assert result.unmatched_count == 1

        summary = result.accuracy_summary
        assert summary.evaluated_count == 4
        assert summary.correct_count == 3
        assert summary.incorrect_count == 1
        assert summary.skipped_count == 0
        assert summary.by_verdict["OPEN_LONG"].correct_count == 1
        assert summary.by_verdict["OPEN_SHORT"].correct_count == 1
        assert summary.by_verdict["NO_ENTRY"].correct_count == 1
        assert summary.by_verdict["SUPPRESS"].incorrect_count == 1
        assert summary.by_verdict["SUPPRESS"].accuracy == 0.0
        assert result.correlations[0].net_return is not None
        assert result.correlations[1].net_return is not None
        assert result.correlations[2].net_return is None
        assert result.correlations[3].net_return is None

    def test_run_simulation_does_not_crash_on_malformed_jsonl(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ):
        verdict_path = tmp_path / "verdict_BTCUSDT.jsonl"
        outcome_path = tmp_path / "outcomes.json"
        _write_jsonl(
            verdict_path,
            [
                _make_verdict(verdict_id="v-1").model_dump_json(),
                "{broken-json}",
            ],
        )
        _write_json(
            outcome_path,
            {"schema_version": "1", "outcomes": [_make_outcome()]},
        )

        with caplog.at_level(logging.WARNING):
            result = run_simulation(_make_config(verdict_path, outcome_path))

        assert result.total_verdict_records_loaded == 1
        assert result.matched_count == 1
        assert result.unmatched_count == 0
        assert result.correlations[0].net_return is not None
        assert len(result.calibration_records) == 1
        assert "Skipping malformed verdict JSONL line" in caplog.text
