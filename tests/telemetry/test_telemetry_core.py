import importlib
import json
import sys
import time
from pathlib import Path

import pytest


def test_order_logger_lazy_import_no_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENV", "")

    sys.modules.pop("apps.reference.telemetry.order_logger", None)
    module = importlib.import_module("apps.reference.telemetry.order_logger")

    log_path = tmp_path / "logs" / "order_log_v1.jsonl"
    assert not log_path.exists()

    module.order_logger.write({"event_type": "TEST_EVENT"})

    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8")


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
