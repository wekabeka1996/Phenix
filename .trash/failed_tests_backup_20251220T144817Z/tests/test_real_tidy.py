#!/usr/bin/env python3
"""
Реальний тест TIDY/gate функціональності з BinanceAdapter на testnet
"""

from apps.reference.config_loader import ConfigLoader
from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.domains.execution_position.order_guardian import OrderGuardian
import asyncio
import logging
import sys
import os
from pathlib import Path

# Додаємо корінь проекту до шляху
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


class RealBus:
    """Реальний event bus для тестування подій"""

    def __init__(self):
        self.events = []

    def emit(self, event_type, data=None):
        self.events.append((event_type, data))
        LOG.info(f"📡 RealBus: {event_type} -> {data}")

    def listen(self, event_type, callback):
        LOG.info(f"👂 RealBus: listening for {event_type}")


async def test_real_tidy_flow():
    """Реальний тест TIDY/gate з BinanceAdapter на testnet"""
    try:
        LOG.info("🔍 Початок реального тесту TIDY/gate на testnet")

        # Завантажуємо конфігурацію через ConfigLoader
        loader = ConfigLoader()
        config = loader.load_config()
        LOG.info("✅ Конфігурація завантажена через ConfigLoader")

        # Створюємо BinanceAdapter для testnet
        testnet_config = config.binance_api.testnet
        adapter = BinanceAdapter(
            api_key=os.getenv("BINANCE_TESTNET_API_KEY",
                              testnet_config.api_key),
            api_secret=os.getenv("BINANCE_TESTNET_API_SECRET",
                                 testnet_config.api_secret),
            base_url=testnet_config.rest_url,
            config=config.execution
        )
        LOG.info("✅ BinanceAdapter створений для testnet")

        # Створюємо event bus
        bus = RealBus()

        # Створюємо guardian
        guardian = OrderGuardian(
            adapter=adapter,
            config=config,
            poll_interval_ms=0,
            bus=bus
        )
        LOG.info("✅ OrderGuardian створений з реальним адаптером")

        # Перевіряємо з'єднання з API
        LOG.info("🔗 Перевіряємо з'єднання з Binance testnet API")
        try:
            # Спробуємо отримати баланс
            balance = await adapter.get_account_balance()
            LOG.info(f"✅ API працює, знайдено {len(balance)} балансів")

            # Спробуємо отримати позиції
            positions = await adapter.get_open_positions()
            LOG.info(f"📊 Поточні позиції: {len(positions)}")

            # Спробуємо отримати відкриті ордери
            open_orders = await adapter.get_open_orders()
            LOG.info(f"📋 Відкриті ордери: {len(open_orders)}")

        except Exception as e:
            LOG.error(f"❌ Помилка з'єднання з API: {e}")
            LOG.warning("⚠️ Продовжуємо тест з обмеженою функціональністю")
            return False

        # === Фаза 1: Перевіряємо поточний стан ===
        LOG.info("📊 Фаза 1: Перевіряємо поточний стан BTCUSDT")

        # Перевіряємо позиції для BTCUSDT
        positions = await adapter.get_open_positions()
        btc_positions = [p for p in positions if p.symbol == "BTCUSDT"]
        has_position = len(btc_positions) > 0

        # Перевіряємо відкриті ордери для BTCUSDT
        open_orders = await adapter.get_open_orders("BTCUSDT")
        bracket_orders = [o for o in open_orders if o.status == "NEW" and
                          ("STOP_MARKET" in str(o.price) or "TAKE_PROFIT_MARKET" in str(o.price))]

        LOG.info(
            f"📊 BTCUSDT - позиції: {len(btc_positions)}, bracket ордери: {len(bracket_orders)}")

        if has_position:
            LOG.info("⚠️ Знайдено відкриту позицію BTCUSDT - тест буде обмеженим")
            # Якщо є позиція, просто перевіряємо reconcile без cleanup
            await guardian.reconcile_symbol("BTCUSDT", "test_rid_1")
            LOG.info("✅ Reconcile виконано без cleanup (позиція існує)")
        else:
            LOG.info(
                "✅ Немає відкритої позиції BTCUSDT - можемо тестувати повний цикл")

            if bracket_orders:
                LOG.info(
                    f"🧹 Знайдено {len(bracket_orders)} bracket ордерів - запускаємо cleanup")
                cancelled = await guardian.cleanup_orphans(symbol="BTCUSDT", hard=True)
                LOG.info(f"🧹 Cleanup скасував {cancelled} orphans")

                # Повторна перевірка після cleanup
                open_orders_after = await adapter.get_open_orders("BTCUSDT")
                bracket_orders_after = [o for o in open_orders_after if o.status == "NEW" and
                                        ("STOP_MARKET" in str(o.price) or "TAKE_PROFIT_MARKET" in str(o.price))]
                LOG.info(
                    f"📊 Після cleanup: bracket ордери: {len(bracket_orders_after)}")

                # Перевіряємо чи відправлено EVT:SYMBOL_TIDY
                tidy_events = [e for e in bus.events if e[0]
                               == "EVT:SYMBOL_TIDY"]
                if tidy_events:
                    LOG.info(f"✅ EVT:SYMBOL_TIDY відправлено: {tidy_events}")
                else:
                    LOG.info("⚠️ EVT:SYMBOL_TIDY не відправлено")
            else:
                LOG.info("✅ Немає bracket ордерів - символ вже tidy")

        # === Підсумок тесту ===
        LOG.info("📋 Підсумок реального тесту TIDY/gate:")
        LOG.info(f"  - Подій в bus: {len(bus.events)}")
        LOG.info(
            f"  - TIDY подій: {len([e for e in bus.events if e[0] == 'EVT:SYMBOL_TIDY'])}")
        LOG.info("🎉 Реальний тест TIDY/gate завершено успішно")

        # Закриваємо з'єднання
        await adapter.aclose()
        LOG.info("🔌 З'єднання з Binance API закрито")

        return True

    except Exception as e:
        LOG.error(f"❌ Помилка в реальному тесті: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_real_tidy_flow())
    sys.exit(0 if success else 1)
