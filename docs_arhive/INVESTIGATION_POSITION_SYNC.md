# 🔍 РОЗСЛІДУВАННЯ: Позиції не синхронізуються на системі

**Дата**: 2025-11-07 06:18
**Статус**: 🚨 КРИТИЧНЕ РОЗСЛІДУВАННЯ
**Проблема**: На біржі Binance TestNet факт 2 активні позиції (ETHUSDT + SOLUSDT), але система їх не бачить (portfolio.positions = 0)

---

## 📋 ФАКТИЧНІ ДАНІ ІЗ ЛОГІВ

### На біржі (Binance TestNet):
```
✅ ETHUSDT LONG позиція:
   orderId: 6830902878
   qty: 0.084
   status: NEW → FILLED (очікується заповнення)
   SL: orderId 6830903334
   TP: orderId 6830903485

✅ SOLUSDT LONG позиція:
   orderId: 1272400694
   qty: 1
   status: NEW → PARTIALLY_FILLED/FILLED (очікується заповнення)
   SL: orderId 1272400907
   TP: orderId 1272400921
```

### У системі (Aurora Core):
```
❌ [06:15:45] Found 0 open orders on Binance (правильно - на той момент ще немає)
❌ [06:15:45] Found 0 positions on Binance (ПРОБЛЕМА - навіть після розміщення ордерів!)
❌ [06:15:47] get_open_positions returned: 0 positions
❌ [06:15:47] Fetched positions: 0 non-zero out of 0 total
```

---

## 🔴 ROOT CAUSE ANALYSIS

### Проблема #1: API Call не бачить позицій

**Log Line 06:15:45,841**:
```
httpx - INFO - HTTP Request: GET https://testnet.binancefuture.com/fapi/v2/positionRisk?...
→ HTTP/1.1 200 OK
apps.reference.domains.execution_position.fsm - INFO - Found 0 positions on Binance
```

**Висновок**: API call `GET /fapi/v2/positionRisk` повертає **успішну 200 відповідь з пустим масивом []**

Це означає одне з:
- ✅ Ордери ще не заповнились на момент цього запиту (можливо, ОК)
- ❌ Ключі доступу API не мають прав на FUTURES (чим пояснити, що ордери розміщуються?)
- ❌ Адреса testimerт трейді інколи дозволяє `place_order` але не дозволяє `get_positions`
- ❌ Ордери розміщуються на одному акаунті, але запит позицій йде від іншого

### Проблема #2: Ордери розміщуються, але позиції ні

**Log Line 06:16:04,159** (ETHUSDT):
```
✅ MARKET entry placed: orderId 6830902878, status='NEW'
   origQty: 0.084 ✓
   But NO position update follows!

Log Line 06:16:18,612** (SOLUSDT):
✅ MARKET entry placed: orderId 1272400694, status='NEW'
   origQty: 1 ✓
   But NO position update follows!
```

**Таймаути ордерів** (Log Line 06:17:04 + 06:17:19):
```
⚠️ Order timeout: 6830902878 (ETHUSDT) - fill_timeout (30s timeout)
⚠️ Order timeout: 1272400694 (SOLUSDT) - fill_timeout (30s timeout)

Failed to cancel timed-out order: -2011 "Unknown order sent."
```

**Висновок**:
- Ордери розміщуються ✓
- Але Binance 30+ сек не запол填 їх
- Замість того щоб завершити та перетворити на позицію
- Ордери виходять за таймаут

### Проблема #3: Невирішена дивергенція

**Margin Used Tracking**:
```
Time 06:16:04 → margin_used=14.11 (після ETHUSDT)
Time 06:16:18 → margin_used=578.77 (після SOLUSDT клип)
Time 06:16:33 → margin_used=2554.88 (багато ордерів спостерігається)
```

**Но portfolio.positions остается = 0 весь час!**

---

## 🔧 ДІАГНОСТИКА: Можливі причини

| # | Гіпотеза | Ймовірність | Перевірка |
|---|----------|-----------|----------|
| 1 | **TestNet ключі обмежені** | 🔴 HIGH | getOpenOrders() обробляється, але get_positions() повертає [] |
| 2 | **На TestNet ордери НЕ заповнюються автоматично** | 🟡 MEDIUM | Ордери статус='NEW', таймауту через 30с |
| 3 | **Мікс live + testnet endpoints** | 🟡 MEDIUM | Система використовує https://testnet.binancefuture.com для позиції але можливо гарячо переключається |
| 4 | **Positionmode = HEDGING на TestNet** | 🟢 LOW | Система роботи BOTH |
| 5 | **API key permissions на TestNet** | 🔴 HIGH | API не має `enable_reading_position` дозволу |

---

## 🚀 ПЛАН РОЗСЛІДУВАННЯ

### Крок 1: Перевірити конфіг

```bash
# Перевірити які endpoints використовуються
grep -r "testnet.binancefuture.com\|fapi.binance.com" config/ apps/
grep -r "positionRisk\|openOrders" apps/reference/domains/
```

### Крок 2: Тести API (ручні)

```bash
# На TestNet перевірити:
curl -X GET "https://testnet.binancefuture.com/fapi/v2/positionRisk" \
  -H "X-MBX-APIKEY: YOUR_KEY" \
  -d "timestamp=..."

# Результат має бути:
# [] або [{"symbol":"ETHUSDT","positionAmt":...}]
```

### Крок 3: Трасування в коді

**Файл**: `apps/reference/domains/account_balance/account_connector.py`

Шукаємо:
- Где `get_open_positions()` називається
- Какие параметры передаются в API запрос
- Проверка: используется ли тот же client, что и для openOrders

### Крок 4: Синхронізація таймингу

**Файл**: `apps/reference/domains/account_observer/account_observer.py`

- Polling interval для позицій
- Чи робиться 1 запит сразу після `place_order` або з затримкою?

---

##  🔴 КРИТИЧНІ ПЕРЕВАЖНІСТЬ:

Система створює резервацію для margin `margin_used=2837.55` (!!!) але позиції залишаються = 0.

Це призводить до:
1. **EXPOSURE блокування**: "would exceed 565.84 USD margin limit" → нові ордери отримують REJECT
2. **Margin не відноситься**: На TestNet ордери не заповнюються, тому margin не звільняється
3. **Deadlock**: Нові ордери відхиляються, тому що система думає, що маржин вихідні ордери вже знялиполу

---

## 🎯 ШВИДКА ПЕРЕВІРКА

**Давайте просто перевіримо конфіг testnet:**

Файл: `config/aurora/trading.yaml` або `.env`

Пошук:
- `BINANCE_FUTURES_BASE_URL` → має бути `https://testnet.binancefuture.com`
- `ACCOUNT_MODE` → має бути `testnet` або `hybrid_live_data_testnet_exec`
- API ключі → чи вони для TestNet?

---

## ⚡ ТИМЧАСОВЕ РІШЕННЯ

Якщо TestNet ключі обмежені:
1. Виключити модуль `account_observer` (він не витягує позицій)
2. Використовувати manual `account_update` events
3. Або переключитися на live режим (якщо у вас є live ключі)

---

## 📊 НАСТУПНІ КРОКИ

1. ✓ Прочитали лог → знайшли дивергенцію
2. ⏳ **Перевірити конфіг endpoints** (URGENT)
3. ⏳ **Тестувати API ручами** на TestNet
4. ⏳ **Знайти де система обробляє positionRisk API**
5. ⏳ **Фіксити: додати fallback або debug логи**
