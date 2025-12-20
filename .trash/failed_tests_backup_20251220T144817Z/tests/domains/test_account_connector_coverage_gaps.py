# PATH: tests/domains/test_account_connector_coverage_gaps.py
"""
FSMP-PERFECT-T16: Coverage gaps tests for the refactored AccountConnector.
"""

import logging
import pytest
from unittest.mock import MagicMock, AsyncMock

from apps.reference.domains.account_balance.account_connector import AccountConnector
from vfoundation.core.fsm import FSM


@pytest.fixture
def mock_fsm():
    """Provides a mock FSM instance with an emit method."""
    fsm = MagicMock(spec=FSM)
    fsm.emit = MagicMock()
    return fsm


@pytest.fixture
def mock_config():
    """Provides a mock configuration dictionary for testnet mode."""
    return {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 0.1},
    }


@pytest.mark.asyncio
async def test_fetch_handles_non_list_balance_response(mock_fsm, mock_config, caplog):
    """
    Test that _fetch_and_emit_account_data handles a non-list (e.g., dict)
    response for balance data gracefully.
    """
    caplog.set_level(logging.ERROR)
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)

    # Mock the adapter methods
    connector.adapter = AsyncMock()
    connector.adapter.get_account_balance.return_value = {"error": "this is not a list"}
    connector.adapter.get_open_positions.return_value = []  # Normal response for positions

    await connector._fetch_and_emit_account_data()

    # Assert that an error was logged and no event was emitted for the malformed data
    assert any(
        "Error processing balance data" in record.message for record in caplog.records
    )

    # Check that emit was not called for balance update
    emit_calls = mock_fsm.emit.call_args_list
    assert not any(
        call.kwargs.get("event_name") == "EVT:BALANCE_UPDATE_RECEIVED"
        for call in emit_calls
    )


@pytest.mark.asyncio
async def test_fetch_handles_non_list_positions_response(mock_fsm, mock_config, caplog):
    """
    Test that _fetch_and_emit_account_data handles a non-list (e.g., dict)
    response for positions data gracefully.
    """
    caplog.set_level(logging.ERROR)
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)

    # Mock the adapter methods
    connector.adapter = AsyncMock()
    connector.adapter.get_account_balance.return_value = []  # Normal response for balance
    connector.adapter.get_open_positions.return_value = {"error": "this is not a list"}

    await connector._fetch_and_emit_account_data()

    # Assert that an error was logged and no event was emitted for the malformed data
    assert any(
        "Error processing positions data" in record.message for record in caplog.records
    )

    # Check that emit was not called for account update
    emit_calls = mock_fsm.emit.call_args_list
    assert not any(
        call.kwargs.get("event_name") == "EVT:ACCOUNT_UPDATE_RECEIVED"
        for call in emit_calls
    )
