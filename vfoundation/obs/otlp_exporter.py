"""
OTLP Exporter foundation — OpenTelemetry Protocol exporter stubs.

Provides ABC + NoopOTLPExporter for testing and placeholder wiring.
HttpOTLPExporter provides buffered HTTP POST export (Phase 17.5).

Constitution §10: observability events must be exportable via OTLP.
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.request
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

LOG = logging.getLogger(__name__)


@dataclass
class SpanRecord:
    """Minimal OTLP span record for internal use."""
    trace_id: str
    span_id: str
    name: str
    rid: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status_ok: bool = True


@dataclass
class MetricRecord:
    """Blueprint 11.3: Metric record for OTLP metric export."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


class OTLPExporter(ABC):
    """
    Abstract base class for OTLP span exporters.

    Implementations must be safe to call from threads.
    All methods are fire-and-forget (no return value on export).
    """

    @abstractmethod
    def export(self, spans: List[SpanRecord]) -> None:
        """Export a batch of spans to the OTLP endpoint."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Flush pending spans and release resources."""
        ...

    @property
    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the exporter is operational."""
        ...

    def export_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> bool:
        """Export a single metric. Default no-op returns False.

        Blueprint 11.3: dual export_span/export_metric API surface.
        Subclasses may override to store or forward metrics.
        """
        return False


class NoopOTLPExporter(OTLPExporter):
    """
    No-op OTLP exporter for testing and environments without OTLP backend.

    Silently discards all spans. Tracks export_count for test assertions.
    """

    def __init__(self) -> None:
        self._export_count: int = 0
        self._shutdown_called: bool = False

    def export(self, spans: List[SpanRecord]) -> None:
        """Discard spans, increment export counter."""
        self._export_count += len(spans)

    def shutdown(self) -> None:
        """Mark as shut down."""
        self._shutdown_called = True

    @property
    def is_healthy(self) -> bool:
        """NoopOTLPExporter is always healthy."""
        return not self._shutdown_called

    @property
    def export_count(self) -> int:
        """Total number of spans exported (for test assertions)."""
        return self._export_count

    def export_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> bool:
        """Noop accepts metrics silently."""
        return True


class InMemoryOTLPExporter(OTLPExporter):
    """
    In-memory OTLP exporter for testing.

    Stores all exported spans in a thread-safe list for test assertions.
    Phase 11.3: Blueprint requirement for test-harness exporter.
    """

    def __init__(self) -> None:
        self._spans: List[SpanRecord] = []
        self._metrics: List[MetricRecord] = []
        self._lock = threading.Lock()

    def export(self, spans: List[SpanRecord]) -> None:
        """Store spans in memory."""
        with self._lock:
            self._spans.extend(spans)

    def shutdown(self) -> None:
        """No-op for in-memory exporter."""
        pass

    @property
    def is_healthy(self) -> bool:
        """Always healthy."""
        return True

    @property
    def spans(self) -> List[SpanRecord]:
        """Return a copy of stored spans for test assertions."""
        with self._lock:
            return list(self._spans)

    def clear(self) -> None:
        """Reset stored spans and metrics."""
        with self._lock:
            self._spans.clear()
            self._metrics.clear()

    def export_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> bool:
        """Store metric in memory for test assertions."""
        with self._lock:
            self._metrics.append(MetricRecord(name=name, value=value, labels=labels or {}))
        return True

    @property
    def metrics(self) -> List[MetricRecord]:
        """Thread-safe snapshot of stored metrics."""
        with self._lock:
            return list(self._metrics)


class HttpOTLPExporter(OTLPExporter):
    """
    HTTP-based OTLP exporter with buffering and batch flush.

    Phase 17.5: Sends spans as JSON via urllib POST.
    Thread-safe with internal Lock.
    """

    def __init__(
        self,
        endpoint: str,
        max_buffer: int = 1000,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._endpoint = endpoint
        self._buffer: Deque[SpanRecord] = deque(maxlen=max_buffer)
        self._headers = headers or {}
        self._lock = threading.Lock()
        self._shutdown_called = False
        self._total_exported = 0
        self._total_errors = 0

    def export(self, spans: List[SpanRecord]) -> None:
        """Buffer spans for later flush."""
        with self._lock:
            for span in spans:
                self._buffer.append(span)

    def flush(self) -> int:
        """
        Send all buffered spans as a JSON batch via HTTP POST.

        Returns:
            Number of spans flushed.
        """
        with self._lock:
            if not self._buffer:
                return 0
            batch = list(self._buffer)
            self._buffer.clear()

        payload = json.dumps(
            [
                {
                    "trace_id": s.trace_id,
                    "span_id": s.span_id,
                    "name": s.name,
                    "rid": s.rid,
                    "attributes": s.attributes,
                    "status_ok": s.status_ok,
                }
                for s in batch
            ]
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                self._endpoint,
                data=payload,
                headers={"Content-Type": "application/json", **self._headers},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            self._total_exported += len(batch)
        except Exception as e:
            self._total_errors += 1
            LOG.warning(f"OTLP HTTP flush failed: {e}")
            # Re-buffer on failure (best-effort)
            with self._lock:
                for span in batch:
                    self._buffer.append(span)

        return len(batch)

    def shutdown(self) -> None:
        """Flush remaining buffer and mark as shut down."""
        self.flush()
        self._shutdown_called = True

    @property
    def is_healthy(self) -> bool:
        """Healthy if not shut down."""
        return not self._shutdown_called

    @property
    def buffer_size(self) -> int:
        """Current number of buffered spans."""
        with self._lock:
            return len(self._buffer)

    @property
    def total_exported(self) -> int:
        """Total spans successfully flushed."""
        return self._total_exported

    def export_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> bool:
        """Log metric for HTTP exporter (buffering metrics is out of scope)."""
        LOG.debug("HttpOTLPExporter.export_metric: %s=%s labels=%s", name, value, labels)
        return True
