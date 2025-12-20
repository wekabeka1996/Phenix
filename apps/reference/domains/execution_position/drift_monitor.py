"""
Drift Monitor for Shadow-Mode Validation (FSMP-P1-T03).

Computes drift% and confusion matrix (TP/FP/FN/TN) between:
- Shadow decisions (DEC:OPEN/CLOSE) from FSM
- Actual events (EVT:ORDER_PLACED/FILL/CANCELLED) from ACL stub

Methodology:
- Group by symbol + RID (with optional time-window ±1s)
- DEC:OPEN → TP if matching EVT:ORDER_PLACED|FILL, else FP
- DEC:CLOSE → TP if matching EVT:CANCELLED|FILL(reduce), else FP
- EVT without matching DEC → FN
- No action/no event → TN
- drift_pct = (FP + FN) / (TP + FP + FN + TN) * 100

Off-path computation: processes WAL/fixtures, not hot-path.
"""

from __future__ import annotations
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from vfoundation.config import config

from apps.reference.utils.accessors import dget


@dataclass
class ConfusionMatrix:
    """Confusion matrix for shadow-mode validation."""

    tp: int = 0  # True Positive: DEC matched by EVT
    fp: int = 0  # False Positive: DEC without matching EVT
    fn: int = 0  # False Negative: EVT without matching DEC
    tn: int = 0  # True Negative: No action, no event

    @property
    def drift_pct(self) -> float:
        """Calculate drift percentage: (FP + FN) / total * 100."""
        total = self.tp + self.fp + self.fn + self.tn
        if total == 0:
            return 0.0
        return ((self.fp + self.fn) / total) * 100.0

    @property
    def accuracy(self) -> float:
        """Calculate accuracy: (TP + TN) / total * 100."""
        total = self.tp + self.fp + self.fn + self.tn
        if total == 0:
            return 0.0
        return ((self.tp + self.tn) / total) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict for metrics/debug."""
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "drift_pct": round(self.drift_pct, 2),
            "accuracy": round(self.accuracy, 2),
        }


@dataclass
class Mismatch:
    """Single mismatch record for drift_report."""

    rid: str
    symbol: str
    type: str  # "FP" or "FN"
    decision_verb: Optional[str] = None  # "OPEN" or "CLOSE" for FP
    event_verb: Optional[str] = None  # "ORDER_PLACED" etc for FN
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict."""
        return {
            "rid": self.rid,
            "symbol": self.symbol,
            "type": self.type,
            "decision_verb": self.decision_verb,
            "event_verb": self.event_verb,
            "timestamp": self.timestamp,
        }


@dataclass
class DriftReport:
    """Complete drift report for /debug endpoint."""

    confusion: ConfusionMatrix
    mismatches: List[Mismatch] = field(default_factory=list)
    computed_at: float = field(default_factory=time.time)
    records_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict for JSON response."""
        return {
            "confusion": self.confusion.to_dict(),
            "mismatches": [m.to_dict() for m in self.mismatches[:5]],  # Limit to 5
            "computed_at": self.computed_at,
            "records_processed": self.records_processed,
        }


def compute_drift(
    decisions: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    time_window_sec: Optional[float] = None,
) -> DriftReport:
    """
    Compute drift between shadow decisions and actual events.

    Args:
        decisions: List of DEC messages (op="DEC", verb="OPEN"|"CLOSE")
        events: List of EVT messages (op="EVT", verb="ORDER_PLACED"|"FILL"|"CANCELLED")
        time_window_sec: Time window for matching (uses config default if None)

    Returns:
        DriftReport with confusion matrix and mismatches
    """
    if time_window_sec is None:
        time_window_sec = config.drift_time_window_sec

    confusion = ConfusionMatrix()
    mismatches: List[Mismatch] = []

    # Index events by RID for fast lookup (symbol may be missing in DEC)
    event_index: Dict[str, List[Dict[str, Any]]] = {}
    for evt in events:
        rid = dget(evt, "rid", "unknown")
        if rid not in event_index:
            event_index[rid] = []
        event_index[rid].append(evt)

    # Track matched events to detect FN later
    matched_events = set()

    # Process decisions (DEC:OPEN/CLOSE) → check for matching events
    for dec in decisions:
        verb = dget(dec, "verb", "")
        if verb not in ("OPEN", "CLOSE"):
            continue  # Skip non-OPEN/CLOSE decisions

        pld_raw = dec.get("pld")
        pld = pld_raw if isinstance(pld_raw, dict) else {}
        symbol = dget(pld, "symbol", "UNKNOWN")
        rid = dget(dec, "rid", "unknown")
        dec_ts = dec["timestamp"] if "timestamp" in dec else time.time()

        # Look for matching events by RID
        candidate_events = event_index[rid] if rid in event_index else []

        matched = False
        for evt in candidate_events:
            evt_ts = evt["timestamp"] if "timestamp" in evt else time.time()
            evt_verb = dget(evt, "verb", "")

            # Check time window
            if abs(evt_ts - dec_ts) > time_window_sec:
                continue

            # Match OPEN → ORDER_PLACED|FILL
            if verb == "OPEN" and evt_verb in ("ORDER_PLACED", "FILL"):
                confusion.tp += 1
                matched = True
                matched_events.add(id(evt))
                break

            # Match CLOSE → CANCELLED|FILL(reduce)
            if verb == "CLOSE" and evt_verb in ("CANCELLED", "FILL"):
                # For FILL events, ensure it's actually a position-reducing fill
                if evt_verb == "FILL":
                    evt_pld_raw = evt.get("pld")
                    evt_pld = evt_pld_raw if isinstance(evt_pld_raw, dict) else {}
                    reduce_only = evt_pld["reduceOnly"] if "reduceOnly" in evt_pld else False
                    # If reduceOnly flag is present, it must be True for position closure
                    if "reduceOnly" in evt_pld and not reduce_only:
                        continue  # This FILL is not a position closure, skip matching
                    # If no reduceOnly flag but we have side info, we could check against position
                    # For now, assume FILL without reduceOnly=False is valid (backward compatibility)

                confusion.tp += 1
                matched = True
                matched_events.add(id(evt))
                break

        if not matched:
            # False Positive: decision without matching event
            confusion.fp += 1
            mismatches.append(
                Mismatch(
                    rid=rid,
                    symbol=symbol,
                    type="FP",
                    decision_verb=verb,
                    timestamp=dec_ts,
                )
            )

    # Process unmatched events → False Negatives
    for evt in events:
        if id(evt) not in matched_events:
            pld_raw = evt.get("pld")
            pld = pld_raw if isinstance(pld_raw, dict) else {}
            symbol = dget(pld, "symbol", "UNKNOWN")
            rid = dget(evt, "rid", "unknown")
            evt_verb = dget(evt, "verb", "")
            evt_ts = evt["timestamp"] if "timestamp" in evt else time.time()

            confusion.fn += 1
            mismatches.append(
                Mismatch(
                    rid=rid,
                    symbol=symbol,
                    type="FN",
                    event_verb=evt_verb,
                    timestamp=evt_ts,
                )
            )

    # TN: stub for now (requires baseline of "no action" states)
    # In shadow mode, TN ≈ periods where neither DEC nor EVT occurred
    # For simplicity, we'll keep TN=0 unless explicitly tracked

    return DriftReport(
        confusion=confusion,
        mismatches=mismatches,
        computed_at=time.time(),
        records_processed=len(decisions) + len(events),
    )


def aggregate_drift_metrics(reports: List[DriftReport]) -> Dict[str, Any]:
    """
    Aggregate multiple drift reports into summary metrics.

    Args:
        reports: List of DriftReport instances

    Returns:
        Dict with aggregated confusion metrics and latest drift_pct
    """
    if not reports:
        return {
            "confusion_tp_total": 0,
            "confusion_fp_total": 0,
            "confusion_fn_total": 0,
            "confusion_tn_total": 0,
            "drift_pct_last": 0.0,
            "accuracy_last": 0.0,
        }

    # Sum all confusion metrics
    total_tp = sum(r.confusion.tp for r in reports)
    total_fp = sum(r.confusion.fp for r in reports)
    total_fn = sum(r.confusion.fn for r in reports)
    total_tn = sum(r.confusion.tn for r in reports)

    # Use last report's drift_pct as "latest"
    last_report = reports[-1]

    return {
        "confusion_tp_total": total_tp,
        "confusion_fp_total": total_fp,
        "confusion_fn_total": total_fn,
        "confusion_tn_total": total_tn,
        "drift_pct_last": round(last_report.confusion.drift_pct, 2),
        "accuracy_last": round(last_report.confusion.accuracy, 2),
    }
