"""
Scenario Logger Factory
=======================

Creates dedicated loggers per scenario with rotating file handlers.
Each scenario gets isolated log files with no cross-scenario write contention.

Log structure per scenario:
  <log_dir>/<scenario_id>/
    scores.jsonl     ΓÇö structured score events (JSON lines)
    scenario.log     ΓÇö human-readable debug log
"""

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional


class ScenarioLoggerFactory:
    """
    Factory for creating dedicated loggers per scenario.

    Each logger writes to isolated files under the scenario's log directory.
    Rotating handlers prevent unbounded growth.
    """

    @staticmethod
    def create_scenario_logger(
        scenario_id: str,
        log_dir: Path,
        max_bytes: int = 10_000_000,  # 10 MB
        backup_count: int = 5,
    ) -> logging.Logger:
        """
        Create a dedicated human-readable logger for a scenario.

        Writes to: <log_dir>/<scenario_id>/scenario.log
        """
        scenario_dir = log_dir / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(f"alpha_search.scenario.{scenario_id}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # no leaks to root

        log_file = scenario_dir / "scenario.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    @staticmethod
    def create_aggregate_logger(
        session_dir: Path,
        max_bytes: int = 20_000_000,  # 20 MB
        backup_count: int = 10,
    ) -> logging.Logger:
        """
        Create aggregate logger for cross-scenario events.

        Writes to: <session_dir>/aggregate/aggregate.log
        """
        agg_dir = session_dir / "aggregate"
        agg_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("alpha_search.aggregate")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        log_file = agg_dir / "aggregate.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger


class ScenarioScoreWriter:
    """
    Writes structured score events to per-scenario scores.jsonl.

    Thread-safe via immediate flush. No buffering across writes.
    """

    def __init__(self, scenario_id: str, log_dir: Path):
        self._scenario_id = scenario_id
        self._dir = log_dir / scenario_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._scores_path = self._dir / "scores.jsonl"
        self._trades_path = self._dir / "trades.jsonl"
        self._health_path = self._dir / "health.jsonl"
        self._count = 0

    def write_score(self, result: Dict[str, Any]) -> None:
        """Append a score result to scores.jsonl."""
        record = {
            "ts": time.time(),
            "scenario_id": self._scenario_id,
            **result,
        }
        self._append_jsonl(self._scores_path, record)
        self._count += 1

    def write_trade(self, trade: Dict[str, Any]) -> None:
        """Append a virtual trade to trades.jsonl."""
        record = {
            "ts": time.time(),
            "scenario_id": self._scenario_id,
            **trade,
        }
        self._append_jsonl(self._trades_path, record)

    def write_health(self, health: Dict[str, Any]) -> None:
        """Append a health event."""
        record = {
            "ts": time.time(),
            "scenario_id": self._scenario_id,
            **health,
        }
        self._append_jsonl(self._health_path, record)

    @staticmethod
    def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
        """Append a single JSON line with immediate flush."""
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
            f.flush()

    @property
    def scores_written(self) -> int:
        return self._count
