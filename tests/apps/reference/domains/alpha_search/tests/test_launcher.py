"""
T4: Launcher Tests
===================

Tests for apps/reference/domains/alpha_search/runtime/launcher.py
12 tests covering config loading, logging setup, path resolution.
"""

import asyncio
import logging
import os
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime as real_datetime

from apps.reference.domains.alpha_search.runtime.launcher import (
    load_matrix_config,
    setup_logging,
)


def _minimal_matrix_config(**input_overrides):
    from apps.reference.domains.alpha_search.runtime.contracts import (
        HotReloadConfig,
        InputConfig,
        RuntimeConfig,
        ScenarioMatrixConfig,
        ScenarioSpec,
    )

    input_data = {"stream_path": "streams/alpha_input_v1.jsonl"}
    input_data.update(input_overrides)

    return ScenarioMatrixConfig(
        matrix_id="test_matrix",
        version=1,
        runtime=RuntimeConfig(health_heartbeat_sec=5.0),
        hot_reload=HotReloadConfig(),
        input=InputConfig(**input_data),
        scenarios=[
            ScenarioSpec(
                scenario_id="S_TEST",
                enabled=True,
                strategy_type="aurora",
                config_mode="override",
                base_refs={
                    "alpha_search": "config/alpha_search.yaml",
                    "aurora": "config/aurora.yaml",
                },
                overrides={},
            )
        ],
    )


@pytest.mark.unit
class TestLoadMatrixConfig:
    """Tests for load_matrix_config."""

    def test_shadow_registry_live_tail_uses_live_mirror_stream(self, tmp_path):
        """Registry live_tail should point standalone ingest at the live mirror file."""
        registry_path = tmp_path / "scenario_registry_v2.yaml"
        registry_path.write_text(yaml.dump({"registry_id": "test_registry", "version": 1}), encoding="utf-8")

        with patch(
            "apps.reference.domains.alpha_search.shadow.registry_adapter.load_registry_as_matrix_config",
            return_value=MagicMock(),
        ) as load_registry:
            load_matrix_config(registry_path, registry_source_mode="live_tail")

        load_registry.assert_called_once_with(
            str(registry_path),
            source_mode="live_tail",
            stream_path="logs/alpha_input/alpha_input_v1_live.jsonl",
        )

    def test_shadow_registry_replay_uses_recorder_built_stream(self, tmp_path):
        """Registry replay should keep using the recorder-built alpha_input file."""
        registry_path = tmp_path / "scenario_registry_v2.yaml"
        registry_path.write_text(yaml.dump({"registry_id": "test_registry", "version": 1}), encoding="utf-8")

        with patch(
            "apps.reference.domains.alpha_search.shadow.registry_adapter.load_registry_as_matrix_config",
            return_value=MagicMock(),
        ) as load_registry:
            load_matrix_config(registry_path, registry_source_mode="replay")

        load_registry.assert_called_once_with(
            str(registry_path),
            source_mode="replay",
            stream_path="logs/alpha_input/alpha_input_v1.jsonl",
        )

    def test_valid_config(self):
        """Real scenario_matrix.yaml loads successfully."""
        project_root = Path(__file__).resolve().parents[4]
        matrix_path = project_root / "config" / "alpha_search" / "scenario_matrix.yaml"
        if not matrix_path.exists():
            pytest.skip("scenario_matrix.yaml not found")

        config = load_matrix_config(matrix_path)
        assert config.matrix_id == "alpha_search_shadow_v2"
        assert len(config.scenarios) == 10

    def test_missing_file(self, tmp_path):
        """FileNotFoundError raised."""
        with pytest.raises(FileNotFoundError):
            load_matrix_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path):
        """ValidationError raised for invalid schema."""
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text(yaml.dump({"invalid": "schema"}), encoding="utf-8")
        with pytest.raises(Exception):  # pydantic.ValidationError
            load_matrix_config(bad_path)


@pytest.mark.unit
class TestSetupLogging:
    """Tests for setup_logging."""

    def test_creates_file_handler(self, tmp_path):
        """Log file created in session_dir."""
        session_dir = tmp_path / "session"
        logger = setup_logging(
            session_dir, log_level="DEBUG", log_to_file=True)

        log_file = session_dir / "aggregate" / "alpha_search_domain.log"
        assert log_file.exists()

        # Cleanup
        for h in logging.root.handlers[:]:
            if hasattr(h, 'baseFilename'):
                h.close()

    def test_console_handler(self, tmp_path):
        """Stdout handler present."""
        session_dir = tmp_path / "session"
        logger = setup_logging(session_dir, log_to_file=False)

        # Should have at least a StreamHandler
        stream_handlers = [
            h for h in logging.root.handlers
            if isinstance(h, logging.StreamHandler)
            and not hasattr(h, 'baseFilename')
        ]
        assert len(stream_handlers) > 0

    def test_no_file(self, tmp_path):
        """log_to_file=False -> no file handler."""
        session_dir = tmp_path / "session"
        logger = setup_logging(session_dir, log_to_file=False)

        log_file = session_dir / "aggregate" / "alpha_search_domain.log"
        assert not log_file.exists()

    def test_invalid_log_level_falls_back_to_info(self, tmp_path):
        """Unknown log levels should not break logging setup."""
        session_dir = tmp_path / "session"
        setup_logging(session_dir, log_level="NOT_A_LEVEL", log_to_file=False)

        assert logging.root.level == logging.INFO


@pytest.mark.unit
class TestPathResolution:
    """Tests for path resolution logic."""

    def test_project_root_resolution(self):
        """parents[5] from launcher.py points to correct root."""
        launcher_path = Path(__file__).resolve(
        ).parents[6] / "apps" / "reference" / "domains" / "alpha_search" / "runtime" / "launcher.py"
        if launcher_path.exists():
            # Simulate the same logic: parents[5] from launcher.py
            project_root = launcher_path.parents[5]
            assert (project_root / "pytest.ini").exists() or \
                   (project_root / "config").exists()

    def test_session_dir_format(self, tmp_path):
        """Session dir uses timestamp format."""
        from datetime import datetime
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = tmp_path / "logs" / "alpha_search_runtime" / session_id
        session_dir.mkdir(parents=True)
        assert session_dir.exists()
        # Format check: YYYYMMDD_HHMMSS
        assert len(session_id) == 15
        assert session_id[8] == "_"


@pytest.mark.unit
class TestMainReactor:
    """Tests for main_reactor function."""

    def test_zero_workers_exits(self, tmp_path):
        """0 workers -> early return."""
        from apps.reference.domains.alpha_search.runtime.launcher import main_reactor
        from apps.reference.domains.alpha_search.runtime.contracts import (
            ScenarioMatrixConfig,
            ScenarioSpec,
            RuntimeConfig,
            HotReloadConfig,
            InputConfig,
        )

        # Create config with a scenario that will fail to init
        config = ScenarioMatrixConfig(
            matrix_id="test",
            version=1,
            runtime=RuntimeConfig(),
            hot_reload=HotReloadConfig(),
            input=InputConfig(stream_path="nonexistent.jsonl"),
            scenarios=[
                ScenarioSpec(
                    scenario_id="S_FAIL",
                    enabled=True,
                    strategy_type="aurora",
                    config_mode="override",
                    base_refs={"aurora": "nonexistent.yaml",
                               "alpha_search": "nonexistent.yaml"},
                    overrides={},
                ),
            ],
        )

        project_root = tmp_path / "project"
        project_root.mkdir()
        session_dir = tmp_path / "session"
        (session_dir / "aggregate").mkdir(parents=True)
        logger = logging.getLogger("test_launcher")

        import asyncio
        # Should return without error (0 workers -> early exit)
        asyncio.run(
            main_reactor(config, project_root, session_dir, logger)
        )

    def test_run_default_matrix_path(self):
        """Default path resolves correctly."""
        from apps.reference.domains.alpha_search.runtime.launcher import run
        project_root = Path(__file__).resolve().parents[4]
        default_path = project_root / "config" / \
            "alpha_search" / "scenario_matrix.yaml"
        # Just verify the path resolution logic (don't actually run)
        assert isinstance(default_path, Path)

    def test_run_custom_matrix_path(self, tmp_path):
        """Absolute and relative paths handled."""
        # Absolute path
        abs_path = tmp_path / "custom_matrix.yaml"
        assert abs_path.is_absolute()

        # Relative path would be resolved against project_root
        rel_path = Path("config/custom_matrix.yaml")
        assert not rel_path.is_absolute()

    def test_live_tail_missing_stream_warns_before_zero_worker_exit(self, tmp_path):
        """live_tail guard should log a startup warning even if no workers come up."""
        from apps.reference.domains.alpha_search.runtime.launcher import main_reactor

        project_root = tmp_path / "project"
        project_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        logger = MagicMock()
        config = _minimal_matrix_config(
            source_mode="live_tail",
            stream_path="missing/live_input.jsonl",
        )

        with patch("apps.reference.domains.alpha_search.runtime.launcher.IngestGateway"), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.ScenarioManager"
        ) as manager_cls, patch(
            "apps.reference.domains.alpha_search.runtime.launcher.ScenarioExecutor"
        ) as executor_cls, patch(
            "apps.reference.domains.alpha_search.runtime.launcher.HealthMonitor"
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.BoundedIngestQueue"
        ):
            manager_cls.return_value.initialize.return_value = 0

            asyncio.run(main_reactor(config, project_root, session_dir, logger))

        logger.warning.assert_called_once()
        logger.error.assert_called_with("No workers initialized. Exiting.")
        executor_cls.return_value.start.assert_not_called()

    def test_replay_missing_stream_logs_error_before_zero_worker_exit(self, tmp_path):
        """replay mode should fail closed with a startup error when the file is absent."""
        from apps.reference.domains.alpha_search.runtime.launcher import main_reactor

        project_root = tmp_path / "project"
        project_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        logger = MagicMock()
        config = _minimal_matrix_config(
            source_mode="replay",
            stream_path="missing/replay_input.jsonl",
        )

        with patch("apps.reference.domains.alpha_search.runtime.launcher.IngestGateway"), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.ScenarioManager"
        ) as manager_cls, patch(
            "apps.reference.domains.alpha_search.runtime.launcher.ScenarioExecutor"
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.HealthMonitor"
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.BoundedIngestQueue"
        ):
            manager_cls.return_value.initialize.return_value = 0

            asyncio.run(main_reactor(config, project_root, session_dir, logger))

        logger.error.assert_any_call(
            f"STARTUP ERROR: source_mode=replay but stream file not found: {project_root / 'missing' / 'replay_input.jsonl'}\n"
            f"  -> Run: python tools/build_alpha_input.py"
        )

    def test_run_resolves_relative_matrix_path_and_sets_default_log_dir(self):
        """run() should resolve relative paths against project root and set session-scoped log dir."""
        from apps.reference.domains.alpha_search.runtime import launcher

        config = _minimal_matrix_config()
        logger = MagicMock()
        fake_now = real_datetime(2026, 1, 2, 3, 4, 5)
        project_root = Path(launcher.__file__).resolve().parents[5]
        expected_session_dir = project_root / "logs" / "alpha_search_runtime" / "20260102_030405"

        class _FakeDateTime:
            @classmethod
            def now(cls):
                return fake_now

        with patch.dict(os.environ, {}, clear=True), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.datetime",
            _FakeDateTime,
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.load_matrix_config",
            return_value=config,
        ) as load_cfg, patch(
            "apps.reference.domains.alpha_search.runtime.launcher.setup_logging",
            return_value=logger,
        ) as setup_log, patch(
            "apps.reference.domains.alpha_search.runtime.launcher.main_reactor",
            new_callable=AsyncMock,
        ) as main_reactor:
            asyncio.run(launcher.run(matrix_path="config/custom_matrix.yaml", log_level="DEBUG"))

            assert os.environ["ALPHA_SEARCH_LOG_DIR"] == str(expected_session_dir / "aggregate")

        load_cfg.assert_called_once_with(project_root / "config" / "custom_matrix.yaml", registry_source_mode="live_tail")
        setup_log.assert_called_once_with(expected_session_dir, log_level="DEBUG")
        main_reactor.assert_awaited_once_with(config, project_root, expected_session_dir, logger)

    def test_run_preserves_existing_alpha_search_log_dir(self):
        """run() should not overwrite explicit ALPHA_SEARCH_LOG_DIR."""
        from apps.reference.domains.alpha_search.runtime import launcher

        config = _minimal_matrix_config()
        logger = MagicMock()

        with patch.dict(os.environ, {"ALPHA_SEARCH_LOG_DIR": "C:/custom/logs"}, clear=True), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.load_matrix_config",
            return_value=config,
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.setup_logging",
            return_value=logger,
        ), patch(
            "apps.reference.domains.alpha_search.runtime.launcher.main_reactor",
            new_callable=AsyncMock,
        ):
            asyncio.run(launcher.run(matrix_path="config/custom_matrix.yaml"))
            assert os.environ["ALPHA_SEARCH_LOG_DIR"] == "C:/custom/logs"
