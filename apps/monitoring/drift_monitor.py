"""Drift Monitor for Shadow-Mode Validation (FSMP-P1-T03).

Off-path only:
- Used by CLI/debug tooling and tests.
- Not imported by runtime domains.

Computes drift% and confusion matrix (TP/FP/FN/TN) between:
- Shadow decisions (DEC:OPEN/CLOSE) from FSM
- Actual events (EVT:ORDER_PLACED/FILL/CANCELLED) from ACL stub
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from vfoundation.config import config

from apps.reference.utils.accessors import dget


@dataclass
class ConfusionMatrix:
    """Confusion matrix for shadow-mode validation."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def drift_pct(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        if total == 0:
            return 0.0
        return ((self.fp + self.fn) / total) * 100.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        if total == 0:
            return 0.0
        return ((self.tp + self.tn) / total) * 100.0

    def to_dict(self) -> Dict[str, Any]:
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
    rid: str
    symbol: str
    type: str
    decision_verb: Optional[str] = None
    event_verb: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
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
    confusion: ConfusionMatrix
    mismatches: List[Mismatch] = field(default_factory=list)
    computed_at: float = field(default_factory=time.time)
    records_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confusion": self.confusion.to_dict(),
            "mismatches": [m.to_dict() for m in self.mismatches[:5]],
            "computed_at": self.computed_at,
            "records_processed": self.records_processed,
        }


def compute_drift(
    decisions: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    time_window_sec: Optional[float] = None,
) -> DriftReport:
    if time_window_sec is None:
        time_window_sec = config.drift_time_window_sec

    confusion = ConfusionMatrix()
    mismatches: List[Mismatch] = []

    event_index: Dict[str, List[Dict[str, Any]]] = {}
    for evt in events:
        rid = dget(evt, "rid", "unknown")
        event_index.setdefault(rid, []).append(evt)

    matched_events = set()

    for dec in decisions:
        verb = dget(dec, "verb", "")
        if verb not in ("OPEN", "CLOSE"):
            continue

        pld_raw = dec.get("pld")
        pld = pld_raw if isinstance(pld_raw, dict) else {}
        symbol = dget(pld, "symbol", "UNKNOWN")
        rid = dget(dec, "rid", "unknown")
        dec_ts = dec["timestamp"] if "timestamp" in dec else time.time()

        candidate_events = event_index.get(rid, [])

        matched = False
        for evt in candidate_events:
            evt_ts = evt["timestamp"] if "timestamp" in evt else time.time()
            evt_verb = dget(evt, "verb", "")

            if abs(evt_ts - dec_ts) > time_window_sec:
                continue

            if verb == "OPEN" and evt_verb in ("ORDER_PLACED", "FILL"):
                confusion.tp += 1
                matched = True
                matched_events.add(id(evt))
                break

            if verb == "CLOSE" and evt_verb in ("CANCELLED", "FILL"):
                if evt_verb == "FILL":
                    evt_pld_raw = evt.get("pld")
                    evt_pld = evt_pld_raw if isinstance(evt_pld_raw, dict) else {}
                    reduce_only = evt_pld["reduceOnly"] if "reduceOnly" in evt_pld else False
                    if "reduceOnly" in evt_pld and not reduce_only:
                        continue

                confusion.tp += 1
                matched = True
                matched_events.add(id(evt))
                break

        if not matched:
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

    return DriftReport(
        confusion=confusion,
        mismatches=mismatches,
        computed_at=time.time(),
        records_processed=len(decisions) + len(events),
    )


def aggregate_drift_metrics(reports: List[DriftReport]) -> Dict[str, Any]:
    if not reports:
        return {
            "confusion_tp_total": 0,
            "confusion_fp_total": 0,
            "confusion_fn_total": 0,
            "confusion_tn_total": 0,
            "drift_pct_last": 0.0,
            "accuracy_last": 0.0,
        }

    total_tp = sum(r.confusion.tp for r in reports)
    total_fp = sum(r.confusion.fp for r in reports)
    total_fn = sum(r.confusion.fn for r in reports)
    total_tn = sum(r.confusion.tn for r in reports)

    last = reports[-1]
    return {
        "confusion_tp_total": total_tp,
        "confusion_fp_total": total_fp,
        "confusion_fn_total": total_fn,
        "confusion_tn_total": total_tn,
        "drift_pct_last": float(last.confusion.drift_pct),
        "accuracy_last": float(last.confusion.accuracy),
    }
