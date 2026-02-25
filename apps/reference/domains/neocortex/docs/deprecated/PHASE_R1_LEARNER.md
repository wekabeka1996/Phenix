# Phase R1 — Learner (state stream → latent/world/viability → metrics)

Ціль R1: навчити “внутрішній стан” і базові метрики (EFE/empowerment/viability), не впливаючи на торгівлю.

---

## 0) Що додається відносно R0

1) Щільний state stream (features_tape) без selection bias.
2) Dataset builder (вікна, епізоди).
3) Моделі:
   - Viability (AE + conformal tau)
   - World model ensemble (uncertainty)
4) Метрики:
   - surprisal/disagreement/EFE
   - empowerment proxy (без fallback chain)

---

## 1) Кроки реалізації (покроково)

### Крок 1.1 — State Stream SSOT

Варіанти:
- **S1 (кращий):** `features_tape.jsonl` 1–5Hz або бари, збирається незалежно від intents.
- **S2:** витяг фіч з WAL (якщо вони там регулярні) — гірше, можливі прогалини.

DoD:
- визначено і задокументовано формат одного запису `features_tape.jsonl`.

### Крок 1.2 — Feature Contract (які саме фічі входять у R1)

У YAML (`models.yaml`) задається:
- список feature keys,
- нормалізація (robust_z/minmax/zscore),
- clamp rules.

DoD:
- якщо feature key відсутній у потоці → це або crash (strict), або `NEOCORTEX_ALERT` (policy з YAML).

### Крок 1.3 — ViabilityModel (без fail-open для інтенцій)

Правило:
- до калібрації `tau` Neocortex може рахувати reconstruction error, але:
  - **не має права** генерувати жодні trade intents (R3) і навіть shadow intents можуть бути помічені як `uncalibrated=true`.

DoD:
- є стабільний `tau` після `min_count` і він логиться у `NEOCORTEX_STATE_UPDATED`.

### Крок 1.4 — World Model Ensemble

Мета: оцінювати:
- `surprisal` (NLL)
- `disagreement` (епістемічна невизначеність)

Вимоги:
- torch — обовʼязкова залежність (немає fallback‑реалізацій).
- детермінізм від `rng_seed` для тестів (де це можливо).

DoD:
- є unit tests на shape/градієнти/стабільність.

### Крок 1.5 — EFE

EFE визначається в YAML вагами та EMA:
- `EFE_t = w_s * EMA(surprisal) + w_d * EMA(disagreement)`

DoD:
- EFE зберігається в state stream і доступний для R2 scoring.

### Крок 1.6 — Empowerment (proxy без “fallback chain”)

В R1 empowerment не керує діями, а лише вимірює “керованість”.

Вимоги:
- чіткий action space (з YAML), навіть якщо ми не діємо.
- контрастивна оцінка (InfoNCE) або інша визначена в YAML.

DoD:
- empowerment стабільний на фікстурі.

---

## 2) Тести R1

- unit: viability calibration (tau) deterministic on fixed seed/data
- unit: world model forward/update, NLL finite
- integration: ingest features_tape + WAL → state updated lines

---

## 3) Коли R1 можна вважати завершеним

R1 завершений, якщо:
- є щільний state stream + dataset builder;
- viability/world/efe/empowerment працюють відтворювано;
- немає жодних “degraded fallback” шляхів у критичних компонентах;
- немає впливу на торгівлю.

