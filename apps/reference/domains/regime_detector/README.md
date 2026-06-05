# regime_detector — Domain README

> **Authoritative domain documentation.** For auto-generated docs see `docs/` (may be stale).

## 1. Purpose

`regime_detector` is a **market regime classifier**. It consumes feature data, runs a priority-based detection cascade, applies hysteresis stabilisation and a volatility slope gate, then emits `EVT:REGIME_DETECTED` with the stable per-symbol regime on every basis bar close.

**It does NOT own strategy decisions, position sizing, or regime-based TP/SL.**

## 2. Responsibility Boundary

Owns:
- Regime classification (6 labels: TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY, UNCERTAIN)
- Priority cascade: Volatility > MeanReversion > SMATrend > UNCERTAIN
- Hysteresis stabilisation (configurable confirmation bars)
- Volatility slope gate (suppress dying HIGH_VOL storms)
- Data quality gating (stale/missing → UNCERTAIN, buffers untouched)
- Per-symbol rolling buffers (price, TR, ATR)
- Warmup backfill via `feed_warmup_bar()`

Does NOT own:
- Regime-based trading decisions (→ decision_making)
- Regime-based TP/SL (→ decision_making/regime_tpsl)
- Regime allowlist enforcement (→ decision_making/readiness_gates)
- Regime multiplier smoothing (→ decision_making/regime_smoother)
- REGIME_SHIFT_SUSPECTED event (→ decision_making)

## 3. Architecture

```
EVT:FEATURES_CALCULATED ──→ handle_event()
  ├── BAR-ONLY filter: tf_sec == basis_tf_sec only
  ├── Data quality gates (stale/missing → UNCERTAIN early return)
  ├── Buffer update: price_buf, tr_buf, atr_buf
  ├── Priority cascade:
  │   ├── P1: Volatility (ATR/baseline ratio → HIGH_VOL / LOW_VOL)
  │   ├── P1a: Slope gate (dying storm → suppress HIGH_VOL)
  │   ├── P2: Mean reversion (SMA spread + price deviation < threshold)
  │   └── P3: SMA trend (SMA crossover + price confirmation)
  ├── Data quality override (drops → UNCERTAIN)
  ├── uncertain_cutoff demote (low confidence → UNCERTAIN)
  ├── Hysteresis stabilisation (N bars confirmation)
  └── EVT:REGIME_DETECTED { regime, confidence, changed, warmup, ... }
```

### Heartbeat pattern
`EVT:REGIME_DETECTED` is emitted on **every** basis bar close, not just transitions. The `changed` flag indicates actual regime transitions. `last_update_ts_ms` (monotonic) enables liveness checking by downstream consumers.

## 4. Events

### Consumed (1)

| Event | Source | Handler |
|-------|--------|---------|
| `EVT:FEATURES_CALCULATED` | feature_engineering | `handle_event` — processes only when `tf_sec == basis_tf_sec` |

### Emitted (1)

| Event | Target | Purpose |
|-------|--------|---------|
| `EVT:REGIME_DETECTED` | decision_making | Stable regime + confidence + warmup state + heartbeat data |

## 5. File Map (2 source files, 803 LOC)

| File | LOC | Role |
|------|-----|------|
| `regime_detector.py` | 793 | Core: detection cascade, hysteresis, slope gate, warmup backfill |
| `__init__.py` | 10 | Package init, sets `__version__` |

### Schemas (1)
| File | Event |
|------|-------|
| `schemas/regime_detected_v1.json` | `EVT:REGIME_DETECTED` — 6 regime labels, warmup, data_quality, heartbeat fields |

## 6. Regime Labels (raw strings)

| Label | Trigger | Source Model |
|-------|---------|-------------|
| `TREND_UP` | SMA_short > SMA_long AND price > SMA_short | `sma_trend_v1` |
| `TREND_DOWN` | SMA_short < SMA_long AND price < SMA_short | `sma_trend_v1` |
| `MEAN_REVERSION` | SMA spread + price deviations < threshold | `mean_reversion_v2` |
| `HIGH_VOLATILITY` | ATR/baseline > threshold_multiplier | `volatility_v2` |
| `LOW_VOLATILITY` | ATR/baseline < low_vol_multiplier | `volatility_v2` |
| `UNCERTAIN` | Default / stale data / low confidence / slope gate suppression | various |

**Note:** Labels are raw strings, not a shared Enum class. Schema enforces at `regime_detected_v1.json` level.

## 7. Fail-Closed Rules

- **Dict config → TypeError** (enforces AuroraConfig object)
- **Missing `models` → ConfigContractError** (no silent fallback)
- **Missing volatility fields → ConfigContractError** (exhaustive attribute check)
- **Stale features → UNCERTAIN** (buffers NOT updated, P0-1 fix)
- **Missing price → silent return** (no emission, no buffer update)
- **Data quality drops → UNCERTAIN** (regime overridden)
- **Low confidence < uncertain_cutoff → UNCERTAIN** (demoted)
- **Slope gate → UNCERTAIN** (dying HIGH_VOL storm suppressed)

## 8. Config Dependencies

| Config Path | Purpose |
|-------------|---------|
| `basis_tf_sec` | Bar timeframe filter (default 300 = 5m) |
| `uncertain_cutoff` | Confidence threshold for regime demotion |
| `hysteresis_bars` | Consecutive confirmation bars for stable transition |
| `vol_slope_gate_enabled` | Enable/disable slope gate |
| `vol_slope_gate_eps` | Slope threshold for dying storm detection |
| `vol_slope_gate_confirm_bars` | Bars to confirm slope rejection |
| `models.sma_trend.*` | SMA periods, confidence multiplier/min/max |
| `models.volatility.*` | ATR period, baseline, thresholds, confidence multipliers |
| `models.mean_reversion.*` | Threshold, confidence multiplier |
| `system.market_data.bar_ttl_ms` | Staleness threshold for bar events |
| `system.market_data.tick_ttl_ms` | Staleness threshold for tick events |

All loaded from `regime.yaml` via AuroraConfig (Pydantic-typed, `extra='forbid'`).

## 9. Cross-Domain Coupling

| Direction | What | Why |
|-----------|------|-----|
| RD → vfoundation | Message (protocol) | Event wrapping |
| RD → config | AuroraConfig, ConfigContractError | Typed config |
| RD → contracts | RuntimeBarSourceMode, RuntimeRegimeLayer, RuntimeRegimeScope, RuntimeRegimeClock, structural_regime_ref | Regime layering contract |
| RD → telemetry | inc_data_quality_drop | Metrics side-channel |
| FE → RD | EVT:FEATURES_CALCULATED | Event-driven input |
| DM ← RD | EVT:REGIME_DETECTED | Event-driven output |

**No direct imports FROM regime_detector in any other domain.**

## 10. Forbidden Patterns

- Do NOT emit regime from any domain other than regime_detector
- Do NOT bypass hysteresis for regime transitions
- Do NOT add silent permissive fallbacks — stale/missing data must yield UNCERTAIN
- Do NOT use regime_detector for strategy decisions — that belongs to decision_making
- Do NOT hardcode regime labels outside the schema enum list
- Do NOT add a global regime concept — regime is per-symbol, bar-clocked

## 11. Testing

```bash
pytest tests/domains/regime_detector/ -v           # 3 test files, ~27 functions
pytest tests/ -k "regime" -v                       # ~18 files, ~181 functions
```

**Total test surface:** ~18 files, ~181 test functions.

## 12. Known Structural Debt

- Regime labels are raw strings — no shared Enum class (schema-only enforcement)
- `__init__.py` does not re-export `RegimeDetector` (only sets `__version__`)
- `docs/deprecated/` contains 6 stale files including old `domain_dict.json`
- 1 unconditionally skipped integration test (`test_regime_detector_event_flow.py`: needs BAR-ONLY mock payload fix)
- `bar_ttl_ms` silently defaults to 10000 via `getattr` (minor config opacity)

---
*Version: 1.0.0 — Created 2026-03-14 (RD-DOMAIN-AUDIT)*
