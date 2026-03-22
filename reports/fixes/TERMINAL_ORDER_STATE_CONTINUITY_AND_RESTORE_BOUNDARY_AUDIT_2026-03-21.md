# REPORT - TERMINAL ORDER STATE CONTINUITY AND RESTORE BOUNDARY AUDIT

## 1. Executive Summary
This audit inspected the active runtime surfaces for terminal non-fill order states and the current restart-truth boundary after exact terminal fill warm-state continuity.

What is now clear:
- `CANCELED`, `EXPIRED`, and generic `REJECTED` are active runtime states.
- Their active effects are mostly idempotent cleanup, tracking, and monitoring, not the same high-risk double-application surface that justified exact terminal fill continuity.
- The semantically important reject path is `EVT:ORDER_REJECTED`, but it is not yet a strong restart-continuity candidate because the contract remains schema-null and its runtime meaning is mixed between maker-only rejects and adapter/business failures.
- Current architecture already has a workable boundary:
  - warm-state continuity for bounded recent exact terminal identity,
  - restore/hydrate for current runtime working state,
  - future replay/canonical truth for causal lifecycle reconstruction.

Recommended next package:
- `identity contract hardening first`, specifically for `EVT:ORDER_REJECTED` and `EVT:ORDER_STATE_CHANGED`, before adding any new non-fill terminal restart continuity.

## 2. Scope
Inspected active surfaces:
- terminal non-fill producers in `binance_ws_client.py` and `watchdog.py`
- execution-position consumers in `fsm.py`, `exposure_manager.py`, `order_index.py`, `fsm_close.py`
- restart attach and hydrate boundaries in `truth_hardening.py`, `main.py`, `position_tracking.py`
- contract metadata in `verb_registry_v1.yaml` and domain dictionaries
- focused tests for watchdog cancel handling, order-rejected import, and recovery ordering

Intentionally not re-audited:
- full execution lifecycle
- broad restore architecture
- full replay semantics
- FSM migration candidates
- unrelated strategy logic

## 3. Active Terminal Non-Fill Paths Confirmed
### Runtime paths
```text
Binance WS ORDER_TRADE_UPDATE
  -> standardized status CANCELED / REJECTED / EXPIRED
  -> OrderIndex.mark_terminal(order_ref)
  -> EVT:ORDER_STATE_CHANGED

Binance WS maker-only GTX entry reject
  -> EXPIRED + GTX + entry + 0 fill
  -> EVT:ORDER_REJECTED

Watchdog REST polling
  -> CANCELED / REJECTED / EXPIRED
  -> EVT:ORDER_STATE_CHANGED
  -> local meta['terminal'] = True

ExecPosFSM
  -> ORDER_STATE_CHANGED
  -> ExposureManager.handle_cancel_event()
  -> best-effort pending bracket cleanup
  -> best-effort OrderIndex.mark_terminal()
  -> EVT:EXPOSURE_SUMMARY_UPDATED
```

### FACTS
- `binance_ws_client.py` emits `EVT:ORDER_STATE_CHANGED` for terminal non-fill statuses and `EVT:ORDER_REJECTED` only for maker-only reject classification.
- `watchdog.py` emits `EVT:ORDER_STATE_CHANGED` for `CANCELED`, `REJECTED`, and `EXPIRED`, and already guards repeated local processing with `meta['terminal']`.
- `fsm_close.py` explicitly disables autonomous close-on-`REJECTED` and close-on-`EXPIRED` rules.
- `exposure_manager.py` handles cancel-like events mostly by cleanup and best-effort terminal marking.

### INFERENCES
- The generic terminal non-fill surface is active, but it is not currently a shared high-risk state-application seam comparable to `EVT:TRADE_EXECUTED`.
- The strategy-significant reject seam is semantic and selective, not a generic terminal-order restart seam.

### ASSUMPTIONS
- Current exchange-terminal non-fill events do not mutate position truth directly after restart the way a duplicated fill can.

### UNKNOWNS
- Whether future runtime paths will make `ORDER_STATE_CHANGED` materially more stateful than its current cleanup/telemetry role.

## 4. Terminal State Eligibility Criteria
A terminal state is eligible for narrow restart continuity only if all of the following are strong enough:

1. Identity quality: cross-path identity is exact or very close to exact.
2. Restart value: continuity materially reduces a real correctness risk, not just telemetry discontinuity.
3. Blast radius: suppression cannot silently block legitimate new lifecycle activity.
4. Observability quality: suppression/hit/miss can remain explicit and interpretable.
5. Truth confusion risk: the cache does not start acting like lifecycle reconstruction.
6. Boundary fit: the state belongs in bounded continuity, not restore/hydrate or future replay.

If these criteria are not met together, continuity should fail closed.

## 5. Terminal Non-Fill State Classification
### Table A - Terminal State Classification Matrix
| Terminal state | Active runtime path? | Identity quality | Restart value | Truth confusion risk | Classification | Notes |
|---|---|---|---|---|---|---|
| `CANCELED` | Yes | Degraded but usable | Low | Medium | `LOW VALUE / DO NOT CONTINUE` | Current effect is mostly cleanup plus terminal marking; watchdog already has local idempotency. |
| `EXPIRED` | Yes | Degraded but usable | Low | Medium | `LOW VALUE / DO NOT CONTINUE` | Generic expired events converge into `ORDER_STATE_CHANGED`; no strong restart-sensitive consumer found. |
| `REJECTED` via generic `ORDER_STATE_CHANGED` | Yes | Degraded but usable | Low | Medium | `LOW VALUE / DO NOT CONTINUE` | Treated like cancel-like state cleanup, not a high-risk truth seam. |
| `ORDER_REJECTED` semantic path | Yes | Mixed | Medium | High | `NOT ELIGIBLE YET` | Operationally meaningful for retry logic, but contract is schema-null and semantics are mixed. |

### Table C - Identity Sufficiency Matrix
| State | Candidate fields | Exact / degraded / weak | Sufficient for continuity? | Notes |
|---|---|---|---|---|
| `CANCELED` | `symbol`, `orderId`, `client_order_id`, `status` | Degraded | No | Watchdog path often has `rid=None`; contract symmetry is incomplete. |
| `EXPIRED` | `symbol`, `orderId`, `client_order_id`, `status`, sometimes GTX context | Degraded | No | Generic expire is weak; maker-only semantic reject should not be merged into generic expire continuity. |
| `REJECTED` via `ORDER_STATE_CHANGED` | `symbol`, `orderId`, `client_order_id`, `status` | Degraded | No | Identity may be enough to dedupe a notification, but restart value is not strong enough. |
| `ORDER_REJECTED` | `symbol`, `rid`, `reason`, `reason_code`, `orderId`, `clientOrderId` | Mixed | Not yet | Semantics are stronger than identity discipline right now; schema and producer consistency should come first. |

### State notes
#### `CANCELED`
FACTS:
- WS and watchdog both surface it.
- Downstream handling is mostly cleanup and `OrderIndex.mark_terminal()`.

INFERENCES:
- Restart continuity would mostly protect repeated cleanup, which is already low-risk.

ASSUMPTIONS:
- Duplicate `EXPOSURE_SUMMARY_UPDATED` after restart is operationally less severe than duplicate fill application.

UNKNOWNS:
- Whether hidden downstream consumers outside the inspected path assign stronger semantics to cancel continuity.

Final classification: `LOW VALUE / DO NOT CONTINUE`.

#### `EXPIRED`
FACTS:
- Generic expired path is `ORDER_STATE_CHANGED`.
- Autonomous close-on-expired is disabled in `CloseFlowFSM`.

INFERENCES:
- Generic expire continuity would add cache complexity without reducing a comparable correctness risk.

ASSUMPTIONS:
- Expired-after-restart is mostly observational unless paired with a stronger semantic contract.

UNKNOWNS:
- Whether future timeout policy changes will elevate restart value.

Final classification: `LOW VALUE / DO NOT CONTINUE`.

#### `REJECTED`
FACTS:
- Generic reject appears on `ORDER_STATE_CHANGED`.
- Maker-only reject uses `ORDER_REJECTED`.
- `md_amr_handler.py` has explicit reject-reason normalization and retry behavior for maker-only/post-only cases.

INFERENCES:
- The important seam is not the terminal status alone, but the semantic reject contract.

ASSUMPTIONS:
- Restart continuity for semantic reject should wait until reject identity and contract are cleaner.

UNKNOWNS:
- Whether non-maker reject producers will become more standardized soon.

Final classification:
- generic `REJECTED`: `LOW VALUE / DO NOT CONTINUE`
- semantic `ORDER_REJECTED`: `NOT ELIGIBLE YET`

## 6. Restore Boundary Model
### Table B - Restore Boundary Matrix
| Layer | Allowed to own | Not allowed to own | Why |
|---|---|---|---|
| warm-state continuity | bounded recent exact identity continuity for narrow high-risk terminal truths | lifecycle reconstruction, semantic state inference, canonical lineage | Its role is restart re-entry reduction, not truth reconstruction. |
| restore/hydrate | current runtime working state from snapshots, WAL replay, and hydrate inputs | claims of full causal truth, exact terminal event lineage continuity | Restore rebuilds working state but remains lossy. |
| future replay/canonical truth | causal reconstruction, canonical lineage, broader lifecycle reconstitution | implicit heuristics hidden in local caches | Replay-capable truth must own the hard reconstruction problem explicitly. |

### Boundary definition
Warm-state continuity is allowed to preserve:
- bounded recent exact identity continuity
- only where duplicate re-entry risk is already proven high
- only where the continuity owner is explicit and observable

Warm-state continuity is not allowed to preserve:
- non-fill terminal semantic meaning by guesswork
- lifecycle phase reconstruction
- strategy-side decision implications

Restore/hydrate is allowed to reconstruct:
- current positions
- current FSM working state
- snapshot-plus-WAL working context

Restore/hydrate is not allowed to claim:
- full terminal order lineage continuity
- complete causal order/fill history

Future replay/canonical truth must eventually own:
- causal sequencing
- canonical order/fill lineage
- broader lifecycle reconstitution across restart

### FACTS
- `main.py` restores snapshot state, replays WAL after snapshot, then hydrates execution FSMs from restored positions.
- current warm-state file contains only exact terminal fill identities.
- domain metadata still says `OrderIndex` is runtime SSOT for order tracking.

### INFERENCES
- Adding more terminal-order warm-state entries now would blur the line between bounded continuity and lifecycle reconstruction.

### ASSUMPTIONS
- Current restart gaps outside exact terminal fills are better addressed by contract/boundary hardening before adding more caches.

### UNKNOWNS
- What the future replay-capable truth plane will use as canonical order-state lineage input.

## 7. Files Inspected
| file | why inspected | relevance |
|---|---|---|
| `apps/reference/adapters/binance_ws_client.py` | confirm active terminal non-fill producer behavior | primary WS producer for `ORDER_STATE_CHANGED` and maker-only `ORDER_REJECTED` |
| `apps/reference/domains/execution_position/watchdog.py` | confirm REST fallback terminal behavior | fallback producer and existing local idempotency |
| `apps/reference/domains/execution_position/fsm.py` | confirm consumer routing | shows `ORDER_STATE_CHANGED` reaches cancel-like handling |
| `apps/reference/domains/execution_position/exposure_manager.py` | inspect downstream side effects | confirms cleanup-oriented behavior |
| `apps/reference/domains/execution_position/order_index.py` | inspect terminal marking semantics | shows repeated `mark_terminal()` is low-risk |
| `apps/reference/domains/execution_position/fsm_close.py` | check close-on-reject/expire behavior | confirms disabled autonomous close rules |
| `apps/reference/domains/execution_position/truth_hardening.py` | inspect current warm-state scope | proves exact terminal fill only |
| `apps/reference/main.py` | inspect restore/hydrate boundary | confirms restore of working state, not terminal lineage |
| `apps/reference/domains/position_tracking/position_tracking.py` | inspect snapshot restore role | working-state restore surface |
| `apps/reference/domains/decision_making/md_amr_handler.py` | inspect semantic reject consumer | shows meaningful reject-specific behavior |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | inspect `ORDER_STATE_CHANGED` consumer | shows status-tracking rather than canonical truth behavior |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | inspect contract maturity | `TRADE_EXECUTED` typed; `ORDER_REJECTED` and `ORDER_STATE_CHANGED` schema-null |
| `apps/reference/domains/execution_position/domain_dict.json` | inspect domain ownership notes | confirms `OrderIndex` runtime SSOT note |

## 8. Tests Inspected / Executed
Executed:
- `tests/domains/execution_position/test_watchdog.py`
  - proves watchdog emits `EVT:ORDER_STATE_CHANGED` for canceled orders and includes `rid=None`
- `tests/domains/decision_making/test_event_import_order_rejected.py`
  - proves `ORDER_REJECTED` remains a real semantic input for decision-making logic
- `tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py`
  - proves terminal fill ordering and cancel-related recovery paths are covered in focused recovery tests

Inspected:
- `tests/domains/execution_position/test_restart_seeded_execution_truth_warm_state.py`
  - confirms the existing restart continuity scope is exact terminal fills only

## 9. Validation Evidence
### Commands run
```powershell
python -m pytest tests/domains/execution_position/test_watchdog.py -k cancelled -q
python -m pytest tests/domains/decision_making/test_event_import_order_rejected.py -q
python -m pytest tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k "trade_executed_marks_order_index_terminal or cancel" -q
```

### Results
```text
tests/domains/execution_position/test_watchdog.py
  1 passed, 11 deselected

tests/domains/decision_making/test_event_import_order_rejected.py
  4 passed

tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py
  8 passed, 22 deselected
```

### Runtime/log evidence
- `logs/execution_truth_warm_state_v1.json` currently stores exact terminal fill keys only.
- `logs/order_log_v1.jsonl` shows many `ORDER_REJECTED` entries are decision-making safety denials, while execution-position `ORDER_REJECTED` appears as a narrower semantic path such as maker-only reject or adapter failure.
- No runtime evidence from the inspected logs showed a high-confidence restart correctness failure driven by missing `CANCELED` or generic `EXPIRED` warm-state continuity.

### Table D - Validation Matrix
| Scenario / question | Proven by code? | Proven by test? | Runtime proof? | Notes |
|---|---|---|---|---|
| non-fill terminal states are active | Yes | Yes | Partial | WS and watchdog producer paths confirmed. |
| watchdog non-fill path already has local idempotency | Yes | Yes | No | `meta['terminal']` guard is explicit. |
| generic non-fill consumers are mostly cleanup-oriented | Yes | Partial | No | `ExposureManager` and `OrderIndex` are low-risk/idempotent. |
| `ORDER_REJECTED` has semantic strategy impact | Yes | Yes | Partial | DM tests prove consumer behavior; logs show live reject records. |
| current warm-state scope is exact terminal fills only | Yes | Yes | Yes | code, tests, and live warm-state file agree. |
| restore/hydrate is not canonical lifecycle replay | Yes | No | Partial | `main.py` restore flow rebuilds working state only. |

### Table E - Non-Goals Matrix
| Non-goal | Why excluded |
|---|---|
| adding new terminal-state warm-state entries now | audit found insufficient value/contract maturity |
| redesigning restore/hydrate | outside narrow boundary-definition scope |
| building replay | explicitly out of scope |
| migrating FSMs | explicitly out of scope |
| broad contract cleanup | only the next narrow recommendation, not this package |

## 10. Safety Assessment
The recommendation is narrow and safe because it does not expand runtime continuity behavior on weak evidence.

What this audit supports safely:
- keep exact terminal fill continuity
- stop short of non-fill terminal continuity sprawl
- harden contracts and boundaries before adding more restart-preserved state

What blast radius remains:
- non-fill terminal event identity is still inconsistent across paths
- restore remains lossy by design
- strategy consumers still rely on schema-null reject/state-change contracts

## 11. Limitations
This audit does not settle:
- whether a future strongly-typed `ORDER_REJECTED` contract would justify a narrow continuity slice later
- whether future exchange adapters will provide stronger non-fill terminal identity
- how a future replay-capable truth plane should canonicalize order terminal lineage
- every downstream use of `ORDER_STATE_CHANGED` outside the inspected active path

## 12. Recommended Next Package
`IDENTITY CONTRACT HARDENING FOR TERMINAL NON-FILL ORDER EVENTS`

Scope recommendation:
- add explicit schemas and contract discipline for `EVT:ORDER_REJECTED` and `EVT:ORDER_STATE_CHANGED`
- align cross-path identity fields between WS and watchdog producers
- make semantic reject categories explicit where they matter operationally
- do not add restart continuity yet

Why this should come next:
- it improves truth discipline without creating another partial cache
- it reduces ambiguity at the exact seam that would otherwise be dangerous to continuity-cache
- it prepares a later decision on whether any non-fill terminal state ever deserves bounded restart continuity

## REPORT Appendix
### Key code references
- `apps/reference/adapters/binance_ws_client.py`
- `apps/reference/domains/execution_position/watchdog.py`
- `apps/reference/domains/execution_position/exposure_manager.py`
- `apps/reference/domains/execution_position/order_index.py`
- `apps/reference/domains/execution_position/fsm_close.py`
- `apps/reference/domains/execution_position/truth_hardening.py`
- `apps/reference/main.py`
- `apps/reference/dictionaries/verb_registry_v1.yaml`

### Sample evidence snippets
```text
Warm-state file:
  trade_executed:BTCUSDT:order_id=12345:client_order_id=ENTRY-BTCUSDT-1

Watchdog cancel payload test:
  {"orderId": "o2", "symbol": "BTC", "status": "CANCELED", "client_order_id": "c1", "rid": None}

Verb registry:
  ORDER_REJECTED -> schema: null
  ORDER_STATE_CHANGED -> schema: null
  TRADE_EXECUTED -> schema: apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
```

### State classification notes
- Exact terminal fill continuity remains justified because duplicate fill re-entry mutates downstream truth.
- Generic non-fill terminal state continuity is not justified yet because current restart value is weak relative to added truth confusion.
- Semantic reject continuity should wait for stronger contract discipline first.
