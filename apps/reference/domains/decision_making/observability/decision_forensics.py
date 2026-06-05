"""Decision Forensics Auditor module.

This module is a completely read-only, decoupled utility designed to audit
decision inputs, feature freshness, regime lag, score lineage, and gateway
execution trails at decision time. It does NOT interfere with runtime trading paths.
"""
from __future__ import annotations

import decimal
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    """Results of the feature and regime freshness check."""
    features_ts_ms: Optional[int]
    decision_ts_ms: Optional[int]
    features_age_ms: Optional[int]
    features_within_deadline: bool
    deadline_ms: Optional[int]
    
    regime_ts_ms: Optional[int]
    regime_age_ms: Optional[int]
    regime_age_bars: Optional[float]


@dataclass(frozen=True, slots=True)
class LineageValidationResult:
    """Validation outcome for score lineage records."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    records_checked: int = 0


@dataclass(frozen=True, slots=True)
class ForensicsAuditReport:
    """Unified forensics audit report for a single decision event."""
    symbol: str
    strategy_id: str
    decision_id: Optional[str]
    side: str
    ts_ms: int
    
    freshness: FreshnessResult
    lineage: LineageValidationResult
    
    # Gateway gate execution
    gates_traced: List[Dict[str, Any]]
    all_gates_passed: bool
    
    # Verdict / Policy indicators
    policy_label: str
    verdict_confidence: Optional[float]
    raw_score: Optional[float]
    decision_score: Optional[float]
    active_threshold: Optional[float]


class DecisionForensicsAuditor:
    """Read-only diagnostic auditor for strategy decisions."""

    @staticmethod
    def audit_decision(
        *,
        symbol: str,
        strategy_id: str,
        payload: Dict[str, Any],
        freshness_deadline_window_ms: int = 30000,
        bar_duration_sec: int = 180,
    ) -> ForensicsAuditReport:
        """Analyze a decision footprint payload and produce a structured forensics report.

        Supports auditing from:
        - `EVT:STRATEGY_SIGNAL_PRODUCED` payloads
        - `shadow_entry_plan` files
        - `verdict` log outputs joined with envelope files
        """
        # 1. Resolve timestamps
        ts_ms = int(payload.get("ts_ms") or payload.get("decision_ts_ms") or 0)
        
        # 2. Extract scoring & lineage details
        scoring = payload.get("scoring") or {}
        if not isinstance(scoring, dict):
            scoring = {}
            
        psi_vector = scoring.get("psi_vector") or {}
        if not isinstance(psi_vector, dict):
            psi_vector = {}

        # 3. Perform Freshness Audit
        features_ts_ms = None
        # Try to extract feature timestamp
        if "features_ts_ms" in payload:
            features_ts_ms = payload["features_ts_ms"]
        elif "features_ts_ms" in psi_vector:
            features_ts_ms = psi_vector["features_ts_ms"]
        elif "features" in payload and isinstance(payload["features"], dict):
            features_ts = payload["features"].get("ts") or payload["features"].get("ts_ms")
            if features_ts is not None:
                try:
                    features_ts_ms = int(features_ts)
                except (ValueError, TypeError):
                    pass
                    
        features_age_ms = None
        features_within_deadline = True
        deadline_ms = None
        if features_ts_ms is not None and ts_ms > 0:
            features_age_ms = ts_ms - features_ts_ms
            deadline_ms = features_ts_ms + freshness_deadline_window_ms
            features_within_deadline = ts_ms <= deadline_ms

        # Regime lag
        regime_ts_ms = None
        # Try to find regime timestamp
        if "regime_ts_ms" in payload:
            regime_ts_ms = payload["regime_ts_ms"]
        elif "regime_ts_ms" in psi_vector:
            regime_ts_ms = psi_vector["regime_ts_ms"]
        elif "features" in payload and isinstance(payload["features"], dict):
            regime_ts_ms = payload["features"].get("regime_ts_ms")
            
        regime_age_ms = None
        regime_age_bars = None
        if regime_ts_ms is not None and ts_ms > 0:
            try:
                regime_ts_ms = int(regime_ts_ms)
                regime_age_ms = ts_ms - regime_ts_ms
                if bar_duration_sec > 0:
                    regime_age_bars = round(regime_age_ms / (bar_duration_sec * 1000), 4)
            except (ValueError, TypeError):
                regime_ts_ms = None

        freshness = FreshnessResult(
            features_ts_ms=features_ts_ms,
            decision_ts_ms=ts_ms,
            features_age_ms=features_age_ms,
            features_within_deadline=features_within_deadline,
            deadline_ms=deadline_ms,
            regime_ts_ms=regime_ts_ms,
            regime_age_ms=regime_age_ms,
            regime_age_bars=regime_age_bars,
        )

        # 4. Perform Score Lineage Audit
        lineage_records = []
        score_lineage_block = payload.get("score_lineage") or scoring.get("score_lineage") or {}
        if isinstance(score_lineage_block, dict) and "records" in score_lineage_block:
            lineage_records = score_lineage_block.get("records") or []
        elif isinstance(payload.get("strategy_lineage_records"), list):
            lineage_records = payload["strategy_lineage_records"]
            
        lineage_errors = []
        records_checked = 0
        if isinstance(lineage_records, list):
            for rec in lineage_records:
                if not isinstance(rec, dict):
                    continue
                records_checked += 1
                fld = rec.get("field")
                val = rec.get("value")
                scale = rec.get("scale")
                
                # Check 1: Key fields are populated
                if not fld or val is None or not scale:
                    lineage_errors.append(fld or f"record_index_{records_checked-1}")
                    continue
                
                # Check 2: Values are finite floats/numbers
                try:
                    num_val = float(val)
                    if not math.isfinite(num_val):
                        lineage_errors.append(f"non_finite:{fld}")
                except (ValueError, TypeError):
                    lineage_errors.append(f"invalid_float:{fld}")

        lineage_valid = len(lineage_errors) == 0
        lineage = LineageValidationResult(
            valid=lineage_valid,
            errors=lineage_errors,
            records_checked=records_checked,
        )

        # 5. Extract Gateway Trace Details
        gates_traced = []
        all_gates_passed = True
        gate_trace = payload.get("gate_trace") or payload.get("trace") or {}
        if isinstance(gate_trace, dict) and "gates" in gate_trace:
            gates_traced = gate_trace["gates"]
            all_gates_passed = gate_trace.get("passed", True)
        elif isinstance(payload.get("gates"), list):
            gates_traced = payload["gates"]
            all_gates_passed = payload.get("passed", True)

        # 6. Extract Policy / Verdict Context
        policy_label = payload.get("policy_label") or payload.get("matched_surface_label") or "UNKNOWN"
        verdict_confidence = payload.get("confidence") or payload.get("verdict_confidence")
        if verdict_confidence is not None:
            try:
                verdict_confidence = float(verdict_confidence)
            except (ValueError, TypeError):
                verdict_confidence = None

        raw_score = payload.get("raw_score") or scoring.get("raw_score")
        if raw_score is not None:
            try:
                raw_score = float(raw_score)
            except (ValueError, TypeError):
                raw_score = None

        decision_score = payload.get("decision_score") or scoring.get("decision_score")
        if decision_score is not None:
            try:
                decision_score = float(decision_score)
            except (ValueError, TypeError):
                decision_score = None

        active_threshold = payload.get("active_threshold")
        if active_threshold is not None:
            try:
                active_threshold = float(active_threshold)
            except (ValueError, TypeError):
                active_threshold = None

        return ForensicsAuditReport(
            symbol=symbol,
            strategy_id=strategy_id,
            decision_id=payload.get("decision_id") or payload.get("plan_id"),
            side=payload.get("side") or payload.get("entry_side") or "UNKNOWN",
            ts_ms=ts_ms,
            freshness=freshness,
            lineage=lineage,
            gates_traced=list(gates_traced),
            all_gates_passed=all_gates_passed,
            policy_label=policy_label,
            verdict_confidence=verdict_confidence,
            raw_score=raw_score,
            decision_score=decision_score,
            active_threshold=active_threshold,
        )
