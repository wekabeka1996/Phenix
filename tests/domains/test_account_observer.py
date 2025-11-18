"""
Tests for Account Observer domain.
"""

from unittest.mock import AsyncMock, MagicMock
import logging
import asyncio
import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.account_observer.account_observer import AccountObserver


class TestAccountObserver:
    @pytest.fixture
    def mock_config(self):
        return {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://testnet.binancefuture.com",
                }
            },
            "account_observer": {"poll_interval": 5, "symbols": ["BTCUSDT", "ETHUSDT"]},
        }

    @pytest.fixture
    def mock_fsm(self):
        return Mock()

    @patch("apps.reference.domains.account_observer.account_observer.Client")
    def test_init_success(self, mock_client, mock_fsm, mock_config):
        """Test successful initialization."""
        observer = AccountObserver(mock_fsm, mock_config)
        assert observer.config == mock_config
        assert observer.fsm is not None

    def test_init_missing_api_key(self, mock_fsm):
        """Test initialization fails when API key is missing."""
        config = {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_secret": "secret",
                    "rest_url": "https://testnet.binancefuture.com",
                    # Missing api_key
                }
            },
        }
        with pytest.raises(ValueError):
            AccountObserver(mock_fsm, config)


# Additional tests for coverage improvement


@pytest.fixture
def mock_fsm_extended():
    """Provides a mock FSM instance with an emit method."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    return fsm


@pytest.fixture
def mock_config_extended():
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


def test_init_live_mode(mock_fsm_extended, mock_config_extended):
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
    observer = AccountObserver(fsm=mock_fsm_extended, config=config)
    assert observer.poll_interval == 30


@patch("apps.reference.domains.account_observer.account_observer.threading.Thread")
def test_start_success(mock_thread, mock_fsm_extended, mock_config_extended):
    """Test successful start of monitoring."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.start()
    assert observer._polling_thread is not None
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()


def test_start_already_running(mock_fsm_extended, mock_config_extended, caplog):
    """Test start when already running."""
    caplog.set_level(logging.WARNING)
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer._polling_thread = MagicMock()  # Simulate already started
    observer.start()
    assert "AccountObserver already started" in caplog.text


@patch("apps.reference.domains.account_observer.account_observer.threading.Event")
def test_stop_success(mock_event, mock_fsm_extended, mock_config_extended):
    """Test successful stop of monitoring."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    observer._polling_thread = mock_thread
    observer._stop_polling = MagicMock()

    observer.stop()

    observer._stop_polling.set.assert_called_once()
    mock_thread.join.assert_called_once()


def test_poll_trades_success(mock_fsm_extended, mock_config_extended):
    """Test successful polling of trades."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.return_value = [
        {
            "id": 12345,
            "symbol": "BTCUSDT",
            "price": "50000.0",
            "qty": "1.0",
            "quoteQty": "50000.0",
            "commission": "5.0",
            "commissionAsset": "USDT",
            "time": 1234567890000,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True,
            "orderId": 67890,
        }
    ]
    observer.processed_trade_ids = {12344}

    observer._poll_trades()

    observer.client.get_my_trades.assert_called()
    # Should emit both TRADE_EXECUTED and FILL events
    assert mock_fsm_extended.emit.call_count == 2
    calls = mock_fsm_extended.emit.call_args_list
    assert calls[0][0][0] == "EVT:TRADE_EXECUTED"  # First positional arg
    assert calls[1][0][0] == "EVT:FILL"  # Second positional arg
    payload = calls[0][1]["payload"]  # Keyword args
    assert payload["symbol"] == "BTCUSDT"
    assert payload["price"] == "50000.0"
    assert payload["quantity"] == "1.0"
    assert payload["side"] == "buy"


def test_poll_trades_no_new_trades(mock_fsm_extended, mock_config_extended):
    """Test polling when no new trades are available."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.return_value = [
        {"id": 12344}  # Same as processed
    ]
    observer.processed_trade_ids = {12344}

    observer._poll_trades()

    observer.client.get_my_trades.assert_called()
    mock_fsm_extended.emit.assert_not_called()


def test_poll_trades_empty_response(mock_fsm_extended, mock_config_extended):
    """Test polling with empty response."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.return_value = []

    observer._poll_trades()

    observer.client.get_my_trades.assert_called()
    mock_fsm_extended.emit.assert_not_called()


def test_poll_trades_exception(mock_fsm_extended, mock_config_extended, caplog):
    """Test polling handles exceptions gracefully."""
    caplog.set_level(logging.DEBUG)
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.side_effect = Exception("API error")

    observer._poll_trades()

    assert any(
        "Error getting trades for" in record.message for record in caplog.records)
    mock_fsm_extended.emit.assert_not_called()


def test_process_trades_success(mock_fsm_extended, mock_config_extended):
    """Test successful processing of trades."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    trades = [
        {
            "id": 12345,
            "symbol": "BTCUSDT",
            "price": "50000.0",
            "qty": "1.0",
            "quoteQty": "50000.0",
            "commission": "5.0",
            "commissionAsset": "USDT",
            "time": 1234567890000,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True,
            "orderId": 67890,
        }
    ]

    observer._process_trades(trades, "binance")

    # Should emit both TRADE_EXECUTED and FILL events
    assert mock_fsm_extended.emit.call_count == 2
    calls = mock_fsm_extended.emit.call_args_list
    assert calls[0][0][0] == "EVT:TRADE_EXECUTED"
    assert calls[1][0][0] == "EVT:FILL"
    payload = calls[0][1]["payload"]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["price"] == "50000.0"
    assert payload["quantity"] == "1.0"
    assert payload["side"] == "buy"


def test_process_trades_multiple(mock_fsm_extended, mock_config_extended):
    """Test processing multiple trades."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    trades = [
        {
            "id": 12345,
            "symbol": "BTCUSDT",
            "price": "50000.0",
            "qty": "1.0",
            "quoteQty": "50000.0",
            "commission": "5.0",
            "commissionAsset": "USDT",
            "time": 1234567890000,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True,
            "orderId": 67890,
        },
        {
            "id": 12346,
            "symbol": "ETHUSDT",
            "price": "3000.0",
            "qty": "2.0",
            "quoteQty": "6000.0",
            "commission": "3.0",
            "commissionAsset": "USDT",
            "time": 1234567900000,
            "isBuyer": False,
            "isMaker": True,
            "isBestMatch": True,
            "orderId": 67891,
        }
    ]

    observer._process_trades(trades, "binance")

    assert mock_fsm_extended.emit.call_count == 4  # 2 events per trade


def test_trade_to_payload_buy(mock_fsm_extended, mock_config_extended):
    """Test trade to payload conversion for buy trade."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    trade = {
        "id": 12345,
        "symbol": "BTCUSDT",
        "price": "50000.0",
        "qty": "1.0",
        "quoteQty": "50000.0",
        "commission": "5.0",
        "commissionAsset": "USDT",
        "time": 1234567890000,
        "isBuyer": True,
        "isMaker": False,
        "isBestMatch": True,
        "orderId": 67890,
    }

    payload = observer._trade_to_payload(trade, "binance")

    assert payload["symbol"] == "BTCUSDT"
    assert payload["price"] == "50000.0"
    assert payload["quantity"] == "1.0"
    assert payload["side"] == "buy"
    assert payload["fees"] == "5.0"
    assert payload["venue"] == "binance"
    assert payload["orderId"] == "67890"
    assert payload["ts"] == 1234567890000


def test_trade_to_payload_sell(mock_fsm_extended, mock_config_extended):
    """Test trade to payload conversion for sell trade."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    trade = {
        "id": 12346,
        "symbol": "ETHUSDT",
        "price": "3000.0",
        "qty": "2.0",
        "quoteQty": "6000.0",
        "commission": "3.0",
        "commissionAsset": "USDT",
        "time": 1234567900000,
        "isBuyer": False,
        "isMaker": True,
        "isBestMatch": False,
        "orderId": 67891,
    }

    payload = observer._trade_to_payload(trade, "binance")

    assert payload["symbol"] == "ETHUSDT"
    assert payload["price"] == "3000.0"
    assert payload["quantity"] == "-2.0"
    assert payload["side"] == "sell"
    assert payload["fees"] == "3.0"
    assert payload["venue"] == "binance"
    assert payload["orderId"] == "67891"
    assert payload["ts"] == 1234567900000


@patch("threading.Event.wait")
def test_poll_loop_success(mock_wait, mock_fsm_extended, mock_config_extended):
    """Test successful poll loop execution."""
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.return_value = []
    observer._stop_polling = MagicMock()
    observer._stop_polling.is_set.side_effect = [
        False, True]  # Stop after one iteration

    observer._poll_loop()

    observer.client.get_my_trades.assert_called()


@patch("threading.Event.wait")
def test_poll_loop_exception_handling(mock_wait, mock_fsm_extended, mock_config_extended, caplog):
    """Test poll loop handles exceptions gracefully."""
    caplog.set_level(logging.DEBUG)
    observer = AccountObserver(
        fsm=mock_fsm_extended, config=mock_config_extended)
    observer.client = MagicMock()
    observer.client.get_my_trades.side_effect = Exception("API error")
    observer._stop_polling = MagicMock()
    observer._stop_polling.is_set.side_effect = [
        False, True]  # Stop after one iteration

    observer._poll_loop()

    # Check for either error message
    has_error = any(
        "Error polling trades" in record.message or "Error getting trades for" in record.message for record in caplog.records)
    assert has_error
