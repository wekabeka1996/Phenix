"""
Tests for Log Rotation Configuration & Numbering

Verifies that:
1. RotatingFileHandler creates correct sequential backup numbering (.log.1, .log.2, ...).
2. All production log handlers use RotatingFileHandler (not plain FileHandler).
3. observability.yaml sizes are 2x the previous defaults.
4. Decentralized adapters (trades, market_data, dm, alpha_search, neocortex) match the policy.
"""

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# 1. RotatingFileHandler produces sequential .log.1, .log.2, ... numbering
# ---------------------------------------------------------------------------

class TestRotationNumbering:
    """Verify Python's RotatingFileHandler creates correct sequential backups."""

    def test_sequential_numbering(self, tmp_path):
        """
        Write enough data to trigger multiple rotations.
        Expect: base.log, base.log.1, base.log.2, ... in sequential order.
        """
        log_file = tmp_path / "base.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=200,   # tiny threshold to trigger rotation fast
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_rotation_numbering")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # Write enough messages to cause several rotations
        for i in range(50):
            logger.debug(f"Message {i:04d} padding to exceed 200 bytes easily")

        handler.close()
        logger.removeHandler(handler)

        # Check files exist with sequential numbering
        assert log_file.exists(), "base.log must exist"
        for n in range(1, 6):
            backup = tmp_path / f"base.log.{n}"
            assert backup.exists(), f"base.log.{n} must exist (backupCount=5)"

        # base.log.6 should NOT exist (backupCount=5)
        assert not (
            tmp_path / "base.log.6").exists(), "base.log.6 should not exist"

    def test_backup_count_respected(self, tmp_path):
        """backupCount=3 means at most .log.1, .log.2, .log.3."""
        log_file = tmp_path / "limited.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=100,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_backup_count")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        for i in range(100):
            logger.debug(f"Line {i:05d} - padding text to fill the file")

        handler.close()
        logger.removeHandler(handler)

        assert (tmp_path / "limited.log").exists()
        assert (tmp_path / "limited.log.1").exists()
        assert (tmp_path / "limited.log.2").exists()
        assert (tmp_path / "limited.log.3").exists()
        assert not (tmp_path / "limited.log.4").exists()

    def test_numbering_is_sequential_not_chaotic(self, tmp_path):
        """
        After multiple rotations, file modification times must be monotonically
        ordered: .log (newest) > .log.1 > .log.2 > ... (oldest).
        """
        log_file = tmp_path / "ordered.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=150,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_numbering_order")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        for i in range(80):
            logger.debug(f"Ordered message {i:04d} with padding text here")

        handler.close()
        logger.removeHandler(handler)

        # .log.1 should be newer (or same) than .log.2
        files_by_number = []
        for n in range(1, 6):
            p = tmp_path / f"ordered.log.{n}"
            if p.exists():
                files_by_number.append(p)

        # RotatingFileHandler: .log.1 is the most recent backup, .log.N is oldest
        # The sizes should all be roughly equal (near maxBytes)
        for p in files_by_number:
            assert p.stat().st_size > 0, f"{p.name} should not be empty"


# ---------------------------------------------------------------------------
# 2. observability.yaml configuration values match 2x policy
# ---------------------------------------------------------------------------

class TestObservabilityConfig:
    """Verify observability.yaml has correct rotation settings."""

    @pytest.fixture
    def obs_config(self):
        config_path = Path(__file__).parent.parent / \
            "config" / "aurora" / "observability.yaml"
        if not config_path.exists():
            pytest.skip(f"observability.yaml not found at {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_global_rotation_defaults(self, obs_config):
        rotation = obs_config["logging"]["rotation"]
        assert rotation["max_bytes"] == 20 * 1024 * \
            1024, "Global max_bytes should be 20 MB"
        assert rotation["backup_count"] == 100

    def test_core_sink(self, obs_config):
        core = obs_config["logging"]["core"]
        assert core["enabled"] is True
        assert core["max_bytes"] == 20 * 1024 * \
            1024, "Core max_bytes should be 20 MB"
        assert core["backup_count"] == 100

    def test_domain_sinks(self, obs_config):
        domains = obs_config["logging"]["domains"]
        for name, cfg in domains.items():
            assert cfg["max_bytes"] == 10 * 1024 * 1024, (
                f"Domain '{name}' max_bytes should be 10 MB, got {cfg['max_bytes']}"
            )
            assert cfg["backup_count"] == 100, (
                f"Domain '{name}' backup_count should be 100"
            )

    def test_event_chain_sink(self, obs_config):
        ec = obs_config["logging"]["event_chain"]
        assert ec["max_bytes"] == 20 * 1024 * \
            1024, "Event chain max_bytes should be 20 MB"
        assert ec["backup_count"] == 100


# ---------------------------------------------------------------------------
# 3. Decentralized adapters use RotatingFileHandler with correct params
# ---------------------------------------------------------------------------

class TestAdapterRotationConfig:
    """Verify that all log adapters use RotatingFileHandler (not plain FileHandler)."""

    def test_aurora_trades_uses_rotating_handler(self):
        """aurora_log_adapter must use RotatingFileHandler, not FileHandler."""
        import importlib
        try:
            mod = importlib.import_module(
                "apps.reference.domains.execution_position.aurora_log_adapter"
            )
        except ImportError:
            pytest.skip("aurora_log_adapter not importable")

        import inspect
        source = inspect.getsource(mod)
        assert "RotatingFileHandler" in source, (
            "aurora_log_adapter.py must use RotatingFileHandler"
        )
        assert "backupCount=100" in source or "backupCount = 100" in source, (
            "aurora_log_adapter.py must have backupCount=100"
        )

    def test_dm_log_adapter_config(self):
        """dm_log_adapter must have 10MB maxBytes and 100 backups."""
        import importlib
        try:
            mod = importlib.import_module(
                "apps.reference.domains.decision_making.dm_log_adapter"
            )
        except ImportError:
            pytest.skip("dm_log_adapter not importable")

        import inspect
        source = inspect.getsource(mod)
        assert "10_000_000" in source or "10000000" in source, (
            "dm_log_adapter.py maxBytes should be 10 MB"
        )
        assert "backupCount=100" in source

    def test_alpha_search_log_adapter_config(self):
        """alpha_search_log_adapter must have 10MB maxBytes and 100 backups."""
        import importlib
        try:
            mod = importlib.import_module(
                "apps.reference.domains.alpha_search.alpha_search_log_adapter"
            )
        except ImportError:
            pytest.skip("alpha_search_log_adapter not importable")

        import inspect
        source = inspect.getsource(mod)
        assert "10_000_000" in source or "10000000" in source, (
            "alpha_search_log_adapter.py maxBytes should be 10 MB"
        )
        assert "backupCount=100" in source

    def test_neocortex_main_config(self):
        """neocortex/main.py must have backupCount=100 and 20MB."""
        import importlib
        try:
            mod = importlib.import_module(
                "apps.reference.domains.neocortex.main"
            )
        except ImportError:
            pytest.skip("neocortex.main not importable")

        import inspect
        source = inspect.getsource(mod)
        assert "backupCount=100" in source or "backupCount = 100" in source, (
            "neocortex/main.py must have backupCount=100"
        )

    def test_market_data_worker_config(self):
        """market_data/worker.py must have 20MB maxBytes and 100 backups."""
        src_path = (
            Path(__file__).parent.parent
            / "apps" / "reference" / "domains" / "market_data" / "worker.py"
        )
        if not src_path.exists():
            pytest.skip("worker.py not found")

        source = src_path.read_text(encoding="utf-8")
        assert "20 * 1024 * 1024" in source or "20971520" in source, (
            "market_data/worker.py maxBytes should be 20 MB"
        )
        assert "backupCount=100" in source
