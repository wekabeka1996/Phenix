# 📅 2-WEEK SPRINT PLAN: Production Readiness & Alpha Search Foundation

**Дата**: 2 листопада 2025
**Цільова дата завершення**: 16 листопада 2025
**Версія**: 1.0

---

## 🎯 SPRINT OBJECTIVES

**Первин**: Підготувати Phenix до production trading + заложити фундамент для alpha search

**Успіх визначається**:
1. ✅ RID GC working (WAL cleanup 1h cycle)
2. ✅ Dynamic risk scoring (varies 0.1-0.95)
3. ✅ Alerts configured (Slack/PagerDuty)
4. ✅ OrchestratorFSM deployed (RID tracking)
5. ✅ AlphaModel framework ready
6. ✅ Test suite intact (800+ tests passing)

---

## 📊 WEEK 1: PRODUCTION STABILIZATION

### Day 1 (Wed, Nov 3): RID GC + Risk Scoring

#### 1.1 RID Garbage Collection Implementation

**Task**: Create `vfoundation/dr/wal_gc.py`

**Steps**:
1. Create class `WALGarbageCollector`
2. Implement methods:
   - `__init__()` - initialize with retention_days, max_size_mb
   - `cleanup_old_wals()` - remove WAL files older than TTL
   - `rotate_current_wal()` - rename WAL when size exceeds threshold
   - `start_background_gc()` - spawn daemon thread
   - `get_stats()` - return disk usage

**Code template**: See IMPLEMENTATION_PLAYBOOK.md section 1.1

**Testing**:
- `tests/test_wal_gc.py::test_cleanup_old_wals` - verify deletion
- `tests/test_wal_gc.py::test_rotate_on_size` - verify rotation
- `tests/test_wal_gc.py::test_concurrent_writes` - WAL thread-safety

**Effort**: 2-3 hours
**Owner**: You
**Acceptance Criteria**:
- [ ] GC thread starts on app init
- [ ] Old WAL files deleted after TTL
- [ ] Rotation happens on size threshold
- [ ] Tests pass (3 new test cases)

---

#### 1.2 Dynamic Risk Scoring

**Task**: Fix `apps/reference/domains/risk_management/risk_management.py`

**Current bug** (line ~155):
```python
risk_score = Decimal(decision_config.get('base_risk_score', '0.85'))
# ← Always 0.85! Never recalculated
```

**Fix**: Replace with dynamic calculation

**Steps**:
1. Replace static assignment with `_calculate_dynamic_risk_score()`
2. Implement method that considers:
   - Leverage ratio (portfolio notional / max allowed)
   - Volatility factor (regime-based)
   - Position correlation (diversification bonus)
   - Drawdown recovery (post-loss penalty reduction)
3. Add logging: show inputs to calculation
4. Update unit tests

**Code template**: See IMPLEMENTATION_PLAYBOOK.md section 1.2

**Testing**:
- `tests/domains/test_risk_manager_dynamic_scoring.py::test_risk_score_varies_with_leverage`
- `tests/domains/test_risk_manager_dynamic_scoring.py::test_risk_score_increases_in_high_volatility`
- `tests/domains/test_risk_manager_dynamic_scoring.py::test_risk_score_decreases_with_diversification`

**Effort**: 1-2 hours
**Owner**: You
**Acceptance Criteria**:
- [ ] Risk score varies (0.1 - 0.95)
- [ ] Increases with leverage
- [ ] Increases in HIGH_VOLATILITY regime
- [ ] Decreases with > 2 positions
- [ ] Tests pass (3 new test cases)

---

#### 1.3 Verify & Commit

**Steps**:
1. Run all tests: `pytest -q`
2. Check risk_score values in logs: `grep -i "risk score calculated"`
3. Verify WAL GC in ops/wal directory
4. Commit: `git commit -m "fix(production): RID GC + dynamic risk scoring [P0-BLOCKER]"`

**Time**: 30 min

---

### Day 2-3 (Thu-Fri, Nov 4-5): Alert Manager Setup

#### 2.1 Alert Framework

**Task**: Create `apps/reference/telemetry/alerts.py`

**Features**:
- Define Alert dataclass (level, title, body, timestamp)
- AlertManager class with handlers
- Slack integration (async)
- PagerDuty integration (critical only)

**Code template**: See IMPLEMENTATION_PLAYBOOK.md section 1.3

**Testing**:
- `tests/telemetry/test_alerts.py::test_alert_manager_sends_to_slack`
- `tests/telemetry/test_alerts.py::test_critical_alert_goes_to_pagerduty`
- `tests/telemetry/test_alerts.py::test_multiple_handlers_fire`

**Effort**: 2-3 hours

---

#### 2.2 Alert Triggers

**Task**: Create `apps/reference/telemetry/alert_triggers.py`

**Triggers**:
1. RiskGateBlockingAlert (block_rate > 80%)
2. CircuitBreakerActiveAlert (domain failures)
3. HighLeverageAlert (leverage > 3x)
4. WALSizeAlert (size > 500 MB)
5. ExposureBleedAlert (positions not tracked)

**Effort**: 2 hours

---

#### 2.3 Integration

**Task**: Wire alerts into domains

**In each domain**:
```python
# risk_management.py
if approval_count < len(intents) * 0.2:  # > 80% blocked
    asyncio.create_task(trading_alerts.alert_risk_gate_blocking(...))

# execution_position.py (on error)
if error_count > threshold:
    asyncio.create_task(trading_alerts.alert_circuit_breaker_active(...))
```

**Effort**: 1 hour

---

#### 2.4 Configuration

**Task**: Create `configs/alerts.yaml`

```yaml
alerts:
  slack:
    webhook: ${SLACK_WEBHOOK}
    channels:
      info: '#trading-info'
      warning: '#trading-warnings'
      critical: '#trading-critical'

  pagerduty:
    routing_key: ${PAGERDUTY_KEY}
    environments:
      testnet: false
      live: true
```

**Effort**: 30 min

---

#### 2.5 Test & Deploy

**Steps**:
1. Run: `pytest tests/telemetry/test_alerts.py -q`
2. Manual test: Send test alert to Slack
3. Commit: `git commit -m "feat(alerts): Slack + PagerDuty integration [P0]"`

**Time**: 1 hour

---

### Day 4-5 (Mon-Tue, Nov 6-7): OrchestratorFSM - Part 1

#### 3.1 Design & Data Structures

**Task**: Create `apps/reference/orchestrator/orchestrator_fsm.py` skeleton

**Define**:
- `RIDLifecycle` dataclass
- `OrchestratorFSM` class with key methods
- `Ed25519Signer` utility

**Code**:
```python
# apps/reference/orchestrator/types.py
@dataclass
class RIDLifecycle:
    rid: str
    state: str  # EVAL, OPEN, MONITOR, CLOSED
    ts_started: int
    ts_ended: Optional[int] = None
    domain_chain: List[str] = field(default_factory=list)
    why_chain: List[str] = field(default_factory=list)
    ttl_sec: int = 3600  # 1 hour default
    sig: Optional[str] = None
    pnl_usd: Decimal = Decimal('0')

    def is_expired(self) -> bool:
        now = time.time()
        return (now - self.ts_started) > self.ttl_sec

# apps/reference/orchestrator/orchestrator_fsm.py
class OrchestratorFSM:
    def __init__(self, fsm_core: FSMCore, config: dict):
        self.fsm = fsm_core
        self.config = config
        self.rid_db: dict[str, RIDLifecycle] = {}
        self.signer = Ed25519Signer(os.getenv('PRIVATE_KEY'))
        self.logger = logging.getLogger('OrchestratorFSM')

        # Register event listeners
        self.fsm.listen('TRADE_INTENT_PROPOSED', self.on_trade_intent)
        self.fsm.listen('CMD:OPEN_ACK', self.on_order_ack)
        self.fsm.listen('EVT:POSITION_CLOSED', self.on_position_closed)
```

**Effort**: 1-2 hours

---

#### 3.2 Implement Key Methods

**Methods**:
1. `on_trade_intent()` - EVAL phase registration
2. `on_order_ack()` - OPEN phase update
3. `on_position_closed()` - CLOSED phase, schedule GC
4. `get_rid_trace()` - debug endpoint
5. `cleanup_expired_rids()` - GC

**Effort**: 3-4 hours

---

#### 3.3 Testing & Debug Endpoint

**Task**: Create `/debug/{rid}` endpoint in main.py

```python
# apps/reference/main.py
from fastapi import FastAPI

app = FastAPI()
orch = OrchestratorFSM(fsm, config)

@app.get("/debug/{rid}")
async def debug_rid(rid: str):
    lifecycle = orch.get_rid_trace(rid)
    return lifecycle
```

**Testing**:
- `tests/test_orchestrator_fsm.py::test_rid_lifecycle_eval_phase`
- `tests/test_orchestrator_fsm.py::test_rid_lifecycle_open_phase`
- `tests/test_orchestrator_fsm.py::test_why_chain_accumulated`
- `tests/test_orchestrator_fsm.py::test_rid_signature_valid`

**Effort**: 1-2 hours

---

#### 3.4 Commit & Verify

**Steps**:
1. Run tests: `pytest tests/test_orchestrator_fsm.py -q`
2. Manual test: Submit trade, check `/debug/{rid}`
3. Verify WHY chain populated
4. Commit: `git commit -m "feat(orchestrator): Central RID coordination [P0]"`

**Time**: 1 hour

---

### Day 5-6 (Wed-Thu, Nov 8-9): Integration & P0 Gate

#### 4.1 Integrate All P0 Components

**Task**: Verify all P0 pieces work together

**Flow**:
1. Market tick → Features → Risk score (dynamic) ✅
2. Risk approval → Trade intent → OrchestratorFSM ✅
3. OrchestratorFSM signs → CMD:OPEN ✅
4. Execution Position processes ✅
5. Alert on failures ✅
6. GC cleanup on background ✅

**Testing**:
- `tests/integration/test_p0_complete_flow.py`

**Effort**: 2-3 hours

---

#### 4.2 Load Testing

**Task**: Verify performance under load

**Scenario**: 100 market ticks/sec for 10 seconds = 1000 signals

```python
# tests/perf/test_p0_latency.py
def test_decision_latency_under_load():
    """Decision latency p95 < 50ms, p99 < 100ms."""
    ...
```

**Effort**: 1 hour

---

#### 4.3 P0 Gate Review

**Checklist**:
- [ ] RID GC working (delete old WAL)
- [ ] Risk score dynamic (varies with leverage + regime)
- [ ] Alerts firing (Slack messages received)
- [ ] OrchestratorFSM deployed (RID tracing works)
- [ ] Test suite passes (800+ tests)
- [ ] Performance acceptable (p95 < 50ms)

**If all ✅**: P0 APPROVED, proceed to WEEK 2

**If any ❌**: Debug + fix immediately

---

---

## 📊 WEEK 2: ALPHA DISCOVERY FOUNDATION

### Day 8-9 (Fri, Nov 10 + Mon, Nov 13): AlphaModel Framework

#### 5.1 Abstract Base Class

**Task**: Create `apps/reference/domains/alpha_search/alpha_model.py`

```python
from abc import ABC, abstractmethod
from vfoundation.core.protocol import Message

class AlphaModel(ABC):
    """Abstract base for all alpha models."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Unique identifier (e.g., 'momentum_v1')."""
        pass

    @abstractmethod
    def on_features(self, event: Message) -> None:
        """Process FEATURES_CALCULATED, emit ALPHA_SCORE_CALCULATED."""
        pass

    def _emit_alpha_score(self, score: float, confidence: float) -> None:
        """Helper to emit alpha score event."""
        self.fsm.emit('EVT:ALPHA_SCORE_CALCULATED', {
            'model_id': self.model_id,
            'score': score,
            'confidence': confidence,
        })
```

**Effort**: 1 hour

---

#### 5.2 Concrete Models

**Task**: Implement 3 models as templates

**Models**:
1. **MomentumModel** (`momentum_v1.py`)
   - Signal = current_price / SMA50 - 1
   - Range: [-1.0, +1.0]

2. **MeanReversionModel** (`mean_reversion_v1.py`)
   - Signal = -1.0 * (current_price - SMA20) / ATR
   - Range: [-1.0, +1.0]

3. **VolatilityModel** (`volatility_v1.py`)
   - Signal = ATR / SMA * confidence (HIGH_VOLATILITY regime)
   - Range: [0.0, 1.0]

**Code template**:
```python
# apps/reference/domains/alpha_search/models/momentum_v1.py
from decimal import Decimal
from apps.reference.domains.alpha_search.alpha_model import AlphaModel

class MomentumModel(AlphaModel):
    model_id = "momentum_v1"

    def __init__(self, config: dict, fsm):
        self.fsm = fsm
        self.config = config
        self.logger = fsm.logger

    def on_features(self, event: Message) -> None:
        features = event.pld.get('features', {})
        price = Decimal(features.get('price', '0'))
        sma_50 = Decimal(features.get('sma_50', '0'))

        if sma_50 == 0:
            return

        # Signal = (price / sma_50) - 1
        signal = float((price / sma_50) - Decimal('1.0'))
        signal = max(-1.0, min(signal, 1.0))  # Clamp to [-1, 1]

        self._emit_alpha_score(signal, confidence=0.7)
```

**Testing**: 3 test files, 15 test cases total

**Effort**: 3-4 hours

---

#### 5.3 AlphaEnsemble Aggregator

**Task**: Create `apps/reference/domains/alpha_search/ensemble.py`

```python
class AlphaEnsemble:
    def __init__(self, models: List[AlphaModel], weights: dict):
        self.models = models  # { model_id: AlphaModel }
        self.weights = weights  # { model_id: float (0.0-1.0) }
        self.latest_scores = {}  # { model_id: score }

    def on_alpha_score(self, event: Message) -> None:
        """Collect alpha scores from models."""
        model_id = event.pld['model_id']
        score = event.pld['score']
        self.latest_scores[model_id] = score

        # When all scores available, aggregate
        if len(self.latest_scores) == len(self.models):
            ensemble_score = self._aggregate()
            self._emit_ensemble_signal(ensemble_score)

    def _aggregate(self) -> float:
        """Weighted sum of alpha scores."""
        total_weight = sum(self.weights.values())
        weighted_sum = sum(
            self.latest_scores.get(mid, 0) * self.weights.get(mid, 0)
            for mid in self.models.keys()
        )
        return weighted_sum / total_weight if total_weight > 0 else 0
```

**Effort**: 1-2 hours

---

#### 5.4 Integration with DecisionMaking

**Task**: Modify `apps/reference/domains/decision_making/decision_making.py`

**Changes**:
1. Listen to `EVT:ENSEMBLE_ALPHA_SCORE` (not `FEATURES_CALCULATED`)
2. Use ensemble score instead of hardcoded signal calculation
3. Preserve regime-adaptive filter
4. Preserve position sizing logic

**Effort**: 1 hour

---

### Day 10-11 (Tue-Wed, Nov 14-15): Backtester & Feature Store

#### 6.1 Feature Store (DuckDB)

**Task**: Create `apps/reference/data/feature_store.py`

```python
import duckdb
import pandas as pd
from pathlib import Path

class FeatureStore:
    def __init__(self, db_path: str = "data/features.db"):
        self.db = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        """Create features table."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS features (
                ts INTEGER,
                symbol VARCHAR,
                timeframe VARCHAR,
                feature_version VARCHAR,
                price DECIMAL,
                sma_short DECIMAL,
                sma_long DECIMAL,
                rsi DECIMAL,
                atr DECIMAL,
                volatility DECIMAL,
            )
        """)

    def store_features(self, event: Message) -> None:
        """Persist calculated features."""
        self.db.execute(
            "INSERT INTO features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.ts,
                event.pld['symbol'],
                '5m',
                '1.0',
                float(event.pld['features']['price']),
                # ... other features
            )
        )

    def fetch_features(self, symbol: str, start_ts: int, end_ts: int) -> pd.DataFrame:
        """Fetch features for backtesting."""
        result = self.db.execute(f"""
            SELECT * FROM features
            WHERE symbol = ? AND ts BETWEEN ? AND ?
            ORDER BY ts
        """, (symbol, start_ts, end_ts)).fetch_all()

        columns = [desc[0] for desc in self.db.description]
        return pd.DataFrame(result, columns=columns)
```

**Effort**: 1-2 hours

---

#### 6.2 Backtester Engine

**Task**: Create `apps/reference/alpha_discovery/backtest_engine.py`

```python
import numpy as np
import pandas as pd
from typing import List, Tuple

class MultiStrategyBacktester:
    def __init__(self, feature_store, lookback_days: int = 90):
        self.fs = feature_store
        self.lookback_days = lookback_days

    def backtest_model(self, model: AlphaModel, symbol: str = 'BTCUSDT') -> dict:
        """
        Run single model on historical features.

        Return: {
            'sharpe': float,
            'max_dd': float,
            'win_rate': float,
            'trades': int,
            'pnl_usd': float,
        }
        """
        # Fetch features
        features_df = self.fs.fetch_features(symbol, lookback_days * 86400)

        # Generate signals
        signals = []
        for _, row in features_df.iterrows():
            msg = Message(
                op='EVT',
                verb='FEATURES_CALCULATED',
                pld={'features': row.to_dict()}
            )
            # model.on_features(msg) → emits alpha score
            # But in backtest, we calculate directly
            score = model._calculate_alpha(row)
            signals.append(score)

        # Simulate trades
        returns = features_df['close'].pct_change()
        trades = []
        position = 0

        for i, signal in enumerate(signals):
            if signal > 0.3 and position == 0:
                position = 1
                entry_price = features_df.iloc[i]['close']
            elif signal < -0.3 and position == 1:
                position = 0
                exit_price = features_df.iloc[i]['close']
                pnl = (exit_price - entry_price) / entry_price
                trades.append(pnl)

        # Calculate metrics
        if not trades:
            return {
                'sharpe': 0.0,
                'max_dd': 0.0,
                'win_rate': 0.0,
                'trades': 0,
                'pnl_usd': 0.0,
            }

        returns_array = np.array(trades)
        sharpe = np.mean(returns_array) / np.std(returns_array) if np.std(returns_array) > 0 else 0

        cum_returns = np.cumprod(1 + returns_array)
        running_max = np.maximum.accumulate(cum_returns)
        dd = (cum_returns - running_max) / running_max
        max_dd = np.min(dd)

        win_rate = np.sum(returns_array > 0) / len(returns_array)

        return {
            'sharpe': float(sharpe),
            'max_dd': float(max_dd),
            'win_rate': float(win_rate),
            'trades': len(trades),
            'pnl_usd': float(np.sum(returns_array)),
        }

    def rank_models(self, models: List[AlphaModel]) -> List[Tuple[str, dict]]:
        """Rank models by Sharpe ratio."""
        results = []
        for model in models:
            metrics = self.backtest_model(model)
            results.append((model.model_id, metrics))

        # Sort by Sharpe
        results.sort(key=lambda x: x[1]['sharpe'], reverse=True)
        return results
```

**Effort**: 2-3 hours

---

#### 6.3 Backtest Testing

**Task**: Create `tests/backtest/test_models_backtest.py`

```python
def test_momentum_model_positive_sharpe():
    """Backtest should show positive Sharpe for momentum on 90d history."""
    model = MomentumModel(config)
    backtest = MultiStrategyBacktester(feature_store)

    metrics = backtest.backtest_model(model, 'BTCUSDT')

    assert metrics['sharpe'] > 0.0, f"Expected positive Sharpe, got {metrics['sharpe']}"
    assert metrics['max_dd'] > -1.0, f"Drawdown unreasonable: {metrics['max_dd']}"
    assert metrics['trades'] > 10, f"Too few trades: {metrics['trades']}"
```

**Effort**: 1 hour

---

#### 6.4 Model Ranking & Weights Optimization

**Task**: Create `apps/reference/alpha_discovery/weight_optimizer.py`

```python
class WeightOptimizer:
    @staticmethod
    def optimize_weights(backtest_results: List[Tuple[str, dict]]) -> dict:
        """
        Assign weights based on Sharpe ratio.
        Higher Sharpe → higher weight.
        """
        total_sharpe = sum(r[1]['sharpe'] for r in backtest_results if r[1]['sharpe'] > 0)

        if total_sharpe == 0:
            # Equal weights fallback
            return {model_id: 1.0 / len(backtest_results) for model_id, _ in backtest_results}

        weights = {}
        for model_id, metrics in backtest_results:
            sharpe = max(metrics['sharpe'], 0)  # Ignore negative Sharpe
            weights[model_id] = sharpe / total_sharpe

        return weights
```

**Effort**: 30 min

---

### Day 12 (Thu, Nov 16): Final Integration & Deployment

#### 7.1 Integrate AlphaModel + Backtester

**Task**: Wire together

1. Create 3 concrete models (momentum, mean_reversion, volatility)
2. Create AlphaEnsemble aggregator
3. Update DecisionMaking to use ensemble signal
4. Update config to specify weights
5. Run full integration test

**Effort**: 2-3 hours

---

#### 7.2 Configuration

**Task**: Update `configs/master_config_v1.yaml`

```yaml
alpha_search:
  enabled: true
  models:
    momentum_v1:
      enabled: true
      config:
        sma_period: 50
    mean_reversion_v1:
      enabled: true
      config:
        sma_period: 20
        atr_period: 14
    volatility_v1:
      enabled: true
      config:
        atr_period: 14

  ensemble:
    momentum_v1: 0.3
    mean_reversion_v1: 0.3
    volatility_v1: 0.2  # Lower weight for volatility model
    # Other weights: ...

  feature_store:
    backend: duckdb
    path: data/features.db
    retention_days: 180
```

**Effort**: 30 min

---

#### 7.3 Final Testing

**Task**: Run full test suite

```bash
pytest -q  # All tests
pytest tests/test_orchestrator_fsm.py -v  # OrchestratorFSM
pytest tests/domains/test_alpha_models.py -v  # Alpha models
pytest tests/backtest/test_models_backtest.py -v  # Backtester
pytest tests/integration/test_p0_complete_flow.py -v  # E2E flow
```

**Target**: 850+ tests passing

**Effort**: 1 hour

---

#### 7.4 Documentation & Commit

**Task**: Update docs + commit

**Files to update**:
- README.md (new alpha search section)
- DEPLOYMENT.md (new deployment steps)
- docs/domains/alpha_search.md (new, explains models)

**Commit**:
```bash
git commit -m "feat(alpha-search): Multi-model ensemble + backtester [P1]"
```

**Effort**: 1-2 hours

---

#### 7.5 Final Verification

**Checklist**:
- [ ] P0 items still working (RID GC, dynamic risk, alerts, OrchestratorFSM)
- [ ] AlphaModel framework operational
- [ ] Backtester produces metrics
- [ ] Feature store persists to DuckDB
- [ ] All 850+ tests passing
- [ ] No performance regression (p95 < 50ms decision)
- [ ] Code committed + pushed

**If all ✅**: SPRINT COMPLETE! 🎉

---

---

## 📊 DEPENDENCIES & BLOCKING

```
                     ┌─────────────┐
                     │   RID GC    │ ← Independent (Day 1)
                     └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ Risk Scoring │ ← Independent (Day 1)
                     └──────────────┘
                            │
                     ┌──────┴──────┐
                     ▼             ▼
             ┌───────────┐   ┌───────────┐
             │  Alerts   │   │ OrchestratorFSM │ ← Dep on P0 (Days 3-7)
             └───────────┘   └───────────┘
                     ▲             ▲
                     └─────┬───────┘
                           │
                  ┌────────▼────────┐
                  │ Integration P0  │ ← (Days 8-9)
                  └────────┬────────┘
                           │
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
   ┌─────────────┐  ┌──────────────┐  ┌────────────┐
   │ AlphaModels │  │FeatureStore  │  │ Backtester │ ← (Days 10-12)
   └─────────────┘  └──────────────┘  └────────────┘
         ▲                 ▲                  ▲
         └─────────────────┼──────────────────┘
                           │
                  ┌────────▼─────────┐
                  │ Integration P1   │ ← Final (Days 12-16)
                  └──────────────────┘
```

**Critical path**: Days 1-3 must complete before Days 4-7
Days 8-12 independent from Days 1-7

---

## 🎯 SUCCESS METRICS

| Metric | Target | Method |
|--------|--------|--------|
| Tests passing | 850+ | `pytest -q` |
| RID GC working | 100% | Check ops/wal directory after 1 hour |
| Risk score dynamic | 0.1-0.95 | Log output analysis |
| Alerts firing | 3/3 systems | Manual Slack test + metrics |
| Decision latency p95 | <50ms | Benchmark test |
| Backtest Sharpe (best model) | >0.5 | Backtest results |
| Feature store retention | 6 months | DuckDB query |

---

## 📝 DAILY STANDUP TEMPLATE

**Each morning, fill in**:
```
## Daily Standup - Day X (Date)

### Completed Yesterday
- [ ] ...
- [ ] ...

### Today's Goal
- [ ] ...

### Blockers
- None / [ ] Specific issue

### Code Metrics
- Tests passing: 800+ / 850+ ✅
- Decision latency p95: 45ms / 50ms ✅
```

---

## 🚨 ROLLBACK PROCEDURES

**If any component fails**:

1. **RID GC breaks**: Disable background thread, manual cleanup
2. **Risk scoring breaks**: Revert to static 0.75, fix calculation
3. **Alerts misconfigured**: Disable Slack/PagerDuty, log to stdout
4. **OrchestratorFSM crashes**: Skip registration, domains continue
5. **AlphaModel fails**: Fall back to old hardcoded signal calculation

**Always**: `git revert <commit>` if needed

---

**Версія**: 1.0 | **Статус**: READY FOR EXECUTION | **Next**: Day 1 - Nov 3
