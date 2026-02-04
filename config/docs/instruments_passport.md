# 📄 Semantic Configuration Passport: `config/aurora/instruments.yaml`

**Нотація:** `instruments.*.<field>` означає «поле `<field>` для будь-якого символа (ключа) в мапі `instruments:`».

---

### `instruments.*.symbol`
- **Type:** `string`
- **Logic Owner:** `config_loader` / `config_symbols` (SSOT symbol registry)
- **Code Reference:** `apps/reference/config_models.py:40` (model: `InstrumentPrecisionSpec`); `apps/reference/config_symbols.py:20` (func: `get_trading_symbols`)
- **Mathematical Role:**
    > Не бере участі у формулах напряму. Використовується як ідентифікатор інструмента; фактична “канонічна” множина символів береться з ключів `config.instruments` (`list(instruments.keys())`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)* (рядок-ідентифікатор).
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має збігатися з ключем мапи (`instruments.<KEY>.symbol == <KEY>`), інакше виникає «дві правди» (ключ використовується як primary у багатьох місцях).

---

### `instruments.*.tick_size`
- **Type:** `string` *(Decimal-encoded)*
- **Logic Owner:** `execution_position` (price quantization / anti-2021), `exchange_filters` (SSOT↔exchange validation)
- **Code Reference:** `apps/reference/config_models.py:41` (model: `InstrumentPrecisionSpec`); `apps/reference/domains/execution_position/utils.py:22` (func: `_round_to_tick`); `apps/reference/domains/exchange_filters/validator.py:202` (func: `_parse_exchange_filters`)
- **Mathematical Role:**
    > **Квантування ціни до сітки тіку:** `q = floor(price / tick_size)` або `ceil(...)` → `price_q = q * tick_size` (Decimal, без float-rounding).  
    > Напрямок округлення залежить від контексту:
    > - StopPrice: BUY → `ceil`, SELL → `floor` (`quantize_stop_price`).
    > - Anti-2021 guard може “підштовхувати” stop_price на правильний бік і потім квантувати (`validate_anti_2021`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Груба сітка цін → TP/SL/stopPrice «стрибають» великими кроками, зростає ризик відхилення ордера або поганої якості виконання (гірший entry/exit).
    - 🔽 **Too Low:** Якщо поставити точність нижчу за біржову (SSOT більш “дозвільна”) → `PRICE_FILTER` reject або fail-fast на старті при валідації фільтрів (критичний mismatch).
- **Invariant/Constraints:** **Must match exchangeInfo exactly** (tickSize). Не можна “вгадувати”; має бути синхронізовано через `ExchangeFiltersValidator` (fail-closed).

---

### `instruments.*.step_size`
- **Type:** `string` *(Decimal-encoded)*
- **Logic Owner:** `execution_position` (qty normalization), `decision_making` (margin-first sizing), `exchange_filters` (SSOT↔exchange validation)
- **Code Reference:** `apps/reference/domains/execution_position/qty_normalizer.py:73` (func: `normalize_qty`); `apps/reference/domains/decision_making/sizing_margin_first.py:20` (func: `floor_to_step`); `apps/reference/domains/exchange_filters/validator.py:185` (func: `_parse_exchange_filters`)
- **Mathematical Role:**
    > **ROUND_DOWN only (no bump-ups):**  
    > `steps = floor(raw_qty / step_size)` → `rounded_qty = steps * step_size` (Decimal, `ROUND_DOWN`).  
    > Це застосовується:
    > - у DM при розрахунку qty (`floor_to_step`)  
    > - у EP перед відправкою ордера (`normalize_qty`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Великий крок лоту → неможливо точно виставляти розмір (over-rounding вниз), більше шансів `rounded_qty` стати 0 або впасти нижче `min_qty`.
    - 🔽 **Too Low:** Якщо `step_size` менший за біржовий → SSOT стає більш “дозвільним” → ризик `LOT_SIZE` reject; `ExchangeFiltersValidator` класифікує як **CRITICAL** (SSOT < exchange) і звалить старт у live/testnet.
- **Invariant/Constraints:** `step_size > 0`. **Must match exchangeInfo `LOT_SIZE.stepSize` exactly.**

---

### `instruments.*.min_qty`
- **Type:** `string` *(Decimal-encoded)*
- **Logic Owner:** `execution_position` (fail-closed qty gate), `decision_making` (exchange constraints), `exchange_filters` (SSOT↔exchange validation)
- **Code Reference:** `apps/reference/domains/execution_position/qty_normalizer.py:73` (Rule 3); `apps/reference/domains/decision_making/sizing_margin_first.py:72` (func: `validate_exchange_constraints`); `apps/reference/domains/exchange_filters/contracts.py:93` (class: `FilterMismatch.severity`)
- **Mathematical Role:**
    > **Hard lower bound:** якщо `rounded_qty < min_qty` → reject (fail-closed).  
    > EP: `NRR-QTY-BELOW-MIN_QTY` (`normalize_qty`).  
    > DM: `validate_exchange_constraints` повертає `MIN_QTY`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Система буде занадто консервативна: багато малих позицій стануть неможливими (часті відмови при малому equity або низькому `margin_pct`).
    - 🔽 **Too Low:** Якщо `min_qty` менший за біржовий → SSOT більш “дозвільний” → біржа відхилятиме ордер; валідатор фільтрів класифікує як **CRITICAL** mismatch і (в нормі) має валити старт.
- **Invariant/Constraints:** `min_qty > 0`. **Must match exchangeInfo `LOT_SIZE.minQty` exactly.**

---

### `instruments.*.min_notional`
- **Type:** `string` *(Decimal-encoded)*
- **Logic Owner:** `execution_position` (fail-closed notional gate), `decision_making` (exchange constraints), `exchange_filters` (SSOT↔exchange validation)
- **Code Reference:** `apps/reference/domains/execution_position/qty_normalizer.py:73` (Rule 4); `apps/reference/domains/decision_making/sizing_margin_first.py:72` (func: `validate_exchange_constraints`); `apps/reference/domains/exchange_filters/validator.py:188` (func: `_parse_exchange_filters`)
- **Mathematical Role:**
    > **Special Focus — поведінка при `qty * price < min_notional`:**  
    > - **EP (перед відправкою ордера):** `notional = rounded_qty * price`; якщо `notional < min_notional` → **reject**, `why=NRR-NOTIONAL-BELOW-MIN` (без “підтягування” qty).  
    > - **DM (на етапі сайзингу):** якщо `qty*price < min_notional` → `reject_code="MIN_NOTIONAL"`; інтенція не генерується/маркується як відхилена.  
    > **Ніяких soft-adjust/bump-up політик у базовому контракті немає.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше відмов на малих рахунках/низькому `margin_pct`; може практично “вимкнути” торгівлю на інструменті, якщо модель часто дає малий notional.
    - 🔽 **Too Low:** Якщо нижче біржового MIN_NOTIONAL → SSOT стає більш “дозвільний” → біржа відхилятиме; валідатор фільтрів класифікує як **CRITICAL** mismatch (SSOT < exchange) і має fail-fast.
- **Invariant/Constraints:** `min_notional >= 0`. **Must match exchangeInfo `MIN_NOTIONAL`/`NOTIONAL` exactly. Cannot be guessed.**

---

### `instruments.*.execution.margin_mode`
- **Type:** `string` *(enum: `isolated` | `cross`)*
- **Logic Owner:** `execution_position` (leverage/margin sync + pre-open gate)
- **Code Reference:** `apps/reference/config_models.py:109` (model: `InstrumentExecutionConfig`); `apps/reference/domains/execution_position/leverage_service.py:182` (func: `set_and_verify`); `apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py:172` (func: `sync_symbol`)
- **Mathematical Role:**
    > Не формула, а **режим маржі** на біржі. Важливий інваріант інтеграції: режим маржі має бути виставлений **до** виставлення плеча (у `LeverageService.set_and_verify` це зафіксовано порядком викликів).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)* (категоріальне поле), але неправильний режим може змінити профіль ризику (cross може “розмазувати” ризик по гаманцю).
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має відповідати фактичному режиму на біржі; інакше `verify_only` політика відхилятиме відкриття (leverage gate).

---

### `instruments.*.execution.target_leverage`
- **Type:** `int`
- **Logic Owner:** `decision_making` (margin-first sizing), `execution_position` (leverage bootstrap/gate), `exposure_guard` (margin-based utilization)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:2530` (func: `_calculate_position_size`); `apps/reference/domains/execution_position/fsm.py:585` (func: `_collect_leverage_configs`); `apps/reference/domains/execution_position/exposure_guard.py:365` (func: `resolve_symbol_leverage`)
- **Mathematical Role:**
    > **Margin-first sizing (SSOT):**  
    > `safe_equity = equity * (1 - fee_buffer)` → `margin_usdt = safe_equity * margin_pct` → `notional_target = margin_usdt * target_leverage`.  
    > Далі `qty = floor_to_step(notional_target / price, step_size)` (ROUND_DOWN).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Різко зростає notional при тому ж `margin_pct` → ризик перевищити leverage bracket / отримати `-2027` (max leverage exceeded), або впертися в портфельні ліміти/експозицію; також підвищує чутливість до помилок при неправильній маржі.
    - 🔽 **Too Low:** Позиції стають дрібніші (частіше нижче `min_notional`), стратегія може “перестати торгувати”; менший ризик, але нижча ефективність капіталу.
- **Invariant/Constraints:** `1 <= target_leverage <= 125` (Pydantic). **Має відповідати leverage bracket / правилам біржі для цього символа**; інакше bootstrap або set може впасти.

---

### `instruments.*.execution.leverage_policy`
- **Type:** `string` *(enum: `verify_only` | `set_and_verify`)*
- **Logic Owner:** `execution_position` (pre-open leverage gate)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_open.py:526` (func: `handle_async`); `apps/reference/domains/execution_position/leverage_service.py:97` (func: `verify`); `apps/reference/domains/execution_position/leverage_service.py:182` (func: `set_and_verify`)
- **Mathematical Role:**
    > Це **політика синхронізації стану біржі**, не числова формула:  
    > - `verify_only`: лише перевірити `actual == expected`, інакше reject.  
    > - `set_and_verify`: спробувати виставити margin_mode + leverage, потім перевірити (з idempotency window).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(set_and_verify всюди)* Більше API-викликів (rate/latency), але вища гарантія консистентності; у випадку помилок біржі частіше буде fail-closed reject перед відкриттям.
    - 🔽 **Too Low:** *(verify_only всюди)* Менше API-викликів, але будь-який дрейф плеча/маржі (ручна зміна, рестарт без bootstrap) призведе до reject і “мовчазної” зупинки торгів по символу.
- **Invariant/Constraints:** Має бути узгоджено з тим, чи реально у проді проводиться leverage bootstrap і чи wired `leverage_service` (без сервісу політика стає фактично неактивною).

---

### `instruments.*.execution.max_notional_utilization`
- **Type:** `float`
- **Logic Owner:** `config_loader` (LIVE contract), *(планований consumer: capacity gate)*
- **Code Reference:** `apps/reference/config_models.py:119` (model: `InstrumentExecutionConfig`); `apps/reference/config_loader.py:715` (func: `_validate_execution_config_for_live`)
- **Mathematical Role:**
    > Наразі у runtime-коді **немає прямого використання** цього поля у формулах/гейтах (окрім fail-closed валідації на старті). Семантика поля за описом моделі: “частка доступної ємності” для L1 capacity gate.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(якщо буде підключено у capacity gate)* дозволить більшу утилізацію notional-ємності → більший ризик концентрації/перевищення.
    - 🔽 **Too Low:** *(якщо буде підключено)* більше блоків через “capacity exceeded”.
- **Invariant/Constraints:** `0.0 <= value <= 1.0`. Якщо ваша архітектурна норма — fail-closed capacity, це поле має бути реально підключене до гейта (інакше воно “мертве”).

---

### `instruments.*.sizing.margin_pct`
- **Type:** `float`
- **Logic Owner:** `decision_making` (margin-first sizing), `config_loader` (LIVE sizing contract)
- **Code Reference:** `apps/reference/domains/decision_making/sizing_margin_first.py:28` (func: `compute_notional_target`); `apps/reference/domains/decision_making/decision_making.py:2530` (func: `_calculate_position_size`); `apps/reference/config_loader.py:764` (func: `_validate_sizing_config_for_live`)
- **Mathematical Role:**
    > **Per-symbol isolated margin budget:**  
    > `safe_equity = equity * (1 - fee_buffer)` (default fee_buffer=0.001)  
    > `margin_usdt = safe_equity * margin_pct`  
    > `notional_target = margin_usdt * leverage`  
    > `qty = floor_to_step(notional_target / price, step_size)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше маржі на символ → більші позиції/ризик, сильніші просадки; при `~1.0` ви майже “all-in” на символ (хоча fee_buffer трохи зменшує safe_equity).
    - 🔽 **Too Low:** Система може систематично не проходити `min_notional` → часті reject-и і фактична “тишина” на символі.
- **Invariant/Constraints:** `0.0 < margin_pct <= 1.0` (Pydantic + live validation). Має узгоджуватися з портфельними exposure-гейтами.

---

### `instruments.*.flip.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making` (flip orchestration; close-on-reversal)
- **Code Reference:** `apps/reference/config_models.py:1106` (model: `FlipOrchestrationConfig`); `apps/reference/domains/decision_making/decision_making.py:1900` (func: `_get_flip_config`); `apps/reference/domains/decision_making/decision_making.py:4014` (func: `_handle_flip_orchestration`)
- **Mathematical Role:**
    > Вмикає/вимикає flip-оркестрацію на символі (за умови, що глобальний killswitch теж увімкнений).  
    > Якщо `false` і є позиція протилежна новому intent — OPEN може бути дозволений без “close-first” сценарію (оркестрація вимкнена).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(true всюди)* Більше “close → defer open” сценаріїв → менше різких flip-входів, але більше latency/складність у швидких реверсах.
    - 🔽 **Too Low:** *(false)* Менше контролю flip-поведінки; можливі агресивні реверси (залежить від біржі/неттингу).
- **Invariant/Constraints:** Якщо глобальний flip killswitch вимкнений, per-symbol `flip.enabled` ігнорується (поведінка визначається глобально).

---

### `instruments.*.flip.hysteresis_mult`
- **Type:** `float`
- **Logic Owner:** `decision_making` (flip hysteresis gate)
- **Code Reference:** `apps/reference/config_models.py:1110` (model: `FlipOrchestrationConfig`); `apps/reference/domains/decision_making/decision_making.py:4078` (func: `_handle_flip_orchestration`)
- **Mathematical Role:**
    > **Optional hysteresis** перед flip-close: потрібен сильніший протилежний сигнал.  
    > Якщо intent = BUY: `required = thr_buy * hysteresis_mult`; блок, якщо `score < required`.  
    > Якщо intent = SELL: `required = thr_sell * hysteresis_mult`; блок, якщо `score > -required`.  
    > Якщо немає `score/thr_buy/thr_sell` у payload — гістерезис не застосовується (не можна безпечно рахувати).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Важче ініціювати flip-close → позиції довше “терплять” розвороти, менше churn, але ризик запізнілого виходу при реальному реверсі.
    - 🔽 **Too Low:** Ближче до `1.0` → майже без гістерезису, частіші flip-дії/закриття при маржинальних протилежних сигналах.
- **Invariant/Constraints:** `hysteresis_mult >= 1.0` (Pydantic). Значення `< 1.0` заборонене як небезпечне (робить flip надто “нервовим”).

---

## Додаткові зауваження (корисні для аудитів)

- **SSOT loading & deprecations:** `config/aurora/instruments.yaml` витягується в `merged_config["instruments"]`; `trading.instruments` заборонений і дає `ConfigContractError` (`apps/reference/config_loader.py:314`).
- **Fail-closed на відсутній symbol:** якщо `instruments.<SYMBOL>` немає — `execution_position` відхиляє ордер (`NRR-INSTRUMENT-CONFIG-MISSING`) (`apps/reference/domains/execution_position/fsm.py:2494`).
- **`attributes.is_stable` / `allow_trading`:** у поточному `config/aurora/instruments.yaml` таких полів немає; runtime consumers теж не знайдено — додавання потребує явного контракту в `InstrumentPrecisionSpec` і гейтів у доменах.

