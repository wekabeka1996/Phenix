# Binance API Compliance Check

> **Дата:** 2026-01-22  
> **Джерела:** Офіційна документація Binance Futures API (developers.binance.com)  
> **Мета:** Перевірка правильності реалізації leverage/margin_type у BinanceAdapter

---

## Executive Summary

| Аспект | Статус | Висновок |
|--------|--------|----------|
| **Leverage Change at Runtime** | ✅ БЕЗПЕЧНО (з обмеженнями) | Можна змінювати при відкритій позиції |
| **Margin Type Change** | ⛔ ЗАБОРОНЕНО | Не можна змінювати при позиції/ордерах |
| **Error -4046 Handling** | ✅ ПРАВИЛЬНО | Код обробляє idempotent success |
| **Leverage Brackets** | ⚠️ НЕ ВИКОРИСТОВУЄТЬСЯ | Gap: немає перевірки max notional |

---

## 1. Leverage Change Safety

### API Endpoint

```
POST /fapi/v1/leverage
Weight: 1
```

**Parameters:**
- `symbol` (STRING, required)
- `leverage` (INT, required) — 1 to 125

**Response:**
```json
{
  "leverage": 21,
  "maxNotionalValue": "1000000",
  "symbol": "BTCUSDT"
}
```

### Чи можна змінювати leverage при відкритій позиції?

**✅ ТАК, з обмеженнями:**

1. **ISOLATED Margin — ЗМЕНШЕННЯ leverage:**
   - **Заборонено** при відкритій позиції
   - Код помилки: **`-4161 ISOLATED_LEVERAGE_REJECT_WITH_POSITION`**
   - Повідомлення: "Leverage reduction is not supported in Isolated Margin Mode with open positions"

2. **ISOLATED Margin — ЗБІЛЬШЕННЯ leverage:**
   - ✅ Дозволено
   - Liquidation Price **миттєво перераховується**

3. **CROSS Margin:**
   - ✅ Можна змінювати в будь-яку сторону

### Обмеження по Notional (Leverage Brackets)

При спробі встановити leverage, який не підтримує поточний notional позиції:

| Помилка | Опис |
|---------|------|
| **`-2027 MAX_LEVERAGE_RATIO`** | "Exceeded the maximum allowable position at current leverage" |
| **`-2028 MIN_LEVERAGE_RATIO`** | "Leverage is smaller than permitted: insufficient margin balance" |

**Приклад:** Позиція $60k, хочемо 125x → Binance може відхилити, бо bracket для 125x може мати `notionalCap: 50000`.

### Інші помилки leverage:

| Код | Назва | Причина |
|-----|-------|---------|
| `-4028` | INVALID_LEVERAGE | Невалідне значення leverage |
| `-4202` | ADJUST_LEVERAGE_KYC_FAILED | Потрібна верифікація для leverage > 20x |
| `-4203` | ADJUST_LEVERAGE_ONE_MONTH_FAILED | leverage > 20x доступний через місяць після реєстрації |
| `-4206` | ADJUST_LEVERAGE_KYC_LIMIT | Регіональні обмеження на leverage |

### Rate Limits

- Request weight: **1**
- Стандартний ліміт: 1200 weight/minute
- Можна викликати часто (до 1200 разів/хв)

---

## 2. Margin Type Restrictions

### API Endpoint

```
POST /fapi/v1/marginType
Weight: 1
```

**Parameters:**
- `symbol` (STRING, required)
- `marginType` (ENUM, required) — `ISOLATED` or `CROSSED`

### ⛔ ЗАБОРОНА при відкритих позиціях/ордерах

| Помилка | Опис |
|---------|------|
| **`-4046`** | NO_NEED_TO_CHANGE_MARGIN_TYPE — Вже встановлено (idempotent) |
| **`-4047`** | THERE_EXISTS_OPEN_ORDERS — Є відкриті ордери |
| **`-4048`** | THERE_EXISTS_QUANTITY — Є відкрита позиція |

### Висновок

**Margin type можна змінювати ТІЛЬКИ коли:**
1. Немає відкритої позиції (qty = 0)
2. Немає активних ордерів (limit/stop)

**Наша стратегія:** Встановлювати margin type **до першого ордера**, а не "на льоту".

---

## 3. Leverage Brackets (Notional Limits)

### API Endpoint

```
GET /fapi/v1/leverageBracket
Weight: 1
```

**Response:**
```json
{
  "symbol": "ETHUSDT",
  "notionalCoef": 1.50,  // User-specific multiplier (if adjusted)
  "brackets": [
    {
      "bracket": 1,
      "initialLeverage": 75,
      "notionalCap": 10000,
      "notionalFloor": 0,
      "maintMarginRatio": 0.0065,
      "cum": 0.0
    },
    {
      "bracket": 2,
      "initialLeverage": 50,
      "notionalCap": 50000,
      "notionalFloor": 10000,
      "maintMarginRatio": 0.01,
      "cum": 35.0
    }
  ]
}
```

### Логіка

Для кожного рівня leverage існує максимальний notional:

| Leverage | Max Notional (приклад BTCUSDT) |
|----------|-------------------------------|
| 125x | $50,000 |
| 100x | $250,000 |
| 50x | $1,000,000 |
| 20x | $5,000,000 |
| 10x | $20,000,000 |

**Якщо notional позиції > bracket cap:**
- Binance автоматично знижує leverage до допустимого
- Або відхиляє запит з `-2027 MAX_LEVERAGE_RATIO`

---

## 4. Code Review — BinanceAdapter

### 4.1. `set_leverage()` (L1020-1053)

```python
async def set_leverage(self, symbol: str, leverage: int) -> bool:
    path = "/fapi/v1/leverage"
    params = {
        "symbol": symbol,
        "leverage": leverage,
    }
    result = await self._request("POST", path, params)
    actual = result.get("leverage")
    LOG.info(f"LEVERAGE_SET: {symbol} -> {leverage}x (response: {actual})")
    
    if actual is not None and int(actual) != leverage:
        raise BinanceAPIError(...)
    return True
```

**Оцінка: ✅ ПРАВИЛЬНО**

| Аспект | Статус | Коментар |
|--------|--------|----------|
| Endpoint | ✅ | `/fapi/v1/leverage` — правильний |
| Parameters | ✅ | `symbol`, `leverage` — правильні |
| Response check | ✅ | Перевіряє `actual != requested` |
| Logging | ✅ | Інформативний лог |

**Gaps:**
- ⚠️ Не перевіряє `-4161` (ISOLATED + зменшення + відкрита позиція)
- ⚠️ Не перевіряє `-2027` / `-2028` (notional vs bracket)
- ⚠️ Не використовує `maxNotionalValue` з response

### 4.2. `set_margin_mode()` (L1154-1190)

```python
async def set_margin_mode(self, symbol: str, mode: str) -> bool:
    margin_type = "ISOLATED" if mode.lower() == "isolated" else "CROSSED"
    
    path = "/fapi/v1/marginType"
    params = {
        "symbol": symbol,
        "marginType": margin_type,
    }
    
    try:
        result = await self._request("POST", path, params)
        LOG.info(f"MARGIN_MODE_SET: {symbol} -> {mode} ({margin_type})")
        return True
    except BinanceAPIError as e:
        # -4046: No need to change margin type (already correct)
        if e.code == -4046:
            LOG.debug(f"MARGIN_MODE_SET: {symbol} already {mode} (no change needed)")
            return True
        raise
```

**Оцінка: ✅ ПРАВИЛЬНО**

| Аспект | Статус | Коментар |
|--------|--------|----------|
| Endpoint | ✅ | `/fapi/v1/marginType` — правильний |
| Parameters | ✅ | `ISOLATED` / `CROSSED` — правильні enum |
| -4046 handling | ✅ | Idempotent success — правильно |
| Logging | ✅ | Інформативний лог |

**Gaps:**
- ⚠️ Не логує `-4047` (open orders exist)
- ⚠️ Не логує `-4048` (position exists)

---

## 5. Gap Analysis

### 5.1. Critical Gaps

| Gap | Impact | Рекомендація |
|-----|--------|--------------|
| **Leverage Brackets не перевіряються** | Можливий reject при set_leverage | Додати `GET /fapi/v1/leverageBracket` перед зміною |
| **-4161 не обробляється** | Unexpected error при ISOLATED + зменшення leverage | Явна обробка помилки |

### 5.2. Recommended Error Handling

```python
# В set_leverage():
except BinanceAPIError as e:
    if e.code == -4161:
        # ISOLATED leverage reduction with open position
        LOG.warning(f"Cannot reduce leverage in ISOLATED mode with open position: {symbol}")
        raise
    if e.code == -2027:
        # Position notional exceeds bracket for requested leverage
        LOG.warning(f"Notional exceeds bracket for {leverage}x on {symbol}")
        raise
    raise
```

### 5.3. Recommended Pre-Flight Check

```python
async def can_set_leverage(self, symbol: str, target_leverage: int) -> tuple[bool, str]:
    """Check if leverage can be set (bracket validation)."""
    brackets = await self.get_leverage_brackets(symbol)
    current_position = await self.get_position(symbol)
    position_notional = abs(current_position.qty * current_position.mark_price)
    
    for bracket in brackets["brackets"]:
        if bracket["initialLeverage"] >= target_leverage:
            if position_notional <= bracket["notionalCap"]:
                return True, "OK"
            else:
                return False, f"Notional {position_notional} exceeds cap {bracket['notionalCap']} for {target_leverage}x"
    
    return False, f"Leverage {target_leverage}x not available for {symbol}"
```

---

## 6. Operational Recommendations

### 6.1. Startup Flow (Recommended)

```
[Startup]
    │
    ▼
[Check margin_mode per symbol]
    │
    ├── Already correct? → Skip
    │
    └── Needs change?
            │
            ├── Has position? → ⛔ FAIL (cannot change)
            │
            └── No position → set_margin_mode()
```

### 6.2. Runtime Leverage Change Flow

```
[Need to change leverage]
    │
    ▼
[Get current position notional]
    │
    ▼
[Get leverage brackets]
    │
    ▼
[Is target_leverage compatible with notional?]
    │
    ├── No → ⛔ REJECT (don't even try API call)
    │
    └── Yes
          │
          ▼
    [Is margin_mode ISOLATED and reducing leverage?]
          │
          ├── Yes + Has position → ⛔ REJECT
          │
          └── No → set_leverage()
```

---

## 7. Summary Table

| Question | Answer |
|----------|--------|
| Чи можна змінювати leverage при відкритій позиції? | ✅ Так, крім ISOLATED + зменшення |
| Чи миттєво перераховується Liquidation Price? | ✅ Так |
| Чи можна змінювати margin_type при позиції? | ⛔ НІ (-4048) |
| Чи можна змінювати margin_type при відкритих ордерах? | ⛔ НІ (-4047) |
| Чи правильно обробляється -4046? | ✅ Так (idempotent success) |
| Чи перевіряються leverage brackets? | ⚠️ НІ (gap) |

---

## 8. Action Items

| Priority | Task | Effort |
|----------|------|--------|
| **P1** | Додати обробку `-4161` в `set_leverage()` | Low |
| **P1** | Додати обробку `-4047`, `-4048` в `set_margin_mode()` | Low |
| **P2** | Реалізувати `get_leverage_brackets()` | Medium |
| **P2** | Додати pre-flight bracket validation | Medium |
| **P3** | Кешувати brackets (вони рідко змінюються) | Low |

---

## References

- [Change Initial Leverage](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage)
- [Change Margin Type](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type)
- [Notional and Leverage Brackets](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets)
- [Error Codes](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code)
