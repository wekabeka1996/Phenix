"""
EXP-FIX: Tests for post-fill hold mechanism.

Tests that reservations move to post-fill hold after FILL to prevent race conditions.
"""

import pytest
import time
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_postfill_hold_until_portfolio_ok():
    """
    GIVEN: pending reservation → FILLED
    WHEN: PORTFOLIO_STATE_UPDATED задерживается > 0с, но < hold_ttl
    THEN: reservation остаётся в postfill_hold и OPEN блокируется по лимиту
    WHEN: приходит свежий portfolio → hold снимается
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_portfolio_fraction": 0.20,
                    "post_fill_hold_ttl_sec": 5,
                }
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = MagicMock(side_effect=lambda *args: emitted_events.append(args))

    fsm = ExecPosFSM(config, fsm_mock, shadow_mode=True)

    # Setup fresh portfolio state
    fresh_ts = int(time.time() * 1000) - 1000
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000.0",
        "open_positions_usd": "1000.0",
        "positions_last_ts_ms": fresh_ts,
    }

    # First, make a reservation
    reserve_key = "test_reserve_123"
    notional_usd = Decimal("2000.0")  # 20% of equity limit
    fsm.exposure_guard.reserve(reserve_key, notional_usd)

    # Verify reservation is active
    assert reserve_key in fsm.exposure_guard.state.reservations
    assert reserve_key not in fsm.exposure_guard.state.postfill_reservations

    # Simulate FILL event
    fill_msg = Message(
        op="EVT",
        verb="FILL",
        src="execution_adapter",
        dst="execution_position",
        rid="fill_rid_123",
        pld={
            "idempotent_key": reserve_key,
            "qty": "1.0",
            "price": "2000.0",
            "symbol": "ETHUSDT",
        },
    )

    fsm.handle(fill_msg)

    # Check that reservation moved to post-fill hold
    assert reserve_key not in fsm.exposure_guard.state.reservations
    assert reserve_key in fsm.exposure_guard.state.postfill_reservations

    # Now try to open another position - should be blocked by post-fill hold
    open_msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="open_rid_456",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "price_ref": "50000.0",
            "idempotent_key": "open_key_456",
        },
    )

    result = fsm.handle(open_msg)
    assert result is None  # Should be blocked

    await asyncio.sleep(0.1)
    error_events = [e for e in emitted_events if len(e) > 0 and hasattr(e[0], 'op') and e[0].op == "ERR"]
    assert len(error_events) == 1
    assert error_events[0][0].pld["reason"] == "EXPOSURE_LIMIT_EXCEEDED"

    # Now simulate fresh portfolio update (positions updated)
    updated_ts = int(time.time() * 1000)
    portfolio_update_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="execution_position",
        rid="portfolio_rid_789",
        pld={
            "equity_free_usdt": "10000.0",
            "open_positions_usd": "3000.0",  # Now includes the filled position
            "positions_last_ts_ms": updated_ts,
        },
    )

    fsm.handle(portfolio_update_msg)

    # Check that post-fill hold was released
    assert reserve_key not in fsm.exposure_guard.state.postfill_reservations

    # Now opening should work again
    result2 = fsm.handle(open_msg)
    # Should proceed to OpenFlowFSM (would return DEC if mocked)


@pytest.mark.asyncio
async def test_postfill_hold_expires_after_ttl():
    """
    GIVEN: post-fill hold активен
    WHEN: TTL истекает без portfolio update
    THEN: hold снимается автоматически с WARN
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    config = {
        "trading": {
            "execution": {
                "exposure": {
                    "post_fill_hold_ttl_sec": 1,  # Short TTL for test
                }
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = MagicMock(side_effect=lambda *args: emitted_events.append(args))

    fsm = ExecPosFSM(config, fsm_mock, shadow_mode=True)

    # Setup portfolio state
    fresh_ts = int(time.time() * 1000) - 1000
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000.0",
        "open_positions_usd": "1000.0",
        "positions_last_ts_ms": fresh_ts,
    }

    # Create post-fill hold
    reserve_key = "expire_test_123"
    notional_usd = Decimal("2000.0")
    fsm.exposure_guard.reserve(reserve_key, notional_usd)

    fill_msg = Message(
        op="EVT",
        verb="FILL",
        src="execution_adapter",
        dst="execution_position",
        rid="fill_expire_123",
        pld={
            "idempotent_key": reserve_key,
            "qty": "1.0",
            "price": "2000.0",
            "symbol": "ETHUSDT",
        },
    )

    fsm.handle(fill_msg)
    assert reserve_key in fsm.exposure_guard.state.postfill_reservations

    # Wait for TTL to expire
    await asyncio.sleep(1.1)

    # Trigger cleanup (normally happens on portfolio update)
    expired = fsm.exposure_guard.expire_stale()

    # Check that post-fill hold was expired
    assert reserve_key not in fsm.exposure_guard.state.postfill_reservations
    assert len(expired) > 0  # Should have expired something
