# Контракти подій домену Execution Position

## Вхідні події та команди (Consumed)

### 1. CMD:OPEN
Основна команда входу в позицію.

**Payload Схема (v1):**
- `symbol` (str): Назва тикера.
- `side` (BUY/SELL): Напрямок.
- `qty` (str): Кількість (сире значення, нормалізується доменом).
- `order_type` (LIMIT/MARKET): Тип ордера.
- `price` (str): Обов'язково для LIMIT.
- `idempotent_key` (str): Для запобігання дублюванню.
- `strategy_id` (str): Назва стратегії (напр. aurora).

---

### 2. CMD:CLOSE
Команда для закриття відкритої позиції.

**Payload Схема:**
- `symbol` (str): Назва тикера.
- `reason` (str): Причина закриття (для логів).

---

### 3. EVT:ORDER_ACK / EVT:ORDER_FILL
- Події від адаптера біржі про статус ордера. 
- На основі них FSM переходить від стану `OPEN` до `MANAGE` або `CLOSED`.

## Вихідні події (Emitted)

### 1. EVT:ORDER_REJECTED / EVT:ORDER_CANCELED
- Емітуються при невдалому виконанні наміру.
- Містять `nrr_code` (Normalized Reject Reason) для аналітики.

### 2. EVT:EXPOSURE_SUMMARY_UPDATED
- Містить інформацію про поточні резервації маржі та загальну експозицію портфеля.
- Споживач: `risk_management`.

### 3. EVT:DEC_CLOSE_COMPLETED
- Сигнал для `decision_making` про те, що позицію закрита і символ готовий до нових сигналів (фліпів).
