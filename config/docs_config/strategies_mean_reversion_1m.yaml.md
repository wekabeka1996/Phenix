# Паспортізація конфігурації: strategies/mean_reversion_1m.yaml

---

## Загальний опис

Файл `strategies/mean_reversion_1m.yaml` містить розширені параметри для стратегії середньоринкової (mean reversion) на 1-хвилинних барах для окремих активів. Дозволяє задавати унікальні налаштування для кожного активу, які мають пріоритет над глобальними параметрами.

---

## Формат документації для кожного активу

- **enabled**: Чи активна стратегія для цього активу (true/false).
- **strategy**:
  - `bb_window`: Вікно для розрахунку Bollinger Bands (кількість барів).
  - `bb_num_std`: Кількість стандартних відхилень для побудови BB.
  - `min_bb_width`: Мінімальна ширина BB (захист від низької волатильності).
  - `entry_threshold`: Поріг для входу (відхилення від середньої).
  - `sl_atr_mult`: Множник ATR для SL (динамічний стоп-лосс).
  - `tp_to_mid`: Чи використовувати середню BB як ціль для TP.
  - `cooldown_sec`: Кулдаун між угодами.
- **allowed_regimes**: Список режимів ринку, в яких дозволена торгівля для цього активу.
- **risk**: Розмір позиції у USD.

---

## Принципи роботи та fallback
- Якщо блок для активу відсутній — стратегія не активна для нього.
- SL/TP розраховуються динамічно через ATR та BB.
- allowed_regimes визначає, коли MR-стратегія може відкривати позиції.
- Значення з цього файлу мають пріоритет над глобальними (trading.mean_reversion_1m).

---

## Валідація та тестування
- Pydantic-схеми: `config_models.py` (MeanReversion1mConfig)
- Основний код: `apps/reference/domains/decision_making/mean_reversion_1m.py`, `feature_engineering/`
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Формули та використання в коді
- Bollinger Bands: `BB = SMA ± bb_num_std * stddev`
- SL: `SL = entry_price - sl_atr_mult * ATR`
- TP: залежить від `tp_to_mid` (до середньої або зовнішньої BB)
- Кулдаун: затримка між угодами для уникнення overtrading

---

## Приклад структури (фрагмент)

```yaml
DOGEUSDT:
  enabled: true
  strategy:
    bb_window: 20
    bb_num_std: 2.1
    min_bb_width: 0.005
    entry_threshold: 0.05
    sl_atr_mult: 1.5
    tp_to_mid: false
    cooldown_sec: 210
  allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
  risk: {position_size_usd: 150}
```

---
