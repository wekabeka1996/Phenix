# Звіт про до� лідження роботи � и� теми з плечем (Leverage)

**Дата до� лідження:** 22 жовтня 2025  
**RID:** AURORA_LEVERAGE_RESEARCH_V1  
**Стату� :** ⚠️ КРИТИЧНІ ПРОГАЛИНИ ВИЯВЛЕНО

---

## 🎯 Мета до� лідження

Визначити, чи � и� тема Aurora розуміє та коректно працює з плечем (leverage) при торгівлі на Binance Futures, та як ця логіка реалізована.

---

## 📊 Результати до� лідження

### ✅ Що ЗНАЙДЕНО в � и� темі:

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

**Ви� новок:** Коментарі вказують на плече x50, але це **лише коментарі**, не робочі параметри.

---

#### 2. **Читання leverage з Account API**
**Файл:** `apps/reference/domains/account_balance/account_connector.py` (рядок 248)
```python
'leverage': int(position.get('leverage', 1)),
'marginType': position.get('marginType', 'cross')
```

**Що відбуваєть� я:**
- Си� тема **ЧИТАЄ** поточне плече з позицій через Binance API
- Отримує `marginType` (cross/isolated)
- Зберігає ці дані у payload події `EVT:ACCOUNT_UPDATE_RECEIVED`

**Ви� новок:** Си� тема **знає**, яке плече в� тановлено на біржі, але **НЕ ВИКОРИСТОВУЄ** цю інформацію.

---

### ❌ Що НЕ ЗНАЙДЕНО:

#### 1. **В� тановлення leverage через API**
❌ Немає викликів до `/fapi/v1/leverage` endpoint  
❌ Немає функцій `set_leverage()` або `change_leverage()`  
❌ Немає логіки в� тановлення leverage при ініціалізації адаптера

**Binance API для в� тановлення leverage:**
```python
# НЕ РЕАЛІЗОВАНО в � и� темі:
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

**Проблема:** Розрахунок викори� товує **equity** (до� тупний капітал), але:
- ❌ Не враховує, що з плечем x50 **маржа** = position_size / 50
- ❌ Не враховує ризик ліквідації при ви� окому плечі
- ❌ Не перевіряє, чи до� татньо маржі для відкриття позиції

---

#### 3. **Захи� т від надмірного leverage**
❌ Немає перевірки мак� имального leverage  
❌ Немає розрахунку ціни ліквідації  
❌ Немає захи� ту від margin call

---

#### 4. **Параметр leverage у конфігурації**
❌ Немає явного параметра `leverage: 50` у `trading.yaml`  
❌ Си� тема не знає, яке плече викори� товувати  
❌ Покладаєть� я на те, що плече вже в� тановлено на біржі вручну

---

## 🔴 КРИТИЧНІ ПРОБЛЕМИ:

### 1. **Си� тема НЕ в� тановлює плече**
- Плече має бути в� тановлено **ВРУЧНУ** через Binance UI або API
- Якщо плече не в� тановлено → працює на дефолтному (зазвичай x20 або x1)
- **РИЗИК:** Невідповідні� ть між очікуваним (x50) та реальним плечем

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
- Потрібна маржа: $3 (2%)  ← Си� тема це НЕ враховує!
```

**На� лідок:** Си� тема обмежує позиції занадто кон� ервативно, не викори� товуючи переваги leverage.

---

### 3. **Немає захи� ту від ліквідації**
При leverage x50:
- Ціна ліквідації дуже близька до entry price (~2% руху)
- Си� тема НЕ розраховує ціну ліквідації
- Немає перевірки від� тані до ліквідації

---

### 4. **max_notional_usd = $10M не має � ен� у**
```yaml
max_notional_usd: 10000000  # $10M per position для x50
```

Якщо equity = $1000:
- З leverage x50 → мак� имальна позиція = $50,000
- Ліміт $10M недо� яжний і не захищає від ризиків

---

## 💡 Рекомендації:

### **Коротко� трокові (URGENT):**

1. **Додати параметр leverage у конфігурацію:**
```yaml
instruments:
  BTCUSDT:
    leverage: 50  # ← ДОДАТИ
    margin_type: "cross"  # ← ДОДАТИ
```

2. **Реалізувати в� тановлення leverage при ініціалізації:**
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

### **Середньо� трокові (HIGH PRIORITY):**

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

6. **Додати захи� т від надмірного leverage:**
```yaml
risk:
  max_leverage: 50
  min_liquidation_distance_pct: 5.0  # Minimum 5% from liquidation
  margin_buffer_pct: 10.0  # Keep 10% margin buffer
```

---

### **Довго� трокові (MEDIUM PRIORITY):**

7. **Реалізувати margin tracker:**
- Моніторинг викори� таної маржі
- Алерти при наближенні до margin call
- Автоматичне зменшення позицій при критичній маржі

8. **Додати режим isolated margin:**
- Для захи� ту від cascade liquidation
- Окремий margin pool для кожної позиції

9. **Stress testing з leverage:**
- Симуляція ек� тремальних рухів ціни
- Розрахунок max drawdown з урахуванням leverage
- Те� тування на і� торичних flash crash'ах

---

## 🎓 Ви� новок:

### **Поточний � тан:**
Си� тема **НЕ керує leverage**, а лише **читає** його з біржі. Розрахунок позицій **НЕ враховує** leverage, що призводить до:
- Надмірно кон� ервативних позицій (не викори� товуєть� я потенціал leverage)
- Від� утно� ті захи� ту від ліквідації
- Неправильної оцінки ризику

### **Критичні� ть:**
🔴 **ВИСОКИЙ РИЗИК** для продакшну з реальними коштами.  
🟡 **СЕРЕДНІЙ РИЗИК** для testnet (але треба виправити перед переходом на mainnet).

### **На� тупні кроки:**
1. Додати явний параметр `leverage` у конфігурацію ✅
2. Реалізувати API виклик для в� тановлення leverage ✅
3. Модифікувати qty calculation з урахуванням margin ✅
4. Додати розрахунок ціни ліквідації ✅

---

**Автор до� лідження:** GitHub Copilot  
**Переглянуто:** [Ім'я розробника]  
**Стату� :** Draft v1.0  
