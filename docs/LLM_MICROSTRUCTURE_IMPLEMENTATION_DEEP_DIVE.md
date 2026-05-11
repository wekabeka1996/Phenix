# LLM MICROSTRUCTURE — Повна технічна документація реалізації

> **Дата:** 2026-05-10
> **Статус:** Актуально (code-driven, перевірено по живому коду)
> **Призначення:** Базовий документ для рефакторингу та розширення стратегії під нове агентне середовище
> **Авторитетні джерела:** `config/aurora/strategies/llm_microstructure.yaml`, `config/aurora/trading.yaml`, `config/aurora/domains.yaml`, `apps/reference/domains/shadow_telemetry/`, `apps/reference/domains/execution_position/flows/open/intent_router.py`, `apps/reference/domains/strategies/plugins/llm_microstructure.py`

---

## Зміст

1. [Архітектурна суть стратегії](#1-архітектурна-суть-стратегії)
2. [Карта всіх ключових файлів](#2-карта-всіх-ключових-файлів)
3. [Конфігурація стратегії](#3-конфігурація-стратегії)
4. [Реєстрація і plugin startup](#4-реєстрація-і-plugin-startup)
5. [HTTP-шар: як LLM підключається до системи](#5-http-шар-як-llm-підключається-до-системи)
6. [Policy gates: шари перевірки запиту](#6-policy-gates-шари-перевірки-запиту)
7. [IPC-шар: Shadow API → Main process](#7-ipc-шар-shadow-api--main-process)
8. [Command mapper: перетворення команди](#8-command-mapper-перетворення-команди)
9. [Execution intake: фінальний прийом в execution_position](#9-execution-intake-фінальний-прийом-в-execution_position)
10. [Хто і де визначає параметри ордеру](#10-хто-і-де-визначає-параметри-ордеру)
11. [Моніторинг відкритих позицій](#11-моніторинг-відкритих-позицій)
12. [WAL та аудит-трейл](#12-wal-та-аудит-трейл)
13. [Синтетичний генератор інтентів](#13-синтетичний-генератор-інтентів)
14. [Що НЕ є активним live-шляхом (legacy surfaces)](#14-що-не-є-активним-live-шляхом-legacy-surfaces)
15. [Повна карта потоку event'ів](#15-повна-карта-потоку-eventів)
16. [Точки розширення для нового агентного середовища](#16-точки-розширення-для-нового-агентного-середовища)

---

## 1. Архітектурна суть стратегії

`llm_microstructure` — це **зовнішньо-керована стратегія** (external-intent strategy). Вона **не є** самостійним in-process обробником ринкових даних, не підписується на бари, не обчислює сигнали, не проходить через `StrategyGateway → DecisionMaking → IntentBuilder`.

Замість цього вона є **bridge-стратегією**: зовнішній агент (LLM) самостійно ухвалює рішення і подає намір (intent) через HTTP. Система виконує багаторівневу валідацію та передає intent в `execution_position` для відкриття LIMIT-ордеру.

### Ключові архітектурні особливості

| Характеристика | Значення |
|---|---|
| Тип | External-intent bridge strategy |
| Plugin | Sentinel-only (тільки реєстрація, ніякої логіки) |
| Транспорт | HTTP → IPC TCP → FSM event bus |
| Ордер-тип | Завжди `LIMIT` (v1 policy, примусово) |
| Поточний символ | `1000PEPEUSDT` |
| Safety gates | Вимкнені (`enabled: false`), не є активним власником live шляху |
| DecisionMaking | Повністю байпасується |
| TP/SL | Обов'язкові, передаються агентом, виставляються як bracket orders |

### Принципова схема

```
┌──────────────────────────────────────────────────────────────┐
│                    LLM Agent / UI Panel                      │
│         POST /intents/llm/v1   Bearer Token                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS  port 8443
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Shadow Telemetry API (FastAPI)                   │
│   apps/reference/domains/shadow_telemetry/main.py            │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  AUTH          Bearer token (hmac.compare_digest)   │    │
│  │  SYMBOL        symbols_llm / allowlist check        │    │
│  │  POLICY        TIF, LIMIT-only, TP/SL required      │    │
│  │  PRICE BAND    max_price_deviation_bps vs snapshot  │    │
│  │  QTY CAP       max_qty / max_notional_usd (clamp)  │    │
│  │  RATE LIMIT    rate_limit_per_min per auth_subject  │    │
│  │  COOLDOWN      cooldown_sec per symbol              │    │
│  │  MAX OPEN      max_open_intents per symbol          │    │
│  │  IPC PROBE     endpoint availability check          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  EVT:LLM_INTENT_RECEIVED_V1  → WAL + snapshot_store         │
│  Accepted → CmdLlmIntentSubmitV1 → IPC enqueue              │
└───────────────────────────┬──────────────────────────────────┘
                            │ IPC TCP  tcp://127.0.0.1:7102
                            ▼
┌──────────────────────────────────────────────────────────────┐
│           LLMIntentIngressBridge (Main process)              │
│   apps/reference/domains/shadow_telemetry/main_bridge.py     │
│                                                              │
│  schema re-validation: CmdLlmIntentSubmitV1                  │
│  mode check: llm_orchestration.mode != baseline              │
│  symbol re-check: symbols_llm + allowlist                    │
│                                                              │
│  EVT:LLM_INTENT_ACCEPTED_V1  → WAL                           │
│  emit CMD:LLM_INTENT_SUBMIT_V1 → FSM bus                     │
└───────────────────────────┬──────────────────────────────────┘
                            │ FSM event bus
                            ▼
┌──────────────────────────────────────────────────────────────┐
│           register_llm_command_mapper()                       │
│   apps/reference/domains/shadow_telemetry/main_bridge.py     │
│                                                              │
│  listen: CMD:LLM_INTENT_SUBMIT_V1                            │
│  → build ext_payload (symbol, side, qty, price, tif,         │
│                        stop_price, target_price, source)     │
│  emit: CMD:EXTERNAL_OPEN_REQUEST_V1                          │
└───────────────────────────┬──────────────────────────────────┘
                            │ FSM event bus
                            ▼
┌──────────────────────────────────────────────────────────────┐
│       execution_position FSM                                  │
│   apps/reference/domains/execution_position/fsm.py           │
│   bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", ...)            │
│                         │                                    │
│                         ▼                                    │
│       IntentRouter.on_external_open_request()                │
│   flows/open/intent_router.py                                │
│                                                              │
│  GATE 1  intent_id present                                   │
│  GATE 2  source == "external_llm"                            │
│  GATE 3  order_type == "LIMIT"                               │
│  GATE 4  tif ∈ {GTC, GTX, IOC, FOK}                         │
│  GATE 5  price present                                       │
│  GATE 6  valid_for_ms (request → config fallback)            │
│                                                              │
│  → CMD:OPEN (strategy="llm_microstructure")                  │
│  → FSM.handle() → Binance LIMIT order                        │
│  → bracket TP/SL orders                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Карта всіх ключових файлів

### Конфігурація

| Файл | Роль |
|---|---|
| `config/aurora/strategies.yaml` | Реєстр assignment: `1000PEPEUSDT → [llm_microstructure]` |
| `config/aurora/strategies/llm_microstructure.yaml` | Профіль стратегії: enabled, type, TTL, execution policy |
| `config/aurora/trading.yaml` (секція `llm_orchestration`) | Глобальна orchestration policy: mode, symbols, intent_policy |
| `config/aurora/domains.yaml` (секція `shadow_telemetry`) | IPC ендпоінти, API host/port, allowlist events |

### Pydantic моделі

| Файл | Роль |
|---|---|
| `apps/reference/config/strategies/llm_microstructure.py` | `LLMMicrostructureStrategyConfig` — typed profile |
| `apps/reference/domains/shadow_telemetry/contracts.py` | `LLMIntentRequestV1`, `LLMOrderV1`, `LLMBracketsV1`, `LLMSnapshotRefV1`, `LLMModelMetaV1`, `LLMPolicyHintsV1`, `CmdLlmIntentSubmitV1`, `IntentAcceptedResponseV1` |

### Runtime (основний)

| Файл | Роль |
|---|---|
| `apps/reference/domains/shadow_telemetry/main.py` | FastAPI додаток: HTTP API, policy gates, IPC egress client |
| `apps/reference/domains/shadow_telemetry/main_bridge.py` | `LLMIntentIngressBridge` (IPC server), `ShadowEventTapPublisher`, `register_llm_command_mapper()` |
| `apps/reference/domains/execution_position/flows/open/intent_router.py` | `IntentRouter.on_external_open_request()` — фінальний intake |
| `apps/reference/domains/execution_position/fsm.py` | FSM wiring: `bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", ...)` |
| `apps/reference/domains/strategies/plugins/llm_microstructure.py` | `LlmMicrostructurePlugin` — sentinel plugin |
| `apps/reference/domains/shadow_telemetry/snapshot_store.py` | SnapshotStore — market data snapshots для агента |

### Допоміжні

| Файл | Роль |
|---|---|
| `tools/simulation/synthetic_llm_intent_generator.py` | CLI синтетичний генератор тестових інтентів |
| `tests/config/test_llm_microstructure_strategy_contracts.py` | Contract tests для профілю |
| `tests/domains/shadow_telemetry/test_main_bridge.py` | Tests для IPC bridge |
| `tests/domains/execution_position/test_external_open_request.py` | Tests для `on_external_open_request()` |
| `tests/unit/llm/test_llm_command_mapper_emits_strategy_signal.py` | Tests для command mapper |

---

## 3. Конфігурація стратегії

### 3.1 Профіль стратегії

`config/aurora/strategies/llm_microstructure.yaml`:

```yaml
llm_microstructure:
  enabled: true
  type: external_intent
  description: External LLM intent strategy (contract-first ingress, fail-closed gates)
  timeframe_sec: 60
  pending_entry_ttl_ms: 120000      # TTL ордеру: 2 хвилини (fallback якщо агент не передає)
  execution:
    entry_order_type: LIMIT         # ДЕКЛАРАТИВНО — не активний власник live шляху
    entry_tif: GTC
    exit_order_type: MARKET
    exit_tif: null
    exit_limit_ttl_ms: null
    gtx_retry_max: 0
    gtx_retry_offset_bps: 2.0
  safety_gates:
    enabled: false                  # БАЙПАСОВАНІ на live external шляху
    system_stress_policy: 'off'
    stress_attenuation_factor: 0.5
```

**Критично важливо:** Секції `execution.*` і `safety_gates.*` є декларативними. На поточному live зовнішньому шляху з них реально споживається **тільки** `pending_entry_ttl_ms` — як fallback для `valid_for_ms` якщо агент не передав його у запиті.

### 3.2 Typed config model

`apps/reference/config/strategies/llm_microstructure.py`:

```python
class LLMMicrostructureStrategyConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')  # strict: заборонені невідомі поля

    enabled: bool
    type: str
    description: str
    timeframe_sec: int = Field(..., ge=1, le=3600)
    pending_entry_ttl_ms: Optional[int] = Field(..., ge=1000)
    execution: StrategyExecutionConfig
    safety_gates: SafetyGatesConfig
```

### 3.3 Глобальна orchestration policy

`config/aurora/trading.yaml` (секція `llm_orchestration`):

```yaml
llm_orchestration:
  mode: hybrid_advisory           # baseline | hybrid_advisory | llm_primary
  llm_role: advisory
  require_telemetry: true         # якщо true — потребує snapshot для symbol
  symbols_llm:
    - 1000PEPEUSDT                # символи під управлінням LLM
  allowlist_symbols:
    - 1000PEPEUSDT
  intent_policy:
    max_open_intents: 3           # макс. активних інтентів на символ одночасно
    cooldown_sec: 30              # пауза між прийнятими інтентами для символу
    allow_limit_only: true        # тільки LIMIT ордери
    require_tp_sl: true           # TP і SL обов'язкові
    max_notional_usd: 100.0       # ліміт позиції в USD
    max_qty: 5000.0               # ліміт кількості
    max_price_deviation_bps: 20.0 # максимальне відхилення ціни від snapshot (bps)
    allowed_tif:
      - GTC
```

### 3.4 Shadow Telemetry IPC та API конфіг

`config/aurora/domains.yaml` (секція `shadow_telemetry`):

```yaml
shadow_telemetry:
  enabled: true
  required_for_mode: false
  ingest:
    source: ipc_tap
    ipc_endpoint: tcp://127.0.0.1:7101       # main → shadow (market events tap)
    allowlist_events:
      - EVT:BAR_CLOSED
      - EVT:FEATURES_CALCULATED
      - EVT:REGIME_DETECTED
      - EVT:ORDER_PLACED
      - EVT:ORDER_STATE_CHANGED
      - EVT:TRADE_EXECUTED
      - EVT:POSITION_CLOSED
      - EVT:LLM_INTENT_RECEIVED_V1
      - EVT:LLM_INTENT_REJECTED_V1
      - EVT:LLM_INTENT_ACCEPTED_V1
      # ... інші
    queue_maxsize: 50000
    overflow_policy: fail_closed
  api:
    enabled: true
    host: 127.0.0.1
    port: 8443
    tls: false
    auth_mode: bearer
    write:
      enabled: true
      intents_endpoint: /intents/llm/v1
      rate_limit_per_min: 30
      max_body_kb: 64
      symbol_allowlist:
        - 1000PEPEUSDT
      require_snapshot_ref: true
      idempotency_ttl_sec: 300         # 5 хвилин TTL для idempotency records
      consequential: true              # x-openai-isConsequential: true (OpenAPI)
  egress_to_main:
    mode: ipc
    ipc_commands_endpoint: tcp://127.0.0.1:7102  # shadow → main (commands)
    queue_maxsize: 50000
    overflow_policy: fail_closed
  snapshot:
    trigger_event: EVT:FEATURES_CALCULATED
    tf_policy:
      bar_snapshots_enabled: true
      tick_snapshots_mode: sampled
      tick_sample_every_n: 20
      min_tf_sec_for_full: 60
    output_dir: data/shadow_telemetry/snapshots
```

**IPC порти:**
- `7101` — main process → shadow telemetry (ринкові дані, tap)
- `7102` — shadow telemetry → main process (LLM команди, зворотній напрям)

---

## 4. Реєстрація і plugin startup

### 4.1 Registry assignment

`config/aurora/strategies.yaml`:

```yaml
assignments:
  1000PEPEUSDT:
    - llm_microstructure
```

Тільки наявність цього рядка запускає всю наступну ланцюжок:
1. `ConfigLoader` завантажує `strategies/llm_microstructure.yaml` → `config.strategies.llm_microstructure`
2. `StrategyRuntime` ініціює plugin для `llm_microstructure`
3. `AuroraConfig` model validator перевіряє перехресний контракт з `trading.llm_orchestration`

### 4.2 Cross-config fail-closed validator

Якщо `llm_orchestration.mode != baseline` і `llm_microstructure` є в assignments:
- `trading.llm_orchestration.symbols_llm` — не може бути порожнім
- `strategies.llm_microstructure` профіль — повинен існувати
- Кожен символ із `symbols_llm` — повинен мати `llm_microstructure` в assignments

### 4.3 Sentinel plugin

`apps/reference/domains/strategies/plugins/llm_microstructure.py`:

```python
@dataclass(frozen=True)
class _LlmMicrostructureSentinelHandler:
    """Sentinel handler: тільки logує. Ніяких FSM listeners."""
    def register(self) -> None:
        LOG.info("LlmMicrostructurePlugin: bridge-driven strategy; "
                 "FSM listeners managed by shadow_telemetry.main_bridge")

@dataclass(frozen=True)
class LlmMicrostructurePlugin:
    """Allowlist sentinel plugin."""
    strategy_id: str = "llm_microstructure"

    def create_handler(self, *, fsm, config) -> _LlmMicrostructureSentinelHandler:
        return _LlmMicrostructureSentinelHandler()
```

Plugin існує **виключно** для задоволення `StrategyRuntime.register()` contract. Вся реальна логіка живе в `shadow_telemetry.main_bridge`.

---

## 5. HTTP-шар: як LLM підключається до системи

### 5.1 Ендпоінт

```
POST http://127.0.0.1:8443/intents/llm/v1
Authorization: Bearer <SHADOW_TELEMETRY_BEARER_TOKEN>
Content-Type: application/json
X-Request-Id: <optional-trace-id>
Idempotency-Key: <optional-idempotency-key>
```

**Автентифікація:**
Токени читаються з env-змінних при старті:
- `SHADOW_TELEMETRY_BEARER_TOKEN` — одиночний токен
- `AURORA_SHADOW_TELEMETRY_BEARER_TOKEN` — альтернативна назва
- `SHADOW_TELEMETRY_BEARER_TOKENS` — comma-separated список

Порівняння виконується через `hmac.compare_digest(token, known)` — захист від timing attacks.

### 5.2 Повна схема тіла запиту (`LLMIntentRequestV1`)

```jsonc
{
  // --- Ідентифікація ---
  "intent_id": "550e8400-e29b-41d4-a716-446655440000",  // uuid4, auto якщо відсутній
  "ts_ms": 1715000000000,                               // unix ms, auto якщо відсутній
  "idempotency_key": "llm:v1:1000PEPEUSDT:sha256...",  // auto-computed якщо відсутній

  // --- Торговий намір ---
  "symbol": "1000PEPEUSDT",   // нормалізується до UPPER
  "side": "BUY",              // BUY | SELL

  // --- Блок ордеру ---
  "order": {
    "type": "LIMIT",           // тільки LIMIT (policy)
    "limit_price": "0.01234",  // string decimal, строго > 0
    "qty": "10000",            // string decimal, строго > 0
    "time_in_force": "GTC"     // GTC | IOC | FOK (тільки GTC по поточній policy)
  },

  // --- TP/SL (обов'язково якщо require_tp_sl=true) ---
  "brackets": {
    "tp_price": "0.01280",     // string decimal
    "sl_price": "0.01200"      // string decimal
  },

  // --- Прив'язка до snapshot (обов'язково якщо require_snapshot_ref=true) ---
  "snapshot_ref": {
    "snapshot_id": "snap-abc123",          // ID snapshot з /snapshots/latest
    "inputs_digest": "sha256hex..."        // sha256 від inputs що бачив LLM
  },

  // --- Метадані моделі (опційно, для аудиту) ---
  "model_meta": {
    "model": "gpt-4o",
    "temperature": 0.2,
    "prompt_hash": "abc123..."   // 8-128 chars
  },

  // --- Обґрунтування (обов'язково) ---
  "why_short": "bullish momentum breakout",  // 1-80 символів

  // --- Опційні hints ---
  "policy_hints": {
    "max_slippage_bps": 5,
    "expiry_ts_ms": 1715001000000,
    "risk_tag": null
  }
}
```

**Інваріанти brackets (перевіряються Pydantic model_validator):**
- `BUY`: `sl_price < limit_price < tp_price`
- `SELL`: `tp_price < limit_price < sl_price`

### 5.3 Відповіді

**Успіх (202 Accepted):**
```jsonc
{
  "intent_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "req-abc123",
  "state": "queued"
}
```

**Помилка (будь-який 4xx/5xx):**
```jsonc
{
  "request_id": "req-abc123",
  "reason_code": "SYMBOL_NOT_ALLOWED",
  "reason": "symbol not in allowlist"
}
```

### 5.4 Допоміжні ендпоінти (для агента)

| Ендпоінт | Метод | Опис |
|---|---|---|
| `/health` | GET | Стан сервісу, глибина черги IPC |
| `/snapshots/latest` | GET | Останній snapshot `?symbol=1000PEPEUSDT` |
| `/snapshots/tail` | GET | Хвіст snapshots `?symbol=...&limit=50` |
| `/intents/status` | GET | Статус intent `?intent_id=...` |

**Приклад `/snapshots/latest` відповіді (скорочено):**
```jsonc
{
  "snapshot_id": "snap-abc123",
  "ts_ms": 1715000000000,
  "symbol": "1000PEPEUSDT",
  "features": {
    "price": 0.01234,
    "volume": 12345678,
    "regime": "TREND_UP"
    // ... інші features
  },
  "bar": {
    "open": 0.01230,
    "high": 0.01240,
    "low": 0.01228,
    "close": 0.01234,
    "volume": 5678900
  }
}
```

### 5.5 Idempotency логіка

- `idempotency_key` — optional у запиті, auto-computed з stable полів якщо відсутній
- При повторному запиті з тим самим ключем і **тим самим** тілом → повертає 202 з кешованою відповіддю (replay-safe)
- При повторному запиті з тим самим ключем і **іншим** тілом → 409 Conflict
- TTL для idempotency records: `idempotency_ttl_sec: 300` (5 хвилин)

Auto-обчислення ключа (`compute_idempotency_key`):
```python
# Стабільні поля для хешування
stable = {
    "v": "v1",
    "symbol": req.symbol,
    "side": req.side,
    "type": req.order.type,
    "limit_price": req.order.limit_price,
    "qty": req.order.qty,
    "tp": req.brackets.tp_price,
    "sl": req.brackets.sl_price,
    "snapshot_id": ...,
    "inputs_digest": ...,
    "expiry_ts_ms": ...,
}
key = f"llm:v1:{req.symbol}:{sha256(stable)}"
```

---

## 6. Policy gates: шари перевірки запиту

Всі перевірки реалізовані у функції `post_llm_intent()` в `apps/reference/domains/shadow_telemetry/main.py`. Параметри читаються з `trading.llm_orchestration.intent_policy` + `shadow_telemetry.api.write`.

### 6.1 Повна таблиця gates (в порядку виконання)

| # | Перевірка | Reject code | HTTP |
|---|---|---|---|
| 1 | `write.enabled == true` | `WRITE_DISABLED` | 503 |
| 2 | Bearer token присутній і коректний | `AUTH_MISSING / AUTH_SCHEME_INVALID / AUTH_TOKEN_EMPTY / AUTH_NOT_CONFIGURED / AUTH_FORBIDDEN` | 401/403/503 |
| 3 | `Content-Length ≤ max_body_kb * 1024` | `PAYLOAD_TOO_LARGE` | 400 |
| 4 | Idempotency: повтор того самого ключа з іншим тілом | `IDEMPOTENCY_CONFLICT` | 409 |
| 5 | Symbol є в `symbols_llm` (якщо список не порожній) | `SYMBOL_NOT_OWNED_BY_LLM` | 400 |
| 6 | Symbol є в effective allowlist (symbols_llm ∩ write.symbol_allowlist ∩ allowlist_symbols) | `SYMBOL_NOT_ALLOWED` | 400 |
| 7 | `time_in_force` є в `allowed_tif` (якщо список не порожній) | `LIMIT_ONLY_POLICY` | 400 |
| 8 | `require_snapshot_ref=true` → `snapshot_ref` не null | `SNAPSHOT_REF_REQUIRED` | 400 |
| 9 | `allow_limit_only=true` → `order.type == LIMIT` | `LIMIT_ONLY_POLICY` | 400 |
| 10 | `require_tp_sl=true` → обидва `tp_price` і `sl_price` є | `TP_SL_REQUIRED` | 400 |
| 11 | Якщо `require_telemetry=true` → snapshot для символу існує | `TELEMETRY_UNAVAILABLE` | 503 |
| 12 | Якщо `max_price_deviation_bps` → reference price зі snapshot існує | `TELEMETRY_UNAVAILABLE` | 503 |
| 13 | `abs(limit_price - ref_price) / ref_price * 10000 ≤ max_price_deviation_bps` | `PRICE_OUT_OF_BAND` | 400 |
| 14 | `qty ≤ max_qty` та `qty * price ≤ max_notional_usd` (clamp якщо ≤3x, reject якщо >3x) | `QTY_CAP_EXCEEDED` | 400 |
| 15 | Rate limit: `requests_in_last_60s < rate_limit_per_min` per auth_subject | `RATE_LIMIT_EXCEEDED` | 429 |
| 16 | Cooldown: `now - last_accept_ts_ms[symbol] ≥ cooldown_sec * 1000` | `SYMBOL_COOLDOWN_ACTIVE` | 429 |
| 17 | `active_intents[symbol].count < max_open_intents` | `MAX_OPEN_INTENTS_EXCEEDED` | 429 |
| 18 | IPC endpoint `tcp://127.0.0.1:7102` доступний (TCP probe) | `IPC_UNAVAILABLE` | 503 |
| 19 | IPC queue enqueue успішний | `IPC_QUEUE_FULL` | 503 |

### 6.2 Qty clamping логіка

```python
# Обчислення cap з двох джерел
cap_qty = min(
    max_qty,                          # абсолютний ліміт кількості
    max_notional_usd / limit_price,   # ліміт через notional
)

overshoot = requested_qty / cap_qty
if overshoot > 3:
    REJECT("QTY_CAP_EXCEEDED")        # відхилення якщо >3x
else:
    effective_qty = cap_qty           # clamp до cap
    # policy_hints.risk_tag = "QTY_CLAMPED"
```

### 6.3 Reference price extraction зі snapshot

```python
# Пріоритет 1: features.price
if snapshot.get("features", {}).get("price"):
    return Decimal(snapshot["features"]["price"])
# Пріоритет 2: bar.close
if snapshot.get("bar", {}).get("close"):
    return Decimal(snapshot["bar"]["close"])
```

---

## 7. IPC-шар: Shadow API → Main process

### 7.1 Транспорт

Прийнятий intent серіалізується як `CmdLlmIntentSubmitV1` (JSON) і ставиться у чергу `JsonlTcpQueueClient` на `tcp://127.0.0.1:7102`.

На боці main-процесу `LLMIntentIngressBridge` слухає цей TCP-порт через `JsonlTcpServer`. Кожне повідомлення обробляється в `_on_command()`.

### 7.2 Payload IPC команди (`CmdLlmIntentSubmitV1`)

```jsonc
{
  "request_id": "req-abc123",
  "intent_id": "550e8400-...",
  "ts_ms": 1715000000000,
  "symbol": "1000PEPEUSDT",
  "side": "BUY",
  "order": {
    "type": "LIMIT",
    "limit_price": "0.01234",
    "qty": "10000",
    "time_in_force": "GTC"
  },
  "brackets": {
    "tp_price": "0.01280",
    "sl_price": "0.01200"
  },
  "snapshot_ref": { "snapshot_id": "...", "inputs_digest": "..." },
  "model_meta": { "model": "gpt-4o", "temperature": 0.2, "prompt_hash": "..." },
  "why_short": "bullish momentum breakout",
  "idempotency_key": "llm:v1:...",
  "policy_hints": null
}
```

### 7.3 `LLMIntentIngressBridge._on_command()` — другий шар захисту

```python
def _on_command(self, payload: Dict[str, Any]) -> None:
    # 1. Schema re-validation (fail-closed)
    try:
        cmd = CmdLlmIntentSubmitV1.model_validate(payload)
    except Exception as e:
        self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1", ..., "llm_intent_schema_invalid")
        return

    # 2. Mode check
    if mode == "baseline":
        self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1", ..., reason_code="LLM_MODE_DISABLED")
        return

    # 3. Symbol re-check
    if symbols_llm and sym_u not in symbols_llm:
        self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1", ..., reason_code="SYMBOL_NOT_OWNED_BY_LLM")
        return

    if allow and sym_u not in allow:
        self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1", ..., reason_code="SYMBOL_NOT_ALLOWED")
        return

    # 4. Accept — emit на FSM bus
    self.fsm.emit("EVT:LLM_INTENT_ACCEPTED_V1", ...)       # аудит
    self.fsm.emit("CMD:LLM_INTENT_SUBMIT_V1", cmd.model_dump())
```

---

## 8. Command mapper: перетворення команди

`register_llm_command_mapper()` в `main_bridge.py` підписується на `CMD:LLM_INTENT_SUBMIT_V1` і будує `ext_payload`:

```python
def _handler(event: Message) -> None:
    cmd = CmdLlmIntentSubmitV1.model_validate(event.pld)

    ext_payload = {
        "rid":          str(cmd.intent_id),
        "intent_id":    str(cmd.intent_id),
        "symbol":       str(cmd.symbol).upper(),
        "side":         str(cmd.side).upper(),          # "BUY" | "SELL"
        "qty":          str(cmd.order.qty),
        "order_type":   str(cmd.order.type),            # "LIMIT"
        "price":        str(cmd.order.limit_price),
        "tif":          str(cmd.order.time_in_force),   # "GTC"
        "stop_price":   str(cmd.brackets.sl_price),     # SL — може бути None
        "target_price": str(cmd.brackets.tp_price),     # TP — може бути None
        "valid_for_ms": None,                           # вирішується далі в IntentRouter
        "idempotent_key": str(cmd.idempotency_key),
        "source":       "external_llm",                 # sentinel value
        "snapshot_ref": cmd.snapshot_ref.model_dump(),  # для аудиту
        "why_short":    truncate_why(cmd.why_short, 80),
    }

    fsm.emit("CMD:EXTERNAL_OPEN_REQUEST_V1", payload=ext_payload)

fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)
```

---

## 9. Execution intake: фінальний прийом в execution_position

### 9.1 FSM wiring

`apps/reference/domains/execution_position/fsm.py`:

```python
# Рядок 562
self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1",
                self._on_external_open_request)
```

`self._on_external_open_request` делегує до `IntentRouter.on_external_open_request()`.

### 9.2 Шість fail-closed gates

`apps/reference/domains/execution_position/flows/open/intent_router.py`:

```python
def on_external_open_request(self, msg: Message) -> None:
    pld = msg.pld or {}

    # GATE 1: intent_id (forensic traceability)
    if not intent_id:
        self._emit_external_rejection(reason_code="NRR-EXT-MISSING-INTENT-ID", ...)
        return

    # GATE 2: source sentinel (захист від підробки джерела)
    if pld.get("source") != "external_llm":
        self._emit_external_rejection(reason_code="NRR-EXT-SOURCE-INVALID", ...)
        return

    # GATE 3: тільки LIMIT (v1 policy)
    if pld.get("order_type") != "LIMIT":
        self._emit_external_rejection(reason_code="NRR-EXT-ORDER-TYPE-NOT-LIMIT", ...)
        return

    # GATE 4: tif обов'язковий, без silent fallback
    tif = pld.get("tif")
    if not tif or tif not in ("GTC", "GTX", "IOC", "FOK"):
        self._emit_external_rejection(reason_code="NRR-EXT-MISSING-TIF", ...)
        return

    # GATE 5: price обов'язкова для LIMIT
    if not pld.get("price"):
        self._emit_external_rejection(reason_code="NRR-EXT-MISSING-PRICE", ...)
        return

    # GATE 6: valid_for_ms — з реквесту або config fallback (fail-closed)
    valid_for_ms = pld.get("valid_for_ms")
    if valid_for_ms is None:
        try:
            config_ttl = self._fsm.config.strategies.llm_microstructure.pending_entry_ttl_ms
        except (AttributeError, KeyError):
            self._emit_external_rejection(reason_code="NRR-EXT-CONFIG-MISSING", ...)
            return
        if config_ttl is None:
            self._emit_external_rejection(reason_code="NRR-EXT-MISSING-VALID-FOR-MS", ...)
            return
        valid_for_ms = config_ttl  # fallback: 120000 ms
```

### 9.3 Побудова CMD:OPEN

```python
cmd_payload = {
    "rid":               rid,
    "symbol":            symbol,
    "side":              pld.get("side"),           # "BUY" | "SELL"
    "qty":               pld.get("qty"),
    "order_type":        "LIMIT",                   # hardcoded
    "price":             price,
    "tif":               tif,
    "valid_for_ms":      valid_for_ms,              # TTL до скасування
    "stop_price":        pld.get("stop_price"),     # SL
    "target_price":      pld.get("target_price"),   # TP
    "idempotent_key":    pld.get("idempotent_key"),
    "price_ref":         price,
    "strategy":          "llm_microstructure",      # hardcoded
    "regime":            None,                      # немає regime для external
    "regime_confidence": None,
    "regime_provenance": None,
    "metadata": {
        "strategy_id":      "llm_microstructure",
        "source":           "external_llm",
        "source_intent_id": intent_id,
        "snapshot_ref":     pld.get("snapshot_ref"),
        "why_short":        pld.get("why_short"),
    },
}

cmd_open = Message(op="CMD", verb="OPEN", ...)
result = self._fsm.handle(cmd_open)
```

Після `handle(cmd_open)` виконується стандартний execution chain: виставлення LIMIT-ордеру на Binance, bracket TP/SL ордери.

---

## 10. Хто і де визначає параметри ордеру

| Параметр | Власник | Джерело |
|---|---|---|
| `side` (BUY/SELL) | **LLM-агент** | `order.side` в HTTP запиті |
| `qty` | **LLM-агент** *(може бути clamp до cap)* | `order.qty`; clamp через `max_qty` / `max_notional_usd` |
| `price` (limit_price) | **LLM-агент** | `order.limit_price`; перевірка відхилення від snapshot |
| `order_type` | **Система (policy)** | Завжди `LIMIT`; примусово на 2 рівнях: Shadow API gate + IntentRouter gate |
| `time_in_force` | **LLM-агент** *(обмежено policy)* | `order.time_in_force`; тільки значення з `allowed_tif: [GTC]` |
| `tp_price` | **LLM-агент** | `brackets.tp_price` |
| `sl_price` | **LLM-агент** | `brackets.sl_price` |
| `valid_for_ms` (TTL ордеру) | **Конфіг** (fallback) | `pending_entry_ttl_ms: 120000` з `llm_microstructure.yaml` якщо агент не передав |
| `strategy` поле в CMD:OPEN | **Система** | Hardcoded `"llm_microstructure"` в `on_external_open_request()` |
| `regime` / `regime_confidence` | **Не визначається** | `None` — стратегія не має regime |

### Формула розрахунку TP/SL (приклад з синтетичного генератора)

```python
bps    = offset_bps / 10000          # зсув ціни від reference (5bps за замовч.)
tp_pct = tp_pct_arg / 100            # TP відсоток (0.4% за замовч.)
sl_pct = sl_pct_arg / 100            # SL відсоток (0.25% за замовч.)

if side == "BUY":
    limit_price = ref_price * (1 - bps)       # трохи нижче ринку
    tp_price    = limit_price * (1 + tp_pct)  # вище entry
    sl_price    = limit_price * (1 - sl_pct)  # нижче entry
else:  # SELL
    limit_price = ref_price * (1 + bps)       # трохи вище ринку
    tp_price    = limit_price * (1 - tp_pct)  # нижче entry
    sl_price    = limit_price * (1 + sl_pct)  # вище entry
```

---

## 11. Моніторинг відкритих позицій

`llm_microstructure` **не має** власного position tracker'а. Позиції потрапляють у стандартний `execution_position` domain.

### 11.1 Bracket TP/SL

Після відкриття LIMIT-ордеру `execution_position` виставляє bracket orders на Binance:
- `stop_price` → SL ордер
- `target_price` → TP ордер

При спрацюванні одного з них — другий скасовується (bracket manager).

### 11.2 Events моніторингу

Всі ці події проходять через shadow telemetry ingest (`tcp://127.0.0.1:7101`) і зберігаються у snapshot store:

| Event | Коли |
|---|---|
| `EVT:ORDER_PLACED` | LIMIT entry ордер виставлений |
| `EVT:ORDER_STATE_CHANGED` | Зміна стану ордеру (PENDING → FILLED, CANCELLED і т.д.) |
| `EVT:TRADE_EXECUTED` | Заповнення (fill) |
| `EVT:POSITION_CLOSED` | Позиція закрита (TP/SL або manual) |

### 11.3 API для спостереження

```bash
# Поточний стан snapshot (market data + features)
GET http://127.0.0.1:8443/snapshots/latest?symbol=1000PEPEUSDT

# Хвіст подій
GET http://127.0.0.1:8443/snapshots/tail?symbol=1000PEPEUSDT&limit=50

# Статус конкретного intent
GET http://127.0.0.1:8443/intents/status?intent_id=550e8400-...

# Стан черги IPC
GET http://127.0.0.1:8443/health
```

---

## 12. WAL та аудит-трейл

Кожен прийнятий/відхилений intent записується в WAL через `vfoundation.dr.wal` з обох боків:

**Shadow API side:**
- `EVT:LLM_INTENT_RECEIVED_V1` — при отриманні валідного запиту
- `EVT:LLM_INTENT_REJECTED_V1` — при будь-якому відхиленні на HTTP рівні

**Main process bridge side:**
- `EVT:LLM_INTENT_ACCEPTED_V1` — коли IPC bridge прийняв команду
- `EVT:LLM_INTENT_REJECTED_V1` — при відхиленні на рівні IPC bridge (mode/symbol check)

**Execution side:**
- `EVT:LLM_EXTERNAL_OPEN_REJECTED` — при відхиленні в `on_external_open_request()` (NRR-EXT-* codes)

**Формат WAL запису:**
```python
Message(
    op="EVT",
    verb="LLM_INTENT_RECEIVED_V1",
    src="shadow_telemetry_api",
    dst="any",
    rid=str(intent_id),
    pld={
        "intent_id": ...,
        "request_id": ...,
        "auth_subject": "bearer:sha256prefix",  # анонімізований
        "source_ip": "127.0.0.1",
        "symbol": "1000PEPEUSDT",
        "side": "BUY",
        "ts_ms": ...,
        "idempotency_key": ...,
        "why_short": ...,
    },
)
```

Додатково, при прийнятті intent, `snapshot_store.record_external_intent()` зберігає повний запис intent'у з LLM-рішенням для подальшого аналізу.

---

## 13. Синтетичний генератор інтентів

`tools/simulation/synthetic_llm_intent_generator.py` — CLI інструмент для тестування:

```bash
python tools/simulation/synthetic_llm_intent_generator.py \
    --base-url http://127.0.0.1:8443 \
    --token YOUR_BEARER_TOKEN \
    --symbol 1000PEPEUSDT \
    --side BUY \
    --qty 0.05 \
    --offset-bps 5.0 \
    --tp-pct 0.4 \
    --sl-pct 0.25 \
    --timeout-sec 8.0
```

**Що робить генератор:**
1. `GET /snapshots/latest` — отримує reference price
2. Обчислює `limit_price`, `tp_price`, `sl_price` за offset і pct параметрами
3. Генерує `inputs_digest` = sha256 від snapshot content
4. `POST /intents/llm/v1` — відправляє синтетичний intent

---

## 14. Що НЕ є активним live-шляхом (legacy surfaces)

Розуміння цього критично важливе перед рефакторингом.

| Компонент | Статус | Пояснення |
|---|---|---|
| `llm_microstructure.execution.*` | ДЕКЛАРАТИВНО / не власник live шляху | Ці поля не читаються на live зовнішньому шляху |
| `llm_microstructure.safety_gates.enabled: false` | БАЙПАСОВАНО | Safety gates в DecisionMaking не задіяні |
| `llm_microstructure.enabled` | ДЕКЛАРАТИВНО | Немає trace'у споживача що блокував би bridge на основі цього прапора |
| `EVT:STRATEGY_SIGNAL_PRODUCED` | НЕ ЕМІТУЄТЬСЯ | Live шлях йде напряму в CMD:EXTERNAL_OPEN_REQUEST_V1 |
| `StrategyGateway` | БАЙПАСУЄТЬСЯ | Зовнішній шлях не проходить через StrategyGateway |
| `DecisionMaking` | БАЙПАСУЄТЬСЯ | Повністю байпасується для external LLM інтентів |
| `IntentBuilder` | НЕ ЗАДІЯНИЙ | Не використовується на live шляху |
| `LlmMicrostructurePlugin.register()` | ТІЛЬКИ ЛОГО | Не реєструє ніяких FSM listeners |
| `timeframe_sec: 60` | МЕТАДАТА | Немає live споживача |

---

## 15. Повна карта потоку event'ів

```
LLM Agent
│
│  POST /intents/llm/v1  (Bearer auth)
│
▼
[Shadow Telemetry API]
│  — AUTH
│  — SYMBOL CHECK (symbols_llm, allowlist)
│  — SCHEMA VALIDATION (LLMIntentRequestV1)
│  — POLICY (LIMIT-only, TP/SL required, TIF, price band, qty cap)
│  — RATE LIMIT / COOLDOWN / MAX OPEN
│  — IPC PROBE
│
├─ reject → EVT:LLM_INTENT_REJECTED_V1 → WAL → HTTP 4xx/5xx
│
└─ accept → EVT:LLM_INTENT_RECEIVED_V1 → WAL
            CmdLlmIntentSubmitV1 → IPC enqueue (tcp://127.0.0.1:7102)
            HTTP 202 → {"intent_id": ..., "state": "queued"}

[IPC TCP 7102]
│
▼
[LLMIntentIngressBridge._on_command()]
│  — schema re-validation (CmdLlmIntentSubmitV1)
│  — mode check (baseline → reject)
│  — symbol re-check
│
├─ reject → EVT:LLM_INTENT_REJECTED_V1 → WAL
│
└─ accept → EVT:LLM_INTENT_ACCEPTED_V1 → WAL
            CMD:LLM_INTENT_SUBMIT_V1 → FSM bus

[FSM bus]
│
▼
[register_llm_command_mapper()._handler()]
│  listen: CMD:LLM_INTENT_SUBMIT_V1
│  build ext_payload (symbol, side, qty, price, tif, stop_price, target_price, source="external_llm")
│  emit: CMD:EXTERNAL_OPEN_REQUEST_V1
│
▼
[execution_position FSM]
│  bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", self._on_external_open_request)
│
▼
[IntentRouter.on_external_open_request()]
│  GATE 1: intent_id     → NRR-EXT-MISSING-INTENT-ID
│  GATE 2: source check  → NRR-EXT-SOURCE-INVALID
│  GATE 3: order_type    → NRR-EXT-ORDER-TYPE-NOT-LIMIT
│  GATE 4: tif           → NRR-EXT-MISSING-TIF
│  GATE 5: price         → NRR-EXT-MISSING-PRICE
│  GATE 6: valid_for_ms  → config fallback (120000ms) → NRR-EXT-MISSING-VALID-FOR-MS
│
├─ reject → EVT:LLM_EXTERNAL_OPEN_REJECTED
│
└─ accept → CMD:OPEN (strategy="llm_microstructure", side, qty, price=LIMIT, tif, valid_for_ms, stop_price, target_price)
            self._fsm.handle(cmd_open)

[Execution chain]
│
├─ Binance LIMIT order placed → EVT:ORDER_PLACED → shadow_telemetry ingest (7101)
│
├─ Fill → EVT:TRADE_EXECUTED → shadow_telemetry ingest (7101)
│
├─ Bracket TP order
│
├─ Bracket SL order
│
└─ Position close (TP/SL hit) → EVT:POSITION_CLOSED → shadow_telemetry ingest (7101)
```

---

## 16. Точки розширення для нового агентного середовища

На основі реального коду, ось де є найбільше можливостей для розширення без порушення існуючих контрактів.

### 16.1 Розширення інформаційної моделі intent

| Поточний стан | Що можна додати |
|---|---|
| `model_meta` опційний, не споживається runtime'ом | Додати обов'язкову валідацію + WAL enrichment з `model`, `prompt_hash` |
| `why_short` обмежений 80 символами | Додати `why_long` / `reasoning_blob` в `model_meta` або окрему секцію |
| `snapshot_ref` лише ID + digest | Додати `inputs_hash` від конкретного feature-set що бачив агент |
| `policy_hints.expiry_ts_ms` існує але не споживається | Підключити як override для `valid_for_ms` замість TTL-fallback |

### 16.2 Розширення символів

```yaml
# config/aurora/strategies.yaml
assignments:
  1000PEPEUSDT:
    - llm_microstructure
  DOGEUSDT:          # ← додати нові символи
    - llm_microstructure

# config/aurora/trading.yaml
llm_orchestration:
  symbols_llm:
    - 1000PEPEUSDT
    - DOGEUSDT       # ← синхронно
  allowlist_symbols:
    - 1000PEPEUSDT
    - DOGEUSDT       # ← синхронно
```

### 16.3 Перехід від суто LIMIT до змішаного режиму

```yaml
# config/aurora/trading.yaml
llm_orchestration:
  intent_policy:
    allow_limit_only: false         # дозволяє MARKET
    allowed_tif: [GTC, IOC, FOK]   # розширення TIF
```

**Увага:** При `allow_limit_only: false` потрібно оновити GATE 3 в `on_external_open_request()` — наразі він жорстко вимагає `LIMIT`.

### 16.4 Підключення режиму advisory через decision feedback

Поточний live шлях байпасує DecisionMaking. Якщо новий агент має власну логіку оцінки сигналів, можна додати опційний feedback loop:
- агент читає `EVT:LLM_INTENT_ACCEPTED_V1` / `EVT:POSITION_CLOSED` зі snapshot tail
- агент отримує P&L результат і коригує наступний intent

### 16.5 Розширення `/snapshots/latest` для агента

Shadow Telemetry API надає агенту повний контекст для ухвалення рішення:

```bash
# Що агент може отримати перед відправкою intent
GET /snapshots/latest?symbol=1000PEPEUSDT

# Відповідь містить:
# features.price         → reference price для розрахунку TP/SL
# features.regime        → поточний режим (TREND_UP, RANGE, тощо)
# features.volume        → обсяг
# bar.{open,high,low,close,volume} → остання закрита свіча
```

### 16.6 Monitoring endpoint для UI-панелі

UI може опитувати ці ендпоінти для відображення стану:

```bash
# Загальний стан системи
GET /health
# → {"status": "healthy", "queue_depth": 0, "ts_ms": ...}

# Хвіст останніх подій (включаючи LLM events)
GET /snapshots/tail?limit=50
# → {"items": [...], "next_cursor": null}

# Статус конкретного intent (до TTL idempotency)
GET /intents/status?intent_id=550e8400-...
# → {"intent_id": ..., "state": "queued", "symbol": ..., "ts_ms": ...}
```

### 16.7 Multi-token access для різних агентів

```bash
# .env
SHADOW_TELEMETRY_BEARER_TOKENS=token_agent1,token_agent2,token_ui_panel
```

Кожен токен отримує незалежний rate limit bucket (по `auth_subject = sha256(token)[:16]`).

---

## Підсумок: критичні факти перед рефакторингом

1. **Plugin = sentinel.** `LlmMicrostructurePlugin` не містить бізнес-логіки. Вся логіка в `shadow_telemetry/main_bridge.py` та `execution_position/flows/open/intent_router.py`.

2. **Два незалежні шари policy.** Shadow API (`intent_policy`) + IntentRouter gates — два незалежні рівні захисту. Зміна одного не впливає на інший.

3. **Єдиний реально споживаний параметр профілю на live шляху** — `pending_entry_ttl_ms: 120000`. Решта полів профілю декларативні.

4. **Байпас DecisionMaking — навмисний.** Live зовнішній шлях ніколи не проходив через `StrategyGateway → safety_gates → IntentBuilder`. Це архітектурне рішення, не баг.

5. **TP/SL формуються агентом** і передаються як `brackets.{tp_price,sl_price}`. Система тільки валідує `sl < entry < tp` для BUY і навпаки для SELL.

6. **IPC — двосторонній.** `7101` (main→shadow, market events tap) та `7102` (shadow→main, LLM commands) — різні канали, різне призначення.
