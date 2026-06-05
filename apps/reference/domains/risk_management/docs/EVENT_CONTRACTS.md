# Контракти подій домену Risk Management

## Вихідні події (Outbound)

### 1. EVT:RISK_ASSESSMENT_COMPLETED
Результат аналізу ризику для конкретного символу.

**Payload Схема:**
- `symbol` (str): Тикер.
- `ts` (int): Таймстамп розрахунку.
- `risk_parameters`:
  - `is_trading_allowed` (bool): Головний дозвіл.
  - `risk_score` (float): Розрахований бал ризику [0..1].
  - `reason` (str): (Опційно) Причина блокування.

---

## Вхідні події (Consumed)

### 1. EVT:FEATURES_CALCULATED
- Використовує: `obi`, `tfi`, `delta_price`, `absorption`.
- Дія: Оновлення `risk_score`.

### 2. EVT:PORTFOLIO_STATE_UPDATED
- Використовує: `equity_cross_usdt`, `equity_free_usdt`.
- Дія: Перевірка денної просадки.
