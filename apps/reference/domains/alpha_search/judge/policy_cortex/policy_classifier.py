"""
J6-S16 — Shadow Policy Classifier

Deterministic, stateless classifier that maps a SurfaceEvidenceRecord
to a PolicyClassifierResult.

Mapping (v1 fixed typed policy):

  REJECTED                   → REJECT_SURFACE
  FRAGILE                    → TRACK_ONLY  (with fragile flag)
  PROMISING_BUT_CONCENTRATED → TRACK_ONLY  (with concentration warning)
  INSUFFICIENT_SAMPLE        → NEEDS_MORE_EVIDENCE
  UNKNOWN (sentinel)         → UNKNOWN
  missing surface            → UNKNOWN

Classifier output must NOT grant advisory, action, or production authority.
authority_mode is hardcoded to 'shadow'; applied=False; advisory=False.

Why the mapping is a fixed typed policy (not YAML-configurable in v1):
  The mapping is a two-level hierarchy (label → output) with no
  numeric thresholds. Adding YAML configurability now would introduce
  complexity without benefit before J6-S17 forward feedback confirms
  any surface label is stable across time. A v2 config surface can be
  added once forward evidence justifies parameterisation.
"""

from __future__ import annotations

from typing import List, Optional

from apps.reference.domains.alpha_search.judge.policy_cortex.evidence_models import (
    PolicyClassifierResult,
    SurfaceEvidenceRecord,
)

# ──────────────────────────────────────────────────────────────
# Label → classifier output mapping (v1 fixed)
# ──────────────────────────────────────────────────────────────
_LABEL_TO_OUTPUT = {
    "REJECTED":                   "REJECT_SURFACE",
    "FRAGILE":                    "TRACK_ONLY",
    "PROMISING_BUT_CONCENTRATED": "TRACK_ONLY",
    "INSUFFICIENT_SAMPLE":        "NEEDS_MORE_EVIDENCE",
    "UNKNOWN":                    "UNKNOWN",
}

# Concentration threshold: if one_symbol_share_pct or one_tf_share_pct
# exceeds this, add a concentration_flag reason code.
_CONCENTRATION_THRESHOLD_PCT = 60.0


def classify_surface(
    record: SurfaceEvidenceRecord,
) -> PolicyClassifierResult:
    """Classify a surface evidence record into a shadow policy output.

    Args:
        record: A SurfaceEvidenceRecord from the registry.
                If the record has label=UNKNOWN (sentinel), output is UNKNOWN.

    Returns:
        PolicyClassifierResult with shadow posture invariants enforced.
    """
    label = record.label
    classifier_output = _LABEL_TO_OUTPUT.get(label, "UNKNOWN")

    reason_codes: List[str] = [f"surface_label:{label}"]

    if label == "REJECTED":
        reason_codes.append("rejected_surface:suppress_shadow_signal")

    elif label == "FRAGILE":
        reason_codes.append("fragile_surface:track_only_no_promotion")
        if record.late_avg_net_pnl is not None and record.late_avg_net_pnl < 0:
            reason_codes.append("late_split_negative:decay_detected")

    elif label == "PROMISING_BUT_CONCENTRATED":
        reason_codes.append("promising_but_concentrated:track_only_no_promotion")
        _append_concentration_codes(record, reason_codes)

    elif label == "INSUFFICIENT_SAMPLE":
        reason_codes.append("insufficient_sample:needs_more_evidence")

    elif label == "UNKNOWN":
        reason_codes.append("surface_not_found_in_registry:fail_closed_unknown")

    # Explicit safety attestation in reason codes
    reason_codes.append("authority:shadow_only")
    reason_codes.append("production_authority:false")

    limitations: List[str] = list(record.limitations)

    return PolicyClassifierResult(
        classifier_output=classifier_output,
        reason_codes=reason_codes,
        matched_surface_key=record.surface_key,
        matched_surface_label=label,
        evidence_version=record.evidence_version,
        source_artifact=record.source_artifact,
        limitations=limitations,
        authority_mode="shadow",
        applied=False,
        advisory=False,
        production_authority=False,
    )


def _append_concentration_codes(
    record: SurfaceEvidenceRecord,
    reason_codes: List[str],
) -> None:
    """Append concentration-related reason codes if thresholds exceeded."""
    if (
        record.one_symbol_share_pct is not None
        and record.one_symbol_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        reason_codes.append(
            f"symbol_concentration:{record.one_symbol_share_pct:.1f}pct_exceeds_threshold"
        )

    if (
        record.one_tf_share_pct is not None
        and record.one_tf_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        reason_codes.append(
            f"tf_concentration:{record.one_tf_share_pct:.1f}pct_exceeds_threshold"
        )

    if (
        record.one_day_share_pct is not None
        and record.one_day_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        reason_codes.append(
            f"day_concentration:{record.one_day_share_pct:.1f}pct_exceeds_threshold"
        )


def build_concentration_flags(record: SurfaceEvidenceRecord) -> List[str]:
    """Return a human-readable list of concentration flags for telemetry.

    Returns [] if no concentration is noteworthy (below threshold).
    Always returns a list (never raises).
    """
    flags: List[str] = []
    if record.label == "UNKNOWN":
        return flags

    if (
        record.one_symbol_share_pct is not None
        and record.one_symbol_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        flags.append(
            f"HIGH_SYMBOL_CONCENTRATION:{record.one_symbol_share_pct:.1f}%"
        )

    if (
        record.one_tf_share_pct is not None
        and record.one_tf_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        flags.append(
            f"HIGH_TF_CONCENTRATION:{record.one_tf_share_pct:.1f}%"
        )

    if (
        record.one_day_share_pct is not None
        and record.one_day_share_pct > _CONCENTRATION_THRESHOLD_PCT
    ):
        flags.append(
            f"HIGH_DAY_CONCENTRATION:{record.one_day_share_pct:.1f}%"
        )

    return flags
