"""
Scenario Executor
=================

Thread pool-based parallel execution for CPU-bound scoring.

Design choice: ThreadPoolExecutor (not ProcessPoolExecutor) because:
- Scoring is CPU-bound but lightweight per call (~1-5ms)
- 10-20 scenarios = 10-20 threads, well within practical range
- Process pool adds IPC serialization overhead exceeding scoring cost
- Shared feature cache is trivial with threads (no multiprocessing.Manager)
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, List, Optional, Union

from .contracts import AlphaInputV1, RuntimeConfig
from .scenario_worker import ScenarioWorker

LOG = logging.getLogger(__name__)


class ScenarioExecutor:
    """
    Parallel executor for scenario fan-out.

    Dispatches snapshots to all workers via thread pool with per-scenario timeout.
    Failed workers return exceptions without crashing others.
    """

    def __init__(self, config: RuntimeConfig):
        self._parallelism = config.parallelism
        self._max_workers = config.max_workers
        self._timeout = config.scenario_timeout_sec
        self._pool: Optional[ThreadPoolExecutor] = None

        # Stats
        self._total_dispatches = 0
        self._total_timeouts = 0
        self._total_errors = 0

    def start(self) -> None:
        """Start the executor pool."""
        if self._parallelism == "thread_pool":
            self._pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="alpha_search_worker",
            )
            LOG.info(
                f"ScenarioExecutor started: parallelism={self._parallelism}, "
                f"max_workers={self._max_workers}, timeout={self._timeout}s"
            )
        else:
            LOG.info("ScenarioExecutor started: parallelism=sequential")

    def execute_all(
        self,
        workers: Dict[str, ScenarioWorker],
        snapshot: AlphaInputV1,
    ) -> Dict[str, Union[List[Dict], Exception]]:
        """
        Fan out snapshot to all workers.

        Returns:
            {scenario_id: [results] | Exception}

        Failed/timed-out workers return Exception objects (no global crash).
        """
        self._total_dispatches += 1

        if self._parallelism == "sequential":
            return self._execute_sequential(workers, snapshot)
        else:
            return self._execute_parallel(workers, snapshot)

    def _execute_sequential(
        self,
        workers: Dict[str, ScenarioWorker],
        snapshot: AlphaInputV1,
    ) -> Dict[str, Union[List[Dict], Exception]]:
        """Execute all workers sequentially (for debugging)."""
        results = {}
        for sid, worker in workers.items():
            start = time.monotonic()
            try:
                results[sid] = worker.process_snapshot(snapshot)
            except Exception as e:
                self._total_errors += 1
                results[sid] = e
                LOG.error(f"[{sid}] Sequential execution error: {e}")
            elapsed = time.monotonic() - start
            if elapsed > self._timeout:
                LOG.warning(
                    f"[{sid}] Sequential exec exceeded timeout: "
                    f"{elapsed:.2f}s > {self._timeout}s"
                )
        return results

    def _execute_parallel(
        self,
        workers: Dict[str, ScenarioWorker],
        snapshot: AlphaInputV1,
    ) -> Dict[str, Union[List[Dict], Exception]]:
        """Execute all workers in parallel via thread pool."""
        if not self._pool:
            return self._execute_sequential(workers, snapshot)

        futures: Dict[str, Future] = {}
        for sid, worker in workers.items():
            futures[sid] = self._pool.submit(worker.process_snapshot, snapshot)

        results = {}
        for sid, future in futures.items():
            try:
                results[sid] = future.result(timeout=self._timeout)
            except FuturesTimeout:
                self._total_timeouts += 1
                results[sid] = TimeoutError(
                    f"Scenario {sid} timed out ({self._timeout}s)"
                )
                LOG.warning(f"[{sid}] Execution timed out ({self._timeout}s)")
            except Exception as e:
                self._total_errors += 1
                results[sid] = e
                LOG.error(f"[{sid}] Parallel execution error: {e}")

        return results

    def shutdown(self) -> None:
        """Shutdown the thread pool."""
        if self._pool:
            self._pool.shutdown(wait=True)
            LOG.info(
                f"ScenarioExecutor stopped: dispatches={self._total_dispatches}, "
                f"timeouts={self._total_timeouts}, errors={self._total_errors}"
            )

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "parallelism": self._parallelism,
            "max_workers": self._max_workers,
            "total_dispatches": self._total_dispatches,
            "total_timeouts": self._total_timeouts,
            "total_errors": self._total_errors,
        }
