# Validation Gap Report — Execution Position Domain (Wave 0)

Date: 2025-11-12
Scope: Cross-check of the “Validated Implementation Plan” against the actual codebase with evidence, deltas, and safe additive recommendations.

## Executive Summary
- Overall architecture matches the intended Wave 0 direction. Several claims in the “validated” plan diverge from the code reality and should be corrected before proceeding.
- No breaking changes required for Wave 0; gaps can be addressed via additive fixes and documentation updates.

## Confirmed (Grounded in Code)
- Exposure fail-closed and post-fill holds exist and are used pre-OPEN in `ExecPosFSM`.
  - Files: `apps/reference/domains/execution_position/fsm.py`, `exposure_guard.py`
  - Evidence: `_check_exposure_fail_closed()` invoked before DEC:OPEN; `ExposureGuard.on_fill()` implements post-fill holds.
- WAL is present and used for DEC decisions.
  - File: `vfoundation/dr/wal.py` (append/CAS/verify); `ExecPosFSM.handle()` appends DEC before execution.
- Order Guardian is active via domain wrapper and unified services implementation.
  - Files: `apps/reference/domains/execution_position/order_guardian.py`, `apps/reference/services/order_guardian.py`
  - Behavior: Orphan cleanup, reconcile, ownership tracking; cohesive integration from `ExecPosFSM`.
- Adapter mode guardrails exist for testnet vs live.
  - File: `apps/reference/domains/execution_position/fsm.py` `_initialize_adapter()` and `_execute_decision()` guard that TESTNET must use testnet URL.

## Mismatches vs. “Validated” Plan (Actionable)
1) ExposureGuard atomicity claim
   - Claim: “already atomic via asyncio.Lock around can_open/reserve”.
   - Actual: No explicit `asyncio.Lock` around `can_open()/reserve()/on_fill()` in `exposure_guard.py`. Operations are single-threaded under normal asyncio execution but not formally locked.
   - Impact: Low risk in single-loop contexts; potential race if called from multiple loops/threads.
   - Recommendation: Add an internal lock or ensure all calls happen on a single loop. Provide a note in docs; defer lock until a concrete multi-loop use case appears.

2) Message parent_rid field
   - Claim: “Message includes parent_rid for why-chain”.
   - Actual: `vfoundation/core/protocol.py::Message` has `rid, span_id, parent_span_id, data_ref, corr_id`, but no `parent_rid`.
   - Impact: Why-chain still possible (rid + parent_span_id + data_ref), but the exact claim is inaccurate.
   - Recommendation: If needed, add an additive `parent_rid: Optional[str]` later via schema process; for Wave 0, standardize on existing fields and helpers (factory to propagate `rid`/`data_ref`).

3) Event verb naming
   - Claim: Pipeline handles `EVT:TRADE_INTENT_GENERATED` end-to-end.
   - Actual: Core runtime uses `EVT:PORTFOLIO_STATE_UPDATED`, `EVT:ORDER_FILL` (plus legacy `FILL`). No runtime references to `TRADE_INTENT_GENERATED` were found.
   - Impact: Documentation drift; not blocking.
   - Recommendation: Align docs and tests with the actual verbs in use. Introduce aliases only if truly needed.

4) WAL replay
   - Claim: “FSM has WAL-driven replay out-of-the-box”.
   - Actual: WAL supports append/verify; replay/snapshotting is not implemented at the FSM layer.
   - Impact: Recovery flows are manual; not a problem for Wave 0.
   - Recommendation: Track a follow-on item: implement `replay(rid)` and snapshot integration on top of `wal.read_*` in a future phase.

5) Config duplication and overrides
   - Observation: `configs/master_config_v1.yaml` declares `trading:` twice; later section overrides earlier fields in YAML.
   - Impact: Confusing precedence, risk of silent overrides.
   - Recommendation: Consolidate into a single `trading` node (additive migration file or documented guidance). No “Kelly” fields found; remove “Kelly duplicates” claim from plan.

6) PositionTracking transactional guarantees
   - Claim: Implied dedicated PositionTracking component with transactional semantics.
   - Actual: No standalone tracker detected; `ExecPosFSM` uses adapter `get_open_positions` and portfolio EVT updates.
   - Impact: Claim is overstated for current code. Not blocking.
   - Recommendation: Update plan to reflect current approach; schedule a future enhancement only if needed.

## Key Evidence
- `apps/reference/domains/execution_position/fsm.py`:
  - Pre-OPEN exposure gate; testnet/live guard rails; WAL append; TP/SL placement with backoff for `-2021`.
- `apps/reference/domains/execution_position/exposure_guard.py`:
  - Fail-closed on stale/unknown portfolio; post-fill holds; soft-clip scaffolding; fallback mode.
  - Cleanup logs include `CLEANUP_PENDING` and `CLEANUP_POSTFILL`.
- `vfoundation/core/protocol.py`:
  - `Message` with no `parent_rid` field; uses `parent_span_id`, `data_ref`, `corr_id`.
- `configs/master_config_v1.yaml`:
  - Duplicate `trading` sections; second overrides first; no Kelly parameters present.

## Risks and Mitigations
- Concurrency/atomicity in ExposureGuard: keep single-loop execution; document; add lock later if multi-loop usage appears.
- Config shadowing: YAML duplicate keys may surprise maintainers; propose a single source of truth and additive migration notes.
- WAL replay not available: postpone to later phase; not required for Wave 0.

## Additive Recommendations (Wave 0 Safe Set)
1) Documentation/Contracts
   - Update plan/docs to remove incorrect claims (lock, parent_rid, TRADE_INTENT_GENERATED) and reflect actual verbs/fields.
   - Add a short “Why-chain usage” guideline: use `rid` + `parent_span_id` + `data_ref` consistently.

2) Config Hygiene
   - Provide a consolidated example config with a single `trading` node; annotate precedence if legacy structure is kept for backward compatibility.

3) Naming/Observability polish
   - Optionally rename log tag `CLEANUP_PENDING` to `STALE_ORDER_CLEANUP` for clarity (additive only; keep old string acceptable as legacy).

4) Test Additions
   - Guardrail tests: verify testnet mode blocks live URL; verify exposure gate emits events on stale portfolio.
   - End-to-end EVT tests: ensure `EVT:ORDER_FILL` and `EVT:PORTFOLIO_STATE_UPDATED` flows update exposure and emit `EXPOSURE_SUMMARY_UPDATED`.

## Deferred (Post–Wave 0)
- WAL-backed FSM replay/snapshotting (`replay(rid)`, snapshots, hydration hooks).
- Optional `Message.parent_rid` (JSON Schema additive) + factory helpers.
- Explicit `asyncio.Lock` in `ExposureGuard` if multi-loop access becomes a real need.

## Next Steps
1) Align docs and “validated plan” with the above deltas (no code changes required).
2) Add minimal guardrail and EVT flow tests to lock current behavior.
3) Prepare a follow-up issue for config consolidation guidance and optional ExposureGuard lock.
