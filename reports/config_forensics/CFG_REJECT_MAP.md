# Forensic Report: Reject Reasons Usage Map
**Task ID:** TASK-CFG-REJECT-FORENSIC-01
**Date:** 2026-01-08

## Executive Summary
The system currently uses a dual-track rejection mechanism.
1. **Business Logic Rejections (Standard):** Handled via `NormalizedRejectReasons` (NRR) and emitted as `EVT:TRADE_INTENT_REJECTED`.
2. **Configuration Contract Violations (Hidden):** Handled via `RejectReason` (reject_reasons.py) and `ConfigContractError`. These are **silently blocked** (logged but not emitted as events), creating "ghost" rejections where trading logic halts without a trace in the event stream.

## Detailed Map: ConfigContractError Handling

### 1. DecisionMaking: Feature Calculation
**Location:** `apps/reference/domains/decision_making/decision_making.py` : ~Line 1744 (in `on_features`)

- **Context:** Processing incoming `EVT:FEATURES_CALCULATED`.
- **Trigger:** Any `ConfigContractError` raised during feature processing or alpha model execution.
- **Action:**
  - `normalize_config_error(e)` -> Generates `CFG_MISSING:path` string.
  - `inc_config_contract_violation(...)` -> Increments Prometheus metric.
  - `logger.critical(...)` -> Logs the error.
  - `_record_blocked_intent(...)` -> Updates internal blocked/dropped counters.
  - **RETURN** -> Stops execution immediately.
- **Side Effects:**
  - **No `EVT:TRADE_INTENT_REJECTED` emitted.**
  - **No `EVT:INTENT_DEFERRED` emitted.**
  - The pipeline silently terminates for this tick.

### 2. DecisionMaking: Strategy Signal Gateway
**Location:** `apps/reference/domains/decision_making/decision_making.py` : ~Line 908 (in `_on_strategy_signal_gateway`)

- **Context:** Processing `EVT:STRATEGY_SIGNAL_PRODUCED` (Strict Sequential Contract).
- **Trigger:** Config errors during strategy arbitration, risk checks, or sizing calculation (e.g., accessing `max_risk_score` override).
- **Action:**
  - `normalize_config_error(e)`
  - `inc_config_contract_violation(...)`
  - `logger.critical(...)`
  - `_record_blocked_intent(...)`
  - **RETURN**
- **Side Effects:**
  - **No event emission.**
  - Strategy signal is effectively swallowed.

### 3. RiskManagement: Risk Calculation (Source)
**Location:** `apps/reference/domains/risk_management/risk_management.py`

- **Context:** `calculate_risk` methods.
- **Behavior:** Raises `ConfigContractError` when critical limits or thresholds are missing from `risk_management` domain config.
- **Handling:** If this runs within the main loop, it likely crashes the Risk worker unless caught by a generic `Exception` handler at the loop level (which usually just logs error and continues).

## Code Evidence
```python
# decision_making.py snippet
except ConfigContractError as e:
    # TASK 17: Central Interception Point
    reason = normalize_config_error(e)
    caught_symbol = e.symbol or symbol
    inc_config_contract_violation(path=e.path or "unknown", symbol=caught_symbol or "unknown")
    self.logger.critical(f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
    if caught_symbol:
        self._record_blocked_intent(caught_symbol)
    return  # <--- GHOST EXIT (No Event Emitted)
```

## Conclusion: "Where the Ghosts Live"
The "ghosts" are entirely located in the `DecisionMaking` domain's catch blocks. Any configuration error during runtime results in a silent drop of the trading opportunity. While metrics exist (`config_contract_violation`), they are often not monitored as closely as the `TRADE_INTENT_REJECTED` event stream, leading to confusion about why the system is "quiet".
