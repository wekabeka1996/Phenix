# EP-STAB-LIVEPOS-AGG-OCO-AUDIT: Executive Summary

**Date**: 2025-11-19
**Investigation**: SL-spam phenomenon (system repeatedly places new SL for already-protected positions)
**Status**: ✅ **Complete (Phase 1)** — Root cause identified, documented, tested

---

## The Issue

After opening position and placing normal aggregated bracket (TP + SL):
- System repeatedly places **new SL orders**
- Position is already protected → spam is incorrect
- Watchdog auto-heal triggers repeatedly
- Retry counter eventually triggers `AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED` (5 retries max)
- But after 60s cooldown, loop can restart → extended spam

---

## Root Cause (HIGH Confidence)

**Divergent exit-order classification** causes false NO_SL_FOR_OPEN_POSITION detection:

| Component | Exit-Order Logic | Used For |
|-----------|------------------|----------|
| **Contracts** (canonical) | Type in {STOP_MARKET, TAKE_PROFIT_MARKET} **OR** reduceOnly=true **OR** closePosition=true | Domain reference, high-level logic |
| **Watchdog** (heuristic) | Type includes "STOP" **OR** clientOrderId ends "_sl" **OR** stopPrice!=0 | Invariant validation (NO_SL detection) |

### Mismatch Example
```
LIMIT order + reduceOnly=true + no stopPrice field:
  → is_exit_order() = True    ✅ (logically reduces position)
  → _is_sl_order() = False    ❌ (no STOP type, no stopPrice)
  → Watchdog sees: "No SL found" → NO_SL_FOR_OPEN_POSITION violation
  → Auto-heal places new SL → Position already had protection → SPAM
```

---

## Evidence

### 1. Architecture Audit (Section A)
- **Responsibility map**: Identified 4 main components (ExecPosFSM, ManageFlowFSM, OrderGuardian, bracket_aggregator)
- **Duplicate check**: Found divergent exit-order classification (HIGH RISK)
- **Finding**: Two independent implementations, no synchronization

### 2. Invariant & Retry Analysis (Section B)
- **NO_SL_FOR_OPEN_POSITION**: Uses divergent `_is_sl_order()` classifier
- **Auto-heal retry**: 5 attempts per 60-second window, then reset → allows restart
- **Finding**: Divergence + retry reset = potential infinite spam after 60s cooldown

### 3. Regression Tests (Section C)
- **3 PASSED** ✅:
  - Happy path: Normal bracket → 3 watchdog cycles → SL count stable [2,2,2]
  - Multiple SL: Correctly detects TOO_MANY_SL invariant
  - State lag: Temporary NO_SL due to async lag resolves next cycle

- **2 XFAILED** (expected, documented):
  - LIMIT+reduceOnly classification mismatch **CONFIRMED**
  - Canonical vs. heuristic inconsistency **CONFIRMED**

### Test Results
```
tests/domains/execution_position/test_agg_oco_sl_spam_regression.py
  ✅ test_agg_oco_no_spam_after_bracket_placement PASSED
  ❌ test_agg_oco_divergent_classification_detects_spam XFAIL
  ✅ test_agg_oco_detects_multiple_sl_spam PASSED
  ✅ test_agg_oco_watchdog_cycles_with_state_lag PASSED
  ❌ test_is_exit_order_vs_is_sl_order_consistency XFAIL

  Result: 3 passed, 2 xfailed in 0.88s
```

---

## Impact

| Scenario | Impact | Timeline |
|----------|--------|----------|
| Position with LIMIT+reduceOnly protection | System places new SL (false positive) | Every 5s watchdog cycle |
| Protection count | 1 → 2 → 3... SL accumulation | Until 5-retry limit hit (25s) |
| Recovery | Loop stopped by circuit breaker | At 60s cooldown boundary |
| Restart risk | Counter resets, can restart spam | Every 60s if watchdog still sees NO_SL |

---

## Recommended Fixes (Phase 2)

### Immediate (HIGH Priority)
1. **Consolidate exit-order classification**:
   - Replace `_is_sl_order()` with call to canonical `is_exit_order()`
   - Or pass order dict to `is_exit_order()` from watchdog
   - Single source of truth → eliminate divergence

### Short-term (MEDIUM Priority)
2. **Add explicit success tracking**:
   - After bracket placement succeeds, set flag in Guardian or ManageFlowFSM
   - Watchdog checks flag before emitting NO_SL
   - Prevents re-triggering heal if state lags

3. **Strengthen retry semantics**:
   - Replace 60s window with exponential backoff
   - Require N successful cycles without violation before unlock
   - Add metrics: retry count, reset frequency, spam episodes

### Observability (MEDIUM Priority)
4. **Instrumentation**:
   - Log which SL orders watchdog considered + classification
   - Compare with canonical is_exit_order() for debugging
   - Alert on divergent classifications

---

## Artifacts

✅ **docs/EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md** (7 sections: A-D + appendix)
- A.1: Responsibility map
- A.2: Duplicate logic check (divergence table)
- B.1-B.3: Invariant definitions + retry semantics
- B.4-B.5: Success detection + root cause hypothesis
- C.1-C.3: Test design + results + conclusions
- D.1-D.3: Duplicate assessment + root cause + recommended fixes
- Appendix: Detailed classification logic comparison

✅ **tests/domains/execution_position/test_agg_oco_sl_spam_regression.py** (313 lines)
- 5 test cases covering: happy path, divergence detection, multiple SL, state lag, classification consistency
- 3 PASS + 2 XFAIL (expected, documented)
- Ready for regression suite

✅ **JOURNAL.md entry**
- RID: EP-STAB-LIVEPOS-AGG-OCO-AUDIT
- Summary + audit scope + findings + artifacts

✅ **TODO.md update**
- Task added: [EP-STAB-LIVEPOS-AGG-OCO-AUDIT] (Phase 1 complete, Phase 2 pending)
- Phase 1: Comprehensive audit ✅
- Phase 2: Root cause fix (pending)

---

## Next Steps

**Phase 2 (To Execute)**:
1. Fix divergent classification (consolidate to `is_exit_order()`)
2. Add success tracking to prevent re-detection
3. Strengthen retry semantics (exponential backoff)
4. Add instrumentation (detailed logging + metrics)
5. Run full regression suite (existing + new tests)
6. Production deployment + monitoring (SL spam rate → 0%)

**Success Criteria**:
- SL spam incidents → 0% (no repeated SL for same position)
- Watchdog accuracy → 99%+ (NO_SL violations only when truly unprotected)
- Auto-heal efficiency → <3 retries per recovery (currently up to 5)

---

**Document Status**: Complete (Phase 1)
**Ready for**: Code review, Phase 2 implementation planning
**Validation**: 3 tests passing (happy path confirmed), 2 xfails documenting divergence (root cause confirmed)
