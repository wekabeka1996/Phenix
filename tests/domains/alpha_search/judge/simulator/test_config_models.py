import pytest

from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)


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


class TestSimulatorConfig:
    def test_valid_config_loads(self):
        config = _make_config()

        assert config.enabled is True
        assert config.judge_logs_path == "logs/judge_experts"
        assert config.fee_per_cycle_bps == 25.0
        assert config.slippage_pct == 0.1

    def test_extra_fields_rejected(self):
        with pytest.raises(Exception):
            SimulatorConfig(
                enabled=True,
                judge_logs_path="logs/judge_experts",
                outcome_data_path="data/simulator/outcomes.json",
                calibration_dataset_path="artifacts/phase5_calibration.jsonl",
                summary_report_path="artifacts/phase5_summary_report.json",
                fee_per_cycle_bps=25.0,
                slippage_pct=0.1,
                unknown_field="bad",
            )

    def test_frozen_behavior_enforced(self):
        config = _make_config()

        with pytest.raises(Exception):
            config.enabled = False

    @pytest.mark.parametrize(
        "field_name",
        [
            "judge_logs_path",
            "outcome_data_path",
            "calibration_dataset_path",
            "summary_report_path",
        ],
    )
    def test_empty_path_rejected(self, field_name: str):
        payload = _make_config().model_dump()
        payload[field_name] = "   "

        with pytest.raises(ValueError, match="non-empty string"):
            SimulatorConfig(**payload)

    def test_negative_fee_rejected(self):
        payload = _make_config().model_dump()
        payload["fee_per_cycle_bps"] = -0.01

        with pytest.raises(ValueError, match="greater than or equal to 0"):
            SimulatorConfig(**payload)

    def test_negative_slippage_rejected(self):
        payload = _make_config().model_dump()
        payload["slippage_pct"] = -0.01

        with pytest.raises(ValueError, match="greater than or equal to 0"):
            SimulatorConfig(**payload)
