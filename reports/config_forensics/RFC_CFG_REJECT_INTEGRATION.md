# RFC: Integration of Config Rejects (Additive-Only)
**Task ID:** TASK-CFG-REJECT-RFC-01
**Date:** 2026-01-08

## Problem Statement
`ConfigContractError` runtime exceptions currently result in a "Ghost Rejection": the system logs a critical error locally but fails to emit a `EVT:TRADE_INTENT_REJECTED` event. This makes these failures invisible to downstream analytics, dashboards, and the NRR (Normalized Reject Reasons) pipeline.

## Proposal: Integrate CFG Errors into NRR Pipeline

### Option A: Minimal Integration (Recommended)
**Design:**
Modify the `except ConfigContractError` blocks in `DecisionMaking.py` to:
1. Normalize the error (keep existing logic).
2. **ADD:** Call `self._emit_trade_intent_rejected(...)` with a new NRR code.

**Implementation Details:**
- Add `CONFIG_CONTRACT_VIOLATION = "NRR-CFG-001"` to `NormalizedRejectReasons`.
- In `DecisionMaking`:
```python
except ConfigContractError as e:
    reason = normalize_config_error(e)
    # ... existing log/metric ...
    
    # NEW: Emit Event
    self._emit_trade_intent_rejected(
        symbol=symbol,
        strategy_id=str(strategy_id),
        side=side, # may be unknown if error covers features
        rid=rid,
        reason_code=NormalizedRejectReasons.CONFIG_CONTRACT_VIOLATION,
        reason=reason, # "CFG_MISSING:domains.risk.max_risk_score"
        context="config_contract_catcher",
        details={"path": e.path, "why": e.why}
    )
    return
```

**Pros:**
- Low risk (additive changes only).
- Instant visibility in `order_log_v1.jsonl` and dashboards.
- Unified "Reason for No Trade" logic.

**Cons:**
- Requires reliable `side`/`strategy_id` context in the catch block (which is available in `strategy_gateway` but harder in `on_features`).

### Option B: Systemic Health Event
**Design:**
Create a new event type `EVT:SYSTEM_HEALTH_DEGRADED` specifically for config violations.

**Pros:**
- Separates "Business Rejects" (price/risk) from "Infrastructure Faults" (config).
- Can trigger paging/alerts differently.

**Cons:**
- Increases API/Schema surface area.
- Doesn't solve the "Why did THIS trade fail?" question in the trade log.

### Option C: Kill-Switch (Strict)
**Design:**
If a `ConfigContractError` occurs, immediately transition the `SystemState` to `STOPPED` or `HESITANT`.

**Pros:**
- Prevents trading in a potentially undefined risk state.
- Maximizes safety.

**Cons:**
- High blast radius: one bad symbol config kills the whole bot.
- Too aggressive for minor config misses (e.g. missing deprecated fields).

## Recommendation
**Proceed with Option A.**
It aligns the "Ghost" errors with the rest of the rejection ecosystem, providing immediate visibility with near-zero engineering cost and risk.
