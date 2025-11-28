# Execution Position Domain — Deep Audit & Simplification Strategy

> **Principal Engineer / Lead Architect Audit**
> **RID:** `EP-AUDIT-SIMPLIFY-S1`
> **Date:** 2025-01-XX
> **Author:** Principal Engineer Review
> **Status:** ACTIONABLE

---

## 📊 Executive Summary

| Metric | Value |
|--------|-------|
| **Total Production Files** | 41 |
| **Total LOC (Production)** | ~14,580 |
| **Test Files** | 44 |
| **God Objects Identified** | 2 |
| **Duplicate Systems** | 3 |
| **Legacy Code Paths** | ~2,000 LOC |
| **Estimated Removable LOC** | ~3,500-4,500 |
| **Simplification Priority** | HIGH |

### Critical Findings

1. **ExecPosRuntimeV2** (2,099 LOC) — God Object; handles 12+ distinct responsibilities
2. **Dual Config Systems** — V2 Pydantic + legacy dict fallback (~50% overlap)
3. **Dual Watchdog Systems** — Root `watchdog.py` (543 LOC) + `shadow_execpos/watchdog.py` (309 LOC)
4. **Legacy Mode Dead Code** — `runtime_mode: "legacy"` removed but config paths remain

---

## 1. File Registry & Inventory

### 1.1 Production Files by Module

#### Root Level (`apps/reference/domains/execution_position/`)
| File | LOC | Type | Purpose | Complexity |
|------|-----|------|---------|------------|
| `binance_execution_adapter.py` | 1,693 | Adapter | REST/WS Binance integration | HIGH |
| `manage_config.py` | 876 | Config | Hybrid V2/legacy resolver | HIGH |
| `contracts.py` | 808 | Models | Pydantic V2 contracts | LOW |
| `watchdog.py` | 543 | Service | Order timeout monitoring | MEDIUM |
| `utils.py` | 542 | Utility | ClientOrderId, price math | LOW |
| `metrics_collector.py` | 412 | Metrics | Performance telemetry | LOW |
| `runtime_factory.py` | 375 | Factory | V2RuntimeFacade builder | MEDIUM |
| `config.py` | 280 | Config | V2 Pydantic SSOT | LOW |
| `metrics_aggregator.py` | 271 | Metrics | Aggregated metrics | LOW |
| `idempotent_cancel.py` | 246 | Utility | Cancel idempotency helper | LOW |
| `drift_monitor.py` | 221 | Observability | Shadow-mode validation | LOW |
| `brackets_config.py` | 215 | Config | Bracket config dataclasses | LOW |
| `simulated_adapter.py` | 210 | Test | Mock adapter for testing | LOW |
| `algo_order_index.py` | 148 | Index | Algo order state mgmt | LOW |
| `order_index.py` | 126 | Index | Order reference tracking | LOW |
| `adapter_factory.py` | 70 | Factory | Adapter selection | LOW |
| `utils_event_bus.py` | 58 | Utility | Local event bus | LOW |
| `internal_types.py` | 49 | Types | Internal DTOs | LOW |
| `execution_adapter.py` | 30 | ABC | AbstractExecutionAdapter | LOW |
| `__init__.py` | 1 | - | Package marker | - |

**Subtotal Root:** ~8,126 LOC

#### Shadow ExecPos (`shadow_execpos/`)
| File | LOC | Type | Purpose | Complexity |
|------|-----|------|---------|------------|
| `runtime.py` | 2,099 | **GOD OBJECT** | Main V2 orchestrator | **CRITICAL** |
| `bracket_service.py` | 957 | Service | Pure bracket logic | MEDIUM |
| `execution_service.py` | 742 | Service | Adapter facade | MEDIUM |
| `watchdog.py` | 309 | Service | Agg-OCO watchdog | MEDIUM |
| `async_manager.py` | 240 | Infra | Async loop management | LOW |
| `wal_writer.py` | 235 | DR | WAL persistence | LOW |
| `gatekeeper.py` | 228 | Guard | Entry validation | LOW |
| `logging_v2.py` | 199 | Observability | Structured logging | LOW |
| `event_adapter.py` | 197 | Adapter | Message→Event transform | LOW |
| `ab_replay.py` | 192 | DR | A/B replay testing | LOW |
| `trailing.py` | 161 | Service | Trailing stop logic | LOW |
| `agg_oco_replay.py` | 158 | DR | Aggregated OCO replay | LOW |
| `position_model.py` | 155 | Model | Position state evolution | LOW |
| `exposure_bridge.py` | 131 | Bridge | ExposureGuard integration | LOW |
| `idempotency.py` | 128 | Guard | Fill/event deduplication | LOW |
| `close_flow.py` | 93 | Service | Close decision logic | LOW |
| `price_enricher.py` | 82 | Utility | Price enrichment | LOW |
| `types.py` | 71 | Types | Runtime event types | LOW |
| `__init__.py` | 7 | - | Package exports | - |

**Subtotal Shadow:** ~6,384 LOC

---

## 2. Architecture Map & Dependency Graph

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ENTRY POINTS                                 │
├─────────────────────────────────────────────────────────────────────┤
│  OrchestratorFSM  ←───────→  V2RuntimeFacade (runtime_factory.py)   │
│       ↓                              ↓                               │
│  FSM Interface (legacy)      Native V2 Interface                     │
└──────────────────────────────────────┬──────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ExecPosRuntimeV2 (2,099 LOC)                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Responsibilities (12+):                                      │   │
│  │ • Event routing (ENTRY/CANCEL/CLOSE intents)                │   │
│  │ • Position state management                                  │   │
│  │ • Order snapshot caching & TTL                              │   │
│  │ • Stale mode recovery                                       │   │
│  │ • Bracket evaluation orchestration                          │   │
│  │ • Guard loop execution                                      │   │
│  │ • Fill idempotency                                          │   │
│  │ • WAL integration                                           │   │
│  │ • Metrics emission                                          │   │
│  │ • Lifecycle (start/stop/hydrate)                            │   │
│  │ • Mirror order tracking                                     │   │
│  │ • Config resolution                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
          ┌───────────────────────────────┼───────────────────────────┐
          │                               │                           │
          ▼                               ▼                           ▼
┌─────────────────┐         ┌─────────────────────┐       ┌───────────────────┐
│ BracketService  │         │ ExecutionService    │       │ AggOcoWatchdog    │
│   (957 LOC)     │         │    (742 LOC)        │       │    (309 LOC)      │
│                 │         │                     │       │                   │
│ Pure computation│         │ Adapter facade      │       │ Bracket invariant │
│ No side effects │         │ Retry logic         │       │ monitoring        │
│                 │         │ Error normalization │       │                   │
└────────┬────────┘         └──────────┬──────────┘       └─────────┬─────────┘
         │                             │                            │
         │                             ▼                            │
         │              ┌──────────────────────────┐                │
         │              │ BinanceExecutionAdapter  │                │
         │              │     (1,693 LOC)          │                │
         │              │                          │                │
         │              │ • REST API calls         │                │
         │              │ • Order placement        │                │
         │              │ • Position queries       │                │
         │              │ • Algo order mgmt        │                │
         │              │ • WS event parsing       │                │
         │              └──────────────────────────┘                │
         │                                                          │
         └──────────────────────────────────────────────────────────┘
```

### 2.2 Config System Layers (Problematic)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CONFIG RESOLUTION PATH                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  config.yaml  ────────────────────────────────────────────────────▶ │
│       │                                                             │
│       ├──▶  config.py (280 LOC)                                    │
│       │     ExecutionPositionConfig (Pydantic V2)                  │
│       │     ├── AggregatedOcoConfig                                │
│       │     ├── TrailingConfig                                     │
│       │     ├── CloseConfig                                        │
│       │     └── SnapshotConfig                                     │
│       │                                                             │
│       └──▶  manage_config.py (876 LOC)  ◀──── **HYBRID**           │
│             ├── _build_manage_from_v2()    (V2 path)               │
│             └── _build_manage_from_legacy() (Legacy fallback)      │
│                                                                     │
│                      ALSO:                                          │
│             ├── brackets_config.py (215 LOC)  ◀──── Dataclasses    │
│             └── runtime._get_snapshot_cfg()   ◀──── Inline resolve │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 Watchdog System Duplication

```
┌─────────────────────────────────────┬───────────────────────────────┐
│ ROOT: watchdog.py (543 LOC)         │ SHADOW: watchdog.py (309 LOC) │
├─────────────────────────────────────┼───────────────────────────────┤
│ OrderTimeoutWatchdog                │ AggOcoWatchdogService         │
│ • REST polling for order status     │ • Wraps BracketService        │
│ • Timeout detection                 │ • Invariant violation check   │
│ • RPS throttling                    │ • Converts BracketPlan →      │
│ • Meta tracking                     │   WatchdogRecommendation      │
├─────────────────────────────────────┼───────────────────────────────┤
│ **USED BY:** Legacy/external?       │ **USED BY:** ExecPosRuntimeV2 │
├─────────────────────────────────────┼───────────────────────────────┤
│ **OVERLAP:** ~40% logic duplication │                               │
└─────────────────────────────────────┴───────────────────────────────┘
```

---

## 3. Code Smell Identification

### 3.1 🔴 CRITICAL — God Object

**File:** `shadow_execpos/runtime.py`
**Class:** `ExecPosRuntimeV2`
**LOC:** 2,099
**Responsibilities:** 12+

#### Symptoms:
- Single class handles orchestration, state management, caching, recovery, metrics
- 50+ methods in one class
- Multiple state dictionaries (`_positions_by_symbol`, `_open_orders_by_symbol`, `_bracket_status`, etc.)
- Tightly coupled to all sub-services

#### Evidence:
```python
class ExecPosRuntimeV2:
    def __init__(self, ...):
        # 15+ instance variables for state
        # 8 service dependencies
        # Multiple caches and TTL trackers

    # Event handlers
    async def handle_entry_intent(...)
    async def handle_cancel_intent(...)
    async def handle_close_intent(...)
    async def handle_trade_executed(...)
    async def handle_orders_snapshot(...)
    async def handle_position_snapshot(...)

    # State management
    def _update_position_state(...)
    def _mark_orders_snapshot(...)
    def _is_orders_snapshot_fresh(...)

    # Stale mode recovery
    def _enter_stale_mode(...)
    def _exit_stale_mode(...)
    async def _stale_recovery_loop(...)

    # Bracket evaluation
    async def _evaluate_brackets(...)
    async def _apply_bracket_plan(...)
    async def _cancel_stale_brackets(...)

    # ... 30+ more methods
```

### 3.2 🟠 HIGH — Duplicate Config Systems

**Files:** `config.py` (280), `manage_config.py` (876), `brackets_config.py` (215)
**Total:** ~1,371 LOC for config alone
**Duplication:** ~50% semantic overlap

#### Evidence from `manage_config.py`:
```python
# Line 44
_ALLOWED_MANAGE_MODES = {"legacy", "aggregated_only"}

# Line 697-704 — Legacy mode validation
if mode == "legacy":
    if aggregated_oco.enabled or aggregated_oco.aggregated_only_mode:
        raise ConfigError(
            "mode=legacy requires aggregated_oco.enabled=false..."
        )

# Line 727 — Legacy fallback builder
def _build_manage_from_legacy(config: Any) -> ExecutionManageConfig:
    """Legacy path builder: constructs from old dict-based config."""
```

### 3.3 🟠 HIGH — Dual Watchdog Systems

**Files:**
- `watchdog.py` (543 LOC) — `OrderTimeoutWatchdog`
- `shadow_execpos/watchdog.py` (309 LOC) — `AggOcoWatchdogService`

#### Confusion Points:
- Both handle order/bracket monitoring
- Both emit recommendations/actions
- Root watchdog appears to be for external/legacy use
- Shadow watchdog is for ExecPosRuntimeV2

### 3.4 🟡 MEDIUM — Dead Legacy References

**Evidence:**
```python
# runtime_factory.py:47-50
if runtime_mode == "legacy":
    raise RuntimeError(
        "ExecPosFSM (legacy mode) has been removed. "
        "Please remove 'runtime_mode: legacy' from your configuration."
    )
```

Legacy mode is **removed** but config validation paths still exist in `manage_config.py`.

### 3.5 🟡 MEDIUM — Adapter Facade Redundancy

**ExecutionService** (742 LOC) wraps **BinanceExecutionAdapter** (1,693 LOC):
- ExecutionService adds retry logic, error normalization
- But BinanceExecutionAdapter already has internal retry/error handling
- Net: 2 layers of error handling

### 3.6 🟢 LOW — Unused Test Utilities

**File:** `simulated_adapter.py` (210 LOC)
- Used only in tests
- Could be moved to `tests/` directory

---

## 4. Subtraction Opportunities

### 4.1 Priority Matrix

| Opportunity | LOC Savings | Risk | Effort | Priority |
|-------------|-------------|------|--------|----------|
| Remove legacy config paths | ~400 | LOW | 2d | **P0** |
| Consolidate watchdogs | ~300 | MEDIUM | 3d | **P1** |
| Extract RuntimeV2 into sub-managers | ~800 | MEDIUM | 5d | **P1** |
| Remove dead `runtime_mode: legacy` refs | ~50 | LOW | 1d | **P0** |
| Move simulated_adapter to tests/ | ~210 | LOW | 0.5d | **P2** |
| Merge config.py + manage_config.py | ~400 | MEDIUM | 3d | **P1** |
| Simplify ExecutionService layer | ~200 | MEDIUM | 2d | **P2** |

### 4.2 Safe Deletions (No Behavioral Change)

```
1. manage_config.py: _build_manage_from_legacy() and related functions (~150 LOC)
   Condition: After verifying no configs use legacy paths

2. manage_config.py: Legacy mode validation (~50 LOC)
   Condition: After removing _build_manage_from_legacy

3. runtime_factory.py: Legacy mode error path (5 LOC)
   Condition: Cosmetic cleanup

4. watchdog.py (root): OrderTimeoutWatchdog (543 LOC)
   Condition: After confirming AggOcoWatchdogService covers all use cases
```

### 4.3 Consolidations

```
1. Config SSOT:
   - DELETE: manage_config.py legacy paths
   - DELETE: brackets_config.py (merge into config.py)
   - KEEP: config.py as sole source

2. Watchdog:
   - DELETE: watchdog.py (root)
   - ENHANCE: shadow_execpos/watchdog.py with timeout logic

3. Runtime Decomposition:
   - EXTRACT: StateManager from ExecPosRuntimeV2 (~400 LOC)
   - EXTRACT: SnapshotManager from ExecPosRuntimeV2 (~300 LOC)
   - EXTRACT: StaleRecoveryService from ExecPosRuntimeV2 (~200 LOC)
```

---

## 5. Subtraction-First Strategy

### Phase 1: Safe Removals (Week 1)
```
EP-SIMPLIFY-01: Remove dead legacy config paths
EP-SIMPLIFY-02: Remove runtime_mode legacy references
EP-SIMPLIFY-03: Move simulated_adapter to tests/
```

### Phase 2: Consolidations (Week 2-3)
```
EP-SIMPLIFY-04: Merge brackets_config.py into config.py
EP-SIMPLIFY-05: Consolidate watchdog systems
EP-SIMPLIFY-06: Simplify ExecutionService error handling
```

### Phase 3: Decomposition (Week 3-4)
```
EP-SIMPLIFY-07: Extract StateManager from RuntimeV2
EP-SIMPLIFY-08: Extract SnapshotManager from RuntimeV2
EP-SIMPLIFY-09: Extract StaleRecoveryService from RuntimeV2
```

---

## 6. Refactoring Tasks (EP-SIMPLIFY-XX)

### EP-SIMPLIFY-01: Remove Legacy Config Paths

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-01 |
| **Scope** | `manage_config.py` |
| **LOC Impact** | -400 |
| **Risk** | LOW |
| **Effort** | 2 days |
| **Dependencies** | Config audit to verify no legacy mode usage |

**Actions:**
1. Grep all YAML configs for `mode: legacy`
2. Delete `_build_manage_from_legacy()` function
3. Delete `_resolve_orphan_monitor()`, `_resolve_quick_profit()`, `_resolve_trailing()`, `_resolve_emergency()` legacy helpers
4. Remove legacy mode validation in `_validate_and_transform_aggregated_oco_config()`
5. Update `resolve_execution_manage_config()` to remove fallback logic

**Validation:**
- All existing tests pass
- No config loading errors
- Manual config load test

---

### EP-SIMPLIFY-02: Remove Dead runtime_mode References

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-02 |
| **Scope** | `runtime_factory.py`, tests |
| **LOC Impact** | -50 |
| **Risk** | LOW |
| **Effort** | 1 day |
| **Dependencies** | None |

**Actions:**
1. Remove `if runtime_mode == "legacy"` block from `build_execution_runtime()`
2. Update docstrings that reference legacy mode
3. Update any tests that explicitly test legacy mode error

**Validation:**
- pytest passes
- No references to `runtime_mode: legacy` in codebase

---

### EP-SIMPLIFY-03: Relocate Test Utilities

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-03 |
| **Scope** | `simulated_adapter.py` |
| **LOC Impact** | -210 (from production) |
| **Risk** | LOW |
| **Effort** | 0.5 days |
| **Dependencies** | None |

**Actions:**
1. Move `simulated_adapter.py` to `tests/domains/execution_position/fixtures/`
2. Update imports in test files
3. Remove from production `__init__.py` exports

**Validation:**
- All tests using SimulatedExecutionAdapter still pass

---

### EP-SIMPLIFY-04: Consolidate Config Models

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-04 |
| **Scope** | `config.py`, `brackets_config.py` |
| **LOC Impact** | -150 |
| **Risk** | MEDIUM |
| **Effort** | 2 days |
| **Dependencies** | EP-SIMPLIFY-01 |

**Actions:**
1. Migrate unique dataclasses from `brackets_config.py` to `config.py`
2. Convert remaining dataclasses to Pydantic models
3. Delete `brackets_config.py`
4. Update all imports

**Validation:**
- Schema validation tests pass
- Config loading tests pass

---

### EP-SIMPLIFY-05: Consolidate Watchdog Systems

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-05 |
| **Scope** | `watchdog.py`, `shadow_execpos/watchdog.py` |
| **LOC Impact** | -300 |
| **Risk** | MEDIUM |
| **Effort** | 3 days |
| **Dependencies** | None |

**Actions:**
1. Audit root `watchdog.py` usage in codebase
2. If unused externally: DELETE root `watchdog.py`
3. If used: Migrate unique features to `shadow_execpos/watchdog.py`
4. Rename `shadow_execpos/watchdog.py` to `bracket_watchdog.py` for clarity

**Validation:**
- Watchdog integration tests pass
- No orphaned bracket violations in testnet
- Guard loop timing unchanged

---

### EP-SIMPLIFY-06: Simplify ExecutionService

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-06 |
| **Scope** | `shadow_execpos/execution_service.py` |
| **LOC Impact** | -200 |
| **Risk** | MEDIUM |
| **Effort** | 2 days |
| **Dependencies** | None |

**Actions:**
1. Remove duplicate error normalization (already in BinanceAdapter)
2. Simplify `_call_adapter()` method
3. Remove Mock detection logic (lines 90-95)
4. Consolidate `_classify_place_error()` with adapter's classification

**Validation:**
- Order placement tests pass
- Error handling tests pass

---

### EP-SIMPLIFY-07: Extract StateManager

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-07 |
| **Scope** | `shadow_execpos/runtime.py` |
| **LOC Impact** | ~-400 (extracted, not deleted) |
| **Risk** | MEDIUM |
| **Effort** | 3 days |
| **Dependencies** | None |

**Actions:**
1. Create `shadow_execpos/state_manager.py`
2. Extract:
   - `_positions_by_symbol` management
   - `_open_orders_by_symbol` management
   - `_bracket_status` tracking
   - Position state update methods
3. Inject StateManager into ExecPosRuntimeV2

**Validation:**
- All runtime tests pass
- State consistency tests pass

---

### EP-SIMPLIFY-08: Extract SnapshotManager

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-08 |
| **Scope** | `shadow_execpos/runtime.py` |
| **LOC Impact** | ~-300 (extracted) |
| **Risk** | MEDIUM |
| **Effort** | 2 days |
| **Dependencies** | EP-SIMPLIFY-07 |

**Actions:**
1. Create `shadow_execpos/snapshot_manager.py`
2. Extract:
   - `_last_orders_snapshot_ts` tracking
   - `_last_position_snapshot_ts` tracking
   - `_is_orders_snapshot_fresh()`
   - `_is_position_snapshot_fresh()`
   - Snapshot refresh hook management
3. Inject SnapshotManager into ExecPosRuntimeV2

**Validation:**
- Snapshot TTL tests pass
- Bracket evaluation timing unchanged

---

### EP-SIMPLIFY-09: Extract StaleRecoveryService

| Field | Value |
|-------|-------|
| **ID** | EP-SIMPLIFY-09 |
| **Scope** | `shadow_execpos/runtime.py` |
| **LOC Impact** | ~-200 (extracted) |
| **Risk** | MEDIUM |
| **Effort** | 2 days |
| **Dependencies** | EP-SIMPLIFY-07, EP-SIMPLIFY-08 |

**Actions:**
1. Create `shadow_execpos/stale_recovery.py`
2. Extract:
   - `_open_orders_stale` tracking
   - `_enter_stale_mode()`
   - `_exit_stale_mode()`
   - `_stale_recovery_loop()`
   - `_try_stale_recovery()`
3. Inject StaleRecoveryService into ExecPosRuntimeV2

**Validation:**
- Timeout resilience tests pass
- Recovery loop tests pass

---

## 7. Test Strategy

### 7.1 Existing Test Coverage

| Area | Test Files | Coverage |
|------|------------|----------|
| Aggregated OCO | 15+ files | HIGH |
| Bracket Service | 10+ files | HIGH |
| Adapter | 5 files | MEDIUM |
| Config | 3 files | LOW |
| Watchdog | 2 files | LOW |

### 7.2 Required New Tests

| Refactoring Task | New Test Required |
|------------------|-------------------|
| EP-SIMPLIFY-01 | `test_config_no_legacy_fallback.py` |
| EP-SIMPLIFY-04 | `test_config_consolidation.py` |
| EP-SIMPLIFY-05 | `test_watchdog_consolidation.py` |
| EP-SIMPLIFY-07 | `test_state_manager_isolation.py` |
| EP-SIMPLIFY-08 | `test_snapshot_manager_isolation.py` |
| EP-SIMPLIFY-09 | `test_stale_recovery_isolation.py` |

### 7.3 Regression Test Plan

For each EP-SIMPLIFY task:
1. **Pre-refactor baseline:** Run full test suite, save results
2. **Post-refactor validation:** Run same suite, compare
3. **Integration verification:**
   - Config loading smoke test
   - E2E bracket flow test
   - Testnet order placement
4. **Performance check:**
   - p95 latency unchanged (< 50ms)
   - No new memory leaks

### 7.4 Kill-Switch Strategy

Each refactoring task should have a feature flag:
```python
# config/domains/execution.yaml
execution_position:
  feature_flags:
    use_consolidated_config: true   # EP-SIMPLIFY-04
    use_unified_watchdog: true      # EP-SIMPLIFY-05
    use_extracted_managers: true    # EP-SIMPLIFY-07/08/09
```

Rollback = flip flag to `false`.

---

## 8. Summary & Recommendations

### 8.1 Immediate Actions (This Sprint)

| Task | Owner | ETA |
|------|-------|-----|
| EP-SIMPLIFY-01: Remove legacy config | TBD | 2d |
| EP-SIMPLIFY-02: Remove dead mode refs | TBD | 1d |
| EP-SIMPLIFY-03: Move test utilities | TBD | 0.5d |

### 8.2 Short-Term (Next Sprint)

| Task | Owner | ETA |
|------|-------|-----|
| EP-SIMPLIFY-04: Consolidate config | TBD | 2d |
| EP-SIMPLIFY-05: Consolidate watchdogs | TBD | 3d |
| EP-SIMPLIFY-06: Simplify ExecutionService | TBD | 2d |

### 8.3 Medium-Term (Next 2-3 Sprints)

| Task | Owner | ETA |
|------|-------|-----|
| EP-SIMPLIFY-07: Extract StateManager | TBD | 3d |
| EP-SIMPLIFY-08: Extract SnapshotManager | TBD | 2d |
| EP-SIMPLIFY-09: Extract StaleRecovery | TBD | 2d |

### 8.4 Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Total LOC | ~14,580 | <11,000 |
| Config files | 3 | 1 |
| Watchdog files | 2 | 1 |
| RuntimeV2 LOC | 2,099 | <1,200 |
| God Objects | 2 | 0 |

### 8.5 Architectural North Star

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TARGET ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  V2RuntimeFacade                                                    │
│       │                                                             │
│       ▼                                                             │
│  ExecPosRuntimeV2 (~800 LOC) ◀── Orchestrator only                 │
│       │                                                             │
│       ├──▶ StateManager (~400 LOC)                                 │
│       │       └── PositionState, OrderState                        │
│       │                                                             │
│       ├──▶ SnapshotManager (~300 LOC)                              │
│       │       └── TTL, Refresh hooks                               │
│       │                                                             │
│       ├──▶ StaleRecoveryService (~200 LOC)                         │
│       │       └── Recovery loop, mode flags                        │
│       │                                                             │
│       ├──▶ BracketService (~900 LOC) ◀── Unchanged (pure)          │
│       │                                                             │
│       ├──▶ BracketWatchdog (~350 LOC) ◀── Unified                  │
│       │                                                             │
│       └──▶ BinanceExecutionAdapter (~1,600 LOC) ◀── Unchanged      │
│                                                             │
│  Config: config.py (~500 LOC) ◀── Single Pydantic SSOT             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9. Детальні приклади спрощень (Було / Стане)

### 9.1 Приклад 1: Спрощення `manage_config.py` (EP-SIMPLIFY-01)

#### БУЛО (Проблеми):

```python
# manage_config.py — 876 LOC з dual-path logic

def resolve_execution_manage_config(config: Any) -> ExecutionManageConfig:
    """
    Main entry point with dual-path (V2 → legacy fallback).
    """
    try:
        v2_result = _build_manage_from_v2(config)
        if v2_result is not None:
            return v2_result
    except ConfigError:
        raise
    except Exception as e:
        LOG.warning(
            "Failed to build manage config from v2, falling back to legacy: %s", e)
        resolved = _build_manage_from_legacy(config)  # <-- LEGACY PATH
        return resolved

    resolved = _build_manage_from_legacy(config)  # <-- ANOTHER LEGACY PATH
    return resolved

# Plus 4 legacy helper functions:
def _resolve_orphan_monitor(config: Any) -> OrphanMonitorConfig: ...  # ~30 LOC
def _resolve_quick_profit(config: Any) -> QuickProfitConfig: ...      # ~25 LOC
def _resolve_trailing(config: Any) -> TrailingConfig: ...             # ~20 LOC
def _resolve_emergency(config: Any) -> EmergencyConfig: ...           # ~25 LOC

def _build_manage_from_legacy(config: Any) -> ExecutionManageConfig:
    """~150 LOC of dict navigation with _pluck() calls"""
    ...
```

**Проблеми:**
- Два шляхи виконання (V2 + legacy) для одного завдання
- 4 окремі legacy resolver-функції
- `_pluck()` utility для dict navigation замість typed access
- Legacy path ніколи не вимикається (завжди fallback)

#### СТАНЕ (Після спрощення):

```python
# manage_config.py — ~450 LOC (V2 only)

def resolve_execution_manage_config(config: Any) -> ExecutionManageConfig:
    """
    Single path: V2 Pydantic config only.
    Raises ConfigError on invalid config.
    """
    return _build_manage_from_v2(config)

# DELETED: _build_manage_from_legacy()
# DELETED: _resolve_orphan_monitor(), _resolve_quick_profit(),
#          _resolve_trailing(), _resolve_emergency()
# DELETED: Legacy mode validation in _validate_and_transform_aggregated_oco_config()
```

**Що видаляємо:**
- `_build_manage_from_legacy()` — ~150 LOC
- 4 legacy resolvers — ~100 LOC
- Legacy mode validation — ~50 LOC
- Fallback try/except logic — ~20 LOC
- **Total: ~320 LOC removed**

**Тести, що прикривають:**
- `test_config_v2_loading.py` — existing V2 config tests
- `test_manage_config_resolve.py` — add test for "no legacy fallback"
- Manual: load all YAML configs, ensure no `mode: legacy` anywhere

---

### 9.2 Приклад 2: Декомпозиція RuntimeV2 (EP-SIMPLIFY-07/08/09)

#### БУЛО (God Object):

```python
# shadow_execpos/runtime.py — 2,099 LOC

class ExecPosRuntimeV2:
    def __init__(self, ...):
        # State management (should be StateManager)
        self._positions_by_symbol: Dict[str, PositionState] = {}
        self._open_orders_by_symbol: Dict[str, List[Dict]] = {}
        self._bracket_status: Dict[str, BracketStatus] = {}

        # Snapshot tracking (should be SnapshotManager)
        self._last_orders_snapshot_ts: Dict[str, float] = {}
        self._last_position_snapshot_ts: Dict[str, float] = {}
        self._orders_snapshot_state: Dict[str, str] = {}

        # Stale recovery (should be StaleRecoveryService)
        self._open_orders_stale: Dict[str, bool] = {}
        self._stale_entered_ts: Dict[str, float] = {}
        self._stale_recovery_task: Optional[asyncio.Task] = None

        # ... 6 more instance variables
        # ... 8 service dependencies

    # 50+ methods mixed together:

    # State methods (~400 LOC)
    def _update_position_state(self, ...): ...
    def _get_position(self, symbol: str): ...
    def _set_bracket_status(self, ...): ...

    # Snapshot methods (~300 LOC)
    def _is_orders_snapshot_fresh(self, symbol: str) -> bool: ...
    def _mark_orders_snapshot(self, symbol: str, ts: float): ...
    async def _request_orders_snapshot(self, ...): ...

    # Stale recovery methods (~200 LOC)
    def _enter_stale_mode(self, symbol: str, reason: str): ...
    def _exit_stale_mode(self, symbol: str, reason: str): ...
    async def _stale_recovery_loop(self): ...

    # Orchestration methods (~800 LOC)
    async def handle_entry_intent(self, ...): ...
    async def handle_trade_executed(self, ...): ...
    async def _evaluate_brackets(self, ...): ...
```

#### СТАНЕ (Decomposed):

```python
# shadow_execpos/state_manager.py — NEW (~400 LOC)
class StateManager:
    """Manages position and order state."""

    def __init__(self):
        self._positions_by_symbol: Dict[str, PositionState] = {}
        self._open_orders_by_symbol: Dict[str, List[Dict]] = {}
        self._bracket_status: Dict[str, BracketStatus] = {}

    def update_position(self, symbol: str, fill: FillEvent) -> PositionState: ...
    def get_position(self, symbol: str) -> Optional[PositionState]: ...
    def set_orders(self, symbol: str, orders: List[Dict]) -> None: ...
    def get_orders(self, symbol: str) -> List[Dict]: ...
    # ... clean state interface
```

```python
# shadow_execpos/snapshot_manager.py — NEW (~300 LOC)
class SnapshotManager:
    """Manages snapshot freshness and TTL."""

    def __init__(self, config: SnapshotConfig, refresh_hook: Callable):
        self._orders_ts: Dict[str, float] = {}
        self._position_ts: Dict[str, float] = {}
        self._config = config
        self._refresh_hook = refresh_hook

    def is_orders_fresh(self, symbol: str) -> bool: ...
    def mark_orders_snapshot(self, symbol: str) -> None: ...
    async def ensure_fresh_snapshot(self, symbol: str) -> None: ...
```

```python
# shadow_execpos/stale_recovery.py — NEW (~200 LOC)
class StaleRecoveryService:
    """Handles stale mode entry/exit and recovery loop."""

    def __init__(self, snapshot_manager: SnapshotManager):
        self._stale_symbols: Set[str] = set()
        self._recovery_task: Optional[asyncio.Task] = None

    def enter_stale(self, symbol: str, reason: str) -> None: ...
    def exit_stale(self, symbol: str, reason: str) -> None: ...
    def is_stale(self, symbol: str) -> bool: ...
    async def recovery_loop(self) -> None: ...
```

```python
# shadow_execpos/runtime.py — SIMPLIFIED (~800 LOC)
class ExecPosRuntimeV2:
    """Orchestrator only — delegates to sub-managers."""

    def __init__(self, ...):
        # Injected managers
        self.state = StateManager()
        self.snapshots = SnapshotManager(config.snapshot, self._request_snapshot)
        self.stale_recovery = StaleRecoveryService(self.snapshots)

        # Services (unchanged)
        self.bracket_service = BracketService(...)
        self.execution_service = ExecutionService(...)
        self.watchdog = AggOcoWatchdogService(...)

    # Clean orchestration methods only
    async def handle_entry_intent(self, event: RuntimeEvent) -> None:
        """Route entry intent through gatekeeper → execution."""
        if self.stale_recovery.is_stale(event.symbol):
            return  # Fail-closed

        decision = self.gatekeeper.check_entry(...)
        if not decision.allowed:
            return

        result = await self.execution_service.place_order(...)
        self.state.update_position(...)
```

**Структурні зміни:**
- RuntimeV2: 2,099 LOC → ~800 LOC (orchestration only)
- + StateManager: ~400 LOC (extracted)
- + SnapshotManager: ~300 LOC (extracted)
- + StaleRecoveryService: ~200 LOC (extracted)

**Переваги:**
- Кожен клас має **одну відповідальність**
- Легше тестувати ізольовано
- Менша когнітивна навантаженість при читанні
- Можливість заміни/мокання окремих компонентів

---

## 10. Потенційні P0-ризики

### 10.1 🔴 CRITICAL: Stale Mode Recovery Race Condition

**Файл:** `shadow_execpos/runtime.py`, метод `_stale_recovery_loop()`

**Проблема:**
```python
async def _stale_recovery_loop(self) -> None:
    while True:
        stale_symbols = [s for s, is_stale in self._open_orders_stale.items() if is_stale]
        # ⚠️ RACE: stale_symbols can change during iteration
        for symbol in stale_symbols:
            await self._request_orders_snapshot(symbol, force=True)
            # ⚠️ No timeout — can hang indefinitely
        await asyncio.sleep(self._stale_recovery_interval_sec)
```

**Ризик:**
- Якщо `_request_orders_snapshot()` зависає (network issue), loop ніколи не продовжиться
- Інші stale symbols залишаться без recovery
- Немає circuit breaker для repeated failures

**P0 Таск:**
```
EP-P0-01: Add timeout and circuit breaker to stale recovery loop
- Add asyncio.wait_for() with 30s timeout per symbol
- Add max_consecutive_failures counter (e.g., 5)
- After max failures: log ALERT, continue to next symbol
- Add jitter to prevent thundering herd
```

---

### 10.2 🔴 CRITICAL: Bracket Evaluation Lock Contention

**Файл:** `shadow_execpos/runtime.py`, метод `_get_evaluation_lock()`

**Проблема:**
```python
def _get_evaluation_lock(self) -> asyncio.Lock:
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        if self._evaluation_lock is None:
            self._evaluation_lock = asyncio.Lock()
        return self._evaluation_lock

    # ⚠️ Lock recreation on loop change
    if self._evaluation_lock_loop is not current_loop:
        self._evaluation_lock = asyncio.Lock()
        self._evaluation_lock_loop = current_loop
```

**Ризик:**
- При зміні event loop старий lock втрачається
- Concurrent evaluations можуть пройти через різні locks
- Потенційне порушення Aggregated OCO invariant (multiple SL/TP)

**P0 Таск:**
```
EP-P0-02: Ensure single evaluation lock per runtime instance
- Add assertion that loop never changes after start()
- If loop change detected: raise RuntimeError (fail-fast)
- Add test: concurrent handle_trade_executed calls on same symbol
```

---

### 10.3 🟠 HIGH: Orphan SL/TP After Position Close

**Файл:** `shadow_execpos/bracket_service.py`

**Сценарій:**
1. Position qty = 1.0, SL order exists
2. External close (manual or from another system) fills completely
3. Position qty = 0
4. SL order залишається на біржі (orphan)
5. Якщо ціна досягне SL level → ORDER_REJECTED (-2022) або unexpected fill

**Поточний захист:**
- `_cancel_stale_brackets()` в guard loop
- Але: guard loop interval = 5s, orphan може жити 5+ секунд

**P0 Таск:**
```
EP-P0-03: Immediate orphan cleanup on position close
- When position goes FLAT: immediately cancel all SL/TP orders
- Don't wait for guard loop
- Add metric: orphan_cleanup_latency_ms
```

---

## 11. Самоперевірка

### 11.1 Чекліст повноти аналізу

| Перевірка | Статус |
|-----------|--------|
| Всі 41 production файлів домену проаналізовано | ✅ |
| Всі 44 тестових файли враховано | ✅ |
| Архітектурна карта побудована | ✅ |
| Dependency graph описано | ✅ |
| God objects ідентифіковано | ✅ (2: RuntimeV2, manage_config) |
| Code smells задокументовано | ✅ (6 категорій) |
| Subtraction opportunities знайдено | ✅ (~3,500 LOC) |
| Refactoring tasks сформовано | ✅ (9 тасків) |
| Test strategy описано | ✅ |
| P0 risks ідентифіковано | ✅ (3 критичних) |

### 11.2 Перевірка інваріантів для кожного таску

| Task | Aggregated OCO | Fail-Closed | Idempotency | Config V2 | p95 < 50ms |
|------|----------------|-------------|-------------|-----------|------------|
| EP-SIMPLIFY-01 | ✅ No impact | ✅ No impact | ✅ No impact | ✅ Improves | ✅ No impact |
| EP-SIMPLIFY-02 | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact |
| EP-SIMPLIFY-03 | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact |
| EP-SIMPLIFY-04 | ✅ No impact | ✅ No impact | ✅ No impact | ⚠️ Test needed | ✅ No impact |
| EP-SIMPLIFY-05 | ✅ Test needed | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact |
| EP-SIMPLIFY-06 | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact | ✅ Improves |
| EP-SIMPLIFY-07 | ✅ Test needed | ✅ Test needed | ✅ Test needed | ✅ No impact | ✅ No impact |
| EP-SIMPLIFY-08 | ✅ Test needed | ✅ Test needed | ✅ No impact | ✅ No impact | ⚠️ Test needed |
| EP-SIMPLIFY-09 | ✅ No impact | ✅ Test needed | ✅ No impact | ✅ No impact | ✅ No impact |

### 11.3 Перевірка "No New Layers"

| Перевірка | Результат |
|-----------|-----------|
| Жоден таск не додає новий шар абстракції без видалення старого | ✅ |
| EP-SIMPLIFY-07/08/09 **екстрагують** код, не обгортають | ✅ |
| Config consolidation **видаляє** файли, не додає | ✅ |
| Watchdog consolidation **видаляє** дублікат | ✅ |
| Жоден "CompatLayer" не створюється | ✅ |

---

## 12. Ітеративний підхід до виконання

### Фаза 1: Low-Risk Cleanup (Тиждень 1)
```
Day 1-2: EP-SIMPLIFY-01 (legacy config paths)
Day 2:   EP-SIMPLIFY-02 (dead mode refs)
Day 3:   EP-SIMPLIFY-03 (move test utilities)
Day 3:   Run full test suite, validate green
```

**Gate:** All tests green, no config loading errors

### Фаза 2: Structural Consolidations (Тиждень 2-3)
```
Day 4-5: EP-SIMPLIFY-04 (config consolidation)
Day 6-8: EP-SIMPLIFY-05 (watchdog consolidation)
Day 9-10: EP-SIMPLIFY-06 (ExecutionService simplification)
```

**Gate:**
- All tests green
- Testnet deployment (shadow mode)
- 24h monitoring for anomalies

### Фаза 3: Deep Decomposition (Тиждень 3-4)
```
Day 11-13: EP-SIMPLIFY-07 (StateManager extraction)
Day 14-15: EP-SIMPLIFY-08 (SnapshotManager extraction)
Day 16-17: EP-SIMPLIFY-09 (StaleRecovery extraction)
```

**Gate:**
- All tests green
- Performance benchmarks unchanged
- Testnet deployment (shadow mode)
- 48h monitoring

### Post-Phase: P0 Risk Fixes (Parallel)
```
EP-P0-01: Stale recovery timeout (can do in Phase 1)
EP-P0-02: Lock assertion (can do in Phase 2)
EP-P0-03: Immediate orphan cleanup (can do in Phase 3)
```

---

## Appendix A: File-by-File LOC Summary

| File | LOC | Keep/Remove/Refactor |
|------|-----|---------------------|
| `shadow_execpos/runtime.py` | 2,099 | REFACTOR (decompose) |
| `binance_execution_adapter.py` | 1,693 | KEEP |
| `exposure_guard.py` | 1,379 | REMOVED |
| `shadow_execpos/bracket_service.py` | 957 | KEEP |
| `manage_config.py` | 876 | REMOVE (legacy parts) |
| `contracts.py` | 808 | KEEP |
| `shadow_execpos/execution_service.py` | 742 | REFACTOR |
| `watchdog.py` | 543 | REMOVE (consolidate) |
| `utils.py` | 542 | KEEP |
| `metrics_collector.py` | 412 | KEEP |
| `runtime_factory.py` | 375 | KEEP |
| `shadow_execpos/watchdog.py` | 309 | ENHANCE |
| `config.py` | 280 | ENHANCE (SSOT) |
| `metrics_aggregator.py` | 271 | KEEP |
| `idempotent_cancel.py` | 246 | KEEP |
| `shadow_execpos/async_manager.py` | 240 | KEEP |
| `shadow_execpos/wal_writer.py` | 235 | KEEP |
| `shadow_execpos/gatekeeper.py` | 228 | KEEP |
| `drift_monitor.py` | 221 | KEEP |
| `brackets_config.py` | 215 | REMOVE (merge) |
| `simulated_adapter.py` | 210 | MOVE (to tests) |
| `shadow_execpos/logging_v2.py` | 199 | KEEP |
| `shadow_execpos/event_adapter.py` | 197 | KEEP |
| `shadow_execpos/ab_replay.py` | 192 | KEEP |
| `shadow_execpos/trailing.py` | 161 | KEEP |
| `shadow_execpos/agg_oco_replay.py` | 158 | KEEP |
| `shadow_execpos/position_model.py` | 155 | KEEP |
| `algo_order_index.py` | 148 | KEEP |
| `shadow_execpos/exposure_bridge.py` | 131 | KEEP |
| `shadow_execpos/idempotency.py` | 128 | KEEP |
| `order_index.py` | 126 | KEEP |
| `shadow_execpos/close_flow.py` | 93 | KEEP |
| `shadow_execpos/price_enricher.py` | 82 | KEEP |
| `soft_clip.py` | 73 | REMOVED |
| `shadow_execpos/types.py` | 71 | KEEP |
| `adapter_factory.py` | 70 | KEEP |
| `utils_event_bus.py` | 58 | KEEP |
| `internal_types.py` | 49 | KEEP |
| `execution_adapter.py` | 30 | KEEP |

---

## Appendix B: Critical Invariants to Preserve

1. **Aggregated OCO:** Max 1 SL + 1 TP per (symbol, side) when qty ≠ 0
2. **Fail-Closed:** On uncertainty, block new trades (stale mode)
3. **Idempotency:** No duplicate fills processed
4. **Config V2 Compatibility:** All existing V2 configs must load without changes
5. **p95 Latency:** < 50ms for hot path operations

---

> **Document Status:** Ready for team review
> **Next Action:** Prioritize EP-SIMPLIFY-01/02/03 for immediate execution
