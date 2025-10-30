"""
EXP-FIX: Tests for position notional aggregation in PositionTracking.

Tests that open_positions_usd is correctly calculated from position data.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_positions_notional_aggregate():
    """
    GIVEN: positions data from Binance
    WHEN: account update приходит
    THEN: open_positions_usd = sum(abs(positionAmt * entryPrice)) for all positions
    """
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    config = {
        "trading": {
            "position_tracking": {
                "positions_stale_ttl_sec": 30,
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = lambda op, **kwargs: emitted_events.append((op, kwargs))

    position_tracking = PositionTracking(fsm_mock, config)

    # Simulate account update with positions
    positions_data = [
        {
            "symbol": "ETHUSDT",
            "positionAmt": "1.5",  # Long 1.5 ETH
            "entryPrice": "2000.0",
            "unrealizedProfit": "150.0",
        },
        {
            "symbol": "BTCUSDT",
            "positionAmt": "-0.02",  # Short 0.02 BTC
            "entryPrice": "50000.0",
            "unrealizedProfit": "-100.0",
        },
        {
            "symbol": "ADAUSDT",
            "positionAmt": "0.0",  # No position
            "entryPrice": "0.0",
            "unrealizedProfit": "0.0",
        }
    ]

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_adapter",
        dst="position_tracking",
        rid="account_rid_123",
        pld={
            "positions": positions_data,
            "assets": [
                {"asset": "USDT", "free": "9500.0", "locked": "500.0"},
                {"asset": "ETH", "free": "0.0", "locked": "1.5"},
                {"asset": "BTC", "free": "0.0", "locked": "0.02"},
            ],
            "totalCrossWalletBalance": "9500.0",  # free USDT
            "totalUnrealizedProfit": "50.0",
        }
    )

    position_tracking.on_account_update(account_msg)

    # Check that portfolio state was emitted with correct notional
    portfolio_events = [e for e in emitted_events if e[0] == "EVT:PORTFOLIO_STATE_UPDATED"]
    assert len(portfolio_events) == 1

    payload = portfolio_events[0][1]["payload"]
    expected_notional = abs(Decimal("1.5") * Decimal("2000.0")) + abs(Decimal("-0.02") * Decimal("50000.0"))
    assert Decimal(payload["open_positions_usd"]) == expected_notional
    assert "positions_last_ts_ms" in payload


@pytest.mark.asyncio
async def test_positions_notional_zero_when_no_positions():
    """
    GIVEN: no open positions
    WHEN: account update приходит
    THEN: open_positions_usd = 0
    """
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    config = {
        "trading": {
            "position_tracking": {
                "positions_stale_ttl_sec": 30,
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = lambda op, **kwargs: emitted_events.append((op, kwargs))

    position_tracking = PositionTracking(fsm_mock, config)

    # Simulate account update with no positions
    positions_data = [
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0.0",
            "entryPrice": "0.0",
            "unrealizedProfit": "0.0",
        }
    ]

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_adapter",
        dst="position_tracking",
        rid="account_zero_123",
        pld={
            "positions": positions_data,
            "assets": [
                {"asset": "USDT", "free": "10000.0", "locked": "0.0"},
            ]
        }
    )

    position_tracking.on_account_update(account_msg)

    # Check that portfolio state was emitted with zero notional
    portfolio_events = [e for e in emitted_events if e[0] == "EVT:PORTFOLIO_STATE_UPDATED"]
    assert len(portfolio_events) == 1

    payload = portfolio_events[0][1]["payload"]
    assert Decimal(payload["open_positions_usd"]) == Decimal("0.0")
    assert "positions_last_ts_ms" in payload


@pytest.mark.asyncio
async def test_positions_notional_handles_precision():
    """
    GIVEN: positions with high precision decimals
    WHEN: aggregation happens
    THEN: precision сохраняется правильно
    """
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking

    config = {
        "trading": {
            "position_tracking": {
                "positions_stale_ttl_sec": 30,
            }
        }
    }

    fsm_mock = MagicMock()
    emitted_events = []
    fsm_mock.emit = lambda op, **kwargs: emitted_events.append((op, kwargs))

    position_tracking = PositionTracking(fsm_mock, config)

    # Simulate account update with high precision positions
    positions_data = [
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0.12345678",  # High precision amount
            "entryPrice": "1999.98765432",  # High precision price
            "unrealizedProfit": "0.0",
        }
    ]

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_adapter",
        dst="position_tracking",
        rid="account_precision_123",
        pld={
            "positions": positions_data,
            "assets": [
                {"asset": "USDT", "free": "10000.0", "locked": "0.0"},
            ]
        }
    )

    position_tracking.on_account_update(account_msg)

    # Check that portfolio state was emitted with correct precision
    portfolio_events = [e for e in emitted_events if e[0] == "EVT:PORTFOLIO_STATE_UPDATED"]
    assert len(portfolio_events) == 1

    payload = portfolio_events[0][1]["payload"]
    expected_notional = abs(Decimal("0.12345678") * Decimal("1999.98765432")).quantize(Decimal("0.01"))
    assert Decimal(payload["open_positions_usd"]) == expected_notional
    assert "positions_last_ts_ms" in payload
