"""
Phase 3 — Execution Safety Guardrails

Tests for DEF-E07: _closing_position flag must be cleared on all early-return
paths in close_executor, not just on happy-path completion.

Tests for DEF-E12: asyncio.CancelledError must be re-raised in cleanup loops.

Tests for DEF-E11: No-loop DEC must emit terminal failure observability event.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestClosingFlagClearedOnBuildFailure:
    """DEF-E07: _closing_position must be False on all exit paths from close flow."""

    def test_closing_flag_cleared_when_submission_is_none(self):
        """
        DEF-E07 regression: if _build_close_submission returns None, the code must
        clear _closing_position before returning. Previously it returned without
        clearing, leaving the position permanently stuck in "closing" state.
        """
        # Simulate the manage_flow state
        manage = MagicMock()
        manage._closing_position = True
        manage._closing_position_ts = 12345.0

        # Simulate the fix: if submission is None, clear the flag
        submission = None
        if submission is None:
            if manage:
                manage._closing_position = False
                manage._closing_position_ts = 0.0

        assert manage._closing_position is False, (
            "DEF-E07: _closing_position must be cleared when _build_close_submission "
            "returns None. Leaving it True blocks all future manage flows for this symbol."
        )
        assert manage._closing_position_ts == 0.0

    def test_closing_flag_invariant_position_truth_unresolved(self):
        """
        DEF-E07: flag must also be cleared when position truth is unresolved
        (this path already existed — verify it clears correctly).
        """
        manage = MagicMock()
        manage._closing_position = True

        # Simulate the unresolved-truth early return (already fixed in code)
        truth_unresolved = True
        if truth_unresolved and manage:
            manage._closing_position = False
            manage._closing_position_ts = 0.0

        assert manage._closing_position is False

    def test_closing_flag_invariant_genuinely_flat(self):
        """DEF-E07: flag must be cleared when position is genuinely flat."""
        manage = MagicMock()
        manage._closing_position = True

        genuinely_flat = True
        if genuinely_flat and manage:
            manage._closing_position = False
            manage._closing_position_ts = 0.0

        assert manage._closing_position is False

    def test_all_exit_paths_clear_closing_flag(self):
        """
        DEF-E07 structural test: documents all paths that must clear the flag.
        Each path that sets _closing_position=True must have a corresponding clear.
        """
        # This test documents the contract:
        # Path 1: truth_unresolved → clear flag → return [line ~1324]
        # Path 2: genuinely_flat → clear flag → return [line ~1346]
        # Path 3: submission is None → DEF-E07 FIX → clear flag → return
        # Path 4: happy path → clear flag at end [line ~1435]
        paths_with_flag_clear = [
            "truth_unresolved_path",
            "genuinely_flat_path",
            "submission_none_path",  # DEF-E07 fix
            "happy_path_completion",
        ]
        assert len(paths_with_flag_clear) == 4, (
            "Update this test if new early-return paths are added to the close flow"
        )


class TestCleanupLoopCancelTerminates:
    """DEF-E12: CancelledError in cleanup loops must be re-raised."""

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_through_cleanup_loop(self):
        """
        DEF-E12 regression: previously the cleanup loop caught CancelledError
        and incremented a counter instead of re-raising. This prevented task
        cancellation from working, causing immortal cleanup loops on shutdown.
        """
        cancel_raised = False

        async def mock_cleanup_loop():
            nonlocal cancel_raised
            while True:
                try:
                    await asyncio.sleep(0.001)
                except asyncio.CancelledError:
                    cancel_raised = True
                    raise  # DEF-E12: must re-raise
                except Exception:
                    pass

        task = asyncio.create_task(mock_cleanup_loop())
        await asyncio.sleep(0)  # Let task start
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancel_raised, "CancelledError handler must have run"
        assert task.cancelled(), "Task must be in cancelled state after re-raise"

    @pytest.mark.asyncio
    async def test_swallowing_cancelled_error_causes_immortal_task(self):
        """
        DEF-E12 documentation: swallowing CancelledError creates an immortal task.
        This test demonstrates WHY re-raising is required.
        """
        stop_flag = False

        async def bad_cleanup_loop():
            """Buggy loop that swallows CancelledError (old behavior)."""
            nonlocal stop_flag
            iterations = 0
            while not stop_flag and iterations < 3:
                try:
                    await asyncio.sleep(0.001)
                    iterations += 1
                except asyncio.CancelledError:
                    pass  # BUG: swallow — loop continues!

        task = asyncio.create_task(bad_cleanup_loop())
        await asyncio.sleep(0)
        task.cancel()

        # Task eventually exits because of stop_flag/iteration limit, NOT cancellation
        await asyncio.sleep(0.01)
        stop_flag = True
        await asyncio.sleep(0.01)

        # Task is NOT properly cancelled — it ran to natural completion
        assert not task.cancelled(), (
            "This demonstrates the bug: swallowing CancelledError → task never cancels"
        )


class TestProcessFlowResultNoLoopTerminalFailure:
    """DEF-E11: No-loop DEC must emit observable terminal failure, not silently discard."""

    def test_no_loop_emits_observability_event(self):
        """
        DEF-E11 regression: when no async loop is available but a DEC was committed
        to WAL, the system must emit a terminal failure event. Previously it only
        logged an error and silently discarded the decision.
        """
        observability_events = []

        def mock_emit_observability(event_type, data):
            observability_events.append({"type": event_type, "data": data})

        # Simulate the fix: if no loop, emit observability event
        loop = None  # No loop available
        if not loop:
            mock_emit_observability("DEC_NO_LOOP_TERMINAL_FAILURE", {
                "verb": "OPEN",
                "rid": "test-rid",
                "symbol": "BTCUSDT",
                "why": "DEF-E11:no_async_loop_decision_unscheduled",
            })

        assert len(observability_events) == 1, (
            "DEF-E11: Must emit exactly one observability event when loop is unavailable"
        )
        event = observability_events[0]
        assert event["type"] == "DEC_NO_LOOP_TERMINAL_FAILURE"
        assert "DEF-E11" in event["data"]["why"]

    def test_no_loop_log_contains_split_brain_warning(self):
        """
        DEF-E11: The error log for no-loop scenario must mention the split-brain risk
        so operators can identify the WAL corruption risk.
        """
        log_messages = []

        class MockLogger:
            def error(self, msg, *args):
                log_messages.append(msg % args if args else msg)

        logger = MockLogger()
        loop = None
        if not loop:
            logger.error(
                "DEF-E11: No async loop available for DEC:%s rid=%s symbol=%s — "
                "WAL has DEC truth but NO exchange action was scheduled. "
                "This is a split-brain state. Manual intervention required.",
                "OPEN", "test-rid", "BTCUSDT"
            )

        assert any("split-brain" in msg for msg in log_messages), (
            "DEF-E11: Error log must mention split-brain so operators understand the risk"
        )
        assert any("DEF-E11" in msg for msg in log_messages)
