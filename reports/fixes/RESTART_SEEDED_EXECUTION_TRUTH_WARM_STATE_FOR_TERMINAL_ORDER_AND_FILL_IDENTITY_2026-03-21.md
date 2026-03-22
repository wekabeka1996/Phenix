# REPORT — RESTART SEEDED EXECUTION TRUTH WARM STATE FOR TERMINAL ORDER AND FILL IDENTITY

## 1. Executive Summary
This package introduces a bounded restart-seeded warm-state for recent exact terminal fill identities.

What changed:
- `ExecutionTruthHardening` now persists a small atomic warm-state snapshot of recent exact `EVT:TRADE_EXECUTED` identities.
- fresh bus-owner attach now loads that warm-state back into the shared fill dedupe seam.
- warm-state load success, empty start, load failure, hit, and miss are explicitly visible in shadow observability.

What restart risk this reduces:
- exact duplicate terminal fill re-entry after restart on the shared `EVT:TRADE_EXECUTED` path.

What it intentionally does not do:
- no replay engine,
- no full restore redesign,
- no FSM migration,
- no attempt to reconstruct full order or position lifecycle state,
- no warm-state seeding for degraded identities.

**Merge safety:** `YES`, for this narrow continuity scope.

---

## 2. Scope
### Active paths changed
- shared `EVT:TRADE_EXECUTED` hardening in `FSMCore.emit()`
- `ExecutionTruthHardening` attach/load/persist path
- execution-position event dedupe config SSOT
- shadow journal critical-event coverage for warm-state lifecycle
- focused restart continuity tests

### Intentionally left untouched
- `CMD:CLOSE` and non-`CMD:CLOSE` close guard semantics
- restore/hydrate architecture in `main.py`
- `CloseExecutor` behavior
- full terminal order-state dedupe beyond the exact terminal fill surface
- degraded fill identity suppression after restart

---

## 3. Active Paths Confirmed
### Terminal fill path targeted
```text
WS ORDER_TRADE_UPDATE (FILLED)
  -> binance_ws_client.py payload
  -> FSMCore.emit("EVT:TRADE_EXECUTED")
  -> ExecutionTruthHardening.evaluate_trade_executed(...)
  -> exact identity persisted to warm-state snapshot

Watchdog REST FILLED
  -> watchdog.py payload
  -> FSMCore.emit("EVT:TRADE_EXECUTED")
  -> ExecutionTruthHardening.evaluate_trade_executed(...)
  -> exact identity persisted to warm-state snapshot
```

### Restart path targeted
```text
PositionTracking.__init__()
  -> attach_shadow_journal(...)
  -> attach_execution_truth_hardening(FSMCore, config)
  -> load warm-state snapshot into shared fill dedupe seam

ExecPosFSM.__init__()
  -> attach_execution_truth_hardening(non-bus owner, config)
  -> reset recorded, but terminal fill warm-state not loaded here
```

### FACTS
- `FSMCore.emit()` is the shared choke point that sees both WS and watchdog `EVT:TRADE_EXECUTED`.
- `attach_execution_truth_hardening()` is already the existing owner attach seam.
- `ExecPosFSM` is not the shared bus owner for `EVT:TRADE_EXECUTED` dedupe.

### INFERENCES
- Warm-state should be owned by the existing hardening object, but loaded only on the bus owner that actually performs shared fill suppression.

### ASSUMPTIONS
- The active `EVT:TRADE_EXECUTED` surfaces remain terminal-fill surfaces, not partial-fill streams.

### UNKNOWNS
- Whether future active producer paths will add a stronger cross-path execution id than the current exact order-lifecycle identity.

---

## 4. Warm-State Design
### Included terminal truths
- exact terminal fill identities observed on `EVT:TRADE_EXECUTED`

### Excluded terminal truths
- degraded fill identities (`orderId + lifecycle_anchor`, `orderId` only)
- close guard state
- non-fill terminal order states (`REJECTED`, `EXPIRED`, `CANCELED`)
- snapshot/hydrate inferred lifecycle state

### Owner
- `ExecutionTruthHardening`
- load only on bus-owner attach (`FSMCore`-style owner with `emit` and `listen`)

### Key structure
```text
trade_executed:{symbol}:order_id={orderId}:client_order_id={clientOrderId}
```

### Retention and pruning
- retention window: `domains.execution_position.event_dedup.ttl_ms`
- max entries: `domains.execution_position.event_dedup.warm_state.max_entries`
- prune rules:
  - drop expired entries on load/update
  - drop oldest entries when exceeding `max_entries`

### Boundedness
- atomic JSON snapshot file
- exact identities only
- bounded by `max_entries`
- not a replay log

### Why this scope is safe
- it preserves only recent exact terminal fill identities,
- it does not attempt lifecycle reconstruction,
- it uses the same exact identity basis already proven safe on the live path,
- it leaves degraded identities fail-open across restart.

### Table A — Terminal Identity Warm-State Matrix
| Terminal truth type | Included? | Identity basis | Exact or degraded? | Retention | Residual risk |
|---|---:|---|---|---|---|
| terminal fill identity from `EVT:TRADE_EXECUTED` | Yes | `symbol + orderId + clientOrderId` | Exact | `ttl_ms` and `max_entries` | only exact cases survive restart |
| terminal fill identity without `clientOrderId` | No | `symbol + orderId + anchor` or `symbol + orderId` | Degraded | N/A | duplicates can still re-enter after restart |
| close guard state | No | state signature | N/A | N/A | repeated close after restart remains process-local only |
| non-fill terminal order identity | No | order terminal status | N/A | N/A | out of scope for this package |

---

## 5. Seed Source Design
### Chosen source
The warm-state seed is a narrow persisted snapshot written by `ExecutionTruthHardening` from the live exact terminal fill surface itself.

### Why this source is trustworthy enough
- it is fed only from exact `EVT:TRADE_EXECUTED` identities already accepted by the shared hardening seam,
- those same events are already visible in the shadow journal,
- it avoids broad journal parsing or replay-like startup behavior,
- it stays bounded and low-coupling.

### What happens on partial or missing seed data
- degraded identities are not persisted,
- empty or missing snapshot -> explicit empty start,
- corrupt snapshot -> explicit load failure and fail-open empty seed.

### What remains heuristic
- nothing in the chosen seed itself is heuristic; heuristics remain only in the broader observability plane, not in the warm-state identity basis.

### Table B — Seed Source Matrix
| Seed source | Trusted enough? | Why | Failure mode | Notes |
|---|---:|---|---|---|
| exact live `EVT:TRADE_EXECUTED` identities persisted by hardening owner | Yes | exact terminal fill surface, same shared seam, bounded | load fail-open, empty seed | chosen source |
| shadow journal scan | No for this package | broader, heavier, closer to replay behavior | startup scan complexity | intentionally not chosen |
| snapshot/hydrate state | No | not terminal identity truth | false continuity | intentionally excluded |

### FACTS
- exact warm-state entries are written only when `TradeExecutedIdentity.exact_identity` is true.
- persisted entry schema stores `key`, `ts_ms`, `symbol`, `order_id`, `client_order_id`, `identity_quality`.

### INFERENCES
- a dedicated bounded snapshot is safer than journal replay for this package because it narrows startup behavior to one continuity concern.

### ASSUMPTIONS
- the atomic snapshot file is acceptable as a continuity cache because it is explicitly bounded and derived from already-visible truth.

### UNKNOWNS
- whether a future canonical truth layer will obsolete this snapshot or absorb it.

---

## 6. Restart Behavior Design
### When warm-state loads
- on fresh `attach_execution_truth_hardening()` for the bus owner

### Missing / empty / corrupt behavior
- missing file -> `RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY`
- empty usable entries -> `RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY`
- corrupt / invalid file -> `RESTORE:EXECUTION_TRUTH_WARM_STATE_LOAD_FAILED`, then fail-open empty seed

### What resets
- in-memory dedupe state
- in-memory close guard state

### What is retained
- exact terminal fill warm-state snapshot only

### What is explicitly observable
- hardening reset
- warm-state loaded / empty / load-failed
- warm-state hit
- warm-state miss
- degraded identity

### What remains unsolved
- full lifecycle restore
- degraded restart continuity
- close guard persistence across restart

### Table C — Restart Behavior Matrix
| State owner | Process-local or seeded? | Loaded on restart? | Reset on restart? | Observable? | Residual risk |
|---|---|---:|---:|---:|---|
| `ExecutionTruthHardening._fill_deduper` | Process-local + exact warm seed | Yes, on bus owner | Yes, before seed | Yes | degraded identities still lost |
| `ExecutionTruthHardening._close_guard` | Process-local only | No | Yes | Yes | repeated close can still re-enter after restart |
| warm-state snapshot file | Seeded cache | Yes | No | Yes | not authoritative lifecycle truth |

---

## 7. Files Changed
| File | Function/Class | Purpose | Behavior risk |
|---|---|---|---|
| `apps/reference/domains/execution_position/truth_hardening.py` | `ExecutionTruthHardening`, `WarmStateLoadResult`, attach/load/persist helpers | add exact terminal fill warm-state continuity | Low |
| `vfoundation/core/fsm_core.py` | `FSMCore.emit()` | emit warm-state hit/miss observability around shared fill dedupe | Low |
| `apps/reference/config_models.py` | `EventDedupWarmStateConfig`, `EventDedupConfig`, shadow-event defaults | SSOT config and observability defaults | Low |
| `config/aurora/domains.yaml` | `event_dedup.warm_state` | live config for path and bounded size | Low |
| `apps/reference/telemetry/shadow_journal.py` | `DEFAULT_CRITICAL_EVENTS` | capture warm-state lifecycle events | Low |
| `config/aurora/observability.yaml` | `shadow_journal.critical_events` | enable warm-state journal events | Low |
| `tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py` | focused restart tests | prove warm-state continuity behavior | None |
| `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py` | updated config isolation | preserve prior process-local-only scenario | None |
| `tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py` | temp warm-state isolation | avoid cross-test pollution | None |
| `tests/telemetry/test_shadow_critical_event_journal.py` | temp warm-state isolation | avoid cross-test pollution | None |
| `tests/domains/execution_position/conftest.py` | shared mock config | explicit warm-state config | None |
| `tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py` | mock config | explicit warm-state config | None |

---

## 8. Behavioral Changes
Intentional runtime behavior changes:

1. exact terminal fill identities now survive restart in a bounded warm-state sense.
2. a fresh bus-owner process can suppress a duplicate exact `EVT:TRADE_EXECUTED` immediately after restart if that identity was recently persisted.
3. degraded identities are explicitly excluded from warm-state persistence and remain fail-open across restart.
4. warm-state load/reset/hit/miss outcomes are now shadow-visible.

Not changed:
- full order or position reconstruction,
- close guard restart continuity,
- lifecycle replay,
- strategy/risk logic,
- adapter execution semantics.

---

## 9. Observability Integration
### New shadow-visible events
- `RESTORE:EXECUTION_TRUTH_WARM_STATE_LOADED`
- `RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY`
- `RESTORE:EXECUTION_TRUTH_WARM_STATE_LOAD_FAILED`
- `HARDENING:TRADE_EXECUTED_WARM_STATE_HIT`
- `HARDENING:TRADE_EXECUTED_WARM_STATE_MISS`

### Existing event still used
- `HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED`
- `HARDENING:TRADE_EXECUTED_SUPPRESSED`
- `RESTORE:EXECUTION_TRUTH_HARDENING_RESET`

### Table D — Observability Matrix
| Scenario | Shadow record emitted? | Exact or heuristic? | Notes |
|---|---:|---|---|
| warm-state empty start | Yes | Exact | missing or zero usable entries |
| warm-state load success | Yes | Exact | includes loaded/skipped counts |
| warm-state load failure | Yes | Exact | fail-open empty seed |
| warm-state hit | Yes | Exact | seeded exact terminal fill key matched |
| warm-state miss | Yes | Exact | exact key observed but not seeded |
| degraded identity | Yes | Exact | existing degraded identity event preserved |

---

## 10. Tests Added / Updated
- `test_restart_seeded_warm_state_suppresses_exact_terminal_fill_after_restart`
  - proves exact terminal fill identity survives restart and suppresses re-entry
- `test_restart_seeded_warm_state_allows_distinct_exact_terminal_fill_after_restart`
  - proves a distinct exact terminal fill is not incorrectly suppressed
- `test_degraded_identity_is_not_seeded_and_remains_visible_after_restart`
  - proves degraded identities are excluded from warm-state and remain visible
- `test_corrupt_warm_state_load_is_observable_and_fail_open`
  - proves load failure is explicit and core flow remains open
- updated older restart-continuation tests to disable warm-state where they intentionally verify process-local-only behavior
- updated shared test helpers to isolate warm-state files per test

---

## 11. Validation Evidence
### Commands run
```text
python -m py_compile apps/reference/domains/execution_position/truth_hardening.py vfoundation/core/fsm_core.py apps/reference/config_models.py apps/reference/telemetry/shadow_journal.py tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py tests/telemetry/test_shadow_critical_event_journal.py tests/domains/execution_position/conftest.py tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py
```
Result: success

```text
python -m pytest tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py -q
```
Result: `4 passed in 2.04s`

```text
python -m pytest tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py -q
```
Result: `4 passed in 1.82s`

```text
python -m pytest tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py tests/telemetry/test_shadow_critical_event_journal.py tests/domains/test_watchdog_polling_fix.py tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k "trade_executed or hardening or shadow or terminal" -q
```
Result: `10 passed, 31 deselected in 4.28s`

```text
python -m pytest tests/domains/execution_position/test_execpos_max_hold_close_routed_v1.py -q
```
Result: `1 passed in 0.75s`

```text
python -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader().load_config(); print(f'shadow_journal.path={cfg.observability.shadow_journal.path}'); print(f'warm_state.path={cfg.domains.execution_position.event_dedup.warm_state.storage_path}'); print(f'warm_state.max_entries={cfg.domains.execution_position.event_dedup.warm_state.max_entries}'); print(f'event_dedup.ttl_ms={cfg.domains.execution_position.event_dedup.ttl_ms}')"
```
Result:
```text
shadow_journal.path=logs/shadow_critical_event_journal_v1.jsonl
warm_state.path=logs/execution_truth_warm_state_v1.json
warm_state.max_entries=2000
event_dedup.ttl_ms=86400000
```

### Example evidence
- exact identity restart hit produced `HARDENING:TRADE_EXECUTED_WARM_STATE_HIT`
- fresh exact identity produced `HARDENING:TRADE_EXECUTED_WARM_STATE_MISS`
- degraded identity produced `HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED` and no warm-state file
- corrupt snapshot produced `RESTORE:EXECUTION_TRUTH_WARM_STATE_LOAD_FAILED`

### Table E — Validation Matrix
| Scenario | Expected behavior | Proven by code? | Proven by test? | Notes |
|---|---|---:|---:|---|
| exact terminal fill survives restart in warm-state sense | duplicate exact fill suppressed after restart | Yes | Yes | dedicated restart warm-state test |
| distinct exact terminal fill remains allowed | new exact key delivered after restart | Yes | Yes | dedicated restart warm-state test |
| degraded identity remains unseeded | restart does not suppress degraded duplicate | Yes | Yes | dedicated restart warm-state test |
| load failure does not break flow | corrupt file logs and falls open | Yes | Yes | dedicated restart warm-state test |
| warm-state load/reset observable | restore events emitted | Yes | Yes | dedicated restart warm-state test |
| prior close hardening unchanged | non-`CMD:CLOSE` slice still passes | Yes | Yes | continuation slice still green |
| no broad drift in covered fill path | regression subset green | Yes | Yes | focused regression slice |

### Additional note
- `tests/domains/execution_position/test_execpos_max_hold_close_routed_v1.py` still emits the existing pytest unraisable warning about `ExecPosFSM._execute_decision` not being awaited. The test passes. This warning is outside the warm-state package scope.

---

## 12. Safety Assessment
This package is still narrow because it preserves only a bounded exact terminal fill identity cache across restart.

Why the blast radius is limited:
- the owner remains the existing `ExecutionTruthHardening` object,
- load happens only on the shared fill-suppression owner,
- only exact identities are seeded,
- degraded identities remain fail-open,
- no restore or hydrate logic was rewritten.

### FACTS
- warm-state is persisted as a bounded atomic JSON snapshot.
- load failure falls open to empty seed.
- close guard state remains process-local only.

### INFERENCES
- this improves restart continuity without creating a hidden second lifecycle truth system.

### ASSUMPTIONS
- the exact order-lifecycle identity remains sufficient for terminal fill continuity on active paths.

### UNKNOWNS
- whether future restart work will require a broader terminal order-state continuity surface.

---

## 13. Limitations
- Restart continuity is only for exact terminal fill identity.
- Degraded identities are still lost across restart.
- Close guard state is still process-local only.
- This package does not reconstruct missed order or position state.
- This package does not make restore canonical or replayable by itself.

---

## 14. Long-Term Goal Alignment
This package moves the system toward a canonical replayable truth plane by making recent terminal identity continuity:
- explicit,
- bounded,
- observable,
- restart-aware,
- and contract-driven.

It does **not** overclaim. The warm-state is a continuity cache, not canonical truth. That is the right direction for pre-replay stabilization.

---

## 15. Next Recommended Package
**Recommended next package:** terminal order-state continuity and restore-boundary audit.

Target scope:
- evaluate whether any terminal non-fill order identities should receive the same narrow restart continuity treatment,
- audit remaining forced-close producers only if they materially affect terminal continuity,
- keep replay and full restore redesign out of scope.

---

## REPORT Appendix
### Files changed
- `apps/reference/domains/execution_position/truth_hardening.py`
- `vfoundation/core/fsm_core.py`
- `apps/reference/config_models.py`
- `config/aurora/domains.yaml`
- `apps/reference/telemetry/shadow_journal.py`
- `config/aurora/observability.yaml`
- `tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py`
- `tests/domains/execution_position/test_execution_truth_continuation_non_cmd_close_identity_restart.py`
- `tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py`
- `tests/telemetry/test_shadow_critical_event_journal.py`
- `tests/domains/execution_position/conftest.py`
- `tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py`

### Key code snippets
#### Warm-state file payload
```python
payload = {
    "schema_version": "1.0.0",
    "state_type": "execution_truth_warm_state_v1",
    "generated_at_ms": int(now_ms),
    "retention_ms": int(self.fill_dedup_ttl_ms),
    "max_entries": int(self.warm_state_max_entries),
    "entries": [...],
}
```

#### Warm-state hit/miss observability
```python
if shadow_journal is not None and decision.warm_state_miss:
    shadow_journal.record_transition(
        event_name="HARDENING:TRADE_EXECUTED_WARM_STATE_MISS",
        ...
    )

if decision.warm_state_hit:
    shadow_journal.record_transition(
        event_name="HARDENING:TRADE_EXECUTED_WARM_STATE_HIT",
        ...
    )
```

#### Restart load outcome
```python
if is_bus_owner:
    load_result = hardening.load_warm_state()
    _record_warm_state_load_outcome(journal, load_result, hardening)
```

### Warm-state schema snippet
```json
{
  "schema_version": "1.0.0",
  "state_type": "execution_truth_warm_state_v1",
  "generated_at_ms": 1760000000000,
  "retention_ms": 86400000,
  "max_entries": 2000,
  "entries": [
    {
      "key": "trade_executed:BTCUSDT:order_id=7777:client_order_id=ENTRY-BTCUSDT-WS-1",
      "ts_ms": 1760000000000,
      "symbol": "BTCUSDT",
      "order_id": "7777",
      "client_order_id": "ENTRY-BTCUSDT-WS-1",
      "identity_quality": "order_lifecycle_contract_identity"
    }
  ]
}
```

### Example shadow records
```json
{"event_name":"RESTORE:EXECUTION_TRUTH_WARM_STATE_LOADED","event_origin_type":"restore","restore_marker":true,"payload_fragment":{"entries_loaded":1,"retention_ms":86400000,"max_entries":2000},"notes":["warm_state_seed_loaded","terminal_fill_exact_only"]}
```

```json
{"event_name":"HARDENING:TRADE_EXECUTED_WARM_STATE_HIT","source_path":"websocket:user_data_stream","notes":["restart_seeded_terminal_identity_hit","fill_key=trade_executed:BTCUSDT:order_id=7777:client_order_id=ENTRY-BTCUSDT-WS-1","order_lifecycle_contract_identity"]}
```

```json
{"event_name":"RESTORE:EXECUTION_TRUTH_WARM_STATE_LOAD_FAILED","event_origin_type":"restore","restore_marker":true,"notes":["warm_state_load_failed","fail_open_empty_seed"]}
```

### Table F — Non-Goals Matrix
| Non-goal | Why excluded |
|---|---|
| full replay engine | too broad and explicitly out of scope |
| full restore redesign | this package only adds continuity cache semantics |
| close guard persistence | different state basis, not terminal fill identity |
| degraded identity restart suppression | too risky without stronger contract inputs |
| FSM migration | explicitly out of scope |
