# vFoundation Engineering Blueprint — Phase 14.2: FSMv2 Enhancement + Domain Migration

**Дата:** 2026-02-24 (rev. 2026-02-24)
**Статус:** Draft (Ready for Execution)
**Ціль:** Розширити існуючий `FSMv2` двигун (342 LOC, `vfoundation/core/fsm_v2.py`) відсутніми можливостями (deadlock-валідація, graph export, WAL-інтеграція, transactional rollback) та провести міграцію доменних станів на його API.

> **УВАГА (rev. 2026-02-24):** Оригінальна версія цього документу пропонувала створення нового `FormalFSM` в `vfoundation/core/state_machine.py`. Це **невірно**: FSMv2 вже реалізує повний формалізм KA. Документ переписаний на "Enhancement + Migration" підхід.

---

## 1. Проблема та Обґрунтування (The Why)

Аукціонні та торговельні системи оперують станами, які змінюють один одного в жорстко визначеному порядку.

### 1.1 Існуючі шари FSM у vFoundation

| Шар | Файл | LOC | Роль |
|-----|-------|-----|------|
| **FSMCore** | `vfoundation/core/fsm_core.py` | 123 | Event Bus (Pub/Sub): `listen()`, `emit()`, RID passthrough |
| **FSMv2** | `vfoundation/core/fsm_v2.py` | 342 | **Formal FSM**: `TransitionRule`, `StateInfo`, guards, per-key state, snapshot/restore |
| **MetaFSMv2** | `vfoundation/core/meta_fsm_v2.py` | 265 | Cross-domain coordinator: NORMAL/LOW_RISK/COOLDOWN/DEGRADED |

### 1.2 Що FSMv2 вже реалізує (не дублюємо!)

FSMv2 (`vfoundation/core/fsm_v2.py`) вже містить:

```python
@dataclass
class TransitionRule:
    from_state: str
    event: str
    to_state: str
    guard: Optional[Callable[["Message"], bool]] = None
    action: Optional[Callable[["Message"], None]] = None

@dataclass
class StateInfo:
    name: str
    terminal: bool = False
    on_enter: Optional[Callable] = None
    on_exit: Optional[Callable] = None
```

**Повний перелік можливостей FSMv2:**
- `register_state(info: StateInfo)` — реєстрація стану з on_enter/on_exit callbacks
- `register_transition(rule: TransitionRule)` — реєстрація переходу з guard + action
- `handle(key: str, msg: Message) -> str` — per-key state machine dispatch (напр. key = symbol)
- `get_state(key) / set_state(key, state)` — прямий доступ до стану
- `tracked_keys()` — список відстежуваних ключів
- `get_transition_table()` — повна матриця переходів
- `get_registered_states()` — список зареєстрованих станів
- `snapshot() / restore(snap)` — серіалізація/відновлення для DR
- `_FSMv2Metrics` — transitions, rejected, guard_rejected, errors
- Thread-safe (`RLock`), fail-closed (`ERR:NO_TRANSITION`)
- Constitution v2.2 limits: `MAX_STATES=20`, `MAX_VERBS=12`

### 1.3 Чого FSMv2 НЕ має (scope цього Blueprint)

1. **Deadlock/Reachability Validator:** Немає автоматичної перевірки матриці переходів на досяжність всіх станів, тупикові стани, та нескінченні цикли.
2. **Graph Export (Mermaid/PlantUML):** Немає CLI-команди для візуалізації переходів.
3. **WAL Integration:** Зміни стану не записуються в WAL як `EVT:STATE_TRANSITION`.
4. **Transactional Rollback:** Якщо `action` кидає Exception, стан може залишитись inconsistent.
5. **Domain Migration:** Жоден домен (`execution_position`, `decision_making`) ще не використовує FSMv2 для свого lifecycle.

### 1.4 Проблема Event Bus (FSMCore) — залишається актуальною

**Чому Event Bus недостатньо для algotrading-системи?**
1. **State Blindness:** Компоненти через FSMCore просто слухають події. Коли `decision_making` отримує `EVT:STRATEGY_SIGNAL`, він не знає глобального "стану" символу.
2. **Непередбачувані Side-Effects:** Будь-хто може зробити `fsm.emit(...)` в будь-який момент. Немає матриці переходів.
3. **Неможливість Формальної Верифікації:** Через FSMCore неможливо перевірити досяжність всіх станів.

> **Рішення:** Домени мають мігрувати з ad-hoc IF-перевірок на FSMv2 `handle(key, msg)`.

---

## 2. Архітектурне Рішення: Enhancement FSMv2

**НЕ створюємо новий клас.** Розширюємо існуючий `FSMv2` в `vfoundation/core/fsm_v2.py`.

### 2.1 Deadlock/Reachability Validator

Додати метод `validate_topology() -> ValidationReport`:

```python
@dataclass
class ValidationReport:
    unreachable_states: list[str]     # Стани, до яких неможливо дістатись з initial
    deadlock_states: list[str]        # Non-terminal стани без вихідних переходів
    cycles: list[list[str]]           # Виявлені цикли (інформаційно, не помилка)
    is_valid: bool                    # True якщо немає unreachable + deadlock
```

- Реалізація через BFS/DFS по графу переходів `get_transition_table()`.
- Викликається автоматично при `register_transition()` якщо `validate_on_register=True`.
- CLI: `vfound fsm validate <fsm-name>`.

### 2.2 Graph Export (Mermaid/PlantUML)

Додати метод `export_graph(format: str = "mermaid") -> str`:

```python
def export_graph(self, format: str = "mermaid") -> str:
    """Генерує Mermaid stateDiagram-v2 або PlantUML з transition table."""
    # Використовує get_transition_table() + get_registered_states()
```

- CLI: `vfound fsm graph <fsm-name> --format mermaid > diagram.md`
- Тести: порівняти output з golden snapshot.

### 2.3 WAL Integration

Після кожного успішного переходу у `handle()`:
```python
wal.write(EVT:STATE_TRANSITION, payload={
    "fsm_name": self.name,
    "key": key,
    "before": old_state,
    "after": new_state,
    "trigger": msg.verb,
    "rid": msg.rid,
    "ts": monotonic_ns()
})
```

- WAL writer передається через `__init__` як optional dependency.
- Replay: `restore()` з WAL записів для DR recovery.

### 2.4 Transactional Action Rollback

У поточному `handle()` стан змінюється ДО виклику action. Потрібно:
```python
# BEFORE (current):
self._states[key] = rule.to_state  # стан змінений
rule.action(msg)                    # якщо впаде — стан вже змінений!

# AFTER (fix):
old_state = self._states[key]
try:
    self._states[key] = rule.to_state
    if rule.action:
        rule.action(msg)
except Exception:
    self._states[key] = old_state   # rollback
    self._metrics.errors += 1
    raise
```

---

## 3. Domain Migration Roadmap

### 3.1 Підключення FSMv2 до FSMCore (Bridge Pattern)

Щоб домени могли мігрувати поступово, створюємо bridge:
- Коли `FSMCore` отримує `emit("EVT:STRATEGY_SIGNAL")`, він **також** передає `Message` до зареєстрованих `FSMv2` через `handle(key, msg)`.
- FSMv2 перевіряє `current_state[key]`, знаходить `TransitionRule`, виконує guard/action.
- Домени, які ще не мігрували, продовжують використовувати `listen/emit` як раніше.

### 3.2 Міграція `execution_position` (Refactoring Phase)

*На цьому етапі домени вже повинні бути декомпоновані (згідно з Blueprint 14.1).*

1. У домені `execution_position` явно визначити стани через FSMv2:
   - `INIT` (Пошук позиції на біржі / Bootstrap)
   - `FLAT` (Немає позиції, немає ордерів)
   - `ENTRY_PENDING` (Очікування виконання ордера на відкриття)
   - `POSITION_OPEN` (Позиція відкрита)
   - `EXIT_PENDING` (Очікування закриття)
   - `COOLDOWN` (Одразу після закриття — блокування нових ордерів)
2. Перевести `ep_orchestrator.py` на використання `FSMv2.handle(symbol, msg)`. Замість ручного трекінгу `self._pending_orders`, FSMv2 контролюватиме стан кожного символу.
3. Guards використовуватимуть існуючий `AlertManager`. Наприклад: Guard *CanOpenPosition* перевіряє, чи не відкритий Circuit Breaker.

### 3.3 Міграція `decision_making` (Refactoring Phase)

1. Створити FSMv2 instance для потоку ухвалення рішень (Signal Lifecycle):
   - Стани: `IDLE`, `EVALUATING`, `QOS_THROTTLED`, `ACCEPTED`, `REJECTED`.
2. Заміна гігантського методу `_on_strategy_signal_gateway` на набір дрібних, тестуємих TransitionRule actions.

---

## 4. Execution Plan

### Етап 1: FSMv2 Enhancements (1 тиждень)

> **Не створюємо новий файл.** Всі зміни в `vfoundation/core/fsm_v2.py` + нові тести.

1. Додати `validate_topology() -> ValidationReport` (deadlock/reachability).
2. Додати `export_graph(format="mermaid") -> str` (graph visualization).
3. Виправити `handle()` на transactional rollback (§2.4).
4. Додати optional WAL writer інтеграцію (§2.3).
5. Розширити тести у `tests/vfoundation/core/test_fsm_v2.py`: +15 тестів для нових можливостей.
6. *Gate: ≥716 passed, 0 failed.*

### Етап 2: FSMCore ↔ FSMv2 Bridge (3 дні)

1. Реалізувати bridge pattern (§3.1) — FSMCore.emit() може делегувати до FSMv2.
2. CLI команди: `vfound fsm validate`, `vfound fsm graph`.
3. *Gate: ≥716 passed, CLI smoke test.*

### Етап 3: Domain Migration — execution_position (1 тиждень)

*Залежність: Blueprint 14.1 (Decomposition) етапи 1-3 виконані.*
1. Визначити стани EP (§3.2).
2. Перевести ep_orchestrator на FSMv2.handle().
3. *Gate: ≥716 passed, нуль ad-hoc `if self._state ==` в EP коді.*

### Етап 4: Domain Migration — decision_making (1 тиждень)

*Залежність: Blueprint 14.1 (Decomposition) етапи 1-2 виконані.*
1. Визначити стани DM (§3.3).
2. Перевести signal lifecycle на FSMv2.
3. *Gate: ≥716 passed.*

---

## 5. Переваги та Гарантії (The Payoffs)

1. **Bug Elimination за дизайном:** Система *фізично* не зможе відправити на біржу другий `OPEN_POSITION` для символа, який вже знаходиться в стані `ENTRY_PENDING`. Цей клас багів знищується архітектурою FSMv2 (fail-closed: `ERR:NO_TRANSITION`).
2. **"Compile Time" Error Detection:** Команда `vfound fsm validate` прочитає transition table і скаже: *"У тебе стан EXIT_PENDING не має переходу до FLAT у випадку помилки API (TIMEOUT)"*.
3. **Traceability:** У WAL ви будете бачити чіткий математичний ланцюг: `FLAT` → `EVT:TRADE_INTENT_PROPOSED` → `ENTRY_PENDING` → `DEC:FILL_RECEIVED` → `POSITION_OPEN`. Ідеально для LLM Agents Data Extraction і аудиту.
4. **Zero Code Duplication:** Жодного нового FSM-класу — тільки enhancement існуючого FSMv2 (342 LOC → ~500 LOC після розширень).
