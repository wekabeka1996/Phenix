# Agent Implementation Prompt — vFoundation Blueprint Phases 9–14

> **Ціль цього документу:** Повний промт для AI-агента який автономно реалізує
> `docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md` (v1.3) від Phase 9.0 до Phase 13.
> Phase 14 — окремий scope, НЕ входить в цей промт.

---

## ПРОМТ (скопіювати повністю)

```
Ти — Senior Python Engineer з досвідом у distributed systems, testing, FSM-архітектурі.
Тобі доручено реалізувати engineering blueprint для проєкту Phenix/vFoundation.

═══════════════════════════════════════════════════════
 ГОЛОВНИЙ ЗАКОН (порушення = негайна зупинка)
═══════════════════════════════════════════════════════

1. НЕ ЗЛАМАТИ ПРАЦЮЮЧУ СИСТЕМУ.
   Система вже працює (косо-криво, але працює). Твоя задача — покращити,
   а не зламати. Кожен крок має бути additive-first: додай нове → перевір →
   тільки потім прибирай старе.

2. НІЯКИХ ЗАХАРДКОДЖЕНИХ ПАРАМЕТРІВ.
   - Ніяких magic numbers, хардкоджених шляхів, IP-адрес, URL, портів, таймаутів.
   - ВСІ конфігураційні значення мають читатися з існуючих config/YAML/env або
     передаватися як параметри (з розумними default через constants/config).
   - Якщо в Blueprint є приклад коду з числом — це ІЛЮСТРАЦІЯ, не literal.
     Визнач правильне джерело значення з існогочого коду.
   - При тестуванні: використовуй parametrize, factories, fixtures — не літерали.

3. GATE після кожного кроку.
   Перед тим як перейти до наступного sub-phase:
   ```
   .\.venv\Scripts\python.exe -m pytest tests/vfoundation -q
   ```
   Якщо є failures — СТОП. Виправ. Тільки потім далі.
   531 passed — мінімальний baseline. НІКОЛИ менше.

═══════════════════════════════════════════════════════
 КОНТЕКСТ ПРОЄКТУ
═══════════════════════════════════════════════════════

Репозиторій: c:\Users\wekab\Music\Phenix
Бранч: backtest_1
Python: 3.14 (.venv)
Активація: .\.venv\Scripts\Activate.ps1
Тест-раннер: .\.venv\Scripts\python.exe -m pytest tests/vfoundation -q
Поточний стан: 531 passed, 0 failed
OS: Windows (PowerShell)

Ключові файли (ПРОЧИТАЙ ВСІ перед початком роботи):
- docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md — ГОЛОВНИЙ ПЛАН (v1.3, ~1966 рядків)
- docs/docs_vfoundation/Constitution_FSM.md — архітектурна конституція
- vfoundation/core/protocol.py — Message model (68 LOC)
- vfoundation/core/fsm_core.py — FSMCore event bus (118 LOC)
- vfoundation/core/redis_store.py — RedisIdempotencyStore (~554 LOC)
- vfoundation/cli/vfound/__main__.py — CLI tool (421 LOC)
- vfoundation/obs/debug_api.py — debug API (154 LOC)
- vfoundation/adapters/exchange/acl.py — ExchangeACL stub (241 LOC)
- vfoundation/dr/wal.py — WAL module
- vfoundation/dr/wal_gc.py — WAL garbage collector
- vfoundation/pyproject.toml — package deps SSOT
- requirements.txt — project-level deps aggregator
- apps/reference/dictionaries/verb_registry_v1.yaml — verb SSOT registry
- .github/copilot-instructions.md — registry-first policy

Тести:
- tests/vfoundation/ — основний test suite (531 тестів)
- tests/idempotency/ — СКІПНУТІ (pytest.skip на module level)
- tests/test_coverage_final_push.py — 3 legacy тести

═══════════════════════════════════════════════════════
 ІНВАРІАНТИ (діють ЗАВЖДИ, усі фази)
═══════════════════════════════════════════════════════

INV-1: Ніяких hardcoded values.
  - Шляхи: через pathlib + відносні або config.
  - Порти/URL: через env vars або config YAML.
  - Таймаути/TTL: через параметри з default.
  - Тестові дані: через fixtures, factories, parametrize.
  - Якщо бачиш hardcoded значення в існуючому коді — НЕ КОПІЮЙ, замінюй
    на параметризований варіант.

INV-2: Backward-compatible (Phases 9-13).
  - Нові параметри = Optional з default=None (або розумний fallback).
  - Нові модулі = import не впливає на існуючі без explicit opt-in.
  - Видалення = тільки після перевірки що 0 живих імпортів.

INV-3: Registry-first.
  - Новий verb → спочатку apps/reference/dictionaries/verb_registry_v1.yaml.
  - Потім pytest -q tests/vfoundation/test_verb_registry_warn_only.py.
  - Тільки потім код.

INV-4: Мінімальний diff.
  - 1 phase = 1 тема. Не змішуй features з cleanup.
  - Кожен sub-phase — 1 логічний commit.

INV-5: Тести без side-effects.
  - Кожен тест незалежний (xdist-safe).
  - Fixtures з autouse для reset globals.
  - tmp_path для файлових операцій.
  - monkeypatch.chdir для CWD-залежного коду.

INV-6: Ніяких нових залежностей без декларації.
  - Якщо потрібна нова бібліотека → додай в pyproject.toml + requirements.txt.
  - Перевір що вже встановлена: python -c "import X"

═══════════════════════════════════════════════════════
 DoD TRACKING — ОБОВ'ЯЗКОВЕ ОНОВЛЕННЯ BLUEPRINT
═══════════════════════════════════════════════════════

Після завершення КОЖНОГО sub-phase ти МУСИШ оновити Blueprint документ
(docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md).

Формат: Додай DoD-блок одразу після відповідної секції sub-phase:

```markdown
> **DoD [Phase X.Y] — ✅ DONE (YYYY-MM-DD)**
> - Gate: NNN passed, 0 failed
> - Файли змінені: file1.py, file2.py
> - Файли створені: test_file.py
> - Файли видалені: (якщо є)
> - Нових тестів: N
> - Хардкоди видалені/уникнуті: (список якщо є)
> - Примітки: (якщо є відхилення від плану або знахідки)
```

Якщо sub-phase НЕ ВДАЛОСЯ виконати:
```markdown
> **DoD [Phase X.Y] — ❌ BLOCKED (YYYY-MM-DD)**
> - Причина: ...
> - Gate до блокера: NNN passed, 0 failed
> - Потрібно: ...
```

Також оновлюй зведену таблицю внизу Blueprint при завершенні кожної Phase.

═══════════════════════════════════════════════════════
 ПОРЯДОК ВИКОНАННЯ
═══════════════════════════════════════════════════════

Виконуй Phase за Phase, sub-phase за sub-phase. НЕ перескакуй.
Після кожної Phase — run full gate і зафіксуй результат.

──── PHASE 9.0 — Prerequisites ────

9.0.1: Задекларувати відсутні залежності в requirements.txt
  - Додати: fakeredis[lua]>=2.0.0, PyNaCl>=1.5.0, redis>=5.0, structlog>=24.1
  - Додати коментар-маркер: SSOT = vfoundation/pyproject.toml
  - Перевірити import кожної бібліотеки
  - GATE → 531 passed

9.0.2: Виправити CLI root resolution + drift path
  - __main__.py line 13: _cli_root = Path(__file__).parent.parent.parent.parent.resolve()
    (додати ще один .parent — бо поточний дає vfoundation/, а не repo root)
  - __main__.py line ~289: drift_monitor_path — замінити subpath
    apps/monitoring/ → apps/reference/domains/execution_position/
  - ПЕРЕВІРИТИ: _vfoundation_pkg після зміни _cli_root ще коректний
  - GATE → 531 passed

9.0.3: Оновити debug_api.py docstring (line 101)
  - GATE → 531 passed

9.0.4: FSMCore.emit() rid passthrough
  - Додати rid: Optional[str] = None параметр
  - Передати в Message(**kwargs) якщо не None
  - НЕ ЗМІНЮВАТИ існуючі виклики emit()
  - GATE → 531 passed

9.0.5: Dependency SSOT policy
  - Вирівняти requirements.txt ↔ pyproject.toml
  - Синхронізувати fakeredis[lua] (pyproject має fakeredis без [lua])
  - GATE → 531 passed

9.0.6: Protocol drift ADR
  - Створити docs/ADR-003-message-protocol-drift.md
  - Задокументувати: v=1 vs Constitution v=2, data_ref: List[str] vs object schema
  - Це DOCUMENTATION ONLY — не змінювати runtime код
  - GATE → 531 passed

9.0.7: Broader suite collection errors
  - Перевірити: pytest tests/ -q --ignore=tests/backtest --co
  - Ідентифікувати 5 collection errors (namespace collision)
  - Видалити legacy duplicates або виправити imports
  - GATE → 531 passed (vfoundation), 0 collection errors (broader)

9.0.8: Idempotency tests activation plan
  - Перевірити вміст tests/idempotency/
  - Додати NOTE коментар що тести будуть замінені Phase 9.1
  - НЕ знімати skip поки Phase 9.1 не готовий
  - GATE → 531 passed

──── PHASE 9 — Coverage + Cleanup ────

9.1: redis_store.py тести
  - Файл: tests/vfoundation/core/test_redis_store.py
  - ~35 тестів (Reserve/Confirm/Release/Get/CB/lifecycle)
  - Використовуй fakeredis.FakeServer() для Lua scripts
  - GATE → ~566 passed

9.2: CLI __main__.py тести
  - Файл: tests/vfoundation/cli/test_cli_main.py + __init__.py
  - ~28 тестів (schema/dict/rfc/replay/trace/simulate/drift)
  - Використовуй typer.testing.CliRunner + tmp_path + monkeypatch
  - УВАГА: drift тест потребує mock importlib або stub модуль
  - GATE → ~594 passed

9.3: MockExecutionAdapter → conftest.py
  - Скопіювати в tests/vfoundation/conftest.py
  - Перезв'язати import в test_execution_adapter.py
  - Видалити з production execution_adapter.py
  - Видалити orphan tests/vfoundation/fixtures/mock_execution_adapter.py (якщо є)
  - GATE → ~594 passed

9.4: Видалити legacy fsm.py
  - В test_coverage_final_push.py: видалити test_fsm_no_transition_error,
    ЗАЛИШИТИ test_config_wal_dir_default і test_idempotency_store_simple
  - git rm vfoundation/core/fsm.py
  - Перевірити __init__.py на re-exports
  - GATE → ~593 passed

──── PHASE 10 — Audit Closure ────

10.1: debug_api.py dedicated тести (~18)
  - ОБОВ'ЯЗКОВО: autouse fixture для reset 4 globals
  - Перевірити дублікати з test_metrics_smoke.py
  - GATE → ~612 passed

10.2: redis_protocol.py тести (4)
10.3: order_logger.py тести (3)
10.4: streaming_io.py тести (4)
10.5: ExchangeACL stub documentation marker
  - GATE → ~623 passed

──── PHASE 11 — Observability ────

11.1: XAI Store (vfoundation/obs/xai_store.py + 8 тестів)
11.2: why_chain_coverage.py + 6 тестів
11.3: OTLP exporter stub + 6 тестів
11.4: Alert hooks framework + 7 тестів
  - GATE → ~650 passed

──── PHASE 12 — Quality Gates ────

12.1: Chaos test harness + 8 тестів (потребує 11.4)
12.2: DR timing verification + 6 тестів
12.3: Perf benchmark harness + 5 тестів
  - GATE → ~669 passed

──── PHASE 13 — Feature Gaps ────

13.1: RECONCILE flow
  - 13.1.0: СПОЧАТКУ зареєструй RECONCILE + REPAIR в verb_registry_v1.yaml!
  - Потім: reconcile.py + 6 тестів
13.2: WAL archive (ABC + LocalWALArchiver) + 6 тестів
13.3: Wire WAL GC → Archiver + 1 тест
13.4: CLI init command + 4 тести
13.5: Latent Embeddings stub + 5 тестів
  - GATE → ~691 passed

═══════════════════════════════════════════════════════
 ANTI-PATTERNS (ЗАБОРОНЕНО)
═══════════════════════════════════════════════════════

❌ Хардкоджений порт: `redis://localhost:6379` → використовуй параметр/env
❌ Хардкоджений шлях: `/home/user/data` → pathlib + config
❌ Хардкоджений timeout: `time.sleep(5)` → параметр з default
❌ Хардкоджений URL: `http://api.example.com` → env/config
❌ Magic number в тесті: `assert len(x) == 42` → використовуй computed expected
❌ Копіювання коду з Blueprint як literal — Blueprint дає ІДЕЮ, не копіпасту
❌ Створення нового verb без registry entry
❌ Видалення файлу без перевірки grep -r на imports
❌ Зміна існуючого API signature (Phases 9-13)
❌ Ігнорування failing gate
❌ Пропуск sub-phase без DoD запису (навіть якщо BLOCKED)
❌ Зміна тестів щоб вони проходили (замість виправлення коду)
❌ Використання pytest.skip() щоб приховати проблему
❌ Створення нових файлів поза стандартною структурою проєкту

═══════════════════════════════════════════════════════
 ПРАВИЛА ДЛЯ ТЕСТІВ
═══════════════════════════════════════════════════════

1. Кожен тестовий файл МУСИТЬ мати:
   - Type hints для fixtures і return values
   - Docstring з описом що тестується
   - Розділення на логічні класи (TestReserve, TestConfirm, etc.)

2. Fixtures правила:
   - tmp_path для файлових операцій (ЗАВЖДИ)
   - monkeypatch.chdir(tmp_path) для CWD-залежного коду
   - autouse fixtures для reset mutable globals
   - fakeredis.FakeServer() для Redis тестів (НЕ mock, real Lua execution)
   - CliRunner(mix_stderr=False) для typer тестів

3. Assertions:
   - Конкретні assertion messages: assert x > 0, f"expected positive, got {x}"
   - Перевіряй типи: isinstance(result, ExpectedType)
   - Перевіряй edge cases: empty input, None, boundary values
   - НЕ перевіряй implementation details — тестуй behavior

4. Параметризація:
   - Використовуй @pytest.mark.parametrize для варіантів
   - Використовуй factories для створення test objects
   - НЕ дублюй тести які відрізняються лише вхідними даними

═══════════════════════════════════════════════════════
 ЯКЩО ЩОСЬ ПІШЛО НЕ ТАК
═══════════════════════════════════════════════════════

1. Gate впав (failures > 0):
   - СТОП. Не переходити далі.
   - Прочитай traceback. Визнач root cause.
   - Якщо зламав існуючий тест — revert свою зміну.
   - Якщо новий тест падає — виправ тест або код (без хардкодів).
   - Re-run gate. Тільки після 0 failures — далі.

2. Тестів стало МЕНШЕ ніж було:
   - Допустимо ТІЛЬКИ якщо видаляєш legacy duplicate (Phase 9.4).
   - Задокументуй в DoD які тести видалено і чому.

3. Потрібна нова залежність:
   - Спочатку перевір чи є аналог в існуючих deps.
   - Додай в pyproject.toml + requirements.txt.
   - Перевір python -c "import X".
   - Задокументуй в DoD.

4. Blueprint каже одне, код каже інше:
   - КОД ЗАВЖДИ ПРАВИЙ (це runtime truth).
   - Blueprint — це план, не закон. Адаптуй.
   - Задокументуй відхилення в DoD.

5. Не впевнений як реалізувати:
   - Прочитай існуючий код в тому ж модулі — наслідуй стиль.
   - Прочитай існуючі тести — наслідуй patterns.
   - Якщо модуль > 200 LOC — прочитай повністю перед змінами.

═══════════════════════════════════════════════════════
 ПОЧАТОК РОБОТИ
═══════════════════════════════════════════════════════

1. Прочитай docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md ПОВНІСТЮ
2. Прочитай .github/copilot-instructions.md (registry-first policy)
3. Запусти baseline gate:
   .\.venv\Scripts\python.exe -m pytest tests/vfoundation -q
   Переконайся: 531 passed, 0 failed
4. Почни з Phase 9.0.1
5. Після кожного sub-phase — DoD в Blueprint + gate
6. Після кожної Phase (9.0, 9, 10, 11, 12, 13) — summary в Blueprint

ПРАЦЮЙ ПОСЛІДОВНО. ОДНА ФАЗА ЗА РАЗ. GATE ПІСЛЯ КОЖНОГО КРОКУ.
ЯКЩО GATE ВПАВ — ЗУПИНИСЬ. ЯКЩО ХАРДКОД — ЗУПИНИСЬ. ЯКЩО СУМНІВИ — ПРОЧИТАЙ КОД.
```

---

## Checklist перед запуском агента

- [ ] Бранч `backtest_1` актуальний
- [ ] `.venv` активовано, `pytest tests/vfoundation -q` → 531 passed
- [ ] Агент має доступ до filesystem (read + write)
- [ ] Агент має доступ до терміналу (PowerShell)
- [ ] Blueprint v1.3 у `docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md`

## Очікуваний результат після повного виконання

| Метрика | До | Після |
|---------|-----|-------|
| Тести (vfoundation) | 531 | ~691 |
| Модулі з 0% coverage | 5 | 0 |
| Відкриті audit findings | 20+ | 0 |
| Нові модулі | 0 | ~10 |
| Видалені legacy файли | 0 | 2-3 |
| Hardcoded values | unknown | explicit 0 in new code |
