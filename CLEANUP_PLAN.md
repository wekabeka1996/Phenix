# 🧹 План очистки проекту

**Дата**: 2025-11-09
**Статус**: В процесі

## 📋 Класифікація файлів у корені

### ✅ ЗБЕРЕГТИ - Документація (не переміщаємо)
```
- README.md                  # Основна документація проекту
- JOURNAL.md                 # Журнал розробки (6900+ рядків, важливо)
- TODO.md                    # План розробки (887 рядків, критично)
- TASK.md                    # План виправлень (138 рядків)
```

### ✅ ЗБЕРЕГТИ - Конфігурація
```
- .env                       # Конфіг середовища (ВАЖЛИВО)
- .env.example               # Приклад конфігу
- .gitignore                 # Git фільтр
- .copilotignore            # Copilot фільтр
- .geminiignore             # Gemini фільтр
- mypy.ini                   # Type checker конфіг
- pytest.ini                 # Pytest конфіг (важливо!)
- requirements.txt           # Python залежності
- package.json               # NPM залежності
- package-lock.json          # NPM lock файл
```

### 🗑️ ВИДАЛИТИ - Legacy документи
```
- TODO_old4.md              # Старий план (replaced by TODO.md)
- GEMINI.md                 # Gemini інструкції (в .copilot-instructions.md)
```

### 🔄 ПЕРЕНЕСТИ У docs/artifacts/ - Аналітичні звіти
```
- CRITICAL_BUG_ANALYSIS.json      → docs/artifacts/CRITICAL_BUG_ANALYSIS.json
- ORPHANS_CANDIDATES.json          → docs/artifacts/ORPHANS_CANDIDATES.json
- dashboard.html                   → docs/artifacts/dashboard.html
- pytest_output.txt                → docs/artifacts/pytest_output.txt
- pytest_results.txt               → docs/artifacts/pytest_results.txt
- test_results_latest.txt          → docs/artifacts/test_results_latest.txt
- recent_logs_debug.txt            → docs/artifacts/recent_logs_debug.txt
```

### 🗑️ ВИДАЛИТИ - Debug утиліти (dev-only, перейшли в production)
```
- fix_unicode.py                   # Міграція завершена
- fix_config_unicode.py            # Міграція завершена
- fix_phase3_unicode.py            # Міграція завершена
- fix_phase5_unicode.py            # Міграція завершена
- advanced_migrate_pydantic.py      # Міграція завершена
- migrate_pydantic.py              # Міграція завершена
- duckdb.py                        # Дослідження, більше не потрібна
- check_orders.py                  # Утиліта для debug (повторюється в prodaction)
- debug_test.py                    # Debug файл
```

### 🗑️ ВИДАЛИТИ - Тестові artifiacts (запускаються як адок-тести)
```
- test_alpha_debug.py              # Debug/дослідження (2 дні назад)
- test_duckdb.py                   # Дослідження DuckDB
- test_duckdb2.py                  # Дослідження DuckDB
- test_msg.py                      # Простий message test
- test_weights.py                  # Unit тест для ваг
- test_ws_sim.py                   # WebSocket симуляція
- test_ws_sim2.py                  # WebSocket симуляція 2
```

### 📚 ПЕРЕНЕСТИ У tests/ - Поточні тести
**ЦІ ТЕСТИ ВИКОРИСТОВУЮТЬСЯ ДЛЯ РОЗРОБКИ, НАЙСВІЖІШІ (0 днів):**
```
# Guardian tests (новітні, важливі):
- test_exposure_guard_config.py    → tests/integration/test_exposure_guard_config.py
- test_full_tidy.py                → tests/integration/test_full_tidy.py
- test_guardian_cleanup_direct.py  → tests/integration/test_guardian_cleanup_direct.py
- test_guardian_cleanup_loop.py    → tests/integration/test_guardian_cleanup_loop.py
- test_guardian_cleanup_mock.py    → tests/integration/test_guardian_cleanup_mock.py
- test_guardian_minimal.py         → tests/integration/test_guardian_minimal.py
- test_guardian_registration.py    → tests/integration/test_guardian_registration.py

# Tidy gate tests (новітні):
- test_tidy_events.py              → tests/integration/test_tidy_events.py
- test_tidy_gate.py                → tests/integration/test_tidy_gate.py
- test_tidy_gate_simple.py         → tests/integration/test_tidy_gate_simple.py

# Real tidy тест:
- test_real_tidy.py                → tests/integration/test_real_tidy.py

# Polling тест:
- test_polling_integration.py      → tests/integration/test_polling_integration.py

# Phase тести (1-2 дні назад, old but related to phases):
- test_phase1_validation.py        → tests/phases/test_phase1_validation.py
- test_phase2_error_handling.py    → tests/phases/test_phase2_error_handling.py
- test_phase2_legacy_support.py    → tests/phases/test_phase2_legacy_support.py
- test_phase3_retry_logic.py       → tests/phases/test_phase3_retry_logic.py
- test_phase3_todo2_fsm_params.py  → tests/phases/test_phase3_todo2_fsm_params.py
- test_phase3_todo3_integration.py → tests/phases/test_phase3_todo3_integration.py
```

### ⚠️ СЦЕНАРІЇ ДЛЯ ПЕРЕВІРКИ
```
- kill_python.ps1                  # Утиліта для kill-all, може залишити для емергенс
- launch_testnet.ps1               # Утиліта для запуску тестнету, потрібна?
```

## 📊 СТАТИСТИКА
- **Видалити**: 15 файлів
- **Перенести у docs/artifacts/**: 7 файлів
- **Перенести у tests/**: 21 файлів
- **Утиліти для перевірки**: 2 файли
- **Зберегти (не чіпати)**: 11 файлів

**Результат**: Коріння буде мати ~11 файлів (чисто, акуратно)

## 🔧 КРОК ЗА КРОКОМ

### 1️⃣ Перенести утилітарні скрипти
```bash
mv *.ps1 scripts/
```

### 2️⃣ Перенести артефакти в docs/artifacts/
```bash
mv CRITICAL_BUG_ANALYSIS.json docs/artifacts/
mv ORPHANS_CANDIDATES.json docs/artifacts/
mv dashboard.html docs/artifacts/
mv pytest_output.txt docs/artifacts/
mv pytest_results.txt docs/artifacts/
mv test_results_latest.txt docs/artifacts/
mv recent_logs_debug.txt docs/artifacts/
```

### 3️⃣ Перенести тести
```bash
# Guardian тести
mv test_guardian_*.py tests/integration/
mv test_exposure_guard_config.py tests/integration/
mv test_full_tidy.py tests/integration/
mv test_tidy_*.py tests/integration/
mv test_real_tidy.py tests/integration/
mv test_polling_integration.py tests/integration/

# Phase тести
mv test_phase*.py tests/phases/
```

### 4️⃣ Видалити застарілі/debug файли
```bash
rm fix_*.py
rm *_pydantic.py
rm duckdb.py
rm check_orders.py
rm debug_test.py
rm test_alpha_debug.py
rm test_duckdb*.py
rm test_msg.py
rm test_weights.py
rm test_ws_sim*.py
rm TODO_old4.md
rm GEMINI.md
```

### 5️⃣ Оновити .gitignore
```
# Add to .gitignore:
logs/
*.log
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
dist/
build/
*.egg-info/
```

## ✅ ЦІЛІ
1. ✅ Організована структура проекту
2. ✅ Чисте коріння (тільки конфіг + docs)
3. ✅ Всі тести в одному місці (tests/)
4. ✅ Артефакти окремо
5. ✅ Готовість до production
