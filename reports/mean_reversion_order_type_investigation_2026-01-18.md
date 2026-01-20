# Mean Reversion — розслідування `execution.entry_order_type` / `entry_tif` (станом на 2026‑01‑18)

## 1) Обсяг дослідження
Мета: зрозуміти, який тип ордера формує стратегія mean_reversion, як ці поля проходять пайплайн, де їх валідують, і чи є ризики (мертвий код/тихі фолбеки/дублювання).

## 2) Джерело правди для типу ордера
- Поля `execution.entry_order_type` та `execution.entry_tif` задані у конфігу стратегії mean_reversion: [config/aurora/strategies/mean_reversion.yaml](config/aurora/strategies/mean_reversion.yaml#L29-L37).
- Значення за замовчуванням для mean_reversion: `entry_order_type: "MARKET"`, `entry_tif: null`.

## 3) Ланцюг формування ордера (end‑to‑end)
### 3.1 MeanReversionHandler → сигнал
- Стратегія генерує `EVT:STRATEGY_SIGNAL_PRODUCED` (звичайний шлях). Це не містить `order_type` прямо, лише signal‑payload: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L556-L632).

### 3.2 DecisionMaking → Trade Intent (SSOT по order_type)
- В `_propose_trade_intent` DecisionMaking читає `execution.entry_order_type` та `execution.entry_tif` з `config.strategies.<strategy_id>` (тобто `mean_reversion`) і **fail‑closed** при відсутності: [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2929-L3012).
- Валідації:
  - `order_type` має бути дозволений капабілітісами домену `execution_position`.
  - Якщо `order_type == LIMIT`, `tif` обов’язковий і має входити в `supported_tif`.
  - Якщо `order_type == MARKET`, `tif` **повинен бути null** (без мовчазних фолбеків).
  - Для `LIMIT` — додатково розраховується `valid_for_ms` (без фолбеків): [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2986-L3060).
- Фінальний `trade_intent.order.order_type` задається `order_type_u` з конфіга (тобто для MR — `MARKET`). [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L3106-L3128).

### 3.3 ExecPosFSM → відкриття позиції
- Вхідний `EVT:TRADE_INTENT_PROPOSED` перевіряє:
  - `order_type` існує (no default),
  - `LIMIT` вимагає `price` і `tif`,
  - `MARKET` забороняє `tif`.
  [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L966-L1013).
- В `_execute_decision` фактично викликається:
  - `adapter.place_limit_entry(...)` якщо `order_type == LIMIT`,
  - інакше `adapter.place_market_entry(...)`.
  [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L2529-L2593).

**Висновок:** для mean_reversion стандартний шлях завжди будує MARKET‑ордера (і без `tif`), бо це закладено в конфіг `mean_reversion.yaml`, а DecisionMaking використовує цей конфіг як SSOT.

## 4) Поточні тести (знайдені)
### 5.1 Контракти конфігу
- Перевірка, що `mean_reversion.yaml` містить `execution.entry_order_type` і `entry_tif`, і що для MR це `MARKET` та `null`: [tests/integration/test_order_policy_01.py](tests/integration/test_order_policy_01.py#L186-L220).
- Повний контракт завантаження YAML у Pydantic‑модель (без «тихих» дефолтів): [tests/config/test_mean_reversion_yaml_contract.py](tests/config/test_mean_reversion_yaml_contract.py#L1-L140).

### 5.2 E2E (потік до розміщення ордера)
- E2E MARKET‑path: перевірка, що `order_type="MARKET"` і `tif` відсутній; і що викликається `place_market_entry`: [tests/e2e/test_e2e_bar_to_order_placement.py](tests/e2e/test_e2e_bar_to_order_placement.py#L300-L393).

### 5.3 Режим direct‑emit (legacy)
- Є тести для direct‑emit, але вони **позначені skipped** (deprecated/forbidden): [tests/domains/decision_making/test_mean_reversion_emit_trade_intent_mode.py](tests/domains/decision_making/test_mean_reversion_emit_trade_intent_mode.py#L1-L140).

## 5) Потенційні ризики/аномалії
- **Тихих фолбеків не виявлено** для `order_type`/`tif`: DecisionMaking і ExecPosFSM працюють fail‑closed і явно відхиляють некоректні значення. [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L2929-L3060), [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L966-L1013).

## 6) Рекомендовані тести (пропозиція, без змін коду)
Якщо потрібне «100% тестування всіх видів», потрібне окреме підтвердження на додавання тестів (бо це зміни коду). Пропоную:
1. **Unit**: перевірити, що DecisionMaking для mean_reversion читає `execution.entry_order_type` і відхиляє відсутність `tif` для LIMIT (на штучному cfg).
2. **Integration**: варіант MR‑config із `entry_order_type="LIMIT"` і перевіркою, що формується `valid_for_ms` і проходить constraints.
3. **Simulation**: симульований потік барів для MR → signal → trade_intent → ExecPosFSM, із валідацією, що `place_market_entry` викликається (аналог уже є у E2E, але можна стабілізувати через lower‑level harness).

Якщо потрібне фактичне додавання цих тестів — підтвердіть, і я підготую зміни окремим кроком.
