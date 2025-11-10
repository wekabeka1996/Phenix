#!/usr/bin/env python3
"""
Повний тест TIDY/gate функціональності з реєстрацією ордерів
"""

from apps.reference.domains.execution_position.order_guardian import OrderGuardian
import asyncio
import logging
import sys
from pathlib import Path

# Додаємо корінь проекту до шляху
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


class MockAdapter:
    """Мок адаптер для тестування без API"""

    def __init__(self):
        self.positions = []
        self.open_orders = []

    async def get_open_positions(self):
        return self.positions

    async def get_open_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_orders if o.get("symbol") == symbol]
        return self.open_orders

    async def cancel_order(self, symbol, order_id):
        # Емулюємо успішну скасування та видаляємо з open_orders
        self.open_orders = [
            o for o in self.open_orders if o.get("orderId") != order_id]
        return {"status": "CANCELED", "orderId": order_id}


class MockBus:
    """Мок event bus для тестування подій"""

    def __init__(self):
        self.events = []

    def emit(self, event_type, data=None):
        self.events.append((event_type, data))
        LOG.info(f"📡 MockBus: {event_type} -> {data}")

    def listen(self, event_type, callback):
        LOG.info(f"👂 MockBus: listening for {event_type}")


async def test_full_tidy_flow():
    """Повний тест TIDY/gate з реєстрацією та cleanup"""
    try:
        LOG.info("🔍 Початок повного тесту TIDY/gate")

        # Створюємо конфігурацію
        config = {
            "guardian": {
                "unified": True,
                "emit_tidy_event": True,
                "cleanup_ttl_ms": 6000,
                "symbol_cooldown_ms": 4000
            },
            "execution": {
                "allow_trade_with_guardian_tidy_only": True,
                "fsm_periodic_cleanup_enabled": False,
                "preflight_backoff_ms": [120, 250, 400, 800, 1200, 1800],
                "anti_race_close_ms": 800,
                "min_post_interval_per_symbol_ms": 300
            }
        }

        # Створюємо mock компоненти
        adapter = MockAdapter()
        bus = MockBus()

        # Створюємо guardian
        guardian = OrderGuardian(
            adapter=adapter,
            config=config,
            poll_interval_ms=0,
            bus=bus
        )
        LOG.info("✅ OrderGuardian створений з mock компонентами")

        # === Фаза 1: Реєструємо entry ордер ===
        LOG.info("📝 Фаза 1: Реєструємо entry ордер")
        guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="entry_001",
            side="BUY",
            qty=0.001
        )

        # === Фаза 2: Реєструємо bracket ордери ===
        LOG.info("📝 Фаза 2: Реєструємо SL та TP ордери")
        guardian.register_brackets(
            symbol="BTCUSDT",
            entry_order_id="12345",
            sl_order_id="67890",
            tp_order_id="54321",
            sl_client_id="sl_001",
            tp_client_id="tp_001"
        )

        # Перевіряємо brackets для entry
        brackets = guardian.get_brackets_for_entry("12345")
        LOG.info(f"🔗 Brackets для entry 12345: {brackets}")
        if not brackets:
            LOG.warning("⚠️ Brackets порожні! Перевіряємо чи entry існує...")
            # Можливо, проблема з clock або store
            LOG.info(f"Guardian має store: {hasattr(guardian._impl, 'store')}")
            LOG.info(f"Guardian має clock: {hasattr(guardian._impl, 'clock')}")

        # === Фаза 3: Емулюємо позицію (є позиція) ===
        LOG.info("📊 Фаза 3: Емулюємо наявність позиції")
        adapter.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.001"}]

        # Викликаємо reconcile - має пропустити cleanup
        await guardian.reconcile_symbol("BTCUSDT", "test_rid_1")
        LOG.info(f"📡 Події після reconcile з позицією: {len(bus.events)}")

        # === Фаза 4: Емулюємо закриття позиції ===
        LOG.info("📊 Фаза 4: Емулюємо закриття позиції")
        adapter.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.0"}]

        # Додаємо bracket ордери в open_orders
        adapter.open_orders = [
            {
                "orderId": "67890",
                "clientOrderId": "sl_001",
                "symbol": "BTCUSDT",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "closePosition": True
            },
            {
                "orderId": "54321",
                "clientOrderId": "tp_001",
                "symbol": "BTCUSDT",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": True
            }
        ]

        # Викликаємо reconcile - має очистити brackets та відправити TIDY
        await guardian.reconcile_symbol("BTCUSDT", "test_rid_2")
        LOG.info(f"📡 Події після reconcile без позиції: {len(bus.events)}")

        # Перевіряємо чи є EVT:SYMBOL_TIDY
        tidy_events = [e for e in bus.events if e[0] == "EVT:SYMBOL_TIDY"]
        if tidy_events:
            LOG.info(f"✅ Знайдено EVT:SYMBOL_TIDY: {tidy_events}")
        else:
            LOG.info("⚠️ EVT:SYMBOL_TIDY не знайдено")

        # === Фаза 5: Перевіряємо cleanup ===
        LOG.info("🧹 Фаза 5: Перевіряємо cleanup orphans")
        cleaned = await guardian.cleanup_orphans(symbol="BTCUSDT", hard=True)
        LOG.info(f"🧹 Cleanup повернув: {cleaned}")

        LOG.info("🎉 Повний тест TIDY/gate завершено успішно")

        # Підсумок
        LOG.info("📋 Підсумок тесту:")
        LOG.info(f"  - Подій в bus: {len(bus.events)}")
        LOG.info(f"  - TIDY подій: {len(tidy_events)}")
        LOG.info(f"  - Очищено orphans: {cleaned}")

    except Exception as e:
        LOG.error(f"❌ Помилка в тесті: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_full_tidy_flow())
    sys.exit(0 if success else 1)
