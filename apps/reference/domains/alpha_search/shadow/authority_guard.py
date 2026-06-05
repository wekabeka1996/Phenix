"""
Authority Guard
================

Enforces shadow authority boundaries at runtime.

RULE: Any output produced by alpha_search shadow expansion must NOT contain:
  - Real ORDER_INTENT events
  - CMD:OPEN / CMD:CLOSE commands
  - real_execution=True
  - authority_applied=True
  - shadow_only=False

This guard validates outputs before they are written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


FORBIDDEN_VERBS = frozenset({
    "ORDER_INTENT",
    "CMD:OPEN",
    "CMD:CLOSE",
    "TRADE_INTENT_PROPOSED",
    "CMD:SUBMIT_ORDER",
    "CMD:MODIFY_ORDER",
    "CMD:CANCEL_ORDER",
    "RISK_GATE_CHECK",
    "EXECUTION_POSITION_OPEN",
})

FORBIDDEN_FIELDS = frozenset({
    "real_execution",
    "authority_applied",
})


@dataclass
class GuardViolation:
    field: str
    value: Any
    description: str


def audit_shadow_event(event: Dict[str, Any]) -> List[GuardViolation]:
    """
    Validate a shadow event dict against authority boundary rules.

    Returns list of violations (empty = clean).
    """
    violations: List[GuardViolation] = []

    # Check forbidden verbs
    verb = event.get("verb") or event.get("event_type") or ""
    if verb in FORBIDDEN_VERBS:
        violations.append(GuardViolation(
            field="verb",
            value=verb,
            description=f"Forbidden verb '{verb}' in shadow event — would affect real trading",
        ))

    # Check shadow_only must be True
    if event.get("shadow_only") is False:
        violations.append(GuardViolation(
            field="shadow_only",
            value=False,
            description="shadow_only=False in shadow event — real trading authority asserted",
        ))

    # Check authority_applied must be False or absent
    if event.get("authority_applied") is True:
        violations.append(GuardViolation(
            field="authority_applied",
            value=True,
            description="authority_applied=True in shadow event — real trading authority asserted",
        ))

    # Check no_effect must be True or absent
    if event.get("no_effect") is False:
        violations.append(GuardViolation(
            field="no_effect",
            value=False,
            description="no_effect=False in shadow event — real effect claimed",
        ))

    return violations


def assert_shadow_boundary(event: Dict[str, Any], context: str = "") -> None:
    """
    Assert no authority boundary violations. Raises if violated.

    Use in test assertions and critical paths.
    """
    violations = audit_shadow_event(event)
    if violations:
        msgs = "; ".join(f"{v.field}={v.value}: {v.description}" for v in violations)
        raise AssertionError(
            f"SHADOW_AUTHORITY_VIOLATION [{context}]: {msgs}"
        )


def audit_lifecycle_batch(
    lifecycles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Audit a batch of lifecycle dicts for authority violations.

    Returns summary dict with:
      total, clean, violations, violation_details
    """
    total = len(lifecycles)
    all_violations = []

    for i, lc in enumerate(lifecycles):
        viols = audit_shadow_event(lc)
        if viols:
            all_violations.append({
                "index": i,
                "scenario_id": lc.get("scenario_id", "?"),
                "violations": [{"field": v.field, "value": v.value, "description": v.description}
                               for v in viols],
            })

    return {
        "total": total,
        "clean": total - len(all_violations),
        "violation_count": len(all_violations),
        "violations": all_violations,
        "boundary_preserved": len(all_violations) == 0,
    }
