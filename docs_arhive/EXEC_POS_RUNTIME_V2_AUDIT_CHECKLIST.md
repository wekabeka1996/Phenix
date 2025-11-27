# Audit Checklist: Execution Position Runtime V2

- [x] **Phase 1: Inventory & Topology**
  - [x] List all files in `apps/reference/domains/execution_position/`.
  - [x] Identify "Core V2" vs "Legacy" vs "Shared".
  - [x] Map dependencies (imports).

- [x] **Phase 2: Deep Code Reading (The "Forensic" Part)**
  - [x] Read `shadow_execpos/runtime.py` (The Brain).
  - [x] Read `shadow_execpos/bracket_service.py` (The Logic).
  - [x] Read `binance_execution_adapter.py` (The Hands).
  - [x] Read `shadow_execpos/watchdog.py` (The Safety Net).

- [x] **Phase 3: Legacy & Dead Code Hunt**
  - [x] Grep for `legacy` imports in `shadow_execpos/`.
  - [x] Verify `fsm_manage.py` / `fsm_open.py` are just shims.
  - [x] Identify unused methods/classes in V2 files.

- [x] **Phase 4: Logical Integrity Analysis**
  - [x] **State Consistency:** Does `snapshot_state` ("FRESH", "UNKNOWN") actually prevent race conditions?
  - [x] **Error Handling:** How does `runtime.py` handle Adapter timeouts? (Does it crash or retry?)
  - [x] **Invariants:** Is `entry_price > 0` enforced before calculating brackets?
  - [x] **Concurrency:** Are `_guard_loop` and `handle()` truly async-safe?

- [x] **Phase 5: Test Coverage Mapping**
  - [x] Run coverage report for `execution_position`.
  - [x] Identify critical paths with < 80% coverage.
  - [x] Check if "Recovery Scenarios" (e.g., restart after crash) are tested.

- [x] **Phase 6: Reporting**
  - [x] Generate `EXEC_POS_RUNTIME_V2_AUDIT.md`.
  - [x] Update `JOURNAL.md`.
