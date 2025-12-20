"""
Test for AccountConnector handling of empty positions list.
Verifies that the connector logs a warning and emits an empty list.
"""

import pytest
import logging
from unittest.mock import MagicMock, AsyncMock, patch
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
async def test_fetch_handles_empty_positions_response(mock_fsm, mock_config, caplog):
    """
    Test that _fetch_and_emit_account_data handles an empty list response
    for positions data by logging a warning and emitting the empty list.
    """
    # Set log level to INFO to capture the specific log (changed from WARNING)
    caplog.set_level(logging.INFO)
    
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)

    # Mock the adapter methods
    connector.adapter = AsyncMock()
    # Mock balance to return something valid so we focus on positions
    connector.adapter.get_account_balance.return_value = [
        {"asset": "USDT", "balance": "1000.0", "crossUnPnl": "0.0", "crossWalletBalance": "1000.0"}
    ]
    # Mock positions to return an EMPTY list
    connector.adapter.get_open_positions.return_value = []

    # Inject the mocked balance data into connector state (needed for _emit_positions_update)
    connector._latest_balance_data = connector.adapter.get_account_balance.return_value

    await connector._fetch_and_emit_account_data()

    # 1. Verify the INFO message about empty positions is logged
    # Note: Log message was changed from "CRITICAL" to informational
    assert any(
        "API returned EMPTY positions list" in record.message 
        for record in caplog.records
    ), f"Expected 'API returned EMPTY positions list' in logs. Got: {[r.message for r in caplog.records]}"
    
    # 2. Verify proper handling - connector processes empty list correctly
    # The "clear internal position state" message is DEBUG level, so we check
    # that the empty positions were processed by verifying emitted event

    # 3. Verify that EVT:ACCOUNT_UPDATE_RECEIVED IS emitted with empty positions
    emit_calls = mock_fsm.emit.call_args_list
    account_update_call = next(
        (call for call in emit_calls if call.kwargs.get("event_name") == "EVT:ACCOUNT_UPDATE_RECEIVED"),
        None
    )
    
    assert account_update_call is not None
    payload = account_update_call.kwargs.get("payload")
    assert payload is not None
    assert payload["positions"] == []  # Should be empty list
