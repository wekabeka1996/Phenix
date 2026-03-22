# REPORT — CONTROLLED_RESTART_RUNTIME_PROOF_FOR_TERMINAL_NON_FILL_ORDER_EVENTS

## 1. Objective
Validate the accepted contract-hardening package for `EVT:ORDER_REJECTED` and the terminal non-fill subset of `EVT:ORDER_STATE_CHANGED` on a fresh controlled run. The runtime-proof goal was to confirm or falsify canonical payload fields, normalization visibility, lineage quality, and masking risk at `FSMCore.emit()`.

## 2. Scope actually executed
Executed:
- read-only baseline capture after fresh restart
- fresh-log / WAL / shadow-journal inspection in the post-restart window
- active-path reconfirmation for scoped producers/consumers
- masking-risk assessment for the `FSMCore.emit()` compatibility seam
- lineage-quality assessment from fresh runtime evidence

Intentionally not executed:
- no code changes
- no replay / restore redesign
- no warm-state expansion
- no broad event redesign
- no FSM migration / cutover work

## 3. Pre-run expectation matrix
Expected from the accepted package, based on code and registry:

| Surface | Expected source(s) | Expected canonical fields |
| --- | --- | --- |
| `EVT:ORDER_REJECTED` | WS reject path, `open_executor`, `fsm` adapter-error reject path | `identity_quality`, `canonical_identity_key`, `terminal_non_fill=true`, `terminal_state_kind=REJECTED`, `reject_reason_normalized`, `compatibility_aliases_retained` |
| terminal non-fill `EVT:ORDER_STATE_CHANGED` | WS terminal non-fill status path, watchdog cancel/expired path | `identity_quality`, `canonical_identity_key`, `terminal_non_fill=true`, `terminal_state_kind`, `compatibility_aliases_retained` |
| shadow observability | `shadow_journal.py` capture path | payload fragment should expose canonical terminal-order fields when scoped events occur |
| compatibility seam | `FSMCore.emit()` | normalization should be explicit and schema-backed, not silent event loss |

Code evidence for expectations:
- [terminal_order_contracts.py](/abs/path-not-used)

Concrete refs:
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L144)
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L156)
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L166)
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L211)
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L221)
- [terminal_order_contracts.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/terminal_order_contracts.py#L229)
- [fsm_core.py](c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#L85)
- [order_rejected_v1.json](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/schemas/order_rejected_v1.json#L7)
- [order_state_changed_v1.json](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/schemas/order_state_changed_v1.json#L7)
- [verb_registry_v1.yaml](c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml#L306)
- [verb_registry_v1.yaml](c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml#L312)

## 4. Controlled restart plan
Controlled restart was user-performed. Validation used the fresh runtime window created by new process starts around `2026-03-21 21:30:47` to `21:31:04`.

Plan executed:
1. Confirm new live process start times and fresh log truncation.
2. Use `aurora_core.log`, `domain_execution_position.log`, `shadow_critical_event_journal_v1.jsonl`, and `ops/wal/2026-03-21.jsonl` as primary evidence.
3. Treat the validation window as the fresh data written after the restart-created files.
4. Search for scoped verbs and canonical fields:
   - `ORDER_REJECTED`
   - `ORDER_STATE_CHANGED`
   - `terminal_state_kind`
   - `reject_reason_normalized`
   - `canonical_identity_key`
   - `compatibility_aliases_retained`
5. Reconstruct only actual captured scoped events; if absent, classify as `did not occur in observed window`, not as proof of correctness.

Sufficient evidence threshold:
- at least one fresh scoped runtime instance with traceable source -> seam -> observability chain

Insufficient evidence threshold:
- zero fresh scoped instances across logs, WAL, and shadow journal

## 5. Fresh runtime evidence
Fresh runtime window facts:
- new Python processes started around `21:30:47` and `21:31:04`
- `logs/order_log_v1.jsonl` was absent in the fresh run window
- `logs/shadow_critical_event_journal_v1.jsonl` was recreated and contains `120` records
- `ops/wal/2026-03-21.jsonl` contains `82` fresh records

Post-warmup follow-up facts:
- by `21:45:01` and later, the runtime was no longer only in startup noise
- `DecisionMaking` produced live signal traffic after warmup
- `logs/order_log_v1.jsonl` now exists and contains `4` `ORDER_REJECTED` rows, all from `DecisionMaking`, not from the scoped execution-side seam
- even after post-warmup activity, `shadow_critical_event_journal_v1.jsonl` and `ops/wal/2026-03-21.jsonl` still contain zero scoped `EVT:ORDER_REJECTED` / `EVT:ORDER_STATE_CHANGED`

Fresh evidence captured:
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log)
  - warm-state reset marker: line `39`
  - active consumer registration:
    - line `158` `MD_AMR_REGISTERED ... EVT:ORDER_REJECTED ... EVT:ORDER_STATE_CHANGED`
    - line `163` `MR_REGISTER ... EVT:ORDER_STATE_CHANGED`
  - repeated shadow tap delivery failures from line `3202` onward to `tcp://127.0.0.1:7101`
- [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log)
  - repeated bracket-health recovery failures for `XRPUSDT`
  - these are logged as `(no-nrr)` and did not emit scoped target verbs in the observed window
- [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl)
  - `120` total records
  - only:
    - `EVT:PORTFOLIO_STATE_UPDATED=59`
    - `EVT:EXPOSURE_SUMMARY_UPDATED=59`
    - `RESTORE:EXECUTION_TRUTH_HARDENING_RESET=1`
    - `RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY=1`
  - zero scoped target records
- [2026-03-21.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-21.jsonl)
  - `82` total records
  - only:
    - `EVT:ACCOUNT_UPDATE_RECEIVED=59`
    - `EVT:BAR_CLOSED=21`
    - `EVT:TRADE_INTENT_REJECTED=2`
  - zero scoped target records

Post-warmup evidence captured:
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L16027) shows `XRPUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L16184) shows `ETHUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L17734) shows `BTCUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L17910) shows `SOLUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L19490) shows `1000PEPEUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L22761) shows later `XRPUSDT FE_WARMUP: full_ready=True`
- [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L22688), [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L25053), [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L27364), and [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L27384) show post-warmup `STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED`
- [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl) contains `5` rows total:
  - `BOOT=1`
  - `ORDER_REJECTED=4`
  - `source_fsm_counts={'OrderLoggerV1': 1, 'DecisionMaking': 4}`
- all fresh `ORDER_REJECTED` rows in [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl) are decision-side `NRR-027` safety-gate rejects, not execution-side terminal non-fill order events
- [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl) now contains `610` records total:
  - `RESTORE:EXECUTION_TRUTH_HARDENING_RESET=1`
  - `RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY=1`
  - `EVT:PORTFOLIO_STATE_UPDATED=304`
  - `EVT:EXPOSURE_SUMMARY_UPDATED=304`
  - still zero scoped target records

## 6. Chain reconstruction
No fresh scoped instances of `EVT:ORDER_REJECTED` or terminal non-fill `EVT:ORDER_STATE_CHANGED` were captured. Therefore no actual runtime source -> seam -> shadow -> consumer chain could be reconstructed for the scoped surfaces.

Observed control chain proving the journal is alive:
- `position_tracking` emitted `EVT:PORTFOLIO_STATE_UPDATED`
- same event appears in [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl) with `source_component=position_tracking`

Observed execution-side non-scoped chain:
- `bracket_manager` preflight allows
- `fsm` logs `[BRACKET-HEALTH] ... failed ... (no-nrr)`
- no corresponding scoped terminal-order event was observed in WAL or shadow journal

Observed post-warmup non-scoped decision chain:
- `DecisionMaking` logs `STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED`
- fresh `ORDER_REJECTED` rows are written to [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl)
- those rows carry `source_fsm=DecisionMaking`, `nrr_code=NRR-027`, and `metadata.reject_reason=SAFETY_GATES_DENY`
- no corresponding execution-side `EVT:ORDER_REJECTED` or terminal non-fill `EVT:ORDER_STATE_CHANGED` appears in WAL or shadow journal

## 7. Facts
- **FACT**: fresh runtime started after restart around `21:30:47–21:31:04`.
- **FACT**: active consumers for scoped verbs re-registered on startup in [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L158) and [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L163).
- **FACT**: [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl) contains zero `EVT:ORDER_REJECTED` and zero `EVT:ORDER_STATE_CHANGED` records in the fresh window.
- **FACT**: [2026-03-21.jsonl](c:/Users/user/Music/Phenix/ops/wal/2026-03-21.jsonl) contains zero `EVT:ORDER_REJECTED` and zero `EVT:ORDER_STATE_CHANGED` records in the fresh window.
- **FACT**: [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log#L1264) through [domain_execution_position.log](c:/Users/user/Music/Phenix/logs/domain_execution_position.log#L1341) show repeated bracket-health failures for `XRPUSDT`, all marked `(no-nrr)`.
- **FACT**: [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L39) logs `Execution truth warm-state empty start`.
- **FACT**: [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L3202) onward logs repeated `shadow_event_tap_client failed to deliver payload to tcp://127.0.0.1:7101`.
- **FACT**: post-warmup `FE_WARMUP: full_ready=True` markers appear for multiple symbols, including [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L17734) and [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L19490).
- **FACT**: post-warmup `STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED` appears in [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L22688), [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L25053), [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L27364), and [aurora_core.log](c:/Users/user/Music/Phenix/logs/aurora_core.log#L27384).
- **FACT**: [order_log_v1.jsonl](c:/Users/user/Music/Phenix/logs/order_log_v1.jsonl) contains four fresh `ORDER_REJECTED` rows, all with `source_fsm=DecisionMaking`, not execution-position.
- **FACT**: after warmup and post-warmup signal traffic, [shadow_critical_event_journal_v1.jsonl](c:/Users/user/Music/Phenix/logs/shadow_critical_event_journal_v1.jsonl) still contains zero scoped `EVT:ORDER_REJECTED` and zero scoped `EVT:ORDER_STATE_CHANGED`.

Cause / mechanism / effect / operational risk:
- Cause: fresh runtime window produced no scoped terminal non-fill events.
  Mechanism: no observed producer fire for the hardened verbs.
  Effect: canonical payload fields were not runtime-proven.
  Operational risk: package correctness remains code-backed, not fresh-runtime-confirmed.
- Cause: shadow tap delivery failures.
  Mechanism: `shadow_event_tap_client` cannot deliver to `tcp://127.0.0.1:7101`.
  Effect: external shadow tap channel is degraded.
  Operational risk: some observability consumers may miss live traffic even while local journal remains alive.

## 8. Inferences
- **INFERENCE**: during the observed window, scoped producers likely did not fire. This is supported by simultaneous absence in execution log, WAL, and shadow journal.
- **INFERENCE**: the accepted contract-hardening package was not falsified by fresh runtime, but it also was not positively validated on live scoped instances.
- **INFERENCE**: the absence of scoped target verbs is no longer explainable only by cold-start warmup, because post-warmup signal traffic and decision-side rejects are present.
- **INFERENCE**: the `FSMCore.emit()` compatibility seam was not exercised by fresh scoped events, so masking risk remains bounded but unproven.
- **INFERENCE**: the repeated bracket-health `(no-nrr)` failures show active execution-side failure behavior exists outside the scoped terminal-order seam.

## 9. Assumptions
- **ASSUMPTION**: the current truncated files represent the post-restart validation window cleanly.
- **ASSUMPTION**: if scoped producers had fired on the inspected active paths, at least one of execution log, WAL, or shadow journal would have shown the verb.

## 10. Unknowns
- **UNKNOWN**: whether raw producer payloads differed materially from canonicalized payloads on this fresh run, because no scoped emit traversed the seam.
- **UNKNOWN**: whether watchdog or WS terminal non-fill paths would produce exact or degraded lineage on a fresh event today.
- **UNKNOWN**: whether `shadow_event_tap_client` failure affects only the external tap or also some downstream forensic tooling relied on by operators.
- **UNKNOWN**: whether future fresh runtime windows with actual cancels / expiries / execution rejects would expose additional producer drift hidden by `FSMCore.emit()`.
- **UNKNOWN**: whether execution-side terminal non-fill events are simply rare on the current live path, or whether some active execution failure classes are bypassing the hardened verb surfaces.

## 11. Compatibility masking assessment
Assessment: **not runtime-proven; bounded residual risk remains**.

What was proven:
- the seam exists at [fsm_core.py](c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#L85)
- producer-side normalization also exists earlier in:
  - [binance_ws_client.py](c:/Users/user/Music/Phenix/apps/reference/adapters/binance_ws_client.py#L402)
  - [watchdog.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/watchdog.py#L453)
  - [open_executor.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/open_executor.py#L92)
  - [fsm.py](c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#L1886)

What was not proven on fresh runtime:
- no raw scoped producer payload was observed before `FSMCore.emit()`
- no normalized scoped payload was observed after `FSMCore.emit()`
- no shadow record exposed `compatibility_aliases_retained` for the scoped verbs because the verbs did not occur
- no post-warmup execution-side scoped verb was observed even after `TRADE_INTENT_PROPOSED` traffic appeared

Decision:
- current evidence does **not** show `FSMCore.emit()` masking a live producer defect on this run
- current evidence also does **not** certify that masking risk is bounded in practice

## 12. Lineage quality assessment
Observed-path classification:

| Path | Fresh observed? | Lineage quality | Reason |
| --- | --- | --- | --- |
| `ORDER_REJECTED` via `open_executor` | No | unknown | no fresh emit |
| `ORDER_REJECTED` via WS maker-only reject | No | unknown | no fresh emit |
| `ORDER_REJECTED` via `fsm` adapter-error reject | No | unknown | no fresh emit |
| terminal non-fill `ORDER_STATE_CHANGED` via watchdog | No | unknown | no fresh emit |
| terminal non-fill `ORDER_STATE_CHANGED` via WS status update | No | unknown | no fresh emit |
| decision-side `ORDER_REJECTED` in `order_log_v1.jsonl` | Yes | degraded but out of scope | rid + symbol + nrr exist, but this is `DecisionMaking`, not the scoped execution seam |
| bracket-health `(no-nrr)` warnings | Yes | weak | symbol-only log evidence, no canonical order identity surfaced in observed artifact chain |

## 13. Semantic separation check
Fresh runtime verdict: **not proven**.

What was observed:
- no fresh `ORDER_REJECTED`
- no fresh terminal non-fill `ORDER_STATE_CHANGED`
- no fresh runtime payload carrying `terminal_state_kind`
- no fresh runtime payload carrying `reject_reason_normalized`

Therefore:
- rejected vs canceled separation: **unknown on fresh runtime**
- rejected vs expired separation: **unknown on fresh runtime**
- `terminal_state_kind` runtime meaning: **unknown on fresh runtime**
- no evidence of collapse into a vague terminal bucket was observed, but absence is not proof

## 14. Runtime decision
**Decision: B**

`B = prior package is broadly correct but has bounded runtime gaps requiring a narrow follow-up package.`

Justification:
- code/registry seam remains in place and active consumers re-registered
- fresh runtime did not contradict the package
- but both the cold-start slice and the post-warmup slice did **not** produce the scoped verbs, so the claimed canonical runtime fields were not proven on live instances
- masking risk at `FSMCore.emit()` remains unexercised
- observability has a fresh bounded issue: repeated shadow tap delivery failures
- post-warmup activity shows the system is alive and producing decisions, but the scoped execution terminal non-fill surfaces still were not exercised

This is not `A`, because fresh runtime proof for the scoped verbs was not obtained.
This is not `C`, because no fresh runtime defect in the hardened scoped contract was directly observed.

## 15. Residual risks
- scoped verb chains remain runtime-unproven on fresh evidence
- `FSMCore.emit()` remains a high-attention compatibility seam without fresh scoped exercise
- shadow tap delivery to `tcp://127.0.0.1:7101` is failing repeatedly
- active execution-side bracket-health failures are happening outside the scoped seam with `(no-nrr)` behavior
- post-warmup live traffic currently proves only decision-side rejects, not scoped execution-side terminal non-fill behavior
- lineage quality for watchdog / WS / reject paths remains unknown until a fresh scoped instance occurs

## 16. Recommended next step
Run a **narrow forced-event runtime proof package** that deliberately generates one controlled instance of:
- execution-side `EVT:ORDER_REJECTED`
- terminal non-fill `EVT:ORDER_STATE_CHANGED`

Requirements for that next package:
- no redesign
- no new schemas
- preserve current contract seam
- capture raw producer payload, post-`FSMCore.emit()` payload, shadow record, and any consumer-visible payload in one bounded validation window
