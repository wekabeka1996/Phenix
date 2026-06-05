# feature_engineering — Domain README

> **Authoritative domain documentation.** For auto-generated docs see `docs/` (may be stale).

## 1. Purpose

`feature_engineering` is the **signal computation engine**. It transforms raw market ticks and bars into normalized feature vectors consumed by regime_detector, decision_making, and risk_management. It also hosts bar-based strategy infrastructure (MR, MD-AMR) used by decision_making.

**It does NOT own trading decisions, regime classification, or risk gating.**

## 2. Responsibility Boundary

Owns:
- Tick-level feature computation (V1 base + V1 phase1 + V2 additive)
- Futures features (funding, OI — config-gated)
- Macro residual (R1), absorption proxy
- Price motion block (multi-window returns + normalized PM)
- Pillar indicators (tactician/operator/strategist from multi-timeframe candles)
- Bar-level volatility/liquidity features (for CMD:PROCESS_STRATEGY)
- Bar resampling (BarResampler, MultiSymbolBarResampler)
- Pure-math indicators (SMA, ATR, RSI, Bollinger, linreg, ADX, ROC)
- MR strategy engine (MeanReversion1mStrategy)
- MD-AMR strategy engine (MDAMRStrategyV11)
- Regime-to-flat mapping (FlatRegime, MRParameters)
- Feature contracts (FeatureSetV1, FeatureSetV2, metadata)
- Warmup/readiness tracking
- CMD:PROCESS_STRATEGY emission (bar-driven trigger)

Does NOT own:
- Regime detection (→ regime_detector)
- Trading decisions / intent emission (→ decision_making)
- Risk gating / drawdown (→ risk_management)
- Raw market data ingestion (→ market_data)
- Position tracking (→ position_tracking)

## 3. Architecture

```
EVT:MARKET_TICK_RECEIVED ──→ on_market_tick()
  ├── V1 base features: obi, tfi, delta_price, price, absorption, liquidity_kappa
  ├── V1 phase1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
  ├── V2 additive: volume_zscore, large_trade_imbalance, spread_bps
  ├── Futures: funding_rate_normalized, oi_delta_pct (config-gated)
  ├── R1: macro_resid (config-gated)
  ├── Price motion block: ret/vol_pct/pm_norm at 10s/60s/300s/900s
  └── EVT:FEATURES_CALCULATED { ts, symbol, features, warmup, price_motion }

EVT:BAR_CLOSED ──→ on_bar_closed()
  ├── Per (symbol, tf_sec) state tracking
  ├── Bar volatility/liquidity: bar_range, true_range, atr_14, obi_close
  ├── Pillar candle updates (tactician/operator/strategist)
  ├── Strategy computations: MR signals, MD-AMR signals
  ├── CMD:PROCESS_STRATEGY (if warmup ready, tf_sec>=60, bar fields present)
  └── EVT:PROCESS_STRATEGY_BLOCKED (if gated)

EVT:REGIME_DETECTED ──→ on_regime_detected()
  └── Updates symbol regime state for MR/MD-AMR strategy logic

EVT:HTF_BARS_IMPORTED ──→ _on_htf_bars_imported()
  └── Seeds pillar buffers from historical candles (warmup backfill)

EVT:FUNDING_UPDATE ──→ _on_funding_update() [futures.enabled]
EVT:OI_UPDATE ──→ _on_oi_update() [futures.enabled]
EVT:ANCHOR_UPDATED ──→ _on_anchor_updated_event()
```

## 4. Events

### Consumed (7)

| Event | Source | Handler |
|-------|--------|---------|
| `EVT:MARKET_TICK_RECEIVED` | market_data | `on_market_tick` |
| `EVT:BAR_CLOSED` | market_data | `on_bar_closed` |
| `EVT:REGIME_DETECTED` | regime_detector | `on_regime_detected` |
| `EVT:HTF_BARS_IMPORTED` | bootstrap | `_on_htf_bars_imported` |
| `EVT:FUNDING_UPDATE` | market_data | `_on_funding_update` (futures-gated) |
| `EVT:OI_UPDATE` | market_data | `_on_oi_update` (futures-gated) |
| `EVT:ANCHOR_UPDATED` | market_data | `_on_anchor_updated_event` |

### Emitted (3)

| Event | Target | Registry Owner |
|-------|--------|---------------|
| `EVT:FEATURES_CALCULATED` | regime_detector, decision_making | feature_engineering |
| `CMD:PROCESS_STRATEGY` | decision_making | strategies |
| `EVT:PROCESS_STRATEGY_BLOCKED` | observability | feature_engineering |

## 5. File Map (16 source files, ~8,849 LOC)

| File | LOC | Role |
|------|-----|------|
| `feature_engineering.py` | 1847 | Core orchestrator: tick/bar handling, event emission, warmup |
| `calculation_engine.py` | 1337 | Feature math: all V1/V2/futures/R1/absorption/pillar computations |
| `types.py` | 997 | State dataclasses (HotState, ColdState, SymbolFeatureState) + FeatureEngineeringConfig |
| `mean_reversion_strategy.py` | 774 | MR strategy: Bollinger/RSI/ATR signals, regime-mapped sizing |
| `utils.py` | 518 | Welford online stats, z-score, linear slope, safe_divide |
| `bar_resampler.py` | 394 | Tick→Bar resampling (single + multi-symbol) |
| `pillar_indicators.py` | 391 | tactician/operator/strategist compute + aggregate |
| `macro_sync_resampler.py` | 386 | Cross-symbol correlation (Pearson) with time-grid alignment |
| `contracts.py` | 380 | Pydantic models: FeatureSetV1/V2, metadata, parsers |
| `indicators.py` | 365 | Pure-math: SMA, STD, Bollinger, ATR, RSI |
| `md_amr_strategy.py` | 362 | MD-AMR strategy: multi-dimensional asymmetric mean reversion |
| `regime_mapping.py` | 335 | FlatRegime enum, thresholds, MR parameter multipliers |
| `pillar_backfill.py` | 272 | Historical candle fetch + pillar warmup |
| `large_trade_imbalance.py` | 217 | Institutional flow detection from aggregated trades |
| `price_motion.py` | 199 | Multi-window returns + volatility proxy + PM normalization |
| `__init__.py` | 75 | Re-exports, `__version__ = "1.2.0"` |

### Schemas (3)
| File | Event |
|------|-------|
| `schemas/features_calculated_v1.json` | EVT:FEATURES_CALCULATED |
| `schemas/cmd_process_strategy_v1.json` | CMD:PROCESS_STRATEGY |
| `schemas/process_strategy_blocked_v1.json` | EVT:PROCESS_STRATEGY_BLOCKED |

## 6. Feature Families

### V1 Base (always computed)
| Feature | Range | Neutral | Group |
|---------|-------|---------|-------|
| `obi` | [-1, 1] | 0 | flow |
| `tfi` | [-1, 1] | 0 | flow |
| `delta_price` | unbounded | 0 | trend |
| `price` | R+ | — | meta |
| `absorption` | varies | 0 | flow |
| `liquidity_kappa` | [0.3, 1.0] | 0.5 | liquidity |

### V1 Phase 1 (enable_new_metrics)
| Feature | Range | Neutral | Group |
|---------|-------|---------|-------|
| `ema_bias` | [0, 1] | 0.5 | trend |
| `volume_spike` | [0, 1] | 0.5 | volume |
| `volatility_state` | [0, 1] | 0.5 | volatility |
| `depth_imbalance` | [0, 1] | 0.5 | liquidity |
| `macro_sync` | [0, 1] | 0.5 | macro |

### V2 Additive (FTR-03)
| Feature | Range | Neutral | Group |
|---------|-------|---------|-------|
| `volume_zscore` | [0, 1] | 0.5 | volume |
| `large_trade_imbalance` | [0, 1] | 0.5 | flow |
| `spread_bps` | R+ | — | liquidity |

### Futures (FTR-05, config-gated)
| Feature | Range | Neutral | Group |
|---------|-------|---------|-------|
| `funding_rate_normalized` | [-1, 1] | 0 | futures |
| `oi_delta_pct` | unbounded % | 0 | futures |
| `funding_rate` | unbounded | 0 | futures (debug) |

### Pillars (Phase 9 Quadratic Brain)
| Feature | Timeframe | Method |
|---------|-----------|--------|
| `pillar_tactician` | M15 | ROC(14), tanh-normalized [-1,+1] |
| `pillar_operator` | H4 | LinReg(20) * ADX(14)/50, tanh-normalized [-1,+1] |
| `pillar_strategist` | D1 | (price - SMA200)/SMA200, tanh-normalized [-1,+1] |
| `pillar_sum` | aggregate | Weighted 0.30/0.40/0.30 |

### Price Motion (multi-window)
| Feature | Windows |
|---------|---------|
| `ret_*s` | 10s, 60s, 300s, 900s |
| `vol_pct_*s` | 10s, 60s, 300s, 900s |
| `pm_norm_*s` | 10s, 60s, 300s, 900s (clipped ±10.0) |

## 7. Config Dependencies

All config via `FeatureEngineeringConfig` (wraps `AuroraConfig`). Key blocks:
- `enable_new_metrics` — V1 phase1 feature toggle
- `enabled_timeframes_sec` — which bar timeframes to process
- `ema.*` — EMA periods
- `volume.*` — volume SMA/window
- `volatility.*` — volatility SMA/window
- `liquidity.*` — depth_half, kappa_min/max
- `ema_bias.*` — clamp range
- `volume_spike.*` — cap, SMA length, eps
- `volume_zscore.*` — clip sigma
- `large_trade_imbalance.*` — window, min_trades, eps
- `depth_imbalance.*` — Laplace smoothing
- `macro_sync.*` — anchors, align_mode, correlation
- `absorption.*` — proxy source, dedup window, clip
- `macro_resid.*` — beta/MAD windows, clip
- `spread_bps.health_gate.*` — health gate
- `pillars.*` — enable, timeframes per layer
- `futures.*` — enable, funding threshold
- `warmup.*` — enforcement_mode, required_ready_keys
- `feature_sanity.*` — NaN/Inf behavior, bounds
- `delta_price.spike_filter_ms` — spike filtering

Source: `config/aurora/domains.yaml` → `domains.feature_engineering`

## 8. Cross-Domain Coupling

| Direction | What | Why |
|-----------|------|-----|
| FE → vfoundation | Message (protocol) | Event wrapping |
| FE → contracts | RuntimeBarSourceMode, RuntimeRegimeLayer, gap_policy | Bar identity + regime layering |
| FE → config | AuroraConfig, FeatureEngineeringDomainConfig | Typed config |
| FE → telemetry | metric counters | Optional observability side-channel |
| FE → clock | Clock, LiveClock | Time abstraction |
| MD → FE | Strategy via `decision_making/strategy_bridge.py` | **Sanctioned facade** (FE-DM-BOUNDARY-STABILIZATION) |
| MD (bar_aggregator) → FE | Bar via `shared/types.py` | Shared helper re-export |
| bootstrap → FE | FeatureEngineering, PillarBackfillService | Domain init + warmup |

**FE↔DM Boundary Policy (2026-03-15):**
- Strategy files (`mean_reversion_strategy.py`, `md_amr_strategy.py`, `regime_mapping.py`) live in FE but are semantically owned by DM
- DM production code MUST import these via `decision_making/strategy_bridge.py`
- Direct FE→strategy imports from DM production code are forbidden
- A future migration will physically move files to DM

## 9. Fail-Closed Rules

- **Dict config → TypeError** (FeatureEngineeringConfig rejects non-config objects)
- **Missing config fields → ConfigContractError** (Pydantic extra='forbid')
- **Price ≤ 0 → no emission** (tick handler early return)
- **Warmup not ready → PROCESS_STRATEGY_BLOCKED** (explicit reason code)
- **Missing bar fields → PROCESS_STRATEGY_BLOCKED** (BAR_FIELDS_MISSING)
- **tf_sec < 60 → PROCESS_STRATEGY_BLOCKED** (TF_SEC_LT_60)
- **NaN/Inf features → neutral + not_ready** (configurable via feature_sanity)
- **Stale anchor data → macro_sync neutral** (TTL-based expiry)

## 10. Forbidden Patterns

- Do NOT compute features outside feature_engineering (regime_detector's SMA/ATR is the only documented exception)
- Do NOT bypass FeatureEngineeringConfig for config access
- Do NOT add feature names without updating contracts.py metadata
- Do NOT emit CMD:PROCESS_STRATEGY without warmup checks
- Do NOT hardcode feature neutral values in strategy logic — use FEATURE_METADATA
- Do NOT add imports to/from decision_making (event-only coupling is the target)

## 11. Testing

```bash
pytest tests/domains/feature_engineering/ -v     # 10 files, ~63 functions
pytest tests/ -k "feature" -v                    # ~150+ functions across ~24 files
```

## 12. Known Structural Debt

- **Strategy files in FE:** `mean_reversion_strategy.py`, `md_amr_strategy.py`, `regime_mapping.py` belong in decision_making conceptually but are imported by DM. Moving them has high blast radius (~150 tests).
- **Hardcoded constants in strategy files:** BB/RSI/ATR defaults, dampening weights, flat regime thresholds are not config-overridable.
- **Two compute_sma functions:** `indicators.py` (list-based) and `pillar_indicators.py` (deque-based) — same math, different input types.
- **domain_dict.json version drift:** was 1.1.0 while `__init__.py` says 1.2.0. Resolved in v2.0.0 rewrite.
- **1 unconditionally skipped integration test** (`test_features_full_chain_happy.py`).
- **2 xfail tests** in `test_task24_feature_engineering_correctness.py` (P1-1, P1-2 regressions).

---
*Version: 1.0.0 — Created 2026-03-15 (FE-DOMAIN-AUDIT)*
