"""
TEST #1: Preflight wait-until logic with exponential backoff.

Tests that _preflight_position_check() retries with 120→250→400ms backoff
when positionAmt is initially 0, and returns True when position appears.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from apps.reference.domains.execution_position.fsm import ExecPosFSM


@pytest.mark.asyncio
async def test_preflight_wait_until_success_on_third_try():
    """
    Mock adapter returns positionAmt=0, 0, then 0.001 on 3rd call.
    Expect: _preflight_position_check() returns True, made 3 calls.
    """
    # Mock FSM with minimal mock fsm core
    mock_fsm_core = MagicMock()
    fsm = ExecPosFSM(config={}, fsm=mock_fsm_core)

    # Mock adapter.get_open_positions to return 0, 0, 0.001
    call_count = 0

    async def mock_get_positions(symbol):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # First two calls: position not synced yet
            return [{"symbol": symbol, "positionAmt": "0.0"}]
        else:
            # Third call: position synced
            return [{"symbol": symbol, "positionAmt": "0.001"}]

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(side_effect=mock_get_positions)

    # Call preflight check
    result = await fsm._preflight_position_check("BTCUSDT")

    # Assertions
    assert result is True, "Should return True when position found on 3rd try"
    assert call_count == 3, f"Expected 3 calls, got {call_count}"
    assert fsm.adapter.get_open_positions.call_count == 3


@pytest.mark.asyncio
async def test_preflight_wait_until_exhausted_returns_false():
    """
    Mock adapter always returns positionAmt=0.
    Expect: _preflight_position_check() returns False after 3+ tries.
    """
    mock_fsm_core = MagicMock()
    fsm = ExecPosFSM(config={}, fsm=mock_fsm_core)

    # Mock adapter to always return 0
    async def mock_get_positions_zero(symbol):
        return [{"symbol": symbol, "positionAmt": "0.0"}]

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        side_effect=mock_get_positions_zero)

    # Call preflight check
    result = await fsm._preflight_position_check("BTCUSDT")

    # Assertions
    assert result is False, "Should return False when position never appears"
    assert fsm.adapter.get_open_positions.call_count == 4, "Should make 4 calls (1 + 3 retries)"
    # Check metric incremented
    assert fsm._orphan_metrics.get("tp_sl_skipped_no_position", 0) == 1


@pytest.mark.asyncio
async def test_preflight_wait_until_immediate_success():
    """
    Mock adapter returns positionAmt=0.005 on first call.
    Expect: _preflight_position_check() returns True immediately (no retries).
    """
    mock_fsm_core = MagicMock()
    fsm = ExecPosFSM(config={}, fsm=mock_fsm_core)

    # Mock adapter to return valid position immediately
    async def mock_get_positions_immediate(symbol):
        return [{"symbol": symbol, "positionAmt": "0.005"}]

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        side_effect=mock_get_positions_immediate)

    # Call preflight check
    result = await fsm._preflight_position_check("ETHUSDT")

    # Assertions
    assert result is True, "Should return True immediately when position exists"
    assert fsm.adapter.get_open_positions.call_count == 1, "Should make only 1 call"


if __name__ == "__main__":
    # Run with: pytest tests/units/test_preflight_wait_until.py -v
    pytest.main([__file__, "-v"])
