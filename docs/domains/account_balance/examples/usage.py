#!/usr/bin/env python3
"""
Приклад використання домену account_balance

Цей приклад демонструє:
1. Ініціалізацію AccountConnector
2. Запуск моніторингу рахунку
3. Обробку FSM подій
4. Правильне завершення роботи
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# Імпорт компонентів системи (приклад - замініть на реальні імпорти)
# from vfoundation.core import FSMCore
# from apps.reference.domains.account_balance import AccountConnector

class MockFSMCore:
    """Мок FSM core для прикладу"""

    def __init__(self):
        self.handlers = {}

    def on(self, event_name: str, handler):
        self.handlers[event_name] = handler

    def emit(self, event_name: str, payload: Dict[str, Any], why: str):
        handler = self.handlers.get(event_name)
        if handler:
            try:
                handler(payload)
            except Exception as e:
                LOG.error(f"Error in event handler for {event_name}: {e}")

class ExampleFSMHandler:
    """Приклад обробника FSM подій для демонстрації"""

    def __init__(self):
        self.balance_updates = 0
        self.account_updates = 0

    def on_balance_update(self, event_data: Dict[str, Any]) -> None:
        """Обробка події EVT:BALANCE_UPDATE_RECEIVED"""
        self.balance_updates += 1
        assets = event_data.get('assets', [])
        LOG.info(f"📊 Balance Update #{self.balance_updates}: {len(assets)} assets")

        # Логування USDT балансу
        for asset in assets:
            if asset['asset'] == 'USDT':
                LOG.info(f"   💰 USDT Balance: {asset['balance']}")
                LOG.info(f"   📈 USDT Unrealized P&L: {asset['crossUnPnl']}")
                break

    def on_account_update(self, event_data: Dict[str, Any]) -> None:
        """Обробка події EVT:ACCOUNT_UPDATE_RECEIVED"""
        self.account_updates += 1
        positions = event_data.get('positions', [])
        wallet_balance = event_data.get('totalWalletBalance', '0')

        LOG.info(f"📊 Account Update #{self.account_updates}:")
        LOG.info(f"   💰 Wallet Balance: {wallet_balance}")
        LOG.info(f"   📈 Unrealized P&L: {event_data.get('totalUnrealizedProfit', '0')}")
        LOG.info(f"   📊 Open Positions: {len(positions)}")

        # Логування позицій
        for pos in positions[:3]:  # Показати максимум 3 позиції
            LOG.info(f"   🔄 {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")

class MockAccountConnector:
    """Мок AccountConnector для прикладу"""

    def __init__(self, fsm, config):
        self.fsm = fsm
        self.config = config
        self.running = False

    def start(self):
        LOG.info("🚀 Mock AccountConnector started")
        self.running = True

    def stop(self):
        LOG.info("🛑 Mock AccountConnector stopped")
        self.running = False

async def main():
    """Основна функція прикладу"""

    LOG.info("🚀 Запуск прикладу account_balance домену")

    # Приклад конфігурації (замініть на реальні значення)
    config = {
        "trading_mode": "testnet",  # або "live" для бойового режиму

        "binance_api": {
            "testnet": {
                "api_key": "your_testnet_api_key",
                "api_secret": "your_testnet_api_secret",
                "rest_url": "https://testnet.binancefuture.com"
            }
        },

        "account_observer": {
            "poll_interval": 30  # секунди
        }
    }

    # Створення FSM core (використовуємо мок для прикладу)
    fsm = MockFSMCore()

    # Створення обробника подій
    handler = ExampleFSMHandler()

    # Реєстрація обробників подій
    fsm.on("EVT:BALANCE_UPDATE_RECEIVED", handler.on_balance_update)
    fsm.on("EVT:ACCOUNT_UPDATE_RECEIVED", handler.on_account_update)

    # Створення AccountConnector (використовуємо мок для прикладу)
    connector = MockAccountConnector(fsm, config)
    LOG.info("✅ AccountConnector створено успішно")

    # Запуск моніторингу
    connector.start()
    LOG.info("✅ Моніторинг рахунку запущено")

    # Симуляція отримання даних (для демонстрації)
    await simulate_data_updates(fsm)

    # Обробка сигналів завершення
    def signal_handler(signum, frame):
        LOG.info(f"📴 Отримано сигнал {signum}, завершення роботи...")
        connector.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Основний цикл (буде працювати поки не отримаємо сигнал)
    try:
        while connector.running:
            await asyncio.sleep(1)

            # Періодично логувати статистику
            if handler.balance_updates > 0 and handler.balance_updates % 10 == 0:
                LOG.info(f"📈 Статистика: {handler.balance_updates} balance updates, "
                        f"{handler.account_updates} account updates")

    except KeyboardInterrupt:
        LOG.info("📴 KeyboardInterrupt, завершення роботи...")

    finally:
        # Гарантоване завершення
        connector.stop()
        LOG.info("✅ AccountConnector зупинено")

async def simulate_data_updates(fsm: MockFSMCore):
    """Симуляція отримання даних для демонстрації"""
    await asyncio.sleep(2)  # Затримка перед початком

    # Симуляція balance update
    balance_payload = {
        'assets': [
            {
                'asset': 'USDT',
                'balance': '1000.50',
                'crossUnPnl': '25.30',
                'crossWalletBalance': '975.20',
                'updateTime': 1640995200000
            },
            {
                'asset': 'BTC',
                'balance': '0.025',
                'crossUnPnl': '2.15',
                'crossWalletBalance': '0.023',
                'updateTime': 1640995200000
            }
        ],
        'updateTime': 1640995200000
    }

    # Симуляція account update
    account_payload = {
        'totalWalletBalance': '1000.50',
        'totalUnrealizedProfit': '25.30',
        'totalCrossWalletBalance': '975.20',
        'positions': [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.001',
                'entryPrice': '50000.00',
                'unRealizedProfit': '5.25',
                'leverage': 10,
                'marginType': 'cross',
                'markPrice': '50250.00',
                'liquidationPrice': '45000.00'
            }
        ],
        'updateTime': 1640995200000
    }

    # Емісія подій
    fsm.emit("EVT:BALANCE_UPDATE_RECEIVED", balance_payload, "Simulated balance update")
    await asyncio.sleep(1)
    fsm.emit("EVT:ACCOUNT_UPDATE_RECEIVED", account_payload, "Simulated account update")

if __name__ == "__main__":
    # Перевірка наявності API ключів (приклад)
    import os

    # Для прикладу використовуємо мок, тому перевірка не обов'язкова
    # required_env_vars = ["BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"]
    # missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    # if missing_vars:
    #     LOG.error(f"❌ Відсутні обов'язкові змінні середовища: {missing_vars}")
    #     LOG.info("💡 Встановіть їх у .env файлі або експортуйте в shell")
    #     sys.exit(1)

    # Запуск прикладу
    asyncio.run(main())</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\examples\usage.py 
 