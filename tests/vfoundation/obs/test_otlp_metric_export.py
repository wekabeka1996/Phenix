"""Tests for OTLP export_metric() — Blueprint 11.3 dual API surface."""
from __future__ import annotations

from vfoundation.obs.otlp_exporter import (
    InMemoryOTLPExporter,
    NoopOTLPExporter,
)


class TestOTLPMetricExport:
    def test_noop_export_metric_returns_true(self) -> None:
        """NoopOTLPExporter.export_metric() returns True (silently accepts)."""
        exp = NoopOTLPExporter()
        assert exp.export_metric("cpu_usage", 42.5, {"host": "node1"}) is True

    def test_inmemory_stores_metrics(self) -> None:
        """InMemoryOTLPExporter stores metrics for inspection."""
        exp = InMemoryOTLPExporter()
        exp.export_metric("latency_ms", 12.3, {"endpoint": "/api"})
        exp.export_metric("error_rate", 0.01)
        assert len(exp.metrics) == 2
        assert exp.metrics[0].name == "latency_ms"
        assert exp.metrics[0].value == 12.3
        assert exp.metrics[0].labels == {"endpoint": "/api"}
        assert exp.metrics[1].labels == {}

    def test_inmemory_clear_resets_metrics(self) -> None:
        """clear() resets both spans and metrics."""
        exp = InMemoryOTLPExporter()
        exp.export_metric("test", 1.0)
        assert len(exp.metrics) == 1
        exp.clear()
        assert len(exp.metrics) == 0
