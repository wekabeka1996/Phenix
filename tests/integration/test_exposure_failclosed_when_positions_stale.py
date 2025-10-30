"""
EXP-FIX: Tests for exposure fail-closed behavior when positions are stale/unknown.

Tests the hard portfolio notional gate implementation.
"""

import pytest
import time
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_exposure_failclosed_when_positions_stale():
    """
    GIVEN: positions_last_ts_ms = 0 (нет данных) или старше 10с
    WHEN: CMD:OPEN
    THEN: ERR:OPEN{PORTFOLIO_STALE_OR_UNKNOWN} и counter exposure_fail_closed_total{reason="PORTFOLIO_STALE_OR_UNKNOWN"}++
    """
    # Import here to avoid circular imports
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

    # Mock config
    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_portfolio_fraction": 0.20,
                    "pending_ttl_sec": 90,
                    "post_fill_hold_ttl_sec": 5,
                    "positions_stale_ttl_sec": 5,
                }
            }
        }
    }

    # Create FSM with mocked components
    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = lambda op, **kwargs: emitted_events.append((op, kwargs))

    fsm = ExecPosFSM(config, fsm_mock, shadow_mode=True)

    # Mock stale portfolio state (no position data)
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000.0",
        "open_positions_usd": None,  # No position data
        "positions_last_ts_ms": 0,  # Never updated
    }

    # Create CMD:OPEN message
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_123",
        pld={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "1.0",
            "price_ref": "3000.0",
            "idempotent_key": "test_key_123"
        }
    )

    # Process the message
    result = fsm.handle(msg)

    # Should return None (error emitted asynchronously)
    assert result is None

    # Check that error event was emitted
    await asyncio.sleep(0.1)  # Allow async emission to complete

    # Find the error event
    error_events = [e for e in emitted_events if e[0] == "ERR"]
    assert len(error_events) == 1

    err_op, err_kwargs = error_events[0]
    assert err_kwargs["verb"] == "OPEN"
    assert err_kwargs["payload"]["reason"] == "PORTFOLIO_UNKNOWN"
    assert err_kwargs["why"] == "exposure_fail_closed_portfolio_unknown"

    # Check that exposure was reserved (fail-closed behavior)
    assert "test_key_123" in fsm.exposure_guard.state.reservations


@pytest.mark.asyncio
async def test_exposure_failclosed_when_positions_too_old():
    """
    GIVEN: positions_last_ts_ms старше 10 секунд
    WHEN: CMD:OPEN
    THEN: ERR:OPEN{PORTFOLIO_STALE} с stale_sec
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_portfolio_fraction": 0.20,
                    "positions_stale_ttl_sec": 5,
                }
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = lambda op, **kwargs: emitted_events.append((op, kwargs))

    fsm = ExecPosFSM(config, fsm_mock, shadow_mode=True)

    # Mock stale portfolio state (10 seconds old)
    stale_ts = int(time.time() * 1000) - 10000  # 10 seconds ago
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000.0",
        "open_positions_usd": "5000.0",
        "positions_last_ts_ms": stale_ts,
    }

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_456",
        pld={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "1.0",
            "price_ref": "3000.0",
            "idempotent_key": "test_key_456"
        }
    )

    result = fsm.handle(msg)
    assert result is None

    await asyncio.sleep(0.1)

    error_events = [e for e in emitted_events if e[0] == "ERR"]
    assert len(error_events) == 1

    err_op, err_kwargs = error_events[0]
    assert err_kwargs["verb"] == "OPEN"
    assert err_kwargs["payload"]["reason"] == "PORTFOLIO_STALE"
    assert "stale_sec" in err_kwargs["payload"]
    assert err_kwargs["payload"]["stale_sec"] > 9  # At least 9 seconds stale


@pytest.mark.asyncio
async def test_exposure_allowed_when_positions_fresh():
    """
    GIVEN: positions_last_ts_ms свежий (< 5 сек)
    WHEN: CMD:OPEN с допустимым exposure
    THEN: Продолжается к OpenFlowFSM
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_portfolio_fraction": 0.50,  # High limit for test
                }
            }
        }
    }

    fsm_mock = MagicMock()
    fsm = ExecPosFSM(config, fsm_mock, shadow_mode=True)

    # Mock fresh portfolio state
    fresh_ts = int(time.time() * 1000) - 1000  # 1 second ago
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000.0",
        "open_positions_usd": "1000.0",  # Low existing exposure
        "positions_last_ts_ms": fresh_ts,
    }

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_789",
        pld={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "1.0",
            "price_ref": "3000.0",
            "idempotent_key": "test_key_789"
        }
    )

    # Mock the open_flow to return a decision
    mock_decision = Message(
        op="DEC",
        verb="OPEN",
        src="execution_position",
        dst="decision_making",
        rid="test_rid_789",
        pld={"symbol": "ETHUSDT", "side": "BUY", "qty": "1.0"}
    )
    fsm.open_flow("ETHUSDT").handle = MagicMock(return_value=mock_decision)

    result = fsm.handle(msg)

    # Should get the decision from OpenFlowFSM
    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"

    # Check that exposure was reserved
    assert "test_key_789" in fsm.exposure_guard.state.reservations
