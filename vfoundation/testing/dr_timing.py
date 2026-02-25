"""
DR timing verification (Phase 12.2).

Measures and verifies Disaster Recovery timing SLOs:
- WAL flush latency
- Checkpoint interval
- Recovery time from a simulated failure

All SLO thresholds must be passed as parameters — no hardcoded values.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class DRTimingResult:
    """Result of a DR timing measurement."""
    operation: str
    elapsed_ms: float
    slo_ms: float
    passed: bool
    message: str = ""

    @classmethod
    def measure(
        cls,
        operation: str,
        slo_ms: float,
        elapsed_ms: float,
    ) -> "DRTimingResult":
        passed = elapsed_ms <= slo_ms
        msg = f"{operation}: {elapsed_ms:.2f}ms {'<=' if passed else '>'} {slo_ms}ms SLO"
        return cls(
            operation=operation,
            elapsed_ms=elapsed_ms,
            slo_ms=slo_ms,
            passed=passed,
            message=msg,
        )


class DRTimingVerifier:
    """
    Verifies DR-related timing SLOs.

    Args:
        wal_flush_slo_ms: Max allowed WAL flush latency (default 10ms).
        checkpoint_slo_ms: Max allowed checkpoint latency (default 100ms).
        recovery_slo_ms: Max allowed recovery time (default 5000ms = 5s).
    """

    def __init__(
        self,
        wal_flush_slo_ms: float = 10.0,
        checkpoint_slo_ms: float = 100.0,
        recovery_slo_ms: float = 5_000.0,
    ) -> None:
        self.wal_flush_slo_ms = wal_flush_slo_ms
        self.checkpoint_slo_ms = checkpoint_slo_ms
        self.recovery_slo_ms = recovery_slo_ms
        self._results: list[DRTimingResult] = []

    def verify_wal_flush(self, elapsed_ms: float) -> DRTimingResult:
        """Verify WAL flush latency against SLO."""
        result = DRTimingResult.measure("wal_flush", self.wal_flush_slo_ms, elapsed_ms)
        self._results.append(result)
        return result

    def verify_checkpoint(self, elapsed_ms: float) -> DRTimingResult:
        """Verify checkpoint latency against SLO."""
        result = DRTimingResult.measure("checkpoint", self.checkpoint_slo_ms, elapsed_ms)
        self._results.append(result)
        return result

    def verify_recovery(self, elapsed_ms: float) -> DRTimingResult:
        """Verify recovery time against SLO."""
        result = DRTimingResult.measure("recovery", self.recovery_slo_ms, elapsed_ms)
        self._results.append(result)
        return result

    @property
    def all_passed(self) -> bool:
        """True if all measurements passed their SLOs."""
        return all(r.passed for r in self._results)

    @property
    def results(self) -> list[DRTimingResult]:
        """All measurement results."""
        return list(self._results)
