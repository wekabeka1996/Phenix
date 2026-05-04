"""
Hot Reload
==========

Config watcher for safe-swap of scenario matrix/configs without restart.

Mechanism:
1. Poll matrix YAML and scenario config dirs at configurable interval
2. Hash comparison to detect changes
3. On change, debounce to avoid rapid re-reads
4. Build generation N+1 candidate: parse + validate all changed configs
5. If valid: execute safe swap (add/remove/restart workers)
6. If invalid: rollback to generation N, log RELOAD_ROLLBACK
"""

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from .contracts import ScenarioMatrixConfig, ScenarioSpec, HotReloadConfig

LOG = logging.getLogger(__name__)


class ReloadDiff:
    """Diff between generation N and N+1."""

    def __init__(
        self,
        added: List[ScenarioSpec],
        removed: List[str],
        changed: List[ScenarioSpec],
        unchanged: List[str],
    ):
        self.added = added
        self.removed = removed
        self.changed = changed
        self.unchanged = unchanged

    def __repr__(self) -> str:
        return (
            f"ReloadDiff(added={len(self.added)}, removed={len(self.removed)}, "
            f"changed={len(self.changed)}, unchanged={len(self.unchanged)})"
        )

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


class ConfigWatcher:
    """
    File watcher for scenario matrix and scenario configs.

    Usage:
        watcher = ConfigWatcher(config, matrix_path, on_reload_callback)
        asyncio.create_task(watcher.watch_loop())
    """

    def __init__(
        self,
        config: HotReloadConfig,
        matrix_path: Path,
        on_reload: Optional[callable] = None,
    ):
        self._config = config
        self._matrix_path = matrix_path
        self._on_reload = on_reload

        self._current_hash: str = ""
        self._generation: int = 0
        self._last_change_ts: float = 0
        self._running = True

        # Stats
        self._reload_attempts = 0
        self._reload_successes = 0
        self._reload_rollbacks = 0

    async def watch_loop(self) -> None:
        """
        Async loop polling for configuration changes.

        Exit by setting self._running = False.
        """
        if not self._config.enabled:
            LOG.info("Hot reload disabled, watcher not starting")
            return

        # Compute initial hash
        self._current_hash = self._compute_hash()
        LOG.info(
            f"ConfigWatcher started: poll={self._config.poll_interval_sec}s, "
            f"debounce={self._config.debounce_sec}s"
        )

        while self._running:
            await asyncio.sleep(self._config.poll_interval_sec)

            try:
                new_hash = self._compute_hash()
                if new_hash != self._current_hash:
                    LOG.info(
                        f"Config change detected (gen={self._generation}): "
                        f"hash {self._current_hash[:8]}.. -> {new_hash[:8]}.."
                    )
                    self._last_change_ts = time.time()

                    # Debounce
                    await asyncio.sleep(self._config.debounce_sec)

                    # Reload
                    await self._try_reload(new_hash)

            except Exception as e:
                LOG.error(f"ConfigWatcher error: {e}", exc_info=True)

    async def _try_reload(self, new_hash: str) -> None:
        """
        Attempt to reload the configuration.

        1. Parse new matrix
        2. Validate all scenarios (dry run)
        3. Compute diff
        4. Apply via callback
        5. On error: rollback
        """
        self._reload_attempts += 1

        try:
            # Parse new matrix
            with open(self._matrix_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)

            new_config = ScenarioMatrixConfig.model_validate(raw)

            # Compute diff
            diff = self._compute_diff(new_config)

            if not diff.has_changes:
                LOG.info("Config changed but no scenario diff detected")
                self._current_hash = new_hash
                return

            LOG.info(f"Reload diff: {diff}")

            # Apply via callback
            if self._on_reload:
                success = self._on_reload(new_config, diff)
                if success:
                    self._generation += 1
                    self._current_hash = new_hash
                    self._reload_successes += 1
                    LOG.info(
                        f"RELOAD_APPLIED: gen={self._generation}, {diff}"
                    )
                else:
                    self._reload_rollbacks += 1
                    LOG.warning(
                        f"RELOAD_ROLLBACK: callback returned False (gen={self._generation})"
                    )
            else:
                # No callback, just update hash
                self._generation += 1
                self._current_hash = new_hash

        except Exception as e:
            self._reload_rollbacks += 1
            if self._config.rollback_on_error:
                LOG.warning(
                    f"RELOAD_ROLLBACK: validation/apply failed: {e}"
                )
            else:
                LOG.error(f"Reload failed (no rollback policy): {e}")

    def _compute_hash(self) -> str:
        """Compute content hash of matrix file."""
        if not self._matrix_path.exists():
            return ""
        content = self._matrix_path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def _compute_diff(self, new_config: ScenarioMatrixConfig) -> ReloadDiff:
        """Compute diff between current generation and new config."""
        # Load current config for comparison
        try:
            with open(self._matrix_path, "r", encoding="utf-8") as f:
                current_raw = yaml.safe_load(f)
            # Note: in production this would compare against cached current_config
            # For now, compute from new vs known worker IDs
        except Exception:
            pass

        # For now, return a simple diff
        # Full implementation would compare scenario specs field by field
        new_ids = {s.scenario_id for s in new_config.scenarios if s.enabled}

        return ReloadDiff(
            added=[s for s in new_config.scenarios if s.enabled],
            removed=[],
            changed=[],
            unchanged=[],
        )

    def stop(self) -> None:
        """Signal the watch loop to exit."""
        self._running = False

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "generation": self._generation,
            "reload_attempts": self._reload_attempts,
            "reload_successes": self._reload_successes,
            "reload_rollbacks": self._reload_rollbacks,
            "current_hash": self._current_hash[:8] + ".." if self._current_hash else "",
        }
