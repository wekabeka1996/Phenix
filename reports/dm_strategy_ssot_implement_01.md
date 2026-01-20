# DM-STRATEGY-SSOT-IMPLEMENT-01 Report

**Date**: 2026-01-13
**Ticket**: DM-STRATEGY-SSOT-IMPLEMENT-01
**Depends-on**: dm_strategy_ssot_fixplan_01.md

---

## Summary

Implemented all fixes identified in the SSOT alignment audit. All 4 issues (P0-1, P0-2, P0-3, P1-1) are now resolved.

---

## Changes Made

### P0-1: MR → Gateway EntryPlan ATR mismatch ✅

**File**: [mean_reversion_handler.py](../apps/reference/domains/decision_making/mean_reversion_handler.py)

**Problem**: Gateway EntryPlan rejects MR signals with `atr_ready=False` because volatility/liquidity data wasn't propagated.

**Fix**:
1. Added `_last_cmd_features: Dict[str, Dict[str, Any]] = {}` cache (line ~148)
2. Modified `on_process_strategy()` to cache full features per-symbol (lines ~893-904)
3. Modified `_emit_signal()` to inject volatility/liquidity from cache into signal payload (lines ~591-620)

**Test**: MR signals now include `volatility: {atr_ready: True, atr_normalized: ...}` and `liquidity` fields.

---

### P0-2: Aurora motion_window_sec 900 → 300 ✅

**File**: [config/aurora/strategies/aurora.yaml](../config/aurora/strategies/aurora.yaml#L145)

**Problem**: `motion_window_sec: 900` references a non-existent schema field. Schema only defines `pm_norm_10s`, `pm_norm_60s`, `pm_norm_300s`.

**Fix**: Changed `motion_window_sec: 900` to `motion_window_sec: 300` with comment explaining the SSOT alignment.

---

### P0-3: Aurora price_motion phantom ✅

**File**: [aurora_handler.py](../apps/reference/domains/decision_making/aurora_handler.py)

**Problem**: Aurora vol-adj gates call `_get_motion_norm_sigma()` but `CMD:PROCESS_STRATEGY` payload doesn't include `price_motion` — only `EVT:FEATURES_CALCULATED` does.

**Fix**:
1. Added `cached_price_motion: Optional[Dict[str, Any]] = None` to `SymbolState` dataclass (lines 67-69)
2. Modified `on_features_data_only()` to cache `price_motion` from `EVT:FEATURES_CALCULATED` (lines 482-499)
3. Modified `_get_motion_norm_sigma()` to fall back to `state.cached_price_motion` when CMD features don't have it (lines 993-1010)

---

### P1-1: Aurora registry SSOT check ✅

**File**: [aurora_handler.py](../apps/reference/domains/decision_making/aurora_handler.py)

**Problem**: `_is_symbol_enabled()` only checked `aurora.assets.<symbol>.enabled`, ignoring `strategies_registry.assignments`. This caused Aurora to emit signals for DOGE/XRP (MR-only symbols), resulting in ARBITRATION_BLOCKED noise.

**Fix**: Modified `_is_symbol_enabled()` to check `strategies_registry.assignments` FIRST (SSOT), then fall back to legacy `aurora.assets.enabled` check (lines 801-825).

**Test Validation**: All 11 tests in `test_aurora_respects_registry.py` PASSED:
- `test_aurora_disabled_for_mr_only_symbol`
- `test_aurora_enabled_for_assigned_symbol`
- `test_xrp_also_disabled_for_aurora`
- `test_legacy_behavior_returns_true_for_mr_only_symbol`
- `test_aurora_does_not_emit_signal_for_mr_only_symbol`
- `test_gateway_never_sees_doge_from_aurora`
- `test_registry_is_canonical_source`
- `test_aurora_assets_is_secondary_kill_switch`
- `test_mean_reversion_already_uses_registry`
- `test_hybrid_symbol_assigned_to_both`
- `test_arbitration_handles_hybrid_correctly`

---

## Test Results

### Mean Reversion Tests
```
17 passed, 2 xfailed
```
All MR tests pass. The xfail are expected (logging tests marked as xfail).

### Aurora Registry Tests
```
11 passed
```
All registry-related tests pass, confirming P1-1 implementation works correctly.

### Pre-existing Issues (Not Related to This PR)

The following test failures existed before these changes and are unrelated:
- `test_anti_churn_harden.py` - 5 failures (anti-churn feature not fully implemented)
- `test_aurora_handler.py::test_skips_when_warmup_not_ready` - test setup issue
- `test_aurora_holding_period.py` - 2 failures (monotonic/wall time injection issues)
- `test_aurora_tick_gating.py` - 2 failures (tick path rejection counter not wired)

---

## Files Modified

| File | Changes |
|------|---------|
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | +25 lines (P0-1) |
| `config/aurora/strategies/aurora.yaml` | 1 line (P0-2) |
| `apps/reference/domains/decision_making/aurora_handler.py` | +25 lines (P0-3, P1-1) |

---

## Verification Commands

```bash
# Run MR tests
pytest tests/domains/decision_making/test_mean_reversion*.py -v

# Run Aurora registry tests
pytest tests/domains/decision_making/test_aurora_respects_registry.py -v

# Validate schema compliance
python -m vfoundation.cli.vfound dict validate
```

---

## SSOT Alignment Status

| Issue | Status | Evidence |
|-------|--------|----------|
| P0-1: MR volatility propagation | ✅ FIXED | Signal payload includes volatility/liquidity |
| P0-2: motion_window_sec | ✅ FIXED | Uses 300s (schema-valid) |
| P0-3: price_motion cache | ✅ FIXED | Falls back to EVT cache |
| P1-1: Registry precedence | ✅ FIXED | 11 tests pass |

---

## Next Steps

1. Address pre-existing test failures in separate tickets
2. Consider adding integration test for full MR→Gateway→EntryPlan flow
3. Monitor logs for ARBITRATION_BLOCKED on DOGE/XRP (should be eliminated)
