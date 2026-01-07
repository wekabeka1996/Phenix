
# Incident Report: ETHUSDT Silent Drop (2026-01-05)

## 1. Executive Summary
**Date:** 2026-01-05
**Incident:** Valid trade intent for `ETHUSDT` (Score 0.1099 > 0.105) was generated in DecisionMaking logs but failed to open an order.
**Severity:** Critical (Valid signals dropped silently).
**Status:** ✅ RESOLVED.

## 2. Root Cause Analysis
During the analysis of `domain_decision_making.log` and `aurora_core.log` around 12:47:27, it was observed that `ETHUSDT` passed all strategy gates (Signal Score > Threshold, Risk Gate = True) and a "Proposed" JSON log was written. However, the intent never reached the Execution Bridge.

**Trace of Failure:**
1.  **Selection:** ETHUSDT signal (0.1099) passed the threshold.
2.  **JSON Log:** `log_decision(...)` successfully wrote the intent to `domain_decision_making.log`.
3.  **Crash Point:** The code proceeded to call `self._record_accepted_intent(symbol)`.
    *   This helper method performs `self.intents_seen_total += 1`.
    *   **The Bug:** The attribute `self.intents_seen_total` was **not initialized** in `__init__`.
    *   **Result:** `AttributeError` was raised.
4.  **Silent Death:** The exception occurred *before* `self.fsm.emit("EVT:TRADE_INTENT_PROPOSED")`. The unhandled exception interrupted the execution flow for that symbol tick. Due to the async/threaded nature of the FSM listeners, the exception did not propagate to a visible crash log (or was swallowed by a generic handler without logging).

## 3. Separation of Concerns (XRP vs ETH)
*   **XRP/DOGE/BTC:** These were correctly blocked by business logic.
    *   XRP: `Regime UNKNOWN` (Safety Gate).
    *   BTC: `Neutral Signal` (Score < Threshold).
    *   DOGE: `Neutral Signal`.
*   **ETH:** This was the **only** symbol that encountered the technical bug, as it was the only one to **pass** all gates and attempt to record acceptance.

## 4. Resolution and Fix
The following fixes were applied to `apps/reference/domains/decision_making/decision_making.py`:

1.  **State Initialization:**
    *   Added initialization of `intents_seen_total`, `intents_blocked_total`, and `last_alert_check_time` in `__init__`.
    
2.  **Defensive Programming:**
    *   Wrapped the `_record_accepted_intent()` call in a `try/except` block.
    *   **Rationale:** Monitoring/Telemetry failures must **never** block the Critical Trading Path. Even if metrics fail, the trade intent MUST be emitted.

3.  **Verification:**
    *   Created `tests/unit/decision_making/test_monitoring_safety.py`.
    *   Verified that `DecisionMaking` initializes correctly and `_record_accepted_intent` no longer crashes.

## 5. Next Steps
*   **Monitor:** Observe the next run. ETH signals should now successfully convert to `EVT:TRADE_INTENT_PROPOSED` and be processed by the Bridge.
*   **Recommendation:** User should consider lowering `signal_threshold` for BTC/ETH (e.g., to 0.08) if they wish to see more volume, as many signals are hovering just below the current 0.105 cutoff.
*   **Recommendation:** User should address the `Trend UNKNOWN` state for XRP/DOGE (via config `allowed_regimes`) if trading is desired in that state.
