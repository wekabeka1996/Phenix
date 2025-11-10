#!/usr/bin/env python3
"""
Простий тест для перевірки TIDY/gate функціональності
"""

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.domains.execution_position.order_guardian import OrderGuardian
from apps.reference.config_loader import ConfigLoader
import asyncio
import logging
import sys
import os
from pathlib import Path

# Додаємо корінь проекту до шляху
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


async def test_tidy_gate():
    """Тест TIDY/gate функціональності"""
    try:
        LOG.info("🔍 Початок тесту TIDY/gate функціональності")

        # Завантажуємо конфігурацію
        config_loader = ConfigLoader()
        config = config_loader.load_config('config/aurora/trading.yaml')
        LOG.info("✅ Конфігурація завантажена")

        # Створюємо адаптер (симуляція)
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            shadow_mode=True
        )
        LOG.info("✅ Адаптер створений (shadow mode)")

        # Створюємо OrderGuardian
        guardian = OrderGuardian(
            adapter=adapter,
            config=config.get('guardian', {}),
            unified=True
        )
        LOG.info("✅ OrderGuardian створений")

        # Тестуємо базові методи
        LOG.info("🔍 Тестування get_open_positions...")
        positions = await adapter.get_open_positions()
        LOG.info(f"📊 Поточні позиції: {len(positions)}")

        LOG.info("🔍 Тестування reconcile_symbol для BTCUSDT...")
        await guardian.reconcile_symbol('BTCUSDT')
        LOG.info("✅ reconcile_symbol виконано")

        # Перевіряємо метрики
        metrics = guardian.get_metrics()
        LOG.info(f"📊 Метрики guardian: {metrics}")

        # Перевіряємо gate стан
        gate_status = guardian.get_gate_status()
        LOG.info(f"🚪 Стан gate: {gate_status}")

        LOG.info("🎉 Тест TIDY/gate завершено успішно")

    except Exception as e:
        LOG.error(f"❌ Помилка в тесті: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_tidy_gate())
    sys.exit(0 if success else 1)
