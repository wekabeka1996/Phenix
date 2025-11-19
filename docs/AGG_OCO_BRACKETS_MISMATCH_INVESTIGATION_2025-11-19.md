# Aggregated OCO / OrderGuardian Brackets Mismatch Investigation (2025‑11‑19)

**Context (short):**  
Live system shows 3 open positions but 4 active brackets on the exchange:  
- 1 TP for BNB  
- 2 SL for BNB  
- 1 SL for BTC  
This violates the Aggregated OCO contract (`at most one bracket_set per (symbol, side)` and a single SL per protected position) and suggests a fragile interaction between the Aggregator OCO layer and `order_guardian` cleanup.

---

## Phases and Plan

**Phase 1 – Domain & Contract Mapping**  
- Map the `execution_position` domain around Aggregated OCO (FSMs, ManageFlow, OrderGuardian, watchdogs).  
- Reconcile high‑level contracts (`CONTRACT_aggregated_oco_v1`, `CONTRACT_aggregated_orders_v1`) with current code paths.  
- Identify all code locations that can place, adjust, or cancel aggregated TP/SL.

**Phase 2 – Behaviour from Tests & Logs**  
- Review `tests/domains/execution_position` Aggregated OCO and OrderGuardian tests to understand intended behaviour.  
- Cross‑check with recent incident logs (`logs/order_log_v1.jsonl`, execution logs if available) to reconstruct the 3‑positions‑4‑orders scenario.  
- Note any gaps where current tests do not cover partial close, scale‑in, restart, or race conditions relevant to this incident.

**Phase 3 – Contracts, Fragility & Failure Modes**  
- Trace the contracts and coupling between ManageFlow, Aggregated OCO logic, and `order_guardian` (bracket metadata, TTL, DR / restart, side normalisation).  
- Identify points where invariants can break (e.g. double SL, missing TP, orphaned brackets, race windows).  
- Classify fragility sources: state duplication, timing assumptions, adapter inconsistencies, or under‑specified contracts.

**Phase 4 – Integration Tests for Dynamic Positions & Brackets Lifecycle**  
- Design integration‑style tests that simulate the intended Aggregator OCO behaviour:  
  - first entry, multi‑scale‑in, partial closes, full close, flip, restart;  
  - ensuring exactly one TP+SL bracket set per `(symbol, side)` at all times;  
  - ensuring no orphaned TP/SL remain when positions are fully closed.  
- Implement tests in `tests/domains/execution_position` using existing helpers (`agg_oco_test_utils`, simulated adapter, FSM harnesses).  
- Make tests expressive enough to catch regressions like “two SL for one position” or “position without TP/SL”.

**Phase 5 – Root Cause Analysis & Fix Plan**  
- From code review + tests + logs, pinpoint concrete root causes of the observed mismatch.  
- Explain why the current design is fragile (where contracts are leaky, where state is duplicated, where races exist).  
- Propose and, if agreed, implement fixes (changes in Aggregated OCO logic, OrderGuardian, or FSM orchestration) so that the new integration tests pass and contracts are enforced.  
- Document final findings, decisions, and open risks.

---

## Phase 1 – Working Notes & Findings (to be updated)

- [x] Map core modules and entry points for Aggregated OCO and OrderGuardian.
  - ManageFlow FSM (`apps/reference/domains/execution_position/fsm_manage.py`) owns aggregated bracket computation (`_place_brackets_aggregated`, `_place_or_update_bracket_set_from_levels`) and registration (`_maybe_register_bracket_set`, `_log_bracket_set_event`).
  - ExecPos FSM (`apps/reference/domains/execution_position/fsm.py`) orchestrates flows, owns the aggregated OCO watchdog (`_run_agg_oco_watchdog_once`) and rehydration (`_rehydrate_guardian_state`).
  - OrderGuardian domain wrapper (`apps/reference/domains/execution_position/order_guardian.py`) delegates to services‑level guardian (ledger + cleanup logic), exposing `register_bracket_set`, `list_bracket_sets`, `rehydrate_bracket_set_for_position`, `ensure_single_bracket_set_for_position`, etc.
  - Watchdog helpers (`apps/reference/domains/execution_position/agg_oco_watchdog.py`) define invariants and normalisation for positions/orders and bracket metadata.
- [x] Align observed responsibilities with `CONTRACT_aggregated_oco_v1.md` and `CONTRACT_aggregated_orders_v1.md`.
  - Code follows the “one bracket_set per (symbol, side)” model and keys guardian metadata strictly by canonical `LONG`/`SHORT` sides.
  - ManageFlow computes TP/SL for aggregated positions and emits decisions; OrderGuardian is the sole owner of bracket metadata and cleanup; ExecPos watchdog only validates and auto‑heals via guardian, without ad‑hoc deletions.
- [x] List all flows that can create, replace, or cancel bracket sets.
  - Creation / recalc: `_place_brackets_aggregated` → `_place_or_update_bracket_set_from_levels` → `_emit_place_order` (SL/TP) → `_on_bracket_placed` → `_maybe_register_bracket_set` → `OrderGuardian.register_bracket_set`.
  - Replacement on scale‑in / partial‑close: same path, but `action` reflects `recalc_scale_in` / `recalc_partial`, and guardian bumps `version` and cancels superseded orders via `ensure_single_bracket_set_for_position`.
  - Cleanup on full close / flip / zero position: ExecPos cleanup loop + guardian `ensure_single_bracket_set_for_position` and `clear_bracket_set_for_position` remove reduce‑only TP/SL and metadata once `position_amt == 0`.
  - DR / restart: ExecPos watchdog calls `rehydrate_bracket_set_for_position` before validation to rebuild metas from live orders.

Summary (Phase 1):  
- Aggregated OCO architecture is consistent with the written contracts: ManageFlow is responsible for computing and issuing new brackets; OrderGuardian enforces the “single bracket_set per (symbol, side)” invariant and orphan cleanup; ExecPos provides periodic validation and DR rehydration.  
- The main risk areas are where these layers overlap in responsibility (e.g. when ManageFlow keeps local IDs but guardian state lags, or when ExecPos watchdog runs during bracket placement / cleanup).

---

## Phase 2 – Working Notes & Findings (to be updated)

- [x] Catalogue existing Aggregated OCO / OrderGuardian tests and what they guarantee.  
  - `tests/domains/execution_position/test_manage_flow_aggregated_oco.py` focuses on logging and side canonicalisation for `ManageFlowFSM`, plus a direct `set_bracket_ids` → `register_bracket_set` happy-path.  
  - `tests/domains/execution_position/test_aggregated_oco_multi_entry_flow.py` models multi-entry, partial-close, full-close flows using a fake adapter + services `OrderGuardian`, but runs with `ttl_protect_new_bracket_ms=0`, so TTL behaviour is never exercised.  
  - `tests/domains/execution_position/test_order_guardian_aggregated_cleanup.py` validates `ensure_single_bracket_set_for_position` TTL, cleanup, and fail-closed semantics, but only for single-symbol cases and with hand-crafted scenarios.  
  - `tests/domains/execution_position/test_agg_oco_runtime_pipeline_regression.py` wires `ExecPosFSM` with a stub guardian/watchdog and checks that a healthy pipeline places exactly one SL + one TP per position, but does not simulate scale-in/partial-close cycles nor TTL.
- [x] Reconstruct the “3 positions, 4 orders (1 TP BNB, 2 SL BNB, 1 SL BTC)” pattern from code and logs.  
  - Live `order_log_v1.jsonl` shows a single BNBUSDT entry fill (`ORDER_PLACED` for `ENTRY-39f3d38c62`) with no bracket orders logged there; bracket placement goes via `ExecPosFSM` adapter methods and `OrderGuardian`, not the generic order log.  
  - `domain_execution_management.log` shows continuous `AGG_OCO_WATCHDOG` warnings during the run, confirming the aggregated watchdog is active but not auto-healing all invariant breaches.  
  - For an aggregated-only configuration with `ttl_protect_new_bracket_ms=3000`, the following flow can produce “1 TP + 2 SL for BNB”:
    - First entry installs a bracket set `(SL1, TP1)` for `BNBUSDT/LONG`.  
    - A later scale-in / partial-close triggers `_recalc_aggregated_brackets` → new `(SL2, TP2)` plus `OrderGuardian.register_bracket_set` (meta now points to SL2/TP2 only).  
    - `ExecPosFSM` calls `OrderGuardian.cleanup_other_brackets_for_symbol`, which in aggregated mode defers to `ensure_single_bracket_set_for_position`.  
    - Inside `ensure_single_bracket_set_for_position`, the TTL guard (`age_ms < ttl_protect_new_bracket_ms`) **returns early before any cleanup**, so neither legacy nor aggregated cleanup removes the old `SL1`.  
    - There is no subsequent scheduled call to `ensure_single_bracket_set_for_position` after TTL expires (only on new bracket placements), so the extra SL remains indefinitely, yielding `SL1 + SL2 + TP2` for BNB plus one SL for BTC (3 positions, 4 reduce-only orders).
- [x] Identify missing scenarios or weak assertions in current tests.  
  - No test asserts that **for an open aggregated position there is at most one SL and one TP order** per `(symbol, side)`; watchdog invariants (`agg_oco_watchdog.validate_agg_oco_invariants`) only check “at least one SL” and “at most one meta”, not “exactly one SL/TP pair”.  
  - TTL behaviour is only tested in `test_ttl_guard_does_not_cancel_fresh_bracket`, which explicitly expects `ensure_single_bracket_set_for_position` to skip cancelling an extra SL when the meta is fresh; this encodes the fragile behaviour that leads to double SLs and never re-checks cleanup after TTL.  
  - There is no integration test that simulates scale-in / partial-close with TTL enabled and verifies that stale brackets are eventually cancelled while the active SL/TP pair is preserved.

Summary (Phase 2):  
- The observed “3 positions, 4 brackets” pattern is consistent with the current implementation: after a bracket recomputation, `ensure_single_bracket_set_for_position` is invoked exactly once via `cleanup_other_brackets_for_symbol`, but the TTL guard bails out before cancelling any extra SL/TP from the previous bracket set.  
- Because no component re-runs aggregated cleanup after TTL and watchdog invariants do not flag “multiple SL for open position” as a violation, these duplicates can persist indefinitely.  
- Existing tests validate logging and some cleanup semantics but miss the exact scenario that produced the live inconsistency (multi-symbol, aggregated-only mode with TTL > 0, repeated bracket recalcs, and the requirement “max one SL/TP per position at all times”).

---

## Phase 3 – Working Notes & Findings (to be updated)

- [ ] Map contracts and invariants between FSMs, Aggregated OCO, and `order_guardian`.  
- [ ] Enumerate concrete failure modes leading to double SL or missing TP/SL.  
- [ ] Flag specific fragile patterns in the implementation (e.g. duplicated state, unclear ownership of cleanup).

Summary (Phase 3): _pending_

---

## Phase 4 – Working Notes & Findings (to be updated)

- [ ] Draft test matrices for dynamic position / brackets lifecycle scenarios.  
- [ ] Implement integration tests that reproduce and then prevent the current incident.  
- [ ] Confirm tests fail with current implementation and pass once fixes are applied.

Summary (Phase 4): _pending_

---

## Phase 5 – Working Notes & Findings (to be updated)

- [ ] Tie failing behaviours to concrete root causes in code.  
- [ ] Document proposed fixes and trade‑offs.  
- [ ] Capture remaining risks and monitoring ideas for production.

Summary (Phase 5): _pending_
