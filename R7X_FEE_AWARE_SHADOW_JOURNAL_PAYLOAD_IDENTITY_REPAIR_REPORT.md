# R7X_FEE_AWARE_SHADOW_JOURNAL_PAYLOAD_IDENTITY_REPAIR_REPORT

## Executive Summary

Verdict: PAYLOAD_IDENTITY_PATCHED_AND_VALIDATED.

R7W correctly localized the remaining defect to shadow journal payload_fragment thinning, not to sink admission, authority, or sidecar behavior. This package adds the smallest event-specific retention branch for EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE so the critical journal now preserves compact candidate-level identity without dumping full nested snapshots. Authority, thresholds, close behavior, strategy behavior, and config policy remain unchanged.

## FACTS

### Payload source audit

Representative upstream emission comes from apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py, where the fee-aware shadow event is published with:

- top-level transitions
- top-level symbol, ts_ms, shadow_only, authority_applied, no_effect
- nested candidate_state carrying fee_multiple, estimated_fee_usd, fee_source, required_edge_usd, is_armed, would_trigger, null_reasons, and optional_pct_floor.candidate_pct when present
- no top-level rid
- no top-level lifecycle_id

Field classification:

| Field | Classification | Evidence |
| --- | --- | --- |
| transitions | UPSTREAM_PRESENT_JOURNAL_STRIPPED | emitted top-level in sidecar shadow_payload; absent from pre-R7X payload_fragment |
| candidate_identity | PRESENT_UNDER_DIFFERENT_NAME | no candidate_key upstream; equivalent identity exists as candidate_state.fee_multiple plus candidate_state.optional_pct_floor.candidate_pct when present |
| fee_source | UPSTREAM_PRESENT_JOURNAL_STRIPPED | emitted in candidate_state.fee_source |
| null_reasons | UPSTREAM_PRESENT_JOURNAL_STRIPPED | emitted in candidate_state.null_reasons |
| rid | UPSTREAM_ABSENT | not populated in emitted fee-aware shadow payload for representative upstream event |
| lifecycle_id | UPSTREAM_ABSENT | not populated in emitted fee-aware shadow payload for representative upstream event |

Additional source-audit facts:

- required_edge_usd is upstream-present inside candidate_state and was previously stripped.
- estimated_fee_usd is upstream-present inside candidate_state and was previously stripped.
- is_armed and would_trigger are upstream-present inside candidate_state and were previously stripped.
- realized_lifecycle_fee as an exact field name is UPSTREAM_ABSENT for this event surface; the upstream payload carries fee_source="realized_lifecycle_fee" plus estimated_fee_usd, not a separate realized_lifecycle_fee field.

### Minimal audit fragment design

The patch keeps the generic shadow journal behavior unchanged for unrelated events and adds one event-specific compact retention branch for EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE.

Retained fields for this event when present upstream:

- symbol
- ts_ms
- shadow_only
- authority_applied
- no_effect
- transitions
- candidate_key if present
- fee_multiple
- optional_pct_candidate when present upstream through candidate_state.optional_pct_floor.candidate_pct
- candidate_identity as a compact equivalent identifier
- fee_source
- null_reasons
- estimated_fee_usd
- realized_lifecycle_fee if ever present upstream
- required_edge_usd
- cost_floor_usd if ever present upstream
- is_armed
- would_trigger
- rid if present upstream
- lifecycle_id if present upstream

Explicitly not retained for this event:

- full candidate_state
- full position_snapshot
- full peak_giveback_snapshot
- trace_id
- reason_codes
- unrelated nested snapshot surfaces

### Exact payload_fragment before / after

Representative pre-R7X payload_fragment on the same deterministic representative fee-aware payload:

```json
{
  "symbol": "ETHUSDT",
  "ts_ms": 1775400000000,
  "shadow_only": true,
  "authority_applied": false,
  "no_effect": true
}
```

Representative post-R7X payload_fragment on the same deterministic representative fee-aware payload:

```json
{
  "symbol": "ETHUSDT",
  "ts_ms": 1775400000000,
  "shadow_only": true,
  "authority_applied": false,
  "no_effect": true,
  "transitions": [
    "ARMED"
  ],
  "fee_multiple": 1.5,
  "optional_pct_candidate": 0.02,
  "candidate_identity": {
    "fee_multiple": 1.5,
    "optional_pct_candidate": 0.02
  },
  "fee_source": "realized_lifecycle_fee",
  "estimated_fee_usd": 0.75,
  "required_edge_usd": 1.125,
  "is_armed": true,
  "would_trigger": false,
  "null_reasons": {}
}
```

### Exact files changed

- apps/reference/telemetry/shadow_journal.py
- tests/telemetry/test_shadow_critical_event_journal.py
- tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py
- R7X_FEE_AWARE_SHADOW_JOURNAL_PAYLOAD_IDENTITY_REPAIR_REPORT.md

### Focused tests and outputs

Focused broad telemetry attempt:

```text
.\.venv\Scripts\python.exe -m pytest tests/telemetry/test_shadow_critical_event_journal.py -k "fee_aware or critical" tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract -q
```

Result:

- mixed / not used as acceptance gate
- 3 failures were in pre-existing unrelated telemetry baseline paths:
  - test_shadow_journal_typed_default_matches_runtime_default_allowlist
  - test_close_flow_transition_captures_before_after_state
  - test_execpos_hydrate_writes_restore_record
- the fee-aware shadow payload slice itself was not the failure source

Acceptance command:

```text
.\.venv\Scripts\python.exe -m pytest tests/telemetry/test_shadow_critical_event_journal.py::test_shadow_journal_strictly_admits_fee_aware_shadow_event_name tests/telemetry/test_shadow_critical_event_journal.py::test_build_payload_fragment_retains_compact_fee_aware_identity_without_snapshot_bloat tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract -q
```

Acceptance result:

- 6 passed in 2.75s

### Synthetic sink proof

Synthetic sink proof used the same admission and writer path as runtime:

- attach_shadow_journal(bus, config)
- emit representative fee-aware shadow event through PositionPolicySidecar onto FSM bus
- parse written temp journal row

Proven from the written row:

- payload_fragment contains symbol
- payload_fragment contains ts_ms
- payload_fragment contains transitions
- payload_fragment contains compact candidate_identity
- payload_fragment contains fee_source
- payload_fragment contains estimated_fee_usd
- payload_fragment contains required_edge_usd
- payload_fragment contains is_armed
- payload_fragment contains would_trigger
- payload_fragment contains null_reasons
- payload_fragment preserves shadow_only=true
- payload_fragment preserves authority_applied=false
- payload_fragment preserves no_effect=true
- payload_fragment does not contain candidate_state
- payload_fragment does not contain position_snapshot
- no close command path was emitted

## INFERENCES

- The next runtime fee-aware shadow journal rows should support candidate-level joins using symbol + ts_ms + transitions + compact candidate identity instead of only symbol + ts_ms.
- The remaining R7W defect is resolved at the journal payload layer for upstream-present compact identity fields.
- Because rid and lifecycle_id are upstream-absent for the representative fee-aware event surface, their absence is not evidence of post-R7X stripping.

## ASSUMPTIONS

- The representative fee-aware payload shape exercised by the focused sidecar observability tests matches the runtime event shape used by the real sink path for this EVT.

## UNKNOWNS

- First real post-R7X runtime confirmation that live journal rows now preserve the compact identity fields added here.
- Economic quality.
- Live-readiness.

## Minimal Safe Verdict

PAYLOAD_IDENTITY_PATCHED_AND_VALIDATED.

The defect was a journal payload filtering problem. The patch is additive, event-specific, and validated with focused tests plus a synthetic sink proof through the real journal admission/writer path. No execution authority or sidecar behavior changed.

## AGENT_REPORT_V1

```text
AGENT_REPORT_V1

task: AURORA_R7X_FEE_AWARE_SHADOW_JOURNAL_PAYLOAD_IDENTITY_REPAIR
verdict: PAYLOAD_IDENTITY_PATCHED_AND_VALIDATED
runtime_authority_changed: false
execution_behavior_changed: false
config_policy_changed: false
files_changed:
  - apps/reference/telemetry/shadow_journal.py
  - tests/telemetry/test_shadow_critical_event_journal.py
  - tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py
  - R7X_FEE_AWARE_SHADOW_JOURNAL_PAYLOAD_IDENTITY_REPAIR_REPORT.md
field_classification:
  transitions: UPSTREAM_PRESENT_JOURNAL_STRIPPED
  candidate_identity: PRESENT_UNDER_DIFFERENT_NAME
  fee_source: UPSTREAM_PRESENT_JOURNAL_STRIPPED
  null_reasons: UPSTREAM_PRESENT_JOURNAL_STRIPPED
  rid: UPSTREAM_ABSENT
  lifecycle_id: UPSTREAM_ABSENT
tests:
  - command: .\.venv\Scripts\python.exe -m pytest tests/telemetry/test_shadow_critical_event_journal.py -k "fee_aware or critical" tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract -q
    result: fail_unrelated_baseline
  - command: .\.venv\Scripts\python.exe -m pytest tests/telemetry/test_shadow_critical_event_journal.py::test_shadow_journal_strictly_admits_fee_aware_shadow_event_name tests/telemetry/test_shadow_critical_event_journal.py::test_build_payload_fragment_retains_compact_fee_aware_identity_without_snapshot_bloat tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract -q
    result: pass
synthetic_sink_proof:
  written: true
  payload_identity_ok: true
  safety_flags_preserved: true
  snapshot_bloat_detected: false
proven:
  - Upstream fee-aware payload already carried transitions and compact candidate economics inside candidate_state.
  - The journal was stripping those upstream-present fields before R7X.
  - Post-R7X journal payload_fragment preserves compact fee-aware identity without retaining full snapshots.
  - Focused fee-aware tests and synthetic sink proof passed with no authority regression.
unproven:
  - First real runtime post-R7X confirmation.
  - Any economic or live-readiness claim.
next_runtime_expectation:
  - next fee-aware shadow journal rows should preserve compact candidate identity fields
next_step:
  - run a short post-R7X runtime confirmation to prove real journal payload identity
```
