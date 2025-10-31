# КОНСТИТУЦІЯ v2.2 — FSM-LLM Федеративна Модульна Архітектура (vFoundation)

*(із доповненнями про Надійні� ть/Відновлення, Спо� тережні� ть/Відладку, Ін� трументи, Дані та Безпеку)*

> Цей документ — єдине джерело і� тини для людей і LLM. Він розширює v2.1, **нічого не ламає**, а додає обов’язкові практики для production-ready � и� тем.

---

## 0) Як кори� тувати� ь

1. В� тав цей тек� т **першим** у “HQ/Проєкт” чат і зафік� уй: *у� і рішення та відповіді — � трого в межах Кон� титуції*.
2. Далі додавай: доменну концепцію, roadmap, Global/Domain Dictionaries, RFC, кре� лення.
3. Для коду — окремі **модульні** чати; у HQ — дизайн/контракти/плани.

---

## 1) Проблема → Мета (нагадування)

Моноліти з LLM розвалюють� я від контек� тного колап� у, “вічних покращень” та ламких зв’язків. Рішення — **федерація доменів** з **Domain FSM** (гарячий шлях), **Meta-FSM** (� тратегія), **контрактами подій**, **safety-вето**, **fail-closed**, **XAI** та тепер — **DR/Observability/Tooling/Data-Security**.

---

## 2) Словник понять (ядро v2.1 без змін)

* **Модуль**, **Домен**, **Domain FSM**, **Meta-FSM**, **Global/Domain Dictionary**, **Freeze**, **RFC**, **why/why_chain** — як у v2.1.
* Нові � и� темні � ен� ори (v2.1): **EntropyMonitor**, **TopologyAuditor**, **Intent Layer**, **Latent State Embeddings** — чинні.

---

## 3) Де� ять інваріантів (без змін)

1. Контракт > код. 2) Модульні� ть + Freeze. 3) Safety має вето. 4) Fail-closed.
2. why обов’язково. 6) Ідемпотентні� ть/порядок. 7) Additive-only.
3. Керовані� ть (≤12 verbs/домен; ≤20 � танів/FSM). 9) Спо� тережні� ть.
4. Жодних “обходів” FSM.

---

## 4) Федеративна модель (нагадування коротко)

* **Тактика (Домени)**: 3–5 автономних кланів з вла� ним **Domain FSM** (hot path).
* **Стратегія (Meta-FSM)**: міждоменні агрегати/директиви (slow/normal path).

---

## 5) Протокол повідомлень (розширено)

### 5.1 OP/verbs/intent (як у v2.1)

* **OP:** `ASK | DEC | EVT | UPD | ERR`
* **StdLib verbs:** `EVAL, OPEN, CLOSE, SCALE, ADJUST, AUTH, READ, WRITE, PING, HEALTH, WHY, ALERT, RECONCILE, CMD`
* **intent:** `INQUIRY | COMMAND | PROPOSAL | OBSERVATION | DECLARATION`

### 5.2 Карка�  повідомлення (доповнено для тра� ування/даних/відлад)

```json
{
  "v": 2,
  "op": "ASK|DEC|EVT|UPD|ERR",
  "verb": "EVAL|OPEN|CLOSE|CMD|...",
  "intent": "INQUIRY|COMMAND|PROPOSAL|OBSERVATION|DECLARATION",
  "src": "module_or_domain",
  "dst": "module_or_domain|any",
  "rid": "uuid",                 // також викори� товуєть� я як trace_id
  "span_id": "uuid",             // для міждоменних � панів
  "parent_span_id": "uuid|null",
  "ts": 1731234567890,
  "key": "resource/position/user",
  "ttl_ms": 2000,
  "pld": {},
  "why": "≤80 chars",            // hot-path поя� нення
  "why_explain_ref": "uri|null", // cold-path детальна довідка (XAI store)
  "data_ref": [                  // по� илання на великі дані (data-by-reference)
    {"uri":"s3://.../obj", "sha256":"...", "bytes":1234567, "ctype":"application/parquet", "ttl_ms": 600000}
  ],
  "sig": "optional"              // ed25519 підпи�  для критичних CMD/DEC
}
```

---

## 6) Продуктивні� ть і маршрутизація (як у v2.1)

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

# 8) Надійні� ть та Відновлення (Disaster Recovery & Resilience)

### 8.1 Цілі DR

* **RTO** (відновлення ча� у): критичні домени ≤ **5–15 хв**, не-критичні ≤ **1–4 год**
* **RPO** (втрата даних): критичні ≤ **1 хв**, не-критичні ≤ **15 хв**

### 8.2 Джерела і� тини та журнали

* **Immutable WAL (append-only) для повідомлень** (per-domain): з **hash-ланцюгом** (Merkle-root/щоденний якор у публічний журнал або об’єкт-блокування S3 WORM).
* **Снапшоти � танів** доменів (checkpoint кожні `N` хв) + **redo** із WAL для рекон� трукції.
* **Global/Domain Dictionary** + � хеми зберігають� я в **geo-реплікованому** репо (вер� ії/міграції підпи� ані).

### 8.3 Рекон� трукція � тану (state reconstruction)

1. Відновити **о� танній � напшот** домену.
2. Програти WAL **з моменту � напшоту** до `ts_failover`.
3. **Ідемпотентні� ть per rid** гарантує коректні� ть дій при повторному за� то� уванні.
4. **Перевірити інваріанти домену** (балан� и, ліміти, позиції).
5. Позначити `RECONCILE` подіями розбіжно� ті; Meta-FSM може видавати `CMD:REPAIR`.

### 8.4 Degradation (граційне зниження)

* **При дефіциті ре� ур� ів / ви� окій ентропії:**

  * відкидати `ASK:INQUIRY` (низький пріоритет),
  * зменшити ча� тоту `EVT:DATA_READY` (coalesce),
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

* **Active-Active** для критичних доменів (Risk/Exec): geo-розне� ені кла� тери, кон� ен� у�  на рівні команд (idempotent).
* **Active-Standby** для аналітики/Audit: прогрів stand-by репліки, RTO ≤ 15 хв.

---

# 9) Спо� тережні� ть і Відладка (Observability & Debug)

### 9.1 Двошарова модель WHY (швидкі� ть vs деталізація)

* **hot_path:** коротке `why` (≤80 � имволів) у повідомленні.
* **cold_path:** `why_explain_ref` → детальна довідка (дерево причин, промпти LLM, фічі, конфіги) у XAI-� ховищі.

### 9.2 Міждоменне тра� ування

* **trace_id = rid**, з **span_id/parent_span_id** для кожного hop.
* Інтеграція з **OpenTelemetry** (опц.): ек� портуємо � пани/атрибути (verb, intent, ttl_profile, latency_ms, error).
* **Sampling:** hot-path 1–10% (у� і ERR=100%), cold-path 100%.

### 9.3 Стандартизований лог-рядок (розширений)

```
ts | rid(trace) | span | parent | op | verb | intent | src→dst | key | ttl | why | why_ref | latency_ms | err? | cb_state
```

### 9.4 Debug endpoint (безпечно)

* `GET /debug/{rid}` (RBAC + redaction): повертає **повний шлях** (� пани, why_chain, why_explain, payload-диф, підпи� и).
* `GET /replay/{rid}`: dry-run реплей із журналу (тільки для sandbox).
* **Alert hooks:** на EVT:ENTROPY_SPIKE/TOPOLOGY_DRIFT/ERR% threshold.

---

# 10) Ефективні� ть розробки і � упроводу (LLM-pipeline, CLI, IDE)

### 10.1 LLM-оптимізації (зменшуємо ітерації)

* **contract_validator (pre-gen):** перед генерацією коду LLM отримує � хеми/� ловники та проходить те� т відповідно� ті (забороняє фантазувати поля/verbs).
* **auto_test_generator (post-gen):** LLM � першу генерує контракт-те� ти (valid/invalid/TTL/idempotency), потім код, що має їх пройти.

### 10.2 CLI-ін� трументи (приклад)

```
vfound init                         # scaffolding проекту
vfound rfc new <name>               # шаблон RFC
vfound dict lint --global --domain  # � ловник-лінтер
vfound schema gen --from pydantic   # генерація JSON Schema
vfound test gen --module X          # auto_test_generator
vfound simulate flow <file.yaml>    # прогін інтеграційного � ценарію
vfound trace get <rid>              # витяг тра� ування
vfound replay <rid> --dry-run       # реплей із WAL
```

### 10.3 IDE-плагіни (напрямок)

* CodeLens над `handle_message`: показує допу� тимі `OP/verb` з Dictionary.
* Quick-fix: “додай why”, “перевір TTL-профіль”, “перевір ідемпотентні� ть per rid”.

### 10.4 Governance для � хем (боремо� ь із schema bloat)

* **Композиція через `$ref`** (base/* + domain/*).
* **Вер� іонування � емантичне** (`_v1`, `_v2`), **deprecation windows** ≥ 2 релізи.
* **Schema-budget** per домен (напр., ≤ N нових � хем/квартал) — перевищення → RFC-обґрунтування.
* **semantic diff** у CI; **auto-RFC draft** із дифа � хеми.

---

# 11) Дані та Безпека

### 11.1 Великі дані — “by reference” (data_lake_integration)

* Повідомлення мі� тить **`data_ref`**: `{uri, sha256, bytes, ctype, ttl_ms}`
* До� туп — по **тимча� ових підпи� аних URL** (KMS), читання **streaming**.
* Заборонено вкладати великі ма� иви/файли у `pld` (шина — для подій, не для даних).

### 11.2 Підпи� ання критичних операцій

* **Обов’язково підпи� увати `CMD/*` і `DEC/*`** (ed25519/KMS), політика ротації ключів, перевірка підпи� ів у FSM перед виконанням.
* Підпи�  включає **хеш payload + метадані** (`rid, ts, src, dst, verb`).

### 11.3 Не-змінні� ть журналів (immutable logging)

* **WORM-� ховище** (Object Lock) для WAL та XAI-артефактів.
* **Хеш-ланцюг** і щоденний **Merkle-root** якорить� я (напр., у зовнішній реє� тр/нотариат).

### 11.4 Контроль до� тупу та приватні� ть

* **RBAC/ABAC** для /debug, /replay, /metrics, data_ref.
* **Redaction** чутливих полів у логах/ендпоінтах.
* **Rate-limits** на критичні verbs (CMD/OPEN/CLOSE).
* **Secret-management** централізовано (KMS), ключі — **не** у коді.

---

# 12) Те� тування та які� ні гейти (оновлено)

**Стратегія** (як у v2.1) + додатково:

* **DR-те� ти:** рекон� трукція � тану зі � напшоту+WAL; RTO/RPO у межах цілей.
* **Chaos-те� ти:** ін’єкція TIMEOUT/CB-OPEN/мережевих розривів.
* **Observability-те� ти:** тра� ування end-to-end, цілі� ні� ть why_chain/why_ref.

**Пороги:**

* why_chain coverage ≥ **95%** (ERR-випадки — 100%).
* p95 FSM (hot) ≤ **50м� **, загальний ≤ **100м� **; ERR:TIMEOUT ≤ **1%**.
* **CB health:** ча� тка OPEN < **2%** запитів, � ередній ча�  у OPEN ≤ **60� **.
* **DR:** відтворення � тану ≤ **RTO**, втрата ≤ **RPO**.
* **LLM-які� ть:** (simple ≤10% галюцинацій; complex ≤30%; pass-rate ≥ пороги).

---

# 13) Артефакти (оновлені фрагменти)

### 13.1 Global Dictionary (міждоменно, доповнено тра� уванням/політиками)

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
* **Метрики у� піху:** p95 ≤ 100м� ; why_chain 100% на ключових рішеннях; CB-OPEN <2%; DR у межах RTO/RPO; 0 contract-break; 0–1 hotfix з процедурою.

---

## 15) Анти-патерни (нагадування + нові)

* Вкладати великі дані у `pld` → ❌ (викори� товуй `data_ref`)
* Від� утні� ть підпи� ів на `CMD/DEC` у проді → ❌
* Від� утні� ть � напшотів/WAL → ❌
* Debug без RBAC/redaction → ❌

---

## 16) Реалізаційна примітка (фреймворк vFoundation)

* Як і у v2.1: Python 3.10+, Pydantic → JSON-Schema, Redis (warm/cold), in-proc (hot), FastAPI (/health, /metrics, /debug), OpenTelemetry (опц.).
* Додаємо: **WORM-бекенд** для журналів, **KMS** для підпи� ів/URL, **CLI** з розділу 10.2.

---


