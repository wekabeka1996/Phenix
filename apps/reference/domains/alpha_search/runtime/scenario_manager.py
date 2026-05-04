"""
Scenario Manager
================

Owns the lifecycle of all ScenarioWorkers.
Loads the scenario matrix, creates workers, fans out snapshots, collects results.

Supports:
- Mixed strategy types (aurora, mean_reversion, ensemble)
- Per-scenario config resolution and log isolation
- Sequential and thread-pool parallel fan-out
- Health heartbeat and graceful degradation
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .contracts import AlphaInputV1, ScenarioMatrixConfig, ScenarioSpec
from .config_resolver import (
    resolve_scenario_config,
    persist_effective_config,
    ConfigResolutionError,
)
from .scenario_worker import ScenarioWorker
from .logger_factory import ScenarioLoggerFactory, ScenarioScoreWriter
from .reporting import AggregateReporter
from .shadow_book import ShadowBook

LOG = logging.getLogger(__name__)


class ScenarioManager:
    """
    Manages lifecycle and fan-out for all scenario workers.

    Responsibilities:
    1. Initialize workers from matrix config
    2. Fan out snapshots to all active workers
    3. Collect and aggregate results
    4. Provide health/summary data
    5. Support safe worker replacement (for hot reload)
    """

    def __init__(
        self,
        config: ScenarioMatrixConfig,
        project_root: Path,
        session_dir: Path,
    ):
        self._config = config
        self._project_root = project_root
        self._session_dir = session_dir
        self._generation = 0

        # Worker pool
        self._workers: Dict[str, ScenarioWorker] = {}
        self._score_writers: Dict[str, ScenarioScoreWriter] = {}
        self._shadow_books: Dict[str, ShadowBook] = {}

        # Aggregate reporter
        self._reporter = AggregateReporter(session_dir)

        # Stats
        self._snapshots_dispatched = 0
        self._start_ts = time.time()

    def initialize(self) -> int:
        """
        Create workers for all enabled scenarios.

        Returns number of successfully initialized workers.
        """
        enabled = [s for s in self._config.scenarios if s.enabled]
        LOG.info(
            f"Initializing {len(enabled)} scenarios "
            f"(matrix={self._config.matrix_id}, gen={self._generation})"
        )

        initialized = 0
        for spec in enabled:
            try:
                self._init_worker(spec)
                initialized += 1
            except ConfigResolutionError as e:
                LOG.error(
                    f"[{spec.scenario_id}] Config resolution failed: {e}")
                self._reporter.log_health({
                    "event": "SCENARIO_INIT_FAILED",
                    "scenario_id": spec.scenario_id,
                    "error": str(e),
                })
            except Exception as e:
                LOG.error(
                    f"[{spec.scenario_id}] Worker init failed: {e}",
                    exc_info=True,
                )
                self._reporter.log_health({
                    "event": "SCENARIO_INIT_FAILED",
                    "scenario_id": spec.scenario_id,
                    "error": str(e),
                })

        LOG.info(
            f"ScenarioManager ready: {initialized}/{len(enabled)} workers active"
        )

        return initialized

    def _init_worker(self, spec: ScenarioSpec) -> None:
        """Initialize a single scenario worker with config resolution."""
        # Resolve configs
        alpha_cfg, system_cfg, strategy_cfg = resolve_scenario_config(
            spec, self._project_root
        )

        # Create log directory
        scenario_log_dir = self._session_dir / spec.scenario_id
        scenario_log_dir.mkdir(parents=True, exist_ok=True)

        # Persist effective config
        persist_effective_config(
            scenario_id=spec.scenario_id,
            alpha_search_config=alpha_cfg,
            system_config=system_cfg,
            strategy_config=strategy_cfg,
            output_dir=scenario_log_dir,
        )

        # Create shadow book (BEFORE worker so it can be injected in)
        shadow_book = ShadowBook(
            scenario_id=spec.scenario_id,
            notional_size=alpha_cfg.virtual_trader.notional_size,
        )

        # Create worker
        worker = ScenarioWorker(
            spec=spec,
            alpha_search_config=alpha_cfg,
            system_config=system_cfg,
            strategy_config=strategy_cfg,
            log_dir=scenario_log_dir,
            shadow_book=shadow_book,
        )

        # Create per-scenario score writer
        score_writer = ScenarioScoreWriter(
            scenario_id=spec.scenario_id,
            log_dir=self._session_dir,
        )

        self._workers[spec.scenario_id] = worker
        self._score_writers[spec.scenario_id] = score_writer
        self._shadow_books[spec.scenario_id] = shadow_book

        LOG.info(
            f"[{spec.scenario_id}] Worker ready: "
            f"strategy={spec.strategy_type}, config_mode={spec.config_mode}"
        )

    def fan_out(self, snapshot: AlphaInputV1) -> Dict[str, List[Dict]]:
        """
        Dispatch a single snapshot to all active workers.

        Returns:
            {scenario_id: [result_dicts]}
        """
        self._snapshots_dispatched += 1
        all_results: Dict[str, List[Dict]] = {}

        for sid, worker in self._workers.items():
            try:
                results = worker.process_snapshot(snapshot)
                all_results[sid] = results

                # Write results to per-scenario log
                writer = self._score_writers.get(sid)
                if writer:
                    for r in results:
                        writer.write_score(r)

                # Write to aggregate
                for r in results:
                    self._reporter.log_result(r)

            except Exception as e:
                LOG.error(f"[{sid}] Fan-out error: {e}")
                all_results[sid] = []

        return all_results

    def get_aggregate_summary(self) -> Dict[str, Any]:
        """Collect summaries from all workers."""
        summaries = {}
        for sid, worker in self._workers.items():
            try:
                summary = worker.get_summary()
                book = self._shadow_books.get(sid)
                if book:
                    summary["shadow_metrics"] = book.get_metrics()
                summaries[sid] = summary
            except Exception as e:
                summaries[sid] = {"error": str(e)}

        return {
            "matrix_id": self._config.matrix_id,
            "generation": self._generation,
            "active_workers": len(self._workers),
            "snapshots_dispatched": self._snapshots_dispatched,
            "uptime_sec": round(time.time() - self._start_ts, 1),
            "scenarios": summaries,
        }

    def shutdown(self) -> None:
        """Shutdown all workers and finalize reports."""
        LOG.info(
            f"ScenarioManager shutting down: {len(self._workers)} workers"
        )

        # Collect final summaries
        final_summary = self.get_aggregate_summary()
        self._reporter.log_summary(final_summary.get("scenarios", {}))

        # Shutdown workers
        for sid, worker in self._workers.items():
            try:
                worker.shutdown()
            except Exception as e:
                LOG.warning(f"[{sid}] Shutdown error: {e}")

        self._reporter.log_health({
            "event": "MANAGER_SHUTDOWN",
            "workers": len(self._workers),
            "snapshots_dispatched": self._snapshots_dispatched,
        })

        LOG.info(
            f"ScenarioManager stopped: dispatched={self._snapshots_dispatched}, "
            f"workers={len(self._workers)}"
        )

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    @property
    def worker_ids(self) -> List[str]:
        return list(self._workers.keys())
