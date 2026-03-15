# Red-Team Audit: Bootstrap Coldstart + MR Regression — Root Cause & Fix Package

## Root Cause Analysis

### Track A — Bootstrap / Hydration / Readiness Failure

**Live evidence**: `md_amr_handler:cold_start:51/96` means BNBUSDT received only 51 live 15m bars (~12.75 hours) against the 96-bar requirement (~24 hours).

**Root cause chain (code-proven)**:

1. [strategy_compatibility_matrix.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py) L217 hardcodes md_amr `basis_required_bars = max(96, channel_window_bars, atr_window, atr_stats_window) = 96`. TF = 900s (15m).
2. [startup_hydration_planner.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py) L232 correctly generates `SEED_HANDLER_BASIS_COUNTER` action for md_amr because `restart_local_basis_counter=True`.
3. [execute_startup_basis_hydration()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#213-434) at L288-329 fetches 15m bars from Binance via `PillarBackfillService.fetch_candles()`.
4. **FAILURE POINT**: If `fetch_result.success = False` (transient Binance error, empty candles), [hydrate_basis_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#71-141) returns 0 (L96-104). Then `imported_counts[(symbol, 900)]` = 0.
5. `seeded_bars = min(imported_counts[key], required_bars) = min(0, 96) = 0` → L351 `if seeded_bars <= 0: continue` → **[seed_startup_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#208-221) is NEVER called**.
6. Handler starts with `_bars_seen_since_restart[BNBUSDT] = 0` → cold-start gate blocks forever (takes 24h of live bars to reach 96).

**Why the previous fix "passed tests but failed live"**: The test [test_real_runtime_path_recovers_from_transient_startup_import_failures](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_basis_real_path.py#129-174) uses [_TransientBackfillAdapter](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_basis_real_path.py#58-73) which forces the *first* call to fail but the retry *within* [fetch_candles()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#111-262) succeeds on the second attempt. However:
- Live Binance can return `success=True` with `candles=[]` (empty response during maintenance/rate limit)
- The top-level [execute_startup_basis_hydration()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#213-434) has **NO retry** — it catches the exception but doesn't retry the fetch
- [pillar_backfill.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py) L245 [fetch_candles()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#111-262) has 3 retries for exceptions but NOT for `success=True` with empty candles

**Fix**: Add top-level retry in [execute_startup_basis_hydration()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#213-434) + improve [hydrate_basis_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#71-141) to handle the `success=True, candles=[]` edge case by returning a clear failure signal.

---

### Track B — Mean Reversion Profitability Regression

**Live evidence**: [bars_300s.tsv](file:///c:/Users/user/Music/Phenix/logs/mean_reversion/bars_300s.tsv) — ALL ~9,500 DOGEUSDT bars from 2026-02-10 to 2026-03-15 show `regime=UNCERTAIN`. ZERO signals were ever produced. MR has been completely non-functional for 33 days.

**Root cause chain (code-proven)**:

1. DOGEUSDT is assigned **only** to `mean_reversion` (not [aurora](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#99-125)) in [strategies.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies.yaml) L31-32.
2. MR handler's [_on_process_strategy()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py#1362-1631) receives 300s bars and passes them to `strategy.on_bar()`.
3. [on_bar()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/mean_reversion_strategy.py#336-411) at L377 calls `self.get_regime(symbol)` → returns "UNCERTAIN" (the default when no regime has been set).
4. L382: `flat_regime = map_to_flat_regime("UNCERTAIN", ...)` → returns `None` → L383 emits neutral signal `regime_not_flat:UNCERTAIN`.
5. **WHY**: The `RegimeDetector` emits `EVT:REGIME_DETECTED` only for symbols it's processing (typically those in `config.instruments`). MR handler listens to `EVT:REGIME_DETECTED` at L321 but the regime data for DOGEUSDT is never received or is always classified as non-FLAT.
6. Even if regime events arrive, the MR handler's [_on_regime_detected](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py#1151-1188) stores the regime, but if the regime is never FLAT (always UNCERTAIN/TRENDING), MR will never trigger.

**The regime backfill in [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py)** L1159 iterates `backfill_plan.symbols` — need to verify whether DOGEUSDT is included. The regime detector uses 5m bars for ATR calculation. If DOGE's ATR% is above the FLAT threshold, it's classified as TRENDING → MR blockers.

**Fix**: The regime detection issue for DOGE must be investigated at the [_on_regime_detected](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py#1151-1188) handler in MR (possibly the structural regime label normalization is dropping DOGE events), and the regime thresholds may need tuning.

---

## Proposed Changes

### Component 1: Bootstrap Retry Hardening

#### [MODIFY] [startup_basis_hydrator.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py)

1. Add top-level retry loop (3 attempts, 2s delay) around the [fetch_candles()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#111-262) + [hydrate_basis_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#71-141) call at L289-302
2. Add a guard: if `imported_counts[(symbol, tf_sec)] == 0` after all retries and `fetch_result.success` was True, emit a WARNING lifecycle event `STARTUP_BASIS_IMPORT_EMPTY`
3. Ensure `seeded_bars` falls through to the `restore_snapshot_bars` fallback path (L341-349) when import returned 0

#### [MODIFY] [pillar_backfill.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py)

1. Add validation in [fetch_candles()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/pillar_backfill.py#111-262): if `success=True` but `len(candles) == 0`, set `success=False` with `error="empty_response"` so upstream callers can detect this

---

### Component 2: MR Regime Detection Fix

#### [MODIFY] [mean_reversion_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py)

1. In [_on_regime_detected()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py#1151-1188): add detailed logging when DOGE regime events arrive (or don't arrive)
2. Add a diagnostic `get_regime_status()` method that reports the last regime and timestamp per symbol

#### [MODIFY] [regime_detector.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/regime_detector/regime_detector.py)

1. Verify that DOGEUSDT is included in the regime detector's symbol list
2. Ensure regime events are emitted for ALL symbols in `config.instruments`, not just strategy-assigned ones

> [!IMPORTANT]
> Before implementing Track B fixes, we need to verify: (a) whether `EVT:REGIME_DETECTED` events are emitted for DOGEUSDT at all, and (b) what regime label they carry. The 33-day "UNCERTAIN" streak strongly suggests DOGE regime events are either not emitted or are dropped by the structural regime normalization layer. The fix may be as simple as ensuring DOGE is in the regime detector's symbol list, or it may require regime threshold tuning.

---

### Component 3: Test Hardening

#### [NEW] [test_startup_basis_empty_fetch_recovery.py](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_basis_empty_fetch_recovery.py)

Test that [execute_startup_basis_hydration()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#213-434) retries on empty candle responses and produces correct readiness state.

#### [NEW] [test_mr_regime_propagation_contract.py](file:///c:/Users/user/Music/Phenix/tests/domains/decision_making/test_mr_regime_propagation_contract.py)

Test that MR handler correctly receives and processes `EVT:REGIME_DETECTED` for all enabled symbols.

#### [MODIFY] [test_startup_basis_real_path.py](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_basis_real_path.py)

Add a test case where [_TransientBackfillAdapter](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_basis_real_path.py#58-73) returns `success=True` but `candles=[]` (simulating the actual live failure pattern).

---

## Verification Plan

### Automated Tests

1. **Existing bootstrap tests** (should still pass):
   ```
   python -m pytest tests/bootstrap/test_startup_basis_real_path.py tests/bootstrap/test_startup_basis_hydrator.py -v
   ```

2. **Existing MR tests** (should still pass):
   ```
   python -m pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py tests/domains/decision_making/test_mean_reversion_runtime_readiness.py -v
   ```

3. **New tests** (must pass after fix):
   ```
   python -m pytest tests/bootstrap/test_startup_basis_empty_fetch_recovery.py -v
   python -m pytest tests/domains/decision_making/test_mr_regime_propagation_contract.py -v
   ```

4. **Full test suite regression** (no regressions):
   ```
   python -m pytest tests/ -x --timeout=120 -q
   ```

### Manual Verification

> [!NOTE]
> Track B requires live investigation. After implementing the regime detection fixes, the user should:
> 1. Check the regime detector's `feed_warmup_bar()` results for DOGEUSDT
> 2. Monitor [domain_mean_reversion.log](file:///c:/Users/user/Music/Phenix/logs/domain_mean_reversion.log) for regime changes from UNCERTAIN to a FLAT variant
> 3. Confirm MR signals are emitted for DOGEUSDT in the log
