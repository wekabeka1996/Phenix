"""
DR timing verification (Phase 12.2).

Measures and verifies Disaster Recovery timing SLOs:
- WAL flush latency
- Checkpoint interval
- Recovery time from a simulated failure

All SLO thresholds must be passed as parameters — no hardcoded values.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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


@dataclass
class DRRecoveryResult:
    """Result of a simulated DR recovery (Blueprint 12.2)."""

    recovery_time_ms: float
    data_loss_events: int
    data_loss_window_ms: float
    rto_ok: bool
    rpo_ok: bool


def simulate_dr_recovery(
    wal_dir: Path,
    snapshot_dir: Path,
    failure_ts: int,
    rto_target_ms: float = 900_000.0,
    rpo_target_ms: float = 60_000.0,
) -> DRRecoveryResult:
    """Blueprint 12.2: Simulate DR by loading snapshot + replaying WAL.

    1. Load latest snapshot from snapshot_dir (*.json, sorted by name).
    2. Read WAL events from wal_dir (*.jsonl, parse lines as JSON).
    3. Filter events with ts > snapshot_ts and ts <= failure_ts.
    4. Measure recovery_time_ms as perf_counter delta of read+replay.
    5. data_loss_events = events between last_checkpoint_ts and failure_ts.
    6. rto_ok = recovery_time_ms <= rto_target_ms.
    7. rpo_ok = data_loss_window_ms <= rpo_target_ms.
    """
    start = time.perf_counter()

    # 1. Load latest snapshot
    snapshot_ts: int = 0
    snapshots = sorted(snapshot_dir.glob("*.json"))
    if snapshots:
        try:
            data = json.loads(snapshots[-1].read_text(encoding="utf-8"))
            snapshot_ts = int(data.get("ts", 0))
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    # 2. Read WAL events
    wal_events: List[Dict[str, Any]] = []
    for wal_file in sorted(wal_dir.glob("*.jsonl")):
        for line in wal_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                wal_events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # 3. Filter events in recovery window
    replay_events = [
        e for e in wal_events
        if snapshot_ts < int(e.get("ts", 0)) <= failure_ts
    ]

    # 4. Measure recovery time
    recovery_time_ms = (time.perf_counter() - start) * 1000.0

    # 5. Compute data loss
    if replay_events:
        last_event_ts = max(int(e.get("ts", 0)) for e in replay_events)
        data_loss_window_ms = float(failure_ts - last_event_ts)
        data_loss_events = sum(
            1 for e in wal_events if int(e.get("ts", 0)) > failure_ts
        )
    else:
        data_loss_window_ms = float(failure_ts - snapshot_ts) if failure_ts > snapshot_ts else 0.0
        data_loss_events = 0

    # 6-7. Check SLOs
    return DRRecoveryResult(
        recovery_time_ms=recovery_time_ms,
        data_loss_events=data_loss_events,
        data_loss_window_ms=data_loss_window_ms,
        rto_ok=recovery_time_ms <= rto_target_ms,
        rpo_ok=data_loss_window_ms <= rpo_target_ms,
    )
