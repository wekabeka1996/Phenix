# Звіт про дослідження роботи системи з плечем (Leverage)

**Дата дослідження:** 22 жовтня 2025  
**RID:** AURORA_LEVERAGE_RESEARCH_V1  
**Статус:** ⚠️ КРИТИЧНІ ПРОГАЛИНИ ВИЯВЛЕНО

---

## 🎯 Мета дослідження

Визначити, чи система Aurora розуміє та коректно працює з плечем (leverage) при торгівлі на Binance Futures, та як ця логіка реалізована.

---

## 📊 Результати дослідження

### ✅ Що ЗНАЙДЕНО в системі:

#### 1. **Коментарі про плече в конфігурації**
**Файл:** `config/aurora/system.yaml`
```yaml
inventory_limits:
  max_abs_position: 500  # МАКСИМАЛЬНО під x50 plече
  max_daily_notional: 10000000  # $10M денний ліміт для x50
```

**Файл:** `config/aurora/trading.yaml`
```yaml
instruments:
  BTCUSDT:
    max_notional_usd: 10000000  # $10M per position для x50
  ETHUSDT:
    max_notional_usd: 10000000  # $10M per position для x50
```

**Висновок:** Коментарі вказують на плече x50, але це **лише коментарі**, не робочі параметри.

---

#### 2. **Читання leverage з Account API**
**Файл:** `apps/reference/domains/account_balance/account_connector.py` (рядок 248)
```python
'leverage': int(position.get('leverage', 1)),
'marginType': position.get('marginType', 'cross')
```

**Що відбувається:**
- Система **ЧИТАЄ** поточне плече з позицій через Binance API
- Отримує `marginType` (cross/isolated)
- Зберігає ці дані у payload події `EVT:ACCOUNT_UPDATE_RECEIVED`

**Висновок:** Система **знає**, яке плече встановлено на біржі, але **НЕ ВИКОРИСТОВУЄ** цю інформацію.

---

### ❌ Що НЕ ЗНАЙДЕНО:

#### 1. **Встановлення leverage через API**
❌ Немає викликів до `/fapi/v1/leverage` endpoint  
❌ Немає функцій `set_leverage()` або `change_leverage()`  
❌ Немає логіки встановлення leverage при ініціалізації адаптера

**Binance API для встановлення leverage:**
```python
# НЕ РЕАЛІЗОВАНО в системі:
POST /fapi/v1/leverage
{
  "symbol": "BTCUSDT",
  "leverage": 50
}
```

---

#### 2. **Врахування leverage при розрахунку позицій**
**Файл:** `apps/reference/domains/decision_making/decision_making.py`

**Розрахунок qty:**
```python
# Рядок 220-221
cvar_trade_usd = equity * Decimal(risk_budgets['trade_cvar95_max_bps']) / Decimal('10000')
cvar_session_usd = equity * Decimal(risk_budgets['session_cvar95_max_bps']) / Decimal('10000')

# Рядок 266
kelly_based_size = equity * kelly_fraction * kelly_conservative_factor

# Рядок 258
notional_cap = min(kelly_based_cap, cvar_based_cap, liquidity_based_cap, default_notional_cap)

# Рядок 330 (конвертація в qty)
qty_raw = position_size / price
```

**Проблема:** Розрахунок використовує **equity** (доступний капітал), але:
- ❌ Не враховує, що з плечем x50 **маржа** = position_size / 50
- ❌ Не враховує ризик ліквідації при високому плечі
- ❌ Не перевіряє, чи достатньо маржі для відкриття позиції

---

#### 3. **Захист від надмірного leverage**
❌ Немає перевірки максимального leverage  
❌ Немає розрахунку ціни ліквідації  
❌ Немає захисту від margin call

---

#### 4. **Параметр leverage у конфігурації**
❌ Немає явного параметра `leverage: 50` у `trading.yaml`  
❌ Система не знає, яке плече використовувати  
❌ Покладається на те, що плече вже встановлено на біржі вручну

---

## 🔴 КРИТИЧНІ ПРОБЛЕМИ:

### 1. **Система НЕ встановлює плече**
- Плече має бути встановлено **ВРУЧНУ** через Binance UI або API
- Якщо плече не встановлено → працює на дефолтному (зазвичай x20 або x1)
- **РИЗИК:** Невідповідність між очікуваним (x50) та реальним плечем

---

### 2. **Розрахунок qty НЕ враховує leverage**
**Приклад проблеми:**
```
Equity: $1000
CVaR limit: $150 (15% від equity)
BTC price: $100,000

БЕЗ leverage:
- Position size: $150
- Qty: 0.0015 BTC
- Потрібна маржа: $150 (100%)

З leverage x50:
- Position size: $150
- Qty: 0.0015 BTC  
- Потрібна маржа: $3 (2%)  ← Система це НЕ враховує!
```

**Наслідок:** Система обмежує позиції занадто консервативно, не використовуючи переваги leverage.

---

### 3. **Немає захисту від ліквідації**
При leverage x50:
- Ціна ліквідації дуже близька до entry price (~2% руху)
- Система НЕ розраховує ціну ліквідації
- Немає перевірки відстані до ліквідації

---

### 4. **max_notional_usd = $10M не має сенсу**
```yaml
max_notional_usd: 10000000  # $10M per position для x50
```

Якщо equity = $1000:
- З leverage x50 → максимальна позиція = $50,000
- Ліміт $10M недосяжний і не захищає від ризиків

---

## 💡 Рекомендації:

### **Короткострокові (URGENT):**

1. **Додати параметр leverage у конфігурацію:**
```yaml
instruments:
  BTCUSDT:
    leverage: 50  # ← ДОДАТИ
    margin_type: "cross"  # ← ДОДАТИ
```

2. **Реалізувати встановлення leverage при ініціалізації:**
```python
# У BinanceExecutionAdapter.__init__()
def _set_leverage(self, symbol: str, leverage: int):
    """Set leverage for symbol via Binance API."""
    params = {
        "symbol": symbol,
        "leverage": leverage,
        "timestamp": int(time.time() * 1000)
    }
    # Sign and POST to /fapi/v1/leverage
```

3. **Додати логування поточного leverage:**
```python
self.logger.info(f"[BinanceAdapter] Using leverage={leverage}x for {symbol}")
```

---

### **Середньострокові (HIGH PRIORITY):**

4. **Модифікувати розрахунок qty з урахуванням leverage:**
```python
# У decision_making.py
required_margin = position_size / leverage
if required_margin > available_margin:
    # Reduce position size
    position_size = available_margin * leverage * safety_factor
```

5. **Додати розрахунок ціни ліквідації:**
```python
liquidation_price = entry_price * (1 - (1 / leverage) * margin_ratio)
min_distance_to_liquidation_pct = 5.0  # 5% safety buffer

if abs(current_price - liquidation_price) / current_price < min_distance_to_liquidation_pct / 100:
    self.logger.error("Position too close to liquidation!")
    return None  # Reject trade
```

6. **Додати захист від надмірного leverage:**
```yaml
risk:
  max_leverage: 50
  min_liquidation_distance_pct: 5.0  # Minimum 5% from liquidation
  margin_buffer_pct: 10.0  # Keep 10% margin buffer
```

---

### **Довгострокові (MEDIUM PRIORITY):**

7. **Реалізувати margin tracker:**
- Моніторинг використаної маржі
- Алерти при наближенні до margin call
- Автоматичне зменшення позицій при критичній маржі

8. **Додати режим isolated margin:**
- Для захисту від cascade liquidation
- Окремий margin pool для кожної позиції

9. **Stress testing з leverage:**
- Симуляція екстремальних рухів ціни
- Розрахунок max drawdown з урахуванням leverage
- Тестування на історичних flash crash'ах

---

## 🎓 Висновок:

### **Поточний стан:**
Система **НЕ керує leverage**, а лише **читає** його з біржі. Розрахунок позицій **НЕ враховує** leverage, що призводить до:
- Надмірно консервативних позицій (не використовується потенціал leverage)
- Відсутності захисту від ліквідації
- Неправильної оцінки ризику

### **Критичність:**
🔴 **ВИСОКИЙ РИЗИК** для продакшну з реальними коштами.  
🟡 **СЕРЕДНІЙ РИЗИК** для testnet (але треба виправити перед переходом на mainnet).

### **Наступні кроки:**
1. Додати явний параметр `leverage` у конфігурацію ✅
2. Реалізувати API виклик для встановлення leverage ✅
3. Модифікувати qty calculation з урахуванням margin ✅
4. Додати розрахунок ціни ліквідації ✅

---

**Автор дослідження:** GitHub Copilot  
**Переглянуто:** [Ім'я розробника]  
**Статус:** Draft v1.0  
