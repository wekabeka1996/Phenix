# 🎯 ROOT CAUSE + FIX: Позиції не синхронізуються

## 📌 ПРОБЛЕМА ЗНАЙДЕНА

**Файл**: `apps/reference/domains/position_tracking/position_tracking.py`
**Метод**: `_calc_margin_used_usd()` (лінія 637)

### Механізм дивергенції:

```python
def _calc_margin_used_usd(self, positions: list[dict]) -> decimal.Decimal:
    if positions:
        # Використовує API дані (positionRisk)
        for p in positions:
            ...
    else:
        # ⚠️ FALLBACK: Використовує внутрішній self._positions словник!
        for symbol, position in self._positions.items():
            ...
```

**Що трапляється:**

1. ✅ API запрос `GET /fapi/v2/positionRisk` повертає 200 OK з `[]` (пустої)
2. ✅ Ордери розміщуються на біржі (orderId 6830902878, 1272400694)
3. ✅ Система додає їх до `self._positions` внутрішнього словника
4. ❌ `get_open_positions()` повертає пусто
5. ❌ `portfolio.positions = 0` (з API)
6. ✅ Но `margin_used = 578.77` (з внутрішнього `self._positions` fallback!)

**Результат**: Дивергенція - система бачить margin але не бачить позицій!

---

## 🔍 ПРИЧИНА ЧОМУ API ПОВЕРТАЄ []

Є два сценарії:

### Сценарій A: TestNet API ключ обмежений
- API ключ не має дозволу на `read_open_positions`
- Але має дозвіл на `place_order` (тому ордери розміщуються)
- Результат: `GET /fapi/v2/positionRisk` → 200 OK [] (або помилка 403)

### Сценарій B: TestNet специфіка
- На Binance TestNet ордери можуть НЕ заповнюватися автоматично
- Результат: `positionRisk` пусто тому що позицій нема (статус NEW сніжу)

### Сценарій C: Мікс live/testnet endpoints
- Система відправляє ордери на live Binance
- Але запитує позиції з TestNet
- Результат: ордери на одному акаунті, запит з другого

---

## ⚡ РІШЕННЯ (Quick Fix)

### Опція 1: Допоміжні логи (діагностика)

**Файл**: `apps/reference/domains/position_tracking/position_tracking.py`

```python
def _calc_margin_used_usd(self, positions: list[dict]) -> decimal.Decimal:
    """..."""
    total_margin = decimal.Decimal("0")

    if positions:
        # API дані доступні ✓
        self.logger.info(f"💚 Using API positions: {len(positions)} positions")
        ...
    else:
        # Fallback активний ⚠️
        self.logger.warning(
            f"⚠️ API positions empty! Falling back to internal _positions: "
            f"{list(self._positions.keys())}"
        )
        ...
```

### Опція 2: Явна дивергенція детектор

**Файл**: `apps/reference/domains/position_tracking/position_tracking.py`

Додати у `_calc_margin_used_usd()`:

```python
# Дивергенція детектор
api_pos_count = len(positions) if positions else 0
internal_pos_count = len(self._positions)

if api_pos_count == 0 and internal_pos_count > 0:
    self.logger.critical(
        f"🚨 DIVERGENCE DETECTED: "
        f"API positions={api_pos_count}, internal positions={internal_pos_count}"
    )
    # Повідомити про це явно
    self._emit_divergence_event({
        "api_positions": api_pos_count,
        "internal_positions": internal_pos_count,
        "symbols": list(self._positions.keys()),
        "margin_from_internal": float(total_margin)
    })
```

### Опція 3: Синхронізувати з внутрішніх дах

Якщо API знеможен, використовувати `self._positions` для відповіді:

```python
def _sync_positions_fallback(self):
    """Якщо API не доступна, синхронізувати з внутрішніх даних"""
    fallback_positions = []
    for symbol, pos in self._positions.items():
        fallback_positions.append({
            "symbol": symbol,
            "positionAmt": str(pos.get("quantity", 0)),
            "markPrice": str(pos.get("mark_price", pos.get("avg_price", 0))),
            "leverage": pos.get("leverage", 20),
            "unrealizedProfit": str(pos.get("unrealized_pnl", 0))
        })
    return fallback_positions
```

---

## 🔧 ТЕСТУВАННЯ РІШЕННЯ

Додайте у логи лаж перед тим как видати даних:

```bash
# Перевірити лог:
# 1. Якщо бачите "API positions=0, internal positions=2" → Дивергенція
# 2. Якщо бачите "Using API positions" → OK
# 3. Якщо бачите "Falling back to internal" → TestNet обмеженість
```

---

## 📋 TODO

- [ ] Додати debug логи в `_calc_margin_used_usd()`
- [ ] Додати дивергенція детектор
- [ ] Тестувати з обмеженим TestNet ключем
- [ ] Перевірити чи ордери на TestNet  заповнюються (статус NEW vs FILLED)
- [ ] Якщо TestNet обмежений - переключитися на live або mock

---

## 🚀 ДЛЯ ВИРІШЕННЯ ПРЯМО ЗАРАЗ

1. **Додайте логи** в `binance_adapter.py` у метод `get_open_positions()`:
   ```python
   async def get_open_positions(self, symbol=None):
       raw = await self._request("GET", "/fapi/v2/positionRisk", params)
       self.logger.info(f"🔍 positionRisk API raw response: {raw}")  # DEBUG
       ...
   ```

2. **Переконайтеся** що API ключ має дозвіл на читання позицій (TestNet console)

3. **Перевірте TestNet ордери** - чи вони заповнюються автоматично або залишаються NEW?

---

**Статус**: 🚨 **ROOT CAUSE FOUND**
**Причина**: API повертає пусто → system falls back → дивергенція
**Рішення**: Debug логи + дивергенція детектор + можливо переключення на live
