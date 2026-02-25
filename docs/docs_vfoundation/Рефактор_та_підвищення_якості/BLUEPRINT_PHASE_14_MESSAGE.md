# vFoundation Engineering Blueprint — Phase 14.3 & 14.4: Message Protocol Refactoring

**Дата:** 2026-02-24
**Статус:** Draft (Ready for Execution)
**Пов'язані файли:**
- `vfoundation/core/protocol.py` — ціль рефакторингу (основний Message, 68 LOC)
- `apps/reference/dictionaries/verb_registry_v1.yaml` — verb SSOT (365 LOC, має `schema` paths)
- `vfoundation/dictionaries/global_v2_2.yaml` — governance config (22 LOC: ops, stdlib_verbs, routing_modes, TTL profiles)
- `vfoundation/schemas/verbs/` — **нова директорія** для Pydantic payload схем (ще не існує)

---

## 1. Проблема та Обґрунтування (The Why)

### 1.1 Поточний стан `Message` (68 LOC, `protocol.py`)

Поточний `Message` є Pydantic-моделлю з жорстко вбудованими Binance-специфічними полями:

```
oco_group_id: Optional[str]           # OCO group ID for entry + SL/TP orders
parent_client_order_id: Optional[str] # Parent order ID for SL/TP orders
link_ack_id: Optional[str]            # Link to exchange ACK order_id
link_fill_id: Optional[str]           # Link to fill order_id
corr_id: Optional[str]                # Correlation ID for order lifecycle
mode: str = "live"                    # live, backtest, paper
mode_contract: Optional[str]          # Mode-specific contract ID
```

**Це порушує принцип "LLM-Friendly Modularity"** та позицію `vfoundation` як **universal framework**: будь-який розробник, що хоче використати `vfoundation` не для трейдингу (наприклад, для медицини чи IoT), змушений бачити "oco_group_id" і не розуміти що це.

### 1.2 Наслідки проблеми
1. **`pld: Dict[str, Any]` — це фактично `Any`** — жодної type-safety на рівні payload. Контракти тримаються лише на конвенції (naming convention), а не на механізмі. LLM або будь-який розробник може передати що завгодно, і система не виявить порушення одразу.
2. **Відсутність per-verb schema validation** — `FSMCore.emit()` не валідує payload проти схеми verb. Помилки "неправильна структура payload" проявляються late at runtime, а не при `emit()`.
3. **Складний Verb Registry Integration** — `verb_registry_v1.yaml` (SSOT) містить для деяких verb-ів поле `schema` з шляхами до JSON-файлів, але ці схеми ніколи не перевіряються при runtime. `global_v2_2.yaml` — мінімальний governance config (22 LOC: ops, stdlib_verbs, routing_modes, TTL profiles), без `payload_schema` полів.

---

## 2. Архітектурне Рішення: Двофазний Підхід

### Фаза A: Очищення Envelope (Backward-Safe)
### Фаза B: Типізований Payload (Pydantic Discriminated Unions)

---

## 3. Фаза A: Очищення `Message` Envelope — Детальний Дизайн

### 3.1 Ціль: "Generic Protocol Envelope"

Після рефакторингу `Message` буде містити **виключно протокольно-необхідні поля**, незалежні від бізнес-домену:

```python
# ПІСЛЯ РЕФАКТОРИНГУ: vfoundation/core/protocol.py
class Message(BaseModel):
    # --- Envelope (Protocol-Level) ---
    v: int = 1                          # ЗАЛИШАЄТЬСЯ v=1 до Phase 16 compat layer (v=2 тільки після повної міграції)
    op: Op                              # ASK | DEC | CMD | EVT | UPD | ERR
    verb: str                           # VERB зі словника (глобального або доменного)
    src: str                            # Ідентифікатор відправника (напр. "decision_making")
    dst: str | Literal["any"]           # Ідентифікатор отримувача
    rid: str                            # Request ID (trace anchor) — UUID4
    span_id: str                        # Span ID для distributed tracing
    parent_span_id: Optional[str]       # Parent span для складних потоків
    ts: int                             # Unix timestamp (ms)
    ttl_ms: int                         # Time-to-live (1..30000 ms)
    
    # --- Observability / Contracts ---
    why: Optional[str]                  # ≤80 chars, mandatory for DEC/CMD
    why_explain_ref: Optional[str]      # Посилання на деталі у XAI store
    why_chain: List[str] = []           # Ланцюжок "чому" від джерела до поточного вузла
    intent: Optional[IntentType]        # INQUIRY | COMMAND | PROPOSAL | OBSERVATION
    data_ref: List[str] = []            # References до великих об'єктів (data_ref pattern)
    
    # --- Security ---
    sig: Optional[str]                  # Ed25519 підпис для CMD/DEC
    
    # --- Typed Payload (NEW!) ---
    pld: Dict[str, Any] = {}            # Payload — БУДЕ deprecated на користь typed_pld
    # typed_pld: Optional[AnyVerbPayload] = None  # Phase B: Discriminated Union

    # --- Auxiliary ---
    key: Optional[str]                  # Routing key для Router
    idempotent_key: Optional[str]       # Для idempotency checks
```

**Поля, що ВИДАЛЯЄМО з `Message` (переносимо до `pld`):**

| Поле | Куди переноситься | Чому |
|---|---|---|
| `oco_group_id` | `pld["exchange_ctx"]["oco_group_id"]` | Binance-специфічне |
| `parent_client_order_id` | `pld["exchange_ctx"]["parent_client_order_id"]` | Binance-специфічне |
| `link_ack_id` | `pld["exchange_ctx"]["link_ack_id"]` | Binance-специфічне |
| `link_fill_id` | `pld["exchange_ctx"]["link_fill_id"]` | Binance-специфічне |
| `corr_id` | `pld["exchange_ctx"]["corr_id"]` | Exchange correlation — не протокольне |
| `mode` | `pld["trading_mode"]` або через `Config` | Конфігурація середовища — не протокольне |
| `mode_contract` | `pld["trading_mode_contract"]` | Теж конфігурація |

### 3.2 Migration Strategy: Deprecation Windows (Additive-First)

**Принцип:** Ми не ламаємо існуючий код. Поля залишаються в `Message` протягом **2 релізів** зі статусом `deprecated`, потім видаляємо.

**Реалізація:**

```python
# vfoundation/core/protocol.py — Перехідний стан (v1.x -> v2.0)
from pydantic import Field
import warnings

class Message(BaseModel):
    # ... (нові поля)

    # DEPRECATED: Буде видалено у v2.0. Перенесіть до pld["exchange_ctx"]
    oco_group_id: Optional[str] = Field(
        default=None, 
        deprecated="Move to pld['exchange_ctx']['oco_group_id']"
    )
    parent_client_order_id: Optional[str] = Field(
        default=None,
        deprecated="Move to pld['exchange_ctx']['parent_client_order_id']"  
    )
    link_ack_id: Optional[str] = Field(default=None, deprecated="Move to pld['exchange_ctx']")
    link_fill_id: Optional[str] = Field(default=None, deprecated="Move to pld['exchange_ctx']")
    corr_id: Optional[str] = Field(default=None, deprecated="Move to pld['exchange_ctx']")
    mode: str = Field(default="live", deprecated="Move to app-level configuration")
    mode_contract: Optional[str] = Field(default=None, deprecated="Deprecated")

    @model_validator(mode="after")
    def _warn_deprecated_fields(self) -> "Message":
        deprecated_fields = ["oco_group_id", "parent_client_order_id",
                             "link_ack_id", "link_fill_id", "corr_id"]
        for f in deprecated_fields:
            if getattr(self, f) is not None:
                warnings.warn(
                    f"Message.{f} is deprecated. Move to pld['exchange_ctx'].{f}",
                    DeprecationWarning, stacklevel=3
                )
        return self
```

### 3.3 Новий Shared Schema: `ExchangeContext`

Оскільки ці поля не зникають з системи — вони переходять у `pld` — нам потрібна єдина Pydantic-схема для них:

```python
# apps/reference/shared/schemas/exchange_ctx.py
from pydantic import BaseModel
from typing import Optional

class ExchangeContext(BaseModel):
    """Exchange-specific order correlation fields (e.g., Binance OCO, SL/TP linking).
    
    Usage: embed as pld["exchange_ctx"] = ExchangeContext(...).model_dump()
    """
    corr_id: Optional[str] = None           # Correlation ID across leg fills
    oco_group_id: Optional[str] = None      # OCO group (entry + SL + TP)
    parent_client_order_id: Optional[str] = None  # Parent order for SL/TP legs
    link_ack_id: Optional[str] = None       # Exchange ACK order ID
    link_fill_id: Optional[str] = None      # Fill order ID for correlation
```

---

## 4. Фаза B: Типізований Payload — Discriminated Unions

### 4.1 Ціль: Per-Verb Pydantic Schemas

Кожен `verb` у `global_v2_2.yaml` отримає свою Pydantic-схему. `FSMCore.emit()` буде автоматично валідувати payload проти схеми під час виклику.

**Нова структура директорій:**
```
vfoundation/
└── schemas/
    └── verbs/
        ├── __init__.py
        ├── _registry.py             # Auto-registered verb -> schema mapping
        ├── core/
        │   ├── evt_feature_calc.py  # EVT:FEATURE_CALC payload schema
        │   ├── evt_trade_intent.py  # EVT:TRADE_INTENT_PROPOSED schema
        │   ├── dec_risk_response.py # DEC:RISK_APPROVED / DEC:RISK_DENIED
        │   └── cmd_open_position.py # CMD:OPEN_POSITION payload schema
        └── dr/
            ├── evt_state_transition.py  # EVT:STATE_TRANSITION (Phase 14.2)
            └── cmd_replay.py            # CMD:REPLAY_FROM_WAL
```

### 4.2 Приклад: Повна Схема для `EVT:TRADE_INTENT_PROPOSED`

```python
# vfoundation/schemas/verbs/core/evt_trade_intent.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from decimal import Decimal

class TradeIntentPayload(BaseModel):
    """Payload schema for EVT:TRADE_INTENT_PROPOSED.
    
    Verb: EVT:TRADE_INTENT_PROPOSED
    Owner: decision_making
    Consumers: execution_position
    Since: v1.0
    """
    symbol: str = Field(..., description="Trading instrument, e.g. BTCUSDT")
    side: Literal["BUY", "SELL"] = Field(..., description="Trade direction")
    
    # Pricing
    entry_price: Decimal = Field(..., gt=0)
    stop_price: Optional[Decimal] = Field(None, gt=0)
    target_price: Optional[Decimal] = Field(None, gt=0)
    
    # Sizing
    qty: Decimal = Field(..., gt=0, description="Order quantity in base asset")
    notional_usdt: Decimal = Field(..., gt=0, description="Notional value in USDT")
    
    # Signal provenance
    strategy_id: str = Field(default="aurora")
    signal_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    regime: Optional[str] = None
    
    # Exchange context (formerly top-level Message fields)
    exchange_ctx: Optional[ExchangeContext] = None
    
    @field_validator("stop_price")
    @classmethod
    def _validate_stop_vs_entry(cls, stop, info):
        entry = info.data.get("entry_price")
        side = info.data.get("side")
        if stop and entry and side == "BUY" and stop >= entry:
            raise ValueError(f"Stop price {stop} must be below entry {entry} for BUY")
        return stop
```

### 4.3 Verb Schema Registry (`_registry.py`)

```python
# vfoundation/schemas/verbs/_registry.py
from typing import Dict, Type
from pydantic import BaseModel

# Auto-populated by @register_verb_schema decorator
_VERB_SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {}

def register_verb_schema(verb: str):
    """Decorator to register a Pydantic schema for a given verb string."""
    def decorator(cls: Type[BaseModel]):
        _VERB_SCHEMA_REGISTRY[verb] = cls
        return cls
    return decorator

def get_schema_for_verb(verb: str) -> Type[BaseModel] | None:
    return _VERB_SCHEMA_REGISTRY.get(verb)
```

### 4.4 Інтеграція з `FSMCore.emit()` — Runtime Validation

```python
# vfoundation/core/fsm_core.py — МОДИФІКАЦІЯ emit()
from vfoundation.schemas.verbs._registry import get_schema_for_verb
from pydantic import ValidationError

def emit(self, event_name: str, payload: Dict[str, Any], why: str, ...) -> None:
    verb = event_name.split(":")[1] if ":" in event_name else event_name
    
    # НОВИЙ: Runtime payload validation
    schema_cls = get_schema_for_verb(verb)
    if schema_cls is not None:
        try:
            schema_cls.model_validate(payload)  # Raises ValidationError if invalid
        except ValidationError as exc:
            self.logger.error(
                "PAYLOAD_SCHEMA_VIOLATION: verb=%s errors=%s",
                verb, exc.errors()
            )
            # Write to WAL as ERR:PAYLOAD_SCHEMA_VIOLATION
            # Fail-closed: do NOT deliver the message
            return
    # ... решта emit() залишається незмінною
```

---

## 5. Дорожня Карта Виконання (Execution Flow)

### Етап 1: Deprecation Warning Infrastructure (3 дні)
1. Додати `@model_validator` з `warnings.warn()` для всіх 7 deprecated полів у `Message`.
2. Запустити `pytest` — всі тести мають пройти (gate: ≥716 passed). Нові `DeprecationWarning` з'являться в stdout.
3. Запустити grep по `DeprecationWarning` у CI/CD logs — отримаємо повний список місць вжитку.

### Етап 2: Shared ExchangeContext Migration (3 дні)
1. Створити `apps/reference/shared/schemas/exchange_ctx.py` з `ExchangeContext`.
2. У `execution_position/fsm.py` замінити:
   ```python
   # БУЛО:
   Message(..., oco_group_id="xxx", corr_id="yyy")
   # СТАЛО:
   Message(..., pld={..., "exchange_ctx": ExchangeContext(oco_group_id="xxx", corr_id="yyy").model_dump()})
   ```
3. Оновити `correlation.py`, `pending_brackets_wal.py` — вони читатимуть `pld["exchange_ctx"]`.
4. *Перевірка:* `pytest tests/vfoundation/core/test_protocol.py` — нові тести для ExchangeContext, всі існуючі зелені (gate: ≥716 passed).

### Етап 3: Verb Schema Scaffolding (5 днів)
1. Створити директорію `vfoundation/schemas/verbs/` зі скелетами.
2. Реалізувати `_registry.py` та декоратор `@register_verb_schema`.
3. Написати перші 5 схем — **починаючи зі stdlib verbs** (вони не залежать від доменної логіки): `RECONCILE`, `HEALTH`, `PING`, `ALERT`, `WHY`. Потім переходити до domain verbs: `TRADE_INTENT_PROPOSED`, `RISK_APPROVED`, тощо.
4. *Перевірка:* `pytest tests/vfoundation/schemas/` — окремий тест-файл перевіряє, що для кожного verb у `verb_registry_v1.yaml` зі `schema` полем є відповідна Pydantic-схема.

### Етап 4: FSMCore Emit Validation (2 дні)
1. Інтегрувати `get_schema_for_verb()` в `FSMCore.emit()` як **warn-only** спочатку.
2. Після стабілізації — переключити в **fail-closed** режим (drop + WAL error).
3. *Перевірка:* `pytest tests/vfoundation/core/test_fsm_core_error_handling.py` — додати тест: `emit` з невалідним payload видає помилку.

### Етап 5: Видалення Deprecated Полів з Message (v2.0) (1 день)
1. Після 2 релізів (або після того, як `grep -r "oco_group_id\|link_ack_id" .` видає 0 результатів у vfoundation core) — видалити поля з `Message`.
2. **v=2 тільки після Phase 16 compat layer** — `Message.v` залишається `1` до того моменту, коли Phase 16 (Schema Versioning) забезпечить backward-compatible migration.
3. *Перевірка:* `pytest tests/vfoundation -q --tb=line` — 0 errors, 0 warnings.

---

## 6. Зведена Таблиця Полів та їх Доля

| Поле в `Message` | Статус після рефакторингу | Нове місце |
|---|---|---|
| `v` | **ЗАЛИШАЄТЬСЯ v=1** → v=2 тільки після Phase 16 compat layer | залишається |
| `op`, `verb`, `src`, `dst`, `rid` | **ЗБЕРІГАЄТЬСЯ** | залишається |
| `span_id`, `parent_span_id`, `ts`, `ttl_ms` | **ЗБЕРІГАЄТЬСЯ** | залишається |
| `why`, `why_explain_ref`, `intent`, `data_ref` | **ЗБЕРІГАЄТЬСЯ** | залишається |
| `sig` | **ЗБЕРІГАЄТЬСЯ** | залишається |
| `key`, `idempotent_key` | **ЗБЕРІГАЄТЬСЯ** | залишається |
| `pld` | **ЕВОЛЮЦІОНУЄ** — залишається, але типізується | залишається |
| `oco_group_id` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | `pld["exchange_ctx"]["oco_group_id"]` |
| `parent_client_order_id` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | `pld["exchange_ctx"]["parent_client_order_id"]` |
| `link_ack_id` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | `pld["exchange_ctx"]["link_ack_id"]` |
| `link_fill_id` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | `pld["exchange_ctx"]["link_fill_id"]` |
| `corr_id` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | `pld["exchange_ctx"]["corr_id"]` |
| `mode` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | App-level `Config` (ENV variable) |
| `mode_contract` | **DEPRECATED → ВИДАЛЯЄТЬСЯ** | App-level `Config` |

---

## 7. Критерій Успіху

1. `vfoundation/core/protocol.py` не містить жодного Binance-специфічного або trading-domain-specific поля.
2. Команда `python -c "from vfoundation.core.protocol import Message; m = Message(op='EVT', verb='PING', src='a', dst='b', why='test'); print(m.model_fields.keys())"` — не показує `oco_group_id`.
3. Для кожного verb у `verb_registry_v1.yaml` зі `schema` полем є відповідний Pydantic-клас у `vfoundation/schemas/verbs/`.
4. `FSMCore.emit("EVT:TRADE_INTENT_PROPOSED", pld={"invalid": True}, why="test")` — повертає помилку замість тихого проходу.
5. Всі тести зеленого кольору (gate: ≥716 passed).
