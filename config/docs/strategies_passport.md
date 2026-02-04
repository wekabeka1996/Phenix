# Semantic Configuration Passport: `config/aurora/strategies.yaml` (Phase 6)

Цей паспорт описує **SSOT конфіг стратегії** в Aurora: реєстр призначень/арбітражу та профілі стратегій, які реально читаються runtime як `config.strategies_registry.*` і `config.strategies.*`.

## SSOT & Wiring (коротко)

- **Loader:** `config/aurora/strategies.yaml` завантажується в `AuroraConfig.strategies_registry`; потім loader підтягує профілі з `config/aurora/strategies/<strategy_id>.yaml` для всіх `strategy_id`, які присутні в assignments. (`apps/reference/config_loader.py:352`)

- **Strategy Loader:** plugins allowlist реєструється у `main.py`, а `StrategyRuntime` стартує handlers тільки для strategy_id, присутніх у assignments. (`apps/reference/main.py:1277`, `apps/reference/domains/strategies/registry.py:62`)

- **Activation (hard):** `strategies_registry.assignments` є **hard SSOT** для того, які стратегії можуть працювати на конкретному символі; `DecisionMaking` fail-closed блокує intents поза assignments. (`apps/reference/domains/decision_making/decision_making.py:1624`)

- **Overrides:** QoS cooldown для Aurora має ієрархію `strategies.aurora.assets.<SYM>.cooldown_sec` → fallback `domains.decision_making.qos.symbol_cooldown_sec`. (`apps/reference/domains/decision_making/decision_making.py:1754`)

- **Order Policy:** `DecisionMaking` читає `strategies.<id>.execution.entry_order_type/entry_tif` (ORDER-POLICY-01) і fail-closed відхиляє, якщо не задано/непідтримувано. (`apps/reference/domains/decision_making/decision_making.py:3130`)

- **Safety Gates:** `strategies.<id>.safety_gates.enabled` керує застосуванням directional sanity + price-motion gates. Missing block ⇒ fail-closed reject. (`apps/reference/domains/decision_making/decision_making.py:2665`)

**Дата генерації:** `2026-02-03`  
**Leaf keys:** `strategies_registry=12`, `strategies.aurora=320`, `strategies.mean_reversion=86`, `total=418`

---
## Registry: `strategies_registry` (from `config/aurora/strategies.yaml`)

### `strategies_registry.version`
- **Type:** `string`
- **Logic Owner:** `config_loader`
- **Code Reference:** `apps/reference/config_loader.py:352` (func: `_merge_config_fragments`)
- **Mathematical Role:**
    > Версія схеми реєстру стратегій (SemVer/рядок). На runtime-логіку не впливає напряму; корисно для аудиту/міграцій.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** (N/A)
    - 🔽 **Too Low:** (N/A)
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies_registry.assignments.ETHUSDT`
- **Type:** `list[string]`
- **Logic Owner:** `strategies`
- **Code Reference:** `apps/reference/domains/strategies/registry.py:62` (func: `StrategyRuntime.start`) ; `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > SSOT активації стратегій для символу: `symbol → [strategy_id...]`. Використовується **двома** споживачами: (1) `StrategyRuntime` стартує лише allowlisted plugins для strategy_id, (2) `DecisionMaking` fail-closed блокує intent, якщо `symbol` або `strategy_id` відсутні в assignments.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше strategy_id у списку ⇒ більше джерел сигналів, але потрібен арбітраж і зростає churn/конфлікти.
    - 🔽 **Too Low:** Порожній/коротший список ⇒ менше сигналів; порожній список фактично вимикає торгівлю для символу (fail-closed).
- **Invariant/Constraints:** Список має містити лише allowlisted `strategy_id`, для яких існує plugin та профіль `config/aurora/strategies/<id>.yaml`.


---

### `strategies_registry.assignments.SOLUSDT`
- **Type:** `list[string]`
- **Logic Owner:** `strategies`
- **Code Reference:** `apps/reference/domains/strategies/registry.py:62` (func: `StrategyRuntime.start`) ; `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > SSOT активації стратегій для символу: `symbol → [strategy_id...]`. Використовується **двома** споживачами: (1) `StrategyRuntime` стартує лише allowlisted plugins для strategy_id, (2) `DecisionMaking` fail-closed блокує intent, якщо `symbol` або `strategy_id` відсутні в assignments.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше strategy_id у списку ⇒ більше джерел сигналів, але потрібен арбітраж і зростає churn/конфлікти.
    - 🔽 **Too Low:** Порожній/коротший список ⇒ менше сигналів; порожній список фактично вимикає торгівлю для символу (fail-closed).
- **Invariant/Constraints:** Список має містити лише allowlisted `strategy_id`, для яких існує plugin та профіль `config/aurora/strategies/<id>.yaml`.


---

### `strategies_registry.assignments.DOGEUSDT`
- **Type:** `list[string]`
- **Logic Owner:** `strategies`
- **Code Reference:** `apps/reference/domains/strategies/registry.py:62` (func: `StrategyRuntime.start`) ; `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > SSOT активації стратегій для символу: `symbol → [strategy_id...]`. Використовується **двома** споживачами: (1) `StrategyRuntime` стартує лише allowlisted plugins для strategy_id, (2) `DecisionMaking` fail-closed блокує intent, якщо `symbol` або `strategy_id` відсутні в assignments.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше strategy_id у списку ⇒ більше джерел сигналів, але потрібен арбітраж і зростає churn/конфлікти.
    - 🔽 **Too Low:** Порожній/коротший список ⇒ менше сигналів; порожній список фактично вимикає торгівлю для символу (fail-closed).
- **Invariant/Constraints:** Список має містити лише allowlisted `strategy_id`, для яких існує plugin та профіль `config/aurora/strategies/<id>.yaml`.


---

### `strategies_registry.assignments.XRPUSDT`
- **Type:** `list[string]`
- **Logic Owner:** `strategies`
- **Code Reference:** `apps/reference/domains/strategies/registry.py:62` (func: `StrategyRuntime.start`) ; `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > SSOT активації стратегій для символу: `symbol → [strategy_id...]`. Використовується **двома** споживачами: (1) `StrategyRuntime` стартує лише allowlisted plugins для strategy_id, (2) `DecisionMaking` fail-closed блокує intent, якщо `symbol` або `strategy_id` відсутні в assignments.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше strategy_id у списку ⇒ більше джерел сигналів, але потрібен арбітраж і зростає churn/конфлікти.
    - 🔽 **Too Low:** Порожній/коротший список ⇒ менше сигналів; порожній список фактично вимикає торгівлю для символу (fail-closed).
- **Invariant/Constraints:** Список має містити лише allowlisted `strategy_id`, для яких існує plugin та профіль `config/aurora/strategies/<id>.yaml`.


---

### `strategies_registry.assignments.BTCUSDT`
- **Type:** `list[string]`
- **Logic Owner:** `strategies`
- **Code Reference:** `apps/reference/domains/strategies/registry.py:62` (func: `StrategyRuntime.start`) ; `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > SSOT активації стратегій для символу: `symbol → [strategy_id...]`. Використовується **двома** споживачами: (1) `StrategyRuntime` стартує лише allowlisted plugins для strategy_id, (2) `DecisionMaking` fail-closed блокує intent, якщо `symbol` або `strategy_id` відсутні в assignments.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше strategy_id у списку ⇒ більше джерел сигналів, але потрібен арбітраж і зростає churn/конфлікти.
    - 🔽 **Too Low:** Порожній/коротший список ⇒ менше сигналів; порожній список фактично вимикає торгівлю для символу (fail-closed).
- **Invariant/Constraints:** Список має містити лише allowlisted `strategy_id`, для яких існує plugin та профіль `config/aurora/strategies/<id>.yaml`.


---

### `strategies_registry.arbitration.mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Режим детермінованого арбітражу, коли **>1** стратегія одночасно подає intent на один symbol. Поточна реалізація підтримує тільки `priority`; інші значення → fail-closed reject.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Непідтримуване значення ⇒ систематичні `ARBITRATION_REJECT:unknown_mode_*`.
    - 🔽 **Too Low:** `priority` ⇒ арбітраж активний і детермінований.
- **Invariant/Constraints:** Enum: `priority`.


---

### `strategies_registry.arbitration.window_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Розмір decision window (ms) для priority arbitration: якщо два intents приходять у межах `window_ms`, виграє стратегія з меншим rank. За межами вікна новий intent може пройти.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше `window_ms` ⇒ довше придушення lower-priority стратегії (менше churn, але більше missed opportunities).
    - 🔽 **Too Low:** Менше `window_ms` ⇒ частіші перемикання winner у часі (більше churn, але більше шансів lower-priority).
- **Invariant/Constraints:** Must be `> 0`.


---

### `strategies_registry.arbitration.priority.aurora`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Priority rank для `strategy_id` (lower = higher priority). Використовується всередині `DecisionMaking._check_strategy_arbitration()`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий rank (наприклад 3 замість 1) ⇒ стратегія частіше програє віконний арбітраж.
    - 🔽 **Too Low:** Нижчий rank (1) ⇒ стратегія частіше виграє арбітраж у межах `window_ms`.
- **Invariant/Constraints:** Must be specified for all strategies on hybrid symbols (len(assignments[symbol])>1).


---

### `strategies_registry.arbitration.priority.mean_reversion`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Priority rank для `strategy_id` (lower = higher priority). Використовується всередині `DecisionMaking._check_strategy_arbitration()`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий rank (наприклад 3 замість 1) ⇒ стратегія частіше програє віконний арбітраж.
    - 🔽 **Too Low:** Нижчий rank (1) ⇒ стратегія частіше виграє арбітраж у межах `window_ms`.
- **Invariant/Constraints:** Must be specified for all strategies on hybrid symbols (len(assignments[symbol])>1).


---

### `strategies_registry.arbitration.logging.rejected_why_prefix`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Префікс для `why`/reason кодів при відхиленні intents через арбітраж (наприклад `ARBITRATION_REJECT:*`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** (N/A)
    - 🔽 **Too Low:** (N/A)
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies_registry.arbitration.logging.log_level`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1624` (func: `_check_strategy_arbitration`)
- **Mathematical Role:**
    > Політика рівня логування для подій арбітражу. **Наразі runtime-споживача не знайдено** (поле не використовується в `DecisionMaking`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** (N/A)
    - 🔽 **Too Low:** (N/A)
- **Invariant/Constraints:** Enum-ish: INFO/WARNING/ERROR (але зараз не застосовується).


---


## Strategy: `aurora` (from `config/aurora/strategies/aurora.yaml`)

### `strategies.aurora.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Декларативний global enable для Aurora. **Важливо:** поточна активація в runtime є SSOT-driven через `strategies_registry.assignments` (і частково `assets.<SYM>.enabled`). `aurora.enabled=false` наразі не використовується як hard stop у `StrategyRuntime`/`AuroraHandler`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ (як задумано) стратегія увімкнена, але фактична активація все одно визначається assignments.
    - 🔽 **Too Low:** `false` ⇒ (очікувано) вимкнення, але зараз може не зупиняти handler без додаткового wiring.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.type`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.description`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.timeframe_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Базовий таймфрейм Aurora (sec): визначає очікувану частоту барів і прокидається в payload як `tf_sec`. Має збігатися з BarAggregator / backtest емісією барів.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший TF ⇒ менше сигналів, більший lag, менше шуму.
    - 🔽 **Too Low:** Менший TF ⇒ більше сигналів/реактивності, але більше шуму й навантаження.
- **Invariant/Constraints:** Pydantic: `60 <= timeframe_sec <= 3600`.


---

### `strategies.aurora.execution.entry_order_type`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3130` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > ORDER-POLICY-01: тип entry-ордера, який `DecisionMaking` вписує в `TradeIntent` (fail-closed якщо відсутній). Також валідується проти `domains.execution_position.order_capabilities.supported_order_types`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `MARKET` ⇒ швидший fill, але гірший контроль ціни/слипедж.
    - 🔽 **Too Low:** `LIMIT` ⇒ кращий контроль ціни, але ризик не-fill/timeout (потрібна watchdog/TTL політика).
- **Invariant/Constraints:** Enum: `LIMIT|MARKET`. For `LIMIT` потрібен `entry_tif`.


---

### `strategies.aurora.execution.entry_tif`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3130` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > ORDER-POLICY-01: time-in-force для LIMIT entries. `DecisionMaking` fail-closed відхиляє LIMIT intent, якщо `entry_tif` не заданий.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш агресивний TIF (IOC/FOK) ⇒ менше hanging orders, але більше rejects/partial fills (залежно від біржі).
    - 🔽 **Too Low:** Більш пасивний TIF (GTC/GTX) ⇒ більше шансів стати maker, але більше ризику висіти/не виконатися.
- **Invariant/Constraints:** For `MARKET` зазвичай `null`. Enum: `GTC|GTX|IOC|FOK`.


---

### `strategies.aurora.safety_gates.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:2665` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > DM-SAFETY-BYPASSES-P1: якщо `true`, `DecisionMaking` застосовує directional sanity + price-motion gates перед OPEN. Якщо `false` — ці гейти пропускаються (корисно для mean reversion, що торгує проти тренду).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ більше safety (менше небезпечних входів), але менше угод (особливо у тренді протилежному сигналу).
    - 🔽 **Too Low:** `false` ⇒ більше угод, але вищий ризик входів у невідповідному тренді/після імпульсу.
- **Invariant/Constraints:** Required: missing safety_gates block triggers fail-closed reject.


---

### `strategies.aurora.decision.testnet.signal_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/config_loader.py:461` (func: `_resolve_mode_overrides`)
- **Mathematical Role:**
    > Mode override для Aurora DecisionConfig: при `trading_mode=<mode>` loader копіює `decision.<mode>.signal_threshold` → `decision.signal_threshold` (null = no override). Оригінальний блок зберігається для документації.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Завищене значення override ⇒ сильніший вплив саме в цьому режимі.
    - 🔽 **Too Low:** Занижене ⇒ слабший вплив у цьому режимі.
- **Invariant/Constraints:** Має відповідати типу target поля; `null` означає 'не перевизначати'.


---

### `strategies.aurora.decision.production.signal_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/config_loader.py:461` (func: `_resolve_mode_overrides`)
- **Mathematical Role:**
    > Mode override для Aurora DecisionConfig: при `trading_mode=<mode>` loader копіює `decision.<mode>.signal_threshold` → `decision.signal_threshold` (null = no override). Оригінальний блок зберігається для документації.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Завищене значення override ⇒ сильніший вплив саме в цьому режимі.
    - 🔽 **Too Low:** Занижене ⇒ слабший вплив у цьому режимі.
- **Invariant/Constraints:** Має відповідати типу target поля; `null` означає 'не перевизначати'.


---

### `strategies.aurora.decision.signal_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Базовий поріг для генерації сигналу в Aurora (перед regime-multiplier та side-bias). У kernel: `thr = base_threshold * regime_factor * bias_mult`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий поріг ⇒ менше сигналів, вища селективність, більший lag входу.
    - 🔽 **Too Low:** Нижчий поріг ⇒ більше сигналів, більше шуму/false positives.
- **Invariant/Constraints:** Must be `> 0`. Missing field is fail-closed for typed config.


---

### `strategies.aurora.decision.neutral_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.symbols_to_track`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.behavior_fsm.enable`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.behavior_fsm.high_vol_multiplier`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.behavior_fsm.low_vol_multiplier`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_threshold_multipliers.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.regime_threshold_multipliers.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.decision.side_bias_min_score`
- **Type:** `null`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.side_bias_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.side_bias_target_ratio`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.side_bias_penalty_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.side_bias_min_intents`
- **Type:** `int`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.retry_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3716` (func: `_emit_intent_deferred_v1`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.retry_max_count`
- **Type:** `int`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.retry_backoff_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.regime_thresholds.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.base_probability`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.kelly_cap`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.kelly_alpha`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.payoff_ratio_r`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.p_min`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.p_max`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.kelly.uplift_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.qos.mode`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.qos.enforce`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.qos.exposure_block_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.qos.symbol_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.qos.max_intents_per_minute_per_symbol`
- **Type:** `int`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.signals.normalize_signals_mode`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.signals.enable_new_metrics`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.signals.delta_price_cap_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.bar_gating`
- **Type:** `null`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.roi_exit`
- **Type:** `null`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.mean_reversion`
- **Type:** `null`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.scoring_version`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.direction_strength_scoring.directional_features`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.direction_strength_scoring.strength_features`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.direction_strength_scoring.strength_alpha`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.direction_strength_scoring.strength_cap`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Стратегічний параметр Aurora (DecisionConfig). Частина полів активно читається `AuroraHandler`/kernel; частина може бути тільки типізованою (без runtime wiring).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення зазвичай робить гейт/фільтр менш або більш строгим залежно від семантики параметра.
    - 🔽 **Too Low:** Зменшення значення — зворотній ефект; для порогів часто збільшує частоту сигналів.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.decision.liquidity_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.decision.liquidity_gate.kappa_min`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.decision.liquidity_gate.kappa_max`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.decision.liquidity_gate.failsafe_qty_check`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.decision.essential_features`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Список required фіч для scoring. У kernel: якщо readiness не містить ключ або ключ не ready → scoring deferred (fail-closed defer).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більш строгий readiness (менше угод під час warmup/дефіциту даних).
    - 🔽 **Too Low:** Менший список ⇒ більше угод, але вищий ризик торгувати без критичних фіч.
- **Invariant/Constraints:** Має відповідати ключам readiness contract з FeatureEngineering.


---

### `strategies.aurora.decision.anchor_shock_veto.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:773` (func: `on_process_strategy`)
- **Mathematical Role:**
    > Anchor Shock Veto: блокує BUY на не-якорних символах, якщо `macro_resid` по anchor падає нижче порогу. Мета — не ловити ніж під час crash BTC.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий (менш негативний) threshold ⇒ частіше veto (консервативніше).
    - 🔽 **Too Low:** Нижчий (більш негативний) threshold ⇒ рідше veto (агресивніше).
- **Invariant/Constraints:** If enabled: requires feature `macro_resid` and correct anchor_symbol.


---

### `strategies.aurora.decision.anchor_shock_veto.anchor_symbol`
- **Type:** `string`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:773` (func: `on_process_strategy`)
- **Mathematical Role:**
    > Anchor Shock Veto: блокує BUY на не-якорних символах, якщо `macro_resid` по anchor падає нижче порогу. Мета — не ловити ніж під час crash BTC.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий (менш негативний) threshold ⇒ частіше veto (консервативніше).
    - 🔽 **Too Low:** Нижчий (більш негативний) threshold ⇒ рідше veto (агресивніше).
- **Invariant/Constraints:** If enabled: requires feature `macro_resid` and correct anchor_symbol.


---

### `strategies.aurora.decision.anchor_shock_veto.threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:773` (func: `on_process_strategy`)
- **Mathematical Role:**
    > Anchor Shock Veto: блокує BUY на не-якорних символах, якщо `macro_resid` по anchor падає нижче порогу. Мета — не ловити ніж під час crash BTC.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий (менш негативний) threshold ⇒ частіше veto (консервативніше).
    - 🔽 **Too Low:** Нижчий (більш негативний) threshold ⇒ рідше veto (агресивніше).
- **Invariant/Constraints:** If enabled: requires feature `macro_resid` and correct anchor_symbol.


---

### `strategies.aurora.decision.holding_period.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.decision.holding_period.min_duration_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.decision.holding_period.emergency_exit_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.decision.holding_period.apply_to_flips`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.decision.gates.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1315` (func: `_apply_vol_adj_gates`)
- **Mathematical Role:**
    > Sigma-normalized motion gates (anti-flat / anti-FOMO). Використовує `pm_norm_{window}s` і пороги `anti_flat_sigma`/`anti_fomo_sigma` для блокування ENTRY.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `anti_fomo_sigma` ⇒ менш суворий anti-FOMO (менше блоків на імпульсах).
    - 🔽 **Too Low:** Нижчий `anti_fomo_sigma` або вищий `anti_flat_sigma` ⇒ більше блоків (менше churn у dead market, але більше missed entries).
- **Invariant/Constraints:** Requires FE price_motion readiness for selected window (10/60/300).


---

### `strategies.aurora.decision.gates.anti_flat_sigma`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1315` (func: `_apply_vol_adj_gates`)
- **Mathematical Role:**
    > Sigma-normalized motion gates (anti-flat / anti-FOMO). Використовує `pm_norm_{window}s` і пороги `anti_flat_sigma`/`anti_fomo_sigma` для блокування ENTRY.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `anti_fomo_sigma` ⇒ менш суворий anti-FOMO (менше блоків на імпульсах).
    - 🔽 **Too Low:** Нижчий `anti_fomo_sigma` або вищий `anti_flat_sigma` ⇒ більше блоків (менше churn у dead market, але більше missed entries).
- **Invariant/Constraints:** Requires FE price_motion readiness for selected window (10/60/300).


---

### `strategies.aurora.decision.gates.anti_fomo_sigma`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1315` (func: `_apply_vol_adj_gates`)
- **Mathematical Role:**
    > Sigma-normalized motion gates (anti-flat / anti-FOMO). Використовує `pm_norm_{window}s` і пороги `anti_flat_sigma`/`anti_fomo_sigma` для блокування ENTRY.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `anti_fomo_sigma` ⇒ менш суворий anti-FOMO (менше блоків на імпульсах).
    - 🔽 **Too Low:** Нижчий `anti_fomo_sigma` або вищий `anti_flat_sigma` ⇒ більше блоків (менше churn у dead market, але більше missed entries).
- **Invariant/Constraints:** Requires FE price_motion readiness for selected window (10/60/300).


---

### `strategies.aurora.decision.gates.motion_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1315` (func: `_apply_vol_adj_gates`)
- **Mathematical Role:**
    > Sigma-normalized motion gates (anti-flat / anti-FOMO). Використовує `pm_norm_{window}s` і пороги `anti_flat_sigma`/`anti_fomo_sigma` для блокування ENTRY.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `anti_fomo_sigma` ⇒ менш суворий anti-FOMO (менше блоків на імпульсах).
    - 🔽 **Too Low:** Нижчий `anti_fomo_sigma` або вищий `anti_flat_sigma` ⇒ більше блоків (менше churn у dead market, але більше missed entries).
- **Invariant/Constraints:** Requires FE price_motion readiness for selected window (10/60/300).


---

### `strategies.aurora.decision.reentry_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Re-entry cooldown після закриття (anti ping-pong) на рівні стратегії Aurora. Fallback: per-asset → global decision.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший cooldown ⇒ менше churn, але більше missed opportunities.
    - 🔽 **Too Low:** Менший cooldown ⇒ швидше повторні входи, але більше ping-pong.
- **Invariant/Constraints:** Must be `>= 0`.


---

### `strategies.aurora.decision.feature_neutrals.obi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.tfi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.delta_price`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.ema_bias`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.volume_spike`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.volatility_state`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.macro_sync`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.feature_neutrals.macro_resid`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Neutral point для фічі (використовується для signed_v2 трансформацій/центрування). Впливає на те, що вважається 'нейтральним' значенням фічі.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення neutral ⇒ змінює sign/амплітуду нормалізованого внеску (може радикально переформатувати score).
    - 🔽 **Too Low:** Зміщення в інший бік ⇒ аналогічно; неконсистентні neutrals можуть викликати bias у скорингу.
- **Invariant/Constraints:** Має бути узгоджено з діапазоном фічі (наприклад 0.5 для [0,1] фіч).


---

### `strategies.aurora.decision.signal_weights.obi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.tfi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.delta_price`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.ema_bias`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.volume_spike`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.volatility_state`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.decision.signal_weights.macro_resid`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.aurora.assets.ETHUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.ETHUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.ETHUSDT.holding_period.min_duration_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.ETHUSDT.holding_period.emergency_exit_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.ETHUSDT.reentry_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Re-entry cooldown після закриття (anti ping-pong) на рівні стратегії Aurora. Fallback: per-asset → global decision.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший cooldown ⇒ менше churn, але більше missed opportunities.
    - 🔽 **Too Low:** Менший cooldown ⇒ швидше повторні входи, але більше ping-pong.
- **Invariant/Constraints:** Must be `>= 0`.


---

### `strategies.aurora.assets.ETHUSDT.weights.ema_bias`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.volume_spike`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.macro_resid`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.obi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.tfi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.volatility_state`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.weights.delta_price`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.ETHUSDT.liquidity_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.ETHUSDT.liquidity_gate.kappa_min`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.ETHUSDT.liquidity_gate.kappa_max`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.ETHUSDT.liquidity_gate.failsafe_qty_check`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.ETHUSDT.side_bias.penalty_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.side_bias.window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.side_bias.target_ratio`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.regime_thresholds.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.regime_thresholds.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.regime_thresholds.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.regime_thresholds.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.regime_sizing.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.ETHUSDT.regime_sizing.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.ETHUSDT.regime_sizing.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.ETHUSDT.exit.sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:781` (func: `_calculate_bracket_prices`)
- **Mathematical Role:**
    > Базовий SL як частка від entry (`0.01`=1%). Використовується в `ManageFlowFSM` для розрахунку SL ціни, якщо стратегія не інжектнула stop_price.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий sl_pct ⇒ ширший SL (рідше stop-out, але більший risk/втрата на угоду).
    - 🔽 **Too Low:** Нижчий sl_pct ⇒ тісніший SL (частіше stop-out, але менший risk/швидший exit).
- **Invariant/Constraints:** Fail-closed: має бути задано для кожного символу, який торгується Aurora (0 < sl_pct < 1).


---

### `strategies.aurora.assets.ETHUSDT.exit.max_hold_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:297` (func: `_get_max_hold_sec`)
- **Mathematical Role:**
    > Max holding time (sec) для примусового reduce-only CLOSE у `ManageFlowFSM` (watchdog проти завислих позицій).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше max_hold_sec ⇒ довше тримати позицію (менше примусових exits), але більший tail risk.
    - 🔽 **Too Low:** Менше max_hold_sec ⇒ часті forced exits, менше risk, але може різати PnL у тренді.
- **Invariant/Constraints:** Optional. Якщо задано — має бути `> 0`.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.FLAT_LOW`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.FLAT_NORMAL`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.sl_mult.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.FLAT_LOW`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.FLAT_NORMAL`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.tp_mult.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.min_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.max_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.min_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.max_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.exit.regime_tpsl.min_dist_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.ETHUSDT.take_profit.tp_low_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.ETHUSDT.take_profit.tp_high_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.ETHUSDT.take_profit.partial_exit_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.ETHUSDT.trailing_stop.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.ETHUSDT.trailing_stop.activation_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.ETHUSDT.trailing_stop.trail_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.ETHUSDT.trailing_stop.min_update_interval_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.ETHUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.signal_threshold.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.signal_threshold.value`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.ETHUSDT.cooldown_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1754` (func: `_get_symbol_cooldown`)
- **Mathematical Role:**
    > Per-symbol QoS cooldown (seconds) для Aurora. `DecisionMaking` використовує його як override для `domains.decision_making.qos.symbol_cooldown_sec` (fallback, якщо значення не задано).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше cooldown ⇒ менше intents/херня-угод, але більше lag і менше чутливість.
    - 🔽 **Too Low:** Менше cooldown ⇒ більше intents, ризик churn/спаму/overtrading.
- **Invariant/Constraints:** Must be `>= 0`. Applies in `DecisionMaking._get_symbol_cooldown()`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.volatility_entry_logic.regime_multipliers.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.ETHUSDT.timeframe_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.holding_period.min_duration_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.SOLUSDT.holding_period.emergency_exit_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.SOLUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.SOLUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.SOLUSDT.reentry_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Re-entry cooldown після закриття (anti ping-pong) на рівні стратегії Aurora. Fallback: per-asset → global decision.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший cooldown ⇒ менше churn, але більше missed opportunities.
    - 🔽 **Too Low:** Менший cooldown ⇒ швидше повторні входи, але більше ping-pong.
- **Invariant/Constraints:** Must be `>= 0`.


---

### `strategies.aurora.assets.SOLUSDT.weights.ema_bias`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.volume_spike`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.macro_resid`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.obi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.tfi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.volatility_state`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.weights.delta_price`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.SOLUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.aurora.assets.SOLUSDT.liquidity_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.SOLUSDT.liquidity_gate.kappa_min`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.SOLUSDT.liquidity_gate.kappa_max`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.SOLUSDT.liquidity_gate.failsafe_qty_check`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.SOLUSDT.side_bias.penalty_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.side_bias.window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.side_bias.target_ratio`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.regime_thresholds.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.regime_thresholds.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.regime_thresholds.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.regime_thresholds.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.regime_sizing.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.SOLUSDT.regime_sizing.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.SOLUSDT.regime_sizing.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.SOLUSDT.exit.sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:781` (func: `_calculate_bracket_prices`)
- **Mathematical Role:**
    > Базовий SL як частка від entry (`0.01`=1%). Використовується в `ManageFlowFSM` для розрахунку SL ціни, якщо стратегія не інжектнула stop_price.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий sl_pct ⇒ ширший SL (рідше stop-out, але більший risk/втрата на угоду).
    - 🔽 **Too Low:** Нижчий sl_pct ⇒ тісніший SL (частіше stop-out, але менший risk/швидший exit).
- **Invariant/Constraints:** Fail-closed: має бути задано для кожного символу, який торгується Aurora (0 < sl_pct < 1).


---

### `strategies.aurora.assets.SOLUSDT.exit.max_hold_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:297` (func: `_get_max_hold_sec`)
- **Mathematical Role:**
    > Max holding time (sec) для примусового reduce-only CLOSE у `ManageFlowFSM` (watchdog проти завислих позицій).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше max_hold_sec ⇒ довше тримати позицію (менше примусових exits), але більший tail risk.
    - 🔽 **Too Low:** Менше max_hold_sec ⇒ часті forced exits, менше risk, але може різати PnL у тренді.
- **Invariant/Constraints:** Optional. Якщо задано — має бути `> 0`.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.FLAT_LOW`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.FLAT_NORMAL`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.sl_mult.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.FLAT_LOW`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.FLAT_NORMAL`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.tp_mult.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.min_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.max_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.min_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.max_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.exit.regime_tpsl.min_dist_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.SOLUSDT.take_profit.tp_low_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.SOLUSDT.take_profit.tp_high_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.SOLUSDT.take_profit.partial_exit_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.SOLUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.trailing_stop.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.SOLUSDT.trailing_stop.activation_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.SOLUSDT.trailing_stop.trail_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.SOLUSDT.trailing_stop.min_update_interval_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.SOLUSDT.signal_threshold.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.signal_threshold.value`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.SOLUSDT.cooldown_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1754` (func: `_get_symbol_cooldown`)
- **Mathematical Role:**
    > Per-symbol QoS cooldown (seconds) для Aurora. `DecisionMaking` використовує його як override для `domains.decision_making.qos.symbol_cooldown_sec` (fallback, якщо значення не задано).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше cooldown ⇒ менше intents/херня-угод, але більше lag і менше чутливість.
    - 🔽 **Too Low:** Менше cooldown ⇒ більше intents, ризик churn/спаму/overtrading.
- **Invariant/Constraints:** Must be `>= 0`. Applies in `DecisionMaking._get_symbol_cooldown()`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.SOLUSDT.timeframe_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.aurora.assets.BTCUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.BTCUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.aurora.assets.BTCUSDT.side_bias.penalty_factor`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.side_bias.window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.side_bias.target_ratio`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.weights.ema_bias`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.volume_spike`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.macro_resid`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.obi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.tfi`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.volatility_state`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.weights.delta_price`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96` (func: `compute_direction_strength_score`)
- **Mathematical Role:**
    > Вага фічі у direction/strength scoring. Входить у лінійну комбінацію в `compute_direction_strength_score()` (після нормалізації/нейтралей).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вища вага ⇒ цей сигнал сильніше впливає на фінальний score.
    - 🔽 **Too Low:** Нижча (або 0) ⇒ сигнал майже не впливає; зміна знаку інвертує вклад.
- **Invariant/Constraints:** Ключі ваг мають відповідати іменам фіч (`obi`, `tfi`, `delta_price`, ...).


---

### `strategies.aurora.assets.BTCUSDT.holding_period.min_duration_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.BTCUSDT.holding_period.emergency_exit_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1078` (func: `_get_min_duration_sec`)
- **Mathematical Role:**
    > Minimum holding period (anti-churn): блокує signal-based exits/flip до `min_duration_sec` з моменту входу, з emergency override по |score|. Per-asset overrides supported.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший `min_duration_sec` ⇒ менше churn, але більше lag на виході/flip.
    - 🔽 **Too Low:** Менший `min_duration_sec` ⇒ більше реактивності, але ризик ping-pong.
- **Invariant/Constraints:** If enabled: `min_duration_sec >= 0`, `0<emergency_exit_threshold<=1`.


---

### `strategies.aurora.assets.BTCUSDT.reentry_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Re-entry cooldown після закриття (anti ping-pong) на рівні стратегії Aurora. Fallback: per-asset → global decision.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший cooldown ⇒ менше churn, але більше missed opportunities.
    - 🔽 **Too Low:** Менший cooldown ⇒ швидше повторні входи, але більше ping-pong.
- **Invariant/Constraints:** Must be `>= 0`.


---

### `strategies.aurora.assets.BTCUSDT.liquidity_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.BTCUSDT.liquidity_gate.kappa_min`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.BTCUSDT.liquidity_gate.kappa_max`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.BTCUSDT.liquidity_gate.failsafe_qty_check`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1858` (func: `_check_liquidity_gate`)
- **Mathematical Role:**
    > Liquidity gate (Score V2): коли enabled, Aurora блокує сигнал якщо `liquidity_kappa` не ready або `kappa < kappa_min`. Fallback: per-asset → global decision → disabled.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `kappa_min`/строгіший gate ⇒ менше угод у тонкій ліквідності, менше slippage risk.
    - 🔽 **Too Low:** Нижчий `kappa_min` ⇒ більше угод, але ризик торгівлі в поганій ліквідності.
- **Invariant/Constraints:** If enabled: requires readiness key `liquidity_kappa` and parseable feature value.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_thresholds.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:86` (func: `AuroraScoringKernel.compute`)
- **Mathematical Role:**
    > Мультиплікатор порогу по режиму (Regime → factor). У kernel: `thr = base_threshold * factor`. Має містити `DEFAULT` або конкретний ключ поточного режиму; інакше scoring deferred.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Фактор >1 ⇒ робить сигнали рідшими в цьому режимі (вищий поріг).
    - 🔽 **Too Low:** Фактор <1 ⇒ робить сигнали частішими в цьому режимі (нижчий поріг).
- **Invariant/Constraints:** All factors must be finite and `> 0`; include `DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.regime_sizing.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.BTCUSDT.regime_sizing.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.BTCUSDT.regime_sizing.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.BTCUSDT.regime_sizing.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.BTCUSDT.regime_sizing.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:923` (func: `_on_strategy_signal_gateway`)
- **Mathematical Role:**
    > Aurora regime sizing multiplier: масштабує `margin_pct` у margin-first sizing (`qty` ∝ `margin_pct_mult`). Fallback: regime key → DEFAULT (якщо є).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий multiplier ⇒ більші позиції у цьому режимі (більший ризик/прибуток).
    - 🔽 **Too Low:** Нижчий multiplier ⇒ менші позиції у цьому режимі (консервативніше).
- **Invariant/Constraints:** Should be finite and `> 0` to avoid zero-size trades.


---

### `strategies.aurora.assets.BTCUSDT.exit.sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:781` (func: `_calculate_bracket_prices`)
- **Mathematical Role:**
    > Базовий SL як частка від entry (`0.01`=1%). Використовується в `ManageFlowFSM` для розрахунку SL ціни, якщо стратегія не інжектнула stop_price.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий sl_pct ⇒ ширший SL (рідше stop-out, але більший risk/втрата на угоду).
    - 🔽 **Too Low:** Нижчий sl_pct ⇒ тісніший SL (частіше stop-out, але менший risk/швидший exit).
- **Invariant/Constraints:** Fail-closed: має бути задано для кожного символу, який торгується Aurora (0 < sl_pct < 1).


---

### `strategies.aurora.assets.BTCUSDT.exit.max_hold_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:297` (func: `_get_max_hold_sec`)
- **Mathematical Role:**
    > Max holding time (sec) для примусового reduce-only CLOSE у `ManageFlowFSM` (watchdog проти завислих позицій).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше max_hold_sec ⇒ довше тримати позицію (менше примусових exits), але більший tail risk.
    - 🔽 **Too Low:** Менше max_hold_sec ⇒ часті forced exits, менше risk, але може різати PnL у тренді.
- **Invariant/Constraints:** Optional. Якщо задано — має бути `> 0`.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.sl_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.tp_mult.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.tp_mult.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.tp_mult.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.tp_mult.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.tp_mult.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.min_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.max_sl_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.min_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.max_tp_rr`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.exit.regime_tpsl.min_dist_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1457` (func: `_compute_regime_tpsl`)
- **Mathematical Role:**
    > Regime-based TP/SL injection (strategy primacy): Aurora може інжектити `stop_price/target_price` у payload на основі режиму. Підтримує режими `pct_mult` (мультиплікатори) та `atr` (ATR-based), плюс guardrails (min/max/мин дистанція).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers/rr ⇒ ширші SL/TP, менше стопів, але більший risk і менша частота тейків.
    - 🔽 **Too Low:** Нижчі multipliers/rr ⇒ тісніші SL/TP, більше стопів/виходів, але менший risk.
- **Invariant/Constraints:** If enabled: requires `DEFAULT` keys in maps; must satisfy guardrails; missing keys can skip injection.


---

### `strategies.aurora.assets.BTCUSDT.take_profit.tp_low_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.BTCUSDT.take_profit.tp_high_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.BTCUSDT.take_profit.partial_exit_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:228` (func: `_get_take_profit_params`)
- **Mathematical Role:**
    > TP параметри в risk-ratio одиницях (відносно SL дистанції): TP1=sl_pct*tp_low_ratio, TP2=sl_pct*tp_high_ratio. Використовується в `ManageFlowFSM` при відсутності intent-injection.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі ratios ⇒ дальші тейки (менше winrate, більше avg win).
    - 🔽 **Too Low:** Нижчі ratios ⇒ ближчі тейки (більше winrate, менше avg win).
- **Invariant/Constraints:** Fail-closed для TP1 (`tp_low_ratio` required якщо немає injected TP).


---

### `strategies.aurora.assets.BTCUSDT.trailing_stop.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.BTCUSDT.trailing_stop.activation_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.BTCUSDT.trailing_stop.trail_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.BTCUSDT.trailing_stop.min_update_interval_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical Role:**
    > Trailing-stop параметри (optional): якщо enabled, ManageFlow може ставити/оновлювати trailing logic згідно activation_pct/trail_pct.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший trail_pct ⇒ більше 'дихання' (менше вибивань), але гірший захист прибутку.
    - 🔽 **Too Low:** Менший trail_pct ⇒ tighter trailing (кращий захист), але більше stop-outs на шумі.
- **Invariant/Constraints:** Optional feature; якщо не задано — trailing disabled.


---

### `strategies.aurora.assets.BTCUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.signal_threshold.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.signal_threshold.value`
- **Type:** `null`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.aurora.assets.BTCUSDT.cooldown_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:1754` (func: `_get_symbol_cooldown`)
- **Mathematical Role:**
    > Per-symbol QoS cooldown (seconds) для Aurora. `DecisionMaking` використовує його як override для `domains.decision_making.qos.symbol_cooldown_sec` (fallback, якщо значення не задано).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше cooldown ⇒ менше intents/херня-угод, але більше lag і менше чутливість.
    - 🔽 **Too Low:** Менше cooldown ⇒ більше intents, ризик churn/спаму/overtrading.
- **Invariant/Constraints:** Must be `>= 0`. Applies in `DecisionMaking._get_symbol_cooldown()`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.HIGH_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.LOW_VOLATILITY`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.TREND_UP`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.TREND_DOWN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.MEAN_REVERSION`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.UNCERTAIN`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.volatility_entry_logic.regime_multipliers.DEFAULT`
- **Type:** `float`
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:2038` (func: `_emit_signal`)
- **Mathematical Role:**
    > Volatility-based entry offset для LIMIT/GTX: `offset = atr * regime_multiplier`; entry_price зміщується від anchor_price, щоб підвищити шанс maker fill. Fail-closed якщо немає `DEFAULT` у regime_multipliers.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші multipliers ⇒ далі від ринку (менше taker fills/менше rejects), але більше missed fills.
    - 🔽 **Too Low:** Менші multipliers ⇒ ближче до ринку (більше fills), але ризик taker/відхилень/‘immediately trigger’ в екстремі.
- **Invariant/Constraints:** If enabled: requires ATR feature and `regime_multipliers.DEFAULT`.


---

### `strategies.aurora.assets.BTCUSDT.timeframe_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `strategies.aurora`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:136` (func: `_load_config`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---


## Strategy: `mean_reversion` (from `config/aurora/strategies/mean_reversion.yaml`)

### `strategies.mean_reversion.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Global kill-switch для Mean Reversion. Якщо MR assigned у `strategies_registry` але `enabled=false` → fail-closed crash (SSOT conflict).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ MR може працювати (але лише на assigned symbols).
    - 🔽 **Too Low:** `false` ⇒ MR вимкнено навіть якщо assigned (зупинка runtime).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.timeframe_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`)
- **Mathematical Role:**
    > Таймфрейм барів для MR (sec). Використовується для bar gating та ініціалізації стратегії.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший TF ⇒ менше сигналів/барів, більше lag.
    - 🔽 **Too Low:** Менший TF ⇒ більше барів/сигналів, більше шуму й навантаження.
- **Invariant/Constraints:** Must be `> 0` and match BarAggregator/backtest TF.


---

### `strategies.mean_reversion.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.execution.entry_order_type`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3130` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > ORDER-POLICY-01: тип entry-ордера, який `DecisionMaking` вписує в `TradeIntent` (fail-closed якщо відсутній). Також валідується проти `domains.execution_position.order_capabilities.supported_order_types`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `MARKET` ⇒ швидший fill, але гірший контроль ціни/слипедж.
    - 🔽 **Too Low:** `LIMIT` ⇒ кращий контроль ціни, але ризик не-fill/timeout (потрібна watchdog/TTL політика).
- **Invariant/Constraints:** Enum: `LIMIT|MARKET`. For `LIMIT` потрібен `entry_tif`.


---

### `strategies.mean_reversion.execution.entry_tif`
- **Type:** `null`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3130` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > ORDER-POLICY-01: time-in-force для LIMIT entries. `DecisionMaking` fail-closed відхиляє LIMIT intent, якщо `entry_tif` не заданий.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш агресивний TIF (IOC/FOK) ⇒ менше hanging orders, але більше rejects/partial fills (залежно від біржі).
    - 🔽 **Too Low:** Більш пасивний TIF (GTC/GTX) ⇒ більше шансів стати maker, але більше ризику висіти/не виконатися.
- **Invariant/Constraints:** For `MARKET` зазвичай `null`. Enum: `GTC|GTX|IOC|FOK`.


---

### `strategies.mean_reversion.safety_gates.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:2665` (func: `_propose_trade_intent`)
- **Mathematical Role:**
    > DM-SAFETY-BYPASSES-P1: якщо `true`, `DecisionMaking` застосовує directional sanity + price-motion gates перед OPEN. Якщо `false` — ці гейти пропускаються (корисно для mean reversion, що торгує проти тренду).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ більше safety (менше небезпечних входів), але менше угод (особливо у тренді протилежному сигналу).
    - 🔽 **Too Low:** `false` ⇒ більше угод, але вищий ризик входів у невідповідному тренді/після імпульсу.
- **Invariant/Constraints:** Required: missing safety_gates block triggers fail-closed reject.


---

### `strategies.mean_reversion.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.atr_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.rsi_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.rsi_oversold`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.rsi_overbought`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.min_bars`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.min_bb_width`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.max_bb_width`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.sl_atr_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.tp_to_mid`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.strategy.cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Параметр MRStrategy (Bollinger/ATR/RSI/фільтри/кулдаун). Використовується для генерації MR сигналів на барах.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Збільшення вікон/кулдаунів ⇒ більше smoothing, менше сигналів; збільшення порогів може як збільшити, так і зменшити частоту (залежить від параметра).
    - 🔽 **Too Low:** Зменшення вікон/кулдаунів ⇒ більше реактивності та шуму.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.regime_thresholds.high_vol_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:311` (func: `_init_strategies`)
- **Mathematical Role:**
    > Пороги класифікації FLAT режимів на основі ATR% (volatility proxy): визначає межі `FLAT_LOW/FLAT_HIGH`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі пороги ⇒ рідше класифікується як high-vol/low-vol (більше потрапляє в 'normal').
    - 🔽 **Too Low:** Нижчі пороги ⇒ частіше крайні класи (low/high), що змінює allowed_regimes та sizing multipliers.
- **Invariant/Constraints:** Must be `> 0` (ratio).


---

### `strategies.mean_reversion.regime_thresholds.low_vol_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:311` (func: `_init_strategies`)
- **Mathematical Role:**
    > Пороги класифікації FLAT режимів на основі ATR% (volatility proxy): визначає межі `FLAT_LOW/FLAT_HIGH`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі пороги ⇒ рідше класифікується як high-vol/low-vol (більше потрапляє в 'normal').
    - 🔽 **Too Low:** Нижчі пороги ⇒ частіше крайні класи (low/high), що змінює allowed_regimes та sizing multipliers.
- **Invariant/Constraints:** Must be `> 0` (ratio).


---

### `strategies.mean_reversion.assets.DOGEUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Per-asset enable для MR. Використовується разом із assignments: enabled_symbols = assigned ∩ enabled_assets.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгувати MR якщо assigned.
    - 🔽 **Too Low:** `false` ⇒ символ вимкнено навіть якщо assigned (fail-closed, якщо assigned).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.mean_reversion.assets.DOGEUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.DOGEUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.min_bb_width`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.sl_atr_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.tp_to_mid`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.strategy.cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.DOGEUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.assets.BTCUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Per-asset enable для MR. Використовується разом із assignments: enabled_symbols = assigned ∩ enabled_assets.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгувати MR якщо assigned.
    - 🔽 **Too Low:** `false` ⇒ символ вимкнено навіть якщо assigned (fail-closed, якщо assigned).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.mean_reversion.assets.BTCUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.BTCUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.min_bb_width`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.tp_to_mid`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.sl_atr_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.strategy.cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.BTCUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.assets.XRPUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Per-asset enable для MR. Використовується разом із assignments: enabled_symbols = assigned ∩ enabled_assets.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгувати MR якщо assigned.
    - 🔽 **Too Low:** `false` ⇒ символ вимкнено навіть якщо assigned (fail-closed, якщо assigned).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.mean_reversion.assets.XRPUSDT.leverage.target`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.XRPUSDT.leverage.mode`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:658` (func: `validate_leverage_ssot_consistency`)
- **Mathematical Role:**
    > Leverage config у strategy профілі. **SSOT для leverage — instruments.yaml**; execution стартово збирає leverage з instruments і лише логгує/валідує mismatch зі strategy leverage. (Strategy значення фактично IGNORED для реального встановлення плеча.)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо розходиться з instruments: збільшує ризик конфіг-дрифту/неочікуваного плеча (але enforcement все одно з instruments).
    - 🔽 **Too Low:** Узгоджені значення ⇒ чистіша SSOT, менше конфіг-шуму.
- **Invariant/Constraints:** SSOT is `instruments.<SYM>.execution.target_leverage`; strategy leverage should match or be removed.


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.min_bb_width`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.tp_to_mid`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.sl_atr_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.strategy.cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.XRPUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.assets.ETHUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Per-asset enable для MR. Використовується разом із assignments: enabled_symbols = assigned ∩ enabled_assets.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгувати MR якщо assigned.
    - 🔽 **Too Low:** `false` ⇒ символ вимкнено навіть якщо assigned (fail-closed, якщо assigned).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.bb_window`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.bb_num_std`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.min_bb_width`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.entry_threshold`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.tp_to_mid`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.sl_atr_mult`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.strategy.cooldown_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.ETHUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.assets.SOLUSDT.enabled`
- **Type:** `bool`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (func: `_parse_config`)
- **Mathematical Role:**
    > Per-asset enable для MR. Використовується разом із assignments: enabled_symbols = assigned ∩ enabled_assets.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгувати MR якщо assigned.
    - 🔽 **Too Low:** `false` ⇒ символ вимкнено навіть якщо assigned (fail-closed, якщо assigned).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.position_mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:4001` (func: `_resolve_position_mode`)
- **Mathematical Role:**
    > Position mode (STRICT|DYNAMIC) для anti-pyramiding / flip orchestration. STRICT блокує same-side pyramiding; DYNAMIC дозволяє.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `DYNAMIC` ⇒ більше pyramiding (агресивніше), але більший ризик експозиції.
    - 🔽 **Too Low:** `STRICT` ⇒ менше pyramiding, більше safety, але менше можливостей у тренді.
- **Invariant/Constraints:** Enum: `STRICT|DYNAMIC`. Missing/invalid ⇒ fail-closed block in flip orchestration.


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.bb_window`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.bb_num_std`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.min_bb_width`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.entry_threshold`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.tp_to_mid`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.sl_atr_mult`
- **Type:** `null`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.strategy.cooldown_sec`
- **Type:** `null` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:289` (func: `_init_strategies`) ; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:320` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Стратегічний параметр (typed config). Без специфічного трасування: трактувати як SSOT knob для відповідного блоку логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зростання значення підсилює відповідний ефект/допуск.
    - 🔽 **Too Low:** Зменшення значення послаблює ефект/допуск.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).


---

### `strategies.mean_reversion.assets.SOLUSDT.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Allowlist flat regimes для торгівлі MR. У MRStrategy: якщо regime не у списку ⇒ NEUTRAL (fail-closed allowlist). Per-asset override підтримується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше режимів у списку ⇒ більше угод (ширший market coverage).
    - 🔽 **Too Low:** Менше режимів ⇒ менше угод, більш консервативно; порожній список ⇒ торгівля вимкнена (allow nothing).
- **Invariant/Constraints:** Regime names must match Flat regime mapping (`FLAT_*`, `MEAN_REVERSION`, ...).


---

### `strategies.mean_reversion.regime_sizing.FLAT_LOW.sizing_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_LOW.stop_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_LOW.target_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_NORMAL.sizing_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_NORMAL.stop_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_NORMAL.target_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_HIGH.sizing_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_HIGH.stop_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---

### `strategies.mean_reversion.regime_sizing.FLAT_HIGH.target_mult`
- **Type:** `float`
- **Logic Owner:** `strategies.mean_reversion`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:357` (func: `MeanReversion1mStrategy.on_bar`)
- **Mathematical Role:**
    > Regime sizing multipliers для MR (per flat regime): sizing_mult/stop_mult/target_mult. Використовується при побудові stop/target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищі multipliers ⇒ більші targets/ширші stops/більший size (залежно від поля).
    - 🔽 **Too Low:** Нижчі multipliers ⇒ консервативніше.
- **Invariant/Constraints:** All multipliers should be positive and finite.


---
