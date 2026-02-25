# vFoundation + Aurora: Інтеграція системи як єдиного організму

**Дата оновлення:** 2026-02-24  
**Гілка верифікації:** `backtest_1`  
**Статус інтеграції:** Partially Operational (core контури працюють, але частина Phase 14/16 артефактів не підключена в runtime)

---

## 1) Для чого це все потрібно

Система об’єднує:
- **бізнес-домени Aurora** (market data, feature engineering, risk, decision, execution),
- **інфраструктурне ядро vFoundation** (FSM/event bus, protocol, WAL/DR, idempotency, observability, security, CLI),

щоб отримати **керовану, відтворювану, fail-closed** платформу для прийняття та виконання торгових рішень.

Ключова цінність:
1. **Контрактність:** рішення й події проходять через стандартизований `Message`-envelope.
2. **Відтворюваність:** WAL + replay дають аудит і DR-відновлення.
3. **Керованість:** CLI/тести/quality gates дозволяють контролювати drift, цілісність та регресії.
4. **Операційна безпека:** idempotency, retry/circuit breaker, policy gates.

---

## 2) Що саме під’єднано зараз (фактична карта інтеграції)

## 2.1 Composition root

Точка композиції runtime:
- `apps/reference/main.py`

У ній підтверджено підключення:
- `FSMCore` (`vfoundation.core`),
- `ExecPosFSM` та доменів Aurora,
- bootstrap-компонентів:
  - `AsyncLoopRuntime` (`apps/reference/bootstrap/async_runtime.py`),
  - `build_live_domains(...)` (`apps/reference/bootstrap/domain_builder.py`),
  - `resolve_backtest_max_ticks(...)` (`apps/reference/bootstrap/backtest_runner.py`),
- DR/ops-компонентів (`vfoundation.dr.*`, `WALGarbageCollector`),
- системних перевірок startup/policy.

## 2.2 Доменний оркестратор

`build_live_domains(...)` збирає в один узгоджений bundle:
- account balance,
- market data (connector/proxy за конфігом),
- feature engineering,
- risk management,
- position tracking,
- execution position FSM,
- decision making,
- regime detector,
- csv recorder,
- bar aggregator (опційно).

Це забезпечує, що домени не ініціалізуються хаотично по коду, а створюються централізовано і типізовано.

## 2.3 Async orchestration

`AsyncLoopRuntime` дає thread-safe API:
- `start()`
- `submit(coro)`
- `run(coro)`
- `stop()`

Це прибирає розрізнене керування event loop у різних місцях і стабілізує інтеграцію з async-джерелами.

## 2.4 CLI як operational surface

CLI entrypoint:
- `python -m vfoundation.cli.vfound`

Активні команди:
- `schema`
- `dict lint`
- `dict validate`
- `rfc`
- `simulate`
- `replay`
- `drift`
- `trace`
- `init`

Критично: команда `drift` завантажує `apps/reference/domains/execution_position/drift_monitor.py` динамічно по виправленому шляху.

---

## 3) Як це працює в потоці (end-to-end)

Базовий життєвий цикл повідомлення:
1. Market/event input потрапляє в доменний контур.
2. Через `FSMCore` і `Message` контракти проходить між доменами.
3. Рішення (`DEC/CMD`) обробляються execution-контуром.
4. Ключові події пишуться в WAL.
5. Observability-шар формує why-chain/метрики/алерти.
6. CLI (`replay/trace/drift`) читає WAL і дає audit/debug ззовні.

Таким чином runtime, observability і DR працюють на одному контрактному протоколі.

---

## 4) Що перевірено практично (а не лише “по коду”)

Під час верифікації пройшли:

1. Базовий vFoundation gate:
- `pytest tests/vfoundation -q` → **1073 passed**

2. Інтеграційні сценарії (DR + runtime + CLI):
- `tests/dr/test_dr_loader.py`
- `tests/runtime/test_task24_retry_scheduler_contracts.py`
- `tests/integration/test_retry_scheduler_integration_v1.py`
- `tests/runtime/test_task24_policy_gates.py`
- `tests/vfoundation/cli/test_cli_main.py`
- `tests/vfoundation/cli/test_cli_drift_coverage.py`

Результат: **56 passed**.

3. E2E сценарій bounded retry scheduler:
- `tests/e2e/test_s5_retry_scheduler_bounded.py`

Результат: **3 passed**.

4. Живий запуск CLI:
- `python -m vfoundation.cli.vfound --help` (успішно, команди доступні).

---

## 4.1) Truth Matrix: що реально підключено, а що ні

Нижче — перевірено по коду і пошуку використань, не по чеклісту:

1. **DecisionMaking decomposition** — **реально виконано**.
  - `apps/reference/domains/decision_making/decision_making.py` є фасадом + модульна декомпозиція по окремих файлах.

2. **ExecutionPosition decomposition** — **не виконано**.
  - `apps/reference/domains/execution_position/fsm.py` = **4687 рядків** (моноліт збережено).

3. **DomainBridge integration** — **підключено в runtime**.
  - `decision_making` і `execution_position` створюють `DomainBridge`, реєструють `register_health_fn(...)` і викликають `emit_status()`.

4. **Typed payloads (`vfoundation/core/payloads.py`)** — **майже не використовується в runtime apps/reference**.
  - Імпорти/виклики `vfoundation.core.payloads` / `Message.typed_payload()` у `apps/reference/**` не знайдені.

5. **FSMv2 enhancements (`validate_reachability`, `to_dot`)** — **є в бібліотеці та тестах, але не інтегровано в operational flow**.
  - Немає автозапуску в startup, і немає окремої CLI-команди для цього.

6. **Protocol migration (`migrate_pld_v1_to_v2`)** — **існує, але використовується лише в тестах**.
  - Runtime-виклики в `apps/reference/**` відсутні.

---

## 5) Як користуватись (практичний мінімум)

## 5.1 Щоденний health-check

1. Перевірка контрактів словників:
```bash
python -m vfoundation.cli.vfound dict validate --report ops/reports/dict_validate.json
```

2. Базовий regression gate:
```bash
python -m pytest tests/vfoundation -q
```

3. Перевірка CLI surface:
```bash
python -m vfoundation.cli.vfound --help
```

## 5.2 Debug конкретного RID

1. Трасування подій:
```bash
python -m vfoundation.cli.vfound trace <RID>
```

2. Реплей з integrity:
```bash
python -m vfoundation.cli.vfound replay <RID> --shadow
```

3. Drift-аналіз по WAL:
```bash
python -m vfoundation.cli.vfound drift --from-wal --window-sec 1.0
```

## 5.3 Генерація схем

```bash
python -m vfoundation.cli.vfound schema
```

Результат: оновлена `schemas/message_v1.json` для інструментів і валідації.

---

## 6) Навіщо кожен ключовий шар

1. **Protocol (`Message`)** — єдина мова обміну між доменами.
2. **FSMCore/FSMv2** — керований event-driven orchestration замість ad-hoc callbacks.
3. **WAL/Replay/DR** — відновлюваність і доказовість рішень.
4. **Idempotency + CB/Retry** — захист від дублювань, timeout storms і нестабільних зовнішніх API.
5. **Observability (why-chain, alerts, OTLP foundation)** — пояснюваність і операційний контроль.
6. **CLI** — стандартна операційна панель без прямого втручання в код.

---

## 7) Поточні обмеження (важливо)

1. Частина компонентів залишаються у **foundation/stub**-стані (наприклад, окремі observability/export елементи).
2. Є попередження безпечності для dev-оточення (наприклад, default токени/ключі) — для production потрібні явні env secrets.
3. Частина roadmap-фаз (особливо schema versioning v2 infra і cross-cutting production contracts) потребують завершення для повної enterprise-готовності.
4. Частина Phase 14 артефактів формально реалізована, але не вбудована в runtime-шлях (ознака checklist-driven completion).
5. Ключовий моноліт `execution_position/fsm.py` лишається головним ризиком підтримуваності.

---

## 8) Рекомендований operational ритуал

Перед релізом/зміною:
1. `dict validate`
2. `pytest tests/vfoundation -q`
3. цільові integration/e2e тести для зміненого контуру
4. `vfound replay`/`vfound drift` на тестовому WAL

Після релізу:
1. моніторинг why-chain/alerts,
2. періодичний drift-аудит,
3. DR smoke (`replay`) на контрольних RID.

---

## 9) Висновок

Станом на цю перевірку система працює як **частково інтегрований контур**:
- ядро runtime/DR/CLI стабільне і підтверджене тестами,
- але частина Phase 14/16 компонентів існує переважно як бібліотечні або тестові артефакти без runtime-використання.

Практично це означає: база придатна до роботи, але для чесних “100% blueprint execution” потрібно окремим циклом добудувати runtime-інтеграцію (payload typing, FSMv2 validation hooks, protocol migration hooks) і розбити `execution_position` моноліт.
