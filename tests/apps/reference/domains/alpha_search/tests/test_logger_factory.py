"""
T4: Logger Factory Tests
=========================

Tests for apps/reference/domains/alpha_search/runtime/logger_factory.py
8 tests covering scenario/aggregate loggers and score writers.
"""

import json
import logging
import pytest
from pathlib import Path

from apps.reference.domains.alpha_search.runtime.logger_factory import (
    ScenarioLoggerFactory,
    ScenarioScoreWriter,
)


@pytest.mark.unit
class TestScenarioLogger:
    """Tests for ScenarioLoggerFactory.create_scenario_logger."""

    def test_writes_to_file(self, tmp_path):
        """Log message appears in scenario.log."""
        logger = ScenarioLoggerFactory.create_scenario_logger(
            scenario_id="S_TEST",
            log_dir=tmp_path,
        )
        logger.info("test message")

        # Flush handlers
        for h in logger.handlers:
            h.flush()

        log_file = tmp_path / "S_TEST" / "scenario.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "test message" in content

        # Cleanup handlers
        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)

    def test_no_propagation(self, tmp_path):
        """propagate=False, no root logger pollution."""
        logger = ScenarioLoggerFactory.create_scenario_logger(
            scenario_id="S_NOPROP",
            log_dir=tmp_path,
        )
        assert logger.propagate is False

        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)

    def test_creates_directory(self, tmp_path):
        """Missing dirs created."""
        log_dir = tmp_path / "deep" / "nested"
        logger = ScenarioLoggerFactory.create_scenario_logger(
            scenario_id="S_DIR",
            log_dir=log_dir,
        )
        assert (log_dir / "S_DIR").exists()

        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)


@pytest.mark.unit
class TestAggregateLogger:
    """Tests for ScenarioLoggerFactory.create_aggregate_logger."""

    def test_writes_to_file(self, tmp_path):
        """Writes to aggregate/aggregate.log."""
        logger = ScenarioLoggerFactory.create_aggregate_logger(
            session_dir=tmp_path,
        )
        logger.info("aggregate msg")

        for h in logger.handlers:
            h.flush()

        log_file = tmp_path / "aggregate" / "aggregate.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "aggregate msg" in content

        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)


@pytest.mark.unit
class TestScenarioScoreWriter:
    """Tests for ScenarioScoreWriter."""

    def test_write_score_jsonl(self, tmp_path):
        """write_score() appends valid JSONL."""
        writer = ScenarioScoreWriter(scenario_id="S_TEST", log_dir=tmp_path)
        writer.write_score({"score": 0.15, "symbol": "BTCUSDT"})

        path = tmp_path / "S_TEST" / "scores.jsonl"
        assert path.exists()
        line = path.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["score"] == 0.15
        assert record["scenario_id"] == "S_TEST"
        assert "ts" in record

    def test_write_trade_jsonl(self, tmp_path):
        """write_trade() appends valid JSONL."""
        writer = ScenarioScoreWriter(scenario_id="S_TEST", log_dir=tmp_path)
        writer.write_trade({"pnl": 50.0, "side": "BUY"})

        path = tmp_path / "S_TEST" / "trades.jsonl"
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["pnl"] == 50.0

    def test_write_health_jsonl(self, tmp_path):
        """write_health() appends valid JSONL."""
        writer = ScenarioScoreWriter(scenario_id="S_TEST", log_dir=tmp_path)
        writer.write_health({"status": "healthy"})

        path = tmp_path / "S_TEST" / "health.jsonl"
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["status"] == "healthy"

    def test_count_property(self, tmp_path):
        """scores_written increments."""
        writer = ScenarioScoreWriter(scenario_id="S_TEST", log_dir=tmp_path)
        assert writer.scores_written == 0
        writer.write_score({"score": 0.1})
        writer.write_score({"score": 0.2})
        assert writer.scores_written == 2
