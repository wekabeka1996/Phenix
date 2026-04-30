from collections import defaultdict
from typing import Dict, Tuple
from threading import Lock

from apps.reference.domains.neocortex.contracts.failure_taxonomy import FailureOutcome, FailureOutcomeTaxonomy, FailureReasonCode
from apps.reference.telemetry.metrics import inc_neocortex_failure_outcome


class FailureLedger:
    def __init__(self):
        self._counts: Dict[Tuple[FailureOutcomeTaxonomy,
                                 FailureReasonCode], int] = defaultdict(int)
        self._lock = Lock()

    def record_failure(self, outcome: FailureOutcome) -> None:
        """
        Record a typed failure outcome.
        Note: Phase 7 will wire this directly into canonical prometheus metrics emission.
        """
        with self._lock:
            self._counts[(outcome.taxonomy, outcome.reason_code)] += 1
            inc_neocortex_failure_outcome(
                outcome.taxonomy.value,
                outcome.reason_code.value,
            )
            # In a real system, we'd also log via the standard logging layer or emit to a metrics sink

    def get_failure_counts(self) -> Dict[Tuple[FailureOutcomeTaxonomy, FailureReasonCode], int]:
        """Return a snapshot of current failure counts."""
        with self._lock:
            return dict(self._counts)

    def get_total_count(self) -> int:
        """Return the total number of recorded failures."""
        with self._lock:
            return sum(self._counts.values())

    def reset_failure_counts(self) -> None:
        """Reset counts. For test isolation only."""
        with self._lock:
            self._counts.clear()


# Global ledger instance for Phase 3 observability
failure_ledger = FailureLedger()
