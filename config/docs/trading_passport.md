# Semantic Configuration Passport: `config/aurora/trading.yaml`

Цей паспорт описує **торгову логіку та ризик** на рівні `trading.yaml`: режим роботи, бюджет TCA/ризику, дані ринку, виконання (execution) та оперативні запобіжники.

**Критичні уточнення (підтверджено трасуванням коду):**
- **`trading.risk.*` частково legacy.** Runtime читає з цього блоку лише:
  - `trading.risk.daily.*` (DailyRiskState: блокування *нових* відкриттів, не ліквідація);
  - `trading.risk.soft_limits.*` + `trading.risk.regime_adaptation.*` (soft-clip/soft-reject сайзингу в `execution_position`).
- **Hard-ліміти експозиції не належать `trading.execution.exposure.*`:** ExposureGuard бере ліміти/TTL з `domains.yaml` (`domains.execution_position.exposure_guard.*`); з `trading.execution.exposure.*` використовуються лише прапорці `count_pending_orders` / `exclude_reduce_only`. (`apps/reference/domains/execution_position/exposure_guard.py:101`)
- **Alias `config.execution` → `config.trading.execution`:** частина коду читає `execution.*` через root alias (Pydantic back-compat). (`apps/reference/config_models.py:3061`)
- **`trading.execution.orders.default_ttl_seconds` зараз не застосовується:** ExecPosFSM читає `trading.orders.default_ttl_seconds` або root `orders.default_ttl_seconds`, а не `trading.execution.orders.*`. (`apps/reference/domains/execution_position/fsm.py:372`)
- **`trading.market_data.websocket_streams` ігнорується:** конектори/воркер підписуються на `bookTicker` + `aggTrade` жорстко. (`apps/reference/domains/market_data/market_data_connector.py:99`, `apps/reference/domains/market_data/worker.py:277`)
- **Panic switch:** `trading.ops.panic_killswitch=true` блокує всі нові `CMD:OPEN`. (`apps/reference/domains/execution_position/fsm_open.py:267`)

---

### `binance_api.live.api_key`
- **Type:** `string` *(env var reference)*
- **Logic Owner:** `config_loader` → `binance_adapter` / `market_data` / `execution_position` / `account_balance`
- **Code Reference:** `apps/reference/config_loader.py:551` (func: `_validate_config`); `apps/reference/domains/market_data/market_data_connector.py:106` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:1794` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > API ключ для ініціалізації `BinanceAdapter` (REST). У live-like режимах відсутність ключа → fail-fast на старті або деградація виконання (shadow mode) в `execution_position`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)* (секрет/рядок).
    - 🔽 **Too Low:** Порожнє/None → неможливо створити адаптер для live; у `ExecPosFSM` може ввімкнутись `shadow_mode=True` (симуляція замість відправки ордерів).
- **Invariant/Constraints:** Не зберігати в репо; резолвиться через `${ENV}`; required для `live`/`hybrid_live_data_testnet_exec`.

---

### `binance_api.live.api_secret`
- **Type:** `string` *(env var reference)*
- **Logic Owner:** `binance_adapter` / `market_data` / `execution_position` / `account_balance`
- **Code Reference:** `apps/reference/config_loader.py:553` (func: `_validate_config`); `apps/reference/domains/account_balance/account_connector.py:68` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:1796` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > API secret для HMAC підпису запитів у `BinanceAdapter`. Відсутність → неможлива авторизація, fail-fast або деградація в shadow-mode.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Порожнє/None → відмова у запуску live-like доменів або симуляція виконання.
- **Invariant/Constraints:** Секрет; не логувати; required у live-like режимах.

---

### `binance_api.live.rest_url`
- **Type:** `string` *(URL)*
- **Logic Owner:** `binance_adapter`
- **Code Reference:** `apps/reference/domains/market_data/market_data_connector.py:110` (func: `__init__`); `apps/reference/domains/account_balance/account_connector.py:70` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Base URL для REST запитів Binance Futures (live). Впливає на всі REST-dependent операції (баланс/позиції/ордери/валидація фільтрів).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Неправильний endpoint → систематичні помилки мережі/HTTP, ризик fail-fast або деградації функцій.
    - 🔽 **Too Low:** Порожнє/None → fail-closed на старті в live-like сценаріях.
- **Invariant/Constraints:** Має бути валідним URL для Binance Futures REST (live).

---

### `binance_api.testnet.api_key`
- **Type:** `string` *(env var reference)*
- **Logic Owner:** `binance_adapter` / `execution_position` / `account_balance`
- **Code Reference:** `apps/reference/main.py:809` (func: `main`); `apps/reference/domains/account_balance/account_connector.py:62` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:1789` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > API ключ для TESTNET виконання (і для hybrid execution). Використовується для REST доступу до testnet-акаунта.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Порожнє/None → execution/account домени не зможуть працювати з testnet (можливий shadow-mode у `ExecPosFSM`).
- **Invariant/Constraints:** Secret via `${ENV}`; required для `testnet` і hybrid execution.

---

### `binance_api.testnet.api_secret`
- **Type:** `string` *(env var reference)*
- **Logic Owner:** `binance_adapter` / `execution_position` / `account_balance`
- **Code Reference:** `apps/reference/domains/account_balance/account_connector.py:69` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:1797` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > API secret для testnet, необхідний для авторизації/підпису запитів.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Порожнє/None → testnet REST недоступний (fail-closed або shadow).
- **Invariant/Constraints:** Secret via `${ENV}`.

---

### `binance_api.testnet.rest_url`
- **Type:** `string` *(URL)*
- **Logic Owner:** `binance_adapter`
- **Code Reference:** `apps/reference/domains/account_balance/account_connector.py:70` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:1798` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > Base URL для Binance Futures TESTNET REST. Визначає, куди піде фактичне виконання/читання testnet позицій.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Невірний URL → помилки мережі/HTTP, виконання/баланс не працюють.
    - 🔽 **Too Low:** Порожнє/None → fail-closed або `shadow_mode=True`.
- **Invariant/Constraints:** Має бути валідним testnet endpoint (у файлі задано `https://testnet.binancefuture.com`).

---

### `trading.mode`
- **Type:** `string` *(enum-ish: `backtest|testnet|production|live|hybrid_live_data_testnet_exec`)*
- **Logic Owner:** `config_loader` / `main` / `decision_making` / `execution_position`
- **Code Reference:** `apps/reference/config_loader.py:951` (func: `load_config`); `apps/reference/config_models.py:3051` (validator: `validate_trading_mode_consistency`); `apps/reference/domains/decision_making/decision_making.py:3888` (func: `_check_and_emit_risk_gate_alert`); `apps/reference/domains/execution_position/fsm.py:1774` (func: `_initialize_adapter`)
- **Mathematical/Architectural Role:**
    > Глобальний режим *поведінки* runtime. Використовується для:
    > - **backtest safety:** якщо `trading.mode=backtest`, loader форсує root `trading_mode=backtest` (запобігає випадковому live/testnet виконанню).  
    > - **alert thresholds:** DM обирає пороги алерту для risk-gate залежно від `trading.mode` (testnet vs production).  
    > - **execution adapter mode:** `ExecPosFSM` використовує `trading.mode` як fallback для вибору `binance_api.live|testnet`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Перехід у live-like режими збільшує blast radius: реальні API виклики/жорсткіші fail-closed вимоги.
    - 🔽 **Too Low:** `backtest` перехоплює `main()` і не запускає live runtime; `testnet` знижує ризик, але відрізняється мікроструктурою (fill/latency).
- **Invariant/Constraints:** Має бути узгоджений з root `trading_mode` (Pydantic синхронізує значення). (`apps/reference/config_models.py:3051`)

---

### `trading.backtest.start_date`
- **Type:** `string` *(YYYY-MM-DD)*
- **Logic Owner:** `main` / `backtest_engine`
- **Code Reference:** `apps/reference/main.py:482` (func: `run_backtest_simulation`)
- **Mathematical/Architectural Role:**
    > Початок історичного вікна для backtest. Парситься як `datetime.strptime(..., "%Y-%m-%d")` і передається у `BacktestEngine`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Пізніший старт → менше даних, менше сигналів/угод, ризик неповного warmup.
    - 🔽 **Too Low:** Ранніший старт → довший прогін, більше часу/ресурсів.
- **Invariant/Constraints:** Формат строго `%Y-%m-%d`; інакше процес завершується (`sys.exit(1)`). (`apps/reference/main.py:489`)

---

### `trading.backtest.end_date`
- **Type:** `string` *(YYYY-MM-DD)*
- **Logic Owner:** `main` / `backtest_engine`
- **Code Reference:** `apps/reference/main.py:486` (func: `run_backtest_simulation`)
- **Mathematical/Architectural Role:**
    > Кінець історичного вікна для backtest.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Пізніший end → довший прогін.
    - 🔽 **Too Low:** Ранніший end → коротший прогін, можливий недобір статистики.
- **Invariant/Constraints:** Формат `%Y-%m-%d`; `end_date` має бути >= `start_date` (інакше backtest логічно некоректний; код явно не перевіряє, але engine може).

---

### `trading.backtest.initial_balance`
- **Type:** `float` *(USDT)*
- **Logic Owner:** `backtest_engine`
- **Code Reference:** `apps/reference/main.py:487` (func: `run_backtest_simulation`)
- **Mathematical/Architectural Role:**
    > Початковий капітал backtest-симуляції (equity/balance baseline).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший капітал → більші абсолютні розміри позицій при fixed-fraction правилах.
    - 🔽 **Too Low:** Менший капітал → більше відмов по `min_notional`/мінімальних лотах; тест може стати “без угод”.
- **Invariant/Constraints:** `> 0`.

---

### `trading.tca_prefs.max_slippage_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making` (TCA metadata)
- **Code Reference:** `apps/reference/config_models.py:2672` (model: `TCAPrefsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не має runtime-споживача**: в `TradeIntent` і downstream читається `max_slippage_bps`, а не `max_slippage_pct`. Поле збережене як типізована частина `tca_prefs`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Тримати узгодженим з `max_slippage_bps` (10 bps = 0.10%) якщо поле використають пізніше.

---

### `trading.tca_prefs.max_slippage_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `decision_making` → `execution_position` (metadata/logging)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3109` (func: `_propose_trade_intent`); `apps/reference/domains/execution_position/fsm.py:1223` (func: `_on_trade_intent_proposed`)
- **Mathematical/Architectural Role:**
    > У поточному коді використовується як **TCA бюджет-метадані** у `TradeIntent` (`tca_budget.max_slippage_bps`).  
    > `ExecPosFSM` витягує значення й логгує для форензіки, але **не застосовує** його як hard gate/price transform.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менше “самоконтролю” в metadata; якщо пізніше буде enforcement — дозволить більший допуск на slippage.
    - 🔽 **Too Low:** Якщо пізніше буде enforcement — часті блокування/відхилення як “занадто далеко від price_ref”.
- **Invariant/Constraints:** `>= 0`. Якщо вводити enforcement — трактувати як bps (÷10000).

---

### `trading.tca_prefs.max_latency_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `decision_making` → `execution_position` (metadata/logging)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3114` (func: `_propose_trade_intent`); `apps/reference/domains/execution_position/fsm.py:1224` (func: `_on_trade_intent_proposed`)
- **Mathematical/Architectural Role:**
    > Декларує допустиму latency (intent→fill) як metadata у `tca_budget.max_latency_ms`.  
    > У поточному `execution_position` **немає** enforcement (тільки логування).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі mostly N/A)*; якщо додадуть enforcement — буде менш чутливим до затримок.
    - 🔽 **Too Low:** *(Наразі mostly N/A)*; якщо додадуть enforcement — часті abort/timeout.
- **Invariant/Constraints:** `> 0` рекомендовано; узгодити з watchdog TTL (див. `trading.execution.watchdog.*`).

---

### `trading.tca_prefs.maker_preference`
- **Type:** `string` *(enum: `maker|taker|neutral|any`)*
- **Logic Owner:** `decision_making` → `execution_position` (metadata/logging)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3116` (func: `_propose_trade_intent`); `apps/reference/domains/execution_position/fsm.py:1225` (func: `_on_trade_intent_proposed`)
- **Mathematical/Architectural Role:**
    > Перевага типу виконання (maker/taker) як metadata (`tca_budget.maker_preference`). Наразі **не змінює** order_type/tif у `ExecPosFSM`; order policy береться зі strategy execution policy. (`apps/reference/domains/decision_making/decision_making.py:3130`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Має бути з allowlist Pydantic, інакше `ValidationError`. (`apps/reference/config_models.py:2675`)

---

### `trading.tca_prefs.preferred_venue`
- **Type:** `string`
- **Logic Owner:** `decision_making` (TCA metadata)
- **Code Reference:** `apps/reference/config_models.py:2679` (model: `TCAPrefsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не використовується** в routing/виборі адаптера (система фактично “single-venue”). Поле збережене як частина typed TCA prefs.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Рядок; рекомендовано тримати як “binance” доки не з’явиться multi-venue router.

---

### `trading.tca_prefs.execution_priority`
- **Type:** `string` *(enum: `speed|price|balanced`)*
- **Logic Owner:** `decision_making` (policy placeholder)
- **Code Reference:** `apps/reference/config_models.py:2680` (model: `TCAPrefsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не має runtime-споживача**: рішення `LIMIT/MARKET` формується через per-strategy execution policy, а не через `execution_priority`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Валідне значення з allowlist, інакше fail-fast.

---

### `trading.risk_budgets.trade_cvar95_max_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `decision_making` (intent metadata / risk budget)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3124` (func: `_propose_trade_intent`)
- **Mathematical/Architectural Role:**
    > Входить у `TradeIntent.risk_budget.trade_cvar95_max_bps` як **metadata**. Наразі не є hard gate у `execution_position`; використання очікується у risk-aware sizing/filtration.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менш консервативний бюджет ризику на угоду (якщо додадуть enforcement).
    - 🔽 **Too Low:** Більше блокувань/зменшень сайзу (якщо додадуть enforcement).
- **Invariant/Constraints:** `>= 0`. Typed config: missing/None → DM блокує intent (fail-closed). (`apps/reference/domains/decision_making/decision_making.py:3127`)

---

### `trading.risk_budgets.session_cvar95_max_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `decision_making` (intent metadata / risk budget)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3125` (func: `_propose_trade_intent`)
- **Mathematical/Architectural Role:**
    > Входить у `TradeIntent.risk_budget.session_cvar95_max_bps` як metadata.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволить більший “session risk” (якщо буде enforcement).
    - 🔽 **Too Low:** Часті early-stop/блокування впродовж сесії (якщо буде enforcement).
- **Invariant/Constraints:** `>= 0`; missing → fail-closed (DM не емітить intent).

---

### `trading.risk_budgets.max_portfolio_risk_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making` (future budgeting)
- **Code Reference:** `apps/reference/config_models.py:2693` (model: `RiskBudgetsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не використовується** у формулах/гейтах (в DM беруться лише CVaR поля). Поле зарезервовано для майбутнього portfolio-risk budgeting.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Typed поле; має бути присутнім у YAML (інакше ValidationError при завантаженні).

---

### `trading.risk_budgets.max_single_position_risk_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making` (future budgeting)
- **Code Reference:** `apps/reference/config_models.py:2694` (model: `RiskBudgetsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не використовується** у runtime-логіці; зарезервовано під per-position budgeting.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Typed поле, required.

---

### `trading.risk_budgets.max_daily_loss_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making` (future budgeting) / `risk_management` (conceptually)
- **Code Reference:** `apps/reference/config_models.py:2695` (model: `RiskBudgetsConfig`)
- **Mathematical/Architectural Role:**
    > Наразі **не підключено** до daily gate: daily gate читає `trading.risk.daily.max_drawdown_pct`, а не `risk_budgets.max_daily_loss_pct`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Typed поле, required.

---

### `trading.risk.max_daily_drawdown_limit`
- **Type:** `float`
- **Logic Owner:** legacy `trading.risk` (no active owner)
- **Code Reference:** `apps/reference/domains/risk_management/daily_gate.py:92` (reads only `risk.daily.*`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Daily gate використовує `trading.risk.daily.max_drawdown_pct`; це поле не читається у `risk_management`/`execution_position`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Рекомендовано прибрати або перенести в SSOT, щоб уникнути “двох правд”.

---

### `trading.risk.score_weights.delta_price`
- **Type:** `float`
- **Logic Owner:** legacy (заміщено `domains.risk_management.risk_score_weights`)
- **Code Reference:** `apps/reference/domains/risk_management/risk_management.py:523` (func: `_get_risk_score_weights`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** RiskManagement бере ваги risk score з `config.domains.risk_management.risk_score_weights`, а не з `trading.risk.score_weights`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Якщо потрібні ваги — змінювати `domains.yaml`, не `trading.yaml`.

---

### `trading.risk.score_weights.obi`
- **Type:** `float`
- **Logic Owner:** legacy (заміщено `domains.risk_management.risk_score_weights`)
- **Code Reference:** `apps/reference/domains/risk_management/risk_management.py:523` (func: `_get_risk_score_weights`)
- **Mathematical/Architectural Role:**
    > **Не використовується**; SSOT ваги в `domains.yaml`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. `domains.risk_management.risk_score_weights.obi`.

---

### `trading.risk.score_weights.tfi`
- **Type:** `float`
- **Logic Owner:** legacy
- **Code Reference:** `apps/reference/domains/risk_management/risk_management.py:523` (func: `_get_risk_score_weights`)
- **Mathematical/Architectural Role:**
    > **Не використовується**; SSOT ваги в `domains.yaml`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. `domains.risk_management.risk_score_weights.tfi`.

---

### `trading.risk.score_weights.absorption_inverse`
- **Type:** `float`
- **Logic Owner:** legacy
- **Code Reference:** `apps/reference/domains/risk_management/risk_management.py:523` (func: `_get_risk_score_weights`)
- **Mathematical/Architectural Role:**
    > **Не використовується**; SSOT ваги в `domains.yaml`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. `domains.risk_management.risk_score_weights.absorption_inverse`.

---

### `trading.risk.testnet.max_risk_score`
- **Type:** `float`
- **Logic Owner:** `config_loader` (legacy mode overrides)
- **Code Reference:** `apps/reference/config_loader.py:524` (func: `_resolve_mode_overrides`)
- **Mathematical/Architectural Role:**
    > Loader читає `trading.risk.<mode>.*` і копіює значення в `trading.risk.trading_allowed_thresholds.*` для legacy risk gates.  
    > **Важливо:** актуальний runtime risk gate використовує `domains.risk_management.trading_allowed_thresholds.max_risk_score`, тож цей ключ може не впливати на торгівлю.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Ймовірно N/A для runtime gate)*; якщо legacy gate буде підключено — дозволить більший risk_score.
    - 🔽 **Too Low:** *(Ймовірно N/A)*; потенційно більше блокувань.
- **Invariant/Constraints:** Тримати узгодженим із SSOT у `domains.yaml`, або видалити legacy блоки.

---

### `trading.risk.production.max_risk_score`
- **Type:** `float`
- **Logic Owner:** `config_loader` (legacy mode overrides)
- **Code Reference:** `apps/reference/config_loader.py:524` (func: `_resolve_mode_overrides`)
- **Mathematical/Architectural Role:**
    > Аналогічно `testnet.max_risk_score`, але для mode=`production`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Потенційно менш суворий legacy gate.
    - 🔽 **Too Low:** Потенційно більш суворий legacy gate.
- **Invariant/Constraints:** Узгоджувати з `domains.risk_management.trading_allowed_thresholds.max_risk_score`.

---

### `trading.risk.trading_allowed_thresholds.max_risk_score`
- **Type:** `float`
- **Logic Owner:** legacy thresholds (loader-mutated)
- **Code Reference:** `apps/reference/config_loader.py:531` (func: `_resolve_mode_overrides`)
- **Mathematical/Architectural Role:**
    > Loader інжектить/оновлює цей поріг як “результат” `risk.<mode>` overrides.  
    > **Runtime gate фактично читає інший SSOT** (`domains.risk_management...`), тому значення може бути чисто документальним.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Не плутати з `domains.risk_management.trading_allowed_thresholds.max_risk_score` (канонічний).

---

### `trading.risk.daily.enabled`
- **Type:** `bool`
- **Logic Owner:** `risk_management` (DailyRiskState)
- **Code Reference:** `apps/reference/domains/risk_management/daily_gate.py:94` (class: `DailyRiskState`)
- **Mathematical/Architectural Role:**
    > Глобальний перемикач daily gate. Якщо `false` → `can_open()` повертає allow і не блокує нові відкриття. Якщо `true` → активуються fail-closed перевірки по equity/drawdown.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → додає жорсткий портфельний gate на відкриття.
    - 🔽 **Too Low:** `false` → вимикає daily gate повністю (ризик невиявленої просадки).
- **Invariant/Constraints:** Поле **required**: якщо відсутнє → `ConfigContractError` (fail-closed). (`apps/reference/domains/risk_management/daily_gate.py:95`)

---

### `trading.risk.daily.max_realized_loss_usd`
- **Type:** `float` *(USD/USDT)*
- **Logic Owner:** legacy daily-loss config
- **Code Reference:** `apps/reference/domains/risk_management/daily_gate.py:102` (reads `max_dd`/`reset_time`, not realized loss)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Поточний daily gate реалізує тільки drawdown від `equity_open`, без ліміту по realized PnL.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Якщо потрібен realized-loss gate — додати в `DailyRiskState` і визначити джерело realized PnL.

---

### `trading.risk.daily.max_drawdown_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `risk_management` (DailyRiskState)
- **Code Reference:** `apps/reference/domains/risk_management/daily_gate.py:103` (init); `apps/reference/domains/risk_management/daily_gate.py:262` (func: `can_open`)
- **Mathematical/Architectural Role:**
    > Поріг блокування нових відкриттів за intraday drawdown:  
    > `dd_pct = (1 - equity_now / equity_open) * 100` і якщо `dd_pct >= max_drawdown_pct` → `can_open=False` (fail-closed).  
    > **Це hard stop для нових OPEN**, не механізм примусового закриття позицій.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволяє більшу просадку до блокування; менше “вибивання”, але більший tail risk.
    - 🔽 **Too Low:** Ранні блокування при звичайній волатильності; ризик частих зупинок торгівлі.
- **Invariant/Constraints:** Має бути `>= 0`. Якщо gate увімкнено, поле required (інакше fail-closed). (`apps/reference/domains/risk_management/daily_gate.py:107`)

---

### `trading.risk.daily.reset_time_utc`
- **Type:** `string` *(HH:MM UTC)*
- **Logic Owner:** `risk_management` (DailyRiskState)
- **Code Reference:** `apps/reference/domains/risk_management/daily_gate.py:104` (init); `apps/reference/domains/risk_management/daily_gate.py:151` (func: `_active_trading_date`)
- **Mathematical/Architectural Role:**
    > Визначає момент “перезапуску” trading day (UTC). До reset-time активна дата вважається “вчорашньою”, після — “сьогоднішньою”; це впливає на те, коли `equity_open` переякорюється.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Пізніший reset (наприклад 23:00) → довший “день” з точки зору gate; можливі несподівані блокування до reset.
    - 🔽 **Too Low:** Ранніший reset → частіше переякорення `equity_open`, потенційно менше шансів накопичити drawdown до ліміту.
- **Invariant/Constraints:** Має бути у форматі `HH:MM`. Якщо gate увімкнено — required.

---

### `trading.risk.profile`
- **Type:** `string`
- **Logic Owner:** legacy risk profile
- **Code Reference:** `apps/reference/domains/execution_position/exposure_guard.py:111` (reads only `soft_limits`/`regime_adaptation`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Профіль не використовується в гейтах/формулах (ані в RiskManagement, ані в Execution).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Уникати “профільних” ключів без резольвера; інакше це конфіг-шум.

---

### `trading.risk.soft_limits.mode`
- **Type:** `string` *(enum: `clip` | `reject`)*
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:71` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/exposure_guard.py:611` (func: `_check_exposure_fail_closed`)
- **Mathematical/Architectural Role:**
    > Режим реакції на soft-limit:
    > - `clip`: якщо `clipped_notional < requested` → зменшує notional до `clipped_notional`;
    > - `reject`: якщо потрібно clip → блокує трейд (`SOFT_LIMIT_REJECT`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `reject` (більш суворо) → більше відхилень, менше trade-through лімітів.
    - 🔽 **Too Low:** `clip` → більше шансів виконати, але з меншим сайзом (може спотворити risk/return очікування).
- **Invariant/Constraints:** Має бути одним із `clip|reject`; інші значення фактично вимикають soft-limit гілку (бо код перевіряє membership у `{clip,reject}`).

---

### `trading.risk.soft_limits.clip_min_notional_usdt`
- **Type:** `int|float` *(USDT)*
- **Logic Owner:** `execution_position` (SoftClipEngine)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:73` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/soft_clip.py:214` (func: `calculate_clipped_size`)
- **Mathematical/Architectural Role:**
    > Мінімальний notional після clipping: якщо `clipped_notional < clip_min_notional_usdt` → `allowed=False` (`BELOW_CLIP_MIN`) і ордер блокується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше блокувань малих угод після clip; менше “пилу”, але ризик втрати дрібних сигналів.
    - 🔽 **Too Low:** Дозволяє дрібні clipped-угоди; ризик впертися у exchange `min_notional` або економічно безглузді трейди.
- **Invariant/Constraints:** `> 0`. Не замінює біржові `min_notional` (вони в instruments/exchange_filters).

---

### `trading.risk.soft_limits.directional_ratio_max`
- **Type:** `float`
- **Logic Owner:** `execution_position` (SoftClipEngine + Regime Adaptation)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:74` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/soft_clip.py:195` (func: `calculate_clipped_size`); `apps/reference/domains/execution_position/exposure_guard.py:1008` (func: `on_regime_changed`)
- **Mathematical/Architectural Role:**
    > Soft-limit “на перекіс” (long vs short) у margin-термінах. У спрощеній реалізації:  
    > - рахується `ratio = max(new_long_margin, new_short_margin) / min(...)`;  
    > - якщо `ratio > directional_ratio_max` → `delta_dir_notional = 0` (тобто clip до 0).  
    > Значення також модифікується через `regime_adaptation` (див. нижче).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволяє сильніший перекіс у напрямок (більший directional exposure).
    - 🔽 **Too Low:** Часті `DIRECTIONAL_RATIO_EXCEEDED` → clip/reject; менше directional risk, але більше пропущених сигналів.
- **Invariant/Constraints:** `> 1` (інакше ratio майже завжди порушений). Рекомендовано задавати разом із bounds у regime_adaptation.

---

### `trading.risk.soft_limits.side_exposure_usdt`
- **Type:** `int|float` *(USDT margin limit, side-specific)*
- **Logic Owner:** `execution_position` (SoftClipEngine)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:75` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/soft_clip.py:176` (func: `calculate_clipped_size`)
- **Mathematical/Architectural Role:**
    > Soft limit на margin exposure по стороні (BUY vs SELL).  
    > Для нового ордера: `allowed_extra_side = side_limit - current_side_margin`, `delta_side_notional = allowed_extra_side * leverage`, і далі clip до мінімуму з дельт.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволяє більше одностороннього ризику (перекіс портфеля).
    - 🔽 **Too Low:** Часті clip/reject при активних трендах; менше directional bet.
- **Invariant/Constraints:** `>= 0`. Має бути узгоджено з leverage та `margin_exposure_usdt`.

---

### `trading.risk.soft_limits.margin_exposure_usdt`
- **Type:** `int|float` *(USDT margin limit, total)*
- **Logic Owner:** `execution_position` (SoftClipEngine)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:76` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/soft_clip.py:165` (func: `calculate_clipped_size`)
- **Mathematical/Architectural Role:**
    > Soft limit на сумарну margin exposure.  
    > `allowed_extra_margin = margin_limit - total_margin_exposure`, `delta_margin_notional = allowed_extra_margin * leverage`, далі clip.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволяє агресивніше використовувати маржу (більше позицій/сайз).
    - 🔽 **Too Low:** Часті `MARGIN_LIMIT_REACHED` → clip/reject; більш консервативно.
- **Invariant/Constraints:** `>= 0`. Для реальних лімітів SSOT — див. `domains.execution_position.exposure_guard.*`.

---

### `trading.risk.regime_adaptation.trend_up_delta`
- **Type:** `float` *(additive delta to directional_ratio_max)*
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:95` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/exposure_guard.py:989` (func: `on_regime_changed`)
- **Mathematical/Architectural Role:**
    > Дельта, що додається до базового `directional_ratio_max` у режимі `TREND_UP`:  
    > `new_ratio = clamp(bounds_min, base_ratio + trend_up_delta, bounds_max)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше дозволений directional перекіс у тренді вгору → агресивніше нарощення позицій.
    - 🔽 **Too Low:** Менше “підсилення” в тренді; більше clip/reject.
- **Invariant/Constraints:** Має бути узгоджено з `bounds` і базовим `directional_ratio_max`.

---

### `trading.risk.regime_adaptation.trend_down_delta`
- **Type:** `float`
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:96` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/exposure_guard.py:993` (func: `on_regime_changed`)
- **Mathematical/Architectural Role:**
    > Дельта для `TREND_DOWN`: `new_ratio = clamp(bounds_min, base_ratio + trend_down_delta, bounds_max)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше дозволений перекіс у тренді вниз (корисно для short-biased систем, але ризик).
    - 🔽 **Too Low:** Консервативніше при падінні; більше clip/reject.
- **Invariant/Constraints:** Узгоджувати з `bounds`.

---

### `trading.risk.regime_adaptation.flat_delta`
- **Type:** `float`
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:97` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/exposure_guard.py:995` (func: `on_regime_changed`)
- **Mathematical/Architectural Role:**
    > Дельта для консервативних bucket-ів (`FLAT`, `VOLATILE`, `UNCERTAIN`):  
    > `new_ratio = clamp(bounds_min, base_ratio + flat_delta, bounds_max)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менше “затягування паска” у flat/uncertain; більше directional risk.
    - 🔽 **Too Low:** Сильніше зменшення дозволеного перекосу в невизначених/волатильних режимах.
- **Invariant/Constraints:** Часто роблять від’ємним (tighten).

---

### `trading.risk.regime_adaptation.bounds`
- **Type:** `list[float]` *(2 elements: min,max)*
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/soft_clip.py:98` (func: `load_soft_limit_config`); `apps/reference/domains/execution_position/exposure_guard.py:986` (func: `on_regime_changed`)
- **Mathematical/Architectural Role:**
    > Межі clamp для `directional_ratio_max` після застосування delta: `[min_ratio, max_ratio]`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий `max` → допускає екстремальні directional перекоси.
    - 🔽 **Too Low:** Нижчий `max` або вищий `min` → частіше clip/reject, менше варіативності адаптації.
- **Invariant/Constraints:** Довжина списку = 2; `min <= max`; обидва > 0.

---

### `trading.risk.feature_flags.dynamic_ratio`
- **Type:** `bool`
- **Logic Owner:** legacy flag (unused)
- **Code Reference:** `apps/reference/domains/execution_position/exposure_guard.py:961` (func: `on_regime_changed` runs unconditionally when called)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Адаптація directional ratio працює через наявність `regime_adaptation`, не через цей feature flag.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Рекомендовано прибрати або реально підключити як gate.

---

### `trading.risk.feature_flags.clipping_enabled`
- **Type:** `bool`
- **Logic Owner:** legacy flag (unused)
- **Code Reference:** `apps/reference/domains/execution_position/exposure_guard.py:611` (soft-limit runs regardless)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Soft-limit механіка запускається за наявності `trading.risk.soft_limits.*`; цей прапорець не читається.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо потрібно enable/disable — додати перевірку цього прапорця у ExposureGuard.

---

### `trading.market_data.poll_interval_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `market_data`
- **Code Reference:** `apps/reference/domains/market_data/market_data_connector.py:98` (func: `__init__`); `apps/reference/domains/market_data/worker.py:160` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Інтервал polling/emit-loop для market data компонентів. У multiprocessing воркері використовується як `_poll_interval` (default 1 якщо ключа нема у dict).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідші апдейти → більший lag у фічах/рішенні; менше навантаження.
    - 🔽 **Too Low:** Часті апдейти → більше CPU/I/O, ризик backpressure у чергах і дропів.
- **Invariant/Constraints:** `> 0`. У воркері (dict path) відсутність дає default 1 (не fail-closed).

---

### `trading.market_data.websocket_streams`
- **Type:** `list[string]`
- **Logic Owner:** `market_data` (placeholder)
- **Code Reference:** `apps/reference/domains/market_data/market_data_connector.py:99` (func: `__init__`); `apps/reference/domains/market_data/worker.py:277` (func: `_make_subscribe_payload`)
- **Mathematical/Architectural Role:**
    > **Не використовується для фактичної підписки.** Конектори/воркер підписуються на `bookTicker` + `aggTrade` жорстко; поле існує як типізована частина `MarketDataConfig`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Список required у typed model (`MarketDataConfig`), але не має effect без зміни коду.

---

### `trading.market_data.use_multiprocessing`
- **Type:** `bool`
- **Logic Owner:** `main` / `market_data`
- **Code Reference:** `apps/reference/main.py:960` (func: `main`)
- **Mathematical/Architectural Role:**
    > Вибір архітектури market_data:
    > - `true` → `MarketDataProxy` (окремий процес-воркер, IPC queue);
    > - `false` → `MarketDataConnector` (legacy single-process).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → краща ізоляція/стабільність під навантаженням, але складніша IPC/дебаг.
    - 🔽 **Too Low:** `false` → простіший стек, але ризик блокувань main loop (особливо при I/O).
- **Invariant/Constraints:** Якщо `false`, `MarketDataConnector` використовує `get_domain_mode_from_mapping()` і може вимагати узгоджених режимів/креденціалів.

---

### `trading.market_data.macro_sync.enabled`
- **Type:** `bool`
- **Logic Owner:** `market_data` (typed config only)
- **Code Reference:** `apps/reference/config_models.py:944` (model: `MacroSyncConfig`); `apps/reference/domains/market_data/market_data_connector.py:91` (requires macro_sync presence)
- **Mathematical/Architectural Role:**
    > **Наразі не впливає на wiring.** Конектори перевіряють наявність `macro_sync` як секції, але не гейтять логіку за `enabled`; фактично використовуються лише `anchors`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → *(N/A)*.
    - 🔽 **Too Low:** `false` → *(N/A)* (секція все одно потрібна в `MarketDataConnector`).
- **Invariant/Constraints:** Поле required у typed config; не плутати з `domains.feature_engineering.macro_sync.enabled` (інший SSOT).

---

### `trading.market_data.macro_sync.anchors`
- **Type:** `list[string]` *(symbols)*
- **Logic Owner:** `market_data`
- **Code Reference:** `apps/reference/domains/market_data/market_data_connector.py:95` (func: `__init__`); `apps/reference/domains/market_data/worker.py:159` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Список “anchor” символів, які market_data підписує/трекає для макро-узгодження (кореляційні/еталонні рухи). Використовується у `WebSocketAggregator` як `anchors=...`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше анкорів → більше WS streams/даних → більше навантаження і ймовірність lag/backpressure.
    - 🔽 **Too Low:** Менше анкорів → менше макро-контексту для downstream фіч.
- **Invariant/Constraints:** Має містити валідні символи; бажано включати ключові “market anchors” (BTCUSDT, ETHUSDT).

---

### `trading.market_data.macro_sync.window`
- **Type:** `int` *(seconds)*
- **Logic Owner:** market_data (placeholder)
- **Code Reference:** `apps/reference/config_models.py:946` (model: `MacroSyncConfig`); `apps/reference/domains/market_data/market_data_connector.py:123` (WebSocketAggregator uses hardcoded `window_seconds=60`)
- **Mathematical/Architectural Role:**
    > **Не використовується у market_data runtime:** `WebSocketAggregator` ініціалізується з `window_seconds=60` жорстко. Поле зарезервоване/типізоване, але не підключене.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Якщо потрібне — прокинути `macro_sync.window` у `WebSocketAggregator(..., window_seconds=...)`.

---

### `trading.market_data.macro_sync.emit_abs`
- **Type:** `bool`
- **Logic Owner:** placeholder (deprecated)
- **Code Reference:** `apps/reference/config_models.py:947` (model: `MacroSyncConfig`)
- **Mathematical/Architectural Role:**
    > Поле позначене як DEPRECATED у typed config; **runtime consumer не знайдено**.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Рекомендовано видалити або реалізувати явно.

---

### `trading.market_data.macro_sync.align_mode`
- **Type:** `string`
- **Logic Owner:** placeholder (planned alignment mode)
- **Code Reference:** `apps/reference/config_models.py:950` (model: `MacroSyncConfig`)
- **Mathematical/Architectural Role:**
    > **Не використовується** у market_data домені. Реальна логіка alignment для macro features належить `feature_engineering` і конфігурується в `domains.yaml`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Тримати узгодженим зі SSOT `domains.feature_engineering.macro_sync.align_mode` (якщо присутній).

---

### `trading.market_data.macro_sync.min_buffer_size`
- **Type:** `int`
- **Logic Owner:** placeholder
- **Code Reference:** `apps/reference/config_models.py:951` (model: `MacroSyncConfig`)
- **Mathematical/Architectural Role:**
    > **Не використовується** у market_data runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо реалізовувати — це має бути ≥2 і узгоджено з window.

---

### `trading.market_data.macro_sync.time_diff_threshold_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** placeholder
- **Code Reference:** `apps/reference/config_models.py:952` (model: `MacroSyncConfig`)
- **Mathematical/Architectural Role:**
    > **Не використовується** у market_data runtime; аналогічна семантика є в feature_engineering macro_sync, але це інший конфіг.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має бути `>= 0` якщо буде підключено.

---

### `trading.market_data.macro_sync.anchor_update_from_ticks`
- **Type:** `bool`
- **Logic Owner:** placeholder
- **Code Reference:** `apps/reference/config_models.py:953` (model: `MacroSyncConfig`)
- **Mathematical/Architectural Role:**
    > **Не використовується** у market_data runtime. Anchor updates у поточній архітектурі робляться через WS streams та/або події.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо вмикати — визначити джерело “ticks” і порядок пріоритетів з `EVT:ANCHOR_UPDATED`.

---

### `trading.market_data.bar_aggregator.enabled`
- **Type:** `bool`
- **Logic Owner:** `main` / `market_data` (BarAggregator observer)
- **Code Reference:** `apps/reference/main.py:985` (func: `main`)
- **Mathematical/Architectural Role:**
    > Якщо `true`, `main` створює `BarAggregator`, підписує його на `EVT:MARKET_TICK_RECEIVED` і він починає емітити `EVT:BAR_CLOSED` для заданих таймфреймів.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → більше CPU/пам’яті на агрегацію барів, але стабільніша база для стратегій/режимів.
    - 🔽 **Too Low:** `false` → немає `EVT:BAR_CLOSED`; домени, що очікують бари, можуть деградувати/не мати даних.
- **Invariant/Constraints:** Якщо enabled, `timeframes_sec` має бути непорожнім (інакше буде fallback у `main`). (`apps/reference/main.py:994`)

---

### `trading.market_data.bar_aggregator.timeframes_sec`
- **Type:** `list[int]` *(seconds)*
- **Logic Owner:** `market_data` (BarAggregator)
- **Code Reference:** `apps/reference/main.py:993` (func: `main`); `apps/reference/domains/market_data/bar_aggregator.py:76` (class: `BarAggregator`)
- **Mathematical/Architectural Role:**
    > Список таймфреймів для агрегації тикових даних у OHLCV бари. Для кожного `tf_sec` бар закривається, коли минає інтервал, і емітиться `EVT:BAR_CLOSED`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші TF → менше барів/сигналів, більший lag, менше шуму.
    - 🔽 **Too Low:** Менші TF → більше барів і реактивності, але більше шуму й навантаження.
- **Invariant/Constraints:** Кожен `tf_sec > 0`, інакше `ValueError`. (`apps/reference/domains/market_data/bar_aggregator.py:81`)

---

### `trading.ops.panic_killswitch`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (OpenFlow gate)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_open.py:267` (func: `handle`)
- **Mathematical/Architectural Role:**
    > Fail-closed gate для `CMD:OPEN`: якщо `panic_killswitch=true`, `OpenFlowFSM` відхиляє відкриття з причиною `PANIC_KILLSWITCH`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → повна зупинка нових входів (але не обов’язково скасовує існуючі ордери/позиції).
    - 🔽 **Too Low:** `false` → торгівля дозволена, якщо інші гейти проходять.
- **Invariant/Constraints:** Має бути явним bool. Для аварійної зупинки — `true`.

---

### `trading.execution.manage.auto`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ManageFlowFSM)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:145` (func: `__init__`); `apps/reference/domains/execution_position/fsm_manage.py:385` (func: `handle`)
- **Mathematical/Architectural Role:**
    > Killswitch для auto-manage: якщо `false`, `ManageFlowFSM` не виконує автоматичні дії (брекети/трейлінг/таймаути) і емітить `EVT:MANAGE_SKIPPED`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → автоматичне керування позицією активне (TP/SL/захист).
    - 🔽 **Too Low:** `false` → позиції можуть залишитися без брекетів/захисту (потрібне ручне управління або інші механізми).
- **Invariant/Constraints:** У live-like режимі рекомендовано `true` для safety.

---

### `trading.execution.manage.brackets.oco_emulation`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ManageFlowFSM)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:1112` (func: `_handle_bracket_fill`)
- **Mathematical/Architectural Role:**
    > Увімкнення OCO емулювання: коли один із брекетів (SL/TP) виконується, інший скасовується (через `DEC:CANCEL_ORDER`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → зменшує ризик “лишніх” reduce-only ордерів після закриття (менше orphan orders).
    - 🔽 **Too Low:** `false` → після fill SL/TP інші брекети можуть залишитися відкритими (ризик зайвих cancel/cleanup процедур).
- **Invariant/Constraints:** Має бути узгоджено з біржовими можливостями (у Futures OCO для reduce-only не завжди доступне, тому емулювання корисне).

---

### `trading.execution.manage.brackets.offset_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position` (ManageFlowFSM safety offsets)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:633` (func: `_place_brackets`)
- **Mathematical/Architectural Role:**
    > Safety-offset для SL/TP перед відправкою (anti -2021):  
    > `offset = add_safety_offset(price, tick_size, offset_bps)` і далі ціна зсувається “подалі” від entry.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більші офсети → менше шансів exchange reject, але гірші ціни SL/TP (далі від бажаних рівнів).
    - 🔽 **Too Low:** Менші офсети → краща точність, але більший ризик помилок на кшталт “order would immediately trigger”.
- **Invariant/Constraints:** `>= 0`. Має бути узгоджено з tick_size (див. instruments SSOT).

---

### `trading.execution.manage.brackets.sl.fixed_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** legacy brackets defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:697` (model: `SLConfig`); `apps/reference/domains/execution_position/fsm_manage.py:781` (func: `_calculate_bracket_prices`)
- **Mathematical/Architectural Role:**
    > **No active consumer found for price calculation.** Поточний розрахунок SL/TP у `ManageFlowFSM` базується на:
    > 1) intent injection (з DM/стратегії), або
    > 2) per-instrument strategy config (`strategies.aurora.assets.<SYM>.exit.sl_pct`, etc.).  
    > `sl.fixed_bps` не використовується у цьому ланцюгу.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A у поточному runtime)*.
    - 🔽 **Too Low:** *(N/A у поточному runtime)*.
- **Invariant/Constraints:** Якщо хочете використовувати fixed_bps як fallback — потрібен явний код-resolver і пріоритети.

---

### `trading.execution.manage.brackets.tp.fixed_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** legacy brackets defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:703` (model: `TPConfig`); `apps/reference/domains/execution_position/fsm_manage.py:781` (func: `_calculate_bracket_prices`)
- **Mathematical/Architectural Role:**
    > Аналогічно `sl.fixed_bps`: **не використовується** для розрахунку TP у поточному runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Не плутати з per-instrument `take_profit` у strategy config (SSOT).

---

### `trading.execution.manage.orphan_monitor.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ExecPosFSM cleanup loop)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:868` (func: `_schedule_fsm_cleanup_loop`)
- **Mathematical/Architectural Role:**
    > Увімкнення periodic orphan cleanup loop (FSM-side): якщо `true`, `ExecPosFSM` може запускати `_cleanup_loop()` і викликати `order_guardian.cleanup_orphans()`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → більше safety (менше orphan orders), але більше фонового навантаження і cancel API.
    - 🔽 **Too Low:** `false` → ризик накопичення orphan brackets після збоїв/рестартів.
- **Invariant/Constraints:** Працює лише якщо є `OrderGuardian` і не заблоковано unified конфігом (див. `trading.execution.fsm_periodic_cleanup_enabled` + domains guardian unified).

---

### `trading.execution.manage.orphan_monitor.run_on_startup`
- **Type:** `bool`
- **Logic Owner:** orphan monitor (planned)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:267` (stores field; no further use found)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Значення зчитується в `_orphan_cfg`, але не використовується для запуску reconcile на старті (start reconcile робиться іншими шляхами).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо потрібна семантика “run once on startup” — додати явний виклик `cleanup_orphans()` у startup path.

---

### `trading.execution.manage.orphan_monitor.periodic_interval_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position` (FSM cleanup loop)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:4455` (func: `_cleanup_loop`)
- **Mathematical/Architectural Role:**
    > Період, з яким `_cleanup_loop()` викликає `order_guardian.cleanup_orphans()` (через `clock.sleep_sec(interval)`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідше cleanup → більше часу orphan ордерам “жити”.
    - 🔽 **Too Low:** Часті cleanup → більше cancel/REST навантаження і ризик rate limits.
- **Invariant/Constraints:** За схемою `>= 5`. (`apps/reference/config_models.py:747`)

---

### `trading.execution.manage.orphan_monitor.min_order_age_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** orphan monitor (planned)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:271` (stored; not used)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Не передається в `cleanup_orphans()` (там є `batch_limit`, але не age filter).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо додати фільтр — має бути `>= 0`.

---

### `trading.execution.manage.orphan_monitor.batch_cancel_limit`
- **Type:** `int`
- **Logic Owner:** orphan monitor (planned)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:272` (stored; not used); `apps/reference/services/order_guardian.py:695` (param: `batch_limit`, default 50)
- **Mathematical/Architectural Role:**
    > **Не підключено:** `OrderGuardian.cleanup_orphans()` підтримує `batch_limit`, але `ExecPosFSM` викликає його без аргументів.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Якщо підключити)* дозволить більше cancel за цикл.
    - 🔽 **Too Low:** *(Якщо підключити)* повільніше прибирання orphan.
- **Invariant/Constraints:** `>= 1`.

---

### `trading.execution.manage.orphan_monitor.rate_limit_per_min`
- **Type:** `int`
- **Logic Owner:** orphan monitor (planned)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:273` (stored; not used)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Rate limiting cleanup зараз не реалізовано через цей параметр.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** `>= 1` (якщо реалізовувати).

---

### `trading.execution.manage.emergency.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ManageFlowFSM emergency stop)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:1024` (func: `_check_rules`)
- **Mathematical/Architectural Role:**
    > Якщо `true`, ManageFlowFSM може активувати emergency STOP_MARKET при несприятливому русі ціни проти entry на `emergency_sl_bps` (і переходить у WAIT_MODE).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → сильніший захист від катастрофічних рухів, але ризик частих аварійних виходів на шумі.
    - 🔽 **Too Low:** `false` → немає emergency stop; покладаєтесь на звичайні SL/інструментальні правила.
- **Invariant/Constraints:** Якщо `true`, має бути коректно налаштовано `emergency_sl_bps` і `_bar_ms`/`wait_mode_bars` (інакше fail-closed у момент активації). (`apps/reference/domains/execution_position/fsm_manage.py:1049`)

---

### `trading.execution.manage.emergency.wait_mode_bars`
- **Type:** `int`
- **Logic Owner:** `execution_position` (ManageFlowFSM)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:122` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Кількість “барів” (за `_bar_ms`), протягом яких ManageFlow переходить у `WAIT_MODE` після emergency stop, щоб уникнути churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довше “охолодження” після аварії → менше повторних входів, але більше missed opportunities.
    - 🔽 **Too Low:** Швидше повернення → ризик повторних входів у небезпечному стані ринку.
- **Invariant/Constraints:** `>= 0`. Реальні одиниці залежать від `_bar_ms` (за замовчуванням 15m, або з `strategies.aurora.decision.bar_gating.bar_ms`). (`apps/reference/domains/execution_position/fsm_manage.py:116`)

---

### `trading.execution.manage.emergency.emergency_sl_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position` (ManageFlowFSM)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:1029` (func: `_check_rules`)
- **Mathematical/Architectural Role:**
    > Поріг adverse move для emergency stop:  
    > `adverse_bps = (adverse / entry_price) * 10000`; якщо `adverse_bps >= emergency_sl_bps` → емісія `STOP_MARKET` і `WAIT_MODE`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідше спрацьовує emergency stop (більший допуск на просадку).
    - 🔽 **Too Low:** Часті emergency exits (може “вибивати” на волатильності).
- **Invariant/Constraints:** `> 0`. Має бути узгоджено з основним SL (стратегічним) та інструментальними фільтрами.

---

### `trading.execution.fsm_periodic_cleanup_enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (FSM cleanup policy)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:299` (func: `__init__`); `apps/reference/domains/execution_position/fsm.py:872` (func: `_schedule_fsm_cleanup_loop`)
- **Mathematical/Architectural Role:**
    > Гейт для FSM-side cleanup loop. Якщо `guardian_unified=true` (SSOT у domains) і цей прапорець `false`, FSM cleanup блокується (cleanup делегується unified guardian).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → дозволяє додатковий FSM cleanup loop (може дублювати unified guardian).
    - 🔽 **Too Low:** `false` → зменшує дублювання, але якщо unified guardian не робить cleanup як очікується — orphan можуть жити довше.
- **Invariant/Constraints:** Використовується як `execution.fsm_periodic_cleanup_enabled` через root alias; переконатися, що `execution` alias активний. (`apps/reference/config_models.py:3066`)

---

### `trading.execution.cooldown_after_close_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position` (ExecPosFSM open guard)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:209` (init); `apps/reference/domains/execution_position/fsm.py:1899` (func: `handle`)
- **Mathematical/Architectural Role:**
    > Глобальний post-close cooldown: після будь-якого закриття позиції `ExecPosFSM` блокує нові `CMD:OPEN` на `cooldown_after_close_ms` (переводиться у секунди).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший cooldown → менше churn/“ping-pong”, але більша затримка ре-ентрі.
    - 🔽 **Too Low:** Менший cooldown → більше churn; ризик повторних входів у шумі.
- **Invariant/Constraints:** Required (fail-closed): відсутність поля → `ValueError` при старті FSM. (`apps/reference/domains/execution_position/fsm.py:209`)

---

### `trading.execution.anti_race_close_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position` (ManageFlowFSM anti-race)
- **Code Reference:** `apps/reference/domains/execution_position/fsm_manage.py:131` (func: `__init__`); `apps/reference/domains/execution_position/fsm_manage.py:538` (func: `_place_brackets`)
- **Mathematical/Architectural Role:**
    > Anti-race вікно: якщо позиція позначена як closing і `elapsed < anti_race_close_ms`, брекети/дії керування пропускаються, щоб уникнути гонок CLOSE↔BRACKETS.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше пропусків manage-дій після close signal → менше гонок, але ризик залишити позицію без оновлень.
    - 🔽 **Too Low:** Менше пропусків → більше шансів гонок і “phantom brackets”.
- **Invariant/Constraints:** `>= 0`. Required (fail-closed) у ManageFlowFSM. (`apps/reference/domains/execution_position/fsm_manage.py:138`)

---

### `trading.execution.fallback`
- **Type:** `object|null` *(FallbackConfig or null)*
- **Logic Owner:** `binance_adapter` (retry backoff)
- **Code Reference:** `apps/reference/adapters/binance_adapter.py:1706` (func: `_get_fallback_backoff_ms`)
- **Mathematical/Architectural Role:**
    > Налаштування backoff для fallback retry логіки в адаптері: читається `fallback.backoff_ms` (якщо є), інакше дефолт `[200, 500, 1000]`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довші backoff → менше RPS, більше latency на retries.
    - 🔽 **Too Low:** Коротші backoff → швидші retries, але більший ризик rate-limit/бурстів.
- **Invariant/Constraints:** Якщо задавати — `backoff_ms` має бути списком додатних int.

---

### `trading.execution.limit_orders`
- **Type:** `object|null`
- **Logic Owner:** `limit_order_monitor` *(service exists; wiring not found in main path)*
- **Code Reference:** `apps/reference/services/limit_order_monitor.py:93` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Зарезервована секція для LimitOrderMonitor (timeout/auto-cancel LIMIT).  
    > **У поточному runtime wiring цього сервісу не знайдено**, тож ключ не впливає на роботу, доки monitor не інстанціюють/не запустять.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A без wiring)*.
    - 🔽 **Too Low:** *(N/A без wiring)*.
- **Invariant/Constraints:** У typed схемі `LimitOrdersConfig` зараз не має полів (`extra='forbid'`), тому додавання підключів у YAML може зламати валідацію.

---

### `trading.execution.exposure.max_equity_utilization_pct`
- **Type:** `float`
- **Logic Owner:** legacy `trading.execution.exposure` (not used for hard limits)
- **Code Reference:** `apps/reference/config_models.py:774` (model: `ExposureConfig`); `apps/reference/domains/execution_position/exposure_guard.py:86` (hard limits come from `domains...`)
- **Mathematical/Architectural Role:**
    > **Не використовується** для hard enforcement. Реальний ліміт береться з `domains.execution_position.exposure_guard.max_equity_utilization_pct`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Щоб змінити hard limit — редагувати `domains.yaml`, не цей ключ.

---

### `trading.execution.exposure.max_portfolio_fraction`
- **Type:** `float`
- **Logic Owner:** legacy (not used)
- **Code Reference:** `apps/reference/config_models.py:775` (model: `ExposureConfig`); `apps/reference/domains/execution_position/exposure_guard.py:87` (SSOT is domains)
- **Mathematical/Architectural Role:**
    > **Не використовується**; SSOT: `domains.execution_position.exposure_guard.max_portfolio_fraction`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Не створювати “дві правди”.

---

### `trading.execution.exposure.max_directional_ratio`
- **Type:** `float`
- **Logic Owner:** legacy (not used)
- **Code Reference:** `apps/reference/config_models.py:777` (model: `ExposureConfig`); `apps/reference/domains/execution_position/exposure_guard.py:94` (SSOT is domains)
- **Mathematical/Architectural Role:**
    > **Не використовується** як hard directional ratio; hard ratio береться з `domains.execution_position.exposure_guard.max_directional_ratio`.  
    > Зверніть увагу: soft-limit directional ratio керується `trading.risk.soft_limits.directional_ratio_max`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Уникати плутанини hard vs soft directional ratio.

---

### `trading.execution.exposure.count_pending_orders`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/exposure_guard.py:108` (func: `__init__`); `apps/reference/domains/execution_position/exposure_guard.py:563` (func: `_check_exposure_fail_closed`)
- **Mathematical/Architectural Role:**
    > Якщо `true`, ExposureGuard включає pending orders у розрахунок експозиції (консервативніше). Якщо `false`, pending не враховуються.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → менше ризику oversubscription, але більше блокувань/clip при серіях ордерів.
    - 🔽 **Too Low:** `false` → ризик перевищити ліміти через “не враховані” pending.
- **Invariant/Constraints:** У live-like режимі зазвичай має бути `true`.

---

### `trading.execution.exposure.exclude_reduce_only`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (ExposureGuard)
- **Code Reference:** `apps/reference/domains/execution_position/exposure_guard.py:109` (func: `__init__`); `apps/reference/domains/execution_position/exposure_guard.py:565` (func: `_check_exposure_fail_closed`)
- **Mathematical/Architectural Role:**
    > Якщо `true`, reduce-only pending ордери **не** додаються до pending exposure (бо вони зменшують ризик, а не збільшують).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → менш консервативно щодо reduce-only, менше фальш-блокувань.
    - 🔽 **Too Low:** `false` → reduce-only рахується як ризик, що може блокувати legitimate exits/hedges.
- **Invariant/Constraints:** Рекомендовано `true`.

---

### `trading.execution.exposure.pending_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** legacy exposure config (unused)
- **Code Reference:** `apps/reference/config_models.py:779` (model: `ExposureConfig`); `apps/reference/domains/execution_position/exposure_guard.py:97` (TTL береться з domains)
- **Mathematical/Architectural Role:**
    > **Не використовується**. Pending TTL у hard guard береться з `domains.execution_position.exposure_guard.pending_ttl_sec`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Змінювати SSOT у `domains.yaml`.

---

### `trading.execution.exposure.post_fill_hold_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** legacy exposure config (unused)
- **Code Reference:** `apps/reference/config_models.py:781` (model: `ExposureConfig`); `apps/reference/domains/execution_position/exposure_guard.py:98` (TTL береться з domains)
- **Mathematical/Architectural Role:**
    > **Не використовується**. Post-fill hold TTL береться з `domains.execution_position.exposure_guard.post_fill_hold_ttl_sec`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Змінювати SSOT у `domains.yaml`.

---

### `trading.execution.exposure.leverage_defaults.BTCUSDT`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Значення не використовується для встановлення плеча в `LeverageService`/адаптері в поточному коді.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо потрібно керувати плечем — визначити SSOT (ймовірно instruments/strategy config) і додати wiring.

---

### `trading.execution.exposure.leverage_defaults.ETHUSDT`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** (див. також `__default__`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має бути >= 1 якщо колись буде використано.

---

### `trading.execution.exposure.leverage_defaults.SOLUSDT`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. leverage policy SSOT (якщо додасться).

---

### `trading.execution.exposure.leverage_defaults.XRPUSDT`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. leverage policy SSOT.

---

### `trading.execution.exposure.leverage_defaults.DOGEUSDT`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Див. leverage policy SSOT.

---

### `trading.execution.exposure.leverage_defaults.__default__`
- **Type:** `int`
- **Logic Owner:** legacy leverage defaults (unused)
- **Code Reference:** `apps/reference/config_models.py:783` (model: `ExposureConfig`)
- **Mathematical/Architectural Role:**
    > Default leverage для символів без явного ключа; **runtime consumer не знайдено**.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо використовувати — має бути >= 1 і узгоджено з exchange leverage limits.

---

### `trading.execution.order_params.LIMIT.timeInForce`
- **Type:** `string`
- **Logic Owner:** legacy order params (unused)
- **Code Reference:** `apps/reference/config_models.py:935` (field: `ExecutionConfig.order_params`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** ExecutionPosition формує payload ордера з intent/стратегії та не мержить `order_params` з конфіга.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо потрібні дефолти TIF/workingType — додати явний merge у адаптері/ExecPosFSM.

---

### `trading.execution.order_params.STOP_MARKET.workingType`
- **Type:** `string`
- **Logic Owner:** legacy order params (unused)
- **Code Reference:** `apps/reference/config_models.py:935` (field: `ExecutionConfig.order_params`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має відповідати Binance Futures `workingType` allowlist (MARK_PRICE/CONTRACT_PRICE).

---

### `trading.execution.order_params.TAKE_PROFIT_MARKET.workingType`
- **Type:** `string`
- **Logic Owner:** legacy order params (unused)
- **Code Reference:** `apps/reference/config_models.py:935`
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.**
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Як вище.

---

### `trading.execution.order_params.TRAILING_STOP_MARKET.callbackRate`
- **Type:** `string`
- **Logic Owner:** legacy order params (unused)
- **Code Reference:** `apps/reference/config_models.py:935`
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** CallbackRate для trailing не підключений у поточному execution path.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Якщо реалізовувати — Binance має ліміти callbackRate; тримати як число/строка за контрактом адаптера.

---

### `trading.execution.watchdog.ack_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position` (ExecPosFSM watchdog)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:352` (func: `__init__`); `apps/reference/domains/execution_position/watchdog.py:53` (class: `OrderTimeoutWatchdog`)
- **Mathematical/Architectural Role:**
    > TTL для ACK: якщо ордер не отримав `ORDER_ACK` до дедлайну, watchdog може ініціювати timeout-обробку (NRR-019 path).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довше чекати ACK → менше false timeouts, але повільніше виявлення “завислих” ордерів.
    - 🔽 **Too Low:** Часті ACK timeouts при лагу мережі/WS.
- **Invariant/Constraints:** `> 0`. ExecPosFSM fail-closed вимагає наявність поля у watchdog config. (`apps/reference/domains/execution_position/fsm.py:343`)

---

### `trading.execution.watchdog.fill_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position` (ExecPosFSM watchdog)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:353` (func: `__init__`); `apps/reference/domains/execution_position/watchdog.py:54` (class: `OrderTimeoutWatchdog`)
- **Mathematical/Architectural Role:**
    > TTL для fill: якщо ордер не заповнений до дедлайну — timeout path.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довше “терпіти” не-fill → більше шансів дочекатися, але більше “висячих” ордерів.
    - 🔽 **Too Low:** Більше timeout/cancel при нормальній волатильності та slow fills.
- **Invariant/Constraints:** `> 0`. Може бути перезаписано per-order `valid_for_ms` для LIMIT (див. DM).

---

### `trading.execution.watchdog.check_interval_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** watchdog (not wired from config)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:393` (watchdog constructed without config dict); `apps/reference/domains/execution_position/watchdog.py:55` (default param)
- **Mathematical/Architectural Role:**
    > **Не підключено до конфіга:** `OrderTimeoutWatchdog` підтримує `check_interval_ms`, але `ExecPosFSM` не передає config dict і не передає цей параметр, тож використовується дефолт з конструктора.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Якби було підключено)* рідші перевірки → повільніші timeouts.
    - 🔽 **Too Low:** *(Якби було підключено)* часті перевірки → більше CPU/async wakeups.
- **Invariant/Constraints:** Для реального effect потрібно прокинути параметр у `OrderTimeoutWatchdog(...)`.

---

### `trading.execution.watchdog.rps_limit`
- **Type:** `int` *(requests per second)*
- **Logic Owner:** watchdog REST polling (not wired from config)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:393` (config not passed); `apps/reference/domains/execution_position/watchdog.py:90` (uses config["rps_limit"] or default 10)
- **Mathematical/Architectural Role:**
    > Ліміт RPS для REST polling всередині watchdog. **Наразі не конфігурується з YAML**, бо config dict не передається при створенні watchdog.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Якби було підключено)* більше REST запитів/сек → швидше виявлення fills, але ризик rate limits.
    - 🔽 **Too Low:** *(Якби було підключено)* менше навантаження, але більший lag у детекції.
- **Invariant/Constraints:** `>= 1`.

---

### `trading.execution.orders.default_ttl_seconds`
- **Type:** `int` *(seconds)*
- **Logic Owner:** intended `execution_position` TTL override (currently miswired)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:372` (reads `trading.orders`, not `trading.execution.orders`)
- **Mathematical/Architectural Role:**
    > **Ймовірний конфіг-баг:** значення задане в `trading.execution.orders.default_ttl_seconds`, але ExecPosFSM читає `trading.orders.default_ttl_seconds` або root `orders.default_ttl_seconds`. У поточному вигляді це поле може бути **ігнороване**.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Якщо виправити wiring)* довший TTL → менше cancels на повільних fills.
    - 🔽 **Too Low:** *(Якщо виправити wiring)* коротший TTL → більше timeouts/cancels.
- **Invariant/Constraints:** `> 0`. Рекомендовано або перенести ключ у шлях, який читає код, або виправити читання в `fsm.py`.

---

### `trading.execution.preflight_backoff_ms`
- **Type:** `list[int]` *(milliseconds)*
- **Logic Owner:** `execution_position` (TP/SL preflight)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:4239` (func: `_preflight_position_check`)
- **Mathematical/Architectural Role:**
    > Експоненційний backoff для preflight перевірки позиції перед постановкою TP/SL після MARKET fill (REST lag).  
    > Цикл робить `sleep_ms(backoff_ms[i])` між спробами до вичерпання списку.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довші/більші backoff → менше шансів помилково пропустити брекети через лаг, але більший lag постановки TP/SL.
    - 🔽 **Too Low:** Коротші backoff → швидше, але більший ризик “позиція ще не з’явилась” → `TP_SL_SKIPPED_NO_POSITION`.
- **Invariant/Constraints:** Список додатних int; відсутність/порожній → fail-closed `ValueError`. (`apps/reference/domains/execution_position/fsm.py:4243`)

---

### `trading.execution.allow_trade_with_guardian_tidy_only`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (symbol tidy entry gate)
- **Code Reference:** `apps/reference/domains/execution_position/fsm.py:3554` (func: `_entry_tidy_gate_allow`)
- **Mathematical/Architectural Role:**
    > Якщо `true`, нові ENTRY дозволяються лише коли отримано недавній `EVT:SYMBOL_TIDY` (від OrderGuardian) у межах `cleanup_ttl_ms`; інакше open блокується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → сильніша safety (не торгувати, якщо guardian не “tidy”), але ризик over-blocking при збоях guardian.
    - 🔽 **Too Low:** `false` → gate вимкнено, відкриття не залежить від tidy.
- **Invariant/Constraints:** Читається через `config.execution` alias; переконатися, що guardian емітить tidy events (SSOT у `domains.execution_position.guardian.emit_tidy_event`).

---

### `trading.execution.order_guardian.unified`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (OrderGuardian store mode)
- **Code Reference:** `apps/reference/domains/execution_position/order_guardian.py:96` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Feature flag для “unified” guardian: коли `true`, wrapper підключає persistent ledger store (sqlite) для idempotency/відновлення; коли `false`, guardian використовує in-memory store.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → краща відновлюваність після рестартів, але потребує коректного `ledger_db_path`.
    - 🔽 **Too Low:** `false` → простіше, але більше ризиків втрати стану/дублювань після рестарту.
- **Invariant/Constraints:** Узгоджувати з `domains.execution_position.guardian.unified` (інші частини системи читають unified саме з domains). (`apps/reference/domains/execution_position/fsm.py:783`)

---

### `trading.execution.order_guardian.ledger_db_path`
- **Type:** `string` *(path)*
- **Logic Owner:** `execution_position` (OrderLedger)
- **Code Reference:** `apps/reference/domains/execution_position/order_guardian.py:109` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Шлях до sqlite DB для ledger store. Якщо задано і `unified=true`, wrapper створює директорію та ініціалізує `OrderLedger(db_path)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Невірний/повільний диск → latency/помилки збереження ledger.
    - 🔽 **Too Low:** `:memory:` або None → без персистентності (втрата стану на рестарті).
- **Invariant/Constraints:** Має бути writable шлях; бажано на локальному диску. Для прод — мати резервне копіювання/ротацію.

---

### `trading.domain_configuration.market_data.trading_mode`
- **Type:** `string` *(enum: `live|testnet`)*
- **Logic Owner:** `bootstrap` / `market_data`
- **Code Reference:** `apps/reference/bootstrap/preflight.py:34` (func: `check_hybrid_coherence`); `apps/reference/domains/market_data/worker.py:184` (func: `__init__`)
- **Mathematical/Architectural Role:**
    > Вказує, звідки market_data читає WS (live vs testnet) у multiprocessing воркері; також використовується preflight перевіркою hybrid coherence.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `live` → реальні ціни/ліквідність (більша “правда”), але може відрізнятись від testnet мікроструктури виконання.
    - 🔽 **Too Low:** `testnet` → синтетичні/інші умови, може спотворювати фічі/режими.
- **Invariant/Constraints:** У hybrid (live data + testnet exec) очікується `live`.

---

### `trading.domain_configuration.feature_engineering.trading_mode`
- **Type:** `string` *(enum: `live|testnet`)*
- **Logic Owner:** `bootstrap` (coherence check)
- **Code Reference:** `apps/reference/bootstrap/preflight.py:36` (func: `check_hybrid_coherence`)
- **Mathematical/Architectural Role:**
    > Наразі використовується лише як частина preflight логіки “any_live” для data-domain coherence. Runtime FE домен не читає це поле напряму.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `live` → очікуваний режим у hybrid.
    - 🔽 **Too Low:** `testnet` → coherence check може вважати hybrid некоректним (бо data має бути live).
- **Invariant/Constraints:** У hybrid очікується `live` для data domains.

---

### `trading.domain_configuration.decision_making.trading_mode`
- **Type:** `string` *(enum: `live|testnet`)*
- **Logic Owner:** `bootstrap` (coherence check)
- **Code Reference:** `apps/reference/bootstrap/preflight.py:37` (func: `check_hybrid_coherence`)
- **Mathematical/Architectural Role:**
    > Аналогічно FE: використовується в preflight як сигнал, що data-path має бути live. DecisionMaking runtime не читає цей ключ напряму.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `live` → очікувано в hybrid.
    - 🔽 **Too Low:** `testnet` → може спричинити incoherent hybrid (дані не live).
- **Invariant/Constraints:** У hybrid очікується `live`.

---

### `trading.risk_management.data_sources.portfolio_state`
- **Type:** `string` *(enum: `live|testnet|follow_execution`)*
- **Logic Owner:** `bootstrap` (hybrid coherence)
- **Code Reference:** `apps/reference/config_models.py:2777` (model: `RiskManagementDataSourcesConfig`); `apps/reference/bootstrap/preflight.py:46` (func: `check_hybrid_coherence`)
- **Mathematical/Architectural Role:**
    > Вказує, звідки RiskManagement має брати portfolio state в hybrid сценаріях. У preflight `follow_execution` нормалізується до `testnet` і перевіряється, що джерело = `testnet`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `live` → ризик змішування live позицій з testnet execution (кохерентність порушена).
    - 🔽 **Too Low:** `testnet`/`follow_execution` → безпечніше для hybrid (risk на основі testnet портфеля).
- **Invariant/Constraints:** Для hybrid очікується `testnet` (або `follow_execution` → `testnet`). (`apps/reference/bootstrap/preflight.py:52`)

---

### `trading.risk_management.data_sources.market_data`
- **Type:** `string` *(enum: `live|testnet`)*
- **Logic Owner:** placeholder (intended hybrid risk pricing source)
- **Code Reference:** `apps/reference/config_models.py:2776` (model: `RiskManagementDataSourcesConfig`)
- **Mathematical/Architectural Role:**
    > **No runtime consumer found.** Preflight coherence перевіряє лише `portfolio_state`; risk_management домен у поточному коді не перемикає джерело цін через цей ключ.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A без wiring)*.
    - 🔽 **Too Low:** *(N/A без wiring)*.
- **Invariant/Constraints:** Якщо реалізовувати — потрібно визначити, як ризик бере mark prices (live ticks vs account markPrice).

