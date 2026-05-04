"""Tests for InMemoryOTLPExporter — Phase 11.3."""
import threading

import pytest

from vfoundation.obs.otlp_exporter import InMemoryOTLPExporter, SpanRecord


def _make_span(name: str = "test_span") -> SpanRecord:
    return SpanRecord(
        trace_id="trace123", span_id="span456", name=name, rid="rid789"
    )


class TestInMemoryOTLPExporter:
    """Phase 11.3: InMemoryOTLPExporter tests."""

    def test_stores_exported_spans(self):
        """export() stores spans in .spans property."""
        exporter = InMemoryOTLPExporter()
        exporter.export([_make_span("a"), _make_span("b")])
        assert len(exporter.spans) == 2
        assert exporter.spans[0].name == "a"
        assert exporter.spans[1].name == "b"

    def test_clear_resets_spans(self):
        """clear() empties the stored spans."""
        exporter = InMemoryOTLPExporter()
        exporter.export([_make_span()])
        assert len(exporter.spans) == 1
        exporter.clear()
        assert len(exporter.spans) == 0

    def test_is_healthy_always_true(self):
        """is_healthy returns True even after shutdown."""
        exporter = InMemoryOTLPExporter()
        assert exporter.is_healthy is True
        exporter.shutdown()
        assert exporter.is_healthy is True

    def test_thread_safety(self):
        """Concurrent exports should not lose spans."""
        exporter = InMemoryOTLPExporter()
        errors: list = []

        def writer(n: int) -> None:
            try:
                for i in range(100):
                    exporter.export([_make_span(f"t{n}_s{i}")])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(exporter.spans) == 400
