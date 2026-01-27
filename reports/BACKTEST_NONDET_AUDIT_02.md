# BACKTEST_NONDET_AUDIT_02 — Forensic Non-Determinism Report

**Date:** 2026-01-22  
**Constraint:** Read-only audit (no code changes)

---

## 1) Repro-Protocol: RunA vs RunB Comparison

### Summary: NON-DETERMINISM CONFIRMED

Comparing two recent consecutive backtest runs from the same config (2023-05-14 to 2023-05-31):

| Metric | RunA (`170447`) | RunB (`171917`) | Delta |
|--------|-----------------|-----------------|-------|
| **Total Trades** | 16 | 7 | **-9** |
| **Total PnL** | -$293.26 | -$15.29 | **+$277.97** |
| **ROI %** | -29.33% | -1.53% | **+27.80%** |
| **Max Drawdown** | 12.49% | 0.99% | -11.50% |
| **Win Rate** | 16.67% | 50.00% | +33.33% |
| **End Balance** | $706.74 | $984.71 | +$277.97 |

**Regime Data:** Identical (4897 events, same counts_by_symbol)  
**Features Data:** Identical (4897 @ tf_sec=300, 4853 full_ready)

> **CAUTION:** The trading logic produces **completely different trade decisions** on identical input data.

---

## 2) RNG Audit

### Randomness Sources Found

| File | Line | Pattern | Used In |
|------|------|---------|---------|
| `backtest_engine/mock_broker.py` | 374 | `uuid.uuid4()` | Order ID generation |
| `tools/sim/regime_replay.py` | 59, 70, 94, 97 | `random.uniform()` | Test synthetic data |
| `tests/test_phase8_backtest.py` | 46, 79, 110+ | `random.uniform()` | Test fixtures |

### Seed Infrastructure

- **Neocortex domain only**: Has `set_global_seed()` in PPO module
- **Backtest engine**: **NO seed initialization**
- **Config**: No `rng_seed` in `trading.yaml` or `backtest` section

### Reseed Policy

| Question | Answer |
|----------|--------|
| Is there seed in config? | ❌ No |
| Is there reseed before each run? | ❌ No |
| Does uuid4() cause non-determinism? | ⚠️ Potentially |

---

## 3) State Leak Audit

### State Objects Summary

| Object | Reset Between Runs? |
|--------|---------------------|
| `MockBroker._orders` | ✅ (new instance) |
| `MockBroker._positions` | ✅ (new instance) |
| `FSMCore.listeners` | ✅ (new instance) |
| `DecisionMaking.symbol_states` | ✅ (new instance) |
| `DecisionMaking._qos_state` | ⚠️ Unclear |
| `MRHandler._last_signal_time` | ✅ (new handler) |

### Clock Analysis

- ✅ Clock IS reset to MockClock per run
- ✅ `reset_clock()` called in finally block

---

## 4) Ordering Audit

### Sorting Status

| File | Pattern | Stable? |
|------|---------|---------|
| `engine.py:113` | `sorted(path.glob())` | ✅ |
| `data_converter.py:94` | `sorted(list(set(files)))` | ✅ |

**No asyncio.gather() in backtest hot path.**

---

## 5) First Divergence Analysis

**Cannot pinpoint exact divergence** - logs lack per-bar intent/decision records.

**Hypothesis:** Cooldown timing differences based on event processing order.

---

## 6) Conclusions

### 🔴 Primary Cause: Event Processing Order Affects Clock State

The `MockClock` is advanced via event listeners. Different event order → different clock → different cooldown evaluations.

### 🟠 Secondary Causes

1. **Symbol Cooldown Logic** (`decision_making.py:1255-1261`)
2. **Bar Gating State** (`decision_making.py:336`)

---

## 7) Minimal Stabilization Plan

### Reset-Fixture List
- MockClock.set_time_ms(0)
- random.seed(SEED)  
- np.random.seed(SEED)

### Reseed Policy
Add to config:
```yaml
backtest:
  seed: 42
  reseed_per_run: true
```

### Ordering Policy
Sort events by: `(ts_ms, tf_sec, symbol, seq)`

### Determinism Mode Concept
```yaml
backtest:
  determinism_mode: strict
```

---

## Appendix: Report Paths

- **RunA:** `reports/backtests/backtest_20260122_170447.json`
- **RunB:** `reports/backtests/backtest_20260122_171917.json`

## Appendix: Suspicious Locations

| File | Line | Issue |
|------|------|-------|
| `mock_broker.py` | 374 | `uuid.uuid4()` |
| `decision_making.py` | 1255-1261 | Cooldown timing |
| `decision_making.py` | 336 | Bar gating |
| `main.py` | 539-543 | Clock advance callback |
