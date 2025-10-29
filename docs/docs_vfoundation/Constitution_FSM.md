# КОНСТИТУЦІЯ v2.2 — FSM-LLM Федеративна Модульна Архітектура (vFoundation)

*(із доповненнями про Надійність/Відновлення, Спостережність/Відладку, Інструменти, Дані та Безпеку)*

> Цей документ — єдине джерело істини для людей і LLM. Він розширює v2.1, **нічого не ламає**, а додає обов’язкові практики для production-ready систем.

---

## 0) Як користуватись

1. Встав цей текст **першим** у “HQ/Проєкт” чат і зафіксуй: *усі рішення та відповіді — строго в межах Конституції*.
2. Далі додавай: доменну концепцію, roadmap, Global/Domain Dictionaries, RFC, креслення.
3. Для коду — окремі **модульні** чати; у HQ — дизайн/контракти/плани.

---

## 1) Проблема → Мета (нагадування)

Моноліти з LLM розвалюються від контекстного колапсу, “вічних покращень” та ламких зв’язків. Рішення — **федерація доменів** з **Domain FSM** (гарячий шлях), **Meta-FSM** (стратегія), **контрактами подій**, **safety-вето**, **fail-closed**, **XAI** та тепер — **DR/Observability/Tooling/Data-Security**.

---

## 2) Словник понять (ядро v2.1 без змін)

* **Модуль**, **Домен**, **Domain FSM**, **Meta-FSM**, **Global/Domain Dictionary**, **Freeze**, **RFC**, **why/why_chain** — як у v2.1.
* Нові системні сенсори (v2.1): **EntropyMonitor**, **TopologyAuditor**, **Intent Layer**, **Latent State Embeddings** — чинні.

---

## 3) Десять інваріантів (без змін)

1. Контракт > код. 2) Модульність + Freeze. 3) Safety має вето. 4) Fail-closed.
2. why обов’язково. 6) Ідемпотентність/порядок. 7) Additive-only.
3. Керованість (≤12 verbs/домен; ≤20 станів/FSM). 9) Спостережність.
4. Жодних “обходів” FSM.

---

## 4) Федеративна модель (нагадування коротко)

* **Тактика (Домени)**: 3–5 автономних кланів з власним **Domain FSM** (hot path).
* **Стратегія (Meta-FSM)**: міждоменні агрегати/директиви (slow/normal path).

---

## 5) Протокол повідомлень (розширено)

### 5.1 OP/verbs/intent (як у v2.1)

* **OP:** `ASK | DEC | EVT | UPD | ERR`
* **StdLib verbs:** `EVAL, OPEN, CLOSE, SCALE, ADJUST, AUTH, READ, WRITE, PING, HEALTH, WHY, ALERT, RECONCILE, CMD`
* **intent:** `INQUIRY | COMMAND | PROPOSAL | OBSERVATION | DECLARATION`

### 5.2 Каркас повідомлення (доповнено для трасування/даних/відлад)

```json
{
  "v": 2,
  "op": "ASK|DEC|EVT|UPD|ERR",
  "verb": "EVAL|OPEN|CLOSE|CMD|...",
  "intent": "INQUIRY|COMMAND|PROPOSAL|OBSERVATION|DECLARATION",
  "src": "module_or_domain",
  "dst": "module_or_domain|any",
  "rid": "uuid",                 // також використовується як trace_id
  "span_id": "uuid",             // для міждоменних спанів
  "parent_span_id": "uuid|null",
  "ts": 1731234567890,
  "key": "resource/position/user",
  "ttl_ms": 2000,
  "pld": {},
  "why": "≤80 chars",            // hot-path пояснення
  "why_explain_ref": "uri|null", // cold-path детальна довідка (XAI store)
  "data_ref": [                  // посилання на великі дані (data-by-reference)
    {"uri":"s3://.../obj", "sha256":"...", "bytes":1234567, "ctype":"application/parquet", "ttl_ms": 600000}
  ],
  "sig": "optional"              // ed25519 підпис для критичних CMD/DEC
}
```

---

## 6) Продуктивність і маршрутизація (як у v2.1)

* **Режими:** `hot_path (in-proc)`, `warm_path (shared memory)`, `cold_path (MQ)`
* **TTL-профілі:** `critical | fast | normal | ml_slow | background`
* **Політика:** `safety_timeout_behavior: DENY`

---

## 7) Інтелектуальні принципи (вбудований “розум”, як у v2.1)

* **EntropyMonitor** → EVT:ENTROPY_SPIKE
* **Intent Layer** → QoS/пріоритезація
* **TopologyAuditor** → EVT:TOPOLOGY_DRIFT_DETECTED
* **Latent Embeddings** → предиктивні CMD

---

# 8) Надійність та Відновлення (Disaster Recovery & Resilience)

### 8.1 Цілі DR

* **RTO** (відновлення часу): критичні домени ≤ **5–15 хв**, не-критичні ≤ **1–4 год**
* **RPO** (втрата даних): критичні ≤ **1 хв**, не-критичні ≤ **15 хв**

### 8.2 Джерела істини та журнали

* **Immutable WAL (append-only) для повідомлень** (per-domain): з **hash-ланцюгом** (Merkle-root/щоденний якор у публічний журнал або об’єкт-блокування S3 WORM).
* **Снапшоти станів** доменів (checkpoint кожні `N` хв) + **redo** із WAL для реконструкції.
* **Global/Domain Dictionary** + схеми зберігаються в **geo-реплікованому** репо (версії/міграції підписані).

### 8.3 Реконструкція стану (state reconstruction)

1. Відновити **останній снапшот** домену.
2. Програти WAL **з моменту снапшоту** до `ts_failover`.
3. **Ідемпотентність per rid** гарантує коректність дій при повторному застосуванні.
4. **Перевірити інваріанти домену** (баланси, ліміти, позиції).
5. Позначити `RECONCILE` подіями розбіжності; Meta-FSM може видавати `CMD:REPAIR`.

### 8.4 Degradation (граційне зниження)

* **При дефіциті ресурсів / високій ентропії:**

  * відкидати `ASK:INQUIRY` (низький пріоритет),
  * зменшити частоту `EVT:DATA_READY` (coalesce),
  * перейти на **safe policy** (`CMD:SWITCH_TO_LOW_RISK_MODE`),
  * freeze не-критичні домени (лише `READ/HEALTH`).
* **Backpressure:** черги per-key із водяними мітками; коли p95 latency > порог, автоматичний throttle.

### 8.5 Політики retry/circuit breaker (проактивна модель)

```yaml
retry_policies:
  default:
    strategy: exponential_jitter
    base_ms: 50
    max_ms: 2000
    max_attempts: 5
  ml_calls:
    base_ms: 200
    max_ms: 10000
    max_attempts: 3
circuit_breaker:
  error_rate_window: 60s
  open_threshold: 0.2        # 20% помилок → OPEN
  half_open_probes: 5        # пробні запити
  cooldown: 30s
fallbacks:
  safety_default: DENY       # fail-closed
  exec_degraded: reduce_only # виконання лише зменшує ризик
dead_letter_queue:
  on_exhausted_retries: true
```

### 8.6 Топології DR

* **Active-Active** для критичних доменів (Risk/Exec): geo-рознесені кластери, консенсус на рівні команд (idempotent).
* **Active-Standby** для аналітики/Audit: прогрів stand-by репліки, RTO ≤ 15 хв.

---

# 9) Спостережність і Відладка (Observability & Debug)

### 9.1 Двошарова модель WHY (швидкість vs деталізація)

* **hot_path:** коротке `why` (≤80 символів) у повідомленні.
* **cold_path:** `why_explain_ref` → детальна довідка (дерево причин, промпти LLM, фічі, конфіги) у XAI-сховищі.

### 9.2 Міждоменне трасування

* **trace_id = rid**, з **span_id/parent_span_id** для кожного hop.
* Інтеграція з **OpenTelemetry** (опц.): експортуємо спани/атрибути (verb, intent, ttl_profile, latency_ms, error).
* **Sampling:** hot-path 1–10% (усі ERR=100%), cold-path 100%.

### 9.3 Стандартизований лог-рядок (розширений)

```
ts | rid(trace) | span | parent | op | verb | intent | src→dst | key | ttl | why | why_ref | latency_ms | err? | cb_state
```

### 9.4 Debug endpoint (безпечно)

* `GET /debug/{rid}` (RBAC + redaction): повертає **повний шлях** (спани, why_chain, why_explain, payload-диф, підписи).
* `GET /replay/{rid}`: dry-run реплей із журналу (тільки для sandbox).
* **Alert hooks:** на EVT:ENTROPY_SPIKE/TOPOLOGY_DRIFT/ERR% threshold.

---

# 10) Ефективність розробки і супроводу (LLM-pipeline, CLI, IDE)

### 10.1 LLM-оптимізації (зменшуємо ітерації)

* **contract_validator (pre-gen):** перед генерацією коду LLM отримує схеми/словники та проходить тест відповідності (забороняє фантазувати поля/verbs).
* **auto_test_generator (post-gen):** LLM спершу генерує контракт-тести (valid/invalid/TTL/idempotency), потім код, що має їх пройти.

### 10.2 CLI-інструменти (приклад)

```
vfound init                         # scaffolding проекту
vfound rfc new <name>               # шаблон RFC
vfound dict lint --global --domain  # словник-лінтер
vfound schema gen --from pydantic   # генерація JSON Schema
vfound test gen --module X          # auto_test_generator
vfound simulate flow <file.yaml>    # прогін інтеграційного сценарію
vfound trace get <rid>              # витяг трасування
vfound replay <rid> --dry-run       # реплей із WAL
```

### 10.3 IDE-плагіни (напрямок)

* CodeLens над `handle_message`: показує допустимі `OP/verb` з Dictionary.
* Quick-fix: “додай why”, “перевір TTL-профіль”, “перевір ідемпотентність per rid”.

### 10.4 Governance для схем (боремось із schema bloat)

* **Композиція через `$ref`** (base/* + domain/*).
* **Версіонування семантичне** (`_v1`, `_v2`), **deprecation windows** ≥ 2 релізи.
* **Schema-budget** per домен (напр., ≤ N нових схем/квартал) — перевищення → RFC-обґрунтування.
* **semantic diff** у CI; **auto-RFC draft** із дифа схеми.

---

# 11) Дані та Безпека

### 11.1 Великі дані — “by reference” (data_lake_integration)

* Повідомлення містить **`data_ref`**: `{uri, sha256, bytes, ctype, ttl_ms}`
* Доступ — по **тимчасових підписаних URL** (KMS), читання **streaming**.
* Заборонено вкладати великі масиви/файли у `pld` (шина — для подій, не для даних).

### 11.2 Підписання критичних операцій

* **Обов’язково підписувати `CMD/*` і `DEC/*`** (ed25519/KMS), політика ротації ключів, перевірка підписів у FSM перед виконанням.
* Підпис включає **хеш payload + метадані** (`rid, ts, src, dst, verb`).

### 11.3 Не-змінність журналів (immutable logging)

* **WORM-сховище** (Object Lock) для WAL та XAI-артефактів.
* **Хеш-ланцюг** і щоденний **Merkle-root** якориться (напр., у зовнішній реєстр/нотариат).

### 11.4 Контроль доступу та приватність

* **RBAC/ABAC** для /debug, /replay, /metrics, data_ref.
* **Redaction** чутливих полів у логах/ендпоінтах.
* **Rate-limits** на критичні verbs (CMD/OPEN/CLOSE).
* **Secret-management** централізовано (KMS), ключі — **не** у коді.

---

# 12) Тестування та якісні гейти (оновлено)

**Стратегія** (як у v2.1) + додатково:

* **DR-тести:** реконструкція стану зі снапшоту+WAL; RTO/RPO у межах цілей.
* **Chaos-тести:** ін’єкція TIMEOUT/CB-OPEN/мережевих розривів.
* **Observability-тести:** трасування end-to-end, цілісність why_chain/why_ref.

**Пороги:**

* why_chain coverage ≥ **95%** (ERR-випадки — 100%).
* p95 FSM (hot) ≤ **50мс**, загальний ≤ **100мс**; ERR:TIMEOUT ≤ **1%**.
* **CB health:** частка OPEN < **2%** запитів, середній час у OPEN ≤ **60с**.
* **DR:** відтворення стану ≤ **RTO**, втрата ≤ **RPO**.
* **LLM-якість:** (simple ≤10% галюцинацій; complex ≤30%; pass-rate ≥ пороги).

---

# 13) Артефакти (оновлені фрагменти)

### 13.1 Global Dictionary (міждоменно, доповнено трасуванням/політиками)

```yaml
version: 2.2
scope: inter-domain protocol (Meta-FSM)
ops: [ASK, DEC, EVT, UPD, ERR]
stdlib_verbs: [CMD, ALERT, RECONCILE, HEALTH, WHY]

routing:
  EVT:HIGH_VOLATILITY_DETECTED: [risk_strategy, audit_xai]
  CMD:SWITCH_TO_LOW_RISK_MODE:  [risk_strategy, execution_position]

policies:
  safety_veto: true
  fail_closed: true
  safety_timeout_behavior: DENY

routing_modes:
  hot_path:  [CMD:*, DEC:CMD]
  warm_path: [EVT:*]
  cold_path: [RECONCILE:*, WHY:*]

ttl_profiles:
  critical: 50
  fast: 200
  normal: 2000
  ml_slow: 10000
  background: 30000

dr:
  rto_critical_min: 5m
  rpo_critical_max: 1m

observability:
  trace: { use_rid_as_trace_id: true, sample_err: 1.0, sample_hot: 0.1 }
  debug_endpoint: "/debug/{rid}"

security:
  require_signature_for: ["CMD:*", "DEC:*"]
  log_storage: "WORM+hash_chain"
```

### 13.2 Module policy (retry/circuit breaker)

```yaml
module: exec_gateway
retry_policy: { strategy: exponential_jitter, base_ms: 50, max_ms: 2000, max_attempts: 5 }
circuit_breaker: { open_threshold: 0.2, error_rate_window: 60s, half_open_probes: 5, cooldown: 30s }
degradation: { mode: reduce_only, drop_low_priority_intents: [INQUIRY] }
```

### 13.3 DR Snapshot & WAL метадані

```yaml
state_snapshot:
  domain: execution_position
  ts: 1731234500000
  uri: s3://bucket/snapshots/exe_pos/2025-10-11T10:15Z.bin
  sha256: "..."
wal_segment:
  from_ts: 1731234500001
  to_ts:   1731234899999
  uri: s3://bucket/wal/exe_pos/2025-10-11.part-42.jsonl
  merkle_root: "..."
```

---

# 14) Пілот (2 тижні) — доповнені цілі

* **Домени:** `risk_strategy`, `execution_position`, `audit_xai`.
* **Потоки:** як у v2.1 + **ін’єкція відмов**, перевірка **DR-відтворення**.
* **Метрики успіху:** p95 ≤ 100мс; why_chain 100% на ключових рішеннях; CB-OPEN <2%; DR у межах RTO/RPO; 0 contract-break; 0–1 hotfix з процедурою.

---

## 15) Анти-патерни (нагадування + нові)

* Вкладати великі дані у `pld` → ❌ (використовуй `data_ref`)
* Відсутність підписів на `CMD/DEC` у проді → ❌
* Відсутність снапшотів/WAL → ❌
* Debug без RBAC/redaction → ❌

---

## 16) Реалізаційна примітка (фреймворк vFoundation)

* Як і у v2.1: Python 3.10+, Pydantic → JSON-Schema, Redis (warm/cold), in-proc (hot), FastAPI (/health, /metrics, /debug), OpenTelemetry (опц.).
* Додаємо: **WORM-бекенд** для журналів, **KMS** для підписів/URL, **CLI** з розділу 10.2.

---


