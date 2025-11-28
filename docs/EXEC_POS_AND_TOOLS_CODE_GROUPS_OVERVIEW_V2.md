# Execution Position & Tools Code Groups Overview V2

**Created**: 2025-01-19
**RID**: EP-CODE-GROUPS-OVERVIEW-S2
**Status**: INVENTORY ONLY (no code changes)

## Purpose

Comprehensive inventory and logical grouping of all modules in:
- `execution_position/**` (including `shadow_execpos/`)
- `apps/reference/tools/**`
- `apps/reference/utils/**`
- `apps/reference/services/**` + `apps/reference/adapters/**`

This document identifies:
- Active modules in current V2 runtime
- Potential duplicate logic
- Suspected dead code
- Conflicts between code and documentation

**Important**: This task is **analysis/documentation only** — no code, config, or test changes.

---

## 1. execution_position

### 1.1. shadow_execpos/ (V2 Runtime — ACTIVE)

**Status**: All ACTIVE (default runtime since EP-RUNTIME-WIRING-V2-S1)

| File | Description | Status |
|------|-------------|--------|
| `runtime.py` | ExecPosRuntimeV2 — main orchestrator composing all sub-services (async manager, execution service, gatekeeper, watchdog, WAL, exposure, close flow, trailing, brackets observe-only). Entry point for V2. | **ACTIVE** |
| `async_manager.py` | ExecPosAsyncManager — async task executor for background order monitoring, watchdog checks, position reconciliation. | **ACTIVE** |
| `execution_service.py` | ExecutionService — pure logic for order planning (OPEN/CLOSE/ADJUST). Computes action plans without adapter calls. | **ACTIVE** |
| `gatekeeper.py` | ExecPosGatekeeper — pre-execution guards (size, price, notional, cooldown, active orders, exposure). Rejects invalid commands. | **ACTIVE** |
| `price_enricher.py` | PriceEnricher — enriches events with market price data. | **ACTIVE** |
| `watchdog.py` | AggOcoWatchdogService — detect-only invariant checker for bracket state (orphan SL/TP, missing SL, stale levels). No auto-heal in V2. | **ACTIVE** |
| `idempotency.py` | FillIdempotency — deduplication for fills using cumulative quantity tracking with TTL-based cleanup. | **ACTIVE** |
| `wal_writer.py` | ExecPosWALWriter — writes all decisions/events to WAL for DR replay. | **ACTIVE** |
| `exposure_bridge.py` | ExposureBridge — publishes exposure updates to exposure_guard domain. | **ACTIVE** |
| `position_model.py` | PositionState — immutable position state dataclass with `apply_fill()` reducer for reconciliation. | **ACTIVE** |
| `close_flow.py` | CloseFlowService — pure service for close planning (market close, partial close, scale-out). No direct adapter calls. | **ACTIVE** |
| `trailing.py` | TrailingStopService — pure service for trailing stop, breakeven, time-exit logic. Computes recommendations only. | **ACTIVE** |
| `bracket_service.py` | BracketService — pure computation layer for bracket state evaluation (MISSING_SL, ORPHAN_SL, TOO_MANY_SL, STALE_LEVELS). Returns BracketPlan with recommended actions. No live execution. | **ACTIVE** |
| `event_adapter.py` | Adapter interface for external event streams (WebSocket → RuntimeEvent conversion). | **ACTIVE** |
| `types.py` | Shared types for V2 runtime (RuntimeEvent, ExecutionCommand, OrderState, PositionSnapshot). | **ACTIVE** |
| `logging_v2.py` | Structured logging for V2 runtime with RID propagation. | **ACTIVE** |
| `ab_replay.py` | A/B replay utilities for comparing V1 vs V2 behavior (regression testing). | **ACTIVE** |

**Dependencies**:
- `bracket_aggregator.py` (TP/SL level computation)
- `order_guardian.py` (bracket metadata, ownership validation)
- `vfoundation/dr/wal` (WAL infrastructure)

---

### 1.2. Top-Level execution_position/ (Glue & Legacy FSM)

| File | Description | Status |
|------|-------------|--------|
| `fsm.py` | Legacy ExecPosFSM wrapper (3-flow orchestration). **REPLACED** by ExecPosRuntimeV2. No longer default. | **LEGACY_DOC_ONLY** |
| `fsm_open.py` | Legacy OpenFlowFSM (CMD:OPEN → DEC:OPEN). Part of old 3-flow architecture. | **LEGACY_DOC_ONLY** |
| `fsm_manage.py` | Legacy ManageFlowFSM (bracket placement, trailing stop). Replaced by V2 services (bracket_service, trailing). Marked `LEGACY_OCO_DEPRECATED=True` (tests only). | **LEGACY_DOC_ONLY** |
| `fsm_close.py` | Legacy CloseFlowFSM (max hold time, emergency close). Replaced by close_flow service. | **LEGACY_DOC_ONLY** |
| `runtime_factory.py` | Factory for creating ExecPosRuntimeV2 instances with dependencies. | **ACTIVE** |
| `contracts.py` | Shared contracts/protocols for execution adapters. | **ACTIVE** |
| `execution_adapter.py` | Abstract interface for execution adapters (place, cancel, modify). | **ACTIVE** |
| `binance_execution_adapter.py` | Binance-specific execution adapter implementation. | **ACTIVE** |
| `simulated_adapter.py` | Simulated adapter for testing (no live API calls). | **ACTIVE** |
| `order_index.py` | In-memory order tracking index (order_id ↔ client_order_id mapping). | **ACTIVE** |
| `watchdog.py` | Top-level aggregated OCO watchdog (may duplicate shadow_execpos/watchdog.py). | **SUSPECT_DUPLICATE** |
| `exposure_guard.py` | Exposure limit enforcement (notional, leverage). Used by gatekeeper. | **ACTIVE** |
| `metrics_collector.py` | Metrics aggregation for execution_position domain. | **ACTIVE** |
| `metrics_aggregator.py` | Metrics aggregator (may overlap with metrics_collector.py). | **SUSPECT_DUPLICATE** |
| `brackets_config.py` | Config models for bracket rules (SL/TP percentages, TTL, max legs). | **ACTIVE** |
| `manage_config.py` | Config models for manage flow (trailing, breakeven, time exit). | **ACTIVE** |
| `idempotent_cancel.py` | Idempotent cancel logic (deduplication for cancel commands). May overlap with shadow_execpos/idempotency.py. | **SUSPECT_DUPLICATE** |
| `soft_clip.py` | Soft clip utility for price/qty rounding to exchange constraints. | **ACTIVE** |
| `utils.py` | Utility functions (client_order_id parsing, side conversions). | **ACTIVE** |
| `utils_event_bus.py` | Event bus integration utilities. | **ACTIVE** |
| `agg_oco_introspection.py` | Introspection tool for aggregated OCO state (debugging). | **ACTIVE** |
| `aurora_log_adapter.py` | Aurora log adapter for structured logging. | **ACTIVE** |
| `drift_monitor.py` | Drift monitor for comparing adapter vs runtime state (confusion matrix). | **ACTIVE** |
| `test_binance_adapter_methods.py` | Adapter method tests (should be in tests/ dir). | **SUSPECT_DEAD** |
| `test_order_index.py` | Order index tests (should be in tests/ dir). | **SUSPECT_DEAD** |

**Bracket/OCO Related** (in vfoundation path):
| File | Description | Status |
|------|-------------|--------|
| `vfoundation/.../bracket_aggregator.py` | Pure function for computing aggregated TP/SL levels from (avg_entry, qty, side, risk_cfg, constraints). Used by BracketService. | **ACTIVE** |

---

### 1.3. execution_position/docs/

| File | Description | Status |
|------|-------------|--------|
| `EXEC_POS_BRACKETS_CONTRACT.md` | Canonical contract for BracketService (v1.0). Defines data models, API, invariants. **Phase 2 complete** (implementation done). | **ACTIVE** |
| `EXEC_POS_CLOSE_TRAILING_CONTRACT.md` | Contract for CloseFlowService and TrailingStopService (v1.0). Defines close/trailing logic. | **ACTIVE** |
| `EXEC_POS_CLOSE_TRAILING_ANALYSIS.md` | Analysis of close/trailing requirements and V2 gaps. | **ACTIVE** |
| `EXECUTION_POSITION_V2_OBSERVABILITY.md` | Observability spec for V2 (logs, metrics, WHY-chains, RID propagation). | **ACTIVE** |
| `FSM_EVENT_MAP.md` | Event routing map for legacy FSM flows. | **LEGACY_DOC_ONLY** |
| `EP_FSM_EXTRACTION_AUDIT.md` | Audit of FSM extraction to V2 services. | **LEGACY_DOC_ONLY** |
| `EP_RUNTIME_SWITCH_PLAN.md` | Plan for switching from V1 FSM to V2 runtime. | **LEGACY_DOC_ONLY** |

---

## 2. tools/

### 2.1. tools/order_trace/

**Status**: ACTIVE (XAI layer for order lifecycle tracing)

| File | Description | Status |
|------|-------------|--------|
| `engine.py` | Correlation engine — builds coherent trade narratives from multiple sources (decision logs, runtime logs, WAL, exposure events). Correlates events by RID/trade_id. | **ACTIVE** |
| `parsers.py` | Parsers for various log formats (decision logs, execpos runtime logs, WAL records, exposure events). | **ACTIVE** |
| `types.py` | Shared types (TraceEvent, TradeTrace, TraceSources). | **ACTIVE** |

**Integration Points**:
- Reads ExecPosRuntimeV2 logs (structured JSON)
- Reads WAL records for DR replay
- Reads exposure events from exposure_bridge
- Used by `tools/order_trace_cli.py` (CLI tool)

**Dependencies**: ExecPosRuntimeV2 logging, WAL infrastructure

---

### 2.2. tools/tca_execpos/

**Status**: ACTIVE (Transaction Cost Analysis for execution_position)

| File | Description | Status |
|------|-------------|--------|
| `engine.py` | TCA engine — computes execution quality metrics (slippage, fill time, VWAP comparison). | **ACTIVE** |
| `loader.py` | Data loader for TCA inputs (fills, market data). | **ACTIVE** |
| `model.py` | Data models for TCA analysis (TCAMetrics, Execution, Benchmark). | **ACTIVE** |

**Integration Points**: Reads ExecPosRuntimeV2 fill events, market data from adapters.

---

## 3. utils/

**Status**: Shared utilities (math, trading modes, cooldowns)

| File | Description | Status |
|------|-------------|--------|
| `tp_sl_calculator.py` | TP/SL calculator — computes TP/SL prices from entry price, SL bps, side, TP ratios. **May duplicate** bracket_aggregator.py logic. | **SUSPECT_DUPLICATE** |
| `trade_cooldowns.py` | Trade cooldown tracking (per-symbol cooldown enforcement). Used by gatekeeper. | **ACTIVE** |
| `trading_modes.py` | Trading mode enums and utilities (LIVE, SHADOW, DRY_RUN). | **ACTIVE** |

**Notes**:
- `tp_sl_calculator.py` has overlapping logic with `bracket_aggregator.py` (both compute TP/SL from entry + risk params). Candidate for consolidation.

---

## 4. services/ + adapters/

### 4.1. services/

| File | Description | Status |
|------|-------------|--------|
| `order_guardian.py` | OrderGuardian service — centralized order/position monitor with bracket ownership validation. Tracks (clientOrderId ↔ orderId) mapping, bracket linkage, safe cleanup. 2086 lines. Frozen contract v1.0. **NOT integrated into V2 runtime** (V2 uses watchdog observe-only). | **ACTIVE** (but not wired to V2) |
| `ledger_store_adapter.py` | Ledger store adapter (persistent storage for trade history). | **ACTIVE** |

**OrderGuardian Status**:
- Exists and functional
- Has frozen contract v1.0
- NOT currently called by ExecPosRuntimeV2 (V2 uses AggOcoWatchdogService for detection only)
- Future integration planned (Phase 3: auto-heal)

---

### 4.2. adapters/

| File | Description | Status |
|------|-------------|--------|
| `binance_adapter.py` | Binance REST API adapter (account, orders, positions, market data). | **ACTIVE** |
| `sdk_adapter_binance.py` | Binance SDK adapter wrapper. | **ACTIVE** |
| `exchange/` | Exchange-specific adapters (may include other exchanges). | **ACTIVE** |

---

## 5. Logical Groups

### Group A: Execution Core (V2 Runtime)

**Role**: Hot path for order execution, position tracking, bracket/close/trailing logic.

**Files**:
- `shadow_execpos/runtime.py` (orchestrator)
- `shadow_execpos/async_manager.py` (async executor)
- `shadow_execpos/execution_service.py` (order planning)
- `shadow_execpos/gatekeeper.py` (pre-execution guards)
- `shadow_execpos/watchdog.py` (invariant detection)
- `shadow_execpos/idempotency.py` (deduplication)
- `shadow_execpos/wal_writer.py` (DR/WAL)
- `shadow_execpos/exposure_bridge.py` (exposure updates)
- `shadow_execpos/position_model.py` (position state)
- `shadow_execpos/close_flow.py` (close planning)
- `shadow_execpos/trailing.py` (trailing logic)
- `shadow_execpos/bracket_service.py` (bracket planning)
- `runtime_factory.py` (V2 factory)
- `brackets_config.py`, `manage_config.py` (config models)
- `vfoundation/.../bracket_aggregator.py` (TP/SL math)
- DR/Restart recovery: `runtime._run_bracket_recovery_pass` applies `BracketPlan` actions once post-hydrate (orphan cleanup / seed protection) via `ExecutionService` + optional OrderGuardian registry.

**SLO**: p95 ≤ 50ms (overall), p95 ≤ 100ms (with adapter)

---

### Group B: XAI / Observability / WAL

**Role**: Order trace, logs, metrics, DR replay, audit trail.

**Files**:
- `tools/order_trace/` (engine, parsers, types)
- `shadow_execpos/logging_v2.py` (structured logs)
- `shadow_execpos/wal_writer.py` (WAL)
- `metrics_collector.py` (metrics aggregation)
- `aurora_log_adapter.py` (log adapter)
- `drift_monitor.py` (adapter vs runtime drift)
- `agg_oco_introspection.py` (OCO state introspection)

**Integration**: Reads V2 logs, WAL records, exposure events. Used for debugging, post-mortem analysis.

---

### Group C: Risk / Math / Utils

**Role**: TP/SL calculation, exposure limits, soft clipping, trading modes.

**Files**:
- `vfoundation/.../bracket_aggregator.py` (aggregated TP/SL math)
- `utils/tp_sl_calculator.py` (legacy TP/SL calculator — **may duplicate bracket_aggregator**)
- `exposure_guard.py` (notional/leverage limits)
- `soft_clip.py` (price/qty rounding)
- `utils/trade_cooldowns.py` (cooldown tracking)
- `utils/trading_modes.py` (LIVE/SHADOW/DRY_RUN)

**Duplication Risk**: `tp_sl_calculator.py` vs `bracket_aggregator.py` — both compute TP/SL from entry + risk params.

---

### Group D: Adapters / Service Layer

**Role**: External integrations (Binance API, event bus, ledger store).

**Files**:
- `adapters/binance_adapter.py` (REST API)
- `adapters/sdk_adapter_binance.py` (SDK wrapper)
- `binance_execution_adapter.py` (execution-specific)
- `simulated_adapter.py` (testing)
- `services/order_guardian.py` (bracket ownership, cleanup)
- `services/ledger_store_adapter.py` (trade history)
- `event_adapter.py` (WebSocket events)
- `utils_event_bus.py` (event bus glue)

**Notes**: OrderGuardian exists but NOT wired to V2 runtime (V2 uses watchdog detect-only).

---

### Group E: Legacy FSM (DEPRECATED)

**Role**: Old 3-flow FSM architecture (OPEN/MANAGE/CLOSE). Replaced by V2 services.

**Files**:
- `fsm.py` (ExecPosFSM wrapper)
- `fsm_open.py` (OpenFlowFSM)
- `fsm_manage.py` (ManageFlowFSM)
- `fsm_close.py` (CloseFlowFSM)

**Status**: LEGACY_DOC_ONLY — no longer default runtime. Kept for historical reference and DR replay of old events.

---

## 6. Status Tags Summary

### ACTIVE (Core V2 Runtime)
- All `shadow_execpos/*.py` files (17 files)
- `runtime_factory.py`
- `brackets_config.py`, `manage_config.py`
- `contracts.py`, `execution_adapter.py`, `binance_execution_adapter.py`, `simulated_adapter.py`
- `order_index.py`
- `exposure_guard.py`
- `metrics_collector.py`
- `soft_clip.py`, `utils.py`, `utils_event_bus.py`
- `agg_oco_introspection.py`, `aurora_log_adapter.py`, `drift_monitor.py`
- `vfoundation/.../bracket_aggregator.py`
- `tools/order_trace/*` (3 files)
- `tools/tca_execpos/*` (3 files)
- `utils/trade_cooldowns.py`, `utils/trading_modes.py`
- `services/order_guardian.py` (frozen contract, not wired to V2)
- `services/ledger_store_adapter.py`
- `adapters/*` (binance_adapter, sdk_adapter_binance)

**Total**: ~40+ active files

---

### SUSPECT_DUPLICATE

| File | Reason | Overlaps With |
|------|--------|---------------|
| `utils/tp_sl_calculator.py` | TP/SL math from entry + risk params | `vfoundation/.../bracket_aggregator.py` |
| `watchdog.py` (top-level) | Aggregated OCO watchdog | `shadow_execpos/watchdog.py` |
| `metrics_aggregator.py` | Metrics aggregation | `metrics_collector.py` |
| `idempotent_cancel.py` | Cancel deduplication | `shadow_execpos/idempotency.py` |

**Recommendation**: Consolidate TP/SL math into `bracket_aggregator.py`, deprecate `tp_sl_calculator.py`. Verify watchdog/metrics duplication.

---

### SUSPECT_DEAD

| File | Reason |
|------|--------|
| `test_binance_adapter_methods.py` | Test file in src/ (should be in tests/) |
| `test_order_index.py` | Test file in src/ (should be in tests/) |

**Recommendation**: Move to `tests/` or delete if redundant with existing test coverage.

---

### LEGACY_DOC_ONLY

| File | Reason |
|------|--------|
| `fsm.py` | Old 3-flow FSM wrapper, replaced by V2 runtime |
| `fsm_open.py` | Legacy OpenFlowFSM |
| `fsm_manage.py` | Legacy ManageFlowFSM (replaced by bracket_service + trailing) |
| `fsm_close.py` | Legacy CloseFlowFSM (replaced by close_flow service) |
| `docs/FSM_EVENT_MAP.md` | Event map for legacy FSM |
| `docs/EP_FSM_EXTRACTION_AUDIT.md` | FSM extraction audit (historical) |
| `docs/EP_RUNTIME_SWITCH_PLAN.md` | V1→V2 switch plan (historical) |

**Recommendation**: Keep for DR replay of old events. Add "HISTORICAL REFERENCE ONLY" headers.

---

## 7. Candidates for Cleanup / Refactor

### 7.1. SUSPECT_DUPLICATE

**Issue**: Multiple implementations of similar logic.

**Files**:
1. **TP/SL Math**:
   - `utils/tp_sl_calculator.py` (199 lines)
   - `vfoundation/.../bracket_aggregator.py` (179 lines)
   - **Overlap**: Both compute TP/SL prices from entry price + risk params (SL bps, TP ratio/RR).
   - **Difference**: `bracket_aggregator.py` is pure functional, handles price constraints, used by BracketService. `tp_sl_calculator.py` is class-based, has CLI interface.
   - **Recommendation**:
     - Keep `bracket_aggregator.py` as canonical (used by V2).
     - Deprecate `tp_sl_calculator.py` or refactor as thin CLI wrapper around `bracket_aggregator.py`.
     - **Task**: `UTILS-TPSL-DEDUP-S1` — Consolidate TP/SL math.

2. **Watchdog**:
   - `watchdog.py` (top-level, 450 lines)
   - `shadow_execpos/watchdog.py` (280 lines)
   - **Overlap**: Both implement aggregated OCO invariant checking.
   - **Difference**: `shadow_execpos/watchdog.py` is integrated into V2 runtime. Top-level may be standalone utility.
   - **Recommendation**: Verify if top-level is still used. If not, deprecate.
   - **Task**: `WATCHDOG-DEDUP-S1` — Verify and consolidate watchdog logic.

3. **Metrics**:
   - `metrics_aggregator.py` (unknown size)
   - `metrics_collector.py` (active in V2)
   - **Overlap**: Both aggregate metrics for execution_position.
   - **Recommendation**: Verify functionality overlap, consolidate if redundant.
   - **Task**: `METRICS-DEDUP-S1` — Consolidate metrics logic.

4. **Idempotency**:
   - `idempotent_cancel.py` (top-level)
   - `shadow_execpos/idempotency.py` (FillIdempotency)
   - **Overlap**: Both handle idempotency for cancel/events.
   - **Recommendation**: Verify if top-level adds value beyond `shadow_execpos/idempotency.py`. Consolidate if redundant.
   - **Task**: `IDEMPOTENCY-DEDUP-S1` — Consolidate idempotency logic.

---

### 7.2. SUSPECT_DEAD

**Issue**: Files not imported/tested, may be obsolete.

**Files**:
1. `test_binance_adapter_methods.py` — Test file in src/ (should be in tests/).
2. `test_order_index.py` — Test file in src/ (should be in tests/).

**Recommendation**:
- Verify if covered by tests in `tests/domains/execution_position/`.
- If yes, delete.
- If no, move to `tests/`.
- **Task**: `TESTS-CLEANUP-S1` — Move or delete misplaced test files.

---

### 7.3. OrderGuardian Integration Gap

**Issue**: OrderGuardian exists (2086 lines, frozen contract v1.0) but NOT integrated into V2 runtime.

**Current State**:
- V2 uses `AggOcoWatchdogService` (detect-only, no auto-heal).
- OrderGuardian has auto-heal capability (safe bracket cleanup, ownership validation).

**Future Work**:
- **Phase 3**: Wire OrderGuardian into ExecPosRuntimeV2 for auto-heal.
- **Task**: `EP-PORT-GUARDIAN-S1` — Integrate OrderGuardian with V2 runtime.

---

### 7.4. Legacy FSM Cleanup

**Issue**: Legacy FSM files (`fsm*.py`) marked as LEGACY_DOC_ONLY but still present in codebase.

**Recommendation**:
- Add "HISTORICAL REFERENCE ONLY" headers to:
  - `fsm.py`
  - `fsm_open.py`
  - `fsm_manage.py`
  - `fsm_close.py`
- Move to `arhive/` or `docs_arhive/` if no longer needed for DR replay.
- **Task**: `FSM-ARCHIVE-S1` — Archive legacy FSM files.

---

### 7.5. Test File Misplacement

**Issue**: Test files in `apps/reference/domains/execution_position/` instead of `tests/`.

**Files**:
- `test_binance_adapter_methods.py`
- `test_order_index.py`

**Recommendation**:
- Move to `tests/domains/execution_position/adapters/` or delete if redundant.
- **Task**: `TESTS-CLEANUP-S1`.

---

## 8. Proposed Future Tasks

### Priority 1 (Deduplication)

1. **UTILS-TPSL-DEDUP-S1** — Consolidate TP/SL Math
   - Scope: Refactor `tp_sl_calculator.py` as thin wrapper around `bracket_aggregator.py`.
   - Impact: Single source of truth for TP/SL calculations.
   - Risk: Low (bracket_aggregator already used by V2).

2. **WATCHDOG-DEDUP-S1** — Verify and Consolidate Watchdog Logic
   - Scope: Check if top-level `watchdog.py` is used outside V2. If not, deprecate.
   - Impact: Reduce duplicate invariant checking code.
   - Risk: Low (shadow_execpos/watchdog already active).

3. **METRICS-DEDUP-S1** — Consolidate Metrics Logic
   - Scope: Verify if `metrics_aggregator.py` duplicates `metrics_collector.py`. Consolidate.
   - Impact: Single metrics aggregation layer.
   - Risk: Low.

4. **IDEMPOTENCY-DEDUP-S1** — Consolidate Idempotency Logic
   - Scope: Verify if `idempotent_cancel.py` adds value beyond `shadow_execpos/idempotency.py`. Consolidate.
   - Impact: Single idempotency layer.
   - Risk: Low.

---

### Priority 2 (Integration Gaps)

5. **EP-PORT-GUARDIAN-S1** — Integrate OrderGuardian with V2 Runtime
   - Scope: Wire OrderGuardian auto-heal into ExecPosRuntimeV2 (replace watchdog detect-only).
   - Impact: Enable safe auto-cleanup of orphan/stale brackets.
   - Risk: Medium (requires careful integration, testing).

6. **TOOLS-TRACE-V2-S2** — Update order_trace for Latest V2 Contracts
   - Scope: Verify order_trace parsers match latest V2 log formats. Update if needed.
   - Impact: Accurate XAI/tracing for V2 runtime.
   - Risk: Low (parsers already stable).

---

### Priority 3 (Cleanup)

7. **TESTS-CLEANUP-S1** — Move or Delete Misplaced Test Files
   - Scope: Move `test_binance_adapter_methods.py`, `test_order_index.py` to `tests/` or delete if redundant.
   - Impact: Clean src/ directory.
   - Risk: Very Low.

8. **FSM-ARCHIVE-S1** — Archive Legacy FSM Files
   - Scope: Add "HISTORICAL REFERENCE ONLY" headers to legacy FSM files. Consider moving to `arhive/`.
   - Impact: Clear separation of active vs historical code.
   - Risk: Very Low (FSM not default runtime).

---

## 9. Dependencies & Integration Map

### V2 Runtime Core Dependencies

```
ExecPosRuntimeV2 (runtime.py)
├── AsyncManager (async_manager.py)
├── ExecutionService (execution_service.py)
├── Gatekeeper (gatekeeper.py)
│   ├── ExposureGuard (exposure_guard.py)
│   └── TradeCooldowns (utils/trade_cooldowns.py)
├── Watchdog (shadow_execpos/watchdog.py)
├── Idempotency (idempotency.py)
├── WALWriter (wal_writer.py)
│   └── vfoundation/dr/wal
├── ExposureBridge (exposure_bridge.py)
├── CloseFlowService (close_flow.py)
├── TrailingStopService (trailing.py)
└── BracketService (bracket_service.py)
    └── BracketAggregator (vfoundation/.../bracket_aggregator.py)
```

### OrderGuardian (Not Wired to V2)

```
OrderGuardian (services/order_guardian.py)
├── BinanceAdapter (adapters/binance_adapter.py)
├── ClientOrderIdMeta (utils.py)
└── BracketLinkage (internal state)
```

**Gap**: V2 uses watchdog (detect-only), OrderGuardian has auto-heal but not integrated.

---

### XAI/Observability Stack

```
order_trace (tools/order_trace/)
├── Parsers (parsers.py)
│   ├── Decision Logs (read)
│   ├── ExecPos Runtime Logs (read)
│   ├── WAL Records (read)
│   └── Exposure Events (read)
└── Engine (engine.py)
    └── TraceEvent Correlation

Metrics/Logs
├── MetricsCollector (metrics_collector.py)
├── LoggingV2 (shadow_execpos/logging_v2.py)
├── AuroraLogAdapter (aurora_log_adapter.py)
└── DriftMonitor (drift_monitor.py)
```

---

## 10. Summary Statistics

| Category | Count | Status |
|----------|-------|--------|
| **Total Files Inventoried** | ~55 | - |
| **ACTIVE (V2 Core)** | ~40 | In production use |
| **SUSPECT_DUPLICATE** | 4 | Needs consolidation |
| **SUSPECT_DEAD** | 2 | Needs verification |
| **LEGACY_DOC_ONLY** | 7 | Historical reference |

**V2 Runtime Complexity**:
- Core services: 17 files in `shadow_execpos/`
- Glue/config: 8 files in top-level `execution_position/`
- Tools: 6 files (order_trace + tca_execpos)
- Utils: 3 files
- Services/Adapters: 5 files

**Test Coverage** (from EP-PORT-BRACKETS-S1-PH2):
- `tests/domains/execution_position/`: 322 passed, 1 skipped
- Bracket service: 17 tests, 100% pass
- Coverage target: ≥90% (FSM), ≥80% (integration)

---

## 11. Conclusion

This inventory provides a comprehensive map of the execution_position codebase and related tools/utils/services. Key findings:

1. **V2 Runtime is ACTIVE**: All `shadow_execpos/` files are production-ready and default since EP-RUNTIME-WIRING-V2-S1.
2. **Legacy FSM is DEPRECATED**: `fsm*.py` files marked as LEGACY_DOC_ONLY, kept for DR replay only.
3. **Duplication Risks**: 4 files with suspected duplicate logic (TP/SL math, watchdog, metrics, idempotency).
4. **Integration Gap**: OrderGuardian exists but not wired to V2 (auto-heal capability unused).
5. **Test Coverage**: Strong (322 tests passing), but 2 test files misplaced in src/.

**Next Steps**: Prioritize UTILS-TPSL-DEDUP-S1, WATCHDOG-DEDUP-S1, then EP-PORT-GUARDIAN-S1 for auto-heal integration.

---

**Document Status**: COMPLETE (Inventory Only)
**No Code Changes Made**: ✅
**Ready for**: Deduplication and integration tasks (Priority 1-3).
