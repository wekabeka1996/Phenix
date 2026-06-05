# R7V_FEE_AWARE_SHADOW_CRITICAL_JOURNAL_SINK_REPAIR_REPORT

## Executive Summary

Verdict: CONFIG_DRIFT_PATCHED_AND_VALIDATED.

The fee-aware shadow event was already emitted on the bus with the correct EVT-prefixed name and was already registered in the verb registry and schema surface. The sink gap was caused by active SSOT drift: config/aurora/observability.yaml omitted EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE from shadow_journal.critical_events, while apps/reference/telemetry/shadow_journal.py still listed it in DEFAULT_CRITICAL_EVENTS. Because apps/reference/config/system/observability.py requires critical_events from YAML and apps/reference/telemetry/shadow_journal.py resolves runtime admission from the loaded config list, the runtime journal used the YAML allowlist and filtered the event out.

The repair was additive and minimal:

- add EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE to config/aurora/observability.yaml shadow_journal.critical_events
- preserve shadow_only, authority_applied, and no_effect in shadow journal payload_fragment so the sink retains the fee-aware shadow invariants needed for audit-grade validation

No authority, threshold, close-submission, strategy, or execution behavior was changed.

## FACTS

### Exact source of sink gap

- Sidecar emission site publishes EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE through PositionPolicySidecar._publish in apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py.
- _publish writes both to the bus and to trade_lifecycle JSONL when logging is enabled.
- vfoundation/core/fsm_core.py sends every emitted bus event through _shadow_journal.record_bus_emit when a journal is attached.
- apps/reference/telemetry/shadow_journal.py gates capture with exact-string membership via should_capture(event_name).
- apps/reference/config/system/observability.py defines shadow_journal.critical_events as a required YAML-loaded List[str].
- apps/reference/telemetry/shadow_journal.py resolve_shadow_journal_config() passes getattr(shadow_cfg, "critical_events", None) through _read_str_list() into the live journal instance.
- Before the patch, config/aurora/observability.yaml did not include EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE in shadow_journal.critical_events.
- apps/reference/telemetry/shadow_journal.py DEFAULT_CRITICAL_EVENTS did include EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE.
- Therefore the event was bus-published but filtered by the active YAML-derived journal allowlist.

### Files inspected

- config/aurora/observability.yaml
- apps/reference/config/system/observability.py
- apps/reference/telemetry/shadow_journal.py
- apps/reference/dictionaries/verb_registry_v1.yaml
- apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py
- apps/reference/domains/execution_position/schemas/position_policy_sidecar_fee_aware_shadow_arm_state_v1.json
- apps/reference/domains/execution_position/fsm.py
- vfoundation/core/fsm_core.py
- tests/config/test_observability_contracts.py
- tests/telemetry/test_shadow_critical_event_journal.py
- tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py

### Routing topology audit

| Hop | Classification | Evidence |
| --- | --- | --- |
| sidecar emission | reached | position_policy_sidecar.py publishes EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE |
| PositionPolicySidecar._publish -> EventBus | reached | _publish calls self._bus.emit(topic, dict(payload), why=...) |
| PositionPolicySidecar._publish -> trade_lifecycle | reached | _publish also writes trade_lifecycle JSONL directly |
| FSMCore.emit -> shadow_journal.record_bus_emit | reached | fsm_core.py invokes record_bus_emit when _shadow_journal is attached |
| shadow_journal critical-event admission | filtered before patch, reached after patch | should_capture() is exact membership against critical_events |
| shadow_journal sink write | reached | synthetic sink proof wrote JSONL row after allowlist repair |

### Required audit answers

1. Is the event only written to trade_lifecycle and never published on the bus?
   No. The sidecar publishes the EVT-prefixed topic on the bus and writes trade_lifecycle separately.

2. Is it published on the bus but filtered by shadow_journal critical_events?
   Yes. This was the root cause before the patch.

3. Is it present in code DEFAULT_CRITICAL_EVENTS but overridden by YAML?
   Yes.

4. Is observability.yaml missing the event from active SSOT?
   Yes. That omission was patched.

5. Is the event name shape mismatched, with or without EVT prefix?
   No. The emission topic is EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE, the registry is EVT + verb POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE, and strict filter testing confirmed the unprefixed near-miss is rejected.

6. Is the shadow journal disabled, stale, or using a different config source?
   No evidence of that. The journal is enabled in active config and resolves from config.observability.shadow_journal.

7. Is the sink writer failing silently?
   No evidence of that in the repaired path. Synthetic sink proof wrote a representative JSONL row successfully.

### Config / registry consistency

- verb_registry_v1.yaml contains exactly one relevant entry:
  - op: EVT
  - verb: POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE
  - owner: execution_position
  - status: experimental
  - schema: apps/reference/domains/execution_position/schemas/position_policy_sidecar_fee_aware_shadow_arm_state_v1.json
- The schema file exists and remains unchanged.
- apps/reference/config/system/observability.py accepts the event because critical_events is a plain List[str] loaded from YAML.
- Runtime loader does not drop the exact event string; it forwards the configured string list into the journal.
- DEFAULT_CRITICAL_EVENTS contradicted active YAML before the patch; YAML remained authoritative.

### Exact path patched

- config/aurora/observability.yaml
  - added EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE under shadow_journal.critical_events
- apps/reference/telemetry/shadow_journal.py
  - added shadow_only, authority_applied, and no_effect to build_payload_fragment() keep-list so the journal retains the fee-aware shadow invariants required by the sink proof
- tests/config/test_observability_contracts.py
  - added active-config admission assertion
- tests/telemetry/test_shadow_critical_event_journal.py
  - added strict filter test for exact EVT name vs near-miss name
- tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py
  - added synthetic sink-write proof using FSMCore + attach_shadow_journal + active config

### Tests and outputs

Focused validation command:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest \
  tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract \
  tests/telemetry/test_shadow_critical_event_journal.py::test_shadow_journal_strictly_admits_fee_aware_shadow_event_name \
  tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_arm_state_emission_and_schema \
  tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_event_isolation_and_backward_compat \
  tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_event_writes_to_shadow_journal_without_authority_regression -q
```

Focused result:

- 5 passed in 3.93s

Additional exploratory command run:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest \
  tests/config/test_observability_contracts.py \
  tests/telemetry/test_shadow_critical_event_journal.py \
  tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py -q
```

Exploratory result:

- mixed: 20 passed, 4 failed
- the 4 failures were outside this fee-aware sink repair surface and came from existing telemetry test baseline behavior in tests/telemetry/test_shadow_critical_event_journal.py plus the first version of the new sink-write assertion before payload_fragment retention was patched
- no claim is made that the full telemetry file or full suite is green

### Minimal repair decision

Chosen path: Path A — YAML whitelist drift.

Reason:

- the event was already emitted
- the event name already matched registry/schema/runtime topic shape
- the journal path was already attached and operational
- the missing active allowlist entry was sufficient to explain 0 journal copies in R7U

## INFERENCES

- The next runtime should continue to produce trade_lifecycle copies of the fee-aware shadow event.
- The next runtime should now also produce shadow_critical_event_journal_v1.jsonl copies for the fee-aware shadow event, assuming the same event surface is emitted again and the active config file is the one loaded at runtime.
- The journal record now preserves the three critical fee-aware invariants needed for downstream audit checks: shadow_only, authority_applied, and no_effect.
- Because the repair stayed inside SSOT allowlisting and payload-fragment retention, execution authority remains unchanged.

## ASSUMPTIONS

- Synthetic sink proof through FSMCore.emit + attach_shadow_journal exercises the same bus-to-journal admission path used by runtime event emission.

## UNKNOWNS

- Whether the next live runtime window will produce the first real fee-aware journal copy on production-like data.
- Broader denominator bias from missing_unrealized_pnl_usdt remains unresolved and is outside this package.
- Fee-aware economic quality remains unproven.
- Live promotion remains unproven and untouched.

## Minimal Safe Verdict

CONFIG_DRIFT_PATCHED_AND_VALIDATED.

The observed sink gap was rooted in active YAML allowlist drift, not in sidecar authority, strategy behavior, or close execution logic.

## AGENT_REPORT_V1

```text
AGENT_REPORT_V1

task: AURORA_R7V_FEE_AWARE_SHADOW_CRITICAL_JOURNAL_SINK_REPAIR
verdict: CONFIG_DRIFT_PATCHED_AND_VALIDATED
runtime_authority_changed: false
execution_behavior_changed: false
config_policy_changed: true
files_changed:
  - config/aurora/observability.yaml
  - apps/reference/telemetry/shadow_journal.py
  - tests/config/test_observability_contracts.py
  - tests/telemetry/test_shadow_critical_event_journal.py
  - tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py
  - R7V_FEE_AWARE_SHADOW_CRITICAL_JOURNAL_SINK_REPAIR_REPORT.md
root_cause:
  classification: YAML_WHITELIST_DRIFT
  evidence: active observability.yaml omitted EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE while DEFAULT_CRITICAL_EVENTS contained it and runtime journal admission resolved from YAML critical_events
tests:
  - command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_observability_contracts.py::test_current_aurora_config_loads_observability_contract tests/telemetry/test_shadow_critical_event_journal.py::test_shadow_journal_strictly_admits_fee_aware_shadow_event_name tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_arm_state_emission_and_schema tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_event_isolation_and_backward_compat tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py::test_fee_aware_shadow_event_writes_to_shadow_journal_without_authority_regression -q
    result: pass
proven:
  - The fee-aware shadow event is bus-published with the EVT prefix.
  - The event is registered once in verb_registry_v1.yaml with execution_position ownership and an existing schema path.
  - Before the patch, the active YAML allowlist excluded the event and caused shadow_journal filtering.
  - After the patch, active config admission, strict filter behavior, and synthetic sink writing are validated.
  - The repaired sink path preserves shadow_only=true, authority_applied=false, and no_effect=true in the journal payload fragment.
  - Existing fee-aware trade_lifecycle emission still works.
unproven:
  - First live runtime confirmation of a real fee-aware journal copy.
  - Any economic or promotion claim.
next_runtime_expectation:
  - fee-aware shadow events should appear in trade_lifecycle.jsonl
  - fee-aware shadow events should appear in shadow_critical_event_journal_v1.jsonl
next_step:
  - run a short runtime window and verify the first real fee-aware journal copy before deeper economic analysis
```
