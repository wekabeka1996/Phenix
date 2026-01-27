# 📄 Паспорт конфігурації: aurora/strategies.yaml (Section: version, assignments, arbitration)

## 🔍 Загальний опис блоку
Файл `strategies.yaml` є **SSOT (Single Source of Truth)** для двох критичних рішень у системі:
1. **Яка стратегія активна для кожного символу** (assignment engine)
2. **Як розв'язувати конфлікти, коли кілька стратегій генерують intent на одному символі** (arbitration engine)

Цей конфіг завантажується в `AuroraConfig.strategies_registry` і контролює роботу decision_making домену.

---

## 🛠 Деталізація полів

| Поле | Тип | Pydantic | Статус | Роль у проекті |
|---|---|---|---|---|
| `version` | `str` | ✅ | 🟢 Active | Версійність конфіг-схеми (SemVer) |
| `assignments` | `Dict[str, List[str]]` | ✅ | 🟢 Active | SSOT: який symbol → які strategies активні |
| `arbitration.mode` | `Literal['priority']` | ✅ | 🟢 Active | Режим розв'язання конфліктів (тільки "priority" реалізована) |
| `arbitration.window_ms` | `int` | ✅ | 🟢 Active | Часове вікно для windowed arbitration (ms) |
| `arbitration.priority` | `Dict[str, int]` | ✅ | 🟢 Active | Ранги пріоритету策略 (lower = higher priority) |
| `arbitration.logging` | `Object` | ✅ | 🟢 Active | Конфіг логування для відкинутих intents |

---

### 1. `version` (Версія реєстру)
* **Суть:** Версійність структури конфіг-файлу. Використовується для детектування несумісних змін при обновленні системи.
* **Домен:** System Core (Config Management).
* **Режими роботи:** Усі режими (Live, Backtest, Testnet).
* **Code Trace:**
    * [apps/reference/config_models.py](apps/reference/config_models.py#L465) — зчитується як рядок у `StrategiesRegistryConfig.version`.
    * [apps/reference/config_loader.py](apps/reference/config_loader.py) — можна переконати версійність при завантаженні (детально не реалізовано).
* **Валідація:**
    * Модель: `StrategiesRegistryConfig.version: str`
    * Обмеження: немає (дозволяється будь-який рядок).
* **Тести:** ✅ Побіжно перевіряється у `test_strategy_aware_gates.py` (структура конфіг-об'єкту).

---

### 2. `assignments` (Призначення стратегій)
* **Суть:** **ОСНОВНИЙ МЕХАНІЗМ** активації стратегій. Словник `symbol → [strategy_id1, strategy_id2, ...]`. Для кожного символу зазначаються ЯКІ стратегії мають генерувати сигнали.
* **Домен:** `Decision Making` (Strategy Activation).
* **Режими роботи:** Усі режими. Критично для Backtest (визначає які стратегії тестуються).
* **Code Trace (Де використовується):**
    * [apps/reference/domains/strategies/registry.py](apps/reference/domains/strategies/registry.py#L60-75) — `StrategyRuntime.start()` читає `assignments`, отримує набір `assigned_ids`, і запускає на кожну plugin.
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L495-514) — `_check_strategy_arbitration()` спочатку перевіряє чи стратегія належить `assignments[symbol]`, інакше відкидає intent (fail-closed).
    * [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py) — Aurora-handler читає `strategies_registry.assignments` для визначення які символи активні для Aurora (STRATEGY-AWARE-GATES-FIX).
    * [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) — MR-handler аналогічно розглядає `assignments['DOGEUSDT']`, `assignments['XRPUSDT']`.
* **Математичний вплив:** Визначає **набір symbols**, для яких система породжує сигнали. Якщо symbol не в `assignments`, всі intent з нього блокуються (fail-closed).
* **Валідація:**
    * Модель: `StrategiesRegistryConfig.assignments: Dict[str, List[str]]`
    * Обмеження:
      * Ключ (symbol) — рядок (e.g., "BTCUSDT")
      * Значення — непустий список строк (strategy_ids)
      * Допустимі strategy_ids: `"aurora"`, `"mean_reversion"`
      * Інші strategy_ids спричиняють `ConfigContractError` у `StrategyRuntime.start()`: "Assigned strategy_ids missing allowlisted plugins"
* **Тести:** 
    * ✅ [tests/unit/test_strategy_aware_gates.py](tests/unit/test_strategy_aware_gates.py#L80-110) — `test_aurora_assigned_to_btc()`, `test_aurora_not_assigned_to_doge()`, `test_mr_assigned_to_doge()`.
    * ✅ [tests/domains/strategies/test_task32_strategy_plugin_registry.py](tests/domains/strategies/test_task32_strategy_plugin_registry.py) — перевірка що `StrategyRuntime.start()` коректно читає `assignments`.
    * ✅ Гібридні (BTC з `["aurora", "mean_reversion"]`) перевіряються у `test_task47_btc_dual_strategy_intents.py`.

**Приклад конфіг-призначення:**
```yaml
assignments:
  BTCUSDT:
    - aurora           # BTC: обидві стратегії активні (гібридний режим)
    - mean_reversion
  ETHUSDT:
    - aurora           # ETH: тільки Aurora
  DOGEUSDT:
    - mean_reversion   # DOGE: тільки Mean Reversion
```

---

### 3. `arbitration.mode` (Режим арбітраж)
* **Суть:** Визначає як система розв'язує конфлікти коли на одному символі >1 стратегія одночасно генерує intent-и.
* **Домен:** `Decision Making` (Intent Arbitration).
* **Режими роботи:** Усі режими, критично для гібридних символів (BTC).
* **Code Trace:**
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1663) — `_check_strategy_arbitration()` спочатку перевіряє `if arb.mode != "priority"` → fail-closed DROP.
* **Валідація:**
    * Модель: `StrategiesArbitrationConfig.mode: Literal['priority']`
    * Обмеження: Тільки значення `'priority'` дозволено. Інші значення (`'regime'`, `'round_robin'` — вказані у коментарях як NOT IMPLEMENTED) спричинять блокування (fail-closed).
* **Тести:** ✅ Вбудовано у `_check_strategy_arbitration()` — невідомий режим повертає `{"allowed": False, "reason": "ARBITRATION_REJECT:unknown_mode_..."}`.

---

### 4. `arbitration.window_ms` (Часове вікно для вибору)
* **Суть:** Розмір часового вікна (мс), протягом якого система застосовує priority arbitration. Запобігає **постійному придушенню** нижчопріоритетної стратегії.
  * **Мотивація:** На BTC обидві стратегії (Aurora + MR) можуть генерувати сигнали. При `window_ms=1000` тільки найперший intent вищого пріоритету за 1с проходить; за межами вікна нижчопріоритетна стратегія може спробувати.
* **Домен:** `Decision Making` (Windowed Arbitration Buffer).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1688-1720) — `_check_strategy_arbitration()`:
      * Зчитує `window_ms = int(arb.window_ms)` (line ~1688)
      * Обчислює `delta_ms = now_ms - last_ts` (line ~1697)
      * Якщо `delta_ms <= window_ms` → порівнює ранги і приймає рішення (line ~1700)
      * Якщо `delta_ms > window_ms` → вікно закінчилось, дозволяє новій стратегії (line ~1718)
* **Математичний вплив:**
  * **Арбітраж у вікні:** `if (now_ms - last_ts) <= window_ms: compare_ranks()`
  * **Вікно закінчилось:** `if (now_ms - last_ts) > window_ms: allow_new_entry()`
* **Валідація:**
    * Модель: `StrategiesArbitrationConfig.window_ms: int`
    * Обмеження: `window_ms > 0` (fail-closed якщо `<= 0`)
* **Тести:** ✅ Логіка windowing перевіряється у `test_task47_btc_dual_strategy_intents.py` — різні комбінації часу вхідних сигналів.

**Приклад:**
- `window_ms = 1000` означає: протягом 1с система дозволяє тільки першому (вищопріоритетному) інтенту пройти; через 1с наступна стратегія може проіснувати нову позицію.

---

### 5. `arbitration.priority` (Ранги пріоритету)
* **Суть:** Словник `strategy_id → rank (int)`. Визначає який intent "виграє" коли кілька стратегій генерують signal у межах одного часового вікна.
  * **Конвенція:** `rank 1` = вищий пріоритет (較低числа), `rank 2` = нижчий пріоритет (вищі числа).
* **Домен:** `Decision Making` (Priority Arbitration).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1673-1683) — Валідація: "Fail-closed if strategy has no priority rank".
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1702-1715) — Порівняння рангів:
      * `if rank < last_rank:` → нова стратегія має вищий пріоритет (нижче число) → **overwrite buffer**
      * `elif rank >= last_rank:` → нова стратегія має нижчий пріоритет → **DROP**
* **Математичний вплив:** 
  * Переможець = `strategy_id` із найменшим `rank` значенням в межах вікна.
* **Валідація:**
    * Модель: `StrategiesArbitrationConfig.priority: Dict[str, int]`
    * Обмеження:
      * Усі strategy_ids зі всіх гібридних символів МАЮТЬ мати записи в `priority`
      * Невдача → `ConfigContractError` при запуску (line ~1643 у config_models.py: validator `validate_priorities_for_hybrid_symbols`)
* **Тести:** 
    * ✅ [tests/unit/test_strategy_aware_gates.py](tests/unit/test_strategy_aware_gates.py) — перевірка валідації гібридних символів
    * ✅ [tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py](tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py) — симуляція BTC з обома стратегіями, перевірка що Aurora (rank=1) блокує MR (rank=2)

**Приклад:**
```yaml
priority:
  aurora: 1            # Вищий пріоритет (вибирається першою)
  mean_reversion: 2    # Нижчий пріоритет (блокується в межах вікна)
```

---

### 6. `arbitration.logging` (Логування відкинутих intents)
* **Суть:** Контролює як система логує событи арбітражу (коли intent відкинуто через нижчий пріоритет).
* **Домен:** `Decision Making` (Observability).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L1714) — Використовується `arb.logging.rejected_why_prefix` при формуванні `reason`:
      ```python
      f"{arb.logging.rejected_why_prefix}:lower_priority_vs_{last_sid}"[:80]
      ```
* **Валідація:**
    * Модель: `StrategiesArbitrationLoggingConfig`
    * Поля:
      * `rejected_why_prefix: str` — префікс для why-кодів (e.g., `"ARBITRATION_REJECT"`)
      * `log_level: str` — рівень логування (`"INFO"` або `"WARNING"`)
* **Тести:** ✅ Перевіряється логування у `test_task47_btc_dual_strategy_intents.py` (чи правильні why-коди формуються).

---

## 📊 Audit Findings (Вердикт)

| Поле | Статус | Примітка |
|---|---|---|
| `assignments` | 🟢 **ACTIVE** | SSOT для активації стратегій; критично для вибору символів. Повна code-trace до `StrategyRuntime` та `DecisionMaking`. |
| `arbitration.mode` | 🟢 **ACTIVE** | Використовується, але тільки `"priority"` реалізована. Інші режими (regime, round_robin) у коментарях (NOT IMPLEMENTED). |
| `arbitration.window_ms` | 🟢 **ACTIVE** | Реалізована детально у windowed arbitration buffer. Логіка повністю прослідкована. |
| `arbitration.priority` | 🟢 **ACTIVE** | Критично для гібридних символів (BTC); валідація при запуску. |
| `arbitration.logging` | 🟢 **ACTIVE** | Контролює why-коди та рівень логування при отриманні reject. |
| `version` | 🟢 **ACTIVE** | Зчитується, але версійність не перевіряється наразі (можна розширити). |

---

## 🔐 Data Cleanliness & Recommendations

### ✅ Що добре:
1. **Fail-closed валідація:** Невідомі strategy_ids спричиняють `ConfigContractError`, а не мовчать.
2. **Pydantic strict validation:** `extra='forbid'` для `StrategiesRegistryConfig` й `StrategiesArbitrationConfig` (SSOT).
3. **Windowed arbitration:** Запобігає постійному придушенню нижчопріоритетної стратегії.

### ⚠️ Потенційні покращення:
1. **Версійність конфіг:** `version` поле зчитується, але версійність при завантаженні не перевіряється. Можна додати gate `if config_version > SUPPORTED_VERSION: raise`.
2. **Інші режими арбітраж:** `"regime"` та `"round_robin"` вказані у коментарях, але не реалізовані. Рекомендується або видалити з коментарів, або позначити як TODO-future.
3. **Документація per-symbol:** На кожному символі мають бути коментарі WHY обрана та конкретна комбінація стратегій (дане повідомлення містить ці коментарі — GOOD).

---

## 🧪 Test Coverage Summary

| Тест-файл | Охоплення |
|---|---|
| [test_strategy_aware_gates.py](tests/unit/test_strategy_aware_gates.py) | ✅ assignments перевірка (aurora vs MR per symbol) |
| [test_task32_strategy_plugin_registry.py](tests/domains/strategies/test_task32_strategy_plugin_registry.py) | ✅ StrategyRuntime.start() + assignments |
| [test_task47_btc_dual_strategy_intents.py](tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py) | ✅ Windowed arbitration, priority ranks |
| [test_mean_reversion_strategy.py](tests/domains/test_mean_reversion_strategy.py) | ✅ MR activation per assignments |

---

**Документ завершено:** 2026-01-27  
**SSOT:** `config/aurora/strategies.yaml` + `config_models.py` (`StrategiesRegistryConfig`, `StrategiesArbitrationConfig`)
