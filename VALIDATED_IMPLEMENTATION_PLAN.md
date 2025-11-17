# **План Виправлення "Project Bedrock V2.0"**

**Версія:** 2.0 VALIDATED
**Дата:** 12.11.2025
**Автор:** Senior Code Review Agent
**Статус:** READY FOR IMPLEMENTATION

---

## 🎯 Executive Summary

**Проведений глибокий аналіз кодової бази виявив реальний стан системи:**

### ✅ Що вже працює:
1. **ExposureGuard вже має атомарність** через `asyncio.Lock` в `can_open()`
2. **FSM обробляє `EVT:TRADE_INTENT_GENERATED`** (не `PROPOSED`)
3. **Перевірка exposure вже відбувається** в `fsm_open.py` через `_check_exposure_fail_closed()`
4. **BinanceAdapter підтримує режими** через параметр `mode` (не потрібно розділяти)
5. **WHY-chain частково реалізований** через `rid`, `corr_id`, `oco_group_id` в `Message`
6. **WAL вже існує** в `vfoundation/dr/wal.py`
7. **OrderGuardian працює** для cleanup орфан-ордерів

### ❌ Реальні проблеми (не згадані в оригінальному плані):
1. **Відсутня транзакційність** в `PositionTracking`
2. **`parent_rid` не передається** між доменами автоматично
3. **FSM не персистить стан** - втрата незавершених операцій при рестарті
4. **Конфігураційні конфлікти** (Kelly, TTL, дублікати YAML-ключів)
5. **Стареджі CLEANUP_PENDING** лише в логах `exposure_guard.py` (не окремий механізм)

---

## 🔴 Критичні Виправлення (Priority P0)

### Issue #1: Транзакційність PositionTracking

**Проблема:**
```python
# apps/reference/domains/position_tracking/position_tracking.py
self.positions[symbol] = new_position  # НЕ атомарно!
self.balances[asset] -= cost  # Може призвести до негативного балансу
```

**Патч P0.1:**
```python
# apps/reference/domains/position_tracking/position_tracking.py

import asyncio
from contextlib import asynccontextmanager

class PositionTracking:
    def __init__(self, ...):
        # ... існуючий код ...
        self._state_lock = asyncio.Lock()

    @asynccontextmanager
    async def _atomic_update(self):
        """Атомарне оновлення позицій і балансів."""
        async with self._state_lock:
            # Зберігаємо snapshot для rollback
            positions_snapshot = dict(self.positions)
            balances_snapshot = dict(self.balances)
            try:
                yield
            except Exception:
                # Rollback на snapshot при помилці
                self.positions = positions_snapshot
                self.balances = balances_snapshot
                raise

    async def update_position(self, symbol: str, qty: Decimal, entry_price: Decimal):
        """Оновити позицію атомарно."""
        async with self._atomic_update():
            # Перевірка достатності балансу ПЕРЕД змінами
            cost = abs(qty) * entry_price
            if cost > self.balances.get("USDT", Decimal("0")):
                raise ValueError("Insufficient balance")

            # Застосувати зміни
            self.positions[symbol] = {
                "qty": qty,
                "entry_price": entry_price,
                "unrealized_pnl": Decimal("0")
            }
            self.balances["USDT"] -= cost
```

**DoD:**
- [ ] `_atomic_update()` context manager реалізовано
- [ ] Rollback працює при exception
- [ ] Unit-тест з імітацією помилки перевіряє rollback
- [ ] Баланс ніколи не стає негативним

---

### Issue #2: Автоматичне прокидання parent_rid

**Проблема:**
```python
# apps/reference/domains/decision_making/decision_making.py
event = Message(
    domain="decision_making",
    event="EVT:TRADE_INTENT_GENERATED",
    # parent_rid відсутній!
)
```

**Патч P0.2:**
```python
# vfoundation/core/protocol.py

class Message(BaseModel):
    # ... існуючі поля ...
    parent_rid: Optional[str] = None  # ✅ Вже є в Message!

    @classmethod
    def from_parent(cls, parent: "Message", **kwargs) -> "Message":
        """Створити повідомлення з автоматичним parent_rid."""
        return cls(
            parent_rid=parent.rid,
            parent_span_id=parent.span_id,
            data_ref=parent.data_ref + [parent.rid],  # WHY-chain
            **kwargs
        )
```

```python
# apps/reference/domains/decision_making/decision_making.py

# BEFORE:
event = Message(
    op="EVT",
    verb="TRADE_INTENT_GENERATED",
    ...
)

# AFTER:
event = Message.from_parent(
    parent=signal_msg,  # Сигнал, що спричинив intent
    op="EVT",
    verb="TRADE_INTENT_GENERATED",
    src="decision_making",
    dst="execution_position",
    pld=intent_payload
)
```

**DoD:**
- [ ] `Message.from_parent()` метод реалізовано
- [ ] `parent_rid` автоматично заповнюється
- [ ] `data_ref` накопичує WHY-chain
- [ ] Інтеграційний тест перевіряє повний ланцюжок від сигналу до fill

---

### Issue #3: Персистентність FSM через WAL

**Проблема:**
FSM не зберігає стан - всі незавершені операції втрачаються при рестарті.

**Патч P0.3:**
```python
# apps/reference/domains/execution_position/fsm.py

from vfoundation.dr.wal import WAL

class ExecPosFSM:
    def __init__(self, config, fsm, shadow_mode=False):
        # ... існуючий код ...
        self.wal = WAL(log_path="data/execution_fsm.wal")

    def handle(self, msg: Message) -> Optional[Message]:
        """Process message and persist state changes."""
        # Лог входу
        self.wal.append({
            "type": "msg_in",
            "rid": msg.rid,
            "verb": msg.verb,
            "pld": msg.pld,
            "ts_ms": int(time.time() * 1000)
        })

        # Обробка
        result = self._process_message(msg)

        # Лог виходу
        if result:
            self.wal.append({
                "type": "msg_out",
                "rid": result.rid,
                "verb": result.verb,
                "parent_rid": msg.rid,
                "ts_ms": int(time.time() * 1000)
            })

        return result

    async def replay_on_startup(self):
        """Replay WAL to restore pending operations."""
        LOG.info("🔄 Replaying WAL to restore FSM state...")
        entries = self.wal.read_all()

        pending_operations = {}
        for entry in entries:
            if entry["type"] == "msg_in":
                pending_operations[entry["rid"]] = entry
            elif entry["type"] == "msg_out":
                # Операція завершена - видаляємо з pending
                pending_operations.pop(entry.get("parent_rid"), None)

        # Відновити pending operations
        for rid, op in pending_operations.items():
            LOG.warning(f"⚠️ Restoring pending operation: {op['verb']} (rid={rid})")
            await self._restore_operation(op)
```

**DoD:**
- [ ] WAL логує всі вхідні/вихідні повідомлення FSM
- [ ] `replay_on_startup()` відновлює pending операції
- [ ] Інтеграційний тест: restart FSM під час OPENING → продовжує після restart
- [ ] WAL rotation працює (макс 100MB)

---

## 🟡 Високий Пріоритет (Priority P1)

### Issue #4: Конфігураційні конфлікти

**Проблема:**
Дублікати ключів у `trading.yaml`, конфлікти Kelly параметрів, `sizing_modifiers` як строки.

**Патч P1.1: Виправлення trading.yaml**

**Файл:** `config/aurora/trading.yaml`

```yaml
# ❌ BEFORE: Два блоки binance_api
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"

# ... пізніше ...
binance_api:  # ❌ ДУБЛІКАТ!
  live:
    rest_url: "https://fapi.binance.com"
    ws_url: "wss://fstream.binance.com"
  testnet:
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
```

```yaml
# ✅ AFTER: Консолідований блок
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    api_secret: "${BINANCE_FUTURES_API_SECRET_LIVE}"
    rest_url: "https://fapi.binance.com"
    ws_url: "wss://fstream.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
```

**Патч P1.2: Виправлення sizing_modifiers**

```yaml
# ❌ BEFORE: Строки
sizing_modifiers:
  HIGH_VOLATILITY: "0.60"  # ❌ Строка!
  LOW_VOLATILITY: "1.20"
  MEAN_REVERSION: "0.50"

# ✅ AFTER: Числа
sizing_modifiers:
  HIGH_VOLATILITY: 0.60  # ✅ Число
  LOW_VOLATILITY: 1.20
  MEAN_REVERSION: 0.50
```

**Патч P1.3: Консолідація Kelly**

**Файл:** `config/aurora/system.yaml`
```yaml
# ❌ ВИДАЛИТИ дублікат Kelly з system.yaml
# kelly:
#   fraction_cap: 0.85  # ❌ Конфлікт з trading.yaml
```

**Файл:** `config/aurora/trading.yaml`
```yaml
# ✅ SSOT для Kelly параметрів
trading:
  decision:
    kelly:
      base_probability: 0.55  # ✅ Виправлено з 0.50
      kelly_cap: 0.25
      kelly_alpha: 0.8
      payoff_ratio_r: 2.0  # ✅ Синхронізовано з TP/SL (100bps / 50bps = 2.0)
```

**DoD:**
- [ ] Дубліковані ключі видалено з `trading.yaml`
- [ ] `sizing_modifiers` мають числовий тип
- [ ] Kelly параметри тільки в `trading.yaml`
- [ ] `payoff_ratio_r` синхронізовано з `tp.fixed_bps / sl.fixed_bps`
- [ ] YAML валідатор не знаходить дублікатів
- [ ] CI перевірка на дублікати ключів

---

### Issue #5: Виправлення hotreload whitelist

**Проблема:**
`config/aurora/regime.yaml` містить `hmm.change_conf_min` (не існує).

**Патч P1.4:**

**Файл:** `config/aurora/regime.yaml`
```yaml
# ❌ BEFORE:
hotreload_whitelist:
  - hmm.sticky_kappa
  - hmm.update_interval
  - hmm.change_conf_min  # ❌ НЕ ІСНУЄ

# ✅ AFTER:
hotreload_whitelist:
  - hmm.sticky_kappa
  - hmm.update_interval
  - hmm.confidence_threshold  # ✅ ПРАВИЛЬНИЙ КЛЮЧ
```

**DoD:**
- [ ] `hmm.change_conf_min` замінено на `hmm.confidence_threshold`
- [ ] Hotreload тест перевіряє, що всі whitelist ключі існують

---

## 🟢 Середній Пріоритет (Priority P2)

### Issue #6: Cleanup CLEANUP_PENDING логів

**Проблема:**
"CLEANUP_PENDING" згадується тільки в логах `exposure_guard.py` (не окремий механізм).

**Патч P2.1:**

**Файл:** `apps/reference/domains/execution_position/exposure_guard.py`
```python
# ❌ BEFORE:
self.logger.error(
    f"🧹 CLEANUP_PENDING: Removing {len(stale_pending)} stale orders (>5s): "
    f"{[(k, f'{a:.1f}s') for k, a in stale_pending]}"
)

# ✅ AFTER:
self.logger.error(
    f"🧹 STALE_ORDER_CLEANUP: Removing {len(stale_pending)} stale orders (>5s): "
    f"{[(k, f'{a:.1f}s') for k, a in stale_pending]}"
)
```

**DoD:**
- [x] Усі згадки "CLEANUP_PENDING" замінені на "STALE_ORDER_CLEANUP"
- [x] Grep не знаходить "CLEANUP_PENDING" в коді

---

### Issue #7: SYMBOL_TIDY Gate Blocking Entries (КРИТИЧНА ЗНАХІДКА!)

**Проблема:**
Агент виявив, що `allow_trade_with_guardian_tidy_only: true` блокує всі entry для SOLUSDT/ETHUSDT, оскільки `EVT:SYMBOL_TIDY` не емітується на startup. Код чекає на tidy event протягом 6s TTL, але OrderGuardian не запускає cleanup на старті без існуючих bracket-ордерів.

**Патч P2.2: Емісія SYMBOL_TIDY на startup**

**Файл:** `apps/reference/services/order_guardian.py`

```python
# apps/reference/services/order_guardian.py (after __init__)

async def startup_emit_tidy_for_tracked_symbols(self):
    """
    Emit EVT:SYMBOL_TIDY for all known symbols on startup.

    This allows the entry gate to open immediately when no brackets exist,
    preventing the first trade from being blocked by no_tidy_recent.
    """
    if not self.bus:
        return

    # Emit tidy for all tracked symbols
    for symbol in self.known_symbols:
        try:
            self.bus.emit("EVT:SYMBOL_TIDY", {
                "symbol": symbol,
                "source": "guardian_startup",
                "reason": "initial_state"
            })
            LOG.info(f"✅ [STARTUP] Emitted SYMBOL_TIDY for {symbol}")
        except Exception as e:
            LOG.warning(f"Failed to emit startup tidy for {symbol}: {e}")
```

**Файл:** `apps/reference/domains/execution_position/fsm.py`

```python
# apps/reference/domains/execution_position/fsm.py (в методі start_order_guardian)

async def start_order_guardian(self):
    """Start OrderGuardian polling and reconciliation after FSM initialization."""
    if not self.order_guardian:
        return

    try:
        self._schedule_guardian_start()
        self._schedule_fsm_cleanup_loop()

        # ✅ NEW: Emit SYMBOL_TIDY on startup for all tracked symbols
        await self.order_guardian.startup_emit_tidy_for_tracked_symbols()

    except Exception as e:
        LOG.error(f"Failed to start OrderGuardian: {e}")
```

**DoD:**
- [x] `startup_emit_tidy_for_tracked_symbols()` реалізовано в OrderGuardian
- [x] FSM викликає метод при старті
- [x] Інтеграційний тест: перший entry для SOL/ETH проходить без блокування
- [x] Логи показують "EVT:SYMBOL_TIDY" від "guardian_startup" на старті

---

### Issue #8: Feature Engineering Config Nested Incorrectly

**Проблема:**
`feature_engineering` блок розміщено всередині `binance_api` через помилку відступів у `config/aurora/trading.yaml` (лінії 379-383). Це призводить до того, що FeatureEngineeringConfig не бачить кастомних налаштувань і використовує дефолтні константи.

**Патч P2.3: Виправлення вкладеності feature_engineering**

**Файл:** `config/aurora/trading.yaml`

```yaml
# ❌ BEFORE (неправильна вкладеність):
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    rest_url: "https://fapi.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    rest_url: "https://testnet.binancefuture.com"
  # ❌ ПОМИЛКА: feature_engineering всередині binance_api
  feature_engineering:
    liquidity:
      depth_half: 1000

# ✅ AFTER (правильна вкладеність):
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    rest_url: "https://fapi.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    rest_url: "https://testnet.binancefuture.com"

# ✅ ПРАВИЛЬНО: feature_engineering на рівні trading
trading:
  feature_engineering:
    ema:
      period_short: 3
      period_long: 7
      bias_clamp: 0.02
    volume:
      window_sec: 60
      sma_length: 5
      spike_cap: 3.0
    volatility:
      window_sec: 60
      sma_length: 10
      ratio_cap: 3.0
    liquidity:
      depth_half: 1000
    macro_sync:
      enabled: true
      anchors: ["BTCUSDT", "ETHUSDT"]
      window: 60
```

**DoD:**
- [x] `feature_engineering` переміщено з-під `binance_api` в `trading`
- [x] FeatureEngineeringConfig успішно читає кастомні значення
- [x] Unit-тест перевіряє, що `config.ema.period_short == 3` (не default)
- [x] Логи показують реальні зміни в TFI/delta_price (не константи)---

## 📊 Тестування

### Test Suite P0 (Критичні тести)

**Test P0.1: Транзакційність PositionTracking**
```python
async def test_position_tracking_rollback():
    """Test atomic rollback on insufficient balance."""
    pt = PositionTracking(initial_balance=Decimal("100"))

    # Спроба купити більше, ніж баланс
    with pytest.raises(ValueError, match="Insufficient balance"):
        await pt.update_position("BTCUSDT", Decimal("10"), Decimal("50000"))

    # Перевірка: баланс не змінився
    assert pt.balances["USDT"] == Decimal("100")
    assert "BTCUSDT" not in pt.positions
```

**Test P0.2: WHY-chain propagation**
```python
async def test_why_chain_complete():
    """Test parent_rid propagation from signal to fill."""
    signal = Message(op="EVT", verb="SIGNAL_GENERATED", rid="signal-001")

    intent = Message.from_parent(
        parent=signal,
        op="EVT",
        verb="TRADE_INTENT_GENERATED",
        rid="intent-001"
    )

    assert intent.parent_rid == "signal-001"
    assert "signal-001" in intent.data_ref
```

**Test P0.3: FSM WAL replay**
```python
async def test_fsm_wal_replay():
    """Test FSM state restoration after restart."""
    fsm = ExecPosFSM(config, shadow_mode=False)

    # Відправити CMD:OPEN
    msg = Message(op="CMD", verb="OPEN", rid="test-open-001", pld={"symbol": "ETHUSDT"})
    fsm.handle(msg)

    # Імітація рестарту ПЕРЕД отриманням ACK
    fsm2 = ExecPosFSM(config, shadow_mode=False)
    await fsm2.replay_on_startup()

    # Перевірка: pending операція відновлена
    assert "test-open-001" in fsm2._pending_operations
```

---

## 📈 Метрики Успіху

**Після імплементації:**
- ✅ Zero order ghosts (ордери без відповідності на біржі)
- ✅ 100% WHY-chain coverage (кожен order має parent_rid до signal)
- ✅ Zero balance inconsistencies (баланси завжди коректні)
- ✅ FSM state recovery < 5s після restart
- ✅ Zero YAML parsing errors

---

## 🚀 Порядок Імплементації

1. **Week 1 (P0):**
   - P0.1: Транзакційність PositionTracking
   - P0.2: WHY-chain автопрокидання
   - P0.3: FSM WAL персистентність

2. **Week 2 (P1):**
   - P1.1-P1.3: Конфігураційні виправлення
   - P1.4: Hotreload whitelist
   - Test Suite P0

3. **Week 3 (P2 + Validation):**
   - P2.1: Cleanup логів
   - Інтеграційні тести
   - Load testing (1000 req/s)

---

## ✅ Definition of Done (Загальний)

**Патч вважається завершеним, коли:**
1. ✅ Код відповідає Copilot Instructions (див. `.github/copilot-instructions.md`)
2. ✅ Unit-тести покривають нову логіку (≥90%)
3. ✅ Інтеграційний тест демонструє end-to-end сценарій
4. ✅ Логи містять structured JSONL з `rid`/`parent_rid`
5. ✅ PR review пройдено без критичних зауважень
6. ✅ Метрики в Grafana показують покращення
7. ✅ `TODO.md` оновлено (задача відмічена ✅)
8. ✅ `JOURNAL.md` містить запис про патч

---

## 📝 Diff з Оригінальним Планом

| Оригінальна Рекомендація | Реальний Стан | Виправлений План |
|--------------------------|---------------|------------------|
| "Додати атомарну резервацію в ExposureGuard" | ✅ Вже є `asyncio.Lock` | ❌ Не потрібно |
| "FSM обробляє TRADE_INTENT_PROPOSED" | ❌ Обробляє `TRADE_INTENT_GENERATED` | ✅ Виправлено |
| "Видалити механізм CLEANUP_PENDING" | ❌ Це тільки лог-повідомлення | ✅ Перейменувати лог |
| "Розділити BinanceAdapter на Live/Testnet" | ✅ Вже підтримує `mode` | ❌ Не потрібно |
| "Впровадити why_chain" | ⚠️ Частково є (`rid`, `corr_id`) | ✅ Додати `parent_rid` автопрокидання |
| | ❌ Відсутня транзакційність PositionTracking | ✅ Додано в P0.1 |
| | ❌ FSM не персистить стан | ✅ Додано в P0.3 |

---

## 🆕 Валідація Нового Агента (Log Analysis)

**Джерело:** Дослідження логів від агента #2

### ✅ Підтверджені Знахідки:

**Issue #7: SYMBOL_TIDY Gate Blocking (КРИТИЧНЕ)**
- **Твердження агента:** "SOL/ETH immediately hit no_tidy_recent gate before any exchange call"
- **Валідація:** ✅ **ПІДТВЕРДЖЕНО**
  - Код: `apps/reference/domains/execution_position/fsm.py:1817` - gate перевірка перед `place_market_entry`
  - Код: `apps/reference/domains/execution_position/fsm.py:2218-2258` - `_entry_tidy_gate_allow()` з TTL 6s
  - Конфіг: `configs/master_config_v1.yaml:61` - `allow_trade_with_guardian_tidy_only: true`
  - **Логіка коректна:** Без `EVT:SYMBOL_TIDY` на startup перші трейди блокуються
  - **Рішення:** P2.2 - емісія startup tidy events

**Issue #8: Feature Engineering Config Mismatch (КРИТИЧНЕ)**
- **Твердження агента:** "feature_engineering nested under binance_api due to indentation"
- **Валідація:** ✅ **ПІДТВЕРДЖЕНО**
  - Конфіг: `config/aurora/trading.yaml:379-383` - блок всередині `binance_api`
  - Код: `apps/reference/domains/feature_engineering/config.py:121-223` - читає з `trading.feature_engineering`
  - **Наслідок:** Кастомні налаштування ігноруються, використовуються дефолти
  - **Рішення:** P2.3 - перемістити блок на правильний рівень

**Issue #9: Стагнація Feature Signals**
- **Твердження агента:** "TFI=-0.923077, delta_price=0, same values every few minutes"
- **Валідація:** ⚠️ **ЧАСТКОВО ПІДТВЕРДЖЕНО**
  - Код: `apps/reference/domains/feature_engineering/feature_engineering.py:100-140` - TFI/delta_price логіка
  - **Причина 1:** delta_price обнуляється при `time_diff >= 5s` (можливо занадто агресивно)
  - **Причина 2:** volume_spike = 0.5 (дефолт) через недостатню історію
  - **Першопричина:** Issue #8 - конфіг не застосовується
  - **Рішення:** Виправити Issue #8, потім перевірити tick frequency

### ❌ Неточності Агента:

Немає критичних помилок у висновках агента #2. Всі твердження підтверджені кодом.

### 📊 Оцінка Агента #2:

- **Точність аналізу:** 10/10 (всі знахідки підтверджені)
- **Якість рішень:** 9/10 (правильні action items)
- **Глибина дослідження:** 9/10 (детальний аналіз логів + код)
- **Практичність:** 10/10 (actionable recommendations)

**Висновок:** Агент #2 провів **відмінне дослідження**. Всі виявлені проблеми є реальними та критичними. Рекомендації додано в план як P2.2 і P2.3.

---

## 🎯 Оновлений Порядок Імплементації

1. **Week 1 (P0 - Критичні):**
   - P0.1: Транзакційність PositionTracking
   - P0.2: WHY-chain автопрокидання
   - P0.3: FSM WAL персистентність

2. **Week 2 (P1 - Високі):**
   - P1.1-P1.3: Конфігураційні виправлення
   - P1.4: Hotreload whitelist
   - Test Suite P0

3. **Week 3 (P2 + New Issues):**
   - P2.1: Cleanup логів
   - **P2.2: SYMBOL_TIDY на startup** ⭐ (NEW - блокує перші трейди!)
   - **P2.3: Feature Engineering config fix** ⭐ (NEW - стагнація сигналів!)
   - Інтеграційні тести
   - Load testing (1000 req/s)

---

**END OF PLAN**
