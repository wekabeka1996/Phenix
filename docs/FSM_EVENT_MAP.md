# System Event Map (SSOT)

This document serves as the Single Source of Truth for system events, complementing the auto-generated `PROJECT_ATLAS.md`. It defines the contract, schema, and semantics of critical events used for decision making, risk, and health monitoring.

## 1. Decision Making Events

### `EVT:DECISION_BLOCKED`
**Description:**  
Emitted when the decision-making process is halted prematurely due to configuration errors, critical health checks, or other blockers that prevent an intent from being formed. This is a **Health Signal** indicating that the pipeline could not proceed to evaluation.

**Payload Schema:**
- `schema_version`: `int` (default: 1)
- `symbol`: `str` - The symbol being processed.
- `stage`: `str` - The pipeline stage where blockage occurred (e.g., `on_features`).
- `reason_code`: `str` - Standardized NRR code (e.g., `NRR-CFG-001`).
- `reason`: `str` - Human-readable reason string.
- `path`: `str` - Configuration path or resource identifier involved in the error.
- `why`: `str` - Short explanation (≤80 chars) suitable for logs/metatags.
- `ts_ms`: `int` - Timestamp in milliseconds.

**Semantics:**
- Unlike `EVT:TRADE_INTENT_REJECTED`, this event implies **no intent was even calculated**.
- Should be treated as a system degradation or misconfiguration alert.

**Related Metrics:**
- `decision_blocked_total{stage, reason_code}`

### `EVT:TRADE_INTENT_REJECTED`
**Description:**
Emitted when a trading intent was proposed (or clearly intended) but rejected by a specific gate (Risk, QoS, Strategy Arbitration, Config).

**Payload Fields (Key subset):**
- `reason_code`: `NRR-xxx`
- `reason`: Detailed string.
- `context`: Where the rejection happened (e.g., `strategy_signal_gateway`).

---

## 2. Risk Management Events

*(Placeholder for future expansion)*
