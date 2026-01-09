# Forensic Report: NRR & Reject Pipeline
**Task ID:** TASK-CFG-REJECT-FORENSIC-02
**Date:** 2026-01-08

## 1. Canonical Rejection vs. Config Rejection

The system currently has two disconnected languages for "No":

| Feature | Canonical Rejection (NRR) | Config Rejection (CFG) |
| :--- | :--- | :--- |
| **Code Registry** | `NormalizedRejectReasons` (NRR-xxx) | `RejectReason` (CFG_MISSING/INVALID) |
| **Event** | `EVT:TRADE_INTENT_REJECTED` | None (Ghost) |
| **Visibility** | High (Events, Dashboards) | Low (Logs, Metrics) |
| **Handling** | Business Logic (Filters, Gates) | Exception Handling (Crash Prevention) |
| **Payload** | Structured JSON with `reason`, `details` | Log string `CFG_MISSING:path` |

## 2. NRR Pipeline Anatomy

The **Canonical NRR Pipeline** is robust and well-integrated.

### Registry
Located in `apps/reference/domains/decision_making/normalized_reject_reasons.py`.
Contains ~40 standard codes covering:
- Exchange errors (NRR-018)
- Risk limits (NRR-011)
- Data constraints (NRR-025 DATA_NOT_READY)
- Strategy logic (NRR-026 TREND_UNKNOWN)

### Emission Mechanism
The `DecisionMaking` domain uses a helper `_emit_trade_intent_rejected` to construct a standardized payload:

```json
{
  "reason_code": "NRR-011",
  "reason": "EXPOSURE_LIMIT_EXCEEDED",
  "symbol": "BTCUSDT",
  "details": { ... },
  "why": "intent_rejected:NRR-011"
}
```

This event is broadcast on the FSM bus and consumed by:
1. **Order Logger:** Writes to `order_log_v1.jsonl` (auditable history).
2. **Monitoring/Metrics:** Counts rejects by reason code.

## 3. Resolved: Config Integration (Active)
As of TASK-CFG-REJECT-INTEGRATE-01, this gap is closed.

### Mechanism
- **Gateway:** `ConfigContractError` -> `EVT:TRADE_INTENT_REJECTED` (Ref: `NRR-CFG-001/002`).
- **Feature Engine:** `ConfigContractError` -> `EVT:DECISION_BLOCKED` (New Health Event).

### New NRR Codes
- `NRR-CFG-001` (CONFIG_CONTRACT_MISSING)
- `NRR-CFG-002` (CONFIG_CONTRACT_INVALID)

## 4. Metrics Check
- **Previously:** Only `inc_config_contract_violation`.
- **Now:** Both `inc_config_contract_violation` AND `trade_intent_rejected_total` are incremented for gateway violations.

- **Exists:** `inc_config_contract_violation` (Specific to CFG)
- **Exists:** `trade_intent_rejected_total` (Labeled by `reason_code` from NRR)

**Problem:** `trade_intent_rejected_total` never sees CFG errors, creating a blind spot in the primary "Health" dashboard that relies on reject rates.
