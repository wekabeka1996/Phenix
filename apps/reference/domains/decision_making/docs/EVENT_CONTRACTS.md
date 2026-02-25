# Контракти подій домену Decision Making

## Вихідні події (Outbound)

### 1. EVT:TRADE_INTENT_PROPOSED
Найважливіша подія, що ініціює торгівлю.

**Ключові поля пейлоаду:**
- `symbol`: string (напр. BTCUSDT)
- `action`: string (OPEN, CLOSE)
- `side`: string (BUY, SELL)
- `qty`: string (Decimal) — кількість для виконання.
- `price`: string (Decimal) — лімітна ціна (або 0 для MARKET).
- `entry_plan`: dict — містить `stop_loss`, `take_profit`, `entry_price`.
- `strategy_id`: string (напр. aurora)
- `rid`: string — унікальний ID запиту для відстеження.

**Схема (v1):** Валідується через `schemas/trade_intent_v1.json`. Вимагає `tif` (Time In Force) для лімітних ордерів.

---

### 2. EVT:STRATEGY_DECISION_BLOCKED
Емітується, коли сигнал від стратегії було відхилено гейтами.

**Поля:**
- `reason_code`: string (напр. `NRR-RISK-STALE`, `NRR-QOS-COOLDOWN`).
- `context`: string — короткий опис гейта, що заблокував рішення.
- `why_chain`: list — ланцюжок причин від стратегії.

---

### 3. EVT:DECISION_TRACE_EMITTED
Технічний лог для форензики.
**Поля:** Містить усі проміжні значення розрахунку: `score`, `confidence`, `regime`, `pm_norm`, `vol_pct`.

## Вхідні події (Consumed)

### 1. CMD:PROCESS_STRATEGY
- **tf_sec**: Має співпадати з конфігом стратегії.
- **warmup**: Об'єкт, що містить `full_ready`. Якщо `False`, рішення зазвичай блокується.

### 2. EVT:RISK_ASSESSMENT_COMPLETED
- **risk_score**: [0..1]. Якщо вище порогу `risk_threshold`, торгівля блокується.
- **is_trading_allowed**: Глобальний вимикач від домену ризиків.
