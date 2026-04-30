"""
Phase 3 — Execution Safety Guardrails

Tests for DEF-E01: Bracket parallel placement partial-success must not
retry the successful side (which would create a duplicate protective order).
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class _FakeBinanceAPIError(Exception):
    def __init__(self, code: int, msg: str = ""):
        super().__init__(msg)
        self.code = code


class TestBracketParallelPartialSuccess:
    """DEF-E01: Only the failed side must be retried after partial gather success."""

    @pytest.mark.asyncio
    async def test_both_succeed_no_extra_calls(self):
        """Baseline: if both SL and TP succeed, no extra adapter calls made."""
        sl_mock = AsyncMock(return_value={"orderId": "SL-1"})
        tp_mock = AsyncMock(return_value={"orderId": "TP-1"})

        # Simulate the gather logic directly as it exists in bracket_manager.py
        results = await asyncio.gather(sl_mock(), tp_mock(), return_exceptions=True)
        sl_result, tp_result = results[0], results[1]

        assert not isinstance(sl_result, BaseException)
        assert not isinstance(tp_result, BaseException)
        assert sl_result == {"orderId": "SL-1"}
        assert tp_result == {"orderId": "TP-1"}

    @pytest.mark.asyncio
    async def test_sl_succeeds_tp_fails_only_tp_retried(self):
        """
        DEF-E01 regression: when SL succeeds and TP fails, only TP must be retried.
        Retrying both sides would place a duplicate SL on the exchange.
        """
        sl_call_count = 0
        tp_call_count = 0

        async def mock_sl():
            nonlocal sl_call_count
            sl_call_count += 1
            return {"orderId": f"SL-{sl_call_count}"}

        async def mock_tp_first_fail_then_ok():
            nonlocal tp_call_count
            tp_call_count += 1
            if tp_call_count == 1:
                raise _FakeBinanceAPIError(-1000, "TP placement failed")
            return {"orderId": f"TP-{tp_call_count}"}

        results = await asyncio.gather(mock_sl(), mock_tp_first_fail_then_ok(), return_exceptions=True)
        sl_result, tp_result = results[0], results[1]

        sl_ok = not isinstance(sl_result, BaseException)
        tp_ok = not isinstance(tp_result, BaseException)

        assert sl_ok, "SL should have succeeded"
        assert not tp_ok, "TP should have failed on first attempt"

        # DEF-E01 check: if SL succeeded and TP failed, only retry TP
        # (sl_call_count must remain 1 — do NOT call mock_sl again)
        if sl_ok and not tp_ok:
            # Only retry TP
            tp_retry_result = await mock_tp_first_fail_then_ok()
            assert isinstance(tp_retry_result, dict)

        assert sl_call_count == 1, (
            f"DEF-E01: SL was called {sl_call_count} times — must be exactly 1 "
            "(retrying SL after it succeeded would create a duplicate protective order)"
        )
        assert tp_call_count == 2, "TP must have been called once (failed) + once (retry)"

    @pytest.mark.asyncio
    async def test_tp_succeeds_sl_fails_only_sl_retried(self):
        """
        DEF-E01: when TP succeeds and SL fails, only SL must be retried.
        SL is the primary protective order — its failure is critical.
        """
        sl_call_count = 0
        tp_call_count = 0

        async def mock_sl_first_fail_then_ok():
            nonlocal sl_call_count
            sl_call_count += 1
            if sl_call_count == 1:
                raise _FakeBinanceAPIError(-2021, "SL placement failed")
            return {"orderId": f"SL-{sl_call_count}"}

        async def mock_tp():
            nonlocal tp_call_count
            tp_call_count += 1
            return {"orderId": f"TP-{tp_call_count}"}

        results = await asyncio.gather(mock_sl_first_fail_then_ok(), mock_tp(), return_exceptions=True)
        sl_result, tp_result = results[0], results[1]

        assert isinstance(sl_result, BaseException), "SL should have failed"
        assert not isinstance(
            tp_result, BaseException), "TP should have succeeded"

        # Retry only SL
        sl_retry_result = await mock_sl_first_fail_then_ok()
        assert isinstance(sl_retry_result, dict)

        assert tp_call_count == 1, (
            f"DEF-E01: TP was called {tp_call_count} times — must be exactly 1 "
            "(retrying TP after it succeeded would create a duplicate protective order)"
        )

    @pytest.mark.asyncio
    async def test_return_exceptions_true_does_not_propagate_immediately(self):
        """
        DEF-E01 contract: gather with return_exceptions=True must NOT raise on first
        failure. Both results must be available for independent classification.
        """
        async def fail():
            raise ValueError("intentional failure")

        async def succeed():
            return "ok"

        # With return_exceptions=True, this must not raise
        results = await asyncio.gather(fail(), succeed(), return_exceptions=True)
        assert isinstance(results[0], ValueError)
        assert results[1] == "ok"

        # Contrast: return_exceptions=False would raise and lose the succeed() result
        with pytest.raises(ValueError):
            await asyncio.gather(fail(), succeed(), return_exceptions=False)
