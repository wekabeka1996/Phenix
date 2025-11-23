# Execution Position Runtime State

**Document ID:** EXEC-POS-RUNTIME-STATE
**Date:** 2025-11-21
**Last Updated:** 2025-11-21 (EP-LEGACY-PURGE-S1)
**Status:** Active

---

## Executive Summary

The execution_position domain uses **ExecPosRuntimeV2** as the sole active runtime.

Legacy `ExecPosFSM` and `runtime_mode="legacy"` have been removed (EP-LEGACY-PURGE-S1).

---

## 1. Active Runtime

**Component:** `ExecPosRuntimeV2` (Shadow V2 Runtime)

**Location:** `apps/reference/domains/execution_position/shadow_execpos/runtime.py`

**Factory:** `apps/reference/domains/execution_position/runtime_factory.py`

**Wiring:**
```
Events → MessageToRuntimeEventAdapter → ExecPosRuntimeV2 → Adapter (Binance/Simulated)
```

**Key Components:**
- **Gatekeeper:** Pre-execution safety checks (exposure, leverage, symbol state)
- **ExecutionService:** Order placement, management, idempotency
- **PositionService:** Position state tracking, reconciliation
- **Watchdog:** Timeout enforcement, bracket health checks
- **OrderGuardian:** Bracket lifecycle management (Aggregated OCO mode)

---

## 2. Configuration

**Config Path:** `config/domains/execution.yaml`

**Key:** `runtime_mode` is **not present** in config (no longer used).

**Behavior:** `runtime_factory.py` defaults to V2 and rejects legacy mode:
```python
if runtime_mode == "legacy":
    raise ValueError(
        "ExecPosFSM (legacy mode) has been removed. "
        "Please remove 'runtime_mode: legacy' from your configuration."
    )
```

---

## 3. Historical Context

**Legacy Runtime:** `ExecPosFSM` (monolithic state machine)

**Legacy Files:** `apps/reference/domains/execution_position/fsm.py` (removed)

**Migration:** EP-RUNTIME-WIRING-V2-S1 → EP-LEGACY-PURGE-S1

**Timeline:**
- 2025-11-15: ExecPosRuntimeV2 wired as active runtime
- 2025-11-21: Legacy ExecPosFSM fully removed (EP-LEGACY-PURGE-S1)

**See Also:**
- `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md` (historical migration plan)
- `docs/EP_LEGACY_PRESENCE_REPORT.md` (inventory of legacy references pre-purge)
- `docs/EP_LEGACY_PURGE_PLAN.md` (purge execution plan)

---

## 4. CI Guards

**Tests:** `tests/domains/execution_position/test_no_execpos_legacy_runtime.py`

**Purpose:** Prevent legacy reintroduction (fail CI if legacy code added).

**Checks:**
- Ensure `apps.reference.domains.execution_position.fsm` cannot be imported
- Ensure `runtime_factory` rejects `runtime_mode="legacy"`
- Ensure config does not contain `runtime_mode: legacy`

---

## 5. Observability

**Metrics Endpoint:** `/metrics` → `execpos_v2` section

**Key Metrics:**
- `execpos_v2_events_processed`
- `execpos_v2_orders_placed`
- `execpos_v2_gatekeeper_rejections`
- `execpos_v2_watchdog_violations`

**Logs:** All ExecPosRuntimeV2 activity logged with structured JSONL.

**See:** `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`

---

## 6. Next Steps / Future Work

- Continue stabilizing V2 runtime on testnet
- Expand test coverage for edge cases (bracket management, concurrency)
- Monitor drift metrics (shadow vs. real adapter behavior)

---

**Document Owner:** Engineering Team
**Maintainer:** Execution Domain Team
