# Position Policy Sidecar Phase-2 Action Package (Testnet-Only Implementation, No Launch Authority)

## 1. Executive Verdict

- The narrow Phase-2 action package is implemented on code, schema, registry, telemetry, and test surfaces only.
- The package adds the missing Phase-2 plumbing admitted by the reopened Phase 6 decision:
  - EP-internal request path,
  - explicit policy-source attribution,
  - request-to-outcome linkage,
  - outcome trace through reconcile.
- The action surface remains bounded to the already admitted narrow contract:
  - symbol-scoped,
  - current-net-position only,
  - reduce-only,
  - no partial reduce,
  - no bracket mutation,
  - no exact targeting.
- `shadow` remains the default safe posture because this package made no config changes and did not launch or enable anything.
- Exact files changed for this package:
  - `apps/reference/domains/execution_position/position_policy_sidecar.py`
  - `apps/reference/domains/execution_position/fsm.py`
  - `apps/reference/domains/execution_position/fsm_close.py`
  - `apps/reference/domains/execution_position/close_executor.py`
  - `apps/reference/dictionaries/verb_registry_v1.yaml`
  - `apps/reference/domains/execution_position/domain_dict.json`
  - `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`
  - `apps/reference/domains/execution_position/schemas/position_policy_sidecar_close_request_state_v1.json`
  - `tests/contracts/test_position_policy_sidecar_contracts.py`
  - `tests/domains/execution_position/test_position_policy_sidecar.py`
  - `tests/domains/execution_position/test_execpos_max_hold_close_executes_adapter_v1.py`
- No config files were changed.
- No system run, restart, mode switch, enablement, or pilot launch was performed by the agent.

## 2. Current Non-Action Seam Audit

- Frozen roadmap boundary:
  - `position_policy_sidecar_roadmap_v_1.md` admits Phase 2 only after Phase 6 and keeps early action narrow.
  - The roadmap explicitly calls for:
    - EP-internal request path only,
    - explicit policy source attribution,
    - request-to-outcome linkage.
- Frozen governance decision:
  - `reports/POSITION_POLICY_SIDECAR_PHASE6_REOPENED_ACTION_READINESS_GATE_REVIEW_20260410.md` admitted `OUTCOME_A_PROMOTE_TO_PHASE2`.
  - The same report explicitly held that immediate guarded 24h pilot was `NOT_ADMISSIBLE_NOW` because:
    - no EP-internal request path existed,
    - no request-to-outcome linkage existed,
    - no outcome trace through reconcile existed.
- Pre-package seam:
  - Phase-1 `enable` posture was still non-action-bearing and terminated at `EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED` per the frozen Phase 6 evidence base.
  - `ManageFlowFSM` already owned local lifecycle truth.
  - `CloseFlowFSM` already owned translation from `CMD:CLOSE` to `DEC:CLOSE`.
  - `CloseExecutor` already owned symbol-scoped reduce-only close execution.
  - The missing live seam was the internal handoff from Sidecar recommendation output into that existing EP-owned close chain.
- Placeholder vs live surfaces before this package:
  - Existing live: sidecar recommendation events, close execution contracts, authoritative reconcile event.
  - Missing before package: sidecar-originated internal close command, sidecar-specific request-state event, preserved provenance bundle across close flow, request-to-reconcile linkage.

## 3. FACTS

- `apps/reference/domains/execution_position/position_policy_sidecar.py` now defines:
  - `ACTION_PACKAGE_VERSION = "phase2_action_package_v1"`
  - `CLOSE_REQUEST_EVENT_TYPE = "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"`
  - `CLOSE_REQUEST_COMMAND_TOPIC = "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"`
- `PositionPolicyCloseRequest` is now the canonical additive request object with:
  - `request_id`
  - `trace_id`
  - `source_event_type`
  - `event_type`
  - `requested_action`
  - `requested_qty`
  - `target_mode`
  - `policy_source`
  - `action_package_version`
  - `allowed_action_scope`
  - `reason_codes`
  - `score_snapshot`
  - `position_snapshot`
  - `feature_ref`
  - `regime_ref`
  - `freshness_snapshot`
  - `fill_correlation`
  - `portfolio_correlation`
- In `position_policy_sidecar.py`, `ENABLE` mode now publishes `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` from the recommendation branch instead of stopping at a phase-1 skip event.
- `apps/reference/domains/execution_position/fsm.py` now:
  - listens to `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`,
  - parses and normalizes the request,
  - enforces fail-closed scope checks,
  - emits `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`,
  - stores pending request context for reconcile linkage,
  - translates accepted requests into EP-owned `CMD:CLOSE`.
- `apps/reference/domains/execution_position/fsm_close.py` now preserves `policy_context` from `CMD:CLOSE` into `DEC:CLOSE`.
- `apps/reference/domains/execution_position/close_executor.py` now emits sidecar request-state updates for:
  - `execution_submitted`
  - `execution_noop`
- `apps/reference/domains/execution_position/fsm.py` now emits `reconciled` request-state rows from `_on_execution_close_reconciled`.
- `apps/reference/dictionaries/verb_registry_v1.yaml` now registers:
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
- `apps/reference/domains/execution_position/domain_dict.json` now:
  - self-imports `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`,
  - self-exports `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`,
  - exports `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` to monitoring.
- `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json` now freezes the request payload contract.
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_close_request_state_v1.json` now freezes the request-state linkage contract.
- `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE` is also appended to `trade_lifecycle.jsonl` with `record_kind = position_policy_sidecar`.
- Tests executed after implementation:
  - `python -m pytest tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_execpos_max_hold_close_executes_adapter_v1.py -q`
    - result: `23 passed`
  - `python -m pytest tests/contracts/test_position_policy_sidecar_contracts.py tests/bootstrap/test_schema_registry_activation.py tests/telemetry/test_trade_lifecycle_sidecar_records.py tests/contracts/test_contract_registry_audit.py tests/domains/execution_position/test_close_flow_cmd_close_always_emits_dec_close.py -q`
    - result: `45 passed`

## 4. INFERENCES

- The missing Phase-2 plumbing identified by the reopened Phase 6 review is now present in code.
- Sidecar still does not own lifecycle truth or close execution. It only emits an attributable internal request that EP validates and routes.
- The package is action-capable at the internal contract level, but it is not operationally active because runtime posture was not changed.
- The request-to-outcome trace is now strong enough for a later guarded testnet pilot review because the same request can be followed through request, suppress, close-command emission, execution submission or noop, and reconcile.

## 5. ASSUMPTIONS

- The operator will keep `shadow` as the default posture until a separate human-controlled runtime decision is made.
- No operator-facing config documentation update was required because the config surface and allowed action flags did not change.
- Existing monitoring and artifact consumers can accept the new additive request/state events through the registered schemas.

## 6. UNKNOWNS

- No live testnet pilot evidence exists yet for the new request path because the agent did not run the system.
- Real-world frequency of `execution_noop`, reconcile latency, and incumbent collision patterns under live action requests remains unobserved.
- This package does not prove business quality of future action decisions by itself; it only implements the admitted bounded internal path.

## 7. New Phase-2 Contract Surface

- New command surface:
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - schema: `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`
  - owner: `execution_position`
- Required request payload fields:
  - `ts_ms`
  - `request_id`
  - `trace_id`
  - `symbol`
  - `sidecar_version`
  - `mode`
  - `evaluation_mode`
  - `event_type = POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`
  - `source_event_type = POSITION_POLICY_SIDECAR_RECOMMENDED`
  - `requested_action = SOFT_CLOSE`
  - `requested_qty`
  - `target_mode = symbol_current_net_only`
  - `policy_source = position_policy_sidecar`
  - `action_package_version`
  - `allowed_action_scope`
  - `reason_codes`
  - `score_snapshot`
  - `position_snapshot`
  - `feature_ref`
  - `regime_ref`
  - `freshness_snapshot`
  - `fill_correlation`
  - `portfolio_correlation`
- New request-state surface:
  - `EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`
  - schema: `apps/reference/domains/execution_position/schemas/position_policy_sidecar_close_request_state_v1.json`
  - states:
    - `suppressed`
    - `close_command_emitted`
    - `execution_submitted`
    - `execution_noop`
    - `reconciled`
- Required request-state linkage fields:
  - `request_id`
  - `trace_id`
  - `policy_source`
  - `policy_context`
  - `why`
- Additive forensic fields:
  - `suppression_reason`
  - `incumbent_owner`
  - `close_cmd_rid`
  - `execution_client_order_id`
  - `execution_close_side`
  - `execution_close_qty`
  - `execution_result`
  - `execution_shadow_mode`
  - `adapter_present`
  - `partial_close`
  - `portfolio_state`
  - `portfolio_position_signature`
  - `business_close_reconciled`
  - `reconcile_source`
  - `reconcile_rid`
  - `reconcile_why`
- Fail-closed admission rules enforced at request intake in `fsm.py`:
  - invalid policy source suppresses,
  - unsupported requested action suppresses,
  - non-`symbol_current_net_only` target suppresses,
  - non-null/non-zero `requested_qty` suppresses,
  - disabled allowed scope suppresses,
  - missing manage flow suppresses,
  - inactive lifecycle suppresses,
  - local close already in progress suppresses,
  - unknown or flat live net position suppresses,
  - unknown position signature suppresses,
  - execution truth hardening can suppress with `close_guard:*`.

## 8. Request Path Implementation Summary

- Path implemented:
  - `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`
  - `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `ExecPosFSM._on_position_policy_close_request`
  - `CMD:CLOSE`
  - `CloseFlowFSM.handle`
  - `DEC:CLOSE`
  - `CloseExecutor`
- `position_policy_sidecar.py` now builds `PositionPolicyCloseRequest` directly from the emitted recommendation context.
- `fsm.py` is the sole intake owner for the new request path.
- Accepted requests are translated into `CMD:CLOSE` with:
  - `trigger = CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
  - `trace = request.trace_id`
  - `idempotent_key = request.request_id`
  - `close_guard_prevalidated = True`
  - `policy_context = {...}`
- `close_guard_prevalidated = True` prevents a second hardening pass from re-suppressing a request already validated by the request intake seam.
- `fsm_close.py` still owns emission of `DEC:CLOSE`; the sidecar does not emit `DEC:CLOSE` directly.
- `close_executor.py` still owns adapter execution via `place_market_reduce_only`; the sidecar does not call the adapter directly.

## 9. Policy Source Attribution Summary

- Every accepted sidecar request now carries explicit provenance:
  - `policy_source = position_policy_sidecar`
  - `source_event_type = POSITION_POLICY_SIDECAR_RECOMMENDED`
  - `request_event_type = POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`
  - `source_trace_id`
  - `request_id`
  - `action_package_version = phase2_action_package_v1`
  - full `reason_codes`
  - full `score_snapshot`
  - full `position_snapshot`
  - full `feature_ref`
  - full `regime_ref`
  - full `freshness_snapshot`
  - full `fill_correlation`
  - full `portfolio_correlation`
- Attribution is preserved across the whole EP-owned path through `policy_context`.
- Suppression and execution state events both retain that same attribution bundle.

## 10. Request-to-Outcome Linkage Summary

- Reconstructable chain now exists by `request_id` plus `trace_id`:
  - recommendation emits `trace_id`
  - internal close request emits `request_id` and repeats `trace_id`
  - `close_command_emitted` records the accepted bridge into EP close handling
  - `execution_submitted` or `execution_noop` records execution outcome
  - `reconciled` records authoritative post-close reconcile outcome
- `test_execpos_position_policy_close_request_state_links_request_to_reconcile` proves:
  - request and close-command emission share the same `request_id`
  - reconcile emits a final linkage row with the same `request_id`
  - reconcile fields include `business_close_reconciled` and `reconcile_source`
- `test_execpos_sidecar_close_emits_execution_submitted_state` proves:
  - execution state captures `execution_close_side`
  - execution state captures `execution_close_qty`
  - execution state captures `execution_client_order_id`

## 11. Reconcile Outcome Trace Summary

- `fsm.py::_on_execution_close_reconciled` now checks for pending sidecar request context by symbol.
- When reconcile arrives for a pending sidecar request, EP emits:
  - `request_state = reconciled`
  - `business_close_reconciled`
  - `reconcile_source`
  - `reconcile_rid`
  - `reconcile_why`
- `close_executor.py` emits:
  - `execution_noop` when no live net position exists at execution time
  - `execution_submitted` when `place_market_reduce_only` is actually submitted
- `_emit_position_policy_close_request_state` writes the same request-state payload to:
  - the internal bus
  - `trade_lifecycle.jsonl`
- This makes request, suppress, execution, and reconcile visible on the authoritative forensic surface instead of leaving the chain split across ad hoc logs.

## 12. Tests Added / Updated

- Added or updated direct package-proof tests:
  - `test_position_policy_sidecar_recommends_and_emits_bounded_close_request_in_enable_mode`
  - `test_position_policy_sidecar_shadow_mode_does_not_emit_close_request`
  - `test_execpos_position_policy_close_request_state_links_request_to_reconcile`
  - `test_execpos_position_policy_close_request_suppresses_when_manage_flow_closing`
  - `test_execpos_position_policy_close_request_forbidden_capabilities_fail_closed`
  - `test_execpos_position_policy_close_request_rejects_bracket_mutation_scope`
  - `test_execpos_sidecar_close_emits_execution_submitted_state`
  - `test_position_policy_sidecar_verbs_are_registered_with_schema_paths`
  - `test_execution_position_domain_dict_exports_sidecar_events_and_self_imports`
- What those tests prove:
  - `shadow` mode still does not emit real close requests.
  - `enable` mode emits only the bounded internal request path.
  - request provenance is explicit and carries the expected narrow scope.
  - accepted requests still traverse `CloseFlowFSM`.
  - reconcile emits a request-linked forensic state.
  - forbidden `partial_reduce`, `bracket_mutation`, and `exact_targeting` capabilities fail closed.
  - incumbent ambiguity via `manage_flow_close_in_progress` suppresses rather than acts.
  - schema registry and domain dictionary know about the new command/event surfaces.
- Compatibility checks also passed:
  - schema activation,
  - sidecar trade-lifecycle telemetry,
  - contract registry audit,
  - `CloseFlowFSM` `CMD:CLOSE -> DEC:CLOSE` behavior.

## 13. SSOT / Registry / Schema Updates

- Added schema:
  - `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`
- Added schema:
  - `apps/reference/domains/execution_position/schemas/position_policy_sidecar_close_request_state_v1.json`
- Updated registry:
  - `apps/reference/dictionaries/verb_registry_v1.yaml`
- Updated domain routing dictionary:
  - `apps/reference/domains/execution_position/domain_dict.json`
- Updated package contract tests:
  - `tests/contracts/test_position_policy_sidecar_contracts.py`
- No config schema or typed config model update was required because:
  - `mode` remained `disable | shadow | enable`
  - `allowed_actions.soft_close_symbol_current_net_only` remained the admitted narrow scope flag
  - `partial_reduce`, `bracket_mutation`, and `exact_targeting` remained `false`

## 14. Residual Risks

- This package does not widen execution truth. Close execution remains symbol-scoped current-net reduce-only, not lifecycle-targeted.
- `CloseExecutor` still supports broader close mechanics for other callers, so the sidecar path must continue relying on its own fail-closed intake checks to prevent partial or exact-targeted behavior.
- No live pilot evidence exists yet for:
  - real request frequency,
  - real reconcile latency,
  - real incumbent collision behavior,
  - real operator ergonomics for the new linkage events.
- `EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED` remains registered for backward compatibility and prior forensic slices, but the Phase-2 enable path no longer depends on it.

## 15. Explicit Non-Launch Handoff

- The Phase-2 action package is implemented.
- The package is not launched.
- The package is not enabled by the agent.
- The agent did not start or restart the system.
- The agent did not switch runtime mode.
- The agent did not run a guarded 24h testnet pilot.
- Runtime start, mode selection, enablement, and any pilot remain operator-only actions.

## 16. Next Exact Step

- Perform the separate operator-controlled review of this package and, only outside this task, decide whether to run the guarded 24h testnet pilot on the new bounded request path.
