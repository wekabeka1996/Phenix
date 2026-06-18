import importlib
import json
import sys
import time
from pathlib import Path

import pytest


def test_order_logger_lazy_import_no_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "")

    sys.modules.pop("apps.reference.telemetry.order_logger", None)
    module = importlib.import_module("apps.reference.telemetry.order_logger")

    expected_root = tmp_path / "repo_root"
    expected_root.mkdir()
    monkeypatch.setattr(module, "_repo_root", lambda: expected_root)

    runtime_cwd = tmp_path / "runtime_cwd"
    runtime_cwd.mkdir()
    monkeypatch.chdir(runtime_cwd)

    log_path = expected_root / "logs" / "order_log_v1.jsonl"
    cwd_relative_path = runtime_cwd / "logs" / "order_log_v1.jsonl"
    assert not log_path.exists()

    module.order_logger.write({"event_type": "TEST_EVENT"})

    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8")
    assert not cwd_relative_path.exists()


def test_audit_logger_timestamp_epoch(tmp_path):
    from apps.reference.telemetry.audit_logger import audit_logger

    if audit_logger.file_handle:
        audit_logger.file_handle.close()
        audit_logger.file_handle = None
    audit_logger.log_dir = Path(tmp_path)
    audit_logger.current_file = None

    start_ms = int(time.time() * 1000)
    audit_logger.log_event("TEST_EVT", foo="bar")
    end_ms = int(time.time() * 1000)

    log_path = tmp_path / "aurora_events.jsonl"
    data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])

    assert data["ts_ms"] >= start_ms
    assert data["ts_ms"] <= end_ms + 1000
    assert data["ts_ms"] > 1_000_000_000_000

    if audit_logger.file_handle:
        audit_logger.file_handle.close()
        audit_logger.file_handle = None


def test_order_logger_schema_path_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from apps.reference.telemetry.order_logger import OrderLoggerV1

    log_file = tmp_path / "order_log.jsonl"
    logger = OrderLoggerV1(log_file=str(log_file))

    assert log_file.exists()
    assert "event_type" in logger.schema.get("properties", {})


def test_order_logger_init_preserves_existing_records(tmp_path):
    from apps.reference.telemetry.order_logger import OrderLoggerV1

    log_file = tmp_path / "order_log.jsonl"
    existing_entry = {
        "rid": "existing-rid",
        "event_type": "ORDER_PLACED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "source_fsm": "seed",
    }
    log_file.write_text(json.dumps(existing_entry) + "\n", encoding="utf-8")

    logger = OrderLoggerV1(log_file=str(log_file))
    logger.write(
        {
            "rid": "follow-up-rid",
            "event_type": "ORDER_FILLED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "source_fsm": "seed",
        }
    )

    lines = [json.loads(line) for line in log_file.read_text(
        encoding="utf-8").splitlines()]

    assert [line["event_type"] for line in lines] == [
        "ORDER_PLACED",
        "BOOT",
        "ORDER_FILLED",
    ]
    assert lines[0]["rid"] == "existing-rid"
    assert lines[2]["rid"] == "follow-up-rid"


def test_order_logger_rotates_and_retains_at_least_thirty_days(tmp_path, monkeypatch):
    from apps.reference.telemetry.order_logger import OrderLoggerV1, iter_order_log_files

    monkeypatch.setenv("ORDER_LOG_ROTATE_BYTES", "1")
    monkeypatch.setenv("ORDER_LOG_RETENTION_DAYS", "7")
    log_file = tmp_path / "order_log_v1.jsonl"
    logger = OrderLoggerV1(log_file=log_file)

    logger.write({
        "rid": "rotated-event",
        "event_type": "ORDER_PLACED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "source_fsm": "test",
    })

    files = iter_order_log_files(log_file)
    assert logger.retention_days == 30
    assert files[-1] == log_file
    assert len(files) == 2
    assert json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])[
        "event_type"] == "BOOT"
    assert json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])[
        "rid"] == "rotated-event"
