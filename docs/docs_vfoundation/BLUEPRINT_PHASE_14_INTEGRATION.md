# vFoundation Engineering Blueprint — Phase 14.5: Meta-FSM & Orphan Domains Integration

**Дата:** 2026-02-24
**Статус:** Draft (Ready for Execution)
**Ціль:** Довести архітектуру до повної відповідності `Constitution_FSM v2.2`, перетворивши існуючий `MetaFSMv2` на центральний координатор (Warm/Cold Path) і включивши всі ізольовані Data/ML домени в контрактний простір FSM.

---

## 1. Проблема та Обґрунтування (The Why)

### 1.1 Неповний Meta-FSM
У гілці є файл `vfoundation/core/meta_fsm_v2.py` (265 LOC). Він містить правильну логіку (стани `NORMAL`, `LOW_RISK`, `COOLDOWN`, `DEGRADED`) і реагує на `EntropyMonitor`.
**Але проблема в тому, що він ізольований.**
- Сигнали від нього (`CMD:SWITCH_TO_LOW_RISK_MODE`) генеруються, але ніким не перехоплюються (routing не обробляє їх глобально).
- `TopologyAuditor` **вже існує** (`vfoundation/obs/topology_auditor.py`, 159 LOC) — він порівнює verb_registry owners vs зареєстровані домени та виявляє drift. **Але** його функціональність обмежена: немає моніторингу healthcheck Redis, WebSocket latency та інших runtime метрик. Тому перехід у `DEGRADED` від `EVT:TOPOLOGY_DRIFT_DETECTED` працює лише для contract drift, не для infrastructure drift.

### 1.2 Orphan Domains (Домени поза FSM)
Аудит коду показав, що 4 домени не використовують `vfoundation` і спілкуються прямо через виклики функцій або свої власні канали:

| Домен | Scope | Пріоритет інтеграції |
|--------|-------|------------------------|
| `neocortex` | Deep Learning, 15+ файлів | **Високий** — впливає на торговельний капітал |
| `alpha_search` | Alpha scoring | **Високий** — `decision_making` імпортує з нього напряму |
| `inflight_reconcile` | State reconciliation | **Критичний** — консистентність позицій |
| `exchange_filters` | Data filtering (3 файли) | **Низький** — утилітарний, може залишитись як pure utility |

> **Верифікований факт:** `decision_making.py` має **1 підтверджений cross-domain import** — з `alpha_search` (line 85), не з `neocortex`.

### 1.3 Scope Boundary: vFoundation infra vs App-level

| Що | Scope | Відповідальність |
|------|-------|------------------|
| FSM Adapters (`*_fsm_adapter.py`) | **vfoundation** | Контрактна обгортка, schema validation |
| TopologyAuditor розширення | **vfoundation** | Infrastructure health metrics |
| Confidence thresholds (>0.9 для LOW_RISK) | **App-level** | Доменна логіка |
| Domain wiring (`main.py`) | **App-level** | Bootstrap/DI |
| `data_ref` S3 зберігання | **App-level** | Infrastructure config |

**Чому це критичний ризик?**
Deep Learning домен (`neocortex`) здатний приймати рішення, які впливають на торговельний капітал. Якщо він збоїть або генерує garbage-показники, Meta-FSM про це не дізнається. Він не має `why_chain`, не пишеться у WAL для disaster recovery, і не може бути зупинений через Circuit Breaker.

---

## 2. RoadMap: Повноцінний Meta-FSM Coordinator

Ми маємо зробити `MetaFSMv2` справжнім "Оком Саурона" (System-wide Coordinator), що працює у Warm-Path (фонові перевірки кожні X секунд, а не на кожному тику ордеру).

### 2.1 Розширення існуючого `TopologyAuditor`
*Відповідно до Phase 4 та Constitution §7.*

> **Факт:** `TopologyAuditor` вже існує (`vfoundation/obs/topology_auditor.py`, 159 LOC). Він порівнює verb_registry owners vs зареєстровані домени (contract drift). Не створюємо з нуля — розширюємо.

1. **Розширити `vfoundation/obs/topology_auditor.py`** новими health probes.
2. **Нова логіка (infrastructure drift):** Аудитор періодично читає `EntropyMonitor`, перевіряє ping до біржових WebSocket-ів (latency), моніторить healthcheck Redis та бази даних.
3. **Емісія:** Раптове зростання error_rate або втрата 2+ WebSocket з'єднань -> `bus.emit("EVT:TOPOLOGY_DRIFT_DETECTED", why="Lost 2 WS connections to Binance")`.

### 2.2 Грифування (Subscribing) Доменів на Meta-FSM Сигнали
Коли `MetaFSMv2` переходить у `LOW_RISK` або `DEGRADED`, він випромінює `CMD:SWITCH_TO_LOW_RISK_MODE`.
1. **Дія:** `decision_making` та `execution_position` повинні зареєструвати handler для цього CMD.
2. **Логіка в `decision_making`:** При переході в LOW_RISK дозволяються лише сигнали з confidence > 0.9.
3. **Логіка в `execution_position`:** При переході в DEGRADED вмикається "Reduce Only" (можна лише закривати позиції, відкриття нових блокується із `WhyCode.REGIME_BLOCKED`).

### 2.3 Wiring in Main
У `__main__.py` або системному бутстрапері потрібно явно запустити `MetaFSMv2` як background task (`asyncio.create_task()`), яка викликає `meta.tick()` кожні 5 секунд.

---

## 3. RoadMap: Міграція Orphan Domains ("Обгортка в Контракти")

Оскільки ML-домени можуть працювати на C++ або в окремих процесах (через ZeroMQ/gRPC), ми інтегруватимемо їх через **FSM Adapters**.

### 3.1 `neocortex` FSM Bridge
`neocortex` генерує прогнози (inference) і має складну логіку навчання.
1. **Зміни у `neocortex`:** Не вимагаємо переписувати DL-моделі на FSM. Замість цього створюємо `neocortex_fsm_adapter.py`.
2. **Контракт входу:** Адаптер слухає `EVT:BAR_CLOSED` (надійшов новий бар). Збирає feature vector, викликає модель.
3. **Контракт виходу:** Отримавши inference, адаптер робить:
   ```python
   fsm.emit(
       "EVT:INFERENCE_READY",
       pld={"model": "v7_ensemble", "predictions": [...]},
       why="periodic inference completed"
   )
   ```
4. `decision_making` більше не імпортує `neocortex` напряму. Він слухає `EVT:INFERENCE_READY`.

### 3.2 `alpha_search` FSM Bridge
Домен відповідає за перебирання сотень стратегій та пошук Alpha-сигналів.
1. Перетворити результат його роботи на контрактний Event: `EVT:ALPHA_SIGNAL_DISCOVERED`.
2. Кожен згенерований сигнал повинен мати `trace_id` для відстеження `why_chain`. Якщо цей сигнал пізніше призведе до Trades — у нас буде 100% End-to-End trace (від сирих даних до ордера).

### 3.3 `inflight_reconcile` 
Це критичний домен для забезпечення консистентності позицій (звіряє локальний стан у WAL із станом на Binance).
1. Зробити його підпорядкованим `MetaFSM`.
2. Якщо `inflight_reconcile` знаходить розбіжність (Drift) між WAL і біржею більше ніж на 0.01%, він емітить `EVT:STATE_DRIFT_DETECTED`.
3. `MetaFSMv2` приймає це і негайно переводить систему в `DEGRADED` (зупиняє торгівлю, поки людина або автоматика не виправить стейт).

---

## 4. Дорожня Карта Виконання (Execution Flow)

### Етап 1: Meta-FSM Топологія (1 тиждень)
1. Розширити існуючий `TopologyAuditor` (159 LOC) збором infrastructure метрик (ping, health).
2. Налаштувати background loop для `MetaFSMv2.tick()` в `main`.
3. Реалізувати handlers для `CMD:SWITCH_TO_LOW_RISK_MODE` у всіх критичних доменах.
4. *Verification:* Chaos test -> штучно симулюємо відключення Redis -> `TopologyAuditor` бачить це -> MetaFSM генерує CMD -> execution-domain зупиняє маркет-ордери.

### Етап 2: ML/Data Domain Contracts (1-2 тижні)
1. Створити нові Verbs у `apps/reference/dictionaries/verb_registry_v1.yaml` (SSOT): `EVT:INFERENCE_READY`, `EVT:ALPHA_SIGNAL_DISCOVERED`, `EVT:STATE_DRIFT_DETECTED`.
2. Створити Typed Payloads для них (див. Blueprint 14.3).
3. Написати `_fsm_adapter.py` для кожного Orphan Domain.
4. Змінити `decision_making` щоб він споживав передбачення через `FSMCore.listen("EVT:INFERENCE_READY")`, а alpha-сигнали через `FSMCore.listen("EVT:ALPHA_SIGNAL_DISCOVERED")`, замість прямого import з `alpha_search`.

### Етап 3: Disaster Recovery for Data (1 тиждень)
1. Упевнитися, що події `EVT:INFERENCE_READY` містять поле `data_ref` (до масивних tensor-об'єктів/numpy arrays, збережених у S3 або локальному k/v сховищі), щоб не перевантажувати FSM та WAL мегабайтами даних.
2. *Verification:* Відновлюємо систему з WAL — система повинна коректно відновити `why_chain` для будь-якого рішення, маючи доступ до inference outputs через `data_ref`.

---

## 5. Критерій Успіху

1. `MetaFSMv2` керує системою: зміна глобального режиму поширюється на всі домени через `FSMCore.emit()`.
2. Домени `neocortex`, `alpha_search`, `inflight_reconcile` більше **не імпортуються** у `decision_making` чи інші hot-path домени.
3. Усі ML-прогнози та висновки щодо позицій проходять через WAL як FSM-події (`why_chain coverage > 95%`).
4. Механізм `fail-closed` повноцінно працює при Topology Drift або розбіжності стейту біржі та локальної бази.
