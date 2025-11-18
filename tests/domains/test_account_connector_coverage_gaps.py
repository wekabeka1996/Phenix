# PATH: tests/domains/test_account_connector_coverage_gaps.py
"""
FSMP-PERFECT-T16: Coverage gaps tests for the refactored AccountConnector.
"""

import logging
import pytest
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
async def test_fetch_handles_non_list_balance_response(mock_fsm, mock_config, caplog):
    """
    Test that _fetch_and_emit_account_data handles a non-list (e.g., dict)
    response for balance data gracefully.
    """
    caplog.set_level(logging.ERROR)
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)

    # Mock the adapter methods
    connector.adapter = AsyncMock()
    connector.adapter.get_account_balance.return_value = {
        "error": "this is not a list"}
    # Normal response for positions
    connector.adapter.get_open_positions.return_value = []

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
    # Normal response for balance
    connector.adapter.get_account_balance.return_value = []
    connector.adapter.get_open_positions.return_value = {
        "error": "this is not a list"}

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


def test_init_success(mock_fsm, mock_config):
    """Test successful initialization of AccountConnector."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    assert connector.fsm == mock_fsm
    assert connector.config == mock_config
    assert connector.update_interval == 0.1
    assert connector.running is False
    assert connector.thread is None
    assert connector._latest_balance_data is None


def test_init_live_mode(mock_fsm):
    """Test initialization in live mode."""
    config = {
        "trading_mode": "live",
        "binance_api": {
            "live": {
                "api_key": "live_key",
                "api_secret": "live_secret",
                "rest_url": "https://fapi.binance.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }
    connector = AccountConnector(fsm=mock_fsm, config=config)
    assert connector.update_interval == 30


def test_init_missing_credentials(mock_fsm):
    """Test initialization fails with missing credentials."""
    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                # Missing api_key and api_secret
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }
    with pytest.raises(ValueError, match="API configuration.*incomplete"):
        AccountConnector(fsm=mock_fsm, config=config)


@patch("apps.reference.domains.account_balance.account_connector.threading.Thread")
def test_start_success(mock_thread, mock_fsm, mock_config):
    """Test successful start of monitoring."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector.start()
    assert connector.running is True
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()


def test_start_already_running(mock_fsm, mock_config, caplog):
    """Test start when already running."""
    caplog.set_level(logging.WARNING)
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector.running = True
    connector.start()
    assert "AccountConnector already running" in caplog.text


@patch("apps.reference.domains.account_balance.account_connector.asyncio")
def test_stop_success(mock_asyncio, mock_fsm, mock_config):
    """Test successful stop of monitoring."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    connector.thread = mock_thread
    connector.running = True

    connector.stop()

    assert connector.running is False
    mock_thread.join.assert_called_once()
    mock_asyncio.run.assert_called_once()


@pytest.mark.asyncio
async def test_emit_balance_update_success(mock_fsm, mock_config):
    """Test successful emission of balance update."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    balance_data = [
        {"asset": "USDT", "balance": "1000.0", "crossUnPnl": "50.0",
            "crossWalletBalance": "1050.0", "updateTime": 1234567890},
        {"asset": "BTC", "balance": "0.0", "crossUnPnl": "0.0",
            "crossWalletBalance": "0.0", "updateTime": 1234567890},
    ]

    result = connector._emit_balance_update(balance_data)

    assert result["assets_emitted"] == 1  # Only USDT has balance > 0
    assert result["updateTime"] == 1234567890
    mock_fsm.emit.assert_called_once()
    call_args = mock_fsm.emit.call_args
    assert call_args.kwargs["event_name"] == "EVT:BALANCE_UPDATE_RECEIVED"
    payload = call_args.kwargs["payload"]
    assert len(payload["assets"]) == 1
    assert payload["assets"][0]["asset"] == "USDT"


@pytest.mark.asyncio
async def test_emit_positions_update_success(mock_fsm, mock_config):
    """Test successful emission of positions update."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector._latest_balance_data = [
        {"asset": "USDT", "balance": "1000.0",
            "crossUnPnl": "50.0", "crossWalletBalance": "1050.0"}
    ]
    positions_data = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "entryPrice": "50000.0",
            "unRealizedProfit": "100.0",
            "leverage": 10,
            "marginType": "cross",
            "markPrice": "51000.0",
            "liquidationPrice": "45000.0",
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0.0",  # Zero position
            "entryPrice": "3000.0",
            "unRealizedProfit": "0.0",
            "leverage": 5,
            "marginType": "cross",
            "markPrice": "3100.0",
            "liquidationPrice": "2500.0",
        }
    ]

    connector._emit_positions_update(positions_data)

    mock_fsm.emit.assert_called_once()
    call_args = mock_fsm.emit.call_args
    assert call_args.kwargs["event_name"] == "EVT:ACCOUNT_UPDATE_RECEIVED"
    payload = call_args.kwargs["payload"]
    assert len(payload["positions"]) == 1  # Only non-zero position
    assert payload["positions"][0]["symbol"] == "BTCUSDT"
    assert payload["totalWalletBalance"] == "1000.0"
    assert payload["totalUnrealizedProfit"] == "50.0"


@pytest.mark.asyncio
async def test_force_snapshot_refresh_success(mock_fsm, mock_config):
    """Test successful force snapshot refresh."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector.adapter = AsyncMock()
    connector.adapter.get_account_balance.return_value = []
    connector.adapter.get_open_positions.return_value = []

    result = connector.force_snapshot_refresh(reason="test")

    assert result["status"] == "ok"
    assert result["reason"] == "test"


@pytest.mark.asyncio
async def test_force_snapshot_refresh_busy(mock_fsm, mock_config):
    """Test force snapshot refresh when already in progress."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector._manual_resync_lock.acquire()  # Simulate busy

    result = connector.force_snapshot_refresh(reason="test")

    assert result["status"] == "busy"
    assert result["reason"] == "resync_in_progress"


@pytest.mark.asyncio
async def test_fetch_and_emit_account_data_success(mock_fsm, mock_config):
    """Test successful fetch and emit of account data."""
    connector = AccountConnector(fsm=mock_fsm, config=mock_config)
    connector.adapter = AsyncMock()
    connector.adapter.get_account_balance.return_value = [
        {"asset": "USDT", "balance": "1000.0", "crossUnPnl": "50.0",
            "crossWalletBalance": "1050.0", "updateTime": 1234567890}
    ]
    connector.adapter.get_open_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "entryPrice": "50000.0",
            "unRealizedProfit": "100.0",
            "leverage": 10,
            "marginType": "cross",
            "markPrice": "51000.0",
            "liquidationPrice": "45000.0",
        }
    ]

    result = await connector._fetch_and_emit_account_data()

    assert result["balance_assets"] == 1
    assert result["positions_total"] == 1
    assert mock_fsm.emit.call_count == 2  # Balance and positions updates
