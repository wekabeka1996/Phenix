# Dashboard Commands Reference

All commands assume the working directory is:
```
C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
```

---

## Порядок чистого запуску (Clean Start Order)

### Перший запуск / після зміни коду

```powershell
# 1. Переконайся, що Docker Desktop запущений (whale-icon у треї)

# 2. Перейди в папку
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent

# 3. Зупини старі контейнери (якщо є)
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1

# 4. Зроби повний ребілд + перезапуск (робить backup пам'яті, rebuild, health check)
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -Update

# 5. Відкрий браузер
#    Основний workbench:  http://127.0.0.1:8787/chat
#    Dashboard (runs):    http://127.0.0.1:8787
```

### Щоденний запуск (код не змінювався)

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1
```

### Зупинка

```powershell
cd C:\Users\user\Music\Phenix\tools\deepseek-terminal-agent
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1
```

### Перевірка без перезапуску (verify-only)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -VerifyOnly
# Виводить DASHBOARD_READY якщо всі endpoints відповідають
```

---

## PowerShell Scripts

| Скрипт | Що робить |
|--------|-----------|
| `start_dashboard.ps1` | Перевіряє Docker, .env, будує образи, запускає контейнер, чекає health |
| `start_dashboard.ps1 -Update` | Бекап `.agent_memory` → зупинка контейнерів → rebuild `--pull` → перевірка integrity → запуск |
| `start_dashboard.ps1 -VerifyOnly` | Перевіряє integrity пам'яті та всі endpoints без перезапуску |
| `stop_dashboard.ps1` | `docker compose down --remove-orphans` |
| `backup_memory.ps1` | Копіює `.agent_memory` у `.agent_memory_backups/<timestamp>/` |
| `check_memory_integrity.ps1` | Валідує структуру `.agent_memory` (JSON, JSONL формати) |
| `restore_memory.ps1` | Відновлює `.agent_memory` з backup |
| `test_dashboard.ps1` | Запускає pytest + ruff всередині контейнера |

---

## Docker Commands

### Основні

```bash
# Зупинити всі контейнери проекту
docker compose down --remove-orphans

# Зібрати образи (потрібно після зміни src/)
docker compose build

# Зібрати образи + підтягнути свіжий base image
docker compose build --pull

# Запустити тільки dashboard в фоні
docker compose up -d dashboard

# Переглянути логи dashboard
docker compose logs dashboard
docker compose logs --tail=50 dashboard
docker compose logs -f dashboard          # follow (stream)

# Статус контейнерів
docker compose ps

# Видалити зупинені контейнери
docker compose rm -fsv
```

### Одноразові команди всередині контейнера

```bash
# Запустити тести (усі, включно bash-тестами)
docker compose run --rm --entrypoint pytest deepseek-agent -q
docker compose run --rm --entrypoint pytest deepseek-agent -v --tb=short

# Linting
docker compose run --rm --entrypoint ruff deepseek-agent check src/ tests/

# Byte-compile check
docker compose run --rm --entrypoint python deepseek-agent -m compileall src/

# Інтерактивний shell всередині контейнера
docker compose run --rm --entrypoint bash deepseek-agent

# Single-shot агент
docker compose run --rm deepseek-agent deepseek-agent run "Describe the repo."
docker compose run --rm deepseek-agent deepseek-agent run --dry-run "How to fix lint?"
```

---

## Локальні команди (без Docker)

```bash
# Встановити залежності
pip install -e ".[dev]"

# Тести
python -m pytest tests/ -q
python -m pytest tests/ -x --tb=short       # зупинитись на першому падінні
python -m pytest tests/test_task_router.py  # конкретний файл

# Linting + compile
python -m ruff check src/
python -m compileall src/ -q
```

---

## API Endpoints

Всі endpoints доступні на `http://127.0.0.1:8787`.

### Системні

| Метод | Шлях | Що робить |
|-------|------|-----------|
| `GET` | `/health` | Liveness: `{"ok": true}` |
| `GET` | `/config-status` | Поточна конфігурація (без ключа API) |
| `GET` | `/models` | Каталог моделей |

### Dashboard (runs-mode)

| Метод | Шлях | Що робить |
|-------|------|-----------|
| `GET` | `/` | Головна сторінка (prompt → background run) |
| `POST` | `/runs` | Створити run, повертає `run_id` одразу |
| `GET` | `/runs` | Список останніх runs |
| `GET` | `/runs/{id}/status` | Статус, фаза, elapsed time, exit code |
| `GET` | `/runs/{id}/output` | Редагований вивід (stdout + stderr) |
| `GET` | `/runs/{id}/events` | Activity feed run-у |
| `POST` | `/runs/{id}/cancel` | Скасувати активний run |

### Session Workbench (`/chat`)

| Метод | Шлях | Що робить |
|-------|------|-----------|
| `GET` | `/chat` | Workbench UI |
| `GET` | `/chat/models` | Каталог моделей + профілі |
| `GET` | `/chat/sessions` | Список сесій |
| `POST` | `/chat/sessions` | Створити нову сесію |
| `GET` | `/chat/sessions/{id}` | Деталі сесії (turns, memory, artifacts) |
| `POST` | `/chat/sessions/{id}/message` | Відправити повідомлення |
| `POST` | `/chat/sessions/{id}/profile` | Змінити модель/профіль (без втрати history) |
| `GET` | `/chat/sessions/{id}/memory` | Memory atoms сесії |
| `GET` | `/chat/sessions/{id}/memory/search?q=` | Пошук по memory atoms |
| `POST` | `/chat/sessions/{id}/memory` | Створити memory atom |
| `POST` | `/chat/sessions/{id}/context` | Переглянути зібраний контекст |
| `POST` | `/chat/sessions/{id}/compress` | Ручна компресія старих turns у spine |
| `GET` | `/chat/sessions/{id}/subagents` | Список subagent runs |
| `POST` | `/chat/sessions/{id}/subagents` | Запустити bounded subagent |

### Agent OS Panels

| Метод | Шлях | Що робить |
|-------|------|-----------|
| `GET` | `/chat/playbooks` | Список playbooks оператора |
| `GET` | `/chat/tools` | Зареєстровані інструменти агента |
| `GET` | `/chat/approvals` | Pending approvals (дії що чекають підтвердження) |
| `POST` | `/chat/approvals/{id}/approve` | Підтвердити дію |
| `POST` | `/chat/approvals/{id}/reject` | Відхилити дію |
| `GET` | `/chat/reports` | Список validation reports |
| `POST` | `/chat/reports/scan` | Запустити сканування (генерує новий report) |
| `GET` | `/chat/decisions` | Список рішень оператора |
| `POST` | `/chat/decisions` | Додати рішення |
| `POST` | `/chat/decisions/{id}/deprecate` | Застаріти рішення |
| `GET` | `/chat/memory-patches` | Пропозиції змін до пам'яті |
| `POST` | `/chat/memory-patches` | Створити memory patch |
| `POST` | `/chat/memory-patches/{id}/approve` | Застосувати patch |
| `POST` | `/chat/memory-patches/{id}/reject` | Відхилити patch |
| `GET` | `/chat/evidence-bundles` | Evidence bundles (зібрані артефакти) |
| `POST` | `/chat/evidence-bundles/scan` | Запустити скан логів для нових bundles |

---

## Task Router — типи задач

Workbench автоматично маршрутизує запит перед відповіддю моделі:

| Тип | Тригер-слова | Що запускає |
|-----|-------------|-------------|
| `direct_answer` | (нічого з нижче) | Пряма відповідь, без subagents |
| `repo_search` | find, search, where, scan, evidencepack, read-only | 1 ScoutAgent (read_only) |
| `test_run` | test, pytest, testreport, ruff, smoke | 1 TestRunner (tests_only) |
| `doc_write` | readme, docs, guide, how to use | 1 DocsScout (read_only) |
| `log_scan` | log, jsonl, metadata, order_log | 1 LogScanner (read_only) |
| `mixed` | evidencepack **І** testreport в одному запиті | 2 subagents: ScoutAgent + TestScoutAgent |

---

## Файлова структура `.agent_memory`

```
.agent_memory/
  sessions/
    <session_id>/
      session.json        — мета-дані сесії, поточний профіль
      turns.jsonl         — всі turns append-only (ніколи не видаляються)
  atoms/
    <atom_id>.json        — memory atoms
  artifacts/
    <artifact_id>.json    — EvidencePack, TestReport, інші артефакти subagents
  playbooks/              — operator playbooks
  decisions/              — operator decisions
  memory_patches/         — pending memory patches
  evidence_bundles/       — evidence bundles
```

`.agent_memory_backups/<timestamp>/` — резервні копії (створюються при `-Update`).

---

## Troubleshooting

| Симптом | Причина | Рішення |
|---------|---------|---------|
| `Memory backup failed` | stdout дочірнього powershell заважав `Invoke-LocalScript` | Вже виправлено (`\| Out-Host`). Запусти `-Update` ще раз |
| `[FAIL] Memory integrity check failed` | Пошкоджений JSON в `.agent_memory` | Запусти `restore_memory.ps1` з останнього backup |
| `DASHBOARD_READY` не з'явився | Dashboard не запустився за 20с | `docker compose logs dashboard` |
| `401 Unauthorized` | Невірний API key | Перевір `DEEPSEEK_API_KEY` у `.env` |
| Docker не знайдено | PATH не налаштовано | `$env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"` |
| `Cannot connect to the Docker daemon` | Docker Desktop не запущений | Запусти Docker Desktop, зачекай whale icon |
| Порт 8787 зайнятий | Старий контейнер або інший процес | `stop_dashboard.ps1`, потім `start_dashboard.ps1` |
