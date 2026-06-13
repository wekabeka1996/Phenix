"""Backward-compat shim for apps.reference.domains.decision_making.readiness_gates.

The active readiness-gate implementation lives in gates.readiness_gates and
continues to own readiness checks around ops-driven panic_killswitch blocking.
"""

from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates

__all__ = ["ReadinessGates"]
