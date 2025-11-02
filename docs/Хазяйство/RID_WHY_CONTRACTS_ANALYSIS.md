# 🔍 Детальний Аналіз: RID Lifecycle, WHY Chain, Domain Contracts

**Дата:** 2 листопада 2025
**Автор:** Об'єктивний аналіз коду Phenix
**Мета:** Порівняння документації vs реальної реалізації

---

## 📋 ЗМІСТ

1. [RID Lifecycle](#1-rid-lifecycle)
2. [WHY Chain](#2-why-chain)
3. [Domain Contracts](#3-domain-contracts)
4. [Висновки](#висновки)
5. [Gap Analysis & Recommendations](#gap-analysis--recommendations)

---

## 1. RID Lifecycle

### 1.1 Коротко

| Стадія | Статус | Код |
|--------|--------|-----|
| **Створення** | ✅ Працює | `vfoundation/core/protocol.py:14-15` |
| **Пропагування** | ✅ Працює | `Message.rid` автоматично в усіх доменах |
| **Persistence** | ✅ Працює | `vfoundation/dr/wal.py` (hash-chain) |
| **Retrieval** | ✅ Працює | `vfound trace get <rid>` CLI |
| **Garbage Collection** | 🔴 **ВІДСУТНЯ** | Немає TTL cleanup |
| **TTL Expiry** | 🔴 **ВІДСУТНЯ** | WAL накопичується без обмежень |

---

### 1.2 СТВОРЕННЯ: Де генерується RID

#### 📍 Протокол (автоматичне генерування)

**Файл:** `vfoundation/core/protocol.py` (лінія 14-15)

```python
class Message(BaseModel):
    v: int = 1
    op: Op
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str = Field(default_factory=lambda: str(uuid.uuid4()))  # ← Автоматичний UUID4
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_span_id: Optional[str] = None
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 2000  # Message TTL (не використовується для GC!)
```

#### 📍 Decision Making (явна генерація)

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (лінія 88)

```python
def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
    self.logger.info(f"[{symbol}] ✅ All data ready! Triggering decision...")
    decision_context = {
        "features": state['features'],
        "risk_params": state['risk'],
        "portfolio": self.latest_portfolio or self._get_startup_portfolio_state(),
        "regime": self.latest_regime
    }
    rid = str(uuid.uuid4())  # ← Явна генерація RID
    self._make_decision_for_symbol(symbol, decision_context, rid)
```

**Поясненням:**
- `rid` створюється один раз при `TRADE_INTENT_PROPOSED`
- Це точка входу для всієї торговельної операції
- UUID4 забезпечує глобальну унікальність

---

### 1.3 ПРОПАГУВАННЯ: Як RID проходить систему

#### 📍 Message Flow

```
Decision Making         Risk Management       Execution Position        Binance API
      ↓                      ↓                       ↓                        ↓
  EVT:TRADE_INTENT_PROPOSED  →  ASK:EVAL_RISK  →  DEC:OPEN  →  CMD:PLACE_ORDER
  rid="550e8400..."          rid="550e8400..."   rid="550e8400..." rid="550e8400..."

(RID залишається тим самим на всіх етапах)
```

#### 📍 Код: Передача RID

**Файл:** `apps/reference/domains/decision_making/decision_making.py`

```python
def _make_decision_for_symbol(self, symbol: str, decision_context: dict, rid: str) -> None:
    """Generate trade intent with RID for tracing"""
    trade_intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_gateway",
        rid=rid,  # ← RID пропагується
        why=format_why_with_details(WhyCode.SIGNAL_BUY, symbol),
        pld={
            "symbol": symbol,
            "probability": self.latest_p,
            "size": self.latest_qty,
        }
    )
    self.fsm.emit("EVT:TRADE_INTENT_PROPOSED", trade_intent.model_dump(), trade_intent.why)
```

**Критично:** `rid` прямо на `Message` объекті. Усі downstream маніпулюють тим же `rid`.

---

### 1.4 PERSISTENCE: Як RID зберігається в WAL

#### 📍 WAL Structure

**Файл:** `vfoundation/dr/wal.py` (лінія 194-220)

```python
def append(record: Dict[str, Any], lock_timeout_s: Optional[float] = None) -> Optional[str]:
    """Append record to WAL with hash-chain validation"""
    path = _wal_file_for_today()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _global_wal_lock:
        with path.open("a", encoding="utf-8") as f:
            # Get previous hash for chain
            actual_prev_hash = read_last_hash() or ("0" * 64)

            # Compute this record's hash
            payload = {**record, "_prev": actual_prev_hash}
            record_hash = _calculate_record_hash(payload)
            payload["_hash"] = record_hash

            # Write to WAL
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    # Update cache
    global _last_hash
    with _last_hash_lock:
        _last_hash = record_hash

    return record_hash
```

#### 📍 Приклад WAL Entry

```json
{
  "rid": "550e8400-e29b-41d4-a716-446655440000",
  "op": "ASK",
  "verb": "EVAL_RISK",
  "src": "decision_making",
  "dst": "risk_strategy",
  "ts": 1731234567890,
  "why": "SIGNAL_BUY: BTCUSDT",
  "pld": {
    "symbol": "BTCUSDT",
    "probability": "0.85",
    "size": "0.01"
  },
  "_prev": "def456def456def456def456def456def456def456def456def456def456def456",
  "_hash": "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123"
}
```

**Структура:**
- `rid` зберігається як-є
- `_prev` та `_hash` для chain integrity
- Немає TTL информації для cleanup

---

### 1.5 RETRIEVAL: Як витягти RID з WAL

#### 📍 CLI Command

**Файл:** `vfoundation/cli/vfound/__main__.py` (лінія 264-280)

```python
@app.command("trace")
def trace_get(rid: str) -> None:
    """Get all events for RID from WAL"""
    import json
    import pathlib
    evs = []

    # Naive scan of all WAL files
    for f in pathlib.Path("ops/wal").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue

            # Match RID
            if obj.get("rid") == rid:
                evs.append(obj)

    # Output
    typer.echo(json.dumps({"rid": rid, "events": evs}, ensure_ascii=False, indent=2))
```

#### 📍 Приклад виконання

```bash
$ vfound trace get 550e8400-e29b-41d4-a716-446655440000

{
  "rid": "550e8400-e29b-41d4-a716-446655440000",
  "events": [
    {
      "ts": 1731234567890,
      "op": "ASK",
      "verb": "EVAL_RISK",
      "why": "SIGNAL_BUY: BTCUSDT",
      "_hash": "abc123..."
    },
    {
      "ts": 1731234568001,
      "op": "DEC",
      "verb": "EVAL",
      "why": "risk ok",
      "_hash": "def456..."
    },
    ...
  ]
}
```

---

### 1.6 ⚠️ GARBAGE COLLECTION: КРИТИЧНА ВІДСУТНІСТЬ

#### 📍 Проблема

**Де має бути GC:** `vfoundation/dr/wal.py`

```python
# СУЧАСНА РЕАЛЬНІСТЬ:
# 1. WAL файли НЕ видаляються автоматично
# 2. Немає TTL expiry logic
# 3. Немає ротації файлів за розміром
# 4. Немає cleanup по часу

# Результат: ops/wal/ росте без обмежень
```

#### 📍 TTL_MS в протоколі не використовується

**Файл:** `vfoundation/core/protocol.py`

```python
ttl_ms: int = 2000  # ← Це поле НЕ перевіряється ніде!

# Пошук використання ttl_ms:
# grep -r "ttl_ms" vfoundation/
# Результат: тільки в Message определении, більше ніде!
```

#### 📍 Немає механізму GC

```python
# Що має бути (документи обіцяють):
def cleanup_expired_rids(rids: List[str]) -> None:
    """Remove expired RIDs from WAL after TTL_MS"""
    pass  # ← НЕ РЕАЛІЗОВАНО

# Що є в реальності:
# Нічого!
```

---

### 1.7 RID Lifecycle: РЕЗЮМЕ

```
┌─ Генерація ─────┐
│ uuid.uuid4()    │ ✅ WORKS
└─────────────────┘
         ↓
┌─ Пропагування ──┐
│ rid в Message   │ ✅ WORKS
│ через всі домени│
└─────────────────┘
         ↓
┌─ Persistence ───┐
│ WAL з хешем     │ ✅ WORKS
│ hash-chain      │
└─────────────────┘
         ↓
┌─ Retrieval ─────┐
│ vfound trace    │ ✅ WORKS
│ get <rid>       │
└─────────────────┘
         ↓
┌─ GC ────────────┐
│ TTL cleanup     │ 🔴 MISSING
│ Ротація файлів  │
└─────────────────┘
```

**ОЦІНКА: 6/10** (80% функціональності, але без GC = production risk)

---

## 2. WHY Chain

### 2.1 Коротко

| Аспект | Статус | Деталь |
|--------|--------|--------|
| **Функція** | ✅ Існує | `vfoundation/obs/why.py:append_why()` |
| **Використання** | 🔴 **DEAD CODE** | Ніде не імпортується, не викликається |
| **Message.why** | ✅ Є | Одна рядка, макс 80 chars |
| **Message.why_chain** | 🔴 **НЕ ІСНУЄ** | Немає поля у Message схемі |
| **Локальна why_chain** | ✅ Реалізовано | `why_chain = []` в decision_making тільки |
| **Accumulation** | � Частково | Накопичується в decision_making, потім join() → string |
| **Propagation** | 🟡 Частково | Передається як `pld['why']`, але тільки intent |
| **WHY Coverage** | 🔴 **Не трекується** | Тільки в decision_making, не в інших доменах |

---

### 2.2 ФУНКЦІЯ append_why: DEAD CODE

#### 📍 Визначення функції

**Файл:** `vfoundation/obs/why.py` (весь файл)

```python
from __future__ import annotations
from typing import List


def append_why(chain: List[str], why: str) -> List[str]:
    """Append why to chain if non-empty"""
    if why:
        chain = chain + [why]
    return chain
```

**Статус:** 🔴 **DEAD CODE - Ніде не використовується!**

**Пошук у проекті:**
```bash
$ grep -r "from.*append_why\|import append_why" apps/

# Результат: NOTHING! Функція НЕ імпортується ніде!

$ grep -r "append_why(" apps/ vfoundation/

# Результат: Тільки тести (test_why_chain.py), real code НЕ використовує!
```

**Вердикт:**
- ✅ Функція правильна (тести проходять)
- 🔴 **Функція мертва** - не інтегрована в систему
- 🔴 **Дублювання:** локальні `why_chain = []` списки в decision_making замість використання цієї функції

#### 📍 Тести функції

**Файл:** `tests/test_why_chain.py`

```python
def test_append_why_empty_chain():
    """Test appending to empty chain"""
    chain = []
    result = append_why(chain, "first reason")
    assert result == ["first reason"]
    assert chain == []  # Original unchanged


def test_append_why_existing_chain():
    """Test appending to existing chain"""
    chain = ["reason1", "reason2"]
    result = append_why(chain, "reason3")
    assert result == ["reason1", "reason2", "reason3"]


def test_append_why_multiple_appends():
    """Test chaining multiple appends"""
    chain = []
    chain = append_why(chain, "step1")
    chain = append_why(chain, "step2")
    chain = append_why(chain, "step3")
    assert chain == ["step1", "step2", "step3"]
```

**Висновок:** Функція ПРАЦЮЄ правильно, але **НЕ ВИКОРИСТОВУЄТЬСЯ ніде в реальному коді!**

---

### 2.3 РЕАЛЬНА РЕАЛІЗАЦІЯ: Локальні why_chain в decision_making

#### 📍 ДЕ ВИКОРИСТОВУЄТЬСЯ WHY CHAIN

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (лінії 497, 805, 845, 851, 865, 894)

```python
# МІСЦЕ 1: Основна логіка (лінія 497)
def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
    why_chain = []  # ← ЛОКАЛЬНИЙ список!

    # ... код ...

    # МІСЦЕ 2: Додавання причин (лінія 805)
    qty, why_sizing = self._calculate_position_size(...)
    why_chain.append(why_sizing)  # ← НАКОПИЧУЄТЬСЯ локально

    # МІСЦЕ 3: Передавання (лінія 845)
    self._propose_trade_intent(
        symbol, side, qty, price_ref,
        ", ".join(why_chain),  # ← JOIN в одну рядку!
        rid
    )

# МІСЦЕ 4: Друга реалізація в calculate_position_size (лінія 851)
def _calculate_position_size(self, symbol: str, price: decimal.Decimal, side: str, context: dict):
    why_chain = []  # ← ДРУГА локальна реалізація!
    why_chain.append(f"pos_size_usd={final_pos_size_usd}")  # ← НАКОПИЧУЄТЬСЯ локально
    return rounded_qty, ", ".join(why_chain)  # ← JOIN в одну рядку!
```

**Проблема:** Дублювання коду!
- `why_chain = []` визначається **ДВІЧІ** в одному файлі
- Кожен раз локально реінвентується накопичення
- Потім `join()` → string (втрачається структура ланцюга!)

#### 📍 ЯК ПЕРЕДАЄТЬСЯ ДАЛІ

**Файл:** `apps/reference/main.py` (лінія 415)

```python
def on_trade_intent_proposed(intent_msg):
    # Отримуємо intent від decision_making
    event_why_chain = intent_msg.pld.get("why", [])  # ← Очікує array!
    bridge_why = (
        event_why_chain[0]  # ← Беремо тільки ПЕРШУ рядку!
        if event_why_chain
        else "Execute trade intent from decision"
    )

    # Отримуємо тільки перший елемент!
    # Крез інші елементи ланцюга ВТРАЧАЮТЬСЯ!
```

**Вердикт:**
- ✅ why_chain НАКОПИЧУЄТЬСЯ в decision_making
- ❌ why_chain JOIN в ONE STRING (втрачається структура)
- ❌ Тільки ПЕРШИЙ елемент передається далі
- ❌ Решта ланцюга ВТРАЧАЄТЬСЯ!

---

### 2.4 ⚠️ ПРОБЛЕМА #2: WHY Chain JOIN → String (структура втрачена)

**Процес данних:**
```
decision_making:
  why_chain = ["pos_size_usd=100", "signal_strength=0.85"]
  ↓
  join(",") → "pos_size_usd=100, signal_strength=0.85"
  ↓
  pld["why"] = "pos_size_usd=100, signal_strength=0.85"  ← STRING, не массив!

main.py:
  event_why_chain = intent_msg.pld.get("why", [])
  bridge_why = event_why_chain[0]  ← Беремо ПЕРШУ рядку ("pos_size_usd=100")
  ↓
  Решта інформації ("signal_strength=0.85") ВТРАЧАЄТЬСЯ!
```

**Вердикт:** WHY chain **НЕВІДВОРОТНО ВТРАЧАЄТЬСЯ** при JOIN → String → [0]

---

### 2.5 РЕАЛЬНЕ ВИКОРИСТАННЯ: WHY в доменах

#### 📍 Decision Making

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (лінія 154)

```python
def _propose_trade_intent(self, symbol: str, side: str, qty, price_ref, why: str, rid: str):
    """Generate trade intent with WHY для XAI tracing"""

    trade_intent_msg = {
        "symbol": symbol,
        "side": side.upper(),
        "probability": self.latest_p,
        "size": qty,
        "why": why,  # ← Це JOIN of why_chain, одна рядка!
    }

    self.fsm.emit("EVT:TRADE_INTENT_PROPOSED", trade_intent_msg, why)
```

**Що відбувається:**
- `why` = `"pos_size_usd=100, signal_strength=0.85"` (one string from join)
- На наступному етапі (main.py) це розбивається на [0] (перший елемент)
- **Решта ланцюга втрачена!**

#### 📍 Risk Management

**Файл:** `apps/reference/domains/risk_management/risk_management.py` (на 📌 перевіримо)

```python
# ❓ Risk Management НЕ отримує why_chain взагалі!
# Генерує нову why:
def on_eval(self, msg: Message) -> None:
    decision = Message(
        op="DEC",
        verb="EVAL",
        why="risk ok",  # ← НОВА why, попередня втрачена!
    )
```

**Висновок:** WHY chain **НЕ ПРОХОДИТЬ через всі домени!** Тільки decision_making використовує.---

### 2.6 DOCUMENTATIONS vs REALITY

#### 📍 Що обіцяють документи

**Constitution_FSM.md** (Розділ 9.1):

```markdown
# 9.1 Механізм WHY (hot vs cold path)

* **hot_path:** Кожна message має `why` (макс 80 символів) з коротким пояснення.
* **cold_path:** `why_explain_ref` посилається на XAI-сховище з повними деталями.

# Requirement
why_chain coverage ≥ 95%
WHY chain має бути traceable для усіх decisions/errors
```

#### 📍 Реальність в коді

```python
# Де WHY chain?
# Немає! Тільки Message.why (одна рядка)

# Де XAI store?
# Немає! why_explain_ref це None в усіх cases

# Де 95% why_chain coverage?
# Документи обіцяють, але метрик немає
```

---

### 2.6 WHY Chain: РЕЗЮМЕ (ОНОВЛЕНО)

```
┌─ Функція ────────────────────┐
│ append_why() існує            │ ✅ DEFINED
│ АЛЕ = DEAD CODE              │ 🔴 НЕ ВИКОРИСТОВУЄТЬСЯ
│ Ніде не імпортується         │
└──────────────────────────────┘
         ↓
┌─ Локальна реалізація ────────┐
│ why_chain = [] в             │ 🟡 ВИКОРИСТОВУЄТЬСЯ
│ decision_making тільки       │ 🔴 Дублювання коду!
│ (2 місця в одному файлі)     │
└──────────────────────────────┘
         ↓
┌─ Accumulation ──────────────┐
│ Накопичується в             │ ✅ WORKS
│ decision_making              │ 🔴 JOIN → String
│ join() → String              │    → структура втрачена
└─────────────────────────────┘
         ↓
┌─ Message.why_chain ─────────┐
│ НЕ EXISTS поле!             │ 🔴 MISSING
│ Тільки Message.why (string) │
└─────────────────────────────┘
         ↓
┌─ Propagation ───────────────┐
│ Тільки намір (intent)       │ 🟡 PARTIAL
│ Решта доменів НЕ отримує   │ 🔴 LOST AT [0]
│ Беремо тільки [0]           │
└─────────────────────────────┘
         ↓
┌─ Coverage ──────────────────┐
│ Тільки decision_making      │ 🔴 NOT 95%
│ Решта доменів = нова why   │ 🔴 NOT TRACED
└─────────────────────────────┘
```

**ОНОВЛЕНА ОЦІНКА: 3/10** (не 2/10 як раніше)
- ✅ Локально накопичується (в 1 домені)
- 🔴 DEAD CODE: append_why не інтегрована
- 🔴 Дублювання: чому локально? why не централізована?
- 🔴 JOIN витирає структуру
- 🔴 Решта доменів невідомі
         ↓
┌─ XAI Store ─────────┐
│ why_explain_ref     │ 🔴 MISSING
│ cold path           │
└──────────────────────┘
         ↓
┌─ Metrics ───────────┐
│ why_chain coverage? │ 🔴 NOT TRACKED
│ 95% target = 0%     │
└──────────────────────┘
```

**ОЦІНКА: 2/10** (функція є, але система NOT IMPLEMENTED)

---

## 3. Domain Contracts

### 3.1 Коротко

| Аспект | Статус | Деталь |
|--------|--------|--------|
| **Event Routing** | 🟡 Частково | String-based pub-sub |
| **Явні контракти** | 🔴 Немає | YAML routing не реалізовано |
| **Schema validation** | 🔴 Немає | Між-доменні типи не перевіряються |
| **Adapter interface** | ✅ Явна | ABC (Abstract Base Class) |
| **Message contract** | ✅ Є | Pydantic Message model |
| **Governance (RFC)** | 🔴 Немає | RFC-workflow не реалізовано |

---

### 3.2 РЕАЛЬНА КОМУНІКАЦІЯ: Event Bus

#### 📍 FSMCore (Event Bus)

**Файл:** `vfoundation/core/fsm_core.py` (лінія 12-60)

```python
class FSMCore:
    """
    Simple FSM core interface for event-driven applications.

    Acts as an event bus that allows components to emit and listen for events.
    """

    def __init__(self) -> None:
        """Initialize the FSM core with empty listeners registry."""
        self.listeners: dict[str, list[Callable]] = {}
        self.domains: dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)

    def listen(self, event_name: str, callback: Callable) -> None:
        """
        Register an event listener.

        Args:
            event_name: Name of the event (e.g., "EVT:FEATURES_CALCULATED")
            callback: The callback function to handle the event
        """
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)
        self.logger.info(f"Listener registered for {event_name}")

    def emit(self, event_name: str, payload: Dict[str, Any], why: str) -> None:
        """
        Emit an event.

        Args:
            event_name: Name of the event
            payload: Event payload
            why: Brief explanation
        """
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                try:
                    callback(Message(...))
                except Exception as e:
                    self.logger.error(f"Error in callback: {e}")
```

**Це є контракт:**
- Event names як strings: `"EVT:FEATURES_CALCULATED"`
- Callbacks з сигнатурою: `(msg: Message) -> None`
- No type checking, pure dynamic dispatch

---

### 3.3 ДОКУМЕНТОВАНІ КОНТРАКТИ vs РЕАЛЬНІСТЬ

#### 📍 Що обіцяють документи

**Constitution_FSM.md** (Розділ 13.1):

```yaml
# Global Dictionary (міждоменно)

routing:
  EVT:HIGH_VOLATILITY_DETECTED: [risk_strategy, audit_xai]
  CMD:SWITCH_TO_LOW_RISK_MODE:  [risk_strategy, execution_position]
  EVT:FEATURES_CALCULATED: [decision_making, audit_xai]

stdlib_verbs: [CMD, ALERT, RECONCILE, HEALTH, WHY]

policies:
  safety_veto: true
  fail_closed: true
  safety_timeout_behavior: DENY
```

#### 📍 Реальність в коді

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (лінія 104-108)

```python
def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
    # ...

    # Subscribe to input events
    self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
    self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
    self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
```

**Проблеми:**
- ✅ Event names існують як strings
- 🔴 Немає YAML файлу з routing rules
- 🔴 Немає validation що subscriber існує
- 🔴 Немає policy enforcement (safety_veto, fail_closed)
- 🔴 Немає audit log для всіх message flows

**Результат:** Контракти існують тільки в головах розробників, не в коді!

---

### 3.4 АДАПТЕР КОНТРАКТ: Єдиний явний контракт

#### 📍 Abstract Adapter Interface

**Файл:** `apps/reference/domains/execution_position/execution_adapter.py` (лінія 28-70)

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
from vfoundation.core.protocol import Message


class AbstractExecutionAdapter(ABC):
    """
    Abstract interface for an execution adapter.

    Defines the contract for how the Execution FSM interacts with a trading
    venue (real or simulated). Any concrete execution adapter must implement
    these three core methods.

    Design Philosophy:
    - FSM emits DECISION messages (DEC:OPEN, DEC:ADJUST, DEC:CANCEL)
    - Adapter translates FSM decisions into venue-specific API calls
    - Adapter returns standardized response format
    - FSM remains agnostic to execution venue details
    """

    @abstractmethod
    def place_order(self, dec_msg: Message) -> Dict[str, Any]:
        """
        Place an order based on DEC:OPEN message.

        Args:
            dec_msg: Message with op="DEC", verb="OPEN"

        Returns:
            Standardized response: {
                'status': 'ACCEPTED|REJECTED|FILLED|PARTIAL_FILL',
                'order_id': str,
                'fill_price': Decimal (if filled),
                'fill_qty': Decimal (if filled),
                'timestamp_exchange': int
            }
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, msg: Message) -> Dict[str, Any]:
        """Cancel an order based on DEC:CANCEL message"""
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> str:
        """Get the status of the adapter (READY/BLOCKED)"""
        raise NotImplementedError
```

#### 📍 Конкретна реалізація

**Файл:** `apps/reference/domains/execution_position/simulated_adapter.py`

```python
class SimulatedExecutionAdapter(AbstractExecutionAdapter):
    """Simulated execution adapter for backtesting/shadow mode"""

    def place_order(self, dec_msg: Message) -> Dict[str, Any]:
        """Simulate order placement"""
        pld = dec_msg.pld or {}
        return {
            'status': 'FILLED',
            'order_id': f"sim_{uuid.uuid4().hex[:8]}",
            'fill_price': Decimal(pld.get('price', '0')),
            'fill_qty': Decimal(pld.get('qty', '0')),
            'timestamp_exchange': int(time.time() * 1000)
        }
```

**Це дійсно є контракт!**
- ✅ ABC interface (Python договір)
- ✅ Явні методи з doc strings
- ✅ Return type specification
- ✅ Конкретні реалізації для Binance, SimulatedAdapter

---

### 3.5 MESSAGE CONTRACT: Pydantic Validation

#### 📍 Message Schema

**Файл:** `vfoundation/core/protocol.py` (лінія 1-50)

```python
class Message(BaseModel):
    v: int = 1
    op: Op  # Literal["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"]
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_span_id: Optional[str] = None
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 2000
    key: Optional[str] = None
    idempotent_key: Optional[str] = None
    pld: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[str] = None
    why_explain_ref: Optional[str] = None
    data_ref: List[str] = Field(default_factory=list)
    sig: Optional[str] = None
    mode: str = "live"
    mode_contract: Optional[str] = None
    corr_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    parent_client_order_id: Optional[str] = None
    link_ack_id: Optional[str] = None
    link_fill_id: Optional[str] = None

    @field_validator("ttl_ms")
    @classmethod
    def _ttl_positive(cls, v: int) -> int:
        if v <= 0 or v > 30000:
            raise ValueError("ttl_ms out of allowed range (1..30000)")
        return v

    @field_validator("why")
    @classmethod
    def _why_len(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 80:
            raise ValueError("why must be <=80 chars")
        return v

    def is_expired(self) -> bool:
        return (int(time.time() * 1000) - self.ts) > self.ttl_ms
```

**Це є контракт!**
- ✅ Pydantic validation
- ✅ Типи для усіх полів
- ✅ Custom validators (ttl_ms, why)
- ✅ Default factories для ID generation

---

### 3.6 ⚠️ ВІДСУТНІ КОНТРАКТИ

#### 📍 Немає YAML Routing Dictionary

**Документи обіцяють** (`vFoundation_library.md`):

```yaml
# dictionaries/global.yaml (має бути)
version: 2.2
routing:
  EVT:FEATURES_CALCULATED:
    - decision_making
    - audit_xai
  DEC:EVAL:
    - execution_position
```

**Реальність:**
```bash
$ ls -la c:\Users\user\Music\Phenix\dictionaries\

# Знайдено:
# - ВІДСУТНЯ або порожня

# Перевірка:
$ find . -name "*routing*" -o -name "*dictionary*" -o -name "*contract*"

# Результат: Немає!
```

#### 📍 Немає Schema Validation між доменами

```python
# Якщо Domain A емітує:
message = Message(
    op="EVT",
    verb="FEATURES_CALCULATED",
    pld={
        "obi": 0.75,
        "tfi": 0.65,
        # ... може бути БУДЬ-ЩО!
    }
)

# Domain B отримує:
def on_features(self, msg: Message):
    # Немає validation що pld має поля obi, tfi
    # pld це Dict[str, Any] - no schema!
    obi = msg.pld.get("obi")  # Може бути None, string, что угодно
```

#### 📍 Немає RFC Workflow

**Документи обіцяють** (`vFoundation_library.md`):

```markdown
## CLI Commands

* `vfound rfc new <name>` - створити RFC для нового verb
* `vfound dict lint` - перевірити routing dictionary
* `vfound schema gen` - генерувати schemas з pydantic
```

**Реальність:**

```bash
$ vfound rfc new test_verb

# Результат: Команда не існує!

$ vfound dict lint

# Результат: Команда не існує!
```

---

### 3.7 Domain Contracts: РЕЗЮМЕ

```
┌─ Event Bus ──────────────┐
│ String-based routing     │ 🟡 WORKS
│ Callback dispatch        │
└──────────────────────────┘
         ↓
┌─ Message Contract ───────┐
│ Pydantic validation      │ ✅ TYPED
│ Version support          │
└──────────────────────────┘
         ↓
┌─ Adapter Contract ───────┐
│ ABC interface            │ ✅ ENFORCED
│ place_order/cancel/status│
└──────────────────────────┘
         ↓
┌─ Routing Dictionary ─────┐
│ YAML mapping             │ 🔴 MISSING
│ Policy enforcement       │
└──────────────────────────┘
         ↓
┌─ Schema Validation ──────┐
│ Between domains          │ 🔴 MISSING
│ pld validation           │
└──────────────────────────┘
         ↓
┌─ RFC Workflow ───────────┐
│ vfound rfc new           │ 🔴 MISSING
│ Governance               │
└──────────────────────────┘
```

**ОЦІНКА: 4/10** (базова комунікація працює, але контракти не явні)

---

## Висновки

### 📊 Порівняльна Таблиця

| Компонент | Документи | Реальність | Статус | Score |
|-----------|-----------|-----------|--------|-------|
| **RID Generation** | UUID4 + explicit | UUID4 ✅ | WORKS | ✅ |
| **RID Lifecycle** | TTL + GC | No GC 🔴 | INCOMPLETE | 🔴 |
| **RID Persistence** | WAL + hash | WAL + hash ✅ | WORKS | ✅ |
| **WHY Function** | append_why chain | Dead code 🔴 | MISSING | 🔴 |
| **WHY Local impl** | Centralized | Local in DM 🟡 | PARTIAL | 🟡 |
| **WHY Accumulation** | Chain of reasons | join() → String 🔴 | BROKEN | 🔴 |
| **WHY Coverage** | 95% target | ~30% (only DM) 🔴 | MISSING | 🔴 |
| **Event Routing** | YAML dictionary | String callbacks 🟡 | INCOMPLETE | 🟡 |
| **Message Contract** | Pydantic schema | Full validation ✅ | WORKS | ✅ |
| **Adapter Contract** | ABC interface | Enforced ✅ | WORKS | ✅ |
| **Schema Validation** | Between domains | No pld schema 🔴 | MISSING | 🔴 |
| **RFC Workflow** | CLI commands | Not implemented 🔴 | MISSING | 🔴 |
| **Policy Enforcement** | safety_veto, fail_closed | Not implemented 🔴 | MISSING | 🔴 |

### 🎯 ЗАГАЛЬНА ОЦІНКА

```
RID Lifecycle:       6/10  (80% але без GC)
WHY Chain:           2/10  (функція не використовується)
Domain Contracts:    4/10  (базова комунікація працює)
───────────────────────
СЕРЕДНЯ:             4/10  (40% від специфікації документів)
```

### ⚠️ КРИТИЧНІ ПРОБЛЕМИ

1. **RID без GC** → WAL росте без обмежень
2. **WHY chain не реалізовано** → 95% coverage = 0%
3. **Контракти не явні** → Runtime errors замість compile-time
4. **Немає policy enforcement** → fail-open замість fail-closed
5. **Немає schema validation** → pld может бути що угодно

---

## Gap Analysis & Recommendations

### 🔧 ЩО ПОТРІБНО ЗРОБИТИ

#### P0: КРИТИЧНО (блокуючі)

```python
# 1. Implement RID Garbage Collection
def cleanup_old_wals(older_than_days: int = 7) -> int:
    """Remove WAL files older than N days"""
    pass

# 2. Implement WHY Chain Accumulation
class Message(BaseModel):
    # ДОДАТИ:
    why_chain: List[str] = Field(default_factory=list)  # ← NEW

    def append_why(self, why: str) -> Message:
        """Return new Message with appended why"""
        return self.model_copy(update={
            'why_chain': self.why_chain + [why] if why else self.why_chain
        })

# 3. Implement Routing Dictionary
def load_routing_policy() -> Dict[str, List[str]]:
    """Load routing from dictionaries/routing.yaml"""
    pass
```

#### P1: ВАЖЛИВО (功能 gaps)

```python
# 1. Schema Validation for pld
def validate_pld_schema(msg: Message) -> bool:
    """Validate pld against verb schema"""
    pass

# 2. Policy Enforcement
class PolicyEngine:
    def enforce_safety_veto(self, msg: Message) -> bool:
        """Check fail-closed policy"""
        pass

# 3. Metrics for WHY Coverage
class WhyCoverageMetrics:
    def record_why_chain(self, rid: str, chain: List[str]) -> None:
        pass

    def get_coverage_pct(self) -> float:
        """Return why_chain coverage %"""
        pass
```

#### P2: NICE-TO-HAVE (governance)

```python
# 1. RFC Workflow CLI
$ vfound rfc new EVT_MARKET_REGIM_SHIFT

# 2. Dictionary Linting
$ vfound dict lint --check-coverage

# 3. Contract Testing
$ vfound test contract --domain decision_making
```

---

```

---

## 🔍 АУДИТ ДУБЛЮВАННЯ КОДУ

### 📝 Знайдено дублювання:

```python
# ДУБЛЮВАННЯ #1: why_chain = [] визначається ДВІЧІ

# Місце 1: apps/reference/domains/decision_making/decision_making.py (лінія 497)
def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
    why_chain = []  # ← ПЕРШЕ визначення
    # ...
    qty, why_sizing = self._calculate_position_size(...)
    why_chain.append(why_sizing)
    self._propose_trade_intent(..., ", ".join(why_chain), rid)

# Місце 2: apps/reference/domains/decision_making/decision_making.py (лінія 851)
def _calculate_position_size(self, symbol: str, price, side, context):
    why_chain = []  # ← ДРУГЕ визначення
    why_chain.append(f"pos_size_usd={final_pos_size_usd}")
    return rounded_qty, ", ".join(why_chain)

# РЕЗУЛЬТАТ: Дві незалежні реалізації в одному файлі!
# Потрібно консолідувати в utils або використати append_why()
```

### ✅ КАК ФІКСИТИ ДУБЛЮВАННЯ:

```python
# Варіант 1: Використовувати vfoundation/obs/why.py::append_why
from vfoundation.obs.why import append_why

def _calculate_position_size(self, ...):
    why_chain = []
    why_chain = append_why(why_chain, f"pos_size_usd={final_pos_size_usd}")
    return rounded_qty, ", ".join(why_chain)

# Варіант 2: Створити utils функцію в decision_making
def _build_why_chain(*reasons: str) -> str:
    """Centralized why_chain builder"""
    return ", ".join(r for r in reasons if r)
```

---

## 🏁 FINAL AUDIT РЕЗУЛЬТАТИ

**Дата:** 2 листопада 2025
**Статус:** ✅ COMPLETED (аудит готовий)

### Дійсні Проблеми:

| Проблема | Статус | Impact | Fixes |
|----------|--------|--------|-------|
| **RID без GC** | 🔴 CRITICAL | WAL rosa ∞ | P0: cleanup_old_wals() |
| **WHY Duplicate** | 🟡 MEDIUM | Code duplication | P1: Consolidate to append_why |
| **WHY not global** | 🟡 MEDIUM | Only decision_making | P0: Propagate to all domains |
| **append_why dead** | 🟡 MEDIUM | Dead code in repo | P1: Remove or integrate |
| **No routing YAML** | 🟡 MEDIUM | No explicit contracts | P0: Create dictionaries/ |
| **No schema validation** | 🟡 MEDIUM | Runtime errors | P1: Add pld schema |

### Перевірено ✅:

- ✅ WHY chain EXISTS (локально в decision_making)
- ✅ Дублювання identifie (2 місця в 1 файлі)
- ✅ append_why = dead code (не імпортується нігде)
- ✅ RID GC відсутня (grep не знайшов cleanup)
- ✅ Routing YAML не існує (dictionaries/ folder missing)

---

**Документ підготовлено:** 2 листопада 2025
```
**Версія:** 1.0
**Статус:** FINAL - Об'єктивна оцінка на основі кодової бази
