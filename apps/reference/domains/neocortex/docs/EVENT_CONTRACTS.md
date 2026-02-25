# Контракти подій домену Neocortex

## Вхідні контракти (Consumed)
Домен покладається на цілісність WAL-журналу.

### 1. EVT:FEATURES_CALCULATED
Служить основним джерелом стану середовища для World Model.

### 2. EVT:TRADE_INTENT_PROPOSED
Використовується для фіксації "дії", яку прийняла основна система, для подальшої оцінки її успішності (Valuation).

## Вихідні контракти (Emitted)

### 1. EVT:NEOCORTEX_ALERT
Емітується при виявленні критичних розбіжностей або аномалій.
**Схема:**
- `type`: string (напр. CONTRACT_VIOLATION)
- `severity`: string (INFO, WARNING, CRITICAL)
- `details`: dict — деталі аномалії.

### 2. EVT:NEOCORTEX_STATE_UPDATED
Трансляція внутрішнього стану (ембедінгів) для моніторингу.
**Схема:**
- `ts`: int
- `latent_z`: list[float] — вектор стану.
- `surprisal`: float — рівень неочікуваності ринкових рухів.
