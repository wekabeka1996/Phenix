# 🏗️ ARCHITECTURAL DECISIONS & DESIGN PATTERNS FOR PHENIX EVOLUTION

**Дата**: 2 листопада 2025
**Мета**: Формалізовані рішення щодо розвитку архітектури
**Адресат**: Solo developer, 9 місяців на проекті

---

## 📋 ЗМІСТ

1. [Ключові архітектурні рішення](#1-ключові-архітектурні-рішення)
2. [Design Patterns](#2-design-patterns-for-scalability)
3. [Data Flow Architecture](#3-data-flow-architecture)
4. [Testing Strategy](#4-testing-strategy)
5. [Deployment & Rollout](#5-deployment--rollout)

---

## 1. КЛЮЧОВІ АРХІТЕКТУРНІ РІШЕННЯ

### 1.1 RID Lifecycle: Centralized vs Distributed

**Рішення**: 🎯 **CENTRALIZED** (OrchestratorFSM)

#### Обґрунтування:

| Аспект | Centralized (OrchestratorFSM) | Distributed (per-domain) |
|--------|-----|----------|
| **WHY chain** | Preserved (append, not join) | Lost (each domain JOINs locally) |
| **Signing** | Single point (OrchestratorFSM) | Per-domain (inconsistent) |
| **TTL GC** | Atomic cleanup | Coordinated hard |
| **Debugging** | `/debug/{rid}` shows full trace | Need to grep WAL |
| **Complexity** | +1 FSM, but clear | Distributed coordination |

**Архітектура**:
```
┌─────────────────────────────────┐
│    OrchestratorFSM (TRADE)      │ ← Central coordinator
│  - RID lifecycle tracking       │
│  - WHY chain accumulation       │
│  - Ed25519 signing              │
│  - TTL enforcement              │
└────────┬────────────────────────┘
         │
    ┌────┴─────────────────────────────┐
    ▼                                   ▼
┌──────────────┐              ┌────────────────┐
│FeatureEng    │              │ Risk Manager   │
│(COLD path)   │              │(DECISION)      │
└──────────────┘              └────────────────┘
    │ EVT:FEATURES_CALCULATED      │ EVT:RISK_APPROVED
    │                              │
    └──────────────┬───────────────┘
                   ▼
            ┌──────────────────┐
            │ Decision Making  │
            │ (TRADE intent)   │
            └────────┬─────────┘
                     │ TRADE_INTENT_PROPOSED
                     ▼
            ┌──────────────────────┐
            │ OrchestratorFSM      │
            │ (OPEN phase)         │
            │ - Validate           │
            │ - Sign (ED25519)     │
            │ - Emit CMD:OPEN      │
            └────────┬─────────────┘
                     │
                     ▼
            ┌──────────────────┐
            │Execution Position│
            │(order submit)    │
            └──────────────────┘
```

**Реалізація**:
```python
# apps/reference/orchestrator/orchestrator_fsm.py
class OrchestratorFSM:
    def __init__(self, fsm_core, config):
        self.rid_db = {}  # { rid: RIDLifecycle }
        self.ttl_manager = TTLManager(config)
        self.signer = Ed25519Signer(os.getenv('PRIVATE_KEY'))

    def on_trade_intent(self, intent: Message) -> None:
        """EVAL phase."""
        rid = intent.rid
        self.rid_db[rid] = RIDLifecycle(
            state='EVAL',
            domain_chain=['decision_making'],
            why_chain=[intent.why or 'unknown'],
            ttl=self.ttl_manager.compute_ttl(intent.pld)
        )
        self.logger.info(f"Registered RID {rid} in EVAL phase")

    def on_order_exec(self, cmd: Message) -> None:
        """OPEN phase: Sign before emission."""
        rid = cmd.rid
        lifecycle = self.rid_db.get(rid)
        if not lifecycle:
            self.logger.error(f"Unknown RID {rid}")
            return

        # Sign the command
        sig = self.signer.sign_ed25519(cmd.pld)
        cmd.sig = sig
        cmd.data_ref = lifecycle.why_chain

        # Emit with signature
        self.fsm.emit('CMD:OPEN', cmd)

        # Update lifecycle
        lifecycle.state = 'OPEN'
        lifecycle.domain_chain.append('execution_position')
        lifecycle.why_chain.append(cmd.why)

    def get_rid_trace(self, rid: str) -> dict:
        """Debug endpoint: Full RID lifecycle."""
        lifecycle = self.rid_db.get(rid)
        if not lifecycle:
            return {'error': 'RID not found'}

        return {
            'rid': rid,
            'state': lifecycle.state,
            'domain_chain': lifecycle.domain_chain,
            'why_chain': lifecycle.why_chain,
            'ts_started': lifecycle.ts_started,
            'duration_ms': (time.time() - lifecycle.ts_started) * 1000,
        }
```

**Переваги**:
- ✅ WHY chain не втрачається
- ✅ Підпис на критичних командах
- ✅ Єдина точка для TTL enforcement
- ✅ Простий debug via `/debug/{rid}`

---

### 1.2 WHY Chain: Local vs Centralized

**Рішення**: 🎯 **CENTRALIZED** (OrchestratorFSM + data_ref field)

#### Поточна проблема:
```python
# Decision making (local, line 497)
why_chain = []
why_chain.append(why_sizing)
message = Message(..., why=", ".join(why_chain))  # ← JOIN destroys structure
# Result: Single string "signal 0.65, risk approved"

# Main.py (line 410)
event_why_chain = intent_msg.pld.get("why", [])  # ← Expects list, gets string
bridge_why = event_why_chain[0] if event_why_chain else "..."  # ← Takes [0], rest lost
```

#### Рішення:
```python
# Message protocol (already has data_ref field!)
class Message(BaseModel):
    why: Optional[str] = None  # Single reason (max 80 chars)
    data_ref: List[str] = Field(default_factory=list)  # ← Full chain!

# OrchestratorFSM populates data_ref
cmd = Message(
    op="CMD",
    verb="OPEN",
    why="Order filled at 30000",  # Current action
    data_ref=lifecycle.why_chain  # Full history: [...previous reasons...]
)
```

**Переваги**:
- ✅ Структура відповідь моментально
- ✅ Повна історія доступна в `data_ref`
- ✅ Одноразова `why` для лога (max 80 chars)
- ✅ Не потребує змін в Message (data_ref вже є!)

---

### 1.3 Alpha Models: Monolithic vs Plugin Architecture

**Рішення**: 🎯 **PLUGIN ARCHITECTURE** (AlphaModel ABC)

#### Обґрунтування:

**Plugin (виберемо)**:
```python
class AlphaModel(ABC):
    """Base class for all alpha models."""

    @abstractmethod
    def on_features(self, features: Message) -> None:
        """Process features, emit EVT:ALPHA_SCORE_CALCULATED."""
        pass

# Concrete models: momentum_v1.py, mean_reversion_v1.py, etc.
class MomentumModel(AlphaModel):
    model_id = "momentum_v1"

    def on_features(self, features: Message) -> None:
        # Calculate signal
        signal = self._calculate_momentum()
        self.fsm.emit('EVT:ALPHA_SCORE_CALCULATED', {
            'model_id': self.model_id,
            'score': signal,
        })
```

**Переваги**:
- ✅ Easy to add new models (no changes to DecisionMaking)
- ✅ A/B test models (live vs backtest)
- ✅ Enable alpha research (20+ models simultaneously)
- ✅ Clear separation of concerns

---

### 1.4 Feature Store: In-Memory vs Persistence

**Рішення**: 🎯 **HYBRID** (In-memory for speed, DuckDB for persistence)

```python
# In-memory cache (last 24h of features)
class FeatureCache:
    def __init__(self, max_age_sec: int = 86400):
        self.cache = defaultdict(list)  # { symbol: [features...] }
        self.max_age = max_age_sec

    def put(self, symbol: str, features: dict, ts: int) -> None:
        """Add features to in-memory cache."""
        self.cache[symbol].append({'ts': ts, **features})
        # Keep only recent
        cutoff = time.time() - self.max_age
        self.cache[symbol] = [f for f in self.cache[symbol] if f['ts'] > cutoff]

# Persistence (DuckDB for backtesting)
class FeatureStore:
    def __init__(self, db_path: str):
        self.db = duckdb.connect(db_path)
        self.cache = FeatureCache()

    def on_features_calculated(self, event: Message) -> None:
        """Store to both cache and DB."""
        features = event.pld['features']
        symbol = event.pld['symbol']
        ts = event.ts

        # Cache
        self.cache.put(symbol, features, ts)

        # DB (async to avoid latency)
        asyncio.create_task(self._write_to_db(symbol, features, ts))
```

**Переваги**:
- ✅ Live trading: sub-millisecond access (in-memory)
- ✅ Backtesting: full history (DuckDB)
- ✅ Research: replay with different features
- ✅ No single point of failure

---

## 2. DESIGN PATTERNS FOR SCALABILITY

### 2.1 Event-Driven Architecture Pattern

**Pattern**: **CQRS-like (Command Query Responsibility Segregation)**

```
Market Data Tick
    ▼
Feature Engineering (Query: "what are the features?")
    ▼
EVT:FEATURES_CALCULATED
    ▼
Risk Management (Query: "is this trade safe?")
    ▼
EVT:RISK_APPROVED or EVT:RISK_REJECTED
    ▼
Decision Making (Command: "should we trade?")
    ▼
TRADE_INTENT_PROPOSED
    ▼
OrchestratorFSM (Command: "sign and execute")
    ▼
CMD:OPEN
    ▼
Execution Position (Action: "submit order")
```

**Benefit**: Each domain owns its responsibility, loose coupling

---

### 2.2 Idempotency Pattern (TTL-based)

**Problem**: Same trade submitted twice (network retry)

**Solution**:
```python
class IdempotencyStore:
    def __init__(self, ttl_sec: int = 300):
        self.store = {}  # { idempotent_key: (result, ts) }
        self.ttl = ttl_sec

    def check_and_record(self, key: str, result: Any) -> bool:
        """
        True if new, False if already processed.
        """
        now = time.time()

        if key in self.store:
            prev_result, prev_ts = self.store[key]
            if (now - prev_ts) < self.ttl:
                # Duplicate within TTL window
                return False

        self.store[key] = (result, now)
        return True

    def cleanup_expired(self) -> int:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, ts) in self.store.items() if (now - ts) > self.ttl]
        for k in expired:
            del self.store[k]
        return len(expired)
```

**Usage**:
```python
# OrchestratorFSM
idempotency = IdempotencyStore(ttl_sec=300)  # 5 min window

def on_order_exec(self, cmd: Message) -> None:
    key = cmd.idempotent_key or cmd.rid
    if not idempotency.check_and_record(key, cmd):
        # Duplicate! Skip
        self.logger.info(f"Duplicate order {key}, skipping")
        return

    # Process order
    self._execute_order(cmd)
```

---

### 2.3 Circuit Breaker Pattern (Graceful Degradation)

**Pattern**: 3-state circuit breaker per domain

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout_sec: int = 60):
        self.state = 'CLOSED'  # Normal operation
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout_sec
        self.last_failure_ts = None

    def record_success(self) -> None:
        self.failure_count = 0
        if self.state != 'CLOSED':
            self.state = 'CLOSED'

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_ts = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

    def allow_request(self) -> bool:
        if self.state == 'CLOSED':
            return True

        if self.state == 'OPEN':
            # Check if timeout passed → try HALF_OPEN
            if (time.time() - self.last_failure_ts) > self.timeout:
                self.state = 'HALF_OPEN'
                return True  # Allow probe
            return False

        # HALF_OPEN
        return True  # Allow probe
```

**Usage**:
```python
# Execution Position domain
cb = CircuitBreaker(failure_threshold=5, timeout_sec=60)

def submit_order(self, order: Message) -> bool:
    if not cb.allow_request():
        self.logger.error("Circuit breaker OPEN, rejecting order")
        asyncio.create_task(trading_alerts.alert_circuit_breaker_active('execution_position'))
        return False

    try:
        result = self._submit_to_exchange(order)
        cb.record_success()
        return result
    except Exception as e:
        cb.record_failure()
        if cb.state == 'OPEN':
            asyncio.create_task(trading_alerts.alert_circuit_breaker_active('execution_position', str(e)))
        raise
```

---

## 3. DATA FLOW ARCHITECTURE

### 3.1 End-to-End Trade Flow (5 phases)

```
PHASE 1: SIGNAL GENERATION (Cold path)
────────────────────────────────────────
Market Data Tick (WebSocket)
    ▼
Feature Engineering (calculate SMA, RSI, ATR, volatility)
    ▼
EVT:FEATURES_CALCULATED (features stored in FeatureCache + FeatureStore)
    ▼
Regime Detector (detect TREND_UP, HIGH_VOLATILITY, etc.)
    ▼
EVT:REGIME_DETECTED

Alpha Models (momentum_v1, mean_reversion_v1, etc.)
    ▼
EVT:ALPHA_SCORE_CALCULATED


PHASE 2: DECISION MAKING (Hot path, <50ms SLO)
────────────────────────────────────────
Decision Making Domain:
  1. Wait for features + regime + risk approval
  2. Aggregate alpha scores (ensemble)
  3. Calculate signal score
  4. Determine side (LONG/SHORT)
  5. Regime-adaptive filter (block counter-trend)
  6. Calculate position size (Kelly fraction)
  7. Emit TRADE_INTENT_PROPOSED
    ▼
RID = UUID4 (auto-generated in Message)
WHY chain starts: [signal_reason, risk_reason, sizing_reason]


PHASE 3: ORCHESTRATION (OrchestratorFSM)
────────────────────────────────────────
OrchestratorFSM receives TRADE_INTENT_PROPOSED:
  1. Register RID in lifecycle db
  2. State = 'EVAL'
  3. Accumulate why_chain in data_ref
  4. Sign the intent (Ed25519)
  5. Emit to Execution Position


PHASE 4: EXECUTION (Hot path)
────────────────────────────────────────
Execution Position Domain:
  1. Receive CMD:OPEN (signed)
  2. Validate signature (Ed25519.verify)
  3. Submit order to Binance
  4. Get order_id, link to RID (link_ack_id)
  5. Emit EVT:ORDER_SUBMITTED


PHASE 5: MONITORING & CLOSE (Warm path)
────────────────────────────────────────
Position Tracking:
  1. Monitor fills
  2. Track P&L
  3. Check SL/TP breach
  4. Emit EVT:POSITION_CLOSED when exit triggered


End State:
  OrchestratorFSM.rid_db[rid].state = 'CLOSED'
  RID ready for GC after TTL expires
```

### 3.2 Latency Budget

```
SLO: p95 ≤ 100ms (overall), p95 ≤ 50ms (decision)

Market Tick
    ↓ 0-2ms (feature_engineering)
Feature Calculated
    ↓ 0-2ms (regime_detector)
Regime Detected
    ↓ 0-3ms (alpha_models, parallel)
Alpha Scores
    ↓ 5-15ms (decision_making, critical)
TRADE_INTENT
    ↓ 1-2ms (OrchestratorFSM)
CMD:OPEN (signed)
    ↓ 10-30ms (execution_position → Binance)
ORDER_SUBMITTED
    ↓ Network latency to Binance (variable)
FILL

Budget remaining: 50-80ms for retries, backpressure, etc.
```

---

## 4. TESTING STRATEGY

### 4.1 Test Pyramid

```
                  ▲
                 / \
                /   \  E2E Tests (3-5 trades, live testnet)
               /  E2E \
              /_________\
             /           \
            /             \  Integration Tests (multi-domain, mocked exchange)
           /  Integration  \
          /__________________\
         /                     \
        /                       \  Unit Tests (individual domains, 800+)
       /        Unit Tests       \
      /_____________________________\
```

### 4.2 Unit Tests (Existing: 800+)

Maintain current coverage:
- ✅ Test per domain in isolation
- ✅ Mock FSMCore, config
- ✅ Verify signal calculations
- ✅ Check edge cases (NaN, extreme values)

### 4.3 Integration Tests (New: 20-30)

```python
# tests/integration/test_full_trade_flow.py
def test_full_trade_flow_btcusdt():
    """End-to-end: feature → decision → order execution."""

    # Setup
    fsm = FSMCore()
    features_engine = FeatureEngineering(config, fsm)
    regime_detector = RegimeDetector(config, fsm)
    decision_making = DecisionMaking(config, fsm)
    orch = OrchestratorFSM(fsm, config)
    exec_pos = ExecutionPosition(config, fsm, exchange=mock_exchange)

    # Trigger: market tick
    tick = Message(
        op='EVT',
        verb='MARKET_TICK',
        pld={'symbol': 'BTCUSDT', 'price': '30000', 'volume': '10'}
    )

    # Execute flow
    features_engine.on_tick(tick)  # → EVT:FEATURES_CALCULATED
    regime_detector.on_features(...)  # → EVT:REGIME_DETECTED
    decision_making.on_features(...)  # → TRADE_INTENT_PROPOSED
    orch.on_trade_intent(...)  # → CMD:OPEN (signed)
    exec_pos.on_cmd(...)  # → EVT:ORDER_SUBMITTED

    # Assertions
    assert mock_exchange.last_order is not None
    assert orch.rid_db[tick.rid].state == 'OPEN'
    assert len(orch.rid_db[tick.rid].why_chain) >= 3
```

### 4.4 Backtesting (New: AlphaModel validation)

```python
# tests/backtest/test_momentum_model_btcusdt.py
def test_momentum_model_on_90_day_history():
    """Backtest momentum_v1 on BTC/USDT 90-day history."""

    # Load historical features
    features = feature_store.fetch_features('BTCUSDT', 90, '1.0')
    returns = features['close'].pct_change()

    # Run backtest
    model = MomentumModel(config)
    signals = model.backtest(features)

    # Evaluate
    trades = backtester.execute_trades(signals, returns)
    metrics = backtester.calculate_metrics(trades)

    assert metrics['sharpe'] > 0.5, f"Sharpe too low: {metrics['sharpe']}"
    assert metrics['max_dd'] > -0.2, f"Max DD too deep: {metrics['max_dd']}"
    assert metrics['win_rate'] > 0.45, f"Win rate too low: {metrics['win_rate']}"
```

---

## 5. DEPLOYMENT & ROLLOUT

### 5.1 Staging Environment (Testnet)

```
Production Environment (Live, BTC/USDT, real money):
                                ▲
                                │
                         Review metrics
                         ↓
Paper Trading (Testnet, real account, sandbox):
  - Submit real orders but don't execute
  - Track hypothetical P&L
  - Duration: 2-4 weeks minimum
                                ▲
                                │
                         A/B test models
                         ↓
Shadow Mode (Dual-write, zero-execute):
  - Same signals as production
  - DON'T submit orders
  - Compare: simulated P&L vs real P&L
  - Drift tolerance: <1% over 1 week
                                ▲
                                │
                         Launch signoff
                         ↓
Development (Backtest only):
  - Test new models
  - Optimize parameters
  - No real orders
```

### 5.2 Canary Deployment

```yaml
# Phase 1: Canary (10% of trades)
alpha_search:
  ensemble:
    models:
      - id: momentum_v1
        weight: 0.2
        rollout_percentage: 10  # ← Only 10% of trades
      - id: mean_reversion_v1
        weight: 0.2
        rollout_percentage: 10
      # Existing models
      - id: legacy_signal_v0
        weight: 0.6
        rollout_percentage: 100  # 90% still use old

# Phase 2: Ramp (50% after 1 week if metrics OK)
# Phase 3: Full (100% after 2 weeks if metrics OK)
```

### 5.3 Rollback Procedure

```python
# If metrics degrade, automatic rollback:
# - Detect: Sharpe < baseline - 0.3 OR win_rate < baseline - 0.1
# - Action: Disable new models, revert to old weights
# - Alert: Send CRITICAL alert to ops

class MetricsMonitor:
    def check_health(self):
        current = self._fetch_metrics()
        baseline = self._fetch_baseline()

        if current['sharpe'] < baseline['sharpe'] - 0.3:
            self._trigger_rollback("Sharpe degradation")
            return False

        return True
```

---

## 🎯 SUMMARY: ARCHITECTURAL PRINCIPLES

| Principle | Implementation |
|-----------|-----------------|
| **Centralization** | OrchestratorFSM coordinates all trades |
| **Traceability** | WHY chain via data_ref field |
| **Resilience** | Circuit breakers, idempotency, TTL-based GC |
| **Scalability** | Plugin alpha models, feature store |
| **Testability** | Unit + integration + backtest pyramid |
| **Operability** | Alerts, dashboard, `/debug/{rid}` endpoint |

---

**Версія**: 1.0 | **Статус**: FINALIZED | **Next**: Start implementing P0 items
