import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.simulator.calibration_dataset_writer import (
    build_calibration_records,
    write_calibration_dataset,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.simulator.simulator_engine import (
    CorrelatedVerdictOutcome,
    CorrelationKey,
    OutcomeRecord,
    VerdictRecord,
)

_SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/simulator/schemas/calibration_dataset_v1.json"
)


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _make_config() -> SimulatorConfig:
    return SimulatorConfig(
        enabled=True,
        judge_logs_path="logs/judge_experts",
        outcome_data_path="data/simulator/outcomes.json",
        calibration_dataset_path="artifacts/phase5_calibration.jsonl",
        summary_report_path="artifacts/phase5_summary_report.json",
        fee_per_cycle_bps=25.0,
        slippage_pct=0.1,
    )


def _make_correlation(
    *,
    verdict_id: str,
    entry_verdict: str,
    matched_trade: bool,
    entry_price: float | None,
    exit_price: float | None,
    raw_return: float | None,
    fee_cost: float | None,
    slippage_cost: float | None,
    net_return: float | None,
    confidence: float = 0.8,
    dissent_noted: bool = False,
    bar_close_ts: int = 1712000000000,
) -> CorrelatedVerdictOutcome:
    key = CorrelationKey(
        strategy_id="aurora",
        symbol="BTCUSDT",
        tf_sec=300,
        bar_close_ts=bar_close_ts,
    )
    return CorrelatedVerdictOutcome(
        verdict=VerdictRecord(
            verdict_id=verdict_id,
            correlation_key=key,
            entry_verdict=entry_verdict,
            confidence=confidence,
            dissent_noted=dissent_noted,
        ),
        outcome=OutcomeRecord(
            correlation_key=key,
            matched_trade=matched_trade,
            entry_price=entry_price,
            exit_price=exit_price,
            exit_ts_ms=1712000005000,
        ),
        side=None,
        entry_price=entry_price,
        exit_price=exit_price,
        raw_return=raw_return,
        fee_cost=fee_cost,
        slippage_cost=slippage_cost,
        net_return=net_return,
    )


class TestCalibrationSchemaAndRecords:
    def test_schema_compiles(self):
        Draft7Validator.check_schema(_load_schema())

    def test_actionable_correct_entry_case(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-long-correct",
                    entry_verdict="OPEN_LONG",
                    matched_trade=True,
                    entry_price=100.0,
                    exit_price=110.0,
                    raw_return=0.1,
                    fee_cost=0.0025,
                    slippage_cost=0.001,
                    net_return=0.0965,
                )
            ],
            disagreements=[],
            config=_make_config(),
        )

        assert len(records) == 1
        assert records[0]["optimal_action"] == "OPEN_LONG"
        assert records[0]["has_disagreement"] is False
        assert records[0]["cohort"] == "CORRECT_ENTRY"
        assert records[0]["raw_return"] == 0.1
        assert records[0]["schema_version"] == "1"

    def test_actionable_incorrect_entry_case(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-long-wrong",
                    entry_verdict="OPEN_LONG",
                    matched_trade=True,
                    entry_price=100.0,
                    exit_price=90.0,
                    raw_return=-0.1,
                    fee_cost=0.0025,
                    slippage_cost=0.001,
                    net_return=-0.1035,
                )
            ],
            disagreements=[
                {
                    "verdict_id": "v-long-wrong",
                    "verdict_action": "OPEN_LONG",
                    "optimal_action": "OPEN_SHORT",
                    "cost_of_disagreement": 0.2,
                }
            ],
            config=_make_config(),
        )

        assert records[0]["optimal_action"] == "OPEN_SHORT"
        assert records[0]["has_disagreement"] is True
        assert records[0]["cohort"] == "INCORRECT_ENTRY"

    def test_no_entry_correct_abstain_case(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-abstain-correct",
                    entry_verdict="NO_ENTRY",
                    matched_trade=False,
                    entry_price=None,
                    exit_price=None,
                    raw_return=None,
                    fee_cost=None,
                    slippage_cost=None,
                    net_return=None,
                )
            ],
            disagreements=[],
            config=_make_config(),
        )

        assert records[0]["optimal_action"] == "NO_ENTRY"
        assert records[0]["cohort"] == "CORRECT_ABSTAIN"
        assert records[0]["has_disagreement"] is False

    def test_no_entry_missed_opportunity_case(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-missed",
                    entry_verdict="NO_ENTRY",
                    matched_trade=True,
                    entry_price=100.0,
                    exit_price=110.0,
                    raw_return=None,
                    fee_cost=None,
                    slippage_cost=None,
                    net_return=None,
                )
            ],
            disagreements=[
                {
                    "verdict_id": "v-missed",
                    "verdict_action": "NO_ENTRY",
                    "optimal_action": "OPEN_LONG",
                    "cost_of_disagreement": 0.0965,
                }
            ],
            config=_make_config(),
        )

        assert records[0]["optimal_action"] == "OPEN_LONG"
        assert records[0]["cohort"] == "MISSED_OPPORTUNITY"
        assert records[0]["has_disagreement"] is True
        assert records[0]["raw_return"] is None
        assert records[0]["net_return"] is None

    def test_unknown_is_inconclusive(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-unknown",
                    entry_verdict="UNKNOWN",
                    matched_trade=True,
                    entry_price=None,
                    exit_price=None,
                    raw_return=None,
                    fee_cost=None,
                    slippage_cost=None,
                    net_return=None,
                )
            ],
            disagreements=[],
            config=_make_config(),
        )

        assert records[0]["cohort"] == "INCONCLUSIVE"
        assert records[0]["has_disagreement"] is False

    def test_suppress_is_inconclusive(self):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-suppress",
                    entry_verdict="SUPPRESS",
                    matched_trade=True,
                    entry_price=None,
                    exit_price=None,
                    raw_return=None,
                    fee_cost=None,
                    slippage_cost=None,
                    net_return=None,
                )
            ],
            disagreements=[],
            config=_make_config(),
        )

        assert records[0]["cohort"] == "INCONCLUSIVE"
        assert records[0]["has_disagreement"] is False


class TestCalibrationWriter:
    def test_writes_jsonl_successfully_and_preserves_order(self, tmp_path: Path):
        records = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-1",
                    entry_verdict="OPEN_LONG",
                    matched_trade=True,
                    entry_price=100.0,
                    exit_price=110.0,
                    raw_return=0.1,
                    fee_cost=0.0025,
                    slippage_cost=0.001,
                    net_return=0.0965,
                    bar_close_ts=1,
                ),
                _make_correlation(
                    verdict_id="v-2",
                    entry_verdict="NO_ENTRY",
                    matched_trade=False,
                    entry_price=None,
                    exit_price=None,
                    raw_return=None,
                    fee_cost=None,
                    slippage_cost=None,
                    net_return=None,
                    bar_close_ts=2,
                ),
            ],
            disagreements=[],
            config=_make_config(),
        )
        output_path = tmp_path / "nested" / "phase5_calibration.jsonl"

        written_path = write_calibration_dataset(
            records=records,
            output_path=output_path,
        )

        assert written_path == output_path
        assert output_path.exists()
        lines = output_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

        parsed = [json.loads(line) for line in lines]
        assert [record["verdict_id"] for record in parsed] == ["v-1", "v-2"]
        assert parsed[0]["cohort"] == "CORRECT_ENTRY"
        assert parsed[1]["cohort"] == "CORRECT_ABSTAIN"

    def test_parent_directory_creation_works(self, tmp_path: Path):
        record = build_calibration_records(
            correlations=[
                _make_correlation(
                    verdict_id="v-parent-dir",
                    entry_verdict="OPEN_LONG",
                    matched_trade=True,
                    entry_price=100.0,
                    exit_price=110.0,
                    raw_return=0.1,
                    fee_cost=0.0025,
                    slippage_cost=0.001,
                    net_return=0.0965,
                )
            ],
            disagreements=[],
            config=_make_config(),
        )
        output_path = tmp_path / "missing" / "dirs" / "phase5_calibration.jsonl"

        write_calibration_dataset(records=record, output_path=output_path)

        assert output_path.exists()

    def test_invalid_record_input_rejected_loudly(self, tmp_path: Path):
        output_path = tmp_path / "phase5_calibration.jsonl"

        with pytest.raises(ValueError):
            write_calibration_dataset(
                records=[{"schema_version": "1"}],
                output_path=output_path,
            )

    def test_existing_target_file_rejected_loudly(self, tmp_path: Path):
        output_path = tmp_path / "phase5_calibration.jsonl"
        output_path.write_text("already exists\n", encoding="utf-8")

        with pytest.raises(FileExistsError):
            write_calibration_dataset(records=[], output_path=output_path)
