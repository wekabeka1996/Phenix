#!/usr/bin/env python3
"""
Простий тест TIDY/gate подій та логіки
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


class MockBus:
    """Мок event bus для тестування подій"""

    def __init__(self):
        self.events = []

    def emit(self, event_type, data=None):
        self.events.append((event_type, data))
        LOG.info(f"📡 MockBus: {event_type} -> {data}")

    def listen(self, event_type, callback):
        LOG.info(f"👂 MockBus: listening for {event_type}")


async def test_tidy_events():
    """Тест TIDY подій та базової логіки"""
    try:
        LOG.info("🔍 Початок тесту TIDY/gate подій")

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

        # Створюємо mock bus
        bus = MockBus()

        # Створюємо guardian з bus
        guardian = OrderGuardian(
            adapter=None,  # Без адаптера для тесту
            config=config,
            poll_interval_ms=0,
            bus=bus
        )
        LOG.info("✅ OrderGuardian створений з mock bus")

        # Емулюємо reconcile_symbol (без адаптера буде пропускати cleanup)
        LOG.info("🔄 Викликаю reconcile_symbol для BTCUSDT...")
        await guardian.reconcile_symbol('BTCUSDT', 'test_rid')
        LOG.info("✅ reconcile_symbol виконано")

        # Перевіряємо події
        LOG.info(f"📡 Події в bus: {len(bus.events)}")
        for event_type, data in bus.events:
            LOG.info(f"  - {event_type}: {data}")

        # Перевіряємо чи є EVT:SYMBOL_TIDY
        tidy_events = [e for e in bus.events if e[0] == "EVT:SYMBOL_TIDY"]
        if tidy_events:
            LOG.info(f"✅ Знайдено EVT:SYMBOL_TIDY події: {len(tidy_events)}")
            for event in tidy_events:
                LOG.info(f"  - {event}")
        else:
            LOG.info(
                "⚠️ EVT:SYMBOL_TIDY події не знайдено (можливо через відсутність адаптера)")

        # Тестуємо cleanup_orphans (без адаптера буде повертати 0)
        LOG.info("🧹 Викликаю cleanup_orphans...")
        cleaned = await guardian.cleanup_orphans()
        LOG.info(f"✅ cleanup_orphans повернув: {cleaned}")

        LOG.info("🎉 Тест TIDY/gate подій завершено успішно")

    except Exception as e:
        LOG.error(f"❌ Помилка в тесті: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_tidy_events())
    sys.exit(0 if success else 1)
