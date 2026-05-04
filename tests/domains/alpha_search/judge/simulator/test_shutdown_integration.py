"""Phase 5 Package 5G — shutdown integration tests.

Tests that backtest_plugin.shutdown() correctly invokes (or skips)
the offline simulator pipeline based on config gating, and that
failures are handled gracefully (fail-closed, no crash).
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    SimulatorShutdownExportConfig,
)


# ── helpers ──────────────────────────────────────────────────────────


def _make_plugin(
    simulator_shutdown_export: SimulatorShutdownExportConfig | None = None,
) -> AlphaSearchBacktestPlugin:
    """Build a minimal plugin with stubbed event bus for shutdown tests."""
    bus = MagicMock()
    bus.subscribe = MagicMock()

    cfg = AlphaSearchConfig(
        enabled=False,
        shadow_mode=True,
        simulator_shutdown_export=simulator_shutdown_export,
    )
    plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)
    return plugin


def _write_judge_simulator_yaml(
    path: Path,
    *,
    enabled: bool = True,
    judge_logs_path: str = "./logs/judge_experts",
    outcome_data_path: str = "./data/simulator/outcomes.json",
    calibration_dataset_path: str = "./artifacts/phase5_calibration.jsonl",
    summary_report_path: str = "./artifacts/phase5_summary_report.json",
) -> Path:
    """Write a judge_simulator.yaml at *path*."""
    data = {
        "judge_simulator": {
            "enabled": enabled,
            "judge_logs_path": judge_logs_path,
            "outcome_data_path": outcome_data_path,
            "calibration_dataset_path": calibration_dataset_path,
            "summary_report_path": summary_report_path,
            "fee_per_cycle_bps": 25,
            "slippage_pct": 0.1,
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


# ════════════════════════════════════════════════════════════════════
# A. Config gating
# ════════════════════════════════════════════════════════════════════


class TestConfigGating:
    """Prove that the config gate correctly enables/disables the path."""

    def test_disabled_config_no_simulator_invocation(self):
        """simulator_shutdown_export.enabled=False → no simulator call."""
        plugin = _make_plugin(
            SimulatorShutdownExportConfig(enabled=False, config_path="x.yaml")
        )
        with patch(
            "apps.reference.domains.alpha_search.backtest_plugin"
            ".AlphaSearchBacktestPlugin._run_simulator_shutdown_export",
            wraps=plugin._run_simulator_shutdown_export,
        ) as wrapped:
            plugin.shutdown()
            wrapped.assert_called_once()

        # Deeper: the actual import should NOT be reached
        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.load_simulator_config"
        ) as mock_load:
            plugin._run_simulator_shutdown_export()
            mock_load.assert_not_called()

    def test_none_config_no_simulator_invocation(self):
        """simulator_shutdown_export=None → no simulator call."""
        plugin = _make_plugin(simulator_shutdown_export=None)
        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.load_simulator_config"
        ) as mock_load:
            plugin._run_simulator_shutdown_export()
            mock_load.assert_not_called()

    def test_enabled_config_invokes_simulator_path(self, tmp_path):
        """enabled=True + valid config → load_simulator_config called."""
        cfg_path = tmp_path / "judge_simulator.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                total_verdict_records_loaded=5,
                total_outcome_records_loaded=3,
                matched_count=2,
            )
            plugin._run_simulator_shutdown_export()
            mock_run.assert_called_once()

    def test_enabled_with_empty_config_path_raises_validation(self):
        """enabled=True + empty config_path → pydantic validation error."""
        with pytest.raises(ValueError, match="non-empty"):
            SimulatorShutdownExportConfig(enabled=True, config_path="")

    def test_enabled_with_whitespace_config_path_raises_validation(self):
        """enabled=True + whitespace-only path → validation error."""
        with pytest.raises(ValueError, match="non-empty"):
            SimulatorShutdownExportConfig(enabled=True, config_path="   ")


# ════════════════════════════════════════════════════════════════════
# B. Shutdown integration
# ════════════════════════════════════════════════════════════════════


class TestShutdownIntegration:
    """Prove the happy-path shutdown orchestration."""

    def test_shutdown_invokes_simulator_exactly_once(self, tmp_path):
        """run_from_config must be called exactly once per shutdown."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                total_verdict_records_loaded=10,
                total_outcome_records_loaded=8,
                matched_count=6,
            )
            plugin.shutdown()
            assert mock_run.call_count == 1

    def test_shutdown_passes_loaded_config_to_run(self, tmp_path):
        """The SimulatorConfig loaded from YAML is passed to run_from_config."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(
            cfg_path,
            judge_logs_path="./custom/logs",
            outcome_data_path="./custom/outcomes.json",
        )

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                total_verdict_records_loaded=0,
                total_outcome_records_loaded=0,
                matched_count=0,
            )
            plugin._run_simulator_shutdown_export()
            called_cfg = mock_run.call_args[0][0]
            assert called_cfg.judge_logs_path == "./custom/logs"
            assert called_cfg.outcome_data_path == "./custom/outcomes.json"

    def test_simulator_disabled_in_yaml_skips_run(self, tmp_path):
        """If judge_simulator.yaml has enabled=False, run_from_config is NOT called."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path, enabled=False)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config"
        ) as mock_run:
            plugin._run_simulator_shutdown_export()
            mock_run.assert_not_called()

    def test_no_duplicate_invocations_on_repeated_shutdown(self, tmp_path):
        """Calling shutdown twice still invokes simulator once per call — no state leak."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                total_verdict_records_loaded=1,
                total_outcome_records_loaded=1,
                matched_count=1,
            )
            plugin.shutdown()
            plugin.shutdown()
            # Each shutdown call invokes once — deterministic, no accumulation
            assert mock_run.call_count == 2


# ════════════════════════════════════════════════════════════════════
# C. Failure behavior
# ════════════════════════════════════════════════════════════════════


class TestFailureBehavior:
    """Prove that failures are handled gracefully (logged, not crashed)."""

    def test_missing_simulator_config_file_handled(self):
        """Non-existent config path → logged error, no exception raised."""
        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path="/nonexistent/path.yaml"
            )
        )
        # Must not raise
        plugin._run_simulator_shutdown_export()

    def test_invalid_yaml_content_handled(self, tmp_path):
        """Config YAML with missing judge_simulator key → logged error."""
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("wrong_key:\n  foo: bar\n", encoding="utf-8")

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(bad_path)
            )
        )
        # Must not raise
        plugin._run_simulator_shutdown_export()

    def test_simulation_runtime_failure_handled(self, tmp_path):
        """If run_from_config raises, error is logged, no crash."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config",
            side_effect=RuntimeError("disk full"),
        ):
            # Must not raise
            plugin._run_simulator_shutdown_export()

    def test_calibration_writer_failure_surfaces_via_run_from_config(
        self, tmp_path
    ):
        """If calibration write fails inside run_from_config, the error
        propagates to our try/except and is logged."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config",
            side_effect=OSError("calibration write failed"),
        ):
            plugin._run_simulator_shutdown_export()

    def test_summary_writer_failure_surfaces_via_run_from_config(
        self, tmp_path
    ):
        """If summary write fails inside run_from_config, error is caught."""
        cfg_path = tmp_path / "sim.yaml"
        _write_judge_simulator_yaml(cfg_path)

        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path=str(cfg_path)
            )
        )

        with patch(
            "apps.reference.domains.alpha_search.judge.simulator.cli.run_from_config",
            side_effect=OSError("summary write failed"),
        ):
            plugin._run_simulator_shutdown_export()

    def test_shutdown_does_not_crash_on_import_failure(self):
        """If simulator module can't be imported, error is logged, no crash."""
        plugin = _make_plugin(
            SimulatorShutdownExportConfig(
                enabled=True, config_path="whatever.yaml"
            )
        )

        with patch(
            "builtins.__import__",
            side_effect=ImportError("module not found"),
        ):
            # This patches import globally — too broad for reliable test.
            # Instead, test the bounded behavior via the method.
            pass

        # Direct approach: patch the specific import path
        with patch.dict("sys.modules", {
            "apps.reference.domains.alpha_search.judge.simulator.cli": None,
        }):
            # When the module is None in sys.modules, import raises ImportError
            # but our method catches it gracefully
            plugin._run_simulator_shutdown_export()


# ════════════════════════════════════════════════════════════════════
# D. Config model validation
# ════════════════════════════════════════════════════════════════════


class TestSimulatorShutdownExportConfig:
    """Validate the new Pydantic config model itself."""

    def test_disabled_by_default(self):
        cfg = SimulatorShutdownExportConfig()
        assert cfg.enabled is False
        assert cfg.config_path == ""

    def test_enabled_requires_path(self):
        with pytest.raises(ValueError):
            SimulatorShutdownExportConfig(enabled=True, config_path="")

    def test_enabled_with_valid_path(self):
        cfg = SimulatorShutdownExportConfig(
            enabled=True, config_path="config/judge_simulator.yaml"
        )
        assert cfg.enabled is True
        assert cfg.config_path == "config/judge_simulator.yaml"

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            SimulatorShutdownExportConfig(enabled=False, unknown_field="x")

    def test_disabled_allows_empty_path(self):
        """When disabled, empty path is fine — no validation error."""
        cfg = SimulatorShutdownExportConfig(enabled=False, config_path="")
        assert cfg.enabled is False
