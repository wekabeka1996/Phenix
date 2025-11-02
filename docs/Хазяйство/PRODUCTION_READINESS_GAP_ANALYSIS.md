# 🚀 PRODUCTION READINESS & ALPHA SEARCH ARCHITECTURE GAP ANALYSIS

**Дата**: 2 листопада 2025
**Версія**: 1.0
**Статус**: Deep Review (NOT DRAFT)

---

## 📋 ЗМІСТ

1. [Архітектурні гепи](#1-архітектурні-гепи---критичні)
2. [Production-Ready дефіцити](#2-production-ready-дефіцити)
3. [Alpha Discovery Pipeline](#3-alpha-discovery-pipeline)
4. [Risk Management](#4-risk-management--production)
5. [Observability & Debugging](#5-observability--debugging)
6. [Implementation Roadmap](#6-implementation-roadmap-prio)

---

## 1. АРХІТЕКТУРНІ ГЕПИ - КРИТИЧНІ

### 1.1 OrchestratorFSM: Відсутня ЦЕНТРАЛІЗОВАНА КООРДИНАЦІЯ

**Статус**: 🔴 **BLOCK FOR PRODUCTION**

#### Що є:
- `MetaFSM` існує, але мініатюрна (11 рядків, тільки "normal" vs "low_risk")
- Доменні FSM работают изолированно (9 independent domains)
- Нема centralized RID lifecycle management
- Нема TTL/CB enforcement на рівні orchestration

#### Що потрібно:
```python
# apps/reference/orchestrator/orchestrator_fsm.py
class OrchestratorFSM:
    """
    Central coordinator for all domain FSMs (TRADE hotpath).

    Responsibilities:
    1. RID lifecycle (EVAL → OPEN → MONITOR → CLOSE/COMPENSATE)
    2. WHY chain accumulation (centralized, not local)
    3. TTL enforcement & garbage collection
    4. Circuit breaker routing across domains
    5. Idempotency enforcement (idempotent_key tracking)
    6. Multi-domain flow coordination
    7. Signing/verification of high-risk commands (CMD:OPEN/CLOSE/ADJUST)
    """

    def __init__(self, fsm_core, config):
        self.rid_lifecycle = {}  # { rid: { state, ts, domain_chain, why_chain, sig } }
        self.ttl_manager = TTLManager(config['ttl_policy'])
        self.cb_manager = CircuitBreakerManager(config['cb_policy'])
        self.idempotency_store = IdempotencyStore(config['idempotency_ttl'])

    def on_trade_intent(self, intent_msg: Message) -> None:
        """EVAL phase: Parse trade intent, validate, register RID."""
        rid = intent_msg.rid
        self.rid_lifecycle[rid] = {
            'state': 'EVAL',
            'ts_started': time.time(),
            'domain_chain': ['decision_making'],
            'why_chain': [intent_msg.why or 'unknown'],
            'sig': None,
            'ttl': self.ttl_manager.ttl_for_intent(intent_msg.pld),
        }

    def on_order_exec(self, cmd_msg: Message) -> None:
        """OPEN phase: Validate, sign, emit CMD:OPEN."""
        rid = cmd_msg.rid
        if rid not in self.rid_lifecycle:
            self.logger.error(f"Unknown RID {rid}")
            return

        # Add to domain chain
        self.rid_lifecycle[rid]['domain_chain'].append('execution_position')
        self.rid_lifecycle[rid]['why_chain'].append(cmd_msg.why or 'open_ordered')

        # SIGN high-risk command
        sig = self.signer.sign_ed25519(cmd_msg.pld)
        self.rid_lifecycle[rid]['sig'] = sig

        # Emit with signature
        cmd_msg.sig = sig
        cmd_msg.data_ref = self.rid_lifecycle[rid]['why_chain']
        self.fsm.emit('CMD:OPEN', cmd_msg)

    def on_position_closed(self, close_msg: Message) -> None:
        """CLOSE phase: Update lifecycle, cleanup."""
        rid = close_msg.rid
        if rid not in self.rid_lifecycle:
            return

        self.rid_lifecycle[rid]['state'] = 'CLOSED'
        self.rid_lifecycle[rid]['ts_ended'] = time.time()

        # Schedule cleanup
        self.ttl_manager.register_for_cleanup(rid)

    def cleanup_expired_rids(self) -> None:
        """GC: Remove expired RID lifecycles."""
        now = time.time()
        expired = [
            rid for rid, data in self.rid_lifecycle.items()
            if (now - data['ts_started']) > data['ttl']
        ]
        for rid in expired:
            del self.rid_lifecycle[rid]
            self.logger.info(f"GC: Cleaned up RID {rid}")
```

**Impact**:
- ✅ Centralized RID tracking (debug via `/debug/{rid}`)
- ✅ WHY chain preserved (not destroyed by JOIN)
- ✅ TTL enforcement (prevent WAL bloat)
- ✅ Signature verification (Ed25519 for CMD:OPEN/CLOSE)
- ✅ Idempotency enforcement (prevent double-trades)

**Priority**: **P0 BLOCKER** (without this, production is impossible)

---

### 1.2 Distributed Tracing & Correlation IDs

**Статус**: 🟡 **PARTIAL** (Message.span_id exists, but no correlation across domains)

#### Що є:
- `Message.span_id`, `parent_span_id` defined in protocol
- Aurora logs have `rid`, but no parent-child tracing
- Each domain logs independently

#### Що потрібно:
```python
# vfoundation/obs/distributed_tracing.py
class DistributedTracer:
    """
    Correlate all domain FSM messages across a single trade lifecycle.

    Emits:
    - Root span: decision_making intent creation
    - Child spans: feature_engineering → risk_management → decision_making → execution_position
    - Timings: latency per domain
    """

    def span_context(self, parent_span_id: str = None) -> dict:
        """Generate span IDs for message linking."""
        span_id = uuid.uuid4().hex
        return {
            'span_id': span_id,
            'parent_span_id': parent_span_id,
        }

    def trace_latency(self, span_id: str) -> float:
        """Measure latency per domain."""
        # Used for detecting slow domains
        pass
```

**Impact**:
- ✅ Full trace from market_data → decision_making → execution_position
- ✅ Identify domain bottlenecks
- ✅ Root cause analysis for failed trades

**Priority**: **P1** (nice-to-have for debug, not blocking production)

---

### 1.3 MultiModel Alpha Strategy Framework: MISSING

**Статус**: 🔴 **MISSING** (Regime detector exists, but no alpha models)

#### Що є:
- Regime detector (TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY)
- Feature engineering (SMA, RSI, ATR, volatility)
- Signal scoring (hardcoded weights)

#### Що потрібно (для alpha search):
```python
# apps/reference/domains/alpha_search/alpha_models.py
class AlphaModel(ABC):
    """
    Abstract base for composable alpha models.
    Each model emits EVT:ALPHA_SCORE_CALCULATED.
    """

    @abstractmethod
    def on_features(self, event: Message) -> None:
        """Process feature event, emit alpha score."""
        pass

    @property
    def model_id(self) -> str:
        """Unique model identifier (e.g., 'momentum_v1', 'mean_reversion_v2')."""
        pass

# Concrete implementations
class MomentumModel(AlphaModel):
    """Buy if price > 50-SMA, sell if < 50-SMA. ROC-based."""
    model_id = "momentum_v1"

class MeanReversionModel(AlphaModel):
    """Buy if price < 20-SMA - 2*STDEV, sell if > 20-SMA + 2*STDEV."""
    model_id = "mean_reversion_v1"

class VolatilityModel(AlphaModel):
    """Buy if ATR spike + TREND_UP, avoid if ATR collapse."""
    model_id = "volatility_v1"

# Ensemble aggregation
class AlphaEnsemble:
    """
    Combine multiple alpha models with weights.
    Meta-model for automated weight optimization.
    """

    def __init__(self, models: List[AlphaModel], weights: dict):
        self.models = models
        self.weights = weights  # { 'momentum_v1': 0.4, 'mean_reversion_v1': 0.3, ... }

    def aggregate_alpha(self, alphas: dict) -> float:
        """Weighted sum of alpha scores from all models."""
        total = sum(
            alphas.get(model_id, 0) * weight
            for model_id, weight in self.weights.items()
        )
        return total / sum(self.weights.values())

    def backtest_weights(self, historical_alphas: List[dict], returns: List[float]) -> dict:
        """Find optimal weights via regression."""
        # Use sklearn.linear_model.LinearRegression
        # Or Sharpe ratio optimization
        pass
```

**Impact**:
- ✅ Pluggable alpha models (test multiple strategies simultaneously)
- ✅ Ensemble aggregation (reduce model risk)
- ✅ Automated weight optimization (alpha discovery)
- ✅ Shadow mode A/B testing (live vs backtest)

**Priority**: **P0 for ALPHA SEARCH** (can't find alpha without models)

---

## 2. PRODUCTION-READY ДЕФІЦИТИ

### 2.1 RID Garbage Collection: ВІДСУТНЯ (**CRITICAL BUG**)

**Статус**: 🔴 **BROKEN**

#### Проблема:
- RID lifecycle stored forever (no TTL cleanup)
- WAL files accumulate unbounded (no rotation)
- **Memory bloat**: 1000 trades/day × 365 days = 365,000 RIDs in-memory

#### Що потрібно:
```python
# vfoundation/dr/wal_gc.py
class WALGarbageCollector:
    """
    Rotate and cleanup old WAL files.
    Triggered periodically (every 1 hour) or when disk usage exceeds threshold.
    """

    def __init__(self, wal_dir: Path, retention_days: int = 7):
        self.wal_dir = wal_dir
        self.retention_days = retention_days

    def cleanup_old_wals(self) -> int:
        """Remove WAL files older than retention_days."""
        cutoff_ts = time.time() - (self.retention_days * 86400)
        removed = 0

        for wal_file in self.wal_dir.glob("wal_*.jsonl"):
            file_ts = wal_file.stat().st_mtime
            if file_ts < cutoff_ts:
                wal_file.unlink()
                removed += 1

        return removed

    def rotate_current_wal(self, max_size_mb: int = 100) -> bool:
        """Rotate WAL file when size exceeds threshold."""
        current_wal = self.wal_dir / "wal_current.jsonl"
        if current_wal.stat().st_size > max_size_mb * 1024 * 1024:
            # Rename to timestamped file
            ts = int(time.time())
            current_wal.rename(self.wal_dir / f"wal_{ts}.jsonl")
            return True
        return False
```

**Deployment**:
```python
# apps/reference/main.py
gc_thread = Thread(
    target=lambda: wal_gc.cleanup_old_wals() every 1 hour,
    daemon=True
)
gc_thread.start()
```

**Impact**:
- ✅ Prevents OOM (out-of-memory) errors in production
- ✅ Reduces disk usage by 95%+
- ✅ Enables 24/7 trading without restart

**Priority**: **P0 BLOCKER**

---

### 2.2 Error Recovery & Resilience: WEAK

**Статус**: 🟡 **PARTIAL**

#### Що є:
- Circuit breaker (exists in TTLManager)
- Graceful shutdown
- Error codes (NRR-001...NRR-019)
- Retry logic in bridge (2 retries max)

#### Що потрібно:
```python
# apps/reference/resilience/error_recovery.py
class ErrorRecoveryManager:
    """
    Handle transient failures (network timeouts, order rejections, etc.)
    """

    def on_order_failed(self, error: OrderError, rid: str) -> Message:
        """
        Classify error:
        - Transient (TEMPORARY_FAILURE) → Retry with backoff
        - Permanent (INVALID_ORDER) → Reject trade
        - Unknown → Circuit breaker activate
        """
        if error.is_transient():
            return Message(op="DEC", verb="RETRY_WITH_BACKOFF", ...)
        elif error.is_permanent():
            return Message(op="DEC", verb="REJECT_INTENT", ...)
        else:
            return Message(op="DEC", verb="ACTIVATE_CB", ...)

    def exponential_backoff(self, attempt: int, base_ms: int = 100) -> int:
        """Backoff: 100ms, 200ms, 400ms, 800ms, ..."""
        return base_ms * (2 ** attempt)
```

**Impact**:
- ✅ Automatic recovery from network glitches
- ✅ Prevents cascading failures
- ✅ Reduces manual intervention

**Priority**: **P1**

---

### 2.3 Monitoring & Alerting: MISSING

**Статус**: 🔴 **MISSING** (only `/metrics` endpoint exists)

#### Що потрібно:
```python
# apps/reference/telemetry/alerts.py
class AlertManager:
    """
    Emit alerts for critical events.
    Integrations: Slack, PagerDuty, email.
    """

    def alert_risk_gate_blocking(self, blocked_trades: int) -> None:
        """Alert if risk manager blocks >90% of trades."""
        if blocked_trades / total_intents > 0.9:
            self.send_alert(
                level="CRITICAL",
                title="Risk gate blocking 90%+ trades",
                body=f"Risk manager rejected {blocked_trades} intents"
            )

    def alert_circuit_breaker_active(self, domain: str) -> None:
        """Alert if circuit breaker is activated."""
        self.send_alert(
            level="HIGH",
            title=f"Circuit breaker active in {domain}",
            body="Domain exceeded error threshold"
        )
```

**Priority**: **P1**

---

## 3. ALPHA DISCOVERY PIPELINE

### 3.1 What's Missing: Multi-Strategy Backtesting

**Статус**: 🔴 **MISSING**

#### Поточна ситуація:
- Regime detector works (TREND_UP, etc.)
- Feature engineering exists
- But: **NO mechanism to test multiple alpha models simultaneously**

#### Що потрібно:
```python
# apps/reference/alpha_discovery/backtest_engine.py
class MultiStrategyBacktester:
    """
    Run 10-100 alpha models in parallel on historical data.
    Track performance metrics for each model.
    """

    def __init__(self, symbols: List[str], lookback_days: int = 90):
        self.symbols = symbols
        self.lookback_days = lookback_days
        self.historical_data = self._fetch_ohlcv()

    def backtest_model(self, model: AlphaModel) -> BacktestResult:
        """
        Run single model on historical OHLCV.

        Return:
        {
            'sharpe': 1.25,
            'max_dd': -0.15,
            'win_rate': 0.62,
            'trades': 145,
            'pnl': 1250.50,
        }
        """
        pass

    def rank_models(self) -> List[Tuple[AlphaModel, float]]:
        """Rank by Sharpe ratio."""
        pass
```

**Inputs for alpha discovery**:
- Historical OHLCV (Binance API via market_data connector)
- Features from feature_engineering
- Regimes from regime_detector

**Outputs**:
- Rankings of alpha models by Sharpe/Sortino
- Optimal ensemble weights
- Recommended models for live trading

**Priority**: **P1 for ALPHA SEARCH**

---

### 3.2 Multi-Timeframe Analysis: MISSING

**Статус**: 🔴 **MISSING**

#### Поточна ситуація:
- Features calculated on 5-min candles only
- Regime detection on 5-min only
- **NO cross-timeframe confirmation**

#### Що потрібно:
```python
# apps/reference/domains/feature_engineering/multi_timeframe.py
class MultiTimeframeAnalyzer:
    """
    Calculate features on 5m, 15m, 1h, 4h timeframes.
    Use higher TFs for confirmation (reduce false signals).
    """

    def on_market_tick(self, tick: Message) -> None:
        """
        Aggregate ticks into 5m, 15m, 1h, 4h candles.
        Emit EVT:FEATURES_CALCULATED for each timeframe.
        """
        for tf in ['5m', '15m', '1h', '4h']:
            candle = self._get_or_create_candle(tf)
            candle.update(tick.pld['price'], tick.pld['volume'])

            if candle.is_complete():
                features = self._calculate_features(candle)
                self.fsm.emit('EVT:FEATURES_CALCULATED', {
                    'timeframe': tf,
                    'features': features,
                })

    def confirm_signal(self, signal_5m: str, signal_15m: str, signal_1h: str) -> bool:
        """
        Confirm 5m signal only if 15m AND 1h agree.
        Reduces whipsaws by 40-60%.
        """
        return signal_5m == signal_15m == signal_1h
```

**Impact**:
- ✅ Reduce false signals by 40-60%
- ✅ Better regime detection (1h trend more stable)
- ✅ Higher win rate

**Priority**: **P1 for ALPHA SEARCH**

---

### 3.3 Feature Store & Version Control: MISSING

**Статус**: 🔴 **MISSING**

#### Поточна ситуація:
- Features calculated on-the-fly
- **NO history** for backtesting
- **NO versioning** (can't compare different feature sets)

#### Що потрібно:
```python
# apps/reference/data/feature_store.py
class FeatureStore:
    """
    Persist features to DuckDB or Parquet.
    Enable backtesting and feature engineering experiments.
    """

    def __init__(self, db_path: str = "data/features.db"):
        self.db = duckdb.connect(db_path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS features (
                ts INT,
                symbol STRING,
                timeframe STRING,
                feature_set_version STRING,
                price DECIMAL,
                sma_short DECIMAL,
                sma_long DECIMAL,
                rsi DECIMAL,
                atr DECIMAL,
                volatility DECIMAL,
            )
        """)

    def store_features(self, event: Message) -> None:
        """Store calculated features."""
        self.db.execute(
            "INSERT INTO features VALUES (?, ?, ?, ?, ?, ...)",
            (event.ts, event.symbol, event.timeframe, '1.0', ...)
        )

    def fetch_features(self, symbol: str, start_ts: int, end_ts: int,
                      version: str = 'latest') -> pd.DataFrame:
        """Fetch features for backtesting."""
        result = self.db.execute(f"""
            SELECT * FROM features
            WHERE symbol = ? AND ts BETWEEN ? AND ?
            AND feature_set_version = ?
        """, (symbol, start_ts, end_ts, version)).fetch_all()
        return pd.DataFrame(result)
```

**Deployment**:
```yaml
# configs/feature_store.yaml
feature_store:
  backend: duckdb  # or: parquet, postgres
  path: data/features.db
  retention_days: 180  # Keep 6 months of features
```

**Impact**:
- ✅ Enable offline backtesting
- ✅ A/B test feature versions
- ✅ Reuse features for research

**Priority**: **P1**

---

## 4. RISK MANAGEMENT & PRODUCTION

### 4.1 Current Risk Manager Issues

**Статус**: 🔴 **BROKEN** (risk_score always 0.85-0.87)

#### Проблема:
```python
# apps/reference/domains/risk_management/risk_management.py (lines 150-160)
risk_score = Decimal(decision_config.get('base_risk_score', '0.85'))
# ← Always 0.85! No recalculation based on market data
```

#### Що потрібно:
```python
class RiskManager:
    def _calculate_dynamic_risk_score(self) -> Decimal:
        """
        Risk score should vary based on:
        1. Portfolio leverage (current / max)
        2. Market regime (HIGH_VOLATILITY → higher risk score)
        3. Correlation of positions (diversified → lower risk)
        4. Recent drawdown (recovering → lower risk)
        5. VIX-like metric (crypto equivalent: BTC dominance, leverage ratio)
        """

        leverage_ratio = self.current_notional / self.max_notional  # 0.0 - 1.0
        regime_factor = 1.2 if self.current_regime == "HIGH_VOLATILITY" else 1.0
        correlation_factor = self._estimate_correlation()  # 0.5 - 1.5
        drawdown_recovery = 1.0 - min(self.current_drawdown / self.max_historical_dd, 1.0)

        risk_score = Decimal(str(
            0.5 * leverage_ratio  # Base: 50% of leverage
            * regime_factor  # Adjust for volatility
            * correlation_factor  # Diversification discount
            * drawdown_recovery  # Recovery bonus
        ))
        return min(risk_score, Decimal("0.95"))  # Cap at 0.95
```

**Priority**: **P0 BLOCKER**

---

### 4.2 Position Correlation Analysis: MISSING

**Статус**: 🔴 **MISSING**

#### Поточна ситуація:
- Risk manager approves each position independently
- **NO correlation check** (can get long BTC + long ETHUSDT = double crypto risk)

#### Що потрібно:
```python
class PortfolioRiskAnalyzer:
    def _estimate_correlation_matrix(self) -> np.ndarray:
        """
        Calculate 14-day rolling correlations between holdings.
        Use for PnL diversification check.
        """
        returns = self._fetch_returns(days=14)
        corr_matrix = returns.corr()
        return corr_matrix

    def check_concentration_risk(self, new_symbol: str) -> bool:
        """
        Reject if adding new_symbol would create correlation risk.
        Rule: Sum of betas for long positions < 2.0 (total market beta)
        """
        current_beta = sum(pos['beta'] for pos in self.positions)
        new_beta = self._estimate_beta(new_symbol)
        return (current_beta + new_beta) < 2.0
```

**Priority**: **P1**

---

### 4.3 Stop Loss & Take Profit: INCOMPLETE

**Статус**: 🟡 **PARTIAL** (orders executed, but SL/TP logic inconsistent)

#### Що є:
- CMD:OPEN creates SL/TP orders (oco_group_id mechanism exists)
- But: **NO validation** that SL/TP actually fill

#### Що потрібно:
```python
class SLTPValidator:
    def on_fill(self, fill: Message) -> None:
        """
        Monitor fills to ensure SL/TP executed as expected.
        Alert if position stayed open despite breach.
        """
        position_id = fill.pld['position_id']
        fill_price = Decimal(fill.pld['fill_price'])

        # Fetch position
        position = self.positions[position_id]

        # Check SL/TP breach
        if fill.pld['side'] == 'BUY':
            if fill_price <= position['sl']:
                # SL should have been filled, but wasn't?
                self.logger.error(f"SL NOT EXECUTED for {position_id}")
```

**Priority**: **P1**

---

## 5. OBSERVABILITY & DEBUGGING

### 5.1 Live Trading Dashboard: MISSING

**Статус**: 🔴 **MISSING** (only `/metrics` JSON endpoint)

#### Що потрібно:
```python
# apps/reference/telemetry/dashboard.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/dashboard")
async def dashboard():
    """
    Real-time trading dashboard with:
    - Open positions (symbol, entry, current PnL)
    - Recent fills
    - Pending orders
    - Portfolio allocation
    - Risk metrics (leverage, VaR, etc.)
    - Recent alerts
    """
    return {
        'open_positions': [...],
        'recent_fills': [...],
        'pending_orders': [...],
        'portfolio_allocation': {...},
        'risk_metrics': {...},
        'alerts': [...],
    }
```

**Dashboard UI** (HTML/JS):
```html
<!-- apps/reference/telemetry/static/dashboard.html -->
<div id="positions">
  <!-- Real-time positions table -->
</div>
<div id="alerts">
  <!-- Real-time alerts -->
</div>
<script>
  setInterval(() => {
    fetch('/dashboard').then(r => r.json()).then(data => updateUI(data));
  }, 1000);
</script>
```

**Priority**: **P1 for OPERATIONS**

---

### 5.2 RID Tracing Endpoint: PARTIALLY DONE

**Статус**: 🟡 **PARTIAL**

#### Що є:
```python
# vfoundation/cli/vfound.py
@click.command()
@click.argument('rid')
def trace(rid: str):
    """Trace order lifecycle: vfound trace <rid>"""
    # Fetches from WAL, prints to stdout
```

#### Що потрібно:
```python
# apps/reference/telemetry/debug_api.py (expand existing)

@app.get("/debug/{rid}")
async def debug_rid(rid: str):
    """
    Complete RID lifecycle trace with WHY chain.

    Return:
    {
        'rid': '...',
        'state': 'CLOSED',
        'lifecycle': [
            {'state': 'EVAL', 'ts': 123456, 'domain': 'decision_making'},
            {'state': 'OPEN', 'ts': 123457, 'domain': 'execution_position'},
            {'state': 'MONITOR', 'ts': 123500, 'domain': 'position_tracking'},
            {'state': 'CLOSED', 'ts': 123600, 'domain': 'execution_position'},
        ],
        'why_chain': ['Signal score 0.65', 'Risk approved', 'Order filled'],
        'pnl': '+125.50',
        'duration_ms': 1144,
    }
    """
    orch = OrchestratorFSM()
    return orch.get_rid_trace(rid)
```

**Priority**: **P0** (already started, just needs expansion)

---

## 6. IMPLEMENTATION ROADMAP (PRIO)

### **P0 BLOCKERS** (Must do BEFORE production)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | Implement OrchestratorFSM | 3-4 days | Centralized RID lifecycle, WHY chain preservation, signing |
| 2 | Fix RID GC (WAL cleanup) | 1 day | Prevents OOM, enables 24/7 trading |
| 3 | Fix dynamic risk_score | 1 day | Risk manager starts working correctly |
| 4 | Create AlphaModel framework | 2 days | Foundation for multi-model alpha search |
| 5 | Implement basic alerts | 1 day | Operations can see critical issues |

**Total P0**: ~8-9 дней

---

### **P1 MUST-HAVE** (Before first live trading)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 6 | Multi-strategy backtester | 3-4 days | Core alpha discovery capability |
| 7 | Feature store (DuckDB) | 2 days | Historical features for backtesting |
| 8 | Error recovery manager | 2 days | Automatic retry + graceful degradation |
| 9 | Position correlation analyzer | 2 days | Prevent concentrated risk |
| 10 | Trading dashboard (web UI) | 2-3 days | Operational visibility |
| 11 | SL/TP validator | 1 day | Ensure risk controls work |

**Total P1**: ~14-15 дней

---

### **P2 NICE-TO-HAVE** (After successful live trading)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 12 | Multi-timeframe analyzer | 2-3 days | Reduce false signals 40-60% |
| 13 | Distributed tracing | 1-2 days | Cross-domain latency analysis |
| 14 | ML-based regime classification | 3-4 days | Better market regime detection |
| 15 | Sentiment analysis integration | 2-3 days | News-based alpha models |

**Total P2**: ~10-12 дней

---

## 📊 SUMMARY: GAP ANALYSIS

### Architecture Completeness Score

| Component | Score | Status | Gap |
|-----------|-------|--------|-----|
| **Core FSM** | 7/10 | 🟡 Domains work, no orchestration | OrchestratorFSM missing |
| **RID Lifecycle** | 4/10 | 🔴 Created OK, but no GC | WAL bloat, OOM risk |
| **WHY Chain** | 3/10 | 🔴 Dead code + duplification | Consolidate, centralize |
| **Risk Management** | 5/10 | 🔴 Broken (always 0.85) | Dynamic scoring + correlation |
| **Alpha Discovery** | 2/10 | 🔴 No framework | Need backtester + ensemble |
| **Observability** | 7/10 | 🟡 Logs good, UI missing | Dashboard + alerts |
| **Production Readiness** | 5.5/10 | 🔴 Many manual steps | GC, alerts, error recovery |

**Overall Gap**: **CANNOT GO PRODUCTION YET** (needs P0 items)

---

## 🎯 RECOMMENDATIONS

### For Production (Next 2 weeks):
1. **Immediately** (Day 1-2): Fix RID GC + dynamic risk_score (stop trading breakage)
2. **Next** (Day 3-6): Implement OrchestratorFSM (centralized coordination)
3. **Then** (Day 7-9): Setup alerts + error recovery (operational safety)

### For Alpha Search (Following 3-4 weeks):
1. **Build** (Week 3-4): AlphaModel framework + backtester
2. **Research** (Week 4-5): Test 10-20 models, find winners
3. **Deploy** (Week 5-6): Ensemble + multi-timeframe filters
4. **Monitor** (Week 6+): Track alpha decay, retrain monthly

### Architecture Debt:
- ✅ Must fix: RID GC, risk_score, WHY chain duplification
- ✅ Should consolidate: append_why() vs local why_chain logic
- ✅ Should add: OrchestratorFSM (foundation for all future features)

---

**Версія**: 1.0 | **Статус**: FINALIZED | **Next Review**: 7 листопада 2025
