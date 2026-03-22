# REPORT — SHADOW ONLY INSTRUMENTATION AND CRITICAL EVENT JOURNAL

## 1. Executive Summary
Implemented a shadow-only, append-only critical event journal for the live decision-to-execution chain. The package adds a strict JSONL journal schema, a replaceable sink, central capture at `FSMCore.emit()`, owner-local transition capture for `ExecPosFSM`, `ManageFlowFSM`, `CloseFlowFSM`, `OrderIndex`, and `PositionTracking`, plus explicit restore/hydrate records.

Intentionally not changed:
- no routing changes
- no order sizing or risk changes
- no execution semantics changes
- no FSM migration
- no reducer/state ownership changes

Mergeability: `YES`, for the stated shadow-only scope.

## 2. Scope
Instrumented:
- central bus emission for critical events
- `ExecPosFSM.handle()` and `ExecPosFSM.hydrate()`
- `ManageFlowFSM.handle()`
- `CloseFlowFSM.handle()`
- `OrderIndex` reserve/upsert/attach/terminal/cancel transitions
- `PositionTracking.on_trade_executed()`
- `PositionTracking.load_snapshot()`

Intentionally untouched:
- business rule implementations
- adapter order placement semantics
- retry behavior
- watchdog logic
- websocket parsing logic
- domain ownership boundaries

## 3. Active Runtime Path Confirmed
FACTS:
- `decision_making.intent_builder` emits `EVT:TRADE_INTENT_PROPOSED` on the shared `FSMCore`.
- `ExecPosFSM` listens for `EVT:TRADE_INTENT_PROPOSED` and routes to `CMD:OPEN` / `CMD:CLOSE`.
- `ExecPosFSM.handle()` produces `DEC:OPEN` / `DEC:CLOSE` / `DEC:BATCH`.
- order lifecycle events flow through `FSMCore.emit()` as `EVT:ORDER_ACK`, `EVT:ORDER_REJECTED`, `EVT:ORDER_STATE_CHANGED`, `EVT:TRADE_EXECUTED`.
- `PositionTracking` consumes `EVT:TRADE_EXECUTED` and emits `EVT:PORTFOLIO_STATE_UPDATED`.
- `EPEventHandlers.on_portfolio_state_updated()` emits `EVT:EXPOSURE_SUMMARY_UPDATED`.
- restart reconstruction enters through `PositionTracking.load_snapshot()` and `ExecPosFSM.hydrate()`.

INFERENCE:
- These are the narrowest active choke points that preserve current ownership while maximizing causality coverage.

ASSUMPTION:
- Current runtime continues to use `FSMCore` as the shared event bus in production paths.

UNKNOWNS:
- Non-`FSMCore` side channels outside this chain are not journaled by this package.

## 4. Journal Schema
Implemented in `apps/reference/telemetry/shadow_journal.py`.

Design:
- strict Pydantic record model: `ShadowJournalRecord`
- versioned fields: `schema_version`, `instrumentation_version`
- append-only sequence counter per process
- deterministic field names
- compact `payload_fragment` instead of raw payload dumps

Table B — Journal Field Matrix

| Field | Required? | Source | Notes |
|---|---|---|---|
| `schema_version` | Yes | config / default | Record schema version |
| `instrumentation_version` | Yes | config / default | Package version |
| `record_type` | Yes | journal writer | `event` / `transition` / `restore` |
| `ts_ms` | Yes | runtime clock | Append timestamp |
| `sequence` | Yes | journal writer | Process-local append order |
| `event_name` | Yes | emit/transition site | Canonical `OP:VERB` |
| `op` | Yes | parsed from `event_name` | Supports `RESTORE:*` too |
| `verb` | Yes | parsed from `event_name` | Canonical verb |
| `source_component` | Yes | heuristics / explicit hook | Emitter or owner seam |
| `source_path` | Yes | heuristics / explicit hook | `decision:*`, `router:*`, `execution:*`, `restore:*`, etc. |
| `event_origin_type` | Yes | heuristics / explicit hook | `websocket`, `watchdog`, `restore`, `router`, `decision`, `execution`, `portfolio`, `unknown` |
| `rid` | Optional | envelope / payload | Primary request identity |
| `causation_rid` | Optional | payload / data_ref | Parent lineage when present |
| `symbol` | Optional | payload | Symbol identity |
| `order_id` | Optional | payload | Exchange order id |
| `client_order_id` | Optional | payload | Client order id |
| `position_id` | Optional | payload | Reserved for position truth |
| `lifecycle_id` | Optional | payload | Idempotent / lifecycle correlation |
| `strategy_id` | Optional | payload | Strategy identity |
| `side` | Optional | payload | BUY / SELL |
| `qty` | Optional | payload | Stringified |
| `price` | Optional | payload | Stringified |
| `truth_owner` | Optional | explicit hook | `ExecPosFSM`, `ManageFlowFSM`, `CloseFlowFSM`, `OrderIndex`, `PositionTracking` |
| `local_state_before` | Optional | snapshot helper | Read-only compact owner snapshot |
| `local_state_after` | Optional | snapshot helper | Read-only compact owner snapshot |
| `restore_marker` | Yes | explicit / heuristic | Exact on restore hooks |
| `suspected_duplicate` | Yes | heuristic | Cross-origin fill/state exposure |
| `duplicate_kind` | Optional | heuristic | Current value: `cross_origin_duplicate_exposure` |
| `duplicate_heuristic` | Yes | heuristic | Explicitly marks heuristic status |
| `repeated_close` | Yes | heuristic | Repeated `CMD:CLOSE` / `DEC:CLOSE` |
| `partial_identity` | Yes | heuristic | Symbol + rid/client id without order id |
| `instrumentation_failure` | Optional | journal writer | Buffered prior write failure surfaced on next success |
| `payload_fragment` | Yes | filtered payload | Safe compact fragment |
| `notes` | Yes | hook / heuristics | Marker annotations |

## 5. Storage / Sink
Sink:
- local append-only JSONL file
- configured at `observability.shadow_journal.path`
- default path: `logs/shadow_critical_event_journal_v1.jsonl`

Append-only guarantees:
- opens file in append mode only
- one JSON object per line
- no in-place mutation or rewrite path

Failure behavior:
- instrumentation is fail-open
- write failures are logged
- the failure marker is buffered and injected into the next successful journal record via `instrumentation_failure`

## 6. Instrumentation Points Added
Table A — Instrumentation Point Matrix

| File | Function/Handler | Event/Transition | Source classification | Truth owner | Before/After captured? | Duplicate marker? | Restore marker? | Risk |
|---|---|---|---|---|---|---|---|---|
| `vfoundation/core/fsm_core.py` | `FSMCore.emit` | Critical bus events | heuristic by event/why | None | No | Yes | heuristic/exact | Low |
| `apps/reference/domains/execution_position/fsm.py` | `handle` | `CMD:OPEN`, `CMD:CLOSE`, routed execution events | `execution:execpos_handle` | `ExecPosFSM` | Yes | Via shared journal | No | Low |
| `apps/reference/domains/execution_position/fsm.py` | `hydrate` | `RESTORE:EXECUTION_POSITION_HYDRATE` | `restore:execution_position_hydrate` | `ExecPosFSM` | Yes | No | Yes | Low |
| `apps/reference/domains/execution_position/fsm_manage.py` | `handle` | manage-flow critical transitions | `execution:manage_flow_handle` | `ManageFlowFSM` | Yes | Via shared journal | No | Low |
| `apps/reference/domains/execution_position/fsm_close.py` | `handle` | close-flow critical transitions | `execution:close_flow_handle` | `CloseFlowFSM` | Yes | Repeated close via shared journal | No | Low |
| `apps/reference/domains/execution_position/order_index.py` | reserve/upsert/attach/mark/cancel | order truth transitions | `execution:order_index` | `OrderIndex` | Yes | No | No | Low |
| `apps/reference/domains/position_tracking/position_tracking.py` | `on_trade_executed` | `EVT:TRADE_EXECUTED` local truth update | `portfolio:on_trade_executed` | `PositionTracking` | Yes | Via shared journal | No | Low |
| `apps/reference/domains/position_tracking/position_tracking.py` | `load_snapshot` | `RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD` | `restore:position_tracking_snapshot_load` | `PositionTracking` | Yes | No | Yes | Low |

Why these points were chosen:
- `FSMCore.emit()` captures live envelope causality without changing business code.
- owner `handle()` / `load_snapshot()` / `hydrate()` seams capture local truth before/after where bus-only capture cannot.
- `OrderIndex` instrumentation captures order-truth mutations that never traverse the bus.

What they capture:
- emission order
- critical identity
- owner-local truth transitions
- restore/hydrate reconstruction points
- duplicate/repeated-close heuristics

What they do not prove:
- end-to-end exchange truth correctness
- replay completeness across process restarts
- exact websocket vs watchdog origin for every legacy event when upstream metadata is absent

Why safer than invasive alternatives:
- no message payload mutation
- no new business callbacks
- no replacement of existing emit/handle owners
- no cross-domain rewiring

## 7. Duplicate / Restore / Close Exposure Flags
`suspected_duplicate`
- Type: heuristic
- Trigger: same `EVT:TRADE_EXECUTED` or `EVT:ORDER_STATE_CHANGED` identity seen from `websocket` and `watchdog`
- Meaning: possible double exposure of the same fill/state event across WS and REST/watchdog paths

`repeated_close`
- Type: heuristic
- Trigger: repeated `CMD:CLOSE` or `DEC:CLOSE` on the same `rid` or symbol within 60 seconds
- Meaning: possible repeated close emission exposure

`restore_marker`
- Type: exact
- Trigger: `PositionTracking.load_snapshot()` and `ExecPosFSM.hydrate()`
- Meaning: state is reconstructed from startup restore/hydrate path, not live event progression

`partial_identity`
- Type: heuristic
- Trigger: symbol present with `rid` and/or `client_order_id` but missing `order_id`
- Meaning: traceability is incomplete; correlation may still be possible but not exact

`instrumentation_failure`
- Type: exact for surfaced buffered failure
- Trigger: a prior journal write failed and a later write succeeded
- Meaning: observability degradation occurred, trading path continued

## 8. Tests Added / Updated
Added:
- `tests/telemetry/test_shadow_critical_event_journal.py`

Coverage:
- append-only writes + repeated-close marker
- fail-open write failure behavior + buffered failure surfacing
- duplicate fill exposure heuristic
- close-flow before/after owner snapshots
- `ExecPosFSM.hydrate()` restore record
- `PositionTracking.load_snapshot()` restore record

No existing tests were modified.

## 9. Validation Evidence
Commands run:

```powershell
python -m py_compile apps/reference/telemetry/shadow_journal.py apps/reference/domains/execution_position/fsm.py apps/reference/domains/execution_position/fsm_manage.py apps/reference/domains/execution_position/fsm_close.py apps/reference/domains/execution_position/order_index.py apps/reference/domains/position_tracking/position_tracking.py vfoundation/core/fsm_core.py tests/telemetry/test_shadow_critical_event_journal.py
```

Result:
- success

```powershell
python -m pytest tests/telemetry/test_shadow_critical_event_journal.py -q
```

Result:
- `5 passed in 0.99s`

```powershell
python -m pytest tests/telemetry/test_shadow_critical_event_journal.py tests/domains/execution_position/test_close_flow_cmd_close_always_emits_dec_close.py tests/domains/execution_position/test_order_index_contracts_v1.py -q
```

Result:
- `12 passed in 2.32s`

```powershell
python -c "from apps.reference.config_loader import ConfigLoader; ConfigLoader().load_config(); print('config_load_ok')"
```

Result:
- `config_load_ok`

Smoke/manual sample:
- generated `.tmp/shadow_journal_sample.jsonl`
- sample showed:
  - first `CMD:CLOSE` record
  - second `CMD:CLOSE` with `repeated_close=true`
  - restore record for `RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD`

Example journal samples:

```json
{"event_name":"CMD:CLOSE","event_origin_type":"router","rid":"sample-close","symbol":"BTCUSDT","repeated_close":false}
{"event_name":"CMD:CLOSE","event_origin_type":"router","rid":"sample-close","symbol":"BTCUSDT","repeated_close":true,"notes":["repeated_close_marker_heuristic"]}
{"event_name":"RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD","event_origin_type":"restore","truth_owner":"PositionTracking","restore_marker":true}
```

Table C — Validation Matrix

| Scenario | Expected journal behavior | Proven by code? | Proven by test? | Notes |
|---|---|---|---|---|
| Critical bus event emit | One record per critical event | Yes | Yes | `FSMCore.emit` hook |
| Append-only sink | New line per record, no mutation | Yes | Yes | JSONL append mode |
| Write failure | Trading/event path continues | Yes | Yes | failure buffered and surfaced |
| Duplicate WS/watchdog fill exposure | `suspected_duplicate=true` | Yes | Yes | heuristic |
| Repeated close exposure | `repeated_close=true` | Yes | Yes | heuristic |
| ExecPos hydrate | explicit restore record | Yes | Yes | `RESTORE:EXECUTION_POSITION_HYDRATE` |
| PositionTracking snapshot load | explicit restore record | Yes | Yes | `RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD` |
| Owner-local before/after snapshots | transition records include compact state | Yes | Yes | `CloseFlowFSM`, `ExecPosFSM`, `PositionTracking` tested; `ManageFlowFSM`, `OrderIndex` covered by code + existing contract tests |
| Config wiring | typed config field loads | Yes | Yes | config load smoke |

## 10. Safety Assessment
FACTS:
- journal writes go to a separate JSONL sink
- write failures are caught and logged
- no emit payloads were mutated
- no handler return values were changed
- no execution/risk/decision branches were rewritten

INFERENCE:
- The package is shadow-only because the new code only observes and appends records; it does not feed any new signal back into business logic.

ASSUMPTIONS:
- file append latency remains acceptable for the current critical event volume

UNKNOWNS:
- sustained live-volume overhead is not yet benchmarked with production traffic

Blast radius that remains:
- additional file I/O on critical paths
- small extra CPU for snapshot extraction and heuristics
- process-local sequence only, not cluster-global ordering

## 11. Limitations
- This is not a replay engine.
- This is not a canonical global WAL.
- Duplicate detection is heuristic, not an exchange-truth proof.
- Repeated close detection is heuristic and process-local.
- Some source classification remains heuristic when upstream legacy events do not carry explicit provenance.
- Restore coverage is explicit for snapshot load and hydrate seams only; it does not prove replay completeness.

Table D — Non-Goals Matrix

| Non-goal | Why excluded from this package |
|---|---|
| FSM migration | Explicitly out of scope; would change ownership and blast radius |
| Business logic refactor | Would confound observability evidence with behavior changes |
| Canonical truth-plane cutover | This package is only a shadow journal |
| Full contract redesign | Additive-only scope |
| Historical backfill | Not required for runtime observability validation |
| Replay engine | Separate package with different risk profile |

## 12. Next Recommended Package
`PRE_STABILIZATION_DUPLICATE_FILL_AND_REPEATED_CLOSE_HARDENING`

Rationale:
- the journal now makes duplicate fill exposure and repeated close exposure visible
- the next safe package should consume this evidence to harden exact dedup and close idempotency, without combining that work with broader migration

## 3. REPORT Appendix
Files changed:
- `apps/reference/telemetry/shadow_journal.py`
- `apps/reference/config_models.py`
- `config/aurora/observability.yaml`
- `vfoundation/core/fsm_core.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/fsm_close.py`
- `apps/reference/domains/execution_position/order_index.py`
- `apps/reference/domains/position_tracking/position_tracking.py`
- `tests/telemetry/test_shadow_critical_event_journal.py`

Key code snippets:

```python
shadow_journal.record_bus_emit(
    event_name=event_name,
    payload=payload,
    why=why,
    data_ref=data_ref,
    rid=rid,
)
```

```python
journal.record_transition(
    event_name="RESTORE:EXECUTION_POSITION_HYDRATE",
    source_component="execution_position.fsm",
    source_path="restore:execution_position_hydrate",
    event_origin_type="restore",
    truth_owner="ExecPosFSM",
    before=before,
    after=snapshot_execpos_state(self, symbol),
    restore_marker=True,
)
```

```python
record = ShadowJournalRecord(
    schema_version=self.schema_version,
    instrumentation_version=self.instrumentation_version,
    record_type="event",
    event_name=event_name,
    source_component=source_component,
    source_path=source_path,
    event_origin_type=origin_type,
    suspected_duplicate=suspected_duplicate,
    repeated_close=repeated_close,
)
```

Schema snippet:

```python
class ShadowJournalRecord(BaseModel):
    schema_version: str
    instrumentation_version: str
    record_type: str
    ts_ms: int
    sequence: int
    event_name: str
    op: str
    verb: str
    source_component: str
    source_path: str
    event_origin_type: str
    ...
```

Sample record(s):

```json
{"event_name":"CMD:CLOSE","rid":"sample-close","symbol":"BTCUSDT","event_origin_type":"router","repeated_close":true}
{"event_name":"RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD","truth_owner":"PositionTracking","restore_marker":true}
```
