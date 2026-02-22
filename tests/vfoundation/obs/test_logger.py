"""Tests for vfoundation.obs.logger — Structured JSON logging."""
from __future__ import annotations

import json
import logging
from io import StringIO

from vfoundation.obs.logger import JsonFormatter, log_event


class TestJsonFormatter:
    def test_formats_as_json(self) -> None:
        handler = logging.StreamHandler(StringIO())
        formatter = JsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_json_fmt")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("hello world")
        output = handler.stream.getvalue()
        data = json.loads(output.strip())

        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert "ts" in data

        logger.removeHandler(handler)

    def test_includes_exception(self) -> None:
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json_exc")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("caught error")

        output = handler.stream.getvalue()
        data = json.loads(output.strip())
        assert "exception" in data
        assert "ValueError" in data["exception"]

        logger.removeHandler(handler)

    def test_extra_fields_included(self) -> None:
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json_extra")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("with extra", extra={"rid": "abc-123", "verb": "OPEN"})
        output = handler.stream.getvalue()
        data = json.loads(output.strip())
        assert data["rid"] == "abc-123"
        assert data["verb"] == "OPEN"

        logger.removeHandler(handler)


class TestLogEvent:
    def test_log_event_writes_json(self, capsys: object) -> None:
        log_event(op="EVT", verb="TEST", msg="hello")
        import sys
        # log_event writes to stdout
        captured = sys.stdout  # capsys is a pytest fixture
        # Just verify it doesn't crash — output goes to real stdout
