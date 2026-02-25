# Neocortex (Standalone) — план створення ізольованого домену

Цей документ перетворює `apps/reference/domains/neocortex/docs/NEOCORTEX_DOMAIN_CONCEPT.md` у **практичний план** створення Neocortex як **окремого, закритого (fail‑closed) процесу**, який:
- **не впливає** на поточну систему Aurora/Phenix та її рантайм;
- **не повʼязаний з її кодом** (жодних імпортів з цього репо, жодної реєстрації домену в `config/aurora/*`);
- працює як **пасивний спостерігач/аналітик**, що приймає **тільки read‑only вхідні дані** (копії WAL/ринкових даних) і генерує **власні** логи/репорти.

---

## 0) Результат, який ми хочемо отримати (ціль R0)

**R0 (Observer, offline‑first):** окремий процес/проєкт, що:
1) інкрементально інгестить WAL `*.jsonl` у свій стор (SQLite/DuckDB + JSONL);
2) відновлює таймлайн по символах/епізодах (intent → execution → position → close);
3) рахує метрики якості рішень/виконання та safety‑інваріанти;
4) генерує `alerts.jsonl` + `report.md`;
5) може працювати **офлайн** (на копії WAL), без доступу до рантайму Aurora.

Після R0 можна додати R1/R2 (латент/World Model/тіньові плани), але **без будь‑якого каналу actuation**.

---

## 1) Незаперечні вимоги ізоляції (hard constraints)

### 1.1. Заборони (мають бути виконані завжди)

- **0 інтеграції в Aurora runtime**
  - не додаємо домен у `config/aurora/domains.yaml`;
  - не додаємо імпорти/хуки в `FSMCore.emit()`, `AuroraBridge`, `decision_making` тощо;
  - не запускаємо Neocortex як частину основних startup‑скриптів.

- **0 залежностей на код цього репо**
  - у Standalone‑проєкті заборонено імпортувати `Phenix/*`, `vfoundation/*`, `apps/*`, будь‑які модулі з цього монорепо;
  - якщо потрібно “узяти ідею/алгоритм” з `living_latent/*` — робимо *копію/порт* коду в Standalone‑проєкт і прибираємо всі імпорти на Phenix‑дерево (після порту це стає автономним кодом).

- **0 команд/зворотного каналу**
  - Neocortex не пише в жодні канали, які споживає Aurora (ніяких `CMD:*`, ніяких “apply modulation”);
  - будь‑які “плани/рекомендації” пишуться лише у вихідні артефакти Neocortex.

- **0 запису в артефакти Aurora**
  - Neocortex не пише у `ops/`, `logs/`, `data/` трейдера;
  - працює у власному `workdir` (окремі `inbox/`, `out/`, `db/`, `models/`).

### 1.2. Дозволений мінімальний контакт із системою

Єдине дозволене — **read‑only споживання копій даних**:
- копія `ops/wal/*.jsonl` (WAL) у папку `inbox/wal/`;
- (опційно) незалежно зібрані ринкові дані/кандли у `inbox/market/`.

Рекомендація: *не tail-ити “живі” файли трейдера*, а працювати по схемі “експорт → інгест”.

---

## 2) Джерела даних (inputs) без змін у коді Aurora

### 2.1. WAL як канонічний причинний слід (обовʼязково)

WAL уже містить усе потрібне для аудиту каузальності (що запропонувалося/що виконалося/що сталося).
Типовий запис (JSONL) має поля на кшталт:
- `op`: `"EVT" | "CMD" | ...` (на практиці часто `EVT`)
- `verb`: `"TRADE_INTENT_PROPOSED"`, `"ORDER_FILLED"`, …
- `src`, `dst`
- `rid` (correlation id)
- `ts` або `timestamp` (unix ms/seconds — треба нормалізувати)
- `pld` (payload)
- `_prev`, `_hash` (hash‑ланцюг, якщо ввімкнено)

**Трансфер WAL у Standalone (offline‑first):**
- стратегія: `copy-only` (додаємо тільки нові файли/рядки, не модифікуємо джерело)
- приклад (вручну або cron на стороні оператора):
  - `rsync -av --ignore-existing /path/to/Phenix/ops/wal/ /path/to/neocortex/inbox/wal/`

### 2.2. Щільний State Stream (опційно, але важливо для R1+)

WAL зазвичай “подієво‑розріджений” (selection bias: бачимо більше даних у моменти активності).
Щоб будувати World Model/Viability більш коректно, потрібен регулярний “стан середовища”.

Оскільки ми **не чіпаємо код Aurora**, State Stream робимо автономно одним з варіантів:

- **Варіант S1 (рекомендовано, незалежний збір):** окремий збирач кандлів/OB з біржі → власний `features_tape.jsonl`.
  - плюси: нуль звʼязку з Aurora; дані щільні;
  - мінуси: треба повторити feature‑engineering (хоча б частково).

- **Варіант S2 (якщо WAL містить фічі):** якщо в WAL є `FEATURES_*` або подібні payload — витягаємо їх і будуємо `features_tape` пост‑фактум.
  - плюси: простіше;
  - мінуси: може бути не 1–5Hz, і все одно буде bias/прогалини.

На R0 можна стартувати **без** State Stream (тільки WAL), а State Stream додати на R1.

---

## 3) Вихідні артефакти Neocortex (outputs)

Усі артефакти живуть лише в Standalone‑проєкті:

- `out/normalized_events.jsonl` — нормалізовані події (уніфікований контракт)
- `out/state.jsonl` — періодичні “знімки” внутрішнього стану
- `out/alerts.jsonl` — інваріанти/аномалії/помилки контрактів
- `out/shadow_plans.jsonl` — “що б я зробив” (тільки для R2, без actuation)
- `reports/YYYY-MM-DD.md` — денні репорти
- `db/neocortex.sqlite` або `db/neocortex.duckdb` — структурований стор
- `models/*` — моделі/ваги (R1+)

---

## 4) Контракти (schemas) без імпорту `vfoundation`

У концепті пропонувався конверт `vfoundation.core.protocol.Message`. Для ізольованого домену це замінюємо на **локальні контракти**, сумісні за змістом.

### 4.1. EventEnvelope (мінімум для R0)

Власний JSON Schema (приклад полів, не код):
- `event_id` (uuid)
- `ts` (unix ms)
- `op` (`EVT|CMD|...` як у джерелі)
- `verb` (рядок)
- `src`, `dst`
- `rid` (uuid/str)
- `payload` (обʼєкт)
- `raw_ref` (посилання на джерело: `filename:line`)
- `hash_prev`, `hash` (якщо є)

### 4.2. Observation (для R1+)

- `symbol`
- `features` (числовий вектор/словник)
- `portfolio` (спрощено)
- `last_intent` (спрощено)
- `market_ts`

### 4.3. ShadowPlan (для R2)

- `symbol`, `ts`
- `action` (`OPEN_LONG|OPEN_SHORT|HOLD|CLOSE|...`)
- `confidence`, `risk_estimate`, `why[]`
- `evaluation_ref` (посилання на backtest/counterfactual)

---

## 5) Архітектура Standalone процесу (модулі)

### 5.1. Ingest

Задача: перетворити “сирий WAL” → “нормалізовані події”.

Вимоги:
- інкрементальність (offset per file + last_hash)
- ідемпотентність (не дублювати при повторному прогоні)
- валідація:
  - коректний JSON
  - наявність `op/verb/ts/rid`
  - опційно: перевірка hash‑ланцюга `_prev/_hash`

### 5.2. State Store

Задача: тримати компактний стан по кожному `symbol` і по активних `rid` (епізод).

Мінімальні сутності R0:
- `Episode` (rid, symbol, side, open_ts, close_ts, outcome)
- `PositionState` (flat/open, qty, avg_price, brackets state якщо є)
- `IntentState` (остання пропозиція intent + ttl)

### 5.3. Evaluator (R0)

Задача: метрики + інваріанти.

Приклади інваріантів (почати з них):
- `INTENT(open) -> eventually POSITION_OPENED or INTENT_EXPIRED` (таймаут/TTL)
- `POSITION_OPENED -> eventually BRACKETS_PLACED` (якщо ваша система очікує brackets)
- “no qty=0 close intent”
- “no naked position” (position open без менеджменту)
- “flip storm” (надмірна частота інтенцій/переворотів)

### 5.4. World Model / Latent / Viability (R1+)

У R0 ці модулі можуть бути stub’ами. На R1:
- baseline world model (EMA/AR) для прогнозу простих метрик
- viability (AE + conformal поріг) для OOD
- EFE/empowerment як аналітичні метрики (без actuation)

### 5.5. Output + Reporting

- JSONL‑логи (state/alerts)
- Markdown репорт “що сталося за період”
- опційно: HTML/Plotly для графіків (але не обовʼязково для R0)

---

## 6) Де жити цьому коду: рекомендована організація

### Варіант A (рекомендовано): окремий git‑репозиторій

1) Створити новий репо, наприклад `neocortex-standalone/`.
2) Відразу зафіксувати “no‑dependency boundary”:
   - жодних сабмодулів на Phenix
   - ніякого `pip install -e /path/to/Phenix`
3) Підняти свій `pyproject.toml`/venv.

### Варіант B (допустимо, якщо дуже зручно): папка в монорепо

Якщо фізично треба тримати все поруч, створити, наприклад:
- `sandbox/neocortex_standalone/`

і гарантувати:
- відсутність імпортів з `Phenix/*`;
- відсутність будь‑яких згадок у runtime‑конфігах Aurora;
- запуск тільки вручну окремою командою.

---

## 7) Покроковий план реалізації (з DoD)

### Phase 0 — Bootstrap (скелет Standalone)

**Задачі:**
1) Створити репо/папку, структуру модулів (`ingest/`, `store/`, `report/`, `schemas/`).
2) Додати CLI:
   - `neocortex ingest --inbox ./inbox --db ./db/neocortex.sqlite`
   - `neocortex report --db ... --out ./reports/...`
3) Визначити JSON‑контракти (schemas) + версіонування.

**Definition of Done:**
- CLI запускається на тестовому шматку WAL і створює `db/` + `out/normalized_events.jsonl`.

### Phase 1 — R0 Observer (офлайн аналіз WAL)

**Задачі:**
1) Інкрементальна інгестація WAL:
   - підтримка “додали нові файли/рядки”;
   - збереження `offset.json` (які файли/позиції вже зʼїли).
2) Нормалізація часу (`ts`/`timestamp`, seconds/ms) + нормалізація `symbol`/`instrument`.
3) Відновлення епізодів і таймлайнів:
   - intent → order → fill → position open/close.
4) Перші інваріанти/алерти:
   - missing brackets / unexpected reduce_only / qty=0 / stale intents / churn.
5) Денний репорт (Markdown) + агрегати по символах/стратегіях.

**Definition of Done:**
- на копії `ops/wal/*.jsonl` за день генерується `out/alerts.jsonl` і `reports/YYYY-MM-DD.md`;
- повторний запуск не дублює записи (ідемпотентність).

### Phase 2 — R0 Continuous (черга “inbox”, без tail живого WAL)

**Задачі:**
1) “Watcher” який сканує `inbox/wal/` і підхоплює нові файли.
2) Політика неповних файлів:
   - або “обробляємо тільки закриті файли” (простий варіант),
   - або “читаємо дозовано” (як `tail -F`, але по копії).
3) Ротація/retention вихідних артефактів.

**Definition of Done:**
- процес може працювати 24/7, обробляючи нові WAL‑файли з `inbox/`, не торкаючись Aurora.

### Phase 3 — R1 Latent + Viability (додаємо стан середовища)

**Задачі:**
1) Визначити джерело State Stream (S1 або S2).
2) Зібрати “щільні” спостереження (1–5Hz або по барах).
3) Побудувати простий latent (ембед) + viability (AE).
4) Додати алерти OOD/аномалій.

**Definition of Done:**
- є відтворюваний пайплайн, який тренує viability‑модель на історії і валідно детектить OOD на наступному дні.

### Phase 4 — R2 Shadow Advisor (лише рекомендації)

**Задачі:**
1) Генерувати `shadow_plans.jsonl` (OPEN/HOLD/CLOSE) з `why`.
2) Оцінювати “що б було” (простий симулятор/контрфакт):
   - хоча б порівняння “якщо HOLD” vs “як було”.
3) Репорт розбіжностей: “Aurora зробила X, Cortex пропонував Y”.

**Definition of Done:**
- щоденний репорт містить таблицю divergences + приблизну оцінку impact (без торгівлі).

### Phase 5 — R3 (інтеграція) — **не входить у цей план**

Усе, що передбачає будь‑який “вплив” на Aurora (Modulation Interface, командний канал), має бути окремим RFC/планом і запускатися тільки після формального safety‑аудиту.

---

## 8) Операційні правила (щоб домен залишався “закритим”)

- Запускати Neocortex під окремим користувачем або хоча б в окремому venv.
- `workdir` Neocortex не перетинається з директоріями Aurora.
- Будь‑який код, що пише у `ops/wal` або `config/aurora`, заборонений (технічно — через ACL/permissions).
- Усі “плани” — тільки в `out/` та `reports/`.

---

## 9) Чек‑лист старту R0 (коротко)

1) Створити Standalone‑проєкт (варіант A або B).
2) Налаштувати `inbox/wal/` і ручний/cron експорт WAL з Aurora.
3) Реалізувати `ingest` + `report`.
4) Прогнати на 1 дні WAL, перевірити:
   - відновлення епізодів,
   - алерти,
   - ідемпотентність.
