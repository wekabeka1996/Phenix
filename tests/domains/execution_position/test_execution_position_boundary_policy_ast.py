"""
Phase 7 — Boundary Policy and Typing Hygiene

Tests for the BOUNDARY_POLICY.md enforcement in the execution_position domain.
These tests:
1. Verify BOUNDARY_POLICY.md exists and documents key forbidden patterns.
2. Enforce that NO NEW cross-peer violations are introduced beyond the
   documented baseline in BOUNDARY_POLICY.md.
3. Verify that key typed structures exist for execution truth classification.

Historical violations documented in BOUNDARY_POLICY.md are DEFERRED and grandfathered.
Any count increase over the baseline triggers a test failure.
"""
from __future__ import annotations

import re
from pathlib import Path

EP_DIR = Path("apps/reference/domains/execution_position")
FLOWS_MANAGE_DIR = EP_DIR / "flows" / "manage"
FLOWS_CLOSE_DIR = EP_DIR / "flows" / "close"
ORCHESTRATION_DIR = EP_DIR / "orchestration"
SIDECAR_DIR = EP_DIR / "sidecar"
STATE_DIR = EP_DIR / "state"
GUARDIAN_DIR = EP_DIR / "guardian"

# Extracted peer modules (not fsm.py itself)
PEER_MODULES = [
    FLOWS_MANAGE_DIR / "bracket_health.py",
    FLOWS_MANAGE_DIR / "bracket_ownership.py",
    ORCHESTRATION_DIR / "fill_ingress_coordinator.py",
    STATE_DIR / "startup_truth_orchestrator.py",
    STATE_DIR / "startup_reconstruction.py",
    SIDECAR_DIR / "position_policy_mediator.py",
    SIDECAR_DIR / "position_policy_sidecar.py",
    GUARDIAN_DIR / "order_guardian.py",
    FLOWS_CLOSE_DIR / "close_executor.py",
    EP_DIR / "exposure_manager.py",
    ORCHESTRATION_DIR / "event_handlers.py",
]


def _read_module(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _count_pattern(pattern: str, files: list[Path]) -> int:
    total = 0
    for f in files:
        content = _read_module(f)
        total += len(re.findall(pattern, content))
    return total


class TestBoundaryPolicyDocumentExists:
    """BOUNDARY_POLICY.md must exist and document forbidden patterns."""

    def test_boundary_policy_file_exists(self):
        policy = EP_DIR / "BOUNDARY_POLICY.md"
        assert policy.exists(), (
            "BOUNDARY_POLICY.md must exist in execution_position/ domain root"
        )

    def test_boundary_policy_documents_forbidden_patterns(self):
        policy = (EP_DIR / "BOUNDARY_POLICY.md").read_text(encoding="utf-8")
        assert "FORBIDDEN" in policy, "BOUNDARY_POLICY.md must document FORBIDDEN patterns"
        assert "_bracket_ownership" in policy, (
            "BOUNDARY_POLICY.md must mention _bracket_ownership as a cross-peer concern"
        )
        assert "_startup_truth_orchestrator" in policy, (
            "BOUNDARY_POLICY.md must document _startup_truth_orchestrator as forbidden cross-peer"
        )

    def test_boundary_policy_has_sanctioned_access_section(self):
        policy = (EP_DIR / "BOUNDARY_POLICY.md").read_text(encoding="utf-8")
        assert "Sanctioned Access" in policy or "Allowed" in policy, (
            "BOUNDARY_POLICY.md must list sanctioned/allowed access patterns"
        )

    def test_boundary_policy_documents_deferred_violations(self):
        policy = (EP_DIR / "BOUNDARY_POLICY.md").read_text(encoding="utf-8")
        assert "Deferred" in policy or "deferred" in policy, (
            "BOUNDARY_POLICY.md must document known deferred historical violations"
        )


class TestCrossPeerViolationBaseline:
    """
    The known baseline of cross-peer violations is documented in BOUNDARY_POLICY.md.
    These tests enforce the baseline — any NEW access raises the count and fails.
    """

    # Baseline documented in BOUNDARY_POLICY.md (2026-04-30):
    # bracket_health.py has 5 _bracket_ownership accesses (deferred)
    BRACKET_OWNERSHIP_CROSS_PEER_BASELINE = 5

    # startup_reconstruction.py has 3 _startup_truth_orchestrator accesses (deferred)
    STARTUP_TRUTH_ORCHESTRATOR_CROSS_PEER_BASELINE = 3

    def test_bracket_ownership_cross_peer_count_at_baseline(self):
        """
        Only bracket_health.py should access _bracket_ownership via FSM back-ref,
        and only the known 5 sites (all deferred per BOUNDARY_POLICY.md).
        Any new cross-peer access must be added via FSM delegator instead.
        """
        count = _count_pattern(
            r"self\._fsm\._bracket_ownership",
            PEER_MODULES
        )
        assert count <= self.BRACKET_OWNERSHIP_CROSS_PEER_BASELINE, (
            f"Cross-peer _bracket_ownership access count has grown from baseline "
            f"{self.BRACKET_OWNERSHIP_CROSS_PEER_BASELINE} to {count}. "
            f"New access must use an FSM-level delegator, not self._fsm._bracket_ownership directly. "
            f"See BOUNDARY_POLICY.md for the approved pattern."
        )

    def test_startup_truth_orchestrator_cross_peer_count_at_baseline(self):
        """
        Only startup_reconstruction.py should access _startup_truth_orchestrator via FSM,
        and only the known 2 sites (all deferred per BOUNDARY_POLICY.md).
        """
        count = _count_pattern(
            r"self\._fsm\._startup_truth_orchestrator",
            PEER_MODULES
        )
        assert count <= self.STARTUP_TRUTH_ORCHESTRATOR_CROSS_PEER_BASELINE, (
            f"Cross-peer _startup_truth_orchestrator access count has grown from baseline "
            f"{self.STARTUP_TRUTH_ORCHESTRATOR_CROSS_PEER_BASELINE} to {count}. "
            f"New access must use an FSM-level delegator. See BOUNDARY_POLICY.md."
        )

    def test_fill_ingress_coordinator_does_not_access_bracket_ownership(self):
        """fill_ingress_coordinator must not access _bracket_ownership (cross-peer chain)."""
        content = _read_module(ORCHESTRATION_DIR / "fill_ingress_coordinator.py")
        assert "_bracket_ownership" not in content, (
            "fill_ingress_coordinator must not access _bracket_ownership directly. "
            "Use FSM delegator if needed."
        )

    def test_position_policy_mediator_does_not_access_bracket_ownership(self):
        """position_policy_mediator must not access _bracket_ownership (cross-peer chain)."""
        content = _read_module(SIDECAR_DIR / "position_policy_mediator.py")
        assert "_bracket_ownership" not in content, (
            "position_policy_mediator must not access _bracket_ownership. "
            "Use FSM delegator if needed."
        )

    def test_close_executor_does_not_access_bracket_ownership_via_fsm(self):
        """close_executor must not access _bracket_ownership through FSM back-ref."""
        content = _read_module(FLOWS_CLOSE_DIR / "close_executor.py")
        assert "self._fsm._bracket_ownership" not in content, (
            "close_executor must not chain to _bracket_ownership via self._fsm._bracket_ownership. "
            "Use FSM delegator instead."
        )


class TestKeyTypedStructuresExist:
    """Key typed structures for execution truth must exist."""

    def test_close_position_truth_classification_exists(self):
        """ClosePositionTruth classification enum must exist in close_executor."""
        content = _read_module(FLOWS_CLOSE_DIR / "close_executor.py")
        assert "ClosePositionTruth" in content or "_ClosePositionTruth" in content, (
            "close_executor.py must contain ClosePositionTruth typed structure"
        )

    def test_exposure_check_result_or_typed_return_exists(self):
        """ExposureGuard must use typed result, not raw dict."""
        from apps.reference.domains.execution_position.guards.soft_clip import ClipResult
        import inspect
        assert inspect.isclass(ClipResult), "ClipResult must be a typed class"

    def test_clip_result_has_allowed_field(self):
        """ClipResult must have 'allowed' field."""
        from apps.reference.domains.execution_position.guards.soft_clip import ClipResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ClipResult)}
        assert "allowed" in fields, "ClipResult must have 'allowed' field"

    def test_position_policy_close_request_is_typed(self):
        """PositionPolicyCloseRequest must be a typed model, not a plain dict."""
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicyCloseRequest,
        )
        assert hasattr(PositionPolicyCloseRequest, "model_fields") or hasattr(
            PositionPolicyCloseRequest, "__dataclass_fields__"
        ) or hasattr(PositionPolicyCloseRequest, "__annotations__"), (
            "PositionPolicyCloseRequest must be a typed model"
        )


class TestNoPeerMutatesEachOtherPrivateState:
    """No extracted peer module should write to another peer's private state."""

    def test_event_handlers_only_writes_portfolio_state_via_fsm_attribute(self):
        """
        event_handlers.py may write _latest_portfolio_state (it is the designated
        update handler). Other extracted modules must not write it.
        """
        for module_path in [
            FLOWS_MANAGE_DIR / "bracket_health.py",
            ORCHESTRATION_DIR / "fill_ingress_coordinator.py",
            SIDECAR_DIR / "position_policy_mediator.py",
            FLOWS_CLOSE_DIR / "close_executor.py",
        ]:
            content = _read_module(module_path)
            # Check for assignment to _latest_portfolio_state (writes, not reads)
            write_pattern = re.compile(
                r"self\._fsm\._latest_portfolio_state\s*="
            )
            matches = write_pattern.findall(content)
            assert not matches, (
                f"{module_path.name} must not WRITE to self._fsm._latest_portfolio_state. "
                f"Only event_handlers.py is the designated update site. "
                f"Found {len(matches)} write(s)."
            )

    def test_no_peer_writes_symbol_brackets_directly(self):
        """Only FSM itself and bracket_ownership should write _symbol_brackets."""
        for module_path in [
            ORCHESTRATION_DIR / "fill_ingress_coordinator.py",
            SIDECAR_DIR / "position_policy_mediator.py",
            FLOWS_CLOSE_DIR / "close_executor.py",
            ORCHESTRATION_DIR / "event_handlers.py",
        ]:
            content = _read_module(module_path)
            write_pattern = re.compile(
                r"self\._fsm\._symbol_brackets\s*\[.*?\]\s*="
            )
            matches = write_pattern.findall(content)
            assert not matches, (
                f"{module_path.name} must not write to self._fsm._symbol_brackets[...] directly. "
                f"Found {len(matches)} write(s)."
            )
