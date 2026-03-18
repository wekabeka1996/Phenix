# 📄 Semantic Configuration Passport: `config/aurora/system.yaml`

> AUDIT SUMMARY
> - Document path: config/docs/system_passport.md
> - Audit date: 2026-03-18
> - Audit mode: code-driven sync
> - Major drifts found:
>   1. `account_observer.poll_interval` has been removed from the codebase (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01). The passport was updated to reflect its DELETED status.
>   2. Several sections are correctly marked as having no runtime consumers (`sequential_tests`, `hawkes`, `hardening`, `risk_core`, etc.).
> - Overall confidence: HIGH
> 
> ---
Цей паспорт описує **системні** налаштування, які визначають “фізику” процесу: таймінги, TTL, бекпрешер/черги, polling, а також секції метаданих (system_meta), які зберігаються для аудиту.

**Критичні уточнення (підтверджено трасуванням коду):**
- **Main loop cadence не конфігурується з `system.yaml`:** у `apps/reference/main.py` цикл життя — `while True: ... time.sleep(1)` (hardcoded), `alert_check_interval = 60` (hardcoded). (`apps/reference/main.py:1366`)
- **Логування НЕ належить `system.yaml`:** конфіг логування SSOT у `config/aurora/observability.yaml`, читається через `apps/reference/logging_setup.py` (CFG-OBS-001). (`apps/reference/main.py:759`, `apps/reference/logging_setup.py:91`)
- **System meta extraction:** кореневі ключі `config_version`, `sequential_tests`, `risk_core`, `kelly`, `calibrator`, `hawkes`, `hardening` переносяться `ConfigLoader` у `config.system_meta.*` (щоб root був `extra='forbid'`). (`apps/reference/config_loader.py:232`)
- **Panic killswitch wiring:** gate для `CMD:OPEN` читає **`config.trading.ops.panic_killswitch`**, а не `config.ops.panic_killswitch`. (`apps/reference/domains/execution_position/fsm_open.py:267`)

---

### `config_version`
- **Type:** `string` *(SemVer-like, metadata)*
- **Logic Owner:** `config_loader` → `system_meta`
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/main.py:764` (func: `main`)
- **Mathematical/Architectural Role:**
    > **Версія `system.yaml` як метадані.** При завантаженні конфіга значення **переміщується** з root `config_version` у `config.system_meta.system_config_version` і використовується для логування/аудиту, а не для runtime-логіки.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)* (рядок-версія).
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Має бути рядком; рекомендовано SemVer. Не використовується у формулах/гейтах напряму.

---

### `trading_mode`
- **Type:** `string` *(enum: `live` | `testnet` | `production` | `hybrid_live_data_testnet_exec` | `backtest`)*
- **Logic Owner:** `config_models` (validation) + `main` (режим виконання) + доменна wiring-логіка
- **Code Reference:** `apps/reference/config_models.py:3038` (validator: `validate_trading_mode`); `apps/reference/config_loader.py:544` (func: `_validate_config`); `apps/reference/main.py:767` (func: `main`)
- **Mathematical/Architectural Role:**
    > **Глобальний режим роботи системи.** Визначає:
    > - чи запускається `run_backtest_simulation()` і процес виходить (коли `backtest`) (`apps/reference/main.py:786`);
    > - fail-fast вимоги до `binance_api.live` в live/hybrid (`apps/reference/config_loader.py:551`);
    > - поведінку startup guards (наприклад, `warn_only_filters` примусово вимикається у `live|production`) (`apps/reference/main.py:805`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Перехід у live-like режими (`live|production|hybrid`) підвищує blast radius: реальне виконання/строгіші fail-closed умови (ключі API, валідація фільтрів).
    - 🔽 **Too Low:** `testnet|backtest` безпечніші для експериментів; `backtest` повністю перехоплює main-loop і не запускає live runtime.
- **Invariant/Constraints:** Значення має бути з allowlist (інакше `ValueError`). В ідеалі `trading.mode` у `trading.yaml` має бути узгоджений (Pydantic синхронізує). (`apps/reference/config_models.py:3040`, `apps/reference/config_models.py:3049`)

---

### `system.market_data.queue_maxsize`
- **Type:** `int`
- **Logic Owner:** `market_data` (IPC/backpressure)
- **Code Reference:** `apps/reference/config_models.py:2881` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/proxy.py:100` (func: `_load_system_market_data_settings`); `apps/reference/domains/market_data/proxy.py:381` (func: `start_async`); `apps/reference/domains/market_data/worker.py:294` (func: `_put_with_backpressure`)
- **Mathematical/Architectural Role:**
    > **Розмір IPC черги (worker → proxy).** Proxy створює `Queue(maxsize=queue_maxsize)`.  
    > Worker пушить повідомлення у чергу; при переповненні застосовується **drop-oldest** (щоб зберігати “найсвіжіше”): `put_nowait` → `queue.Full` → `get_nowait()` (drop) → `put_nowait()`; лічильник `ticks_dropped` росте.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше RAM і більший потенційний lag (черга може накопичувати історію, приховуючи, що consumer не встигає).
    - 🔽 **Too Low:** Часті `queue.Full` → часті drop-oldest → деградація якості маркет-даних і downstream подій `EVT:MARKET_TICK_RECEIVED`.
- **Invariant/Constraints:** `int > 0` (fail-fast у proxy). (`apps/reference/domains/market_data/proxy.py:115`)

---

### `system.market_data.tick_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `regime_detector` (data-quality TTL) *(але tick path зараз фактично вимкнений)*
- **Code Reference:** `apps/reference/config_models.py:2885` (model: `SystemMarketDataConfig`); `apps/reference/domains/regime_detector/regime_detector.py:230` (func: `handle_event`); `apps/reference/domains/regime_detector/regime_detector.py:261` (func: `handle_event`)
- **Mathematical/Architectural Role:**
    > **Задум:** TTL для тик-подій (tf_sec=0): якщо `now_wall_ms - ts_ms > tick_ttl_ms` → stale drop.  
    > **Факт у поточному коді:** RegimeDetector **ігнорує tick-level features** (`tf_sec == 0` → early return) **до** TTL-логіки, тому `tick_ttl_ms` не впливає на runtime при бар-режимі. (`apps/reference/domains/regime_detector/regime_detector.py:230`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі N/A)*; якщо tick-процесінг буде увімкнено — дозволить більш “старі” тики (ризик noisy/late реакцій).
    - 🔽 **Too Low:** *(Наразі N/A)*; якщо tick-процесінг буде увімкнено — більше відкидань тика через мережевий lag.
- **Invariant/Constraints:** `int >= 0`, очікується в ms. Не плутати з TTL у `decision_making` для tick, який використовує `features_ttl_sec` домену.

---

### `system.market_data.bar_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `decision_making` (TTL gates) + `regime_detector` (stale guard)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:991` (Gate 5 TTL); `apps/reference/domains/decision_making/decision_making.py:2375` (func: `_features_ready`); `apps/reference/domains/regime_detector/regime_detector.py:261` (func: `handle_event`)
- **Mathematical/Architectural Role:**
    > **Bar-aware TTL (DM + RegimeDetector).**  
    > - DM (Gate 5): для барів (`tf_sec>0`) `ttl_ms = system.market_data.bar_ttl_ms` (fallback: `tf_sec*1000*2`), і якщо `signal_age_ms > ttl_ms` → **reject** як stale. (`apps/reference/domains/decision_making/decision_making.py:991`)  
    > - DM (`_features_ready`): `lag_ms = now_ms - start_ts`, де `start_ts` залежить від `bar_event_age_mode`, і `lag_ms <= bar_ttl_ms` визначає готовність. Додатково є **safety guard**: `bar_actual_age_ms = now_ms - bar_close_ts`; якщо `bar_actual_age_ms > max(tf_sec*1000, bar_ttl_ms)` → reject як “ancient bar”. (`apps/reference/domains/decision_making/decision_making.py:2422`)  
    > - RegimeDetector: якщо `ttl_ms > 0 and (now_wall_ms - ts_ms) > ttl_ms` → emit `EVT:REGIME_DETECTED` з `regime="UNCERTAIN"` і ранній return (fail-closed на stale). (`apps/reference/domains/regime_detector/regime_detector.py:274`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш толерантно до лагів, але зростає ризик торгувати на “вчорашніх” барах/фічах (особливо якщо upstream затримує події).
    - 🔽 **Too Low:** Більше fail-closed відмов (`stale signal/features`), потенційно менше угод і більше `UNCERTAIN` через тимчасові мережеві/чергові затримки.
- **Invariant/Constraints:** Має бути **int, не `null`** (у RegimeDetector викликається `int(...)` без `or` fallback). У DM значення `0` трактується як “unset” через `or`-fallback, але в RegimeDetector `0` фактично **вимикає** stale-check (бо `ttl_ms > 0` не виконується) — уникати таких “псевдо-вимкнень”.

---

### `system.market_data.bar_event_age_mode`
- **Type:** `string` *(enum: `received` | `close_ts`)*
- **Logic Owner:** `decision_making` (bar freshness semantics)
- **Code Reference:** `apps/reference/config_models.py:2887` (model: `SystemMarketDataConfig`); `apps/reference/domains/decision_making/decision_making.py:1992` (inject `_received_ts`); `apps/reference/domains/decision_making/decision_making.py:2397` (func: `_features_ready`)
- **Mathematical/Architectural Role:**
    > **Вибір “нульової точки” для віку бару в TTL-перевірках:**
    > - `received`: `start_ts = features_data["_received_ts"]` (інʼєктується в `on_features` при прийомі події) → TTL міряє “час у чергах/системі”.  
    > - `close_ts`: `start_ts = features_ts` (event time / close time) → TTL міряє “час з моменту закриття бару”.  
    > В обох режимах зберігається safety guard по `bar_close_ts`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Перехід у `received` робить систему більш толерантною до транспортного lag (менше false-stale), але може пропускати проблему “старий бар прийшов зараз”.
    - 🔽 **Too Low:** `close_ts` більш fail-closed (краще блокує “прострочені” бари), але підвищує ризик відмов при легітимних затримках доставки.
- **Invariant/Constraints:** Має бути одне з `{"received","close_ts"}` (Pydantic). Для `received` потрібна наявність `_received_ts`, який інʼєктується DM (інакше fallback на `features_ts`).

---

### `system.market_data.ws_heartbeat_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `market_data` (WebSocket keepalive)
- **Code Reference:** `apps/reference/config_models.py:2891` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/worker.py:170` (init validation); `apps/reference/domains/market_data/worker.py:420` (func: `_ws_loop`)
- **Mathematical/Architectural Role:**
    > Параметр `aiohttp.ClientSession.ws_connect(..., heartbeat=ws_heartbeat_sec)`: частота heartbeat/ping для підтримки WS-зʼєднання активним.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідкі heartbeat → довше не помічаються “напівмертві” зʼєднання/мережеві паузи.
    - 🔽 **Too Low:** Зайвий мережевий/CPU overhead; у поганій мережі може частіше провокувати disconnect.
- **Invariant/Constraints:** `> 0` (worker fail-fast). (`apps/reference/domains/market_data/worker.py:172`)

---

### `system.market_data.ws_receive_timeout_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `market_data` (stall detection / reconnect)
- **Code Reference:** `apps/reference/config_models.py:2892` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/worker.py:171` (init validation); `apps/reference/domains/market_data/worker.py:435` (func: `_ws_loop`)
- **Mathematical/Architectural Role:**
    > **Детектор “тихого зависання” WS:** `msg = await ws.receive(timeout=ws_receive_timeout_sec)`; якщо `asyncio.TimeoutError` → лог warning і reconnect (close ws → break).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довше триматиметься stalled WS → більший lag маркет-даних перед відновленням.
    - 🔽 **Too Low:** Часті reconnect-и на тимчасових паузах потоку → більше churn і потенційний тиск на rate limits.
- **Invariant/Constraints:** `> 0` (worker fail-fast). (`apps/reference/domains/market_data/worker.py:174`)

---

### `system.market_data.proxy_batch_size`
- **Type:** `int`
- **Logic Owner:** `market_data` (proxy throughput/latency tradeoff)
- **Code Reference:** `apps/reference/config_models.py:2893` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/proxy.py:100` (func: `_load_system_market_data_settings`); `apps/reference/domains/market_data/proxy.py:279` (func: `_consume_queue_sync`)
- **Mathematical/Architectural Role:**
    > Ліміт повідомлень “за один батч” в consumer thread: `while items_processed < proxy_batch_size: queue.get(...); emit...`. Визначає компроміс між throughput і latency/інтерактивністю.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Кращий throughput у піках, але довші батчі можуть збільшувати latency інших задач потоку/логування.
    - 🔽 **Too Low:** Більше overhead на loop/таймаути, повільніше “доганяння” черги → ризик накопичення та drop-oldest у worker.
- **Invariant/Constraints:** `int > 0` (proxy fail-fast). (`apps/reference/domains/market_data/proxy.py:117`)

---

### `system.market_data.proxy_queue_get_timeout_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `market_data` (proxy queue polling)
- **Code Reference:** `apps/reference/config_models.py:2894` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/proxy.py:100` (func: `_load_system_market_data_settings`); `apps/reference/domains/market_data/proxy.py:282` (func: `_consume_queue_sync`)
- **Mathematical/Architectural Role:**
    > Таймаут блокуючого читання: `msg = queue.get(timeout=proxy_queue_get_timeout_sec)`. Менше значення → швидше реагування на stop/порожню чергу, але більше частих таймаутів (CPU).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Consumer може “засинати” довше на `get()` → більша затримка обробки нових повідомлень/зупинки.
    - 🔽 **Too Low:** Більше wakeups/таймаутів → вище навантаження CPU (особливо при порожній черзі).
- **Invariant/Constraints:** `> 0` (proxy fail-fast). (`apps/reference/domains/market_data/proxy.py:120`)

---

### `system.market_data.proxy_idle_sleep_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `market_data` (proxy idle backoff)
- **Code Reference:** `apps/reference/config_models.py:2895` (model: `SystemMarketDataConfig`); `apps/reference/domains/market_data/proxy.py:100` (func: `_load_system_market_data_settings`); `apps/reference/domains/market_data/proxy.py:327` (func: `_consume_queue_sync`)
- **Mathematical/Architectural Role:**
    > Якщо батч порожній (`items_processed==0`) → `time.sleep(proxy_idle_sleep_sec)` для уникнення busy-waiting. Це **другий** (після `get(timeout=...)`) регулятор CPU/latency.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менше CPU, але більша latency на старті нових бурстів (дані можуть прийти одразу після sleep).
    - 🔽 **Too Low:** Менше latency, але ризик busy-loop (особливо якщо `proxy_queue_get_timeout_sec` також малий).
- **Invariant/Constraints:** `> 0` (proxy fail-fast). (`apps/reference/domains/market_data/proxy.py:121`)

---

### `ops.panic_killswitch`
- **Type:** `bool`
- **Logic Owner:** `execution_position` (entry gate) *(але фактичний read-path з `trading.ops`)*
- **Code Reference:** `apps/reference/config_models.py:2608` (model: `OpsConfig`); `apps/reference/domains/execution_position/fsm_open.py:267` (func: `handle`); `apps/reference/domains/execution_position/fsm.py:1056` (func: `on_panic_killswitch_activated`)
- **Mathematical/Architectural Role:**
    > **Глобальний killswitch для входів:** при `panic_killswitch=true` блокується будь-який новий `CMD:OPEN` (fail-closed reject).  
    > Важливо: у gate читання йде з `config.trading.ops.panic_killswitch` (trading.yaml), а не з `config.ops.panic_killswitch` (system.yaml). Тобто **цей ключ у `system.yaml` може не мати ефекту** для entry-gate, якщо `trading.ops` відрізняється або є єдиним джерелом. (`apps/reference/domains/execution_position/fsm_open.py:270`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` → повне блокування нових входів + потенційні аварійні відміни pending entries (якщо зовнішній код викликає `on_panic_killswitch_activated()`).
    - 🔽 **Too Low:** `false` → звичайний режим (нові входи дозволені за іншими гейтами).
- **Invariant/Constraints:** Має бути bool. Для гарантованого ефекту на `CMD:OPEN` встановлювати в `trading.yaml` → `trading.ops.panic_killswitch`.

---

### `ops.metrics_url`
- **Type:** `string|null` *(URL, tooling only)*
- **Logic Owner:** `ops` / tooling
- **Code Reference:** `apps/reference/config_models.py:2611` (model: `OpsConfig`); `tools/metrics_summary.py:15` (func: `_get_cfg`)
- **Mathematical/Architectural Role:**
    > Endpoint для scrape Prometheus-метрик у tooling (`metrics_summary.py`). На core-runtime (main loop/FSM) не впливає.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)* (рядок-URL).
    - 🔽 **Too Low:** Невалідний/недоступний URL → tooling не зможе зчитати метрики.
- **Invariant/Constraints:** Має бути валідним URL (`http(s)://...`). У runtime може бути `null`.

---

### `ops.reports_dir`
- **Type:** `string|null` *(path, tooling only)*
- **Logic Owner:** `ops` / tooling
- **Code Reference:** `apps/reference/config_models.py:2615` (model: `OpsConfig`); `tools/metrics_summary.py:46` (func: `_get_cfg`)
- **Mathematical/Architectural Role:**
    > Директорія для запису звітів tooling (напр., Markdown/JSON звіти `metrics_summary.py`). Не впливає на частоту/логіку торгового циклу.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Невірний шлях/немає прав → tooling не зможе зберігати звіти.
- **Invariant/Constraints:** Має бути шляхом у файловій системі, доступним для запису.

---

### `execution`
- **Type:** `object|null` *(ExecutionConfig override)*
- **Logic Owner:** `config_models` (root alias/override) + `execution_position` (consumption via `config.execution`)
- **Code Reference:** `apps/reference/config_models.py:2990` (field: `AuroraConfig.execution`); `apps/reference/config_models.py:3060` (model_validator: `_backcompat_root_execution_alias`); `apps/reference/domains/execution_position/fsm.py:3554` (func: `_entry_tidy_gate_allow`)
- **Mathematical/Architectural Role:**
    > **Root override для `trading.execution`.** Контракт: якщо `execution` заданий (не `null`) — він може **override** trading-level execution policy; якщо `null`, Pydantic після завантаження може підставити `config.execution = config.trading.execution` (back-compat alias).  
    > Downstream код часто читає `config.execution.*` (наприклад, entry-gate `allow_trade_with_guardian_tidy_only`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо заповнити `execution` у root — можна непомітно “відрізати” або змінити критичні execution guards/TTL/backoff (залежно від полів), бо споживачі читають саме `config.execution`.
    - 🔽 **Too Low:** `null` → немає override; використовується `trading.execution` (через alias), або `None` (у мінімальних тестових конфігах).
- **Invariant/Constraints:** Якщо не `null`, має відповідати схемі `ExecutionConfig` (Pydantic fail-fast). У `system.yaml` зараз `null` — це **свідомий** вибір “не override”.

---

### `brackets`
- **Type:** `object|null` *(BracketsConfig override)*
- **Logic Owner:** `execution_position` (але фактичний SSOT у `trading.execution.manage.brackets`) + `config_models`
- **Code Reference:** `apps/reference/config_models.py:2991` (field: `AuroraConfig.brackets`); `apps/reference/domains/execution_position/fsm_manage.py:634` (brackets SSOT requirement)
- **Mathematical/Architectural Role:**
    > У поточному runtime немає читання `config.brackets` (root). Фактична робоча конфігурація брекетів (TP/SL) читається з `trading.execution.manage.brackets` і є **fail-closed required** для safety offset (`offset_bps`).  
    > Тобто `brackets: null` у `system.yaml` не впливає на реальну постановку TP/SL.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A наразі)*; заповнення `brackets` у root не змінить поведінку, доки немає споживача.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** Для реальної роботи брекетів налаштовувати `trading.execution.manage.brackets` (trading.yaml); там `offset_bps` є required без fallback. (`apps/reference/domains/execution_position/fsm_manage.py:634`)

---

### `trailing.activation_pct`
- **Type:** `float`
- **Logic Owner:** `execution_position` (ManageFlowFSM trailing)
- **Code Reference:** `apps/reference/config_models.py:721` (model: `TrailingDefaultsConfig`); `apps/reference/domains/execution_position/fsm_manage.py:1231` (func: `_check_trailing_stop`)
- **Mathematical/Architectural Role:**
    > **Поріг активації трейлінгу від entry.** Для BUY:  
    > `activation_threshold = entry_price * (1 + activation_pct)`; активація коли `current_price >= activation_threshold`.  
    > Для SELL аналогічно вниз: `entry_price * (1 - activation_pct)`.  
    > **Fail-closed:** якщо per-instrument `trailing_stop.activation_pct` відсутній, тоді система вимагає глобальний fallback `config.trailing.activation_pct` (цей ключ). (`apps/reference/domains/execution_position/fsm_manage.py:1234`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Трейлінг активується пізніше → більше потенційного giveback до активації; менше випадків раннього “затягування” SL.
    - 🔽 **Too Low:** Трейлінг активується раніше → більше шансів передчасного tighten/stop-out на шумі.
- **Invariant/Constraints:** Має бути `>= 0`. Для символів з увімкненим трейлінгом або задайте per-instrument значення, або забезпечте цей глобальний дефолт (інакше ValueError).

---

### `trailing.trail_pct`
- **Type:** `float`
- **Logic Owner:** `execution_position` (ManageFlowFSM trailing)
- **Code Reference:** `apps/reference/config_models.py:722` (model: `TrailingDefaultsConfig`); `apps/reference/domains/execution_position/fsm_manage.py:1267` (func: `_check_trailing_stop`)
- **Mathematical/Architectural Role:**
    > **Відстань трейлінгу від high-water mark (peak).**  
    > BUY: `new_sl = peak_price * (1 - trail_pct)`; оновлення лише якщо `new_sl > current_sl` (tighten).  
    > SELL: `new_sl = peak_price * (1 + trail_pct)`; оновлення лише якщо `new_sl < current_sl`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш “широкий” трейлінг → менше tighten-ів, більше giveback, але менше випадкових стопів.
    - 🔽 **Too Low:** Дуже “тугий” трейлінг → частіші оновлення/скасування+нові SL, вищий ризик стоп-аута на шумі.
- **Invariant/Constraints:** Має бути `> 0`. Якщо per-instrument `trail_pct` відсутній — потрібен глобальний fallback (fail-closed).

---

### `trailing.min_update_interval_sec`
- **Type:** `int`
- **Logic Owner:** `execution_position` *(intended, але global fallback не підключений)*
- **Code Reference:** `apps/reference/config_models.py:723` (model: `TrailingDefaultsConfig`); `apps/reference/domains/execution_position/fsm_manage.py:268` (func: `_get_trailing_stop_params`)
- **Mathematical/Architectural Role:**
    > **Задум:** мінімальний інтервал між оновленнями SL при трейлінгу (rate limit).  
    > **Факт у поточному коді:** `ManageFlowFSM` бере `min_update_interval_sec` **лише** з per-instrument `trailing_stop.min_update_interval_sec` (або жорсткий default `5`), і **не читає** `config.trailing.min_update_interval_sec` (цей ключ). (`apps/reference/domains/execution_position/fsm_manage.py:283`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі N/A)*; якщо буде підключено — рідші оновлення SL (менше API churn, більше lag у tighten).
    - 🔽 **Too Low:** *(Наразі N/A)*; якщо буде підключено — частіші оновлення (краще слідування за ціною, але більше cancel/replace).
- **Invariant/Constraints:** Має бути `>= 0`. Реальний rate-limit зараз задається per-instrument або константою `5`.

---

### `sequential_tests.wald.alpha`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Зберігається як `config.system_meta.sequential_tests` (dict) для аудиту/майбутніх модулів. У поточному runtime-циклі споживача не знайдено.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту у runtime)*.
    - 🔽 **Too Low:** *(Наразі без ефекту у runtime)*.
- **Invariant/Constraints:** Має бути присутнім у `system.yaml`, інакше `SystemMetaConfig` може не пройти валідацію (fail-fast). Тримати у діапазоні (0,1).

---

### `sequential_tests.wald.beta`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані для Wald sequential test (ймовірнісний поріг/помилка II роду). Наразі не підключено до runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту у runtime)*.
    - 🔽 **Too Low:** *(Наразі без ефекту у runtime)*.
- **Invariant/Constraints:** Рекомендовано (0,1). Підтримувати узгодженість з `alpha`.

---

### `sequential_tests.wald.mu0`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: гіпотеза `H0` (середнє) для Wald test. У поточному runtime не використовується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути числом; узгоджувати з `mu1`.

---

### `sequential_tests.wald.mu1`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: гіпотеза `H1` (середнє) для Wald test. У поточному runtime не використовується.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути числом; зазвичай `mu1 != mu0`.

---

### `sequential_tests.wald.sigma`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: оцінка σ для Wald test. Наразі не підключено до runtime-алгоритмів.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути `> 0` у статистичному сенсі.

---

### `sequential_tests.glr.alpha`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані для GLR тесту. У поточному runtime не читається.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Рекомендовано (0,1).

---

### `sequential_tests.glr.beta`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані для GLR тесту. У поточному runtime не читається.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Рекомендовано (0,1).

---

### `sequential_tests.glr.min_samples`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: мінімальна кількість семплів для GLR. Наразі не споживається runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути `>= 1`.

---

### `risk_core.cvar_threshold_bps`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані для “risk_core” (CVaR threshold у bps). У поточній реалізації risk домену споживача цього ключа не знайдено; зберігається в `config.system_meta.risk_core`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту у runtime)*.
    - 🔽 **Too Low:** *(Наразі без ефекту у runtime)*.
- **Invariant/Constraints:** Ціле число bps (`>=0`). Підтримувати консистентність з `trading.risk_budgets.*` (інший, живий контур).

---

### `risk_core.stress_scenarios`
- **Type:** `list[string]`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Перелік назв stress-сценаріїв (напр., `flash_crash`, `volatility_spike`). Наразі лише зберігається як метадані.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Список рядків; рекомендується whitelist/enum (щоб уникнути “мертвих” сценаріїв).

---

### `risk_core.inventory_limits.max_abs_position`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: максимальна абсолютна позиція (units). Наразі не підключено в `risk_management` runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 0`. В реальних гейтах позицій ліміти зараз задаються в інших SSOT секціях.

---

### `risk_core.inventory_limits.max_daily_notional`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: денний notional cap (USD). Наразі не споживається runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 0`.

---

### `kelly.fraction_cap`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only; не плутати з `decision.kelly`)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`); `apps/reference/config_models.py:638` (field: `DecisionConfig.kelly`)
- **Mathematical/Architectural Role:**
    > Метадані “Kelly cap” у `config.system_meta.kelly`. У живій логіці sizing (DecisionMaking) використовується **інший** Kelly-контур (`domains.decision_making.*` / `decision.kelly`), а цей блок наразі не має споживача.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту у runtime)*.
    - 🔽 **Too Low:** *(Наразі без ефекту у runtime)*.
- **Invariant/Constraints:** Зазвичай `0 < fraction_cap <= 1`.

---

### `kelly.decay_half_life_days`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: half-life у днях для decay у Kelly-контурі. Наразі не споживається runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 1` у практичному сенсі.

---

### `calibrator.state_store.backend`
- **Type:** `string`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані для calibrator state store (напр., `sqlite`). У поточному runtime calibrator не інтегровано.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути узгоджено з `path` (якщо backend потребує файлу/URL).

---

### `calibrator.state_store.path`
- **Type:** `string` *(path)*
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: шлях до state DB (`data/calibrator/state.db`). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Невірний шлях → майбутні модулі (якщо будуть підключені) не зможуть писати стан.
- **Invariant/Constraints:** Путь має бути writable, якщо підключити calibrator.

---

### `calibrator.state_store.versioning`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: чи увімкнено версіонування калібратора. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `calibrator.state_store.retention_days`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: політика retention у днях для state store. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 0`.

---

### `hawkes.enabled`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: перемикач Hawkes-модуля. У runtime споживача не знайдено; зберігається у `config.system_meta.hawkes`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `hawkes.kernel.decay_beta_ms`
- **Type:** `float` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: параметр decay kernel (β) для Hawkes у ms. Наразі не споживається runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** Має бути `> 0` у сенсі decay.

---

### `hawkes.eta_max`
- **Type:** `float`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: верхня межа η для Hawkes. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 0`.

---

### `hawkes.update_interval_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: інтервал оновлення Hawkes-оцінок. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `> 0` якщо/коли буде підключено.

---

### `hawkes.window_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: розмір вікна для Hawkes. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `> 0` якщо/коли буде підключено.

---

### `hawkes.bivariate`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: bivariate режим Hawkes. Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `hardening.ttl_config.entry_place_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: TTL для постановки entry-ордера (коментар у YAML: “5 seconds for entry orders”). Наразі не знайдено читання в runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — більш поблажливо до лагів, але довше триматиме “живі” старі інтенції.
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — більше fail-closed таймаутів.
- **Invariant/Constraints:** `> 0` у практичному сенсі.

---

### `hardening.ttl_config.bracket_place_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: TTL для постановки брекетів (TP/SL) (коментар: “3 seconds for bracket orders”). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `> 0` у практичному сенсі.

---

### `hardening.ttl_config.cancel_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: TTL для cancel-операцій (коментар: “2 seconds for cancellations”). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `> 0` у практичному сенсі.

---

### `hardening.retry_config.max_tries`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: максимальна кількість ретраїв (коментар: “Maximum retry attempts”). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — більше часу/спроб на відновлення, але більше latency і потенційних дублювань.
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — швидше fail-fast.
- **Invariant/Constraints:** `>= 0`.

---

### `hardening.retry_config.backoff_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: базовий backoff для ретраїв (коментар: “Base backoff time”). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — повільніші повтори, менший тиск на API.
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — швидші повтори, вищий ризик rate-limit.
- **Invariant/Constraints:** `>= 0`.

---

### `hardening.retry_config.jitter`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: чи додавати jitter до backoff (коментар: “Add random jitter”). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `hardening.circuit_breaker.fail_max`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: кількість fail-ів для відкриття circuit (коментар у YAML). Не знайдено runtime-споживача цього конкретного конфіга.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — circuit відкриватиметься рідше (менше false-open).
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — більш агресивне відкриття circuit (більше fail-closed поведінки).
- **Invariant/Constraints:** `>= 1` у практичному сенсі.

---

### `hardening.circuit_breaker.reset_timeout_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: час у OPEN перед HALF_OPEN (коментар у YAML). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — довше в OPEN (більше безпеки, менше доступності).
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — швидше тестові запити (HALF_OPEN), але ризик флапінгу.
- **Invariant/Constraints:** `> 0`.

---

### `hardening.circuit_breaker.exclude`
- **Type:** `list[string]` *(regex patterns)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: винятки, які не рахуються як fail у circuit breaker (regex на exception-string). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — більше помилок ігнорується (менше circuit-open, але більше ризику “терпіти” реальні збої).
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — більше помилок рахуються (агресивніший circuit).
- **Invariant/Constraints:** Валідні regex/патерни; не робити надто широкими (маскування критичних проблем).

---

### `hardening.circuit_breaker.open_threshold_pct`
- **Type:** `int` *(percent)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: open якщо >X% викликів fail у вікні (коментар у YAML). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — рідше відкриття circuit по error-rate.
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — частіше/агресивніше відкриття.
- **Invariant/Constraints:** `0..100`.

---

### `hardening.circuit_breaker.error_rate_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: rolling window для error-rate (коментар у YAML). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — більш інертний error-rate (менше реактивності).
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — більш “нервовий” error-rate (ризик флапінгу).
- **Invariant/Constraints:** `> 0`.

---

### `hardening.circuit_breaker.half_open_attempts`
- **Type:** `int`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: кількість тестових викликів у HALF_OPEN (коментар у YAML). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*; якщо підключити — більше перевірок перед поверненням у CLOSED (менше ризику, більше latency).
    - 🔽 **Too Low:** *(Наразі без ефекту)*; якщо підключити — швидше повернення, але більше ризику помилкового CLOSED.
- **Invariant/Constraints:** `>= 1`.

---

### `hardening.market_data.max_allowed_lag_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: максимальний дозволений lag маркет-даних. У поточному `market_data`/DM/RD контурі цей параметр не читається; lag гейти реалізовані через `bar_ttl_ms`/`ws_receive_timeout_sec` та інші механізми.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(Наразі без ефекту)*.
    - 🔽 **Too Low:** *(Наразі без ефекту)*.
- **Invariant/Constraints:** `>= 0`.

---

### `hardening.market_data.sequence_check_enabled`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: чи увімкнено sequence number validation. Наразі у WS worker присутня власна логіка по out-of-order (`trades_dropped_out_of_order` у payload), але цей перемикач не wired.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `hardening.wal.integrity_check_enabled`
- **Type:** `bool`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: toggle для WAL integrity checks. Наразі логіка WAL має локальні перевірки/помилки, але цей параметр не прочитується як конфіг.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` *(N/A зараз)*.
    - 🔽 **Too Low:** `false` *(N/A зараз)*.
- **Invariant/Constraints:** Bool.

---

### `hardening.wal.hash_algorithm`
- **Type:** `string`
- **Logic Owner:** `system_meta` *(metadata only; AURORA_HARDENING_V1)*
- **Code Reference:** `apps/reference/config_loader.py:232` (func: `_extract_system_meta`); `apps/reference/config_models.py:2925` (model: `SystemMetaConfig`)
- **Mathematical/Architectural Role:**
    > Метадані: алгоритм хешування для WAL integrity (коментар: `"sha256"`). Наразі не використовується runtime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** Невалідний алгоритм → майбутній інтеграції доведеться fail-fast.
- **Invariant/Constraints:** Має бути імʼям алгоритму, підтриманого реалізацією (якщо буде підключено).

---

### `account_observer.poll_interval`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `account_balance` (polling loop)
- **Code Reference:** `apps/reference/config_models.py:3935` (module: `AccountObserverConfig` removed)
- **Mathematical/Architectural Role:**
    > **REMOVED (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)**: The `account_observer` config section and its related `AccountObserverConfig` were removed from the codebase. The `account_observer.start()` call is currently commented out in `main.py`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** *(N/A)*.
    - 🔽 **Too Low:** *(N/A)*.
- **Invariant/Constraints:** DELETED

