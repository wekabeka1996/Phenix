"""
T4: Hot Reload Tests
=====================

Tests for apps/reference/domains/alpha_search/runtime/hot_reload.py
11 tests covering hash detection, diff, reload, rollback, and watch loop.
"""

import asyncio
import pytest
import yaml
from pathlib import Path

from apps.reference.domains.alpha_search.runtime.contracts import (
    HotReloadConfig,
    ScenarioMatrixConfig,
    ScenarioSpec,
    RuntimeConfig,
    InputConfig,
)
from apps.reference.domains.alpha_search.runtime.hot_reload import (
    ConfigWatcher,
    ReloadDiff,
)


def _write_matrix(path: Path, scenarios=None, matrix_id="test_matrix"):
    """Write a minimal matrix YAML."""
    if scenarios is None:
        scenarios = [{
            "scenario_id": "S01",
            "enabled": True,
            "strategy_type": "aurora",
            "config_mode": "override",
            "base_refs": {"aurora": "aurora.yaml", "alpha_search": "as.yaml"},
            "overrides": {},
        }]

    raw = {
        "matrix_id": matrix_id,
        "version": 1,
        "runtime": {
            "max_scenarios": 20,
            "max_concurrent_scenarios": 20,
            "parallelism": "sequential",
            "max_workers": 1,
            "queue_maxsize": 100,
            "backpressure_policy": "drop_oldest",
            "memory_budget_mb_per_scenario": 50,
            "scenario_timeout_sec": 5.0,
            "health_heartbeat_sec": 30.0,
        },
        "hot_reload": {
            "enabled": False,
            "poll_interval_sec": 5.0,
            "debounce_sec": 2.0,
            "rollback_on_error": True,
        },
        "input": {
            "source_mode": "replay",
            "stream_path": "logs/stream.jsonl",
        },
        "scenarios": scenarios,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(raw, f)
    return path


@pytest.mark.unit
class TestComputeHash:
    """Tests for _compute_hash."""

    def test_changes_on_write(self, tmp_path):
        """Hash before != hash after."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=True)
        watcher = ConfigWatcher(cfg, path)

        hash1 = watcher._compute_hash()
        assert hash1 != ""

        # Modify file
        _write_matrix(path, matrix_id="modified_matrix")
        hash2 = watcher._compute_hash()

        assert hash1 != hash2

    def test_missing_file(self, tmp_path):
        """Returns '' for nonexistent file."""
        cfg = HotReloadConfig(enabled=True)
        watcher = ConfigWatcher(cfg, tmp_path / "nonexistent.yaml")
        assert watcher._compute_hash() == ""


@pytest.mark.unit
class TestReloadDiff:
    """Tests for ReloadDiff."""

    def test_has_changes_true(self):
        """True when added/removed/changed non-empty."""
        spec = ScenarioSpec(
            scenario_id="S_NEW",
            enabled=True,
            strategy_type="aurora",
            config_mode="override",
            base_refs={"aurora": "a.yaml", "alpha_search": "as.yaml"},
            overrides={},
        )
        diff = ReloadDiff(added=[spec], removed=[], changed=[], unchanged=[])
        assert diff.has_changes is True

    def test_has_changes_false(self):
        """False when all empty."""
        diff = ReloadDiff(added=[], removed=[], changed=[], unchanged=["S01"])
        assert diff.has_changes is False

    def test_compute_diff_has_changes(self, tmp_path):
        """Added scenarios detected."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=True)
        watcher = ConfigWatcher(cfg, path)

        with open(path) as f:
            raw = yaml.safe_load(f)
        new_config = ScenarioMatrixConfig.model_validate(raw)

        diff = watcher._compute_diff(new_config)
        assert diff.has_changes is True  # All scenarios treated as "added"


@pytest.mark.asyncio
@pytest.mark.unit
class TestTryReload:
    """Tests for _try_reload."""

    async def test_valid_config(self, tmp_path):
        """Callback invoked, generation incremented."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=True, rollback_on_error=True)

        callback_called = []

        def on_reload(new_config, diff):
            callback_called.append(True)
            return True

        watcher = ConfigWatcher(cfg, path, on_reload=on_reload)
        new_hash = watcher._compute_hash()
        await watcher._try_reload(new_hash)

        assert len(callback_called) == 1
        assert watcher._generation == 1
        assert watcher._reload_successes == 1

    async def test_invalid_yaml_rollback(self, tmp_path):
        """Rollback counter incremented, hash unchanged."""
        path = tmp_path / "matrix.yaml"
        _write_matrix(path)

        cfg = HotReloadConfig(enabled=True, rollback_on_error=True)
        watcher = ConfigWatcher(cfg, path)
        watcher._current_hash = "old_hash"

        # Write invalid YAML
        path.write_text("invalid: [yaml: {{{bad", encoding="utf-8")

        await watcher._try_reload("new_hash")

        assert watcher._reload_rollbacks == 1
        assert watcher._current_hash == "old_hash"

    async def test_callback_returns_false(self, tmp_path):
        """Rollback counter incremented when callback rejects."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=True, rollback_on_error=True)

        def reject_reload(new_config, diff):
            return False

        watcher = ConfigWatcher(cfg, path, on_reload=reject_reload)
        new_hash = watcher._compute_hash()
        await watcher._try_reload(new_hash)

        assert watcher._reload_rollbacks == 1
        assert watcher._generation == 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestWatchLoop:
    """Tests for watch_loop lifecycle."""

    async def test_disabled_exits(self, tmp_path):
        """enabled=False -> immediate return."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=False)
        watcher = ConfigWatcher(cfg, path)

        # Should return immediately without blocking
        await asyncio.wait_for(watcher.watch_loop(), timeout=1.0)

    async def test_stop_signal(self, tmp_path):
        """_running = False exits loop."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(
            enabled=True,
            poll_interval_sec=1.0,
        )
        watcher = ConfigWatcher(cfg, path)

        async def stop_after_delay():
            await asyncio.sleep(1.5)
            watcher.stop()

        await asyncio.wait_for(
            asyncio.gather(watcher.watch_loop(), stop_after_delay()),
            timeout=5.0,
        )
        assert watcher._running is False


@pytest.mark.unit
class TestWatcherStats:
    """Tests for stats property."""

    def test_stats_property(self, tmp_path):
        """All fields present."""
        path = _write_matrix(tmp_path / "matrix.yaml")
        cfg = HotReloadConfig(enabled=True)
        watcher = ConfigWatcher(cfg, path)

        stats = watcher.stats
        assert "generation" in stats
        assert "reload_attempts" in stats
        assert "reload_successes" in stats
        assert "reload_rollbacks" in stats
        assert "current_hash" in stats
