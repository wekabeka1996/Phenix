# План виправлень і тестування: QoS / Retry / Portfolio Contracts / ExecutionPosition
**Дата:** 2026-01-26  
**Статус:** частково реалізовано (Phase 0 ✅ DONE, Phase 1 ✅ DONE, Phase 2 ✅ DONE)  
**Останнє оновлення:** 2026-01-26 15:30

---

## 0) Контекст (що болить зараз)

На основі аудитів і логів (зокрема `logs/domain_execution_position.log`, `logs/aurora_core.log*`, `logs/backtests/order_log_*.jsonl`) підтвердилися кілька “контрактних” і “оркестраційних” проблем, які можуть:

- давати **некоректний QoS** у strategy gateway (split-brain між check vs write);
- робити **defer фактично “мертвим”** (є emit `EVT:INTENT_DEFERRED`, але нема гарантованого retry);
- ламати **fail-closed exposure** через **невідповідність схеми портфеля** (`equity_free_usdt` інколи відсутнє);
- створювати **шумні warning-и** в watchdog (“ACK received for unknown order …”) через дубльований ACK шлях і/або відсутній tracking bracket-ордерів;
- лишати **volatile critical state** для LIMIT-деферред TP/SL (ризик “naked position” при рестарті, якщо це live-патерн).

Це не “косметика”: частина проблем має прямий вплив на безпеку виконання (execution safety) і на детермінізм/керованість системи.

---

## 1) Головні цілі (SSOT + детермінізм)

1. **QoS має бути консистентним і strategy-aware**: той самий `strategy_id` використовується для read/compute/write.
2. **Defer має означати retry**, або його не повинно бути (fail-closed / drop з видимим reason).
3. **Схема `EVT:PORTFOLIO_STATE_UPDATED` має бути стабільною** (мінімум для exposure/risk gates), з єдиною timebase.
4. **ExecutionPosition має бути fail-safe для LIMIT**: deferred brackets не можуть бути “тільки в RAM”.
5. **Observability без false positives**: watchdog та логи не повинні маскувати реальні проблеми шумом.

---

## 2) План виправлень (по пріоритетах)

### Phase 0 (P0): ✅ DONE — Backtest Determinism (Monotonic/Timebase)

**Проблема (виправлено 2026-01-26):**
- `MockClock.set_time_ms()` НЕ оновлював `_monotonic`, тому REENTRY_COOLDOWN завжди показував `0.0s < 45.0s`.
- `AuroraHandler` не отримував `bt_clock.monotonic` через aurora_builtin.py.
- `Watchdog.start()` викликався тільки в `except` блоці — не стартував при успішній ініціалізації.

**Виправлення:**
- `clock.py:170-180`: `set_time_ms()` тепер оновлює `_monotonic += delta_ms / 1000.0` (тільки позитивні delta).
- `aurora_builtin.py:123`: передає `monotonic_fn=monotonic_fn` в AuroraHandler.
- `main.py:565`: передає `bt_clock.monotonic` при створенні aurora handler.
- `fsm.py:501,540`: `watchdog.start()` викликається завжди (не тільки в except).

**Результат:** ORDER_PLACED збільшився з 2 до 5+, REENTRY_COOLDOWN тепер показує реальний delta (300s, 600s...).

---

### Phase 1 (P0): ✅ DONE — QoS consistency у DecisionMaking

**Проблема (підтверджено):** у strategy gateway `_qos_allow()` викликається без `strategy_id`, але `_update_qos_state()` пише з фактичним `strategy_id`. Це створює split-brain QoS.  
**Де видно:**  
- QoS check: `apps/reference/domains/decision_making/decision_making.py:844` (`_qos_allow(symbol)` без strategy_id)  
- QoS write: `apps/reference/domains/decision_making/decision_making.py:1169` (`_update_qos_state(symbol, strategy_id)`)  
- QoS state partition: `apps/reference/domains/decision_making/decision_making.py:186–194`

**Що змінити (суть):**
- у gateway передавати `strategy_id` в `_qos_allow(...)`;
- у defer-гілці передавати `strategy_id` в `_calculate_next_allowed_time(...)` і зробити її strategy-aware (читати `self._qos_state[strategy_id]`);
- вирівняти reason-коди: cooldown ≠ rate-limit (cooldown → `SYMBOL_COOLDOWN_ACTIVE`).

**Очікуваний ефект на поведінку:**
- QoS почне реально ізолювати стратегії (як заявлено в коментарях), без крос-впливів;
- `next_allowed_ts` у defer перестане бути “майже now” при активному cooldown/rate-window;
- метрики/алерти QoS стануть інтерпретованими (правильні reason).

**Ризики:**
- зменшення/збільшення частоти торгів залежно від того, як зараз “випадково” працював QoS;
- можливі зміни в backtest результатах (це нормально; потрібна калібровка).

**Acceptance criteria:**
- для двох різних `strategy_id` QoS cooldown/rate-limit працює незалежно;
- `EVT:INTENT_DEFERRED.next_allowed_ts` монотонно > now при активному блокуванні.

---

### Phase 2 (P0): ✅ DONE — Вирішити контракт retry для `EVT:INTENT_DEFERRED`

**Проблема (підтверджено частково):**
- `DecisionMaking` емiтить `EVT:INTENT_DEFERRED`, але в коді відсутній `fsm.listen("EVT:INTENT_DEFERRED", ...)` (пошук по repo не знаходить).  
- В `apps/reference/main.py:1168` є примітка “Bridge RetryScheduler binding removed (BRIDGE-SUNSET-01)”.

**Критичне рішення (SSOT контракт):** хто відповідає за retry?

Варіанти:
1) **Відновити централізований RetryScheduler** (рекомендовано як SSOT для retry), зробити явне binding/listen в `apps/reference/main.py` (або іншому composition root).  
2) **Інтегрувати retry в DecisionMaking** (використати існуючий `DeferredIntentScheduler` або власний механізм), але це гірше: DM стає менш “pure” і виникає дублювання з `apps/reference/retry_scheduler.py`.
3) **Відмовитись від defer** у gateway (лише shadow/enforce), якщо retry інфраструктуру не готові підтримувати.

**Очікуваний ефект на поведінку:**
- “defer” перестає бути drop; система або робить retry, або чесно блокує (з видимим NRR).

**Ризики:**
- неправильна timebase в `next_allowed_ts` (в backtest треба брати `get_clock()`, не `time.time()`; див. нижче “Timebase”).

**Acceptance criteria:**
- у backtest/e2e видно повторні спроби після defer (по `order_log_*.jsonl` та/або по логам з `retry_key`).

---

### Phase 3 (P0): ✅ DONE — Portfolio state contract + timebase (ExposureGuard / PositionTracking)

**Проблема (підтверджено):**
- `ExposureGuard.can_open()` fail-closed повертає `EQUITY_UNKNOWN`, якщо немає `equity_free_usdt` (`apps/reference/domains/execution_position/exposure_guard.py:470–473`).  
- В логах є `ON_PORTFOLIO_DEBUG … equity_raw=MISSING` (наприклад `logs/aurora_core.log.2:1432`).  
- Причина: `PositionTracking.on_trade_executed` формує payload без `equity_free_usdt` (`apps/reference/domains/position_tracking/position_tracking.py:240–265`), тоді як інші гілки (account/balance update) це поле додають (`apps/reference/domains/position_tracking/position_tracking.py:403+`).

**Що змінити (суть):**
- привести `EVT:PORTFOLIO_STATE_UPDATED` до стабільної мінімальної схеми (орієнтир: `apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json`), особливо `equity_free_usdt`, `positions_last_ts_ms`, `open_positions_*`.
- у backtest/live усунути змішування timebase (частина коду використовує wall-clock, частина — `get_clock()`/MockClock). TTL/staleness мають рахуватись в одній системі часу.

**Очікуваний ефект на поведінку:**
- зникнуть випадкові fail-closed блокування через “equity missing”;
- staleness/TTL стануть передбачуваними, особливо в backtest.

**Ризики:**
- інші модулі могли неявно покладатися на “legacy” поля (наприклад `equity` як proxy). Потрібна backward compatibility або чітка версія схеми.

**Acceptance criteria:**
- `ExposureGuard` не отримує payload без `equity_free_usdt` в нормальному потоці;
- немає `equity_raw=MISSING` в `ON_PORTFOLIO_DEBUG` у backtest прогоні.

---

### Phase 4 (P1): ✅ DONE — ExecutionPosition — deferred brackets (LIMIT) + cancel cleanup

**Реалізовано:**
- `pending_brackets_wal.py` — WAL persistence для `_pending_brackets`
- fsm.py інтегровано: WAL write при store/clear, rehydration в `__init__`
- Тести: `tests/vfoundation/test_pending_brackets_wal_v1.py` — 8/8 passed

**Проблема (підтверджено, RESOLVED):**
- `_pending_brackets` для LIMIT живе в RAM (`apps/reference/domains/execution_position/fsm.py:3049–3069`) і використовується на fill (`apps/reference/domains/execution_position/fsm.py:1595–1596`).  
  Рестарт між “LIMIT placed” і “FILL” може дати позицію без TP/SL (в live — критично).
- Cancel-on-regime-change робить `watchdog.on_order_cancel(...)`, але **не емiтить cancel event** і тому `_handle_cancel_event()` (який чистить `_pending_brackets`) може не викликатись (`apps/reference/domains/execution_position/fsm.py:904–976` vs cleanup у `apps/reference/domains/execution_position/fsm.py:3921–3925`). У логах немає “Cleaning up pending brackets …” → ризик сміття стану.

**Що змінити (суть):**
- зробити persistence `_pending_brackets` (WAL/kv) + rehydrate при старті;
- гарантувати cleanup при cancel (або emit відповідного cancel event у внутрішній bus, або прямий cleanup в місці cancel).

**Очікуваний ефект на поведінку:**
- LIMIT entry стає fail-safe до рестарту;
- менше “висячого” стану.

**Ризики:**
- WAL/kv збільшиться; потрібна ідемпотентність і GC.

**Acceptance criteria:**
- інтеграційний тест: рестарт між place LIMIT і fill → TP/SL все одно ставляться (або позиція закривається fail-safe).

---

### Phase 5 (P1): ✅ DONE — Watchdog — “ACK received for unknown order …” (шум vs сигнал)

**Проблема (підтверджено):**
- watchdog попереджає, якщо ACK приходить для `order_id`, якого нема в `pending_orders` (`apps/reference/domains/execution_position/watchdog.py:226–230`).  
- У ExecPosFSM є **дубльований шлях ACK**:
  - після `place_*` код одразу викликає `watchdog.on_order_ack(entry_order_id)` (`apps/reference/domains/execution_position/fsm.py:3045`);
  - потім приходить реальний `EVT:ORDER_ACK` і `_on_order_ack` ще раз викликає `watchdog.on_order_ack(order_id)` (`apps/reference/domains/execution_position/fsm.py:1508`).
  В результаті другий ACK часто виглядає “unknown” (бо ордер уже в `acked_orders`, а `on_order_ack` перевіряє тільки `pending_orders`).
- Bracket-ордера (TP/SL) не трекаються watchdog’ом (`track_order_placed` викликається лише для entry), тому їх ACK теж “unknown”.

**Що змінити (суть):**
- або чітко визначити, що “ACK” для polling/backtest — це лише факт “order accepted” від adapter, і **не прокидати EVT:ORDER_ACK**, або не викликати `on_order_ack` вручну і чекати події;
- або розширити watchdog: вважати ACK валідним і для `acked_orders` (idempotent no-op), і/або трекати bracket-ордера окремо;
- знизити severity/перетворити warning на debug тільки після того, як контракт стане однозначним (інакше це маскує реальні аномалії).

**Очікуваний ефект на поведінку:**
- прибирається шум у логах;
- watchdog-сигнали знову стануть діагностично цінними.

---

## 3) План тестування (що саме перевіряти)

### 3.1 Unit (DecisionMaking QoS)

1) **Partition correctness**  
Вхід: два `strategy_id` для одного `symbol`.  
Очікування: cooldown/rate-window в одному strategy не блокує інший.

2) **Defer timestamp correctness**  
Вхід: під час активного cooldown QoS mode=defer.  
Очікування: `next_allowed_ts > now_ms` і приблизно дорівнює `last_decision + cooldown`.

3) **Reason code correctness**  
Вхід: cooldown активний.  
Очікування: reason == `SYMBOL_COOLDOWN_ACTIVE`, а не `RATE_LIMIT_EXCEEDED`.

### 3.2 Contract tests (Portfolio schema)

1) **Schema minimum**  
Для кожного джерела portfolio update (trade_executed/account_update/balance_update) перевірити наявність `equity_free_usdt` та `positions_last_ts_ms`.

2) **Timebase**  
У backtest режимі перевірити, що `positions_last_ts_ms` узгоджений з MockClock / `get_clock()`.

### 3.3 Integration/E2E (Defer → Retry)

1) Е2Е прогін: сгенерувати `EVT:INTENT_DEFERRED` і перевірити, що система повторно емiтить оригінальний event (або чітко блокує, якщо retry не підтримується).  
2) Перевірити bounded retries (max_attempts) і відсутність “зомбі” задач.

### 3.4 Integration (ExecPosFSM LIMIT deferred brackets)

1) **Restart survival**  
Place LIMIT entry → “restart” (очистити RAM стан) → fill → brackets мають бути розміщені або позиція закрита fail-safe.

2) **Cancel cleanup**  
Place LIMIT entry → cancel (regime change / TTL) → `_pending_brackets` не має містити запису для цього entry.

### 3.5 Observability regression

- watchdog: відсутність “ACK unknown” на нормальному happy-path;
- відсутність `equity_raw=MISSING` в `ON_PORTFOLIO_DEBUG`;
- `order_log_*.jsonl`: послідовність “INTENT → ORDER_PLACED → (FILL) → BRACKETS”.

---

## 4) Критичні невирішені питання (блокери дизайну)

1) **Хто SSOT-власник retry?**  
`RetryScheduler` існує (`apps/reference/retry_scheduler.py`), але нині не інтегрований в main. Чи повертаємо binding, чи виносимо retry в DM, чи відмовляємось від defer?

2) **Єдина timebase**  
Який стандарт: `get_clock()`/MockClock чи wall-clock? Зараз змішано (особливо видно в backtest логах). TTL/стейлнес мають бути в одній системі часу.

3) **Portfolio schema v1 — “мінімально необхідне”**  
Чи робимо `equity_free_usdt` обов’язковим всюди (краще для fail-closed), чи дозволяємо fallback (ризиковано, може відкрити торгівлю без реальної equity).

4) **Watchdog контракт**  
ACK приходить як подія з біржі, чи “синтетично” після REST accept? Чи трекаємо bracket-ордера? Чи watchdog взагалі увімкнений в backtest (є `disable()` у watchdog, але не видно виклику)?

5) **QoS semantics vs arbitration**  
QoS має застосовуватись до сигналів до/після arbitration? (зараз QoS gate стоїть після flip gate у strategy gateway). Чи правильно це для мульти-стратегій?

---

## 5) Вплив змін (модулі → поведінка)

- `apps/reference/domains/decision_making/decision_making.py`  
  Вплив: частота/порядок trade intents, QoS defer/enforce, reason codes, метрики.
- `apps/reference/main.py` + `apps/reference/retry_scheduler.py`  
  Вплив: чи існує реальний retry після `EVT:INTENT_DEFERRED`; bounded retries; thread-safety.
- `apps/reference/domains/position_tracking/position_tracking.py`  
  Вплив: якість portfolio snapshots; робота exposure/risk gates; backtest детермінізм.
- `apps/reference/domains/execution_position/fsm.py`  
  Вплив: безпека LIMIT entry (deferred brackets), cancel semantics, WAL/persistence.
- `apps/reference/domains/execution_position/watchdog.py`  
  Вплив: правильність timeout tracking, шум/сигнал у логах.
- `apps/reference/domains/execution_position/exposure_guard.py`  
  Вплив: fail-closed поведінка при відсутніх полях; точність exposure обмежень.
- `config/aurora/domains.yaml`, `config/aurora/trading.yaml`  
  Вплив: TTL, bounds для regime_adaptation, QoS параметри.

---

## 6) Чому це треба реалізовувати (обґрунтування)

- **QoS split-brain** робить систему непередбачуваною: неможливо пояснити, чому інколи блокується/пропускається сигнал; це ризик прод-інцидентів і “невідтворюваних” backtest результатів.
- **Defer без retry** — це прихований drop грошей: система думає “перенесла”, але фактично “втратила”.
- **Portfolio schema mismatch** підриває fail-closed: або блокує валідні трейди (false negatives), або змушує робити небезпечні fallback-и.
- **Deferred brackets в RAM** — класична execution safety проблема (особливо для LIMIT): при рестарті можна отримати naked позицію.
- **Шумні warnings** маскують реальні аномалії: коли “unknown ACK” трапляється постійно, справжній інцидент загубиться в шумі.

---

## 7) Критика плану (ризики/вартість/альтернативи)

- План торкається **контрактів між доменами**, тому регресії можливі навіть при “малих” патчах. Потрібен поетапний rollout (shadow → enforce) і contract-тести.
- Відновлення retry може збільшити активність (більше подій/виконань), тому треба bounded retries + метрики.
- Portfolio schema виправлення може потребувати **версіонування** або backward-compat полів, інакше сторонні споживачі (risk/monitoring) можуть зламатися.
- Watchdog “заспокоїти” простим пониженням log-level — погана ідея без виправлення контракту (це приховає реальні проблеми).

---

## 8) Definition of Done (мінімальний)

1) QoS gateway: check/write в одній partition, `next_allowed_ts` коректний, reason-коди валідні.
2) `EVT:INTENT_DEFERRED` або реально ретраїться, або система ніколи не емiтить “defer” без механізму повтору.
3) `EVT:PORTFOLIO_STATE_UPDATED` завжди містить `equity_free_usdt` і узгоджений `positions_last_ts_ms`.
4) LIMIT deferred brackets переживають рестарт або мають fail-safe політику.
5) Watchdog warnings “unknown ACK” відсутні на нормальному сценарії або мають чітко визначену семантику.

