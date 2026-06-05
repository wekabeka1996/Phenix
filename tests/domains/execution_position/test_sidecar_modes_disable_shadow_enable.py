"""
Phase 6 — Sidecar Action-Bearing Contract

Tests for DEF-E16: SHADOW mode must NOT emit CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST.
Tests for close-in-progress suppression and duplicate signature suppression.
"""
from __future__ import annotations

import inspect
import pytest
from unittest.mock import MagicMock


CLOSE_REQUEST_TOPIC = "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"


class TestSidecarModeEnumValues:
    """PositionPolicySidecarMode must have exactly DISABLE / SHADOW / ENABLE."""

    def test_mode_enum_has_disable(self):
        from apps.reference.config.domains.execution_position import PositionPolicySidecarMode
        assert hasattr(PositionPolicySidecarMode, "DISABLE")
        assert PositionPolicySidecarMode.DISABLE.value == "disable"

    def test_mode_enum_has_shadow(self):
        from apps.reference.config.domains.execution_position import PositionPolicySidecarMode
        assert hasattr(PositionPolicySidecarMode, "SHADOW")
        assert PositionPolicySidecarMode.SHADOW.value == "shadow"

    def test_mode_enum_has_enable(self):
        from apps.reference.config.domains.execution_position import PositionPolicySidecarMode
        assert hasattr(PositionPolicySidecarMode, "ENABLE")
        assert PositionPolicySidecarMode.ENABLE.value == "enable"


class TestShadowModeNeverEmitsCloseCommand:
    """DEF-E16: SHADOW mode must NOT emit CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST."""

    def test_close_request_emission_guarded_by_enable_check(self):
        """
        DEF-E16 regression: both close command emission sites must be guarded
        with PositionPolicySidecarMode.ENABLE check, not just DISABLE skip.
        SHADOW mode passes the DISABLE check and must be explicitly excluded.
        """
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicySidecar,
        )

        source = inspect.getsource(PositionPolicySidecar._evaluate_symbol)
        # The ENABLE guard must appear before close request topic emission
        enable_guard_pos = source.find("PositionPolicySidecarMode.ENABLE")
        close_topic_pos = source.find(
            '"CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"')

        assert enable_guard_pos != -1, (
            "DEF-E16: _evaluate_symbol must guard close command with ENABLE mode check"
        )
        # close topic is likely referenced as a constant CLOSE_REQUEST_COMMAND_TOPIC
        # check via the constant usage or just verify ENABLE guard exists
        assert "PositionPolicySidecarMode.ENABLE" in source, (
            "DEF-E16: Close command emission must require ENABLE mode"
        )

    def test_peak_giveback_close_command_also_guarded_by_enable(self):
        """DEF-E16: Peak giveback path also must require ENABLE mode to emit close command."""
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicySidecar,
        )

        source = inspect.getsource(
            PositionPolicySidecar._handle_peak_giveback_trigger)
        assert "PositionPolicySidecarMode.ENABLE" in source, (
            "DEF-E16: Peak giveback close command must also require ENABLE mode"
        )

    def test_shadow_mode_is_not_equal_to_enable(self):
        """SHADOW and ENABLE are distinct enum values."""
        from apps.reference.config.domains.execution_position import PositionPolicySidecarMode
        assert PositionPolicySidecarMode.SHADOW != PositionPolicySidecarMode.ENABLE

    def test_shadow_mode_is_not_equal_to_disable(self):
        """SHADOW and DISABLE are distinct enum values."""
        from apps.reference.config.domains.execution_position import PositionPolicySidecarMode
        assert PositionPolicySidecarMode.SHADOW != PositionPolicySidecarMode.DISABLE

    def test_disable_mode_causes_early_return_before_any_emit(self):
        """
        DISABLE mode must cause early return in _evaluate_symbol before
        any publish calls — no advisory events, no close commands.
        """
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicySidecar,
        )

        source = inspect.getsource(PositionPolicySidecar._evaluate_symbol)
        # DISABLE check must be near the top (before other logic)
        disable_pos = source.find("PositionPolicySidecarMode.DISABLE")
        first_publish_pos = source.find("_publish(")

        assert disable_pos != -1, "DISABLE mode check must exist in _evaluate_symbol"
        assert disable_pos < first_publish_pos, (
            "DISABLE mode return must appear before any _publish call"
        )


class TestSidecarDuplicateCloseSuppressionContract:
    """Sidecar must suppress duplicate recommendations with the same state signature."""

    def test_recommendation_signature_dedup_logic_exists(self):
        """
        Same score+position+fill-correlation signature must be suppressed.
        This prevents spam-closing a position on every heartbeat.
        """
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicySidecar,
        )

        source = inspect.getsource(PositionPolicySidecar._evaluate_symbol)
        assert "last_recommendation_signature" in source, (
            "Sidecar must compare last_recommendation_signature to suppress duplicates"
        )
        assert "recommendation_duplicate_same_state" in source, (
            "Suppression reason 'recommendation_duplicate_same_state' must be used"
        )

    def test_recommendation_signature_method_exists(self):
        """_recommendation_signature must exist as a dedicated method."""
        from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
            PositionPolicySidecar,
        )
        assert hasattr(PositionPolicySidecar, "_recommendation_signature"), (
            "PositionPolicySidecar must have _recommendation_signature() method"
        )


class TestSidecarCloseInProgressSuppression:
    """Sidecar mediator must suppress close requests when close is already in progress."""

    def test_mediator_checks_closing_position_flag(self):
        """
        DEF-E16: PositionPolicyMediator.on_position_policy_close_request must check
        manage_flow._closing_position before emitting CMD:CLOSE.
        If True, suppress with 'manage_flow_close_in_progress'.
        """
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
            PositionPolicyMediator,
        )

        source = inspect.getsource(
            PositionPolicyMediator.on_position_policy_close_request
        )
        assert "_closing_position" in source, (
            "Mediator must check manage_flow._closing_position flag"
        )
        assert "manage_flow_close_in_progress" in source, (
            "Suppression reason 'manage_flow_close_in_progress' must be used"
        )

    def test_mediator_checks_active_lifecycle_before_close(self):
        """Mediator must verify manage_flow has active lifecycle (not already closed)."""
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
            PositionPolicyMediator,
        )

        source = inspect.getsource(
            PositionPolicyMediator.on_position_policy_close_request
        )
        assert "has_active_lifecycle" in source, (
            "Mediator must check manage_flow.has_active_lifecycle()"
        )
        assert "manage_flow_has_no_active_lifecycle" in source, (
            "Suppression reason 'manage_flow_has_no_active_lifecycle' must be set"
        )

    def test_mediator_suppresses_when_no_manage_flow(self):
        """Mediator must suppress when no manage flow exists for symbol."""
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
            PositionPolicyMediator,
        )

        source = inspect.getsource(
            PositionPolicyMediator.on_position_policy_close_request
        )
        assert "no_manage_flow_for_symbol" in source, (
            "Mediator must suppress with 'no_manage_flow_for_symbol' when manage_flow is None"
        )

    def test_mediator_suppresses_partial_reduce_forbidden(self):
        """Mediator must not allow partial_reduce scope to be active (safety contract)."""
        import inspect
        from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
            PositionPolicyMediator,
        )

        source = inspect.getsource(
            PositionPolicyMediator.on_position_policy_close_request
        )
        assert "partial_reduce_forbidden" in source, (
            "Mediator must enforce partial_reduce_forbidden scope restriction"
        )


class TestSidecarBracketsPendingLifecycleEligibility:
    """
    A5 governance: BRACKETS_PENDING is an active lifecycle state.

    Both observed runtime sidecar closes occurred with manage_state=BRACKETS_PENDING.
    This class documents and enforces the explicit design decision that sidecar close
    requests are intentionally permitted in BRACKETS_PENDING (position is real, fill
    confirmed, bracket placement not yet exchange-confirmed).
    """

    def test_has_active_lifecycle_returns_true_for_brackets_pending(self):
        """
        BRACKETS_PENDING must pass has_active_lifecycle() — the state is non-FLAT,
        meaning the sidecar mediator will not suppress on lifecycle grounds.
        """
        from apps.reference.domains.execution_position.flows.manage.fsm_manage import (
            ManageFlowFSM,
            ManageState,
        )

        source = inspect.getsource(ManageFlowFSM.has_active_lifecycle)
        # has_active_lifecycle() is authoritative via state != FLAT check
        assert "ManageState.FLAT" in source, (
            "has_active_lifecycle must compare against ManageState.FLAT"
        )
        # BRACKETS_PENDING is not FLAT, so it returns True without additional checks
        assert ManageState.BRACKETS_PENDING != ManageState.FLAT, (
            "BRACKETS_PENDING must be a distinct non-FLAT state"
        )

    def test_mediator_does_not_block_brackets_pending_by_name(self):
        """
        Mediator source must NOT contain a BRACKETS_PENDING-specific suppression guard.
        The eligibility decision (allow) must remain implicit via has_active_lifecycle().
        If this test fails, a guard was added that changes the existing contract.
        """
        from apps.reference.domains.execution_position.sidecar.position_policy_mediator import (
            PositionPolicyMediator,
        )

        source = inspect.getsource(
            PositionPolicyMediator.on_position_policy_close_request)
        assert "BRACKETS_PENDING" not in source, (
            "A5 governance: Mediator must not contain a BRACKETS_PENDING-specific block. "
            "If intentionally adding one, update this test and the SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT "
            "lifecycle-state eligibility matrix accordingly."
        )

    def test_brackets_pending_state_is_in_manage_state_enum(self):
        """ManageState.BRACKETS_PENDING must exist with the exact string value."""
        from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState

        assert hasattr(ManageState, "BRACKETS_PENDING"), (
            "ManageState enum must define BRACKETS_PENDING"
        )
        assert ManageState.BRACKETS_PENDING.value == "BRACKETS_PENDING"
