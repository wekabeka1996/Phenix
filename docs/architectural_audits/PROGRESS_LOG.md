# PROGRESS LOG — Telemetry/Monitoring/Orchestrator Remediation

## 2026-02-24

### Iteration 1 — RCA Completed
- Confirmed centralized `OrchestratorFSM` anti-pattern and cleanup/signing defects.
- Confirmed unbounded memory growth in `TradeLifecycleLogger._trades` and `AlertManager.recent_alerts`.
- Confirmed `AlertManager` SSOT bypass through direct env reads.
- Confirmed lock-based, custom `PerformanceMonitor` duplication/overhead.

### Iteration 2 — Implementation Started
- Added typed `AlertsConfig` into `AuroraConfig.observability.alerts`.
- Refactored `AlertManager` to consume config-only alert settings.
- Added bounded cleanup (`_prune_recent_alerts`) with TTL + hard-cap eviction.

### Iteration 3 — Memory Leak Remediation
- Added TTL sweeper (`sweep_expired`) to `TradeLifecycleLogger`.
- Added max-open-trades capacity guard with LRU-style eviction.
- Added tests for TTL eviction and capacity eviction.

### Iteration 4 — Architecture Decommission
- Migrated `LocalBus` import paths to `execution_position` domain fallback.
- Deleted `apps/reference/orchestrator/` implementation files.
- Removed obsolete orchestrator/performance monitor unit tests tied to removed modules.

### Iteration 5 — Metrics Migration
- Added Prometheus-native decision latency/outcome metrics helpers in telemetry metrics module.
- Deleted legacy lock-based `apps/reference/monitoring/performance_monitor.py`.

---

## Services & Core Domain Remediation (2026-02-24)

### Triage Findings
- Live file inspection confirmed migration was already partially complete: all three `apps/reference/services/` files (`order_guardian.py`, `limit_order_monitor.py`, `ledger_store_adapter.py`) were already deprecation shims pointing to canonical implementations in `execution_position`.
- Canonical `execution_position/order_guardian.py` (1360 LOC): full implementation with config-driven store selection, no polling.
- Canonical `execution_position/limit_order_monitor.py` (311 LOC): per-order asyncio timer tasks, no polling loop.
- Canonical `execution_position/infra/ledger_store_adapter.py` (159 LOC): SQLite SSOT with proper soft-delete for Split-Brain prevention.
- `PLAN_SERVICES_CORE.md` corrected to reflect actual state.

### Actions Taken
1. Updated `PLAN_SERVICES_CORE.md` with corrected triage (supersedes stale analysis).
2. Fixed 9 remaining import sites (`apps.reference.services.*` → `apps.reference.domains.execution_position.*`):
   - 8 × `order_guardian` imports in tests
   - 1 × `ledger_store_adapter` import in `tools/diagnose_execution.py`
3. Deleted `apps/reference/services/` directory (4 files: `__init__.py` + 3 shims).
4. Fixed regression in `execution_position/order_guardian._build_store_from_config`: added `if config is None: return InMemoryStore()` guard to restore backward-compat default (old services code defaulted to `InMemoryStore` when no config passed; new canonical code incorrectly defaulted to `LedgerStoreAdapter`).
5. Fixed `tests/test_tpsl_placement.py` fixture: changed `config={}` to `config=None` (dict rejected by TypedConfig guard added in canonical impl).

### Test Results
- Affected tests (53): all pass ✅
- Pre-existing decision_making failures (10): unchanged, confirmed pre-existing ✅
- Full suite: 669 passed, 28 skipped, 7 deselected, 10 pre-existing failures

### DoD Status
- [x] `apps/reference/services/` directory deleted
- [x] Zero `from apps.reference.services` imports in live codebase (only `.trash/` dead files)
- [x] `pytest` affected subset green (53/53)
- [x] Split-Brain addressed in canonical `LedgerStoreAdapter` (soft-delete implemented)
- [x] `LimitOrderMonitor` event-driven (per-order timers, no polling)
- [x] `PROGRESS_LOG.md` updated

