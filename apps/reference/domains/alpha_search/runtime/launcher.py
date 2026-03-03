"""
Alpha Search Standalone Launcher
=================================

Async reactor for the standalone alpha search domain.
Pattern follows apps/reference/domains/neocortex/main.py.

Flow:
  load_config() -> setup_logging() -> main_reactor()
     -> IngestGateway -> ScenarioManager -> [Workers] -> AggregateReporter
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import yaml

from .contracts import ScenarioMatrixConfig
from .ingest import IngestGateway
from .scenario_manager import ScenarioManager
from .executor import ScenarioExecutor
from .backpressure import BoundedIngestQueue
from .health import HealthMonitor
from .logger_factory import ScenarioLoggerFactory

LOG = logging.getLogger(__name__)


def load_matrix_config(matrix_path: Path) -> ScenarioMatrixConfig:
    """
    Load and validate scenario matrix config (fail-closed).

    Raises:
        FileNotFoundError: if matrix YAML not found
        pydantic.ValidationError: if schema invalid
    """
    if not matrix_path.exists():
        raise FileNotFoundError(f"Scenario matrix not found: {matrix_path}")

    with open(matrix_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return ScenarioMatrixConfig.model_validate(raw)


def setup_logging(
    session_dir: Path,
    log_level: str = "INFO",
    log_to_file: bool = True,
) -> logging.Logger:
    """
    Setup structured logging for standalone domain.

    Console + optional rotating file handler.
    """
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_to_file:
        log_dir = session_dir / "aggregate"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "alpha_search_domain.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=20 * 1024 * 1024,  # 20 MB
            backupCount=50,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, log_level, logging.INFO))
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_format,
        handlers=handlers,
        force=True,
    )

    return logging.getLogger("alpha_search.launcher")


async def main_reactor(
    config: ScenarioMatrixConfig,
    project_root: Path,
    session_dir: Path,
    logger: logging.Logger,
) -> None:
    """
    Main async reactor loop.

    1. Create IngestGateway
    2. Create ScenarioManager + initialize workers
    3. Create Executor (thread pool or sequential)
    4. Fan out snapshots: ingest -> executor -> workers -> reporter
    5. Periodic heartbeat with health checks
    """
    # --- Components ---
    ingest = IngestGateway(
        stream_path=project_root / config.input.stream_path,
        mode=config.input.source_mode,
    )

    manager = ScenarioManager(
        config=config,
        project_root=project_root,
        session_dir=session_dir,
    )

    executor = ScenarioExecutor(config.runtime)
    health = HealthMonitor(config.runtime)
    queue = BoundedIngestQueue(
        maxsize=config.runtime.queue_maxsize,
        policy=config.runtime.backpressure_policy,
    )

    # --- Initialize ---
    worker_count = manager.initialize()
    if worker_count == 0:
        logger.error("No workers initialized. Exiting.")
        return

    executor.start()

    logger.info(
        f"Reactor started: workers={worker_count}, "
        f"mode={config.input.source_mode}, "
        f"parallelism={config.runtime.parallelism}"
    )

    # --- Main loop ---
    last_heartbeat = time.time()
    snapshots_processed = 0

    try:
        if config.input.source_mode == "replay":
            # Replay mode: synchronous iteration
            for snapshot in ingest.iter_replay():
                # Fan out to all workers via executor
                results = executor.execute_all(
                    manager._workers, snapshot
                )

                # Process results
                for sid, result in results.items():
                    if isinstance(result, Exception):
                        health.record_failure(sid, str(result))
                    else:
                        health.record_success(sid)
                        # Write results to per-scenario logs
                        writer = manager._score_writers.get(sid)
                        if writer:
                            for r in result:
                                writer.write_score(r)
                        # Write to aggregate
                        for r in result:
                            manager._reporter.log_result(r)

                snapshots_processed += 1

                # Periodic heartbeat
                now = time.time()
                if now - last_heartbeat >= config.runtime.health_heartbeat_sec:
                    statuses = health.check_health(manager.worker_ids)
                    logger.info(
                        f"Heartbeat: processed={snapshots_processed}, "
                        f"health={statuses}, "
                        f"ingest={ingest.stats}"
                    )
                    last_heartbeat = now

        else:
            # Live tail mode: async iteration
            async for snapshot in ingest.iter_live_tail():
                results = executor.execute_all(
                    manager._workers, snapshot
                )

                for sid, result in results.items():
                    if isinstance(result, Exception):
                        health.record_failure(sid, str(result))
                    else:
                        health.record_success(sid)
                        writer = manager._score_writers.get(sid)
                        if writer:
                            for r in result:
                                writer.write_score(r)
                        for r in result:
                            manager._reporter.log_result(r)

                snapshots_processed += 1

                now = time.time()
                if now - last_heartbeat >= config.runtime.health_heartbeat_sec:
                    statuses = health.check_health(manager.worker_ids)
                    logger.info(
                        f"Heartbeat: processed={snapshots_processed}, "
                        f"health={statuses}"
                    )
                    last_heartbeat = now

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        # --- Shutdown ---
        logger.info(
            f"Reactor stopping: processed={snapshots_processed}"
        )
        executor.shutdown()
        manager.shutdown()

        # Final stats
        logger.info(
            f"Final stats: "
            f"ingest={ingest.stats}, "
            f"executor={executor.stats}, "
            f"health={health.stats}"
        )


async def run(
    matrix_path: Optional[str] = None,
    log_level: str = "INFO",
) -> None:
    """
    Top-level entry point.

    1. Resolve paths
    2. Load and validate matrix config (fail-closed)
    3. Setup logging
    4. Enter main reactor
    """
    # Resolve project root (5 levels up from this file)
    # apps/reference/domains/alpha_search/runtime/launcher.py -> project root
    project_root = Path(__file__).resolve().parents[5]

    # Default matrix path
    if matrix_path is None:
        matrix_path_resolved = project_root / "config" / \
            "alpha_search" / "scenario_matrix.yaml"
    else:
        matrix_path_resolved = Path(matrix_path)
        if not matrix_path_resolved.is_absolute():
            matrix_path_resolved = project_root / matrix_path_resolved

    # Session directory
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = project_root / "logs" / "alpha_search_runtime" / session_id
    # Avoid cross-process contention on Windows: keep alpha_search adapter logs per session by default.
    if "ALPHA_SEARCH_LOG_DIR" not in os.environ:
        os.environ["ALPHA_SEARCH_LOG_DIR"] = str(session_dir / "aggregate")

    # Load config (fail-closed)
    config = load_matrix_config(matrix_path_resolved)

    # Setup logging
    logger = setup_logging(session_dir, log_level=log_level)

    logger.info(
        f"Alpha Search Standalone Domain starting\n"
        f"  matrix: {matrix_path_resolved}\n"
        f"  session: {session_dir}\n"
        f"  scenarios: {len([s for s in config.scenarios if s.enabled])} enabled\n"
        f"  parallelism: {config.runtime.parallelism}"
    )

    # Enter reactor
    await main_reactor(config, project_root, session_dir, logger)
