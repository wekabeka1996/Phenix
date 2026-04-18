# ExecPosFSM Decomposition Roadmap v1.2

**Status**: Draft — Advisory Roadmap (SSOT for execution_position fsm.py decomposition)
**Scope**: `apps/reference/domains/execution_position/fsm.py` (4,675 LOC, ~120 methods)
**Owner**: execution_position domain
**Date**: 2026-04-18
**Branch**: `Phenix_v2`
**Mode**: Additive-only. No broad rewrite. Contract-first.

This document is the phased implementation map for breaking ExecPosFSM down
without violating runtime truth ownership. It must be followed in order.
No package may start until the previous package has landed with validation
evidence recorded per `docs/ai/AGENT_REPORT_SCHEMA.md`.

### Revision history

- **v1.0 (2026-04-18)** — initial roadmap.
- **v1.1 (2026-04-18)** — applied external review:
  1. Added **Package 0 — Truth-boundary freeze inside `fsm.py`** before P1.
  2. Swapped order of former P2 and P3 (position-policy mediator now precedes
     bracket-ownership registry, because mediator is more locally bounded and
     ownership is cross-cutting through restore/health/recovery).
  3. Made P6 sub-splitting into 6a/6b/6c **mandatory**, not recommended.
  4. Added domain-contract note: `execution_position` must stay an
     **execution soldier** (owns lifecycle truth, accepts intents).
     `decision_making` remains owner of strategy dispatch and
     `TRADE_INTENT_PROPOSED`. No new policy/decision logic may be added to
     `execution_position` during decomposition.
- **v1.2 (2026-04-18)** — pre-P0 micro-revision before any implementation:
  1. **Explicit forbidden private-state list** hardened into Package 0
     (named attributes, grep-verifiable).
  2. **Explicit sanctioned accessor/mutator allowlist** hardened into
     Package 0 as the only permitted surface for new modules to reach
     ExecPosFSM state.
  3. Added exit criterion **"no new back-pointer spread"** to §19:
     new modules MUST NOT read or write `fsm._<private>` attributes
     outside the allowlist; `self._fsm` references limited to sanctioned
     method calls only.
  4. Reduced dependence on absolute line numbers: all anchors are now
     symbol names (method / attribute / class). Remaining `L####` refs
     are retained as *indicative ranges only* and MUST NOT be used as
     navigation primitives by later packages — they drift across commits.

---

## 1. Problem framing

`apps/reference/domains/execution_position/fsm.py` is ~4,675 lines,
~120 methods on `ExecPosFSM`, with a multi-hundred-line `__init__` wiring
~30 sub-systems (line ranges captured at time of analysis are indicative
only — navigate by symbol, not by line number). Phase 14A/14.2 Strangler-Fig extractions introduced 16 sibling
modules, but `fsm.py` remains the **central runtime-truth owner** for:

- bracket ownership,
- position-policy close-request mediation,
- restore artifacts,
- canonical fill ingress,
- startup runtime-truth reconstruction.

The question is **not** "should it be decomposed?" — it already is, partially.
The question is: **what is the shape of the residual God object, and what is
the next safest surgical cut that preserves runtime truth ownership?**

---

## 2. FACTS (runtime-verified from code)

- **F1.** `ExecPosFSM` inherits 4 mixins: `ConfigResolverMixin`,
  `AsyncSchedulingMixin`, `AdapterInitMixin`, `HealthMetricsMixin`.
- **F2.** `__init__` constructs 9 collaborator objects (`_lev_cfg`,
  `_entry_mgr`, `_exposure_mgr`, `_lifecycle_mgr`, `_intent_router`,
  `_evt_handlers`, `_close_exec`, `_open_exec`, `_bracket_mgr`) plus sidecar,
  truth_hardening, shadow_journal, intent_boundary_audit, restore/truth
  artifact writers, watchdog, order_guardian, alert_manager.
- **F3.** Bus wiring happens **only in `ExecPosFSM.__init__`** (8 listeners on
  `self.bus.listen`). Sidecar receives events through re-dispatch in `_on_*`
  methods, not direct subscription.
- **F4.** `handle()` is the central DEC dispatcher and contains inline logic
  for: cooldown gate, `OPEN_GUARD_FAIL` construction, pending intent caching,
  close-guard evaluation (`hardening.evaluate_close_command`),
  `_closing_position` flag mutation, shadow-journal transition recording,
  and restore-artifact snapshot persistence on signature change.
- **F5.** `_execute_decision()` is a thin dispatcher to `_close_exec`/
  `_open_exec`, but still contains: testnet/live guardrail check, non-CMD
  close hardening re-check, centralized `UncertainSubmitRecoveryError`
  translation, canonical `EVT:ORDER_REJECTED` emission, and
  `_exec_error_counts` circuit breaker increment.
- **F6.** Runtime-truth dictionaries owned by `ExecPosFSM`:
  `_symbol_brackets`, `_symbol_bracket_truth_source`,
  `_symbol_manage_truth_source`, `_pending_brackets`,
  `_bracket_owner_by_symbol`, `_pending_intent_data`,
  `_last_lifecycle_rid/ikey/fill_price_by_symbol`,
  `_last_realized_pnl_by_symbol`, `_last_close_reason_by_symbol`,
  `_proven_terminal_close_by_symbol`, `_position_policy_close_requests`,
  `_supersede_queue`, `_supersede_canceling`, `_open_regime_by_symbol`,
  `_last_regime_by_symbol`, `_open_strategy_by_symbol`,
  `_pending_entry_meta`, `_last_features_cache`,
  `_portfolio_event_stage_traces`, `_latest_portfolio_state`,
  `_prev_position_amts`, `_last_position_closed_ts`,
  `_last_any_position_closed_ts`, `_accumulated_fees_by_symbol`,
  `_last_trade_id_by_symbol`, `_last_entry_side_by_symbol`.
- **F7.** Canonical fill ingress (`_build_canonical_fill_message` /
  `_handle_canonical_fill_ingress`, L2925–L3204) lives in `fsm.py`, not in
  `event_handlers.py`. It calls back into `_evt_handlers.on_trade_executed` /
  `on_order_fill` for bookkeeping, then drives `manage_flow.handle()` directly.
- **F8.** Position-policy close-request mediation
  (`_on_position_policy_close_request`, `_parse_position_policy_close_request`,
  `_position_policy_allowed_scope`, `_emit_position_policy_close_request_state`,
  L3262–L3568) lives **in `fsm.py`**, not in `position_policy_sidecar.py`.
  The sidecar emits the request; `fsm.py` applies the suppression matrix.
- **F9.** Restore & startup-truth logic (L1162–L2450, ~1,300 lines) lives in
  `fsm.py`. The `restore_artifact.py` module provides **data classes and
  writers**, not orchestration.
- **F10.** Strategy-owner resolution for brackets (`_resolve_bracket_strategy_owner`,
  `_resolve_strategy_owner_from_decision`, `_resolve_strategy_owner_for_recovery`,
  `_remember_bracket_owner`, `_append_bracket_ownership_record`,
  L2569–L2838) lives in `fsm.py`, not in `bracket_manager.py`.
- **F11.** Bracket health loop (`_schedule_bracket_health_check`,
  `_bracket_health_loop`, `_run_bracket_health_check`,
  `_check_brackets_on_exchange`, `_compute_strategy_health_check_brackets`,
  `_place_health_check_brackets`, L3666–L4171) lives in `fsm.py`.
  `bracket_manager.py` only handles deferred brackets + preflight.
- **F12.** Advanced pending-entry guards (`_evaluate_supersede_reprice_guard`,
  `_evaluate_advanced_stale_cancel`, L834–L1004) live in `fsm.py` and call
  back into `_entry_mgr` for execution. `_resolve_price` also lives here.
- **F13.** Local-open guard (`_local_open_guard`, L4804–L4877) constructs the
  canonical `OPEN_GUARD_FAIL` payload with divergence detection.
- **F14.** Sidecar receives events via **manual re-dispatch** from `_on_*`
  handlers plus from fill ingress. Not a bus subscriber.
- **F15.** Extracted module sizes: `open_executor.py` 1102, `truth_hardening.py`
  953, `position_policy_sidecar.py` 927, `event_handlers.py` 806,
  `close_executor.py` 802, `intent_router.py` 630, `bracket_manager.py` 635,
  `restore_artifact.py` 644.
- **F16.** `_portfolio_event_stage_traces` (256-entry bounded FIFO) is used
  only for forensic sidecar-refresh trace.
- **F17.** Watchdog, `BoundedEventDeduper`, AlertManager, OrderGuardian
  initialization all live inline in `__init__`.

---

## 3. INFERENCES (code-supported, not runtime-verified)

- **I1.** The 4 mixins are **cosmetic inheritance splits**, not subsystem
  boundaries — they share `self` state with no interface contract.
- **I2.** Existing extracted objects all take `self` as their first
  constructor argument (`Manager(self)` pattern) — meaning they are
  **back-pointer façades**, not independent components. They read/write the
  same truth dictionaries listed in F6.
- **I3.** `ExecPosFSM` is a **hidden composition root** (F2) **and** a
  **runtime truth owner** (F6) **and** an **orchestration shell** (F4, F5)
  **and** a **bus ingress adapter** (F3). Classic "mixed shell + truth owner
  + composition root" anti-pattern.
- **I4.** The sidecar re-dispatch pattern (F14) is load-bearing: it ensures
  the incumbent handlers run **before** sidecar observers, protecting
  ownership order. Breaking this order is the single most dangerous class
  of change.
- **I5.** Canonical fill ingress (F7) is logically a separate subsystem
  but deeply entangled with `manage_flow.handle()` invocation, proven-
  terminal-close remembering, fill-ingress record append, and sidecar-after-
  result guard.
- **I6.** Position-policy close mediation (F8) forms a self-contained
  pipeline: parse → suppression matrix → emit `CMD:CLOSE` via `self.handle()`
  → track → complete on `EXECUTION_CLOSE_RECONCILED`. Extractable **if** it
  gets a narrow handle to `fsm.handle()`, truth-hardening, and
  portfolio-state.
- **I7.** Restore / startup-truth (F9) has clean envelope/record shapes but
  depends on 7 mutable dictionaries and calls into `manage_flow`/`close_flow`
  state directly. Extractable but not first.

---

## 4. ASSUMPTIONS (stated, not proven)

- **A1.** Tests cover `handle()` contracts and
  `_on_position_policy_close_request` suppression paths. Unproven without
  running `tests/domains/execution_position/` against the current `fsm.py`.
- **A2.** `_evt_handlers.on_trade_executed` does **not** itself call
  `manage_flow.handle()` — the canonical fill ingress handles activation.
- **A3.** `restore_artifact.py` data classes are used exclusively through
  the writers/readers, not duplicated elsewhere.
- **A4.** The sidecar re-dispatch order is stable because no current listener
  mutates the `Message` object in place.

---

## 5. UNKNOWNS

- **U1.** Whether any test asserts the specific call order inside
  `_handle_canonical_fill_ingress` (trade_executed bookkeeping → flow
  activation → sidecar).
- **U2.** Whether `_position_policy_close_requests` is read by any path
  other than `_on_execution_close_reconciled`.
- **U3.** Whether `_portfolio_event_stage_traces` is consumed by any
  external reporter or only observed in tests.
- **U4.** The exact durable downstream effects of
  `_apply_authoritative_local_close_reset` + `clear_symbol=True`.
- **U5.** Whether `_intent_boundary_audit` registers listeners that overlap
  with `_intent_router`.

---

## 6. Responsibility map of `ExecPosFSM`

| # | Responsibility | Location | Delegates to | Owned state |
|---|---|---|---|---|
| R1 | Composition root | `__init__` | — | all collaborator refs |
| R2 | Config contract enforcement | `__init__` L362-L500 | `ConfigResolverMixin` (partial) | config-derived scalars |
| R3 | Bus listener wiring | `__init__` L565-L594 | — | `bus` |
| R4 | Flow factory per symbol (thread-safe) | L4173-L4267 | — | flows dicts + `_flows_lock` |
| R5 | Central `handle()` dispatch + verb routing | L4321-L4504 | `_close_exec`, `_open_exec`, flows | `_pending_intent_data`, closing flag |
| R6 | Async `_execute_decision` + guardrail + error funnel | L4505-L4696 | `_close_exec`, `_open_exec` | `_exec_error_counts` |
| R7 | Canonical fill ingress | L2925-L3204 | `_evt_handlers` (bookkeeping only) | proven-terminal cache, fill ingress WAL |
| R8 | Bus event re-dispatch façade `_on_*` | L1108-L1144, L3205-L3234 | `_evt_handlers`, `_intent_router`, sidecar | trace FIFO |
| R9 | Position-policy close-request mediator | L3262-L3568 | `hardening`, `self.handle()` | `_position_policy_close_requests` |
| R10 | Restore-artifact authoritative read/apply/dark-read/persist | L1162-L2446, L3635-L3664 | restore writers/readers | bracket + manage-truth dicts |
| R11 | Startup truth reconstruction | L1579-L1780, L4957+ | order_guardian, order_index | bracket/manage truth dicts |
| R12 | Bracket ownership truth (strategy resolution + JSONL) | L2533-L2838, L2839-L2910 | `config.strategies_registry` | `_bracket_owner_by_symbol`, `_open_strategy_by_symbol` |
| R13 | Bracket health loop | L3666-L4171 | adapter, guardian, `_bracket_mgr.preflight` | `_bracket_health_started`, regime cache |
| R14 | Local OPEN guard + exposure bridge | L4804-L4881 | `_exposure_mgr` | portfolio state, lifecycle caches |
| R15 | Cooldown-after-close gate | `handle()` L4339-L4357 | — | `_last_any_position_closed_ts` |
| R16 | Advanced pending-entry guards | L834-L1004 | `_entry_mgr` for action | `_pending_entry_meta`, features |
| R17 | Idempotent cancel helper façade | L1023-L1084 | `IdempotentCancelHelper`, adapter | helper + max_retries |
| R18 | Async background loops | mixin + L4941+ | guardian, adapters | scheduling flags, orphan metrics |
| R19 | Portfolio state cache + forensic trace FIFO | L2449-L2523 | — | dicts |
| R20 | Observability emission | L4783-L4803, L4906-L4930 | `bus`, `LOG` | — |
| R21 | Shutdown + graceful teardown | L3596-L3618 | watchdog, guardian, ws, audit | — |
| R22 | Shadow-journal transition recording | `handle()` finally | `shadow_journal` | — |
| R23 | Flow-result processing (WAL + async schedule) | L3052-L3108 | `wal`, `_execute_decision` | — |
| R24 | Hydrate + restore-from-snapshot entries | L4269-L4320 | flows, shadow_journal | — |

---

## 7. Existing extractions: real vs superficial

| Module | Real delegation? | Notes |
|---|---|---|
| `leverage_config.py` | **Real** | Three one-line wrappers in `fsm.py`. Clean. |
| `entry_manager.py` | **Real** | Owns cancel/supersede/timeout/panic. Reads fsm state. |
| `exposure_manager.py` | **Real** | Owns exposure checks + bookkeeping. |
| `lifecycle.py` | **Unknown / low-usage from fsm.py** | Likely consumed by ManageFlowFSM. |
| `intent_router.py` | **Real** (one-line delegations), but 630 LOC implies re-owned intent logic. |
| `event_handlers.py` | **Partial**. Owns regime/order_ack/features/tidy. Does **NOT** own canonical fill ingress (F7). |
| `close_executor.py` | **Real** for `_execute_decision` CLOSE/CANCEL/PLACE. Does **NOT** own `_on_execution_close_reconciled` or close-request mediator. |
| `open_executor.py` | **Real** for submission. `UncertainSubmitRecoveryError` crosses boundary back to fsm.py. |
| `bracket_manager.py` | **Partial**. Owns preflight + deferred. Does **NOT** own health loop (R13), ownership records (R12), or snapshot APIs (R10). |
| `position_policy_sidecar.py` | **Real for observation side** (regime/features/fill/portfolio + recommendation). Does **NOT** own close-request mediation (R9). |
| `restore_artifact.py` | **Real for writers / readers / dataclasses**. Does **NOT** own orchestration (R10/R11). |
| `truth_hardening.py` | **Real** — evaluation + caches. |
| `async_scheduling.py` | **Cosmetic mixin**. |
| `adapter_init.py` | **Cosmetic mixin**. |
| `health_metrics.py` | **Cosmetic mixin**. |
| `config_resolver.py` | **Cosmetic mixin**. |

---

## 8. Root cause vs symptom

- **Symptom**: `fsm.py` is 4,675 lines.
- **Masking layer**: Phase 14A/14.2 mixins and `Manager(self)` objects
  reduce apparent method count on the class but keep state ownership
  identical.
- **Contributing factors**: bus wiring in `__init__`; 26+ per-symbol
  dictionaries never normalized into an owned sub-state; canonical fill
  ingress positioned at the dispatch layer; close mediation living in the
  dispatcher rather than adjacent to the sidecar.
- **Root cause**: `ExecPosFSM` conflates three responsibilities that can
  be independently reasoned about:
  1. **Bus ingress / dispatcher shell** (R3, R5, R6, R8, R23).
  2. **Symbol-level runtime truth repository** (F6, R7, R10–R12, R19).
  3. **Cross-cutting orchestration policies** (R9, R11, R13, R22).
  Until the **truth repository** is named as its own object with an
  explicit API, further file splits just move methods without reducing
  coupling.

---

## 9. Recommended target architecture

Introduce (eventually) an explicit **`ExecutionPositionTruthStore`** that
owns the per-symbol mutable state and exposes a narrow API. `ExecPosFSM`
becomes the dispatcher shell + bus adapter. Managers continue to hold a
back-pointer, which later becomes a reference to the truth store, then to a
narrow interface.

**Target shape (additive, no-rewrite)**:

- `fsm.py`: bus wiring, `handle()`, `_execute_decision()`, `hydrate()`,
  `shutdown()`, flow factory, shadow-journal integration, cooldown-after-
  close gate, `OPEN_GUARD_FAIL` construction. Target **< 1,500 lines**.
- `bracket_ownership.py` (new): R12.
- `bracket_health.py` (new): R13.
- `position_policy_mediator.py` (new, separate from sidecar): R9.
- `fill_ingress_coordinator.py` (new): R7.
- `startup_truth_orchestrator.py` (new): R10/R11 orchestration only (writers
  stay in `restore_artifact.py`).
- `pending_entry_guards.py` (new): R16.
- Keep `restore_artifact.py`, `truth_hardening.py`, existing managers.
- Mixins remain until the truth store lands.

---

## 10. Method-to-module migration table (additive-only)

| Method(s) in fsm.py | Target | Rationale | Shared state needed | Form |
|---|---|---|---|---|
| `_resolve_bracket_strategy_owner`, `_resolve_strategy_owner_from_decision`, `_resolve_strategy_owner_for_recovery`, `_strategy_assignments_for_symbol`, `_strategy_profile_has_symbol`, `_remember_bracket_owner`, `_append_bracket_ownership_record` | `bracket_ownership.py` | Cohesive strategy resolution + ownership journal; one record-kind. | `_bracket_owner_by_symbol`, `_open_strategy_by_symbol`, `config.strategies_registry`, `config.strategies`, `_persist_restore_artifact_snapshot`, `_emit_observability_event`, `_trade_lifecycle_log_path` | Manager (`BracketOwnershipRegistry`). |
| `_schedule_bracket_health_check`, `_bracket_health_loop`, `_run_bracket_health_check`, `_check_brackets_on_exchange`, `_resolve_health_check_bracket_context`, `_compute_strategy_health_check_brackets`, `_compute_health_check_brackets`, `_place_health_check_brackets` | `bracket_health.py` | Independent async subsystem. | adapter, guardian, `_symbol_brackets`, `_last_regime_by_symbol`, `BracketOwnershipRegistry`, `_bracket_mgr.preflight_position_check` | Manager. Depends on BracketOwnershipRegistry. |
| `_on_position_policy_close_request`, `_parse_position_policy_close_request`, `_position_policy_allowed_scope`, `_position_policy_context_from_request_payload`, `_emit_position_policy_close_request_state`, `_position_policy_known_symbols`, `_create_position_policy_sidecar` | `position_policy_mediator.py` | Self-contained parse→suppression→CMD:CLOSE→state pipeline. | `config`, `bus`, `handle` ref, `manage_flows`, `hardening`, `_position_policy_close_requests`, portfolio getters, trade-lifecycle log | Mediator. `_on_position_policy_close_request` remains a one-line delegation. |
| `_build_canonical_fill_message`, `_missing_fill_activation_fields`, `_append_execution_fill_ingress_record`, `_handle_canonical_fill_ingress`, `_remember_proven_terminal_close`, `get_recent_terminal_close_proof` | `fill_ingress_coordinator.py` | Canonical-fill pipeline with clear inputs/outputs. | `manage_flows`, `_get_or_create_flows`, `_evt_handlers`, `_position_policy_sidecar`, `_latest_portfolio_state`, position signature getter, `_proven_terminal_close_by_symbol`, order_index, `_process_flow_result` | Coordinator. `_on_trade_executed`/`_on_order_fill`/`handle(TRADE_EXECUTED/ORDER_FILL)` become thin delegations. |
| All restore/startup-truth methods (~24 methods, L1162-L2446, L4957+) | `startup_truth_orchestrator.py` | Largest cohesive block. **Highest risk** — mutates manage/close flow state and truth dicts directly. | Everything in F6 + manage/close flows + `_wire_*` helpers | Orchestrator taking ExecPosFSM handle. |
| `_evaluate_supersede_reprice_guard`, `_evaluate_advanced_stale_cancel`, `_resolve_price` | `pending_entry_guards.py` | Pure evaluation; delegates action to `_entry_mgr`. | `_pending_entry_meta`, `_last_features_cache`, watchdog pending/acked, config pending_entry_ttl, `_emit_observability_event` | Helper. |
| `_set_symbol_bracket_order`, `_set_symbol_brackets_snapshot`, `_clear_symbol_brackets`, `_symbol_bracket_truth_source_for`, `_manage_truth_source_for`, `_set_manage_truth_source`, `_clear_manage_truth_source`, `_apply_authoritative_local_close_reset` | **Stay in fsm.py for now** | Core truth-store primitives. Too many cross-manager call sites. | — | Keep. Document as future `ExecutionPositionTruthStore` API. |
| `_portfolio_event_trace_id`, `_record_portfolio_event_trace_stage`, `_portfolio_event_trace_snapshot` | Stay | Forensic-only, low reward. | — | — |
| `_cancel_order`, `_is_cancel_success_response`, `_cancel_status_str`, `_is_unknown_order_error` | Stay | Thin façade over `IdempotentCancelHelper`. | — | — |

---

## 11. What must stay in `fsm.py`

- `__init__` (composition root until truth store lands).
- Bus listener wiring (R3).
- `handle()` + `_execute_decision()` dispatch shell (R5, R6).
- Flow factories `_create_open_flow`, `_get_or_create_*`, `_wire_*` (R4).
- Truth-store primitives listed above.
- Cooldown-after-close gate, `_local_open_guard`,
  `_cancel_entry_reservation`.
- `shutdown()`, `hydrate()`, `restore_startup_from_snapshot_positions()`,
  `start_order_guardian()`, `open_flow/manage_flow/close_flow` accessors.
- `_emit_observability_event`, `_emit_execution_bus_event`.
- `_process_flow_result`.
- `PendingEntryMeta` local DTO.

---

## 12. Critical invariants that must not break

1. **Bus listener registration order** (F3). `bus.listen(...)` must not move
   out of `fsm.__init__` without preserving time-ordering vs sidecar announce.
2. **Sidecar-after-incumbent order** in `_on_*` handlers (F14).
3. **Canonical fill ingress call sequence** (F7, I5): trade_executed
   bookkeeping (with `_skip_trade_lifecycle_on_fill`) → order_fill
   bookkeeping → `manage_flow.handle(canonical_msg)` →
   `_append_execution_fill_ingress_record` → sidecar notify →
   `_process_flow_result`.
4. **Close-guard duplicate suppression** in both `handle(CMD:CLOSE)` (L4404)
   and `_execute_decision(DEC:CLOSE)` (L4526): non-CMD path MUST re-check;
   `close_guard_prevalidated` only honored for CMD path.
5. **Bracket ownership record idempotency** via fingerprint comparison
   (L2797).
6. **Authoritative restore short-circuits heuristic hydrate** in
   `restore_startup_from_snapshot_positions` (L4310).
7. **`_closing_position` flag set synchronously in `handle(CMD:CLOSE)`**
   before `close_flow.handle` (L4442).
8. **Shadow-journal `record_transition` always runs in `handle()` finally**
   (R22).
9. **Position-policy close-request suppression matrix order** (L3301–L3346):
   identity → scope → manage flow → portfolio → hardening.
10. **`_apply_authoritative_local_close_reset`** is the **only** path that
    atomically resets manage state, close state, brackets, and pending
    brackets for a symbol.
11. **`_persist_restore_artifact_snapshot` triggered on semantic signature
    change** in `handle()` (L4488).
12. **Pending-brackets WAL hydration skipped in backtest** (L492).

---

## 13. Duplication / near-duplication observed

- **Close guard evaluation** appears twice (CMD vs non-CMD DEC) with slightly
  different helpers. Intentional distinction. Keep.
- **`_compute_health_check_brackets`** appears to trivially unwrap
  `_resolve_health_check_bracket_context`. Possibly dead; confirm callers
  before removing (UNKNOWN).
- `_cancel_pending_entries_for_symbol` / `_cancel_all_pending_entries` /
  `on_panic_killswitch_activated` are one-line delegations — cosmetic.
- Watchdog/`orphan_monitor` dict mirror in `__init__` duplicates what a
  single `WatchdogConfig` resolver would express.
- `_resolve_price` could live alongside other normalizers in `utils.py`.

---

## 14. Safe package order

Each package is additive, behind existing public contracts, validated before
the next starts.

### Package 0 — Truth-boundary freeze inside `fsm.py` (prerequisite)

**Not an extraction.** A discipline-setting pass that must land before any
code moves to new modules.

Deliverables:

1. **Sanctioned accessor / mutator allowlist** (the ONLY surface new
   modules may use to reach ExecPosFSM state). Each entry annotated in
   `fsm.py` with `# sanctioned-api: truth-store` marker:

   *Bracket truth-store (mutators)*:
   - `_set_symbol_bracket_order`
   - `_set_symbol_brackets_snapshot`
   - `_clear_symbol_brackets`

   *Bracket truth-store (readers)*:
   - `_symbol_bracket_truth_source_for`
   - `_get_symbol_brackets_snapshot` (if exists; else add)

   *Manage-flow truth*:
   - `_manage_truth_source_for`
   - `_set_manage_truth_source`
   - `_clear_manage_truth_source`

   *Close-path authoritative reset*:
   - `_apply_authoritative_local_close_reset`

   *Portfolio state readers*:
   - `_latest_portfolio_state`
   - `_get_portfolio_state_for_symbol`
   - `_get_portfolio_position_signature`
   - `_has_active_lifecycle_for_symbol`

   *Shared write helpers / emitters*:
   - `_persist_restore_artifact_snapshot`
   - `_emit_observability_event`
   - `_emit_execution_bus_event`
   - `_trade_lifecycle_log_path`
   - `_process_flow_result`

   *Loop + timing*:
   - `_get_async_loop`

   Any primitive not in this list is **not** part of the sanctioned API.
   If a new package needs access to state outside the list, its REPORT
   MUST either (a) extend this allowlist in the same diff with
   justification, or (b) add a narrow read-only accessor — never reach
   into a private dict directly.

2. **Forbidden private-state list** (grep-verifiable). New modules MUST
   NOT read or write any of these attributes on `ExecPosFSM`:

   *Bracket / ownership dicts*:
   - `_symbol_brackets`
   - `_bracket_owner_by_symbol`
   - `_open_strategy_by_symbol`
   - `_pending_brackets`
   - `_primary_bracket_identity`

   *Pending-entry / local-guard state*:
   - `_pending_entry_meta`
   - `_pending_entry_data`
   - `_pending_intent_data`
   - `_local_open_guard` (state, not method)

   *Position-policy + policy-close state*:
   - `_position_policy_close_requests`
   - `_policy_close_requests`

   *Manage-flow raw dicts*:
   - `_manage_truth_source` (dict)
   - `_manage_flow_by_symbol`
   - `_close_flow_by_symbol`

   *Fill-ingress internals*:
   - `_fill_coord_state`
   - `_canonical_fill_ingress_wal`
   - `_proven_terminal_cache`

   *Flow factory internals*:
   - `_flows_lock`
   - `_flows_by_symbol`

   *Cooldown / portfolio caches*:
   - `_last_any_position_closed_ts`
   - `_latest_portfolio_state_raw`

   *Exec-error funnel*:
   - `_exec_error_counts`

   This list is authoritative for P1–P6c. A package may add an entry if
   it discovers additional private state; it may NOT remove entries.

3. A documented ADR-style rule (inline in `fsm.py` module docstring + a
   short note under `docs/ai/`): new extracted modules MAY only
   read/mutate ExecPosFSM state through the §1 allowlist. Each package
   MUST convert its own target access to the sanctioned API as part of
   its own diff; existing managers keep their current access until their
   respective package lands.

4. Static guard: a grep check (manual in P0, may be formalized later as
   a pytest or ruff rule). For every file touched by P1–P6c, the REPORT
   must include output of:

   ```text
   # forbidden-access sweep
   rg -n 'self\._fsm\._(symbol_brackets|bracket_owner_by_symbol|open_strategy_by_symbol|pending_brackets|primary_bracket_identity|pending_entry_(meta|data)|pending_intent_data|position_policy_close_requests|policy_close_requests|manage_truth_source|manage_flow_by_symbol|close_flow_by_symbol|fill_coord_state|canonical_fill_ingress_wal|proven_terminal_cache|flows_lock|flows_by_symbol|last_any_position_closed_ts|latest_portfolio_state_raw|exec_error_counts)' apps/reference/domains/execution_position/<new_module>.py
   ```

   The sweep MUST be empty. A non-empty result blocks the package.

5. Line-number independence: sanctioned-API markers and the forbidden
   list are expressed as symbol names only. No step in P0–P6c may
   reference a literal line number as a navigation primitive. Symbol
   names are the only stable anchors.

- Basis: review correction #1. Without this step every new module becomes
  another `Manager(self)` façade, which thins the God object rather than
  breaking its ownership.
- Estimated `fsm.py` line reduction: **~0** (pure annotation +
  documentation), small docstring growth.
- No behavior change. Validation: full test suite clean; no code
  references changed.

### Package 1 — Pending-entry guards (lowest risk, first real extraction)
Move `_evaluate_supersede_reprice_guard`, `_evaluate_advanced_stale_cancel`,
`_resolve_price` into `pending_entry_guards.py`. Keep one-line delegations.
- Basis: F12, pure evaluation, no bus side-effects except observability.
- Prereq: Package 0 landed.
- Estimated reduction: ~200 lines.

### Package 2 — Position-policy mediator
Move R9 + `_create_position_policy_sidecar` into
`position_policy_mediator.py`. Mediator receives `bus`, `hardening_getter`,
`handle` callback, portfolio-state accessors via sanctioned API.
- Basis: review correction #2. Mediator is locally bounded (sidecar →
  suppression matrix → `CMD:CLOSE`) and already conceptually detached via
  the sidecar; extracting it before ownership registry reduces cumulative
  risk.
- Prereq: Package 1 validated.
- Estimated reduction: ~310 lines.

### Package 3 — Bracket ownership registry
Move F10 / R12 into `bracket_ownership.py`. Manager consumes the sanctioned
truth-store API from Package 0 (no direct dict access).
- Prereq: Package 2 validated.
- Estimated reduction: ~300 lines.
- Note: ownership registry is a dependency for Package 5 (bracket health);
  keep its public surface narrow.

### Package 4 — Fill ingress coordinator
Move R7 into `fill_ingress_coordinator.py`. `_on_trade_executed`,
`_on_order_fill`, `handle(TRADE_EXECUTED/ORDER_FILL)` become one-liners.
- Prereq: Package 2 validated (mediator observes fills after the
  incumbent path).
- Estimated reduction: ~280 lines.

### Package 5 — Bracket health loop
Move R13 into `bracket_health.py`. Depends on Package 3 (ownership registry).
- Prereq: Packages 3 & 4 validated.
- Estimated reduction: ~500 lines.

### Package 6 — Startup truth orchestrator (highest risk, MANDATORY split)
Move R10/R11 orchestration into `startup_truth_orchestrator.py`. Must be
done **after** all other packages — stable truth-store primitives required.

**Split into 6a → 6b → 6c is MANDATORY (review correction #3).** Each sub-
package has its own validation gate and REPORT; 6b does not start until
6a is green.

- **6a — Artifact I/O + dark-read + comparison**.
  Move: `_create_restore_artifact_*`, `_create_startup_truth_artifact_writer`,
  `_run_restore_artifact_dark_read_comparison`,
  `_run_restore_artifact_authoritative_read` (read-only parts),
  `_restore_artifact_mode`, `_authoritative_restore_enabled`,
  `_restore_artifact_has_state`, `_persist_restore_artifact_snapshot`,
  `_schedule_restore_artifact_loop`, `_restore_artifact_loop`,
  `_build_execution_restore_artifact_records`,
  `_build_execution_restore_artifact_record`,
  `_resolve_restore_artifact_bracket_snapshot`,
  `_restore_semantics_signature`, `_execution_truth_cache_status`.
  No runtime state mutation — strictly read + emit + persist.
- **6b — Authoritative apply**.
  Move: `_apply_authoritative_restore_record`,
  `_finalize_restore_authoritative_status`,
  `_build_startup_truth_unknown_records`,
  `_append_startup_truth_artifact_record`. These mutate
  `manage_flow.state` / `close_flow.state` / pending brackets; must reuse
  Package 0 truth-store primitives exclusively.
- **6c — Startup reconstruction + guardian reconcile**.
  Move: `_startup_reconstruct_runtime_bracket_truth`,
  `_append_restart_truth_record`, `_startup_order_guardian_reconcile`,
  `_restore_artifact_symbol_candidates`.

- Prereq: Packages 0–5 validated.
- Combined estimated reduction: ~1,300 lines.

**Deferred (not in this plan)**: introducing
`ExecutionPositionTruthStore` as a real class. Do not attempt before all
6 packages land. Package 0 freeze is the dispositive substitute until then.

---

## 15. Validation path per package

Minimum gates per package. Run in order; do not proceed if any gate fails.

1. **Diff review**: net deletion in `fsm.py` ≥ net addition in the new
   module minus imports (confirm additive, not duplicative).
2. **Unit suite**: full `tests/domains/execution_position/` run. No new
   failures vs baseline.
3. **Targeted runtime tests** per package:
   - **P0**: full execution_position suite (baseline regression). Plus
     manual grep confirming no new module reaches into forbidden private
     dicts.
   - **P1**: tests touching supersede / stale-cancel (grep
     `supersede_reprice_guard`, `advanced_stale_cancel`).
   - **P2** (mediator): `test_position_policy_sidecar*close*`,
     `test_position_policy_*suppression*`.
   - **P3** (ownership registry): `test_execpos_*_bracket_ownership*`,
     `test_execpos_bracket_math_owner*`,
     `test_execpos_bracket_owner_recovery*`.
   - **P4**: `test_execpos_canonical_fill_ingress*`,
     `test_execpos_def005_restart_runtime_truth*`,
     `test_terminal_ws_close_truth*`.
   - **P5**: `test_execpos_guardian_child_identity*`,
     `test_execpos_auxiliary_bracket_registration_hardening*`.
   - **P6a**: restore-artifact dark-read / IO tests (grep
     `restore_artifact`, `dark_read`). No state mutation expected.
   - **P6b**: authoritative-apply tests. `test_execpos_def005_restart_runtime_truth_reconstruction`,
     `apply_authoritative_local_close_reset` related tests.
   - **P6c**: `test_bootstrap/test_runtime_analytics_restore`,
     `test_bootstrap/test_startup_hydration_planner`, startup guardian
     reconcile tests.
4. **Log / JSONL parity**: same record-kinds in `logs/trade_lifecycle.jsonl`
   before/after (at least: `execution_bracket_ownership_record`,
   `execution_fill_ingress_record`, `position_policy_sidecar_record`,
   `execution_restart_truth`).
5. **Bus event parity**: pre/post capture of emitted event topics during a
   replay scenario — diff must be empty.
6. **Static**: mypy + ruff on changed files. No new `# type: ignore`.
7. **REPORT** per `docs/ai/AGENT_REPORT_SCHEMA.md` per package, with
   explicit FACTS / INFERENCES / RISKS.

---

## 16. Risks / unproven areas

- **R-A**: Sidecar event order (F14). **Mitigation**: all packages keep
  `bus.listen` in `fsm.py`; new modules are invoked from the re-dispatch
  points.
- **R-B**: Truth dict aliasing. Packages 2, 3, 5 read truth dicts directly
  via back-pointer. **Mitigation**: document every cross-boundary state
  access; audit again before Package 6.
- **R-C**: Startup orchestrator (Package 6) is the largest single extraction
  and mutates flow state during an async context. **Mitigation**: split into
  6a/6b/6c.
- **R-D**: Mixin MRO fragility. **Mitigation**: keep unique names; do not
  collapse mixins until truth-store lands.
- **R-E**: `IntentBoundaryAudit` and `IntentRouter` may double-register
  listeners (U5). Confirm before Package 3.
- **R-F**: `trade_intent_open_intake` / `trade_executed_contracts`
  unreviewed — may contain additional shell logic; re-scan before Package 4.
- **R-G**: Backtest WAL-hydration skip (L492) must be preserved.
- **R-H**: No new module-level singletons that break parallel tests.
- **R-I**: `_async_loop` injection timing — modules must obtain the loop
  via `_get_async_loop()`, never cache.

---

## 17. Final verdict

- **Current shape**: `ExecPosFSM` is a **hidden composition root + runtime
  truth owner + orchestration shell + bus ingress adapter**. Phase 14A/14.2
  shrank the surface but did not change ownership.
- **Domain contract reminder**: `execution_position` remains an
  **execution soldier** — it owns lifecycle truth and accepts intents.
  `decision_making` remains the owner of strategy dispatch and
  `TRADE_INTENT_PROPOSED`. During decomposition no new policy/decision
  logic may be pushed into `execution_position`.
- **Recommendation**: do **not** attempt a broad rewrite. Execute
  Package 0 (truth-boundary freeze) first, then the 6-package sequence
  (P1 → P2 mediator → P3 ownership → P4 fill-ingress → P5 health →
  P6a/b/c). Strictly additive, smallest first, validation gate per package.
- **Deferred**: `ExecutionPositionTruthStore` as a real class — after all
  6 packages. Package 0 freeze is its provisional substitute.
- **Do not extract**: truth-store primitives, flow factory, cooldown gate,
  `OPEN_GUARD_FAIL` builder, dispatch shell (`handle()` /
  `_execute_decision()`), `_apply_authoritative_local_close_reset`, or
  mixins. They are the legitimate residual responsibility of the shell.
- **Pre-flight**: run the full `tests/domains/execution_position/` baseline
  on current `Phenix_v2` head and archive the result as regression
  reference before starting Package 0.

---

## 18. Pre-flight checklist (before Package 0)

- [ ] Archive baseline `tests/domains/execution_position/` run output.
- [ ] Archive baseline `logs/trade_lifecycle.jsonl` record-kind
      fingerprint.
- [ ] Capture baseline line-count + method-count of `fsm.py`.
- [ ] Confirm U1 / U2 / U5 answered or explicitly deferred in REPORT.
- [ ] Confirm mypy + ruff clean on current `fsm.py` head.

## 19. Per-package exit criteria (applies to P0 through P6c)

Each package's REPORT must state, at minimum:

- Diff summary (files, net LOC delta, methods moved).
- Sanctioned-API compliance: list of truth-store primitives read/written
  by the new module; confirmation that no forbidden private-dict access
  was added.
- **No new back-pointer spread** (exit criterion, v1.2): the new module
  must contain zero `self._fsm._<attr>` references outside the P0
  sanctioned allowlist. The forbidden-access sweep from Package 0 §4
  MUST be executed and its empty output pasted into the REPORT. Any
  non-empty hit blocks the package until the access is routed through a
  sanctioned accessor (or the allowlist is extended with justification
  in the same diff).
- Test evidence: pass count delta vs baseline for the targeted suite.
- JSONL record-kind parity evidence.
- Bus event topic parity evidence (for packages touching the bus layer).
- Known risks carried forward into the next package.

---

*End of roadmap v1.2.*
