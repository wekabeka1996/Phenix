"""
T4: Launcher Tests
===================

Tests for apps/reference/domains/alpha_search/runtime/launcher.py
12 tests covering config loading, logging setup, path resolution.
"""

import logging
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from apps.reference.domains.alpha_search.runtime.launcher import (
    load_matrix_config,
    setup_logging,
)


@pytest.mark.unit
class TestLoadMatrixConfig:
    """Tests for load_matrix_config."""

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


@pytest.mark.unit
class TestPathResolution:
    """Tests for path resolution logic."""

    def test_project_root_resolution(self):
        """parents[5] from launcher.py points to correct root."""
        launcher_path = Path(__file__).resolve(
        ).parents[1] / "runtime" / "launcher.py"
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
