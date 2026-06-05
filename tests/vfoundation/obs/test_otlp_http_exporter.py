"""Tests for HttpOTLPExporter — Phase 17.5."""
import json
from unittest.mock import MagicMock, patch

import pytest

from vfoundation.obs.otlp_exporter import HttpOTLPExporter, SpanRecord


def _make_span(name: str = "test_span") -> SpanRecord:
    return SpanRecord(
        trace_id="trace123", span_id="span456", name=name, rid="rid789"
    )


class TestHttpOTLPExporter:
    """Phase 17.5: HttpOTLPExporter tests."""

    def test_buffers_spans(self):
        """export() buffers spans without sending."""
        exporter = HttpOTLPExporter(endpoint="http://localhost:4318/v1/traces")
        exporter.export([_make_span("a"), _make_span("b")])
        assert exporter.buffer_size == 2
        assert exporter.total_exported == 0

    @patch("vfoundation.obs.otlp_exporter.urllib.request.urlopen")
    def test_flush_sends_batch(self, mock_urlopen: MagicMock):
        """flush() sends buffered spans via HTTP POST."""
        mock_urlopen.return_value = MagicMock()
        exporter = HttpOTLPExporter(endpoint="http://localhost:4318/v1/traces")
        exporter.export([_make_span("a"), _make_span("b")])
        flushed = exporter.flush()

        assert flushed == 2
        assert exporter.buffer_size == 0
        assert exporter.total_exported == 2
        mock_urlopen.assert_called_once()

        # Verify the payload is valid JSON with correct structure
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        payload = json.loads(request_obj.data)
        assert len(payload) == 2
        assert payload[0]["name"] == "a"
        assert payload[1]["name"] == "b"

    @patch("vfoundation.obs.otlp_exporter.urllib.request.urlopen")
    def test_shutdown_flushes(self, mock_urlopen: MagicMock):
        """shutdown() flushes buffer before marking as shut down."""
        mock_urlopen.return_value = MagicMock()
        exporter = HttpOTLPExporter(endpoint="http://localhost:4318/v1/traces")
        exporter.export([_make_span()])
        exporter.shutdown()

        assert exporter.is_healthy is False
        assert exporter.total_exported == 1
        assert exporter.buffer_size == 0
