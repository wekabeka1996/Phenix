# 🔍 PHENIX GAP ANALYSIS TABLE: Production Readiness (Detailed)

**Дата**: 2 листопада 2025
**Версія**: 1.0
**Фокус**: Точна оцінка кожного компонента, що не вистачає

---

## 📊 COMPLETE GAP MATRIX

### 1. RUNTIME STABILITY

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **RID Garbage Collection** | None | WAL cleanup every 1h | Remove old files (TTL 7d) | P0 | 1d | YES |
| RID Memory Limit | Unlimited | 100k max RIDs | Add cleanup trigger | P0 | 2h | YES |
| **Dynamic Risk Score** | Static 0.85 | 0.1-0.95 variance | Recalc based on leverage+regime | P0 | 1d | YES |
| **Circuit Breaker** | Per-domain only | Orchestrator-level CB | Add global circuit state | P1 | 1d | NO |
| Error Retry Logic | 2 retries only | Exponential backoff + jitter | Add retry manager | P1 | 1d | NO |
| **Position Correlation** | None | Concentration risk check | Add correlation matrix | P1 | 1d | NO |
| Exposure Tracking | Manual | Auto-track & validate | Fix double-booking bug | P0 | 2h | YES |

**P0 Stability Effort**: 4 days (RID GC, risk score, exposure fix)

---

### 2. CENTRAL ORCHESTRATION

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **RID Lifecycle Manager** | None | OrchestratorFSM | Track EVAL→OPEN→MONITOR→CLOSE | P0 | 3d | YES |
| **WHY Chain Aggregation** | Local + duplified | Centralized in data_ref | Accumulate across domains | P0 | 2d | YES |
| **Ed25519 Signing** | Not on CMD | Sign high-risk commands | Add signer to OrchestratorFSM | P0 | 1d | YES |
| **Idempotency Store** | Ad-hoc only | TTL-based dedup | Track idempotent_keys | P1 | 1d | NO |
| Multi-Domain Tracing | Partial (span_id) | Full parent-child correlation | Add trace aggregation | P1 | 1d | NO |

**P0 Orchestration Effort**: 6 days (OrchestratorFSM from scratch)

---

### 3. OBSERVABILITY & DEBUGGING

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **Alert System** | None | Slack + PagerDuty | Build alert manager | P0 | 2d | YES |
| **RID Trace Endpoint** | Basic CLI | Full `/debug/{rid}` REST API | Expand trace API | P0 | 1d | YES |
| **Trading Dashboard** | None | Real-time web UI | Build FastAPI + JS frontend | P1 | 2-3d | NO |
| **Latency Dashboard** | No monitoring | Track p50/p95/p99 latency | Add timing instrumentation | P1 | 1d | NO |
| **Error Rate Monitoring** | Logs only | Real-time metrics | Add Prometheus exporters | P1 | 1d | NO |
| **PnL Tracking Dashboard** | Manual | Real-time P&L per symbol | Add position valuation | P1 | 1d | NO |

**P0 Observability Effort**: 3 days (alerts + trace API)

---

### 4. ALPHA DISCOVERY FRAMEWORK

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **AlphaModel ABC** | None | Abstract base for models | Define interface | P1 | 4h | NO |
| **Momentum Model** | Hardcoded in decision | Pluggable model_v1 | Extract to separate class | P1 | 1d | NO |
| **Mean Reversion Model** | None | Pluggable model_v1 | Implement with ATR bands | P1 | 1d | NO |
| **Volatility Model** | None | Pluggable model_v1 | ATR-based regime model | P1 | 1d | NO |
| **Ensemble Aggregator** | None | Weighted sum of models | Combine 3+ models | P1 | 1d | NO |
| **Multi-Strategy Backtester** | None | Test 20+ models on 90d data | DuckDB + evaluation loop | P1 | 2d | NO |
| **Feature Store** | In-memory only | Persist to DuckDB (6mo) | Add data layer | P1 | 1d | NO |
| **Weight Optimizer** | None | Optimize ensemble weights | Sharpe-based optimization | P2 | 1d | NO |
| **Multi-Timeframe** | 5m only | 5m + 15m + 1h + 4h | Aggregate candles | P2 | 2d | NO |

**P1 Alpha Effort**: 10-12 days (models + backtester + feature store)

---

### 5. RISK MANAGEMENT ENHANCEMENTS

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **Dynamic Risk Score** | Static 0.85 | Varies 0.1-0.95 | Formula + leverage factor | P0 | 1d | YES |
| **Concentration Risk** | None | Max correlation check | Compare position betas | P1 | 1d | NO |
| **VaR Calculation** | None | Daily VaR at 95% | Add variance calculation | P2 | 1d | NO |
| **Expected Shortfall** | None | CVaR at 95% | Add tail risk metric | P2 | 1d | NO |
| **SL/TP Validation** | Orders created | Verify fills occurred | Add fill monitor | P1 | 1d | NO |
| **Drawdown Tracking** | Manual | Auto track peak-to-trough | Add running max logic | P1 | 4h | NO |

**P0 Risk Effort**: 1 day (dynamic risk score)

---

### 6. DATA & PERSISTENCE

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **Feature Store** | None | DuckDB + 6mo retention | Persist + query layer | P1 | 1d | NO |
| **Trade Journal** | JSONL logs | Queryable schema | Centralized storage | P1 | 1d | NO |
| **Order Archive** | WAL only | Indexed by symbol/date | Searchable database | P2 | 1d | NO |
| **Model Performance DB** | None | Track Sharpe/DD per model | Store backtest results | P1 | 1d | NO |
| **Configuration Versioning** | Static files | Git-tracked + rollback | Enable config drift detection | P2 | 1d | NO |

**P1 Data Effort**: 2-3 days (feature store + trade journal)

---

### 7. TESTING & VALIDATION

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **Unit Tests** | 844 passing | Maintain + 50 new | Add P0/P1 tests | P1 | 2d | NO |
| **Integration Tests** | 10 only | 30+ multi-domain | Full flows + edge cases | P1 | 2d | NO |
| **Backtesting Suite** | None | Validate all models | Historical replay engine | P1 | 2d | NO |
| **E2E Live Tests** | None | Paper trading mode | Testnet execution | P2 | 1d | NO |
| **Stress Testing** | None | 1000 ticks/sec for 10s | Load testing suite | P2 | 1d | NO |
| **Property-Based Tests** | None | Hypothesis framework | Generative testing | P2 | 1d | NO |

**P1 Testing Effort**: 4 days (integration + backtest + new unit tests)

---

### 8. DEPLOYMENT & OPERATIONS

| Component | Current | Need | Gap | P | Effort | Block |
|-----------|---------|------|-----|---|--------|-------|
| **Canary Deployment** | No mechanism | Gradual rollout (10% → 50% → 100%) | Add feature flags | P2 | 1d | NO |
| **Graceful Degradation** | Partial (shutdown) | Error scenarios recovery | Fallback strategies | P1 | 1d | NO |
| **Monitoring Alerts** | None | Slack + PagerDuty + email | Alert manager | P0 | 2d | YES |
| **Configuration Management** | YAML + env vars | Dynamic + rollback | Config versioning | P2 | 1d | NO |
| **Health Checks** | None | `/health` + liveness probe | Add health endpoint | P1 | 4h | NO |
| **Metrics Export** | Prometheus (partial) | Full OpenMetrics export | Add all metrics | P1 | 1d | NO |

**P0 Operations Effort**: 2 days (alerts)

---

## 📈 CUMULATIVE EFFORT ESTIMATE

### By Priority

```
P0 (BLOCKERS - Must complete before production):
  RID GC                    1 day
  Dynamic risk score        1 day
  Alerts (Slack)            2 days
  OrchestratorFSM          3 days
  Exposure fix             0.5 day
  RID trace API            1 day
  ─────────────────────────────
  TOTAL P0:               9.5 days

P1 (Must for alpha search):
  AlphaModel framework      1 day
  3x concrete models        3 days
  Ensemble aggregator       1 day
  Backtester                2 days
  Feature store             1 day
  Integration tests         2 days
  Error recovery            1 day
  SL/TP validator           1 day
  ─────────────────────────────
  TOTAL P1:               12 days

P2 (Nice-to-have):
  Multi-timeframe           2 days
  ML regime detection       3 days
  Dashboard UI              2 days
  Canary deployment         1 day
  ─────────────────────────────
  TOTAL P2:               8 days

TOTAL EFFORT: 29.5 days (4.2 weeks)
- Production-ready: 9.5 days
- Alpha search foundation: 12 days
- Optimization: 8 days
```

### By Timeline

| Week | P0 | P1 | P2 | Status |
|------|----|----|----|----- |
| Week 1 (Nov 3-7) | 9.5d | - | - | **RID GC, risk, alerts, orchestrator** |
| Week 2 (Nov 10-16) | - | 12d | - | **Alpha models, backtester** |
| Week 3 (Nov 17-23) | - | - | 8d | **Optimization** |

---

## 🎯 BLOCKING DEPENDENCIES

```
┌─────────────────────────────────────────────────────┐
│ P0 MUST COMPLETE FIRST (9.5 days)                  │
│                                                     │
│ 1. RID GC (1d) ──┐                                 │
│ 2. Risk score (1d)  ├── Integration (1d)          │
│ 3. Alerts (2d) ──┴─ OrchestratorFSM (3d) ──┐      │
│ 4. Exposure fix (0.5d) ─────────────────┘     │   │
│ 5. RID trace (1d) ──────────────────────────┘   │
│                                                │   │
│                            P0 GATE ✅        │   │
│                           (Day 10)            │   │
│                                                │   │
└────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │ P1 CAN START (12 days)             │
        │                                     │
        │ Alpha models (3d)                  │
        │ Backtester (2d)                    │
        │ Feature store (1d)                 │
        │ Integration tests (2d)             │
        │ ...                                │
        │                                     │
        │        P1 GATE ✅                 │
        │       (Day 22)                     │
        │                                     │
        └─────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │ PRODUCTION READY                   │
        │ ALPHA SEARCH FOUNDATION            │
        │ Paper trading → Live trading       │
        │                                     │
        │         (Week 4+)                  │
        └─────────────────────────────────────┘
```

---

## 🚨 CRITICAL BLOCKERS (P0 = PRODUCTION BLOCKER)

| Issue | Why It Blocks | Symptom | Fix Time |
|-------|---------------|---------|----------|
| **RID GC missing** | OOM in 30 days | App crashes after 30d | 1d |
| **Risk always 0.85** | Trades blocked | Can't execute any trades | 1d |
| **No orchestration** | Can't track trades | No `/debug/{rid}` endpoint | 3d |
| **No alerts** | Blind ops team | Can't see errors | 2d |
| **Exposure bug** | Double-booking | Positions exceed limits | 0.5d |

**If you implement P0 items**: ✅ Production-ready

**If you skip any P0 item**: ❌ Cannot go live (high risk)

---

## ✨ NICE-TO-HAVE ENHANCEMENTS (P2+)

These don't block production but significantly improve alpha discovery:

1. **Multi-timeframe analysis** → Reduce false signals 40-60%
2. **ML-based regime detection** → Better market classification
3. **Sentiment analysis** → News-based alpha
4. **Inter-market correlations** → Cross-asset regime detection
5. **Automated weight optimization** → Meta-learning
6. **Model performance feedback loop** → Continuous improvement

---

## 📋 SUMMARY TABLE: What, Why, How

| Gap | What's Missing | Why It Matters | How to Fix | Days |
|-----|----------------|----|----------|------|
| GC | No WAL cleanup | OOM crash | Rotation + TTL cleanup | 1 |
| Risk | Always 0.85 | No risk variation | Dynamic formula | 1 |
| Orch | No central coord | Can't track RID | OrchestratorFSM | 3 |
| Alpha | No model framework | Can't find alpha | AlphaModel ABC | 1 |
| Backtest | No history replay | Can't validate models | Feature store + backtester | 3 |
| Alerts | No notifications | Blind ops | Slack + PagerDuty | 2 |
| UI | No dashboard | Manual monitoring | Web UI + WebSocket | 2 |

---

**Версія**: 1.0 | **Статус**: FINALIZED | **Ready for implementation**
