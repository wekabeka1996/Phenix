#!/usr/bin/env python3
"""
Мінімальний тест TIDY/gate логіки без API викликів
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


async def test_guardian_logic():
    """Тест тільки логіки guardian без API"""
    try:
        LOG.info("🔍 Початок мінімального тесту guardian логіки")

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

        # Створюємо guardian без адаптера (None)
        guardian = OrderGuardian(
            adapter=None,  # Без адаптера
            config=config,
            poll_interval_ms=0
        )
        LOG.info("✅ OrderGuardian створений без адаптера")

        # Тестуємо методи що не потребують API
        metrics = guardian.get_metrics()
        LOG.info(f"📊 Початкові метрики: {metrics}")

        gate_status = guardian.get_gate_status()
        LOG.info(f"🚪 Початковий стан gate: {gate_status}")

        # Тестуємо gate логіку
        can_enter = guardian.can_enter_symbol('BTCUSDT')
        LOG.info(f"🚪 can_enter_symbol BTCUSDT: {can_enter}")

        # Емулюємо TIDY подію
        guardian.on_tidy_event('BTCUSDT')
        LOG.info("✅ Емулював TIDY подію для BTCUSDT")

        # Перевіряємо після TIDY
        can_enter_after_tidy = guardian.can_enter_symbol('BTCUSDT')
        LOG.info(
            f"🚪 can_enter_symbol BTCUSDT після TIDY: {can_enter_after_tidy}")

        # Фінальні метрики
        final_metrics = guardian.get_metrics()
        LOG.info(f"📊 Фінальні метрики: {final_metrics}")

        LOG.info("🎉 Мінімальний тест guardian логіки завершено успішно")

    except Exception as e:
        LOG.error(f"❌ Помилка в тесті: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_guardian_logic())
    sys.exit(0 if success else 1)
