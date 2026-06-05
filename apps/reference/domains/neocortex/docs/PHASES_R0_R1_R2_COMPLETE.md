# Neocortex — Фази R0, R1, R2 (повний цикл)

Повна реалізація асоціативного вівбір-фіча машинізму для Phenix. Три послідовні фази від пасивного спостерігача до активного аналізатора.

---

## Огляд архітектури

```
R0 (Observer)       → WAL ingest + state + alerts + report
    ↓
R1 (Learner)        → feature stream + viability + world model + EFE + empowerment
    ↓
R2 (Shadow Advisor) → shadow intents + divergence report
```

---

# Phase R0 — Observer (WAL ingest → state → alerts → report)

Ціль R0: **пасивний спостерігач**, який не впливає на торгівлю і дає:
- відтворюваний ingest WAL,
- state store (episodes/таймлайни),
- інваріанти/алерти,
- щоденний репорт.

> На R0 ми не робимо ML. Ми робимо "правильну інженерію даних" і контракт‑аудит.

---

## R0 — Артефакти (що має зʼявитись на виході)

У `logs/neocortex/` (або інший path з YAML):
- `offsets.json` — інкрементальний прогрес ingest
- `normalized_events.jsonl` (optional) — нормалізований стрім
- `alerts.jsonl` — алерти інваріантів
- `reports/YYYY-MM-DD.md` — щоденний репорт
- `neocortex.sqlite` / `neocortex.duckdb` — стор

---

## R0 — Кроки реалізації (покроково)

### Крок 1.1 — Конфіги R0 (SSOT)

1) Додати `config/aurora/neocortex/system.yaml` (paths/logging/phase).
2) Додати `config/aurora/neocortex/ingest.yaml` (WAL rules + time normalization).
3) Додати `config/aurora/neocortex/store.yaml` (DB backend + retention).
4) Додати `config/aurora/neocortex/safety.yaml` (інваріанти thresholds, TTLs).

DoD:
- missing key → crash (Pydantic V2).
- unresolved `${VAR}` → crash.

### Крок 1.2 — WAL Reader (інкрементальний ingest)

**Вхід:** директорія WAL, glob, offsets.  
**Вихід:** потік рядків JSONL, які ще не були оброблені.

Політика:
- обробляємо файли у стабільному порядку (lexicographic по назві, або explicit "date sort").
- offsets зберігаються як:
```json
{
  "files": {
    "2026-01-02.jsonl": {
      "bytes": 1234567,
      "lines": 9876,
      "last_hash": "..."
    }
  }
}
```

Edge cases:
- частково дописаний файл (немає `\n` в кінці) → не читаємо останній неповний рядок.
- ротація файлів → offsets по filename, не по inode.

DoD:
- повторний запуск не дублює події.

### Крок 1.3 — Normalizer (WAL → EventEnvelope)

Мета: зробити один контракт, незалежно від форми WAL запису.

**Mapping‑таблиця (приклад):**
- `ts_ms`:
  - якщо є `ts` → беремо `ts` і трактуємо як ms (YAML rule)
  - інакше якщо є `timestamp` → трактуємо як seconds (YAML rule) і множимо на 1000
- `rid`:
  - root `rid` або `pld.rid`
- `symbol`:
  - `pld.symbol` або `pld.instrument`
- `op/verb/src/dst`:
  - root поля або дефолт‑мапінг (але дефолт дозволений тільки якщо визначений у YAML)

DoD:
- будь‑який запис, що не може бути нормалізований, фіксується як `NEOCORTEX_ALERT` з `code=INGEST_NORMALIZATION_FAILED`.

### Крок 1.4 — Episode Builder (rid → lifecycle)

Мінімальний lifecycle:
- `TRADE_INTENT_PROPOSED` → "episode created"
- `CMD:OPEN`/`ORDER_ACK`/`ORDER_FILL` → "episode executing"
- `POSITION_OPENED` → "episode open"
- `CMD:CLOSE`/`POSITION_CLOSED` → "episode closed"

DoD:
- для кожного `rid` з intent маємо відновлюваний timeline.

### Крок 1.5 — Invariants/Alerts

Всі інваріанти конфігуруються в YAML (allowlist кодів, thresholds).

Початковий набір:
- `INVARIANT_INTENT_EXPIRED_NO_EXECUTION`
- `INVARIANT_POSITION_OPENED_NO_BRACKETS`
- `INVARIANT_QTY_ZERO_CLOSE_INTENT`
- `INVARIANT_FLIP_STORM`
- `INVARIANT_PORTFOLIO_STALE_WHEN_INTENT`

DoD:
- `alerts.jsonl` має стабільний формат і не змінюється без bump версії.

### Крок 1.6 — Report Generator

Щоденний репорт (структура):
1) Summary (скільки intents, скільки episodes, PnL summary якщо є)
2) Top alerts (by severity)
3) Churn/flip statistics
4) Data quality (bad lines, missing fields, integrity checks)

DoD:
- репорт відтворюваний при replay того ж WAL.

---

## R0 — Тести

- unit: timestamp normalization, rid extraction, symbol extraction
- unit: offsets (partial line handling)
- integration: ingest `tests/domains/neocortex/fixtures/wal_small.jsonl` → очікуваний `alerts.jsonl`

---

## R0 — Умови завершення

R0 завершений, якщо:
- ingest ідемпотентний;
- репорт/алерти відтворювані;
- немає hardcoded тюнінгів у домені (все у YAML);
- Neocortex не має жодних side‑effects на трейдинг.

---

---

# Phase R1 — Learner (state stream → latent/world/viability → metrics)

Ціль R1: навчити "внутрішній стан" і базові метрики (EFE/empowerment/viability), не впливаючи на торгівлю.

---

## R1 — Що додається відносно R0

1) Щільний state stream (features_tape) без selection bias.
2) Dataset builder (вікна, епізоди).
3) Моделі:
   - Viability (AE + conformal tau)
   - World model ensemble (uncertainty)
4) Метрики:
   - surprisal/disagreement/EFE
   - empowerment proxy (без fallback chain)

---

## R1 — Кроки реалізації (покроково)

### Крок 2.1 — State Stream SSOT

Варіанти:
- **S1 (кращий):** `features_tape.jsonl` 1–5Hz або бари, збирається незалежно від intents.
- **S2:** витяг фіч з WAL (якщо вони там регулярні) — гірше, можливі прогалини.

DoD:
- визначено і задокументовано формат одного запису `features_tape.jsonl`.

### Крок 2.2 — Feature Contract (які саме фічі входять у R1)

У YAML (`models.yaml`) задається:
- список feature keys,
- нормалізація (robust_z/minmax/zscore),
- clamp rules.

DoD:
- якщо feature key відсутній у потоці → це або crash (strict), або `NEOCORTEX_ALERT` (policy з YAML).

### Крок 2.3 — ViabilityModel (без fail-open для інтенцій)

Правило:
- до калібрації `tau` Neocortex може рахувати reconstruction error, але:
  - **не має права** генерувати жодні trade intents (R3) і навіть shadow intents можуть бути помічені як `uncalibrated=true`.

DoD:
- є стабільний `tau` після `min_count` і він логиться у `NEOCORTEX_STATE_UPDATED`.

### Крок 2.4 — World Model Ensemble

Мета: оцінювати:
- `surprisal` (NLL)
- `disagreement` (епістемічна невизначеність)

Вимоги:
- torch — обовʼязкова залежність (немає fallback‑реалізацій).
- детермінізм від `rng_seed` для тестів (де це можливо).

DoD:
- є unit tests на shape/градієнти/стабільність.

### Крок 2.5 — EFE

EFE визначається в YAML вагами та EMA:
- `EFE_t = w_s * EMA(surprisal) + w_d * EMA(disagreement)`

DoD:
- EFE зберігається в state stream і доступний для R2 scoring.

### Крок 2.6 — Empowerment (proxy без "fallback chain")

В R1 empowerment не керує діями, а лише вимірює "керованість".

Вимоги:
- чіткий action space (з YAML), навіть якщо ми не діємо.
- контрастивна оцінка (InfoNCE) або інша визначена в YAML.

DoD:
- empowerment стабільний на фікстурі.

---

## R1 — Тести

- unit: viability calibration (tau) deterministic on fixed seed/data
- unit: world model forward/update, NLL finite
- integration: ingest features_tape + WAL → state updated lines

---

## R1 — Умови завершення

R1 завершений, якщо:
- є щільний state stream + dataset builder;
- viability/world/efe/empowerment працюють відтворювано;
- немає жодних "degraded fallback" шляхів у критичних компонентах;
- немає впливу на торгівлю.

---

---

# Phase R2 — Shadow Advisor (shadow intents + divergence report)

Ціль R2: Neocortex генерує "тіньові" інтенти (без впливу) і порівнює їх із реальною поведінкою Aurora.

---

## R2 — Вхід/вихід

**Вхід:**
- Observation/state (R0)
- metrics (EFE/viability/empowerment) (R1)
- WAL + реальні `EVT:TRADE_INTENT_PROPOSED` (Aurora)

**Вихід:**
- `shadow_intents.jsonl`
- divergence report (Markdown)

---

## R2 — Action Space (SSOT у YAML)

R2 не робить "slerp‑містки в латенті" як ціль. Він працює у **просторі дій**, який легко перекласти в трейдинг:
- `HOLD`
- `OPEN_LONG`
- `OPEN_SHORT`
- `CLOSE`
- `REDUCE_RISK`
- `MODULATE` (тільки як пропозиція, не як дія)

---

## R2 — Router/Scoring (без магії)

Всі ваги та гейти — з YAML:
- hard gates: freshness TTL, viability calibrated, max churn/hour, risk limits
- soft score: expected return proxy, risk proxy, EFE penalty, empowerment bonus

Вимога:
- selection детермінований: `rng_seed` + bucketed time.

---

## R2 — Побудова ShadowIntent

ShadowIntent завжди має:
- `idempotent_key`
- `why[]` з метриками і причинами гейтів
- посилання на observation snapshot (наприклад `raw_ref` або `window_id`)

Формат: див. `apps/reference/domains/neocortex/docs/EVENTS.md` (`EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED`).

---

## R2 — Divergence Report (Aurora vs Neocortex)

Для кожного `symbol` і тайм‑bucket:
- `aurora_action` (витягуємо з `EVT:TRADE_INTENT_PROPOSED`)
- `cortex_action` (shadow)
- `match/mismatch`
- "why mismatch" (коротко)

Метрики:
- mismatch rate
- "cortex would have skipped but aurora traded" rate
- churn proxy (скільки разів cortex хотів flip)

---

## R2 — Умови завершення

R2 завершений, якщо:
- shadow intents генеруються стабільно і без спаму (idempotent_key);
- divergence report відтворюваний по replay того ж WAL;
- контракти подій/логів стабільні (schema + versioning).

---

---

# Резюме та послідовність

| Фаза | Основна мета | Залежність | Вихід |
|------|--------------|-----------|-------|
| **R0** | Пасивний ingest + аудит | — | alerts, reports, episodes |
| **R1** | Навчити метрики + стан | R0 | features_tape, metrics (EFE, viability) |
| **R2** | Shadow intents + аналіз | R0 + R1 | shadow_intents.jsonl, divergence report |

**Ключові принципи:**
- Жоден side-effect на торгівлю до R3.
- Все конфігуруємо в YAML.
- Детермінізм для відтворюваності.
- Контракти версіонуються.
- Тести на кожному етапі.
