#!/usr/bin/env python3
"""
Приклади тестів для домену account_balance

Демонструє:
1. Модульні тести для окремих функцій
2. Інтеграційні тести з моками API
3. Тести обробки помилок
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any


# Мок класи для тестування
class MockFSMCore:
    def __init__(self):
        self.events = []

    def emit(self, event_name: str, payload: Dict[str, Any], why: str):
        self.events.append({"event_name": event_name, "payload": payload, "why": why})


class MockBinanceAdapter:
    def __init__(self):
        self.get_account_balance = AsyncMock()
        self.get_open_positions = AsyncMock()
        self.close_session = AsyncMock()


# Приклад модульного тесту
def test_account_connector_initialization():
    """Тест ініціалізації AccountConnector"""
    from apps.reference.domains.account_balance import AccountConnector

    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }

    fsm = MockFSMCore()

    # Тест успішної ініціалізації
    connector = AccountConnector(fsm, config)
    assert connector.update_interval == 30
    assert connector.running == False
    assert connector._latest_balance_data is None

    print("✅ Тест ініціалізації пройдено")


# Приклад тесту з моками API
@pytest.mark.asyncio
async def test_balance_update_emission():
    """Тест емісії події оновлення балансу"""
    from apps.reference.domains.account_balance import AccountConnector

    # Мок дані API
    mock_balance_data = [
        {
            "asset": "USDT",
            "balance": "1000.50",
            "crossUnPnl": "25.30",
            "crossWalletBalance": "975.20",
            "updateTime": 1640995200000,
        },
        {
            "asset": "BTC",
            "balance": "0.000",  # буде відфільтровано
            "crossUnPnl": "0.00",
            "crossWalletBalance": "0.000",
            "updateTime": 1640995200000,
        },
    ]

    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }

    fsm = MockFSMCore()
    connector = AccountConnector(fsm, config)

    # Виклик методу емісії
    connector._emit_balance_update(mock_balance_data)

    # Перевірка емісії події
    assert len(fsm.events) == 1
    event = fsm.events[0]

    assert event["event_name"] == "EVT:BALANCE_UPDATE_RECEIVED"
    assert event["why"] == "Balance data updated from Binance API."

    payload = event["payload"]
    assert "assets" in payload
    assert "updateTime" in payload
    assert len(payload["assets"]) == 1  # тільки USDT з балансом > 0
    assert payload["assets"][0]["asset"] == "USDT"

    print("✅ Тест емісії балансу пройдено")


# Приклад тесту обробки помилок
@pytest.mark.asyncio
async def test_api_error_handling():
    """Тест обробки помилок API"""
    from apps.reference.domains.account_balance import AccountConnector

    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }

    fsm = MockFSMCore()
    connector = AccountConnector(fsm, config)

    # Мок адаптера з помилкою
    mock_adapter = MockBinanceAdapter()
    mock_adapter.get_account_balance.side_effect = Exception("API Error")
    mock_adapter.get_open_positions.side_effect = Exception("API Error")
    connector.adapter = mock_adapter

    # Виклик методу отримання даних
    await connector._fetch_and_emit_account_data()

    # Перевірка, що події не емітувались через помилки
    assert len(fsm.events) == 0

    print("✅ Тест обробки помилок пройдено")


# Приклад інтеграційного тесту
@pytest.mark.asyncio
async def test_full_data_flow():
    """Тест повного потоку даних від API до FSM"""
    from apps.reference.domains.account_balance import AccountConnector

    # Мок дані API
    mock_balance_data = [
        {
            "asset": "USDT",
            "balance": "1000.50",
            "crossUnPnl": "25.30",
            "crossWalletBalance": "975.20",
            "updateTime": 1640995200000,
        }
    ]

    mock_positions_data = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.001",
            "entryPrice": "50000.00",
            "unRealizedProfit": "5.25",
            "leverage": 10,
            "marginType": "cross",
            "markPrice": "50250.00",
            "liquidationPrice": "45000.00",
        }
    ]

    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }

    fsm = MockFSMCore()
    connector = AccountConnector(fsm, config)

    # Мок адаптера
    mock_adapter = MockBinanceAdapter()
    mock_adapter.get_account_balance.return_value = mock_balance_data
    mock_adapter.get_open_positions.return_value = mock_positions_data
    connector.adapter = mock_adapter

    # Запуск повного циклу
    await connector._fetch_and_emit_account_data()

    # Перевірка емісії обох подій
    assert len(fsm.events) == 2

    # Перевірка події балансу
    balance_event = next(
        e for e in fsm.events if e["event_name"] == "EVT:BALANCE_UPDATE_RECEIVED"
    )
    assert len(balance_event["payload"]["assets"]) == 1

    # Перевірка події позицій
    account_event = next(
        e for e in fsm.events if e["event_name"] == "EVT:ACCOUNT_UPDATE_RECEIVED"
    )
    assert len(account_event["payload"]["positions"]) == 1
    assert account_event["payload"]["totalWalletBalance"] == "1000.50"

    print("✅ Тест повного потоку даних пройдено")


# Приклад параметризованого тесту
@pytest.mark.parametrize(
    "balance_value,expected_filtered",
    [
        ("1000.50", True),  # баланс > 0 - має бути включено
        ("0.000", False),  # баланс = 0 - має бути відфільтровано
        ("-10.00", False),  # негативний баланс - має бути відфільтровано
    ],
)
def test_balance_filtering(balance_value, expected_filtered):
    """Тест фільтрації активів за балансом"""
    from apps.reference.domains.account_balance import AccountConnector

    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {"poll_interval": 30},
    }

    fsm = MockFSMCore()
    connector = AccountConnector(fsm, config)

    # Тестові дані
    balance_data = [
        {
            "asset": "TEST",
            "balance": balance_value,
            "crossUnPnl": "0.00",
            "crossWalletBalance": balance_value,
            "updateTime": 1640995200000,
        }
    ]

    # Виклик методу
    connector._emit_balance_update(balance_data)

    # Перевірка результату
    if expected_filtered:
        assert len(fsm.events) == 1
        assert len(fsm.events[0]["payload"]["assets"]) == 1
    else:
        assert len(fsm.events) == 1
        assert len(fsm.events[0]["payload"]["assets"]) == 0

    print(f"✅ Тест фільтрації балансу {balance_value} пройдено")


# Функція для запуску прикладів тестів
def run_examples():
    """Запуск прикладів тестів"""
    print("🚀 Запуск прикладів тестів для account_balance домену")
    print()

    # Запуск синхронних тестів
    test_account_connector_initialization()
    test_balance_filtering("1000.50", True)
    test_balance_filtering("0.000", False)

    # Запуск асинхронних тестів через asyncio
    asyncio.run(run_async_examples())

    print()
    print("✅ Всі приклади тестів пройдено успішно")


async def run_async_examples():
    """Запуск асинхронних прикладів тестів"""
    await test_balance_update_emission()
    await test_api_error_handling()
    await test_full_data_flow()


if __name__ == "__main__":
    run_examples()
