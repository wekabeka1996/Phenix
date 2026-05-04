# Контракти домену Regime Allowlist

## Функціональні інтерфейси

### `validate_all`
**Вхід:**
- `assignments`: Мапінг символ -> список стратегій.
- `aurora_assets`: Детальна конфігурація інструментів.

**Дія:** Виконує повний аудит сумісності режимів для всієї системи.

### `is_regime_allowed`
**Вхід:**
- `current_regime`: Поточна фаза ринку.
- `allowed_regimes`: Список дозволених фаз із конфігу.

**Результат:** `True/False`.

## Реєстр режимів (ALL_REGIMES)
Домен визнає такі канонічні типи режимів:
- `TREND_UP`, `TREND_DOWN`
- `HIGH_VOLATILITY`, `LOW_VOLATILITY`
- `MEAN_REVERSION`
- `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`
- `UNCERTAIN`
