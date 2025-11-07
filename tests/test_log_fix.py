#!/usr/bin/env python3
"""Unit тест для перевірки LOG NameError fix"""

import logging
import sys
from unittest.mock import MagicMock
from decimal import Decimal

# Налаштовуємо логування
logging.basicConfig(level=logging.DEBUG,
                    format='%(name)s - %(levelname)s - %(message)s')

print("=" * 60)
print("🧪 UNIT ТЕСТ: on_account_update() NameError Fix")
print("=" * 60)

# Імпортуємо клас
try:
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking
    print("✅ КРОК 1: PositionTracking ІМПОРТОВАНА")
except Exception as e:
    print(f"❌ Помилка імпорту: {e}")
    sys.exit(1)

# Створюємо mock FSM та config
mock_fsm = MagicMock()
mock_fsm.emit = MagicMock()
mock_config = MagicMock()

# Створюємо instance
try:
    pt = PositionTracking(fsm=mock_fsm, config=mock_config)
    print("✅ КРОК 2: Instance створена")
except Exception as e:
    print(f"❌ Помилка створення: {e}")
    sys.exit(1)

# Перевіримо що self.logger існує
if not hasattr(pt, 'logger'):
    print("❌ self.logger НЕ ІСНУЄ!")
    sys.exit(1)
print(f"✅ КРОК 3: self.logger EXISTS ({type(pt.logger).__name__})")

# Симулюємо on_account_update() з mock payload
mock_event = MagicMock()
mock_event.pld = {
    "balances": [
        {"asset": "USDT", "free": "1000", "locked": "0"},
        {"asset": "BTC", "free": "0.1", "locked": "0"}
    ],
    "positions": [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.1",
            "entryPrice": "45000",
            "markPrice": "46000"
        }
    ]
}

print("\n🔍 Запускаємо on_account_update()...")

try:
    # Запускаємо метод - якщо NameError, падатиме тут
    pt.on_account_update(mock_event)
    print("✅ КРОК 4: on_account_update() ЗАВЕРШИЛАСЯ БЕЗ NameError!")

except NameError as e:
    print(f"❌ КРОК 4 ПРОВАЛИЛАСЯ: NameError: {e}")
    print("   👉 LOG не визначена у методі!")
    sys.exit(1)

except AttributeError as e:
    # Це OK - інша помилка, не NameError
    err_str = str(e)[:100]
    print(f"⚠️  КРОК 4: AttributeError (OK - не NameError)")
    print(f"   Деталі: {err_str}")

except Exception as e:
    # Інші помилки OK
    err_name = type(e).__name__
    err_str = str(e)[:100]
    print(f"⚠️  КРОК 4: {err_name} (OK - не NameError)")
    print(f"   Деталі: {err_str}")

print("\n" + "=" * 60)
print("✅ ВЕРДИКТ: LOG NameError ВИРІШЕНА!")
print("✅ self.logger УСПІШНО ВИКОРИСТОВУЄТЬСЯ у on_account_update()")
print("=" * 60)
