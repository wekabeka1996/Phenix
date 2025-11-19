# Aggregated OCO Deep Investigation Plan

**Дата початку:** 19 листопада 2025
**Ціль:** Виявити причини некоректної роботи системи Aggregated OCO та OrderGuardian

## Проблема
Після міграції на нову логіку Aggregated OCO та виправлення тестів система працює некоректно:
- На біржі відкрито 3 позиції
- Виставлено 4 ордери замість очікуваних 6 (по 2 на позицію: TP + SL)
- Розподіл: 1 TP для BNB, 2 SL для BNB, 1 SL для BTC
- Система крихка і непередбачувана

## Фази дослідження

### Фаза 1: Збір контексту та аналіз архітектури (30-40 хв)
**Мета:** Зрозуміти поточну архітектуру та контракти

**Підфази:**
1. Аналіз логів виконання (`domain_execution_management.log`, `order_log_v1.jsonl`)
2. Вивчення структури модулів:
   - `apps/reference/domains/execution_position/fsm.py` (ExecPosFSM)
   - `apps/reference/domains/execution_position/agg_oco_*.py` (Aggregated OCO логіка)
   - `apps/reference/domains/execution_position/order_guardian.py`
   - `apps/reference/domains/execution_position/fsm_manage.py` (ManageFlowFSM)
3. Читання контрактів та схем даних
4. Мапування потоку даних від відкриття позиції до виставлення TP/SL

**Результат:** Діаграма архітектури, список критичних компонентів

---

### Фаза 2: Аналіз поточного стану на біржі (15-20 хв)
**Мета:** Встановити точний стан ордерів та позицій

**Підфази:**
1. Парсинг логів для відновлення timeline подій
2. Ідентифікація всіх створених ордерів (ENTRY, TP, SL)
3. Перевірка correlation ID між ордерами та позиціями
4. Виявлення "orphaned" ордерів
5. Аналіз роботи `AGG_OCO_WATCHDOG` (повторювані WARNING)

**Результат:** Таблиця відповідності позицій та ордерів, список аномалій

---

### Фаза 3: Code Review критичних модулів (60-90 хв)
**Мета:** Виявити дефекти в реалізації

**Підфази:**
1. **Aggregated OCO створення bracket-ордерів:**
   - Перевірка логіки `_place_aggregated_oco_brackets`
   - Аналіз `_recalc_aggregated_brackets`
   - Валідація умов trigger-ів для recalc

2. **OrderGuardian cleanup логіка:**
   - Перевірка `cleanup_orphans`
   - Аналіз `reconcile_symbol`
   - Виявлення race conditions

3. **ManageFlowFSM життєвий цикл:**
   - Обробка `TRADE_EXECUTED` подій
   - Логіка `on_portfolio_state_updated`
   - Trigger-и для bracket adjustment

4. **ExecPosFSM координація:**
   - Routing між OpenFlow → ManageFlow → CloseFlow
   - Dispatch decision logic
   - Event handling (`handle` method)

5. **Idempotency та deduplication:**
   - Перевірка `_processed_events`
   - Correlation store usage
   - Duplicate order prevention

**Результат:** Список виявлених дефектів з пріоритетами (P0-P2)

---

### Фаза 4: Аналіз умов виникнення "крихкості" (30-40 хв)
**Мета:** Зрозуміти чому система нестабільна

**Підфази:**
1. Виявлення race conditions між компонентами
2. Аналіз async/await patterns та event loop usage
3. Перевірка error handling та fallback logic
4. Аналіз TTL, timeouts, polling intervals
5. Виявлення shared state та concurrency issues

**Результат:** Діаграма race conditions, список критичних шляхів

---

### Фаза 5: Створення інтеграційних тестів (45-60 хв)
**Мета:** Створити тести, які симулюють реальні сценарії

**Тест-сценарії:**
1. **Nominal flow:**
   - Відкриття позиції → створення TP/SL
   - Часткове закриття → recalc brackets
   - Повне закриття → cleanup brackets

2. **Edge cases:**
   - Множинні entry ордери для однієї позиції
   - Швидкі часткові закриття (rapid fills)
   - Position flip (LONG → SHORT)
   - Orphaned brackets detection

3. **Failure modes:**
   - Network timeout під час bracket placement
   - Duplicate ORDER_FILL events
   - Race між bracket creation та position close
   - Guardian cleanup під час active position

**Результат:** Файл `tests/domains/execution_position/test_agg_oco_integration.py`

---

### Фаза 6: Root cause analysis (30-40 хв)
**Мета:** Ідентифікувати primary causes некоректної поведінки

**Підфази:**
1. Correlation дефектів з логами
2. Відтворення проблем через тести
3. Верифікація hypothesis про root causes
4. Пріоритизація fixes

**Результат:** Документ з root causes та recommended fixes

---

### Фаза 7: Рекомендації та план виправлення (20-30 хв)
**Мета:** Створити actionable plan

**Підфази:**
1. Список критичних fixes (must-have)
2. Архітектурні поліпшення (should-have)
3. Refactoring opportunities (nice-to-have)
4. Пропозиції щодо monitoring та observability

**Результат:** `AGG_OCO_FIX_PLAN.md` з пріоритизованими задачами

---

## Метрики успіху

- [ ] 100% позицій мають відповідні TP і SL ордери
- [ ] Orphaned brackets видаляються за < 5 секунд після закриття позиції
- [ ] Recalc triggers спрацьовують коректно при partial fills
- [ ] Інтеграційні тести покривають 90%+ критичних шляхів
- [ ] Zero race conditions між OrderGuardian та ManageFlow

---

## Статус виконання

- [x] Фаза 1: Збір контексту
- [x] Фаза 2: Аналіз поточного стану
- [x] Фаза 3: Code Review (Див. `docs/AGG_OCO_PHASE3_DEFECTS_REPORT.md`)
- [x] Фаза 4: Аналіз крихкості (Див. `docs/AGG_OCO_PHASE4_FRAGILITY_REPORT.md`)
- [x] Фаза 5: Інтеграційні тести (Див. `docs/AGG_OCO_PHASE5_TEST_REPORT.md`)
- [x] Фаза 6: Root cause analysis (Підтверджено тестами)
- [ ] Фаза 7: Рекомендації та план виправлення

---

**Очікуваний час:** 4-6 годин
**Документи результатів:**
- `AGG_OCO_ARCHITECTURE_DIAGRAM.md` (TBD)
- `docs/AGG_OCO_PHASE3_DEFECTS_REPORT.md`
- `docs/AGG_OCO_PHASE4_FRAGILITY_REPORT.md`
- `docs/AGG_OCO_PHASE5_TEST_REPORT.md`
- `AGG_OCO_FIX_PLAN.md` (Next Step)
- `tests/domains/execution_position/test_agg_oco_integration.py`
