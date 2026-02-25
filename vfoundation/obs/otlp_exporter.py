"""
OTLP Exporter foundation — OpenTelemetry Protocol exporter stubs.

Provides ABC + NoopOTLPExporter for testing and placeholder wiring.
Real implementation will be added in Phase 14/15 when OTLP is activated.

Constitution §10: observability events must be exportable via OTLP.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SpanRecord:
    """Minimal OTLP span record for internal use."""
    trace_id: str
    span_id: str
    name: str
    rid: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status_ok: bool = True


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
