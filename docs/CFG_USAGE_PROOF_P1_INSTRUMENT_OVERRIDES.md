# CFG_USAGE_PROOF_P1_INSTRUMENT_OVERRIDES

**Date:** 2025-12-17
**Scope:** `apps/reference/domains` (decision_making, risk_management, execution_position)
**Pattern:** `getattr(obj, key, default)` or `dict.get(key, default)` affecting trade behavior.

## Executive Summary
Found **8** critical clusters of P1 violations where hardcoded defaults in runtime code override the Strict SSOT principle. These fallbacks prevent "fail-closed" behavior when config is missing.

## 1. Risk Management (Critical P1)

| File:Line | Pattern | Category | Risk | Recommended Fix |
| :--- | :--- | :--- | :--- | :--- |
| `daily_gate.py:71` | `.get("max_realized_loss_usd", "250")` | **P1-TRADE** | Silent fallback to 250 allows trading when safety gate missing. | Remove default. Raise `ValueError` if None. |
| `risk_management.py:536` | `.get("delta_price_pct", 0.1)` | **P1-TRADE** | Hardcoded weights alter risk score silently. | Use typed config. Fail if weights missing. |
| `risk_management.py:548` | `class DefaultWeights` | **P1-TRADE** | Explicit fallback class overrides SSOT. | **DELETE**. Fail-closed. |
| `risk_management.py:587` | `return decimal.Decimal("0.8")` | **P1-TRADE** | Hardcoded max risk score default. | **DELETE**. Fail-closed (Block trading). |
| `risk_management.py:88` | `.get('use_absorption_penalty', False)` | **P1-TRADE** | Feature flag fallback. | Explicit access. Fail if config is broken. |

## 2. Decision Making (Critical P1)

| File:Line | Pattern | Category | Risk | Recommended Fix |
| :--- | :--- | :--- | :--- | :--- |
| `decision_making.py:2735` | `.get("DEFAULT", "1.0")` | **P1-TRADE** | Hardcoded regime threshold multiplier. | Require strict map or fail. |
| `decision_making.py:3052` | `.get("fixed_bps", 50)` | **P1-TRADE** | Hardcoded SL default (0.5%). | **BLOCK** trade if SL config missing. |
| `decision_making.py:3068` | `.get("payoff_ratio_r", 1.5)` | **P1-TRADE** | Hardcoded Kelly R-ratio. | Use config value or None. |
| `decision_making.py:3474` | `getattr(tca, 'max_slippage_bps', 10)` | **P1-TRADE** | Execution quality fallback. | Use config value. |

## 3. P2 Diagnostic / State (Safe to Ignore)

| File:Line | Pattern | Category | Analysis |
| :--- | :--- | :--- | :--- |
| `exposure_guard.py:771` | `item.get("margin", 0)` | **P2-STATE** | Accessing internal state dict, not config. Safe. |
| `decision_making.py:2159` | `state["features"].get("ts", 0)` | **P2-DIAGNOSTIC** | Event payload parsing. Safe. |
| `risk_management.py:121` | `payload.get("symbol")` | **P2-DIAGNOSTIC** | Logging extra field. Safe. |

## 4. Contract Logic Proposal

**Principle:** "Config exists OR Trading Blocked"

### Rule 1: No In-Code Defaults
**BAD:**
```python
max_loss = cfg.get("max_loss", 250)
if max_loss is None: raise ValueError(...) # Never reached!
```

**GOOD:**
```python
max_loss = cfg.max_loss # Typed access
if max_loss is None:
    return False, {"reason": "CFG_REJECT", "detail": "max_loss_missing"}
```

### Rule 2: Tuning Flags
Feature flags (e.g., `use_absorption_penalty`) should treat `None` as `False` (Safe Default), but SHOULD NOT have defaults for numerical weights/thresholds.

### Rule 3: Error Codes
*   **`CFG_REJECT:<field_name>`** - Config missing for required field.
*   **`RISK_REJECT:<reason>`** - Logic blocked (safe state).
