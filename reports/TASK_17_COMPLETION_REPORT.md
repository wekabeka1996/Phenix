
# Task 17 Completion Report: Config Contract Enforcement & Normalization

## Overview
This task (Task 17) focused on enforcing a Strict Configuration Contract within the P1 Critical Path (Decision Making & Risk Management). The goal was to eliminate silent failures, remove "magic number" defaults, and ensure that any configuration variability results in a deterministic, normalized block of trading activity.

## Key Achievements

### 1. Centralized Interception ("The Catcher")
We implemented a single failure handling mechanism at the entry points of the `DecisionMaking` domain:
- **Location**: `on_features` (Aurora Signals) and `_on_mr_signal_gateway` (MR Signals).
- **Mechanism**: A `try/except ConfigContractError` block wraps the entire signal processing logic.
- **Behavior**:
  - Catches any `ConfigContractError` raised by deep dependencies (Position Sizing, Risk, Strategy Registry).
  - **Blocks the Trade**: Prevents emission of `EVT:TRADE_INTENT_PROPOSED`.
  - **Normalizes Error**: Converts the exception into a standard string using `normalize_config_error` (e.g., `CFG_MISSING:trading.decision.kelly.base_probability`).
  - **Metrics**: Increments `config_contract_violation_total` with label `path`.

### 2. Standardization of Rejection Reasons
- **New Registry**: `apps/reference/contracts/reject_reasons.py`.
- **Why**: To prevent log pollution with random string messages and to allow downstream systems (FSM, Dashboard) to aggregate rejection reasons reliably.
- **Codes**: `CFG_MISSING`, `CFG_INVALID`.

### 3. Formalized AST Strictness Policy
- **New Policy File**: `tests/policies/config_strictness_policy.py`.
- **Purpose**: explicitly defines what constitutes a "safe default" (e.g., `False` for flags, `0.0` for confidence scores, `UNKNOWN` for logs) and what is forbidden (numeric constants like `1.0`, `50`, `100` that affect trading logic).
- **Enforcement**: Refactored `tests/runtime/test_p1_instrument_overrides_no_fallbacks.py` to import and apply this policy during CI/CD static analysis.

### 4. P1 Critical Path Cleanliness
- **Fail-Closed Enforcement**:
  - **Risk Management**: Removed default weights and thresholds. Missing risk config now blocks trading.
  - **Decision Making**: Removed defaults for Regime Multipliers, SL/TP BPS, and Kelly Criterion parameters.
- **Zero AST Violations**: All P1 files passed the strict AST analysis.

## Verification Results

### Automated Tests
1.  **Block Normalization Test** (`tests/runtime/test_config_contract_block_normalization.py`):
    - **Passed**: Confirmed that a simulated missing config deep in the call stack results in a blocked trade and a correctly labeled metric increment.
2.  **AST Compliance Test** (`tests/runtime/test_p1_instrument_overrides_no_fallbacks.py`):
    - **Passed**: Confirmed that `RiskManagement` and `DecisionMaking` contain no forbidden config access patterns.
3.  **Regression Suite**:
    - **Passed**: All existing config tests (Schema, Loading, SSOT) passed.

## Next Steps
- **Monitoring**: Add alerts based on `config_contract_violation_total > 0`.
- **Expansion**: Apply similar strictness to P2 paths (Execution, Market Data) in future tasks.
