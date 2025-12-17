# CFG-AUDIT-FULL-12: Configuration System Forensic Audit

**Date:** 2025-12-17
**Auditor:** Antigravity (Principal Engineer)
**Scope:** `config/aurora/`, `apps/reference/config_loader.py`, `apps/reference/config_models.py`

## 1. Executive Summary

The Configuration System is **90% SSOT-compliant**, centered around a robust `ConfigLoader` that enforces canonical paths for key configurations. However, several "soft" violations (duplicates, `extra='allow'`) persist.

*   **SSOT Confidence Score:** **9/10** (High).
*   **Canonical Loader:** `apps.reference.config_loader.ConfigLoader` is the single effective entry point.
*   **Critical Gaps:**
    *   1 Orphaned legacy file (`features.yaml`).
    *   Partial Strictness: Many Pydantic models still use `extra='allow'`, permitting drift.
    *   Duplicate definitions of `symbols_to_track` across `system.yaml` and `trading.yaml`.

## 2. CONFIG ARTIFACTS MAP (Load Graph)

| Artifact File | Loaded By (Loader) | Merged Into (Key) | Pydantic Model (Strictness) | Consumed By |
| :--- | :--- | :--- | :--- | :--- |
| `system.yaml` | `_load_yaml` | `root` | `SystemConfig` (Forbid) | Core infra, Logging, Hawkes |
| `trading.yaml` | `_load_yaml` | `root` (Strategy/Decisions) | `TradingConfig` (Forbid) | DecisionMaking, Execution |
| `regime.yaml` | `_load_yaml` | `root` (Regimes) | `RegimeDetectorConfig` (Allow) | `RegimeDetector` |
| `domains.yaml` | `_load_yaml` | `domains` (SSOT) | `DomainsConfig` (Forbid) | Domain Resolvers |
| `instruments.yaml` | `_load_yaml` | `instruments` (SSOT) | `Dict[str, InstrumentSpec]` (Allow) | `Execution`, `MarketData` |
| `strategies.yaml` | `_load_yaml` | `strategies_registry` (SSOT) | `StrategiesRegistryConfig` (Forbid) | `StrategiesRegistry` |
| `strategies/{id}.yaml` | Registry Logic | `root.{id}` | `MeanReversion1mStrategyConfig` (Allow) | Strategy Logic |
| `aurora_instruments.yaml`| `_load_yaml` | `aurora_instruments` (SSOT) | `Dict[str, AuroraInstrumentConfig]` (Forbid) | `DecisionMaking` |
| `features.yaml` | **NOT LOADED** | **ORPHAN** | N/A | **DEPRECATED** |

## 3. Fallbacks & Fail-Open Audit

| Location | Pattern | Risk | Severity | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| `config_loader.py:36` | `AuroraConfig.get(key, default)` | Silent default override | P2 | Deprecate `.get()`, enforce strict attribute access. |
| `config_loader.py:326` | `try...except FileNotFoundError` | Silent fallback to legacy paths | P3 | Remove exception handler for `domains.yaml` (Strict Mode should fail). |
| `config_loader.py:177` | `_extract_active_symbols` | Priority Chain (Shadowing) | P3 | Simplify. Force `instruments.yaml` as sole source. |

## 4. Duplicates & Overwrites Matrix

| Key Path | Winning Source | Losing Source | Detected by Strict? | Fix Strategy |
| :--- | :--- | :--- | :--- | :--- |
| `trading.symbols_to_track` | `trading.yaml` | `system.yaml` | No | Remove from `system.yaml` (orphaned there). |
| `domains` | `domains.yaml` | `trading.yaml` | **YES** (Loader warns/fails) | Keep Strict Mode=1. |
| `instruments` | `instruments.yaml` | `trading.yaml` | **YES** (Loader warns/fails) | Keep Strict Mode=1. |
| `aurora_instruments` | `aurora_instruments.yaml`| `trading.yaml` | **YES** (Loader warns/fails) | Keep Strict Mode=1. |

## 5. Strict Contracts (Pydantic)

### 5.1 `extra='allow'` Inventory (Risk of Config Drift)
The following models allow undefined keys, violating the "Strict Contract" principle:
*   `InstrumentSpec` (Low risk, exchange compat)
*   **`MeanReversion1mStrategyConfig`** (High risk, strategy logic)
*   `RegimeDetectorConfig` (Medium risk)
*   `FeatureEngineeringConfig` (Medium risk)
*   `MarketDataConfig` (Medium risk)
*   `ExposureConfig` (High risk - financial limits)

### 5.2 `Dict[str, Any]` Surface Area
*   `FeatureEngineeringConfig`: `ema`, `volume`, `volatility`, `liquidity` are all `Dict[str, Any]`. **Critical Typed-Plan needed.**

## 6. Orphan YAML List
1.  **`config/aurora/features.yaml`**: Exists but ignored.
    *   *Action*: Delete.

## 7. Fix Pack Proposals

### CFG-FIXPACK-01: Cleanup Orphans & Duplicates
*   **Scope**: Delete `features.yaml` and remove `symbols_to_track` from `system.yaml`.
*   **Files**: `config/aurora/features.yaml`, `config/aurora/system.yaml`
*   **Risk**: Low.

### CFG-FIXPACK-02: Enforce Strict Strategy Contracts
*   **Scope**: Change `MeanReversion1mStrategyConfig` to `extra='forbid'`.
*   **Files**: `apps/reference/config_models.py`
*   **Risk**: Medium (Schema validation failure if unused keys exist).

### CFG-FIXPACK-03: Remove Legacy Fallbacks
*   **Scope**: Remove `try/except` around `domains.yaml` loading in `ConfigLoader`. Enforce existence.
*   **Files**: `apps/reference/config_loader.py`
*   **Risk**: Medium (Boot failure if config missing).

---
**Verdict:** The system is mature and safe, with `ConfigLoader` doing heavy lifting. Primary remaining work is cleaning up `extra='allow'` laziness and deleting the one orphan file.
