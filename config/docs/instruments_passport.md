# 📄 Паспорт конфігурації: aurora/instruments.yaml (Section: instrument precision, execution, sizing)

## 🔍 Загальний опис блоку
Файл `instruments.yaml` є **SSOT (Single Source of Truth)** для **per-symbol параметрів прецизійності та виконання**. Він визначає:
1. **Прецизійність контактів** (step_size, tick_size, min_qty, min_notional) — обмеження від біржі
2. **Режим виконання** (margin_mode, target_leverage, leverage_policy) — як керувати плечем
3. **Сайзинг** (margin_pct) — скільки маржі виділяти для позиції

Це **MANDATORY конфіг** для LIVE-режиму; відсутність → crash при запуску (fail-closed).

---

## 🛠 Деталізація полів

| Поле | Тип | Pydantic | Статус | Роль у проекті |
|---|---|---|---|---|
| `symbol` | `str` | ✅ | 🟢 Active | Назва символу (e.g., BTCUSDT) |
| `step_size` | `str` (Decimal) | ✅ | 🟢 Active | Мінімальна кількість лоту (LOT_SIZE stepSize) |
| `tick_size` | `str` (Decimal) | ✅ | 🟢 Active | Мінімальна зміна ціни (PRICE_FILTER tickSize) |
| `min_qty` | `str` (Decimal) | ✅ | 🟢 Active | Мінімальна кількість (LOT_SIZE minQty) |
| `min_notional` | `str` (Decimal) | ✅ | 🟢 Active | Мінімальна вартість позиції (MIN_NOTIONAL) |
| `execution.margin_mode` | `Literal` | ✅ | 🟢 Active | isolated або cross |
| `execution.target_leverage` | `int` | ✅ | 🟢 Active | Цільовий lever (1-125) |
| `execution.leverage_policy` | `Literal` | ✅ | 🟢 Active | verify_only або set_and_verify |
| `execution.max_notional_utilization` | `float` | ✅ | 🟢 Active | Max нотіональна утилізація (0-1) |
| `sizing.margin_pct` | `float` | ✅ | 🟢 Active | % маржи від equity для виділення |

---

### 1. `symbol` (Назва символу)
* **Суть:** Унікальний ідентифікатор торгової пари (BTCUSDT, ETHUSDT, тощо).
* **Домен:** System Core (Instrument Identification).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/config_models.py](apps/reference/config_models.py#L28) — `symbol: str = Field(description="Symbol name (e.g., BTCUSDT)")`
    * Використовується як ключ у словнику `instruments: Dict[str, InstrumentPrecisionSpec]` (line 2889)
* **Валідація:** `str` (no constraints)
* **Тести:** ✅ [test_config_symbols_one_truth.py](tests/config/test_config_symbols_one_truth.py) — перевірка унікальності символів

---

### 2. `step_size` (Розмір лоту)
* **Суть:** **КРИТИЧНИЙ** параметр. Визначає мінімальний крок кількості від біржі (LOT_SIZE constraint від Binance). Кількість завжди має бути кратна `step_size`.
  * При `step_size="1"` (DOGE, SOL) — кількість має бути цілим числом
  * При `step_size="0.001"` (BTC, ETH) — мінімальна точність 0.001
* **Домен:** `Decision Making` (Sizing), `Execution Position` (Quantity Normalization).
* **Режими роботи:** Усі режими. CRITICAL для LIVE execution.
* **Code Trace (Де використовується):**
    * [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L20-25) — функція `floor_to_step()`:
      ```python
      def floor_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
          if step_size <= 0:
              raise ValueError("step_size must be > 0")
          if qty <= 0:
              return Decimal("0")
          return (qty / step_size).to_integral_value(rounding=decimal.ROUND_DOWN) * step_size
      ```
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2629) — завантаження у розрахунку кількості
    * [apps/reference/domains/execution_position/qty_normalizer.py](apps/reference/domains/execution_position/) — нормалізація кількості перед виставленням ордера
* **Математичний вплив:**
  * `rounded_qty = floor(raw_qty / step_size) * step_size`
  * Приклад: при `step_size="1"` і `raw_qty=1.5` → `rounded_qty=1.0`
  * Приклад: при `step_size="0.001"` і `raw_qty=0.0015` → `rounded_qty=0.001`
* **Валідація:**
    * Модель: `InstrumentPrecisionSpec.step_size: str` (зберігається як рядок, конвертується у Decimal при читанні)
    * Обмеження: `step_size > 0` (fail-closed якщо `<= 0`)
* **Тести:** 
    * ✅ [test_task50_qty_normalizer.py](tests/domains/execution_position/test_task50_qty_normalizer.py) — перевірка floor_to_step логіки
    * ✅ [test_sizing_margin_first.py](tests/domains/decision_making/test_sizing_margin_first.py) — unit тести для compute_qty

---

### 3. `tick_size` (Мінімальна зміна ціни)
* **Суть:** Мінімальний крок ціни від біржі (PRICE_FILTER constraint). Ціна повинна бути кратна `tick_size`.
  * При `tick_size="0.1"` (BTC) — мінімальний крок $0.10
  * При `tick_size="0.01"` (ETH, SOL) — мінімальний крок $0.01
  * При `tick_size="0.0001"` (XRP) — мінімальний крок $0.0001
* **Домен:** `Exchange Filters` (Price Validation), `Entry Plan` (Limit price rounding).
* **Режими роботи:** Live, Hybrid, Backtest.
* **Code Trace:**
    * [apps/reference/domains/exchange_filters/contracts.py](apps/reference/domains/exchange_filters/) — перевірка ціни відповідності `tick_size`
    * [apps/reference/domains/decision_making/entry_plan.py](apps/reference/domains/decision_making/) — використання при округленні ліміт-ціни
* **Математичний вплив:**
  * `price_rounded = floor(price / tick_size) * tick_size`
* **Валідація:**
    * Модель: `InstrumentPrecisionSpec.tick_size: str`
    * Обмеження: `tick_size > 0` (fail-closed)
* **Тести:** ✅ Побіжно у фільтрах біржі (test_exchange_filters_validation.py)

**Рекомендація:** Ніколи не змінюйте `tick_size` або `step_size` без оновлення на біржі. Вони — прямі обмеження від Binance.

---

### 4. `min_qty` (Мінімальна кількість)
* **Суть:** **FAIL-CLOSED гейт**. Мінімальна кількість лоту, дозволена біржею (LOT_SIZE minQty). Якщо розрахована кількість < `min_qty`, ордер **відкидається** (не очищується мінімум).
  * При `min_qty="1"` (DOGE, SOL) → не можна трейдити < 1 лота
  * При `min_qty="0.001"` (BTC, ETH) → не можна трейдити < 0.001 BTC
* **Домен:** `Decision Making` (Sizing Validation).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L75-85) — функція `validate_exchange_constraints()`:
      ```python
      def validate_exchange_constraints(
          *,
          qty: Decimal,
          price: Decimal,
          min_qty: Decimal,
          min_notional: Decimal,
      ) -> tuple[Optional[str], str]:
          if min_qty > 0 and qty < min_qty:
              return "MIN_QTY", f"qty {qty} < min_qty {min_qty}"
          ...
      ```
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2630) — завантаження при розрахунку
* **Математичний вплив:**
  * Fail-closed валідація: `if qty < min_qty: REJECT intent`
* **Валідація:**
    * Модель: `InstrumentPrecisionSpec.min_qty: str`
    * Обмеження: `min_qty >= 0`
* **Тести:** 
    * ✅ [test_sizing_margin_first.py](tests/domains/decision_making/test_sizing_margin_first.py) — test validate_exchange_constraints
    * ✅ [test_sizing_matrix.py](tests/domains/test_sizing_matrix.py) — матриця розмірів із min_qty перевіркою

---

### 5. `min_notional` (Мінімальна вартість)
* **Суть:** **FAIL-CLOSED гейт**. Мінімальна вартість (notional = qty * price) позиції від біржі (MIN_NOTIONAL constraint). Якщо `qty * price < min_notional`, ордер **відкидається**.
  * При `min_notional="100"` (BTC) → не можна відкривати позиції < $100
  * При `min_notional="20"` (ETH) → не можна < $20
  * При `min_notional="5"` (DOGE, SOL, XRP) → не можна < $5
* **Домен:** `Decision Making` (Sizing Validation).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L84-85) — валідація:
      ```python
      notional = qty * price
      if min_notional > 0 and notional < min_notional:
          return "MIN_NOTIONAL", f"notional {notional} < min_notional {min_notional}"
      ```
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2631) — завантаження
* **Математичний вплив:**
  * Fail-closed валідація: `if (qty * price) < min_notional: REJECT intent`
* **Валідація:**
    * Модель: `InstrumentPrecisionSpec.min_notional: str`
    * Обмеження: `min_notional >= 0`
* **Тести:** ✅ [test_precision_min_notional.py](tests/domains/execution_position/test_precision_min_notional.py) — dedicated тест

**CRITICAL:** У BACKTEST із малою équité min_notional може блокувати маленькі тради. Збільшите `equity` або зменште позиції.

---

### 6. `execution.margin_mode` (Режим маржі)
* **Суть:** Визначає як взимається маржа для цієї позиції.
  * `"isolated"` — маржа виділяється за позицією (одна позиція не впливає на іншу)
  * `"cross"` — маржа ділиться на весь портфель (ризиково)
* **Домен:** `Execution Position` (Leverage Management).
* **Режими роботи:** Live, Testnet (важливо перевірити перед LIVE трейдингом).
* **Code Trace:**
    * [apps/reference/domains/execution_position/leverage_bootstrapper.py](apps/reference/domains/execution_position/) — читання margin_mode при ініціалізації плеча
    * [apps/reference/adapters/binance_adapter.py](apps/reference/adapters/) — встановлення margin_mode на біржі
* **Валідація:**
    * Модель: `InstrumentExecutionConfig.margin_mode: Literal["isolated", "cross"]`
    * Обмеження: тільки дві дозволені значення
* **Тести:** ✅ [test_leverage_wiring.py](tests/domains/execution_position/test_leverage_wiring.py) — перевірка встановлення режиму

**Рекомендація:** Залиште `"isolated"` для ВСІХ символів у BACKTEST/TESTNET. Це безпечніше.

---

### 7. `execution.target_leverage` (Цільовий lever)
* **Суть:** Цільовий lever для цієї позиції на біржі. Система намагатиметься встановити цей lever при відкритті позиції.
  * `target_leverage=20` (DOGE, SOL, XRP) — 20x lever
  * `target_leverage=41` (ETH) — 41x lever
  * `target_leverage=50` (BTC) — 50x lever (вищий через більші обмеження min_notional)
* **Домен:** `Execution Position` (Leverage Management), `Decision Making` (Notional Calculation).
* **Режими роботи:** Live, Testnet (автоматичне встановлення), Backtest (симуляція).
* **Code Trace:**
    * [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L30-37) — використання у `compute_notional_target()`:
      ```python
      def compute_notional_target(
          *,
          equity: Decimal,
          margin_pct: Decimal,
          leverage: int,  # target_leverage
          ...
      ) -> tuple[Decimal, Decimal]:
          ...
          margin_usdt = safe_equity * margin_pct
          notional_target = margin_usdt * Decimal(leverage)
      ```
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2633) — передача у розрахунок
    * [apps/reference/domains/execution_position/leverage_bootstrapper.py](apps/reference/domains/execution_position/) — встановлення на біржі
* **Математичний вплив:**
  * `notional_target = (equity * margin_pct) * target_leverage`
  * Приклад: `equity=$1000, margin_pct=0.11, target_leverage=20` → `notional_target = 1000 * 0.11 * 20 = $2200`
* **Валідація:**
    * Модель: `InstrumentExecutionConfig.target_leverage: int` (ge=1, le=125)
    * Обмеження: 1-125 (Binance Futures max)
    * **Fail-closed:** Відсутність → `ValidationError`
* **Тести:** 
    * ✅ [test_leverage_wiring.py](tests/domains/execution_position/test_leverage_wiring.py) — перевірка встановлення
    * ✅ [test_sizing_matrix.py](tests/domains/test_sizing_matrix.py) — вплив на вихідну notional

**CRITICAL:** BTC має `target_leverage=50` (не 20) через min_notional=$100. При `margin_pct=0.10, equity=$1000`:
- Якщо `target_leverage=20` → `notional_target = 1000*0.10*20 = $2000` ✅ > min_notional=$100
- Якщо `target_leverage=50` → `notional_target = 1000*0.10*50 = $5000` ✅✅ більш безпечно

---

### 8. `execution.leverage_policy` (Політика встановлення плеча)
* **Суть:** Як система має керувати левером при розбіжностях.
  * `"verify_only"` — тільки перевірити що lever правильний, не встановлювати
  * `"set_and_verify"` — встановити lever, а потім перевірити (рекомендовано)
* **Домен:** `Execution Position` (Leverage Management).
* **Режими роботи:** Live, Testnet.
* **Code Trace:**
    * [apps/reference/domains/execution_position/leverage_bootstrapper.py](apps/reference/domains/execution_position/) — читання при ініціалізації
* **Валідація:**
    * Модель: `InstrumentExecutionConfig.leverage_policy: Literal["verify_only", "set_and_verify"]`
* **Тести:** ✅ [test_leverage_wiring.py](tests/domains/execution_position/test_leverage_wiring.py)

**Рекомендація:** Залиште `"set_and_verify"` для автоматичного встановлення плеча.

---

### 9. `execution.max_notional_utilization` (Max нотіональна утилізація)
* **Суть:** Maximum fraction (0-1) нотіональної ємності, що дозволяється використовувати для цієї позиції.
  * `max_notional_utilization=0.8` (80%) — можна використовувати 80% доступної ємності
* **Домен:** `Exposure Guard` (Capacity Check).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/) — перевірка при обчисленні ємності
* **Математичний вплив:**
  * `max_allowed_notional = capacity * max_notional_utilization`
* **Валідація:**
    * Модель: `InstrumentExecutionConfig.max_notional_utilization: float` (ge=0.0, le=1.0)
* **Тести:** ✅ [test_exposure_guard_wiring.py](tests/domains/execution_position/test_exposure_guard_wiring.py)

---

### 10. `sizing.margin_pct` (Margin Percentage)
* **Суть:** **КРИТИЧНИЙ ПАРАМЕТР**. Визначає скільки % від equity виділяється як маржа для цієї позиції (margin-first sizing SSOT).
  * `margin_pct=0.11` (BTC, DOGE, SOL, XRP, ETH) — 11% від equity як маржа
  * `margin_pct=0.10` (BTC) — 10% від equity як маржа (більш консервативно)
* **Домен:** `Decision Making` (Sizing Engine), `Sizing Gateway`.
* **Режими роботи:** Усі режими. **MANDATORY** у LIVE.
* **Code Trace (Де використовується):**
    * [apps/reference/domains/decision_making/sizing_margin_first.py](apps/reference/domains/decision_making/sizing_margin_first.py#L30-47) — `compute_notional_target()`:
      ```python
      margin_usdt = safe_equity * margin_pct
      notional_target = margin_usdt * Decimal(leverage)
      ```
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2607-2615) — завантаження та застосування
    * [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L486) — використання у MR handler
* **Математичний вплив (MARGIN-FIRST MODEL):**
  ```
  notional_target = (equity * margin_pct) * target_leverage
  qty = floor(notional_target / price, step_size)
  ```
  * Приклад: `equity=$1000, margin_pct=0.11, target_leverage=20, price=$50000` (BTC):
    - `margin_usdt = 1000 * 0.11 = $110`
    - `notional_target = 110 * 20 = $2200`
    - `qty = floor($2200 / $50000, 0.001) = 0.044 BTC`
* **Валідація:**
    * Модель: `InstrumentSizingConfig.margin_pct: float` (gt=0.0, le=1.0)
    * Обмеження: `0 < margin_pct <= 1` (fail-closed якщо порушено)
    * **Fail-closed:** Відсутність → `ValidationError` при завантаженні конфіг
* **Тести:** 
    * ✅ [test_sizing_margin_first.py](tests/domains/decision_making/test_sizing_margin_first.py) — unit тести логіки
    * ✅ [test_sizing_margin_first_runtime.py](tests/domains/decision_making/test_sizing_margin_first_runtime.py) — runtime тести
    * ✅ [test_sizing_margin_first_ssot.py](tests/config/test_sizing_margin_first_ssot.py) — конфіг SSOT валідація
    * ✅ [test_sizing_gateway_margin_first.py](tests/integration/test_sizing_gateway_margin_first.py) — integration тест

**CRITICAL:** `margin_pct` — основний лавер для контролю risk. Збільшення = більше 마진 = більший ризик. В BACKTEST зазвичай більше ніж в LIVE.

Приклад:
- `margin_pct=0.11` → 11% від $1000 = $110 маржи
- `margin_pct=0.50` → 50% від $1000 = $500 маржи (більш агресивно)

---

## 📊 Audit Summary (Вердикт)

| Поле | Статус | Примітка |
|---|---|---|
| `symbol` | 🟢 **ACTIVE** | Назва символу. Не читається в коді але використовується як ключ. |
| `step_size` | 🟢 **ACTIVE** | CRITICAL. Floor_to_step нормалізація. Full code-trace. |
| `tick_size` | 🟢 **ACTIVE** | Мінімальна зміна ціни. Перевіряється у фільтрах. |
| `min_qty` | 🟢 **ACTIVE** | FAIL-CLOSED гейт. validate_exchange_constraints. |
| `min_notional` | 🟢 **ACTIVE** | FAIL-CLOSED гейт. validate_exchange_constraints. |
| `execution.margin_mode` | 🟢 **ACTIVE** | Встановлюється на біржі. Full code-trace. |
| `execution.target_leverage` | 🟢 **ACTIVE** | CRITICAL. compute_notional_target. Full code-trace. |
| `execution.leverage_policy` | 🟢 **ACTIVE** | Управління левером. Full code-trace. |
| `execution.max_notional_utilization` | 🟢 **ACTIVE** | Exposure guard capacity. Full code-trace. |
| `sizing.margin_pct` | 🟢 **ACTIVE** | CRITICAL. MARGIN-FIRST SSOT. Full code-trace. |

---

## 🔐 Data Cleanliness & Recommendations

### ✅ Що добре:
1. **Fail-closed валідація:** `min_qty`, `min_notional` — explicit constraints, DROP якщо не виконані.
2. **Margin-first SSOT:** Одне джерело істини для сайзингу. No duplicates.
3. **Pydantic strict:** `extra='forbid'` для обох `InstrumentPrecisionSpec` та `InstrumentExecutionConfig`.
4. **Per-symbol гнучкість:** Кожен символ може мати свої значення (BTC vs DOGE).

### ⚠️ Що перевірити:
1. **Біржева конвергенція:** `step_size`, `tick_size`, `min_qty`, `min_notional` **МАЮТЬ** точно відповідати Binance Futures constraints, інакше ордери відхилятимуться.
2. **Leverage limits:** `target_leverage` > 125 або < 1 → Binance reject. Переконайтесь що значення дійсні.
3. **Min_notional блокування:** Якщо `min_notional=$100` і `equity=$1000`, можливо буде важко трейдити в BACKTEST.

### 🚀 Рекомендація для BACKTEST:
```yaml
BTCUSDT:
  step_size: "0.001"
  tick_size: "0.1"
  min_qty: "0.001"
  min_notional: "5"          # ЗМЕНШИТИ з $100 для backtest (більше гнучкості)
  execution:
    target_leverage: 20      # ЗМЕНШИТИ з $50 для backtest
    margin_pct: 0.25         # ЗБІЛЬШИТИ з 0.10 для backtest (агресивніше)
```

---

## 🧪 Test Coverage

| Тест-файл | Охоплення |
|---|---|
| [test_task50_qty_normalizer.py](tests/domains/execution_position/test_task50_qty_normalizer.py) | ✅ step_size normalization |
| [test_sizing_margin_first.py](tests/domains/decision_making/test_sizing_margin_first.py) | ✅ margin-first logic, min_qty/min_notional |
| [test_precision_min_notional.py](tests/domains/execution_position/test_precision_min_notional.py) | ✅ min_notional validation |
| [test_leverage_wiring.py](tests/domains/execution_position/test_leverage_wiring.py) | ✅ leverage setup |
| [test_sizing_matrix.py](tests/domains/test_sizing_matrix.py) | ✅ Complete sizing matrix |
| [test_sizing_margin_first_ssot.py](tests/config/test_sizing_margin_first_ssot.py) | ✅ Config SSOT validation |
| [test_p1_instrument_overrides_no_fallbacks.py](tests/runtime/test_p1_instrument_overrides_no_fallbacks.py) | ✅ Per-symbol overrides |

---

**Документ завершено:** 2026-01-27  
**SSOT:** `config/aurora/instruments.yaml` + `config_models.py` (`InstrumentPrecisionSpec`, `InstrumentExecutionConfig`, `InstrumentSizingConfig`)
