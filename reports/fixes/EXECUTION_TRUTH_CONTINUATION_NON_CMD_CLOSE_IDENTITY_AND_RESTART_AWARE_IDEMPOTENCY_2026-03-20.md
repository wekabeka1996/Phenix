# REPORT — EXECUTION TRUTH CONTINUATION NON CMD CLOSE IDENTITY AND RESTART AWARE IDEMPOTENCY

## 1. Executive Summary
This package extends the previous pre-stabilization hardening in three narrow areas:

1. non-`CMD:CLOSE` close propagation,
2. stronger shared identity discipline for `EVT:TRADE_EXECUTED`,
3. explicit restart-aware semantics for process-local idempotency state.

Implemented changes:
- added a non-`CMD:CLOSE` close suppression seam at the `DEC:CLOSE` execution boundary,
- strengthened shared fill identity from `symbol + orderId` to `symbol + orderId + clientOrderId` when available, with explicit degraded modes when not,
- enriched WS and watchdog `EVT:TRADE_EXECUTED` payloads so the shared seam sees the same identity inputs on both producer paths,
- made restart reset of the in-memory hardening state explicit and observable via shadow journal records.

Intentionally not changed:
- no FSM migration,
- no broad close-logic redesign,
- no restore/hydrate refactor,
- no persisted dedupe cache,
- no contract cleanup beyond the fields needed for the shared identity seam.

**Merge safety:** `YES`, for the narrow scope of this package.

---

## 2. Scope
### Changed active paths
- WS `ORDER_TRADE_UPDATE` `FILLED` -> `EVT:TRADE_EXECUTED`
- watchdog REST `FILLED` detection -> `EVT:TRADE_EXECUTED`
- shared `EVT:TRADE_EXECUTED` hardening in `FSMCore.emit()`
- non-`CMD:CLOSE` `DEC:CLOSE` execution path in `ExecPosFSM._execute_decision()`
- hardening attach/reset visibility during owner initialization
- shadow journal critical-event coverage for the new hardening events

### Intentionally left untouched
- `CloseFlowFSM` contract and ownership
- full restart/replay truth reconstruction
- non-fill order-state identity redesign
- broader `ManageFlowFSM` policy logic
- downstream `CloseExecutor` semantics

---

## 3. Active Paths Confirmed
### Fill path instrumented and hardened
```text
BinanceWS ORDER_TRADE_UPDATE (status=FILLED)
  -> payload built in binance_ws_client.py
  -> FSMCore.emit("EVT:TRADE_EXECUTED")
  -> ExecutionTruthHardening.evaluate_trade_executed(...)
  -> callbacks / PositionTracking / other listeners

Watchdog REST poll (status=FILLED, executedQty>0)
  -> fill_payload built in watchdog.py
  -> emit_fn("EVT:TRADE_EXECUTED", fill_payload)
  -> FSMCore.emit("EVT:TRADE_EXECUTED")
  -> ExecutionTruthHardening.evaluate_trade_executed(...)
  -> callbacks / PositionTracking / other listeners
```

### Non-`CMD:CLOSE` close path hardened
```text
ManageFlowFSM._check_max_hold_time()
  -> returns DEC:CLOSE directly
  -> ExecPosFSM._execute_decision()
  -> non-CMD close guard
  -> CloseExecutor.execute_close(...)
```

### Restart-aware attach path observed
```text
ExecPosFSM.__init__()
  -> attach_execution_truth_hardening(...)
  -> RESTORE:EXECUTION_TRUTH_HARDENING_RESET

PositionTracking.__init__()
  -> attach_execution_truth_hardening(...)
  -> reuses existing owner-attached hardening or records reset on fresh attach
```

### FACTS
- `ManageFlowFSM._check_max_hold_time()` still emits `DEC:CLOSE` directly for max-hold timeout.
- `CloseFlowFSM` still describes itself as a soldier that executes explicit `CMD:CLOSE`.
- WS `EVT:TRADE_EXECUTED` emission is gated on `standardized_status == "FILLED"`.
- watchdog `EVT:TRADE_EXECUTED` emission is gated on `status == "FILLED"` and `executedQty > 0`.

### INFERENCES
- The max-hold `DEC:CLOSE` path was the highest-confidence uncovered non-`CMD:CLOSE` close producer on the active path.
- Because both producer paths are terminal-fill paths, order-lifecycle identity is a safer shared basis than it would be for partial-fill streams.

### ASSUMPTIONS
- Other non-`CMD:CLOSE` close emitters, if any, are lower-frequency or out of the validated runtime slice for this package.

### UNKNOWNS
- Whether any additional rare `DEC:CLOSE` producers exist outside the validated path and carry materially different semantics.

---

## 4. Non-CMD-CLOSE Coverage Audit
| Close path | Active? | Previously covered? | Newly hardened? | Guard basis | Residual risk |
|---|---|---:|---:|---|---|
| `CMD:CLOSE -> CloseFlowFSM -> DEC:CLOSE` | Yes | Yes | No | `cmd_close:{symbol}:position_signature:qty` | Existing process-local-only behavior remains |
| `ManageFlowFSM._check_max_hold_time() -> DEC:CLOSE` | Yes | No | Yes | `non_cmd_dec_close:{symbol}:position_signature:qty` | Only same-effective-state repeats are suppressed |
| `DEC:CLOSE` with unknown position but `rid` present | Possible | No | Yes | `non_cmd_dec_close:{symbol}:unknown_position:rid:qty` | Depends on `rid` stability |
| `DEC:CLOSE` with missing symbol | Fail-open only | No | No | None | Explicit fail-open |
| Other downstream close execution inside `CloseExecutor` | Not changed | No | No | N/A | Out of scope for this package |

Why the max-hold path was hardened:
- it was proven active,
- it bypassed the previous direct `CMD:CLOSE` guard,
- `ExecPosFSM._execute_decision()` is the narrowest common execution choke point before downstream close side effects,
- guarding there preserves existing `ManageFlowFSM` ownership and avoids rewriting policy emitters.

Why other close logic was left unchanged:
- this package is not a broad close-system redesign,
- no stronger active-path evidence justified pushing the guard lower into `CloseExecutor`,
- a lower guard would have larger blast radius and a higher risk of suppressing semantically distinct close actions.

---

## 5. Fill Identity Design
### Chosen policy
Primary shared key:
```text
trade_executed:{symbol}:order_id={orderId}:client_order_id={clientOrderId}
```

Degraded fallback order:
1. `symbol + orderId + lifecycle_anchor`, where `lifecycle_anchor = idempotent_key or rid`
2. `symbol + orderId`
3. fail-open if `symbol` or `orderId` is missing

### Why this identity was chosen
- `orderId` is present on both active producer paths.
- `clientOrderId` is now explicitly propagated on both active producer paths.
- WS `tradeId` exists, but watchdog/REST does not provide a shared equivalent on the active path.
- `idempotent_key` and `rid` are useful degraded anchors but not strong enough to replace lifecycle contract identity when `clientOrderId` exists.

### What counts as “same fill truth”
For this package, “same fill truth” means:
- same terminal `FILLED` event,
- same `symbol`,
- same exchange `orderId`,
- same lifecycle `clientOrderId`.

Because the active emission surfaces are terminal-fill only, that identity is strong enough for the current shared dedupe seam.

### Table B — Fill Identity Matrix
| Candidate field | Available on WS path? | Available on watchdog/REST path? | Stable enough? | Used in final key? | Notes |
|---|---:|---:|---:|---:|---|
| `symbol` | Yes | Yes | Yes | Yes | Required context field |
| `orderId` | Yes | Yes | Yes | Yes | Shared exchange order anchor |
| `clientOrderId` / `client_order_id` | Yes | Yes | Yes | Yes | Added to watchdog path; strongest shared lifecycle anchor |
| `tradeId` / `trade_id` | Yes | No | No for shared seam | No | Logged as present-but-not-used when degraded |
| `idempotent_key` | Yes | Not reliably | Partial | Fallback only | Derived from order index on WS path |
| `rid` | Yes | Yes | Partial | Fallback only | Used only when stronger lifecycle identity missing |
| `qty` | Yes | Yes | Not enough alone | No | Distinct fills could share qty |
| `price` | Yes | Yes | Not enough alone | No | Distinct fills could share price |
| `ts_ms` | Yes | Yes | Not enough alone | No | Timing alone is too weak |

### Owner / lifetime / invalidation
- Owner: `ExecutionTruthHardening`
- Storage owner in process: `_fill_deduper`
- Lifetime: process-local, bounded by `event_dedup.ttl_ms`
- Invalidation: TTL expiry and bounded-size eviction
- Restart behavior: full reset on fresh attach

### Exact vs degraded identity cases
- Exact: `symbol + orderId + clientOrderId`
- Degraded: `symbol + orderId + (idempotent_key or rid)`
- More degraded: `symbol + orderId`
- Fail-open: missing `symbol` or `orderId`

### FACTS
- WS producer now emits `clientOrderId`, `client_order_id`, `tradeId`, `trade_id`, `quantity`, `price`, `ts_ms`.
- watchdog producer now emits `clientOrderId`, `client_order_id`, `rid`, `qty`, `price`, `ts_ms`.
- `FSMCore.emit()` is the shared choke point that sees both producer paths.

### INFERENCES
- `symbol + orderId + clientOrderId` is the strongest practical shared identity basis currently available across both active producer paths.

### ASSUMPTIONS
- Terminal `FILLED` events are not intended to represent multiple distinct business fills for the same `orderId + clientOrderId` combination on the active path.

### UNKNOWNS
- Whether future adapter changes could expose a reliable cross-path trade/execution id that is stronger than order-lifecycle identity.

---

## 6. Restart-Aware Idempotency Design
### Policy
No dedupe or close-guard state is persisted in this package.

Instead:
- attach creates a fresh `ExecutionTruthHardening` instance,
- fresh attach emits `RESTORE:EXECUTION_TRUTH_HARDENING_RESET`,
- the reset record states that both fill dedupe and close guard state are `process_local_only`,
- prior process suppression state is intentionally not reused after restart.

### Why this is safe enough now
- it is explicit,
- it is observable,
- it avoids pretending the system has a canonical replayable restore layer today,
- it avoids introducing a hidden competing truth store,
- it keeps later replay/cutover work honest.

### Table C — Restart Idempotency Matrix
| State owner | Key/state tracked | Process-local or persisted? | Reset on restart? | Observable? | Residual risk |
|---|---|---|---:|---:|---|
| `ExecutionTruthHardening._fill_deduper` | fill identity keys | Process-local | Yes | Yes | duplicate events after restart can still reapply |
| `ExecutionTruthHardening._close_guard` | per-scope close guard key by symbol | Process-local | Yes | Yes | repeated close after restart can re-enter if runtime state unchanged |
| Shadow journal | reset marker only | Persisted append-only file | No | Yes | journal observes reset but does not seed guards |

### What resets
- fill dedupe keys
- `cmd_close` guard entries
- `non_cmd_dec_close` guard entries

### What persists
- shadow journal records only

### What is only observed
- restart reset itself
- the fact that no persisted seed is used

### FACTS
- `attach_execution_truth_hardening()` records `RESTORE:EXECUTION_TRUTH_HARDENING_RESET`.
- reset notes include `process_local_only_state`, `no_persisted_seed`, `restart_reset_explicit`.

### INFERENCES
- Explicit reset plus observability is safer than a partial persisted cache with unclear invalidation semantics.

### ASSUMPTIONS
- Later replay-safe truth work will introduce a stronger canonical seed or replay discipline rather than stretching this package into hidden persistence.

### UNKNOWNS
- The exact future owner of persisted execution identity state.

---

## 7. Files Changed
| File | Function/Class | Purpose | Behavior risk |
|---|---|---|---|
| `apps/reference/domains/execution_position/truth_hardening.py` | `ExecutionTruthHardening`, `resolve_trade_executed_identity()`, `evaluate_non_cmd_close_decision()`, `attach_execution_truth_hardening()` | stronger fill identity, non-`CMD:CLOSE` guard, explicit restart reset | Low, narrow hardening only |
| `vfoundation/core/fsm_core.py` | `FSMCore.emit()` | shared `EVT:TRADE_EXECUTED` identity evaluation and degraded-identity observability | Low, fail-open on hardening failure |
| `apps/reference/domains/execution_position/fsm.py` | `_execute_decision()` | suppress repeated non-`CMD:CLOSE` close execution before downstream side effects | Medium-low, close-path behavior change but narrow |
| `apps/reference/domains/execution_position/watchdog.py` | `_poll_order_statuses()` fill payload | propagate shared identity fields on REST path | Low, additive payload only |
| `apps/reference/adapters/binance_ws_client.py` | `ORDER_TRADE_UPDATE` payload build | propagate additive shared identity fields on WS path | Low, additive payload only |
| `apps/reference/telemetry/shadow_journal.py` | critical event list, payload fragment retention | preserve visibility for new hardening events | Low |
| `apps/reference/config_models.py` | `ShadowCriticalEventJournalConfig` defaults | keep new critical events in SSOT config model | Low |
| `config/aurora/observability.yaml` | `shadow_journal.critical_events` | enable new shadow records by config | Low |
| `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py` | focused tests | prove continuation behavior | None in runtime |

---

## 8. Behavioral Changes
Intentional runtime changes introduced by this package:

1. repeated non-`CMD:CLOSE` `DEC:CLOSE` executions for the same effective state are now suppressed before `CloseExecutor.execute_close()` is called.
2. `EVT:TRADE_EXECUTED` dedupe now uses stronger lifecycle identity when `clientOrderId` is available on both producer paths.
3. degraded fill identity is now explicitly surfaced in shadow observability.
4. process restart or fresh attach now explicitly resets hardening state, with a visible shadow record.

Not changed:
- business close reasons,
- sizing,
- routing,
- exchange calls,
- strategy/risk logic,
- restore state reconstruction semantics.

---

## 9. Observability Integration
### New shadow-visible events
- `HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED`
- `HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED`
- `RESTORE:EXECUTION_TRUTH_HARDENING_RESET`

### Existing shadow-visible event preserved
- `HARDENING:TRADE_EXECUTED_SUPPRESSED`

### What is visible now
- when fill identity is exact vs degraded,
- when a trade id existed but could not be used for the shared key,
- when a repeated non-`CMD:CLOSE` close was suppressed,
- when process-local hardening state reset on attach/restart.

### Table D — Observability Matrix
| Scenario | Shadow record emitted? | Exact or heuristic? | Notes |
|---|---:|---|---|
| degraded `EVT:TRADE_EXECUTED` identity | Yes | Exact | based on missing shared identity fields |
| duplicate `EVT:TRADE_EXECUTED` suppression | Yes | Exact within chosen identity basis | key and identity quality recorded |
| repeated non-`CMD:CLOSE` `DEC:CLOSE` suppression | Yes | Exact within guard basis | guard key and reason recorded |
| hardening state reset on attach/restart | Yes | Exact | reset is explicit, not inferred |

---

## 10. Tests Added / Updated
- `test_trade_executed_order_only_identity_is_observable_as_degraded`
  - proves degraded fill identity is recorded and does not block first delivery
- `test_restart_reset_is_explicit_and_previous_fill_dedupe_state_is_not_reused`
  - proves dedupe state is process-local and reset is visible
- `test_watchdog_fill_payload_preserves_shared_identity_fields`
  - proves the REST watchdog path now carries the shared identity fields
- `test_non_cmd_dec_close_guard_suppresses_repeated_execution_and_allows_after_state_change`
  - proves repeated non-`CMD:CLOSE` close execution is suppressed, and a real position change reopens the path

---

## 11. Validation Evidence
### Commands run
```text
python -m py_compile apps/reference/domains/execution_position/truth_hardening.py apps/reference/domains/execution_position/fsm.py apps/reference/domains/execution_position/watchdog.py apps/reference/adapters/binance_ws_client.py apps/reference/telemetry/shadow_journal.py apps/reference/config_models.py vfoundation/core/fsm_core.py tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py
```
Result: success

```text
python -m pytest tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py -q
```
Result: `4 passed in 1.45s`

```text
python -m pytest tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py tests/telemetry/test_shadow_critical_event_journal.py tests/domains/test_watchdog_polling_fix.py tests/domains/execution_position/test_execpos_max_hold_close_routed_v1.py -q
```
Result: `12 passed in 2.63s`

```text
python -m pytest tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k trade_executed_marks_order_index_terminal -q
```
Result: `1 passed, 29 deselected in 0.55s`

```text
python -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader().load_config(); print(f'shadow_journal.path={cfg.observability.shadow_journal.path}'); print(f'anti_race_close_ms={cfg.trading.execution.anti_race_close_ms}'); print(f'event_dedup.ttl_ms={cfg.domains.execution_position.event_dedup.ttl_ms}')"
```
Result:
```text
shadow_journal.path=logs/shadow_critical_event_journal_v1.jsonl
anti_race_close_ms=800
event_dedup.ttl_ms=86400000
```

### Additional note
- Running `tests/domains/execution_position/test_execpos_max_hold_close_routed_v1.py` still produces a pytest unraisable warning: `coroutine 'ExecPosFSM._execute_decision' was never awaited`. The test itself passes. This warning was observed outside the new continuation test file and was not introduced by the new dedicated continuation assertions.

### Table E — Validation Matrix
| Scenario | Expected behavior | Proven by code? | Proven by test? | Notes |
|---|---|---:|---:|---|
| active non-`CMD:CLOSE` path audited | max-hold direct `DEC:CLOSE` confirmed | Yes | Yes | code path and execution test |
| repeated non-`CMD:CLOSE` close suppressed | second same-state execution blocked | Yes | Yes | dedicated continuation test |
| legitimate new close after state change allowed | third execution after position change allowed | Yes | Yes | dedicated continuation test |
| stronger shared fill identity used | `clientOrderId` participates in key | Yes | Yes | payload propagation + tests |
| degraded identity remains visible | shadow event emitted with missing-field notes | Yes | Yes | dedicated continuation test |
| restart reset explicit | reset marker emitted on attach | Yes | Yes | dedicated continuation test |
| prior process dedupe not reused | same fill after new attach is not suppressed | Yes | Yes | dedicated continuation test |
| regression slice still passes | no broad drift in covered tests | Yes | Yes | focused regression subset |

---

## 12. Safety Assessment
This package remains narrow because it hardens two load-bearing seams and one restart observability seam without changing domain ownership:

- fill dedupe remains centralized at the existing shared emit choke point,
- non-`CMD:CLOSE` hardening is added only at the close execution boundary, not spread across policy producers,
- restart behavior is made explicit through shadow observability rather than hidden persistence.

Blast radius that remains:
- process-local guard state still resets on restart,
- uncovered close producers outside the validated path are still possible,
- fill identity remains degraded when `clientOrderId` is missing,
- no canonical replay/reseed mechanism exists yet.

### FACTS
- instrumentation and hardening both fail open on internal error.
- no strategy, risk, sizing, or adapter order-routing code path was redesigned.

### INFERENCES
- this package improves runtime truth discipline without moving ownership into a new hidden subsystem.

### ASSUMPTIONS
- the current active producer paths remain terminal-fill paths rather than partial-fill streams.

### UNKNOWNS
- how much additional close-path coverage will be needed before broader lifecycle stabilization.

---

## 13. Limitations
- No persisted dedupe state. Duplicate fill or repeated close exposure can still re-enter after restart.
- Fill identity still degrades to weaker bases when `clientOrderId` is absent.
- `tradeId` is not yet a shared exact key because the watchdog path does not provide a matching stable value on the active path.
- This package does not solve replay, restore completeness, or canonical lifecycle reconstruction.
- This package does not harden every possible close-producing path in the repo; it hardens the highest-confidence uncovered active path.

---

## 14. Long-Term Goal Alignment
This package moves the system toward a canonical replayable truth plane in four ways:

1. identity is more explicit and less heuristic on the live fill surface,
2. suppression reasons are explicit and shadow-visible,
3. restart semantics are explicit instead of implicit,
4. the hardening seams remain additive and low-coupling rather than becoming a hidden SSOT.

It does **not** pretend the long-term goal is already solved. That is the correct alignment for pre-stabilization work.

---

## 15. Next Recommended Package
**Recommended next package:** restart-seeded execution truth warm-state for terminal order/fill identity.

Target scope:
- use journal-visible truth to seed a narrow restart warm set for recent terminal order/fill identities,
- validate seeding rules explicitly against restore/hydrate boundaries,
- extend close-path audit to any remaining active forced-close producers,
- do not yet attempt full replay or FSM migration.

---

## REPORT Appendix
### Files changed
- `apps/reference/domains/execution_position/truth_hardening.py`
- `vfoundation/core/fsm_core.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/watchdog.py`
- `apps/reference/adapters/binance_ws_client.py`
- `apps/reference/telemetry/shadow_journal.py`
- `apps/reference/config_models.py`
- `config/aurora/observability.yaml`
- `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py`

### Key code snippets
#### Shared fill identity policy
```python
if client_order_id:
    return TradeExecutedIdentity(
        key=(
            f"trade_executed:{symbol}:order_id={order_id}:"
            f"client_order_id={client_order_id}"
        ),
        identity_quality="order_lifecycle_contract_identity",
        exact_identity=True,
        degraded_identity=False,
        ...
    )
```

#### Non-CMD close suppression at execution boundary
```python
if decision.verb in ("CLOSE", "CLOSE_POSITION"):
    ...
    if symbol and hardening is not None and trigger != "CMD:CLOSE":
        close_decision = hardening.evaluate_non_cmd_close_decision(...)
        if close_decision.suppress:
            journal.record_transition(
                event_name="HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED",
                ...
            )
            return
```

#### Explicit restart reset visibility
```python
journal.record_transition(
    event_name="RESTORE:EXECUTION_TRUTH_HARDENING_RESET",
    source_component="execution_truth_hardening",
    source_path="restore:execution_truth_hardening_reset",
    event_origin_type="restore",
    restore_marker=True,
    notes=[
        "process_local_only_state",
        "no_persisted_seed",
        "restart_reset_explicit",
    ],
)
```

### Identity/suppression config snippet
```yaml
observability:
  shadow_journal:
    critical_events:
      - HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED
      - HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED
      - RESTORE:EXECUTION_TRUTH_HARDENING_RESET
```

### Example shadow records
```json
{"event_name":"RESTORE:EXECUTION_TRUTH_HARDENING_RESET","source_component":"execution_truth_hardening","source_path":"restore:execution_truth_hardening_reset","event_origin_type":"restore","truth_owner":"ExecutionTruthHardening","restore_marker":true,"notes":["process_local_only_state","no_persisted_seed","restart_reset_explicit"]}
```

```json
{"event_name":"HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED","source_path":"watchdog:rest_poll","notes":["order_only_identity_degraded","missing_client_order_id"]}
```

```json
{"event_name":"HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED","source_path":"execution:non_cmd_close_guard","truth_owner":"ExecPosFSM","notes":["duplicate_non_cmd_dec_close_same_effective_state","guard_key=non_cmd_dec_close:BTCUSDT:position=LONG:0.01:qty=0.01"]}
```

### Table A — Close Path Coverage Matrix
| Close path | Active? | Previously covered? | Newly hardened? | Guard basis | Residual risk |
|---|---:|---:|---:|---|---|
| direct `CMD:CLOSE` path | Yes | Yes | No | `cmd_close` state key | process-local reset only |
| max-hold direct `DEC:CLOSE` path | Yes | No | Yes | `non_cmd_dec_close` state key | only same-effective-state repeats suppressed |
| unknown-position non-`CMD:CLOSE` close | Possible | No | Yes | `rid + qty` fallback | depends on `rid` presence |
| downstream close execution variants | Not covered here | No | No | N/A | out of scope |

### Table F — Non-Goals Matrix
| Non-goal | Why excluded |
|---|---|
| FSM migration | explicitly out of scope for continuation hardening |
| full restore redesign | requires broader truth-plane work |
| persisted replay engine | this package only makes reset explicit |
| broad close-system rewrite | too invasive for pre-stabilization |
| global contract cleanup | only additive fields required for shared identity were changed |
