# Execution Position Runtime Migration Plan (Revised)

**Document ID:** EP-RUNTIME-SWITCH-PLAN-REV-S1
**Date:** 2025-11-20
**Status:** ✅ **MIGRATION COMPLETE** (2025-11-21)
**Purpose:** Define strategy for "Direct V2 on Testnet" migration

---

## ✅ MIGRATION COMPLETE (2025-11-21)

**Status:** Legacy `runtime_mode="legacy"` has been removed in **EP-LEGACY-PURGE-S1**.

**ExecPosRuntimeV2 is the only active runtime.** Attempting to set `runtime_mode="legacy"`
will raise a ValueError.

This document is preserved for historical context on the migration strategy.

**See:** `docs/EXEC_POS_RUNTIME_STATE.md` for current runtime state.

---

## Executive Summary

This revised plan outlines the strategy for adopting `ExecPosRuntimeV2` (shadow) as the **active runtime** for the execution_position domain on the OWNER's local testnet environment.

**Key Strategic Shift:** Instead of running complex dual-mode (legacy + shadow) on a single machine, we will switch directly to `v2` mode for testnet, keeping `legacy` available as a config-based fallback.

---

## 1. Runtime Modes

### 1.1 Configuration Key

**Proposed Config Path:**
```
execution_position.runtime_mode: "legacy" | "v2" | "dual_future"
```

**Config Source:**
- Config v2 YAML
- Environment variable override: `EP_RUNTIME_MODE`
- Default: `"legacy"` (safe fallback)

### 1.2 Mode Definitions

#### Mode: `legacy` (DEFAULT)
- **Behavior:** Only `ExecPosFSM` is instantiated.
- **Status:** Current production behavior.
- **Use Case:** Production default, rollback state for testnet.
- **Wiring:** Events → ExecPosFSM → Real Adapter.

#### Mode: `v2` (TESTNET TARGET)
- **Behavior:** Only `ExecPosRuntimeV2` is instantiated. `ExecPosFSM` is NOT instantiated.
- **Status:** Target state for OWNER's testnet.
- **Use Case:** Active development and validation on testnet.
- **Wiring:** Events → EventAdapter → ExecPosRuntimeV2 → Real Adapter.

#### Mode: `dual_future` (RESERVED)
- **Behavior:** Both runtimes instantiated.
- **Status:** Reserved for future phases (e.g., staging environment with more resources).
- **Use Case:** Advanced validation if needed later.
- **Wiring:** Events → Both Runtimes (one active, one observe-only).

---

## 2. Wiring & Architecture

### 2.1 Current Legacy Wiring
- **Entry Point:** `ExecPosFSM.handle(msg)`
- **Event Source:** `vfoundation.core.protocol.Message` (via event bus)
- **Dependencies:**
  - Inbound: Decision/Risk messages
  - Outbound: `binance_adapter` (or `sim_adapter`)

### 2.2 V2 Wiring (New)
- **Entry Point:** `ExecPosRuntimeV2.handle(event)`
- **Adapter Layer:** `MessageToRuntimeEventAdapter` (New Component)
  - Responsibilities:
    - Receive `vfoundation.core.protocol.Message`
    - Convert to `shadow_execpos.types.RuntimeEvent`
    - Call `ExecPosRuntimeV2.handle()`
  - **Crucial:** This is the ONLY place where message mapping occurs.

**Data Flow (V2 Mode):**
```
Upstream (Bus)
    ↓
Message (CMD:OPEN, etc.)
    ↓
MessageToRuntimeEventAdapter
    ↓
RuntimeEvent (ENTRY_INTENT, etc.)
    ↓
ExecPosRuntimeV2
    ↓
Shadow Components (Gatekeeper, ExecutionService, etc.)
    ↓
Real Adapter (binance_adapter)
```

---

## 3. Migration Phases (Revised)

### Phase M0: Current State [COMPLETE]
- `ExecPosFSM` is live production runtime.
- `ExecPosRuntimeV2` exists in shadow, tested via replay harness.
- No production wiring changes yet.

### Phase M1: Direct V2 on Testnet
- **Goal:** Make `ExecPosRuntimeV2` the active runtime on OWNER's testnet.
- **Actions:**
  1. Implement `runtime_mode` flag and factory logic.
  2. Implement `MessageToRuntimeEventAdapter`.
  3. Wire `v2` mode in domain bootstrap.
  4. Set `runtime_mode="v2"` in OWNER's local config.
- **Exit Criteria:** Testnet operates normally using V2 runtime (entries, exits, cancels).

### Phase M2: Stabilized V2 & Optional Dual Future
- **Goal:** Deepen validation and prepare for potential production use.
- **Actions:**
  1. Extended scenario testing on testnet (brackets, edge cases).
  2. (Optional) Implement `dual_future` if rigorous AB comparison is required on staging.
- **Exit Criteria:** V2 runtime proven stable and feature-complete for production needs.

### Phase M3: Production V2 Switch
- **Goal:** Migrate production to V2.
- **Strategy:** To be designed based on M1/M2 results (likely canary rollout).

---

## 4. Safety & Rollback

### 4.1 Testnet Safety
- **Risk:** Low (testnet funds).
- **Requirements:**
  - V2 passes all offline replay tests.
  - Basic manual verification of trading flows (Entry, SL, Cancel, Close).
- **Rollback:**
  - Change config: `runtime_mode="legacy"`
  - Restart service.

### 4.2 Future Production Safety
- **Requirements:**
  - Extended automated test suite (including edge cases).
  - Canary deployment (if supported by infra).
  - Comprehensive metrics monitoring.

---

## 5. Observability

### 5.1 Metrics
- Ensure `ExecPosRuntimeV2` exports key metrics:
  - `events_processed`
  - `orders_placed`
  - `gatekeeper_rejections`
  - `watchdog_violations`

### 5.2 Logs
- Log active runtime mode on startup: `INFO: Execution Position Runtime Mode: v2`
- Log all adapter calls in V2 for debugging.

---

## 6. Next Steps

1. **[EP-RUNTIME-WIRING-V2-S1]** Implement `runtime_mode` flag and `MessageToRuntimeEventAdapter`.
2. **[EP-RUNTIME-EVENT-ADAPTER-S2]** Wire V2 into main entrypoint and verify on testnet.

---

**Document Owner:** Engineering Team
**Last Updated:** 2025-11-20
