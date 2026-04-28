# Neocortex — архітектура та креслення

## 1) Контекст системи (Aurora як середовище)

```mermaid
graph TD
  subgraph Aurora[Aurora Runtime]
    FE[feature_engineering]
    RM[risk_management]
    PT[position_tracking]
    RD[regime_detector]
    DM[decision_making]
    EP[execution_position]
    WAL[(ops/wal/*.jsonl)]
  end

  subgraph Neocortex[Neocortex Domain]
    ING[Ingestor]
    NORM[Normalizer]
    STORE[(State Store)]
    INV[Invariant Engine]
    DATASET[Dataset Builder]
    MODELS[Models: latent/world/viability]
    METRICS[Metrics: EFE/Empowerment]
    PLAN[Planner/Router]
    INTENT[Intent Builder]
    OUT[Logs/Reports]
  end

  WAL --> ING --> NORM --> STORE
  STORE --> INV --> OUT
  STORE --> DATASET --> MODELS --> METRICS
  METRICS --> PLAN --> INTENT --> OUT

  FE -->|EVT:FEATURES_CALCULATED| STORE
  RM -->|EVT:RISK_ASSESSMENT_COMPLETED| STORE
  PT -->|EVT:PORTFOLIO_STATE_UPDATED| STORE
  RD -->|EVT:REGIME_DETECTED| STORE
  DM -->|EVT:TRADE_INTENT_PROPOSED| STORE
  EP -->|EVT:ORDER_ACK/FILL/POSITION_*| STORE
```

Принципи:
- **R0–R2:** Neocortex не має жодного “зворотного каналу” у торгівлю (тільки лог/репорт).
- **R3:** будь‑який вплив тільки через окремо задокументований і заґейтований інтерфейс (allowlist + TTL + audit).

---

## 2) Потоки виконання

### 2.1. Standalone (offline‑first) ingest WAL → store → alerts/report

```mermaid
sequenceDiagram
  autonumber
  participant NC as Neocortex
  participant WR as WAL Reader
  participant NZ as Normalizer
  participant DB as Store (SQLite/DuckDB)
  participant IE as Invariants
  participant RP as Reporter

  loop scan interval
    NC->>WR: scan inbox WAL (glob)
    WR->>WR: read new lines (offsets)
    WR->>NZ: raw JSON line
    NZ->>DB: upsert EventEnvelope
    DB->>IE: update episode/indexes
    IE->>DB: persist Alert
  end

  NC->>RP: generate daily report
  RP->>DB: aggregate metrics
  RP-->>NC: report.md + summaries
```

### 2.2. In‑proc (FSM bus) — тільки для low‑latency R2/R3

```mermaid
sequenceDiagram
  autonumber
  participant FE as feature_engineering
  participant FSM as FSMCore
  participant NC as neocortex
  participant DM as decision_making
  participant EP as execution_position

  FE->>FSM: EVT:FEATURES_CALCULATED
  FSM->>NC: Message
  NC->>NC: update state/latent
  NC->>FSM: EVT:NEOCORTEX_STATE_UPDATED (monitoring)

  DM->>FSM: EVT:TRADE_INTENT_PROPOSED
  FSM->>NC: Message
  NC->>NC: divergence + shadow intent (R2)

  EP->>FSM: EVT:ORDER_FILL / EVT:POSITION_CLOSED
  FSM->>NC: Message
  NC->>NC: episode outcome + alerts
```

---

## 3) Машина станів ingest (щоб не “розмазати” edge cases)

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Scanning: tick
  Scanning --> Reading: file found
  Reading --> Parsing: line read
  Parsing --> Normalizing: valid json
  Parsing --> BadLine: invalid json
  Normalizing --> Persisting
  Persisting --> Reading
  BadLine --> Reading: count++ / policy
  Reading --> Scanning: EOF / rotate
  Scanning --> Idle
```

Ключові політики (все з YAML):
- обробляти тільки “закриті” WAL файли або дозволяти partial‑tail (але тільки на копії);
- `max_bad_lines = 0` у strict‑режимі (fail‑closed для R0 аналізу);
- timestamp‑нормалізація без евристик (явні правила для `ts`/`timestamp`).

---

## 4) “Креслення” компонентів (what to implement)

### 4.1. Ingestor

Вхід: `ops/wal/*.jsonl` (або копія).
Вихід: `EventEnvelope` (нормалізований контракт) + offset state.

Обовʼязково:
- idempotent ingestion (offsets + dedup ключ);
- інтегриті‑перевірка hash chain (якщо `_prev/_hash` присутні).

### 4.2. State Store

Мінімум таблиць/колекцій:
- `events` (raw + normalized)
- `episodes` (rid + lifecycle)
- `alerts` (інваріанти/аномалії)
- `shadow_intents` (R2)

### 4.2.a. Training provenance boundary

Для ML/RL dataset builder, який читає `EVT:TRADE_INTENT_PROPOSED` з WAL:
- pre-cutover поля `p`, `payoff_ratio_r` і `size.kelly_fraction` вважаються **untrusted**, бо до прийнятого Kelly provenance repair вони могли бути synthetic boundary metadata;
- точну cutover boundary треба записувати в Kelly acceptance re-audit report і дублювати в ingest/reporting surface перед увімкненням цих полів у train/eval dataset;
- якщо cutover boundary не зафіксована, dataset builder має маскувати ці Kelly поля або явно позначати їх як `provenance_untrusted_pre_cutover`.

### 4.3. Invariant Engine

Працює на timeline/episodes і викидає `NEOCORTEX_ALERT`:
- missing brackets / missing fill / close anomalies / churn / stale intents.

### 4.4. Model Layer (R1+)

Окремі модулі:
- viability (AE + conformal tau)
- world model ensemble (uncertainty)
- EFE/empowerment як метрики (не як “магічні” скори)

---

## 5) Вузькі місця (попередження)

Проблемні зони, які треба врахувати в дизайні/коді:
- WAL schema drift (частина записів має `ts`, частина `timestamp`, `rid` може бути в `pld.rid`);
- змішані одиниці часу (seconds vs ms);
- обʼєм WAL (потрібен інкрементальний ingest + індексація, інакше буде дуже повільно);
- selection bias, якщо вчитись лише по WAL (на R1 потрібен “щільний” state stream);
- deterministic behavior: всі рішення router/selector мають бути відтворювані з `rng_seed`.

