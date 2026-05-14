# AGENT_REPORT_V1

## Executive Summary
The remaining R4 PPS BTC close residual localized to PositionPolicyMediator lifecycle recovery: when explicit policy_context.lifecycle_id was absent, the mediator ignored canonical fill_correlation.rid even though it already carried the correct aurora lifecycle surface, allowing the close path to collapse to the PPS request id and miss the FINAL lifecycle_stats row.

## Proven Facts
- The failing live BTC PPS request [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L152160) emitted close_command_emitted with policy_context.lifecycle_id = null while fill_correlation.rid already equaled aurora_BTCUSDT_1778613004676.
- The same failing request [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L152166) and [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L152177) kept policy_context.lifecycle_id = null through execution_submitted and reconciled.
- Earlier OrderIndex entry reservation and upsert rows for the failing aurora lifecycle already recorded rid_ref.idempotent_key = aurora_BTCUSDT_1778613004676 in [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L45420) and [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L45430).
- The failing close still traversed the normal close bridge path in [logs/domain_execution_position.log.2](logs/domain_execution_position.log.2#L8136), so the bridge was active rather than skipped.
- The failing request then produced ORDER_FILLED and POSITION_CLOSED rows keyed to the PPS request id instead of the aurora lifecycle in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L563) and [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L564).
- No FINAL lifecycle_stats row exists for the failing aurora lifecycle candidate; the prior runtime validation already established that absence in [R4_RESIDUAL_PPS_POST_PATCH_RUNTIME_VALIDATION_REPORT.md](R4_RESIDUAL_PPS_POST_PATCH_RUNTIME_VALIDATION_REPORT.md).
- The passing BTC PPS request [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L181879) emitted close_command_emitted with policy_context.lifecycle_id = aurora_BTCUSDT_1778662804871 and the same value in fill_correlation.rid.
- The same passing request preserved that lifecycle through execution_submitted and reconciled in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L181888) and [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L181899).
- Earlier OrderIndex entry reservation and upsert rows for the passing aurora lifecycle likewise recorded rid_ref.idempotent_key = aurora_BTCUSDT_1778662804871 in [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L59215) and [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L59228).
- The passing request also traversed the same close bridge path in [logs/domain_execution_position.log.1](logs/domain_execution_position.log.1#L1645), showing bridge behavior is common to both cases.
- The passing request produced ORDER_FILLED and POSITION_CLOSED rows keyed to the aurora lifecycle in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L651) and [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L652), followed by a FINAL lifecycle_stats row in [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L20386).
- Both failing and passing requests encountered the same stale_local_lifecycle_conflict execution guard in [logs/domain_execution_position.log.2](logs/domain_execution_position.log.2#L8164) and [logs/domain_execution_position.log.1](logs/domain_execution_position.log.1#L1677), so that guard is not the differentiating event.
- In the failing class, the closest earlier canonical identity still existed inside PPS fill_correlation.rid at close request time, which is visible in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L152160).
- The production patch in [apps/reference/domains/execution_position/sidecar/position_policy_mediator.py](apps/reference/domains/execution_position/sidecar/position_policy_mediator.py) now resolves close lifecycle identity in this order: explicit lifecycle_id, canonical fill_correlation.rid, cached lifecycle, then OrderIndex recovery, and emits identity_recovery_failed observability when no canonical candidate exists.
- A seam-revealing regression test now proves the missing branch in [tests/domains/execution_position/test_close_producer_bridge_package6.py](tests/domains/execution_position/test_close_producer_bridge_package6.py), and targeted validation passed after the patch.

### Failing vs Passing Runtime Chain

| Stage | Failing BTC request | Passing BTC request | Evidence-backed reading |
| --- | --- | --- | --- |
| close_command_emitted | policy_context.lifecycle_id = null; fill_correlation.rid = aurora_BTCUSDT_1778613004676 | policy_context.lifecycle_id = aurora_BTCUSDT_1778662804871; fill_correlation.rid matches | First divergence appears here, before downstream execution logic. |
| execution_submitted | lifecycle_id still null | lifecycle_id still aurora_BTCUSDT_1778662804871 | Divergence persists unchanged through mediator follow-up state. |
| CLOSE bridge | Both requests pass CMD:CLOSE -> DEC:CLOSE successfully | Both requests pass CMD:CLOSE -> DEC:CLOSE successfully | The bridge is not the overwrite seam. |
| EXECUTION_GUARD_BLOCKED | stale_local_lifecycle_conflict | stale_local_lifecycle_conflict | Common event, not causal for the residual split. |
| ORDER_FILLED | lifecycle_id becomes ppsreq:pps:BTCUSDT:1778622610290:109168 | lifecycle_id is aurora_BTCUSDT_1778662804871 | Downstream resolution follows the lifecycle identity seeded upstream. |
| POSITION_CLOSED | lifecycle_id remains PPS request id | lifecycle_id remains aurora lifecycle | Terminal close truth stays split on the same identity seam. |
| lifecycle_stats terminal row | FINAL row absent for failing aurora candidate | FINAL row present for aurora_BTCUSDT_1778662804871 | Missing canonical lifecycle propagation explains the missing final ledger closure. |

## Inferred Findings
- The first meaningful divergence is not in close bridge execution, trade fill ingress, or stale guard behavior; it is the absence of canonical lifecycle_id at PPS close_command_emitted even though canonical fill_correlation.rid is already present.
- The primary root seam is accurately classified as close_command_builder_ignores_fill_correlation_rid.
- Cache and OrderIndex fallback paths are insufficient as the primary recovery mechanism for this residual class because the failing close already had an immediately available canonical aurora surface in fill_correlation.rid, while any later cache or OrderIndex-based recovery depends on state that may already be missing or unreachable at close time.
- Adding fail-closed observability on unresolved identity recovery is operationally justified because the prior behavior allowed lifecycle degradation to stay silent until downstream ledger absence became visible.

## Contradictions / Evidence Gaps
- Fresh live runtime evidence after the patch does not exist in this session. The live logs cited here are pre-patch evidence used to localize the seam, not proof of post-patch production behavior.
- The inspected runtime evidence proves that fill_correlation.rid carried the needed aurora identity at close time, but it does not prove that every historical PPS residual shares this exact mechanism.
- This report does not prove whether the failing close could still have reached a live OrderIndex entry ref at the exact close moment; it only proves that the needed canonical aurora identity was still directly available in fill_correlation.rid and was ignored there.

## Root Cause Candidates
- Confirmed: PositionPolicyMediator lifecycle recovery skipped canonical fill_correlation.rid when explicit lifecycle_id was absent, allowing PPS request id propagation downstream.
- Rejected: close_producer_bridge overwrote or dropped lifecycle_id. Both failing and passing requests used the same bridge path and only diverged earlier.
- Rejected: stale_local_lifecycle_conflict caused the missing FINAL row by itself. The same guard exists in the passing chain.
- Contributing factor: cached lifecycle and OrderIndex recovery are weaker late-stage recovery surfaces for older PPS closes than the already-serialized canonical fill_correlation.rid.

## Operational Risk
- Runtime
- Observability Gap

## Files / Areas Touched
- [apps/reference/domains/execution_position/sidecar/position_policy_mediator.py](apps/reference/domains/execution_position/sidecar/position_policy_mediator.py)
- [tests/domains/execution_position/test_close_producer_bridge_package6.py](tests/domains/execution_position/test_close_producer_bridge_package6.py)
- Read-only forensic evidence from [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl), [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl), [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl), [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl), [logs/domain_execution_position.log.1](logs/domain_execution_position.log.1), and [logs/domain_execution_position.log.2](logs/domain_execution_position.log.2)

## Validation Performed
- Focused seam test: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_close_producer_bridge_package6.py -k recovers_canonical_fill_rid_without_order_index_entry
- Focused mediator slice: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_close_producer_bridge_package6.py
- Focused lifecycle stats slice: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py
- Focused bracket and stale-guard non-regression: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_brackets_pending_silent_drop_fix.py tests/domains/execution_position/test_entry_fill_preserves_primary_bracket_identity.py
- Static sanity check: no IDE-reported errors in [apps/reference/domains/execution_position/sidecar/position_policy_mediator.py](apps/reference/domains/execution_position/sidecar/position_policy_mediator.py) and [tests/domains/execution_position/test_close_producer_bridge_package6.py](tests/domains/execution_position/test_close_producer_bridge_package6.py)

## Residual Risk
- If a PPS close arrives with neither explicit lifecycle_id nor canonical aurora fill_correlation.rid, downstream canonical closure can still remain incomplete; the new behavior makes that state observable rather than silent.
- The patch preserves existing close flow instead of hard-blocking unresolved requests, so runtime correctness still depends on operators noticing identity_recovery_failed telemetry if the canonical candidate is truly absent.
- Post-patch live runtime proof for this exact BTC residual class remains pending until a new capture produces a matching PPS close chain.

## What Remains Unproven
- A fresh live PPS close showing the patched mediator populating policy_context.lifecycle_id directly from fill_correlation.rid.
- Whether any other residual lifecycle-loss class exists downstream after this seam is repaired.
- Whether operator alerting already consumes the new identity_recovery_failed request_state with sufficient urgency.

## Minimal Safe Verdict
- The narrow production patch is justified and well-bounded: it repairs the earliest proven divergence by promoting canonical fill_correlation.rid into mediator close lifecycle recovery, adds explicit observability when no canonical candidate exists, and passes focused regression coverage. The change should be treated as locally validated but not yet runtime-proven until a new live PPS close capture confirms canonical aurora lifecycle propagation and FINAL lifecycle_stats closure.
