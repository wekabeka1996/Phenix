"""
Why-chain coverage tool.

Analyzes WAL records or XAI records for a given rid and reports
coverage gaps in the why-chain (events with missing/weak WHY fields).

Constitution §7: every emitted event must carry a meaningful WHY.
This tool detects violations and computes a coverage score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WhyChainEntry:
    """Single entry in a why-chain analysis report."""
    step: int
    rid: str
    verb: str
    why: Optional[str]
    has_why: bool
    why_length: int


@dataclass
class WhyCoverageReport:
    """Coverage report for a request ID's why-chain."""
    rid: str
    total_events: int
    covered_events: int
    missing_why: List[WhyChainEntry] = field(default_factory=list)
    weak_why: List[WhyChainEntry] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        """Percentage of events with non-empty WHY (0.0–100.0)."""
        if self.total_events == 0:
            return 100.0
        return round(100.0 * self.covered_events / self.total_events, 2)

    @property
    def is_fully_covered(self) -> bool:
        """True if all events have a non-empty WHY."""
        return self.total_events > 0 and self.covered_events == self.total_events

    def passes_threshold(self, threshold_pct: float = 95.0) -> bool:
        """Blueprint 11.2: True if coverage_pct >= threshold_pct."""
        return self.coverage_pct >= threshold_pct

    @property
    def err_missing_why(self) -> List[str]:
        """Blueprint 11.2: List of verbs with missing WHY fields."""
        return [e.verb for e in self.missing_why]


# WHY_MIN_LENGTH: WHY strings shorter than this are considered "weak"
WHY_MIN_LENGTH: int = 5


def analyze_why_chain(
    records: List[Dict[str, Any]],
    rid: Optional[str] = None,
    why_min_length: int = WHY_MIN_LENGTH,
) -> WhyCoverageReport:
    """
    Analyze why-chain coverage from a list of event records.

    Args:
        records: List of event dicts, each expected to have keys:
                 'rid', 'verb'/'op', 'why'. Missing fields default to empty.
        rid: Expected RID label for the report (auto-detected if None).
        why_min_length: Minimum WHY length to count as "covered". Default=5.

    Returns:
        WhyCoverageReport with coverage statistics and gap lists.
    """
    if not records:
        return WhyCoverageReport(
            rid=rid or "", total_events=0, covered_events=0
        )

    detected_rid = rid or (records[0].get("rid") or "")
    entries: List[WhyChainEntry] = []

    for step, record in enumerate(records):
        why_val = record.get("why") or ""
        verb = record.get("verb") or record.get("op") or "UNKNOWN"
        rec_rid = record.get("rid") or detected_rid
        has_why = len(why_val) >= why_min_length
        entry = WhyChainEntry(
            step=step,
            rid=rec_rid,
            verb=str(verb),
            why=why_val if why_val else None,
            has_why=has_why,
            why_length=len(why_val),
        )
        entries.append(entry)

    covered = [e for e in entries if e.has_why]
    missing = [e for e in entries if not e.why]
    weak = [e for e in entries if e.why and not e.has_why]

    return WhyCoverageReport(
        rid=detected_rid,
        total_events=len(entries),
        covered_events=len(covered),
        missing_why=missing,
        weak_why=weak,
    )


def measure_why_coverage(
    events: List[Dict[str, Any]],
    rid: Optional[str] = None,
) -> WhyCoverageReport:
    """Blueprint 11.2: Convenience wrapper — delegates to analyze_why_chain."""
    return analyze_why_chain(events, rid=rid)
