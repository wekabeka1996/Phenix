# Constitution FSM-LLM v2.2 (vFoundation)

*(Фінансова система / трейдинг, алгоритмічна / ML торгівля / ризик-менеджмент, виконання, моніторинг, аудит)*

> Цей документ є офіційною конституцією системи FSM-LLM. Базується на v2.1, **суттєво розширений**, містить усі вимоги для production-ready розгортання.

---

## 0) Статус та авторитет

1. Цей документ є **джерелом істини** для HQ та всіх підсистем: *будь-які суперечності між кодом і цим документом вирішуються на користь документа*.
2. Зміни вносяться через: архітектурний огляд, roadmap, Global/Domain Dictionaries, RFC, та голосування.
3. Реалізацію контролює **архітектурна рада**; HQ має право вето на порушення / відхилення / виключення.

---

## 1) Ціль та охоплення (виконавче резюме)

Цей документ визначає повну архітектуру LLM-агентів та їх взаємодію в межах системи. Охоплює **доменні автомати станів** (Domain FSM — hot path), **Meta-FSM** (міждоменний), **протокол повідомлень**, **safety-вето**, **fail-closed**, **XAI**, а також **DR/Observability/Tooling/Data-Security**.

---

## 2) Що успадковано (базис від v2.1)

* **Протокол повідомлень**, **verb-простір**, **Domain FSM**, **Meta-FSM**, **Global/Domain Dictionary**, **Freeze**, **RFC**, **why/why_chain** — успадковані з v2.1.
* Нові компоненти v2.2 (відсутні в v2.1): **EntropyMonitor**, **TopologyAuditor**, **Intent Layer**, **Latent State Embeddings** — описані нижче.

---

## 3) Незмінні принципи (інваріанти системи)

1. Контракт > реалізація. 2) Безпека + Freeze. 3) Safety-вето завжди активне. 4) Fail-closed за замовчуванням.
2. why обов'язковий для кожного повідомлення. 6) Ідемпотентність вхідних / вихідних операцій. 7) Additive-only зміни.
3. Обмеження складності (макс. 12 verbs/домен; макс. 20 станів/FSM). 9) Аудит кожної дії.
4. Заборонено циклічні залежності між FSM.

---

## 4) Рівні розгляду (гарячий та холодний шляхи)

* **Гарячий шлях (in-process)**: 3–5 мс затримка для критичних переходів у **Domain FSM** (hot path).
* **Холодний шлях (Meta-FSM)**: міждоменна координація / аудит (slow/normal path).

---

## 5) Протокол повідомлень (специфікація)

### 5.1 OP / verbs / intent (успадковано з v2.1)

* **OP:** `ASK | DEC | EVT | UPD | ERR`
* **StdLib verbs:** `EVAL, OPEN, CLOSE, SCALE, ADJUST, AUTH, READ, WRITE, PING, HEALTH, WHY, ALERT, RECONCILE, CMD`
* **intent:** `INQUIRY | COMMAND | PROPOSAL | OBSERVATION | DECLARATION`

### 5.2 Канонічна структура повідомлення (мінімальний / розширений / з даними)

```json
{
  "v": 2,
  "op": "ASK|DEC|EVT|UPD|ERR",
  "verb": "EVAL|OPEN|CLOSE|CMD|...",
  "intent": "INQUIRY|COMMAND|PROPOSAL|OBSERVATION|DECLARATION",
  "src": "module_or_domain",
  "dst": "module_or_domain|any",
  "rid": "uuid",                 // глобальний ідентифікатор запиту = trace_id
  "span_id": "uuid",             // ідентифікатор поточного span
  "parent_span_id": "uuid|null",
  "ts": 1731234567890,
  "key": "resource/position/user",
  "ttl_ms": 2000,
  "pld": {},
  "why": "макс. 80 chars",            // hot-path: коротке обґрунтування
  "why_explain_ref": "uri|null", // cold-path: посилання на детальне пояснення (XAI store)
  "data_ref": [                  // передача великих даних за посиланням (data-by-reference)
    {"uri":"s3://.../obj", "sha256":"...", "bytes":1234567, "ctype":"application/parquet", "ttl_ms": 600000}
  ],
  "sig": "optional"              // ed25519 підпис — обов'язковий для CMD/DEC
}
```

---

## 6) Маршрутизація та TTL-профілі (успадковано з v2.1)

* **Режими маршрутизації:** `hot_path (in-proc)`, `warm_path (shared memory)`, `cold_path (MQ)`
* **TTL-профілі:** `critical | fast | normal | ml_slow | background`
* **Поведінка при таймауті:** `safety_timeout_behavior: DENY`

---

## 7) Нові компоненти v2.2 (відсутні в попередній версії, додані в v2.2)

* **EntropyMonitor** — генерує EVT:ENTROPY_SPIKE
* **Intent Layer** — управляє QoS / пріоритизацією
* **TopologyAuditor** — генерує EVT:TOPOLOGY_DRIFT_DETECTED
* **Latent Embeddings** — розширений контекст для CMD

---

# 8) Відмовостійкість та відновлення (Disaster Recovery & Resilience)

### 8.1 Цільові показники DR

* **RTO** (час відновлення): стандартні домени — **5–15 хвилин**, критичні домени — **1–4 хвилини**
* **RPO** (допустима втрата даних): стандартні домени — **1 хвилина**, критичні домени — **15 секунд**

### 8.2 Стратегія резервного копіювання

* **Immutable WAL (append-only) для кожного домену** (per-domain): з **hash-ланцюжком** (Merkle-root / криптографічна верифікація — зберігається в S3 WORM).
* **Снепшоти стану** зберігаються кожні `N` подій (checkpoint) + **redo** з WAL до точки відмови.
* **Global/Domain Dictionary** + конфігурація маршрутизації — **geo-реплікація** (мінімум 3 регіони / незалежні зони доступності).

### 8.3 Процедура відновлення (state reconstruction)

1. Завантажити **останній валідний снепшот** відповідного домену.
2. Відтворити WAL **від снепшота до точки відмови** `ts_failover`.
3. **Дедублікувати повідомлення per rid** для забезпечення ідемпотентності відновлення.
4. **Верифікувати цілісність стану** (контракти, ліміти, інваріанти).
5. Надіслати `RECONCILE` для узгодження між доменами; Meta-FSM ініціює `CMD:REPAIR`.

### 8.4 Деградація (graceful degradation)

* **При частковій недоступності / перевантаженні:**

  * Скидати низькопріоритетні `ASK:INQUIRY` (не критичні запити),
  * Укрупнювати батч-повідомлення `EVT:DATA_READY` (coalesce),
  * Активувати **safe policy** (`CMD:SWITCH_TO_LOW_RISK_MODE`),
  * Freeze для некритичних операцій (залишати тільки `READ/HEALTH`).
* **Backpressure:** черги per-key з обмеженням розміру; при p95 latency > порогу — автоматичний throttle.

### 8.5 Конфігурація retry / circuit breaker (рекомендований стандарт)

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
  open_threshold: 0.2        # 20% помилок → стан OPEN
  half_open_probes: 5        # кількість пробних запитів для відновлення
  cooldown: 30s
fallbacks:
  safety_default: DENY       # fail-closed
  exec_degraded: reduce_only # тільки знижувати позицію, не нарощувати
dead_letter_queue:
  on_exhausted_retries: true
```

### 8.6 Топологія розгортання DR

* **Active-Active** для критичних доменів (Risk/Exec): geo-розподілене розгортання, всі вузли обробляють трафік (idempotent).
* **Active-Standby** для аудиту / зберігання: резервний вузол на stand-by, RTO до 15 хвилин.

---

# 9) Спостережуваність та налагодження (Observability & Debug)

### 9.1 Пояснення рішень WHY (коротке пояснення vs детальний аудит)

* **hot_path:** обов'язкове поле `why` (макс. 80 символів) у кожному повідомленні.
* **cold_path:** `why_explain_ref` вказує на сховище детальних пояснень (причинно-наслідкові ланцюжки, виводи LLM, графи, метрики) в XAI-сховищі.

### 9.2 Розподілене трасування

* **trace_id = rid**, плюс **span_id/parent_span_id** на кожному hop.
* Метрики експортуються через **OpenTelemetry** (OTLP): гістограми затримок / лічильники помилок (verb, intent, ttl_profile, latency_ms, error).
* **Sampling:** hot-path 1–10% (виключення ERR=100%), cold-path 100%.

### 9.3 Канонічний формат рядка журналу (структурований лог)

```
ts | rid(trace) | span | parent | op | verb | intent | src → dst | key | ttl | why | why_ref | latency_ms | err? | cb_state
```

### 9.4 Debug endpoint (захищений доступ)

* `GET /debug/{rid}` (RBAC + redaction): повний **граф обробки запиту** (стани, why_chain, why_explain, payload-хеш, метрики).
* `GET /replay/{rid}`: dry-run відтворення повідомлення (ізольований sandbox).
* **Alert hooks:** при EVT:ENTROPY_SPIKE / TOPOLOGY_DRIFT / ERR% > порогу.

---

# 10) Інструментарій та автоматизація (LLM-pipeline, CLI, IDE)

### 10.1 LLM-асистент (автоматична валідація генерації)

* **contract_validator (pre-gen):** перевіряє до генерації LLM відповідність схемам / інваріантам системи (заборонені / невідомі verbs).
* **auto_test_generator (post-gen):** LLM автоматично генерує контрактні тести (valid/invalid/TTL/idempotency), снепшоти, тести регресії.

### 10.2 CLI-команди (довідник)

```
vfound init                         # scaffolding нового домену
vfound rfc new <name>               # створити новий RFC
vfound dict lint --global --domain  # перевірити словники на відповідність
vfound schema gen --from pydantic   # генерувати JSON Schema з Pydantic
vfound test gen --module X          # auto_test_generator
vfound simulate flow <file.yaml>    # симуляція потоку повідомлень між модулями
vfound trace get <rid>              # отримати трас за rid
vfound replay <rid> --dry-run       # відтворити повідомлення з WAL
```

### 10.3 IDE-інтеграція (довідник)

* CodeLens поряд з `handle_message`: підказки контексту `OP/verb` з Dictionary.
* Quick-fix: заповнити поле why, виправити TTL-профіль, згенерувати тест ідемпотентності per rid.

### 10.4 Governance схем (запобігання schema bloat)

* **Використовувати спільні `$ref`** (base/* + domain/*).
* **Версіонувати всі схеми** (`_v1`, `_v2`), **deprecation windows** мінімум 2 релізи.
* **Schema-budget** per домен (наприклад, макс. N полів/рівень вкладеності) — зміни понад ліміт потребують RFC-затвердження.
* **Semantic diff** в CI; **auto-RFC draft** при значних змінах.

---

# 11) Безпека та конфіденційність даних

### 11.1 Передача великих даних за посиланням (data_lake_integration)

* Великі корисні навантаження передаються через **`data_ref`**: `{uri, sha256, bytes, ctype, ttl_ms}`
* Посилання захищені **presigned URL з обмеженим TTL** (KMS), без підтримки **streaming** в поточній версії.
* Заборонено вбудовувати великі бінарні / файлові дані прямо в `pld` (порушення протоколу, ігнорується).

### 11.2 Підписи повідомлень та верифікація

* **Обов'язкові підписи для `CMD/*` та `DEC/*`** (ed25519/KMS), верифікація при отриманні, відхилення без підпису FSM при порушенні.
* Підписується **канонічний payload + метадані** (`rid, ts, src, dst, verb`).

### 11.3 Незмінне журналювання (immutable logging)

* **WORM-сховище** (Object Lock) для WAL та XAI-пояснень.
* **Hash-ланцюжок** з верифікацією через **Merkle-root** на кожному checkpoint (наприклад, щогодинна верифікація / сповіщення при порушенні).

### 11.4 Контроль доступу та таємниці

* **RBAC/ABAC** для /debug, /replay, /metrics, data_ref.
* **Redaction** чутливих полів у журналах / трасах.
* **Rate-limits** для небезпечних verbs (CMD/OPEN/CLOSE).
* **Secret-management** — виключно через KMS, **ніколи** не в середовищі / конфігурації.

---

# 12) Тестування та якість (контрактні тести)

**Базовий набір** (успадкований з v2.1) + розширення:

* **DR-тести:** симуляція відмови + відновлення з WAL; перевірка RTO/RPO на відповідність специфікації.
* **Chaos-тести:** ін'єкція TIMEOUT/CB-OPEN/мережевих розділів.
* **Observability-тести:** перевірка end-to-end трасування, наявність why_chain/why_ref.

**Порогові значення:**

* why_chain coverage ≥ **95%** (ERR-повідомлення — 100%).
* p95 FSM (hot) ≤ **50 мс**, cold-path ≤ **100 мс**; ERR:TIMEOUT ≤ **1%**.
* **CB health:** час у стані OPEN < **2%** від загального часу, тривалість одного OPEN-епізоду ≤ **60 с**.
* **DR:** підтвердження відповідності **RTO**, відсутність втрат понад **RPO**.
* **LLM-генерація:** (simple ≤ 10% регресій контрактів; complex ≤ 30%; pass-rate відстежується).

---

# 13) Довідник конфігурацій (канонічні приклади)

### 13.1 Global Dictionary (між доменами, маршрутизація / протокол / політики)

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

### 13.2 Політика модуля (retry / circuit breaker)

```yaml
module: exec_gateway
retry_policy: { strategy: exponential_jitter, base_ms: 50, max_ms: 2000, max_attempts: 5 }
circuit_breaker: { open_threshold: 0.2, error_rate_window: 60s, half_open_probes: 5, cooldown: 30s }
degradation: { mode: reduce_only, drop_low_priority_intents: [INQUIRY] }
```

### 13.3 DR Snapshot & WAL сегмент

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

# 14) Дорожня карта (2 наступні квартали)

* **Цільові домени:** `risk_strategy`, `execution_position`, `audit_xai`.
* **Мета:** повна міграція з v2.1 + **контрактна верифікація**, впровадження **DR-автоматики**.
* **Критерії успіху:** p95 ≤ 100 мс; why_chain 100% для всіх критичних повідомлень; CB-OPEN <2%; підтверджено RTO/RPO; 0 contract-break; 0–1 hotfix за квартал.

---

## 15) Антипатерни (заборонені дії + наслідки)

* Вбудовувати великі об'єкти в `pld` замість використання `data_ref`
* Надсилати `CMD/DEC` без підпису
* Ігнорувати WAL/снепшоти при розгортанні
* Відкривати Debug endpoint без RBAC/redaction

---

## 16) Стек технологій (технічні вимоги vFoundation)

* **Базовий стек v2.1:** Python 3.10+, Pydantic для JSON-Schema, Redis (warm/cold), in-proc (hot), FastAPI (/health, /metrics, /debug), OpenTelemetry (OTLP).
* **Нові вимоги v2.2:** **WORM-сховище** для незмінних логів, **KMS** для підписів/presigned URL, **CLI** згідно з розділом 10.2.

---
