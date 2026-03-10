# Neocortex — тестування та acceptance критерії

## 1) Цілі тестування

- Гарантувати **SSOT конфігів** (YAML) без hardcoded дефолтів у коді.
- Гарантувати **відтворюваність** (replay WAL → однакові alerts/reports).
- Гарантувати **безпеку**: R0–R2 не мають впливу на торгівлю.

---

## 2) Матриця тестів

### 2.1. Config Contract (обовʼязково)

- missing key → startup crash
- extra key → startup crash
- unresolved `${VAR}` → startup crash
- “no defaults” guard для `config_models.py`
- заборона `os.getenv` у домені (окрім YAML `${VAR}` резольверу)

### 2.2. Unit (математика/ядро)

- timestamp normalization
- WAL normalizer (rid/symbol/ts)
- viability calibrator (tau), deterministic on fixture
- world model: forward/update/nll finite
- router deterministic selection

### 2.3. Contract (events)

- `NEOCORTEX_*` payload schemas (див. `apps/reference/domains/neocortex/docs/EVENTS.md`)
- TradeIntent payload валідний під `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`

### 2.4. Integration

- ingest `wal_small.jsonl` → alerts/report
- ingest `features_tape_small.jsonl` → state updates (R1)
- shadow intents + divergence report (R2)

---

## 3) Фікстури

Рекомендована структура:
- `tests/domains/neocortex/fixtures/wal_small.jsonl`
- `tests/domains/neocortex/fixtures/features_tape_small.jsonl`
- `tests/config/aurora/neocortex/*` (повний комплект YAML)

---

## 4) Acceptance (DoD)

R0:
- ingest ідемпотентний, replay відтворюваний
- alerts/report стабільні
- 0 side effects

R1:
- viability/world/efe/empowerment відтворювані
- немає degraded‑режимів

R2:
- shadow_intents без спаму (idempotent_key)
- divergence report відтворюваний

