# Незалежний архітектурний аудит Blueprint Phases 9–14

**Дата:** 2026-02-21  
**Роль:** Staff Architect (незалежний рев'ю)  
**Об'єкт:** `docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md` v1.2 (DRAFT)  
**Метод:** Full code + doc review, Constitution cross-reference

---

## Executive Summary
Blueprint структурований і пріоритизований краще за попередні плани, але має критичний розрив між "план каже виправлено" і фактичним станом репозиторію. Найбільший ризик — хибне відчуття готовності exactly-once/DR: активний gate (`tests/vfoundation`) зелений, але production-критичні сценарії Redis/Lua і cross-suite CI лишаються незакритими. Phase 14 (envelope refactor) у поточному вигляді має високий ризик breakage для downstream-коду без реальної migration-інфраструктури. Рекомендація: **No-Go для прямого старту Phase 9**, тільки після короткого Pre-Phase 9 hardening-блоку з 6 блокерами нижче.

---

## 1. Constitution Compliance Matrix

| Constitution | Статус після Phase 14 (якщо виконати Blueprint) | Коментар / gap |
|---|---|---|
| §1 Ціль та охоплення | PARTIAL | План покриває велику частину vFoundation, але доменні інтеграції залишаються фрагментованими. |
| §2 Базис v2.1 | PARTIAL | Є сумісність на рівні термінів, але фактичний контракт Message дрейфує від spec. |
| §3 Інваріанти | PARTIAL | Registry-first декларується (`BLUEPRINT_PHASES_9_14.md:1506`), але registry фактично не оновлений для RECONCILE/REPAIR. |
| §4 Hot/Cold path | PARTIAL | Є ідея perf harness (Phase 12.3), але без чіткої CI-політики SLO/регресій. |
| §5 Message Protocol | PARTIAL/HIGH RISK | `Message.v=1` (`vfoundation/core/protocol.py:24`) vs Constitution `v=2` (`docs/docs_vfoundation/Constitution_FSM.md:58`); Phase 14.3 додає breaking risk. |
| §6 Routing/TTL | PARTIAL | Базова логіка є, але idempotency у Router in-memory (`vfoundation/core/routing.py:71`), не distributed. |
| §7 Нові компоненти v2.2 | PARTIAL | Entropy/Topology/Intent є в коді, Latent Embeddings лишається лише планом/stub (Phase 13.5). |
| §8 DR/Resilience | PARTIAL | Є WAL hash-chain, але немає WORM/S3 архіву (TODO в `vfoundation/dr/wal_gc.py:63`). |
| §9 Observability | PARTIAL | План 11.x великий, але зараз немає consumer-ланцюга для `why_explain_ref` (лише поле у model). |
| §10 Tooling/Automation | PARTIAL | CLI не відповідає переліку §10.2 повністю (`vfoundation/cli/vfound/__main__.py:32`, `:400`). |
| §11 Security/Data | PARTIAL | Signing перевіряється, але KMS/WORM/Object Lock не реалізовані фактично. |
| §12 Testing/Quality | PARTIAL | `tests/vfoundation` стабільні (531 passed), але broader suite має 5 collection errors, chaos/DR quality gates ще не існують. |

---

## 2. Верифікація проти коду

### Phase 9.0–9.4

1. **Claim: path drift fixed** (`BLUEPRINT_PHASES_9_14.md:68-84`) — **спростовано частково (fix неповний)**.  
Actual:
```python
# vfoundation/cli/vfound/__main__.py:288
drift_monitor_path = (_cli_root / "apps" / "monitoring" / "drift_monitor.py")
```
`_cli_root` резолвиться в `.../Phenix/vfoundation`, не repo root; отже навіть proposed `.../apps/reference/...` під `_cli_root` лишиться non-existent. Команда реально падає: `python -m vfoundation.cli.vfound drift` -> `FileNotFoundError` на `...\vfoundation\apps\monitoring\drift_monitor.py`.

2. **Claim: deps declared in requirements** (`BLUEPRINT_PHASES_9_14.md:46-56`) — **спростовано**.  
`requirements.txt:1-18` не містить `redis`, `PyNaCl`, `fakeredis[lua]`.  
При цьому `vfoundation/pyproject.toml:19-22,30` містить `PyNaCl`, `redis`, `fakeredis` (без `[lua]`). Dependency source of truth роздвоєний.

3. **Claim: rid passthrough gap exists and needs fix** (`BLUEPRINT_PHASES_9_14.md:107-155`) — **підтверджено**.  
`FSMCore.emit` не приймає `rid` (`vfoundation/core/fsm_core.py:41`) і створює `Message(...)` без `rid` (`vfoundation/core/fsm_core.py:56-64`), тоді як `Message.rid` автогенерується (`vfoundation/core/protocol.py:29`).

4. **Claim: MockExecutionAdapter moved to tests/conftest** (`BLUEPRINT_PHASES_9_14.md:413-429`) — **спростовано (ще не зроблено)**.  
`tests/vfoundation/conftest.py` відсутній; production mock лишився у `vfoundation/core/adapters/execution_adapter.py:468`; тести імпортують його напряму (`tests/vfoundation/core/test_execution_adapter.py:12-19`).

5. **Claim: legacy FSM cleanup ready** (`BLUEPRINT_PHASES_9_14.md:444-462`) — **частково**.  
`vfoundation/core/fsm.py` існує (`vfoundation/core/fsm.py:1-43`) і ще використовується (`tests/test_coverage_final_push.py:15`).

6. **LOC claim mismatch** (`BLUEPRINT_PHASES_9_14.md:169,282,631`) — **частково спростовано**.  
Фактично: `__main__.py` 420 LOC, `redis_store.py` 553 LOC, `acl.py` 240 LOC (`rg -n "." ... | tail`). План каже 421/554/237.

### Phase 10.x

7. **Claim: dedicated test suites planned** (`BLUEPRINT_PHASES_9_14.md:498,573,592,610`) — **в коді відсутні target файли**.  
Немає: `tests/vfoundation/obs/test_debug_api.py`, `tests/vfoundation/core/test_redis_protocol.py`, `tests/vfoundation/obs/test_order_logger.py`, `tests/vfoundation/dataref/test_streaming_io.py`.

8. **Coverage reality** — **ризик підтверджено**.  
Поточний run: `pytest tests/vfoundation -q --cov=vfoundation` -> 531 passed, total 78%; `debug_api.py` 30%, `redis_store.py` 0%, `redis_protocol.py` 0%, `fsm.py` 0%.

9. **ExchangeACL stub marker needed** (`BLUEPRINT_PHASES_9_14.md:629-631`) — **підтверджено**.  
Навіть при `shadow_mode=False` викликається `_stub_submit` (`vfoundation/adapters/exchange/acl.py:98-101`).

### Phase 11.x

10. **Claim: XAI/OTLP/alert foundation to be added** (`BLUEPRINT_PHASES_9_14.md:676,775,822`) — **зараз відсутні модулі**.  
Немає `vfoundation/obs/xai_store.py`, `why_chain_coverage.py`, `otlp_exporter.py`, `alert_hooks.py`.

11. **Consumer gap** — **підтверджено**.  
`why_explain_ref` існує лише у model (`vfoundation/core/protocol.py:38`), практичних producer/consumer в runtime не знайдено.

### Phase 12.x

12. **DR timing plan існує тільки як synthetic design** (`BLUEPRINT_PHASES_9_14.md:931-983`) — **ризик реалістичності**.  
План міряє simulated recovery, але не містить вимоги до реального WAL replay benchmark на production-like I/O.

13. **Broader CI readiness gap** — **підтверджено**.  
`pytest tests -q --ignore=tests/backtest` дає 5 collection errors (зокрема `vfoundation.dr`/`vfoundation.core` package import issues).

### Phase 13.x

14. **Registry-first precondition for RECONCILE/REPAIR** (`BLUEPRINT_PHASES_9_14.md:1061-1072`) — **фактично не виконано**.  
`apps/reference/dictionaries/verb_registry_v1.yaml` не містить `verb: RECONCILE` / `verb: REPAIR` (search -> `NO_MATCH`). Це конфлікт із `.github/copilot-instructions.md:14-37`.

15. **WAL archive contract** (`BLUEPRINT_PHASES_9_14.md:1128-1185`) — **відсутній в коді**.  
Немає `vfoundation/dr/wal_archive.py`; у GC лишився TODO (`vfoundation/dr/wal_gc.py:63-64`).

16. **CLI gap closure §10.2** (`BLUEPRINT_PHASES_9_14.md:1191-1221`) — **неповне навіть у плані**.  
Фактично планує лише `init`; `migrate/test gen/analyze` не доведені до конкретної імплементації. Поточний CLI має лише `schema,rfc,simulate,replay,drift,trace,dict` (`vfoundation/cli/vfound/__main__.py:32,44,60,153,165,187,268,400`).

17. **Domain integration claim** (`BLUEPRINT_PHASES_9_14.md:1515-1523`) — **неповний перелік**.  
План каже 5 доменів без vfoundation; фактично 6: `alpha_search`, `exchange_filters`, `inflight_reconcile`, `neocortex`, `regime_allowlist`, `snapshot_scheduler`.

### Phase 14.x

18. **Envelope refactor migration risk** (`BLUEPRINT_PHASES_9_14.md:1344-1368`) — **HIGH**.  
Top-level поля вже широко використовуються (`oco_group_id` у `apps/reference/domains/execution_position/fsm.py:3235,3266,3284,...`; `vfoundation/core/protocol.py:46-49`).

19. **Migration command mismatch** (`BLUEPRINT_PHASES_9_14.md:1360`) — **спростовано поточним CLI**.  
План вимагає `vfound migrate message-envelope`, але `migrate` command відсутній у CLI.

20. **Backward compatibility infra не готова** — **підтверджено**.  
У `vfoundation/core/protocol.py` немає deprecation validators/warnings для envelope fields (на відміну від наявного прикладу deprecation у `vfoundation/core/fsm.py:7-11`).

---

## 3. Архітектурні прогалини

1. **HIGH:** Blueprint вважає Phase 9.0.2 fixed, але root-cause не закрито (`_cli_root` -> `.../vfoundation`, не repo root). Це блокує `vfound drift` runtime (`vfoundation/cli/vfound/__main__.py:13,288`).
2. **HIGH:** Exactly-once coverage у активному gate ілюзорна: `redis_store.py` 0% в `tests/vfoundation`, а наявний `tests/idempotency` пакет примусово skip (`tests/idempotency/__init__.py:3`).
3. **HIGH:** Contract drift між Constitution і runtime Message: Constitution вимагає `v=2` (`Constitution_FSM.md:58`), code має `v=1` (`protocol.py:24`); `data_ref` schema у Constitution об'єктна (`Constitution_FSM.md:73-75`), у code `List[str]` (`protocol.py:40`).
4. **HIGH:** RECONCILE/REPAIR flow планується без фактично оновленого SSOT registry (порушення registry-first policy).
5. **MEDIUM:** DR archive/WORM залишається TODO (`wal_gc.py:63-64`), хоча Blueprint оцінює це як закритий gap у 13.2/13.3.
6. **MEDIUM:** Phase 14.3/14.4 не має operational migration backbone (немає `migrate` CLI, немає schema versioning pipeline).
7. **MEDIUM:** Hidden coupling між доменами лишається високим (cross-domain imports), а план фокусується переважно на тестах vfoundation.
8. **LOW:** LOC-based пріоритизація в Blueprint частково неточна; це не blocker, але знижує довіру до estimation.

---

## 4. Missing Concerns

1. Немає окремої стратегії **schema/version lifecycle** (registry/schema version bumps, compatibility matrix, automated contract diff gates).
2. Немає плану **canary/feature flags** для Phase 14 breaking changes.
3. Немає явного **graceful shutdown + startup ordering test plan** для нових компонентів 11.x–13.x.
4. Немає нормалізованої **error taxonomy** (codes/classes/metric labels) як cross-cutting standard.
5. Немає **metric naming convention** і cardinality budget policy для нових observability модулів.
6. Немає політики **backpressure/rate-limiting at system boundary** у Blueprint, хоча Constitution це вимагає (`Constitution_FSM.md:128-129,245`).
7. Немає плану **dependency SSOT** (корінь `requirements.txt` vs `vfoundation/pyproject.toml` drift).
8. Немає explicit плану **package boundary hardening** (namespace package pitfalls, import stability у full suite).

---

## 5. Risk Assessment

| Ризик | Probability (1-5) | Impact (1-5) | Score | Коментар |
|---|---:|---:|---:|---|
| Неправильний `drift` path/root блокує CLI DR tooling | 5 | 4 | 20 | Уже відтворюється runtime падінням. |
| Exactly-once false confidence (active tests не покривають Redis Lua path) | 4 | 5 | 20 | Критично для trading idempotency. |
| Phase 14 envelope refactor ламає downstream | 4 | 5 | 20 | Багато live usages top-level fields; migration infra відсутня. |
| DR/WORM очікування > реалізація | 4 | 4 | 16 | `wal_gc` archive лишається TODO; RTO/RPO claims не підтверджені benchmark-ом. |
| Registry-first drift (RECONCILE/REPAIR не в SSOT) | 4 | 4 | 16 | Порушує governance і contract compliance. |

---

## 6. Scoring Matrix

| Критерій | Score (1-10) | Коментар |
|---|---:|---|
| 1. Архітектурна відповідність Constitution | 5 | Часткова; ключові пункти §5/§8/§10 мають drift. |
| 2. Повнота production scenarios | 4 | Немає повного покриття failure modes (disk full, Redis failover ambiguity, package import instability). |
| 3. Реалістичність test strategy | 5 | Гарна деталізація, але частина залежить від неактивних/відсутніх артефактів. |
| 4. Пріоритизація (P0→P5) | 7 | Загалом логічна послідовність. |
| 5. Інкрементальність (additive-first) | 8 | Фази 9–13 добре декомпозовані. |
| 6. Contract-first compliance | 5 | Registry-first декларується, але фактичні контракти дрейфують. |
| 7. Security coverage | 6 | Signing/WAL hash-chain є, але KMS/WORM/operational hardening не покриті. |
| 8. DR/HA coverage | 4 | Немає реального WAL archive path та benchmark-driven RTO/RPO validation. |
| 9. Observability coverage | 6 | Сильний план, але ризик over-engineering без consumer-driven rollout. |
| 10. Backward compatibility planning | 4 | Phase 14 має high-level intent, але без інструментальної опори. |
| 11. Domain integration strategy | 3 | Перелік неповний, coupling/cycles недооцінені. |
| 12. CI/CD integration readiness | 4 | `tests/vfoundation` green, але full suite не стабільний. |
| 13. Performance/scalability awareness | 5 | Perf harness planned, але thresholds не вшиті як mandatory gates. |
| 14. Error handling taxonomy | 3 | Немає єдиного taxonomy/semantics contract across modules. |
| 15. Documentation quality | 7 | Детально і структурно, але є self-referential "✅ fixed" claims без code parity. |

**Загальний індекс (середній): 5.1/10**

---

## 7. Рекомендації

1. **P0 (0.5 дня):** Зробити Pre-Phase 9 hotfix для CLI root/path resolution (`_cli_root`) і додати regression test для `vfound drift` import path.
2. **P0 (1 день):** Вирівняти dependency policy: один SSOT для deps; явно додати `redis`, `PyNaCl`, `fakeredis[lua]`/`lupa` strategy для CI.
3. **P0 (1 день):** Реально активувати Redis/Lua idempotency tests у основному gate (або прибрати misleading "covered" claims); зняти module-level skip в `tests/idempotency/__init__.py` або перенести релевантні тести в `tests/vfoundation`.
4. **P0 (0.5 дня):** Закрити registry drift: додати/підтвердити `RECONCILE`/`REPAIR` в `verb_registry_v1.yaml` до будь-якого коду Phase 13.1.
5. **P1 (1-2 дні):** Перед стартом 14.3 затвердити окремий `BLUEPRINT_PHASE_14_BREAKING.md` з migration matrix (producer/consumer inventory, rollback, telemetry KPIs).
6. **P1 (1 день):** Додати contract-gap ADR для Message protocol (`v`, `op`, `data_ref` schema) і визначити canonical spec, щоб прибрати drift Constitution vs runtime.
7. **P2 (2-3 дні):** Ввести CI quality profile: `tests/vfoundation` + critical integration subset + contract checks + fail-under по coverage для критичних модулів (idempotency/DR/CLI).
8. **P2 (1-2 дні):** Додати cross-cutting стандарти: error taxonomy, metric naming conventions, backpressure/rate-limit test checklist.

---

## 8. Висновок

**Рішення:** **No-Go** для безпосереднього старту Phase 9 у поточному стані Blueprint.

**Умова переходу в Go:** після закриття Pre-Phase 9 блокерів (CLI root/path, dependency SSOT + Lua strategy, активні Redis/Lua tests у main gate, registry-first parity). Після цього — **Conditional Go** з жорстким gate на contract parity і CI stability.
