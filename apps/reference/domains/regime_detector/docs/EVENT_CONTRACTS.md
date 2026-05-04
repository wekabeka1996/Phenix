# Контракти подій домену Regime Detector

## Вихідні події (Outbound)

### 1. EVT:REGIME_DETECTED
Центральна подія контексту ринку.

**Payload Схема:**
- `regime` (str): Канонічна назва (`TREND_UP`, `MEAN_REVERSION`, `HIGH_VOLATILITY` тощо).
- `confidence` (str/Decimal): Впевненість [0.5, 0.95].
- `changed` (bool): Флаг фактичної зміни режиму (для фільтрації логів).
- `warmup`: Об'єкт готовності індикаторів.
- `last_update_ts_ms` (int): Монотонний час оновлення (heartbeat).

## Вхідні події (Consumed)

### 1. EVT:FEATURES_CALCULATED
- Вимагає `tf_sec` (timeframe).
- Процесує лише події з `tf_sec == basis_tf_sec` (зазвичай 300с).
- Вимагає `price`, `sma_short`, `sma_long`, `atr`.
