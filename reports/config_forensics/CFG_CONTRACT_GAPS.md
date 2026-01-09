# Forensic Report: Runtime Policy & Config Gaps
**Task ID:** TASK-CFG-REJECT-FORENSIC-03
**Date:** 2026-01-08

## 1. Startup vs. Runtime
The system employs a "Strict Contract" via `DomainConfigResolver`, which successfully enforces presence of *some* keys at startup (during `__init__`).

- **Validated on Startup:**
  - `domains` root key.
  - `strategies_registry` (if used).
  - High-level domain sections (`qos`, `position_sizing`).
  
- **NOT Validated on Startup (The Gap):**
  - **Deep Nested Keys:** Keys that are accessed dynamically based on runtime paths.
  - **Per-Symbol Overrides:** `strategies.aurora.assets.<SYMBOL>.max_risk_score`. Since the set of symbols might be dynamic or large, the resolver often lazily fetches these during execution.
  - **Conditional Configs:** Configs that are only accessed if a specific feature flag is enablement (e.g., `alpha_models` needing specific weight maps).

## 2. Why Runtime Errors Happen
Runtime `ConfigContractError` occurs because:
1. **Lazy Loading:** Python's `getattr` chain or dictionary lookups happen only when the specific code path (e.g., specific strategy logic) is executed.
2. **Dynamic Symbols:** The system may subscribe to a symbol that isn't fully defined in `strategies.aurora.assets` (if overrides are expected but missing).
3. **Fail-Closed Logic:** The code explicitly checks `if val is None: raise ConfigContractError` deep in the decision loop to avoid trading with undefined parameters (e.g. risk limits).

## 3. Can we `validate_all`?
**Yes, but it's hard.**
Writing a validator that iterates every possible symbol in the `strategies_registry` and pre-checks every required override in `aurora.assets` would prevent most runtime ghosts.

**Current State:**
There is **NO** universal `validate_all_required_on_startup` mechanism that walks the entire decision tree. Validation is fragmented between `ConfigLoader` (pydantic types) and `DomainConfigResolver` (structural presence).

## 4. Policy Recommendation
The runtime catch block is **necessary** as a defense-in-depth measure. Even with better startup validation, a "Fail-Closed" runtime guard is critical for financial safety. We cannot rely solely on startup checks.
