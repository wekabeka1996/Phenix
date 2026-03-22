# REPORT — IDENTITY_CONTRACT_HARDENING_FOR_TERMINAL_NON_FILL_ORDER_EVENTS

## 1. Objective
Implement a narrow contract-hardening package for:
- `EVT:ORDER_REJECTED`
- terminal non-fill subset of `EVT:ORDER_STATE_CHANGED`

The package goal was to reduce contract drift, strengthen canonical identity, make reject/cancel/expire semantics explicit, preserve compatibility visibly, and avoid warm-state expansion, replay work, restore redesign, or FSM migration.

## 2. Scope actually executed
Touched:
- active producer paths in `binance_ws_client.py`, `watchdog.py`, `open_executor.py`, and `fsm.py`
- shared compatibility seam in `vfoundation/core/fsm_core.py`
- reject consumer normalization preference in `md_amr_handler.py`
- shadow payload fragment capture in `shadow_journal.py`
- registry/schema entries in `verb_registry_v1.yaml`
- focused tests for watchdog, WS maker-only reject, consumer compatibility, and new terminal-order contract helpers

Intentionally not touched:
- warm-state continuity
- restart behavior
- replay or hydrate design
- broad `ORDER_STATE_CHANGED` redesign
- FSM migration
- business routing, sizing, execution, or risk behavior

## 3. Evidence base
Files inspected:
- `apps/reference/adapters/binance_ws_client.py`
- `apps/reference/domains/execution_position/watchdog.py`
- `apps/reference/domains/execution_position/open_executor.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/intent_boundary_audit.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/telemetry/shadow_journal.py`
- `vfoundation/core/fsm_core.py`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `apps/reference/domains/execution_position/domain_dict.json`
- `apps/reference/domains/decision_making/domain_dict.json`

Tests executed:
- `tests/domains/execution_position/test_terminal_non_fill_order_contracts.py`
- `tests/domains/execution_position/test_watchdog.py`
- `tests/domains/decision_making/test_order_rejected_payload_normalization.py`
- `tests/domains/decision_making/test_event_import_order_rejected.py`
- `tests/integration/test_ep01_5_ws_expired_maker_reject.py`
- `tests/telemetry/test_shadow_critical_event_journal.py`

Search/grep evidence:
- producer/consumer search for `EVT:ORDER_REJECTED`
- producer/consumer search for `EVT:ORDER_STATE_CHANGED`
- canonical field search for `canonical_identity_key`, `reject_reason_normalized`, `terminal_state_kind`, `compatibility_aliases_retained`

Runtime/manual trace used:
- compatibility smoke through schema-initialized `FSMCore.emit()`

## 4. Active runtime paths reconfirmed
### 4.1 `EVT:ORDER_REJECTED`
| producer module/function | emitted verb | emitted payload fields at source | actual runtime meaning | downstream consumer(s) | fields read by consumer(s) | aliases/drift | identity available | reason available | status semantics |
|---|---|---|---|---|---|---|---|---|---|
| `binance_ws_client.py::_handle_order_trade_update()` | `EVT:ORDER_REJECTED` | `symbol`, `status`, `rid`, `clientOrderId`, `client_order_id`, `exchangeOrderId`, `orderId`, `side`, `order_type`, `qty`, `quantity`, `price`, `time_in_force`, `ts_ms`, `reason`, `fallback` | maker-only GTX reject on entry path | `md_amr_handler`, `intent_boundary_audit`, monitoring | `symbol`, reject reason | camel/snake id aliases; `reason` field only | exact: symbol + orderId + clientOrderId + rid | `reason=MAKER_ONLY_REJECT` | `status=EXPIRED` at source, but semantic event is reject |
| `open_executor.py` instrument-config / qty / order-policy reject paths | `EVT:ORDER_REJECTED` | `symbol`, `side`, `raw_qty`, `reason`, `details` plus `rid` on envelope | execution-stage reject before successful order working state | `md_amr_handler`, monitoring | `symbol`, reject reason | no order ids on many paths | weak: symbol + rid | `reason` only | reject semantics only |
| `open_executor.py::_place_limit_entry()` | `EVT:ORDER_REJECTED` | `symbol`, `side`, `reason`, `error_code` plus `rid` on envelope | exchange-level maker-only reject caught on submit path | `md_amr_handler`, monitoring | `symbol`, reject reason | no order ids in this local emit path | weak: symbol + rid | `reason` only | reject semantics only |
| `fsm.py` adapter error path | `EVT:ORDER_REJECTED` | `symbol`, `side`, `reason_code`, `reason_text`, `exception_class`, `ts_ms` plus `rid` on envelope | execution failure surfaced as reject event | monitoring, some downstream audit paths | `symbol`, reason fields | `reason_code` / `reason_text` shape differs from `reason` | weak: symbol + rid | `reason_code + reason_text` | reject semantics only |

### 4.2 terminal non-fill `EVT:ORDER_STATE_CHANGED`
| producer module/function | emitted verb | emitted payload fields at source | actual runtime meaning | downstream consumer(s) | fields read by consumer(s) | aliases/drift | identity available | reason available | status semantics |
|---|---|---|---|---|---|---|---|---|---|
| `binance_ws_client.py::_handle_order_trade_update()` | `EVT:ORDER_STATE_CHANGED` | `symbol`, `status`, `rid`, `idempotent_key`, `clientOrderId`, `client_order_id`, `exchangeOrderId`, `orderId`, `side`, `order_type`, `qty`, `quantity`, `price`, `time_in_force`, `ts_ms` | generic order state change; terminal non-fill when status is `CANCELED`, `REJECTED`, or `EXPIRED` | `mean_reversion_handler`, `md_amr_handler`, `intent_boundary_audit`, monitoring | mostly `symbol`, `status` | richer than watchdog; camel/snake aliases | exact on WS terminal path | none normally | status carries meaning |
| `watchdog.py::_poll_order_statuses()` | `EVT:ORDER_STATE_CHANGED` | `orderId`, `symbol`, `status`, `client_order_id`, `rid=None` | watchdog-detected terminal non-fill order state | `mean_reversion_handler`, `md_amr_handler`, `intent_boundary_audit`, monitoring | mostly `symbol`, `status` | thinner than WS; no `clientOrderId`, no `event_ts_ms`, no semantic marker before patch | degraded/exact locally if orderId + client_order_id present; weak lineage because `rid=None` | none | status carries meaning |

### FACTS
- active producer surfaces are limited and identifiable
- `ORDER_REJECTED` is not a single-source contract today
- terminal non-fill `ORDER_STATE_CHANGED` is produced by WS and watchdog
- active consumers mostly read `symbol`, `status`, and reject reason fields

### INFERENCES
- one shared normalization seam is safer than widening alias handling in every consumer

### ASSUMPTIONS
- current active consumers are compatible with additive fields

### UNKNOWNS
- whether there are non-active producer paths that still emit older shapes not covered by current tests

## 5. Facts
1. `verb_registry_v1.yaml` had `schema: null` for both targeted verbs before this package.
2. `binance_ws_client.py` emits `EVT:ORDER_REJECTED` only on the maker-only reject branch.
3. `binance_ws_client.py` emits `EVT:ORDER_STATE_CHANGED` for other order state changes, including terminal non-fill statuses.
4. `watchdog.py` emits `EVT:ORDER_STATE_CHANGED` with a thinner payload than the WS path.
5. `open_executor.py` emits `EVT:ORDER_REJECTED` from multiple execution-stage reject branches with different reason shapes.
6. `fsm.py` emits `EVT:ORDER_REJECTED` on adapter execution failure with `reason_code` and `reason_text`.
7. `md_amr_handler.py` already normalized reject reasons from mixed legacy fields.
8. `mean_reversion_handler.py` and `md_amr_handler.py` key `ORDER_STATE_CHANGED` handling off `status`.
9. `FSMCore.emit()` is the shared runtime choke point before schema validation.
10. Shadow journal payload fragments already capture selected payload fields and can be extended additively.

## 6. Inferences
1. The package can be hardened safely by canonicalizing producer payloads and adding a shared pre-validation compatibility seam.
2. Reject/cancel/expire semantics do not need a new verb to become clearer; explicit semantic fields are sufficient for this package.
3. Canonical identity can be strengthened now even though continuity and replay remain out of scope.
4. The main contract weakness was shape drift and schema absence, not missing runtime owners.

## 7. Assumptions
1. Additive fields will not break active consumers that ignore unknown keys.
2. Existing tests cover the active producer/consumer paths that matter for this seam.
3. `rid` remains optional on watchdog path because the correlation boundary is not solved in this package.

## 8. Unknowns
1. Whether non-inspected logging or analytics code outside the executed tests depends on minimal old payload shapes.
2. Whether future producer paths will add stronger exchange-native reject identity.
3. Whether a later replay-capable truth plane will want a dedicated terminal-order verb split instead of enriched current verbs.

## 9. Contract drift found
### Drift item 1
- location: `verb_registry_v1.yaml`
- symptom: `ORDER_REJECTED` and `ORDER_STATE_CHANGED` were schema-null
- root cause: contract registry lagged behind live runtime use
- mechanism: payload validation could not enforce shape
- effect: mixed live shapes remained valid by default
- operational risk: consumers and forensic tooling had no canonical contract anchor

### Drift item 2
- location: `open_executor.py`, `fsm.py`, `binance_ws_client.py`
- symptom: reject reasons arrived as `reason`, `reject_reason`, or `reason_code` plus `reason_text`
- root cause: producer-local formatting choices
- mechanism: consumer had to infer canonical meaning from multiple fields
- effect: semantic ambiguity and brittle compatibility
- operational risk: retry logic and forensics could disagree on reject class

### Drift item 3
- location: `watchdog.py` vs `binance_ws_client.py`
- symptom: terminal `ORDER_STATE_CHANGED` payload shapes differed materially
- root cause: thin watchdog payload and no canonical translation seam
- mechanism: WS path had richer ids and metadata; watchdog path did not
- effect: different identity quality for the same event family
- operational risk: replay-readiness and causality interpretation remained weaker on fallback path

### Drift item 4
- location: both target verbs
- symptom: no explicit canonical identity quality or identity key
- root cause: identity was implicit in ad hoc field combinations
- mechanism: each consumer effectively decided for itself what mattered
- effect: difficult to reason about exact vs degraded identity
- operational risk: later dedupe/replay work would start from inconsistent assumptions

### Drift item 5
- location: `ORDER_STATE_CHANGED`
- symptom: terminal non-fill semantics were inferred from `status` only
- root cause: one verb covers both terminal and non-terminal state changes
- mechanism: no explicit terminal semantic marker
- effect: canceled/expired/rejected meaning was runtime-known but contract-implicit
- operational risk: semantic overloading remained harder to audit

## 10. Canonical semantics after package
`EVT:ORDER_REJECTED` means:
- the canonical rejection surface for non-fill order rejection semantics on active runtime paths
- it is not a generic state-change event
- it always carries:
  - `terminal_non_fill=true`
  - `terminal_state_kind=REJECTED`
  - canonical reject reason when resolvable as `reject_reason_normalized`

terminal non-fill `EVT:ORDER_STATE_CHANGED` means:
- a generic state-change event that becomes explicit terminal non-fill truth when `status` is terminal non-fill
- for `CANCELED`, `EXPIRED`, or `REJECTED`, it now carries:
  - `terminal_non_fill=true`
  - `terminal_state_kind=<CANCELED|EXPIRED|REJECTED>`

How they differ after package:
- rejected:
  - use `EVT:ORDER_REJECTED`
  - semantic meaning is reject/non-acceptance surface
  - canonical reason surface is explicit
- canceled:
  - remains `EVT:ORDER_STATE_CHANGED`
  - semantic meaning is terminal cancel state
  - explicit via `terminal_state_kind=CANCELED`
- expired:
  - remains `EVT:ORDER_STATE_CHANGED`
  - semantic meaning is terminal expire state
  - explicit via `terminal_state_kind=EXPIRED`

No semantic collapse was introduced.

## 11. Canonical identity basis after package
Canonical identity basis:
- `symbol`
- `orderId` and `clientOrderId` when both exist
- `rid` as fallback lineage identity when order ids are absent
- event surface (`EVT:ORDER_REJECTED` vs `EVT:ORDER_STATE_CHANGED`)
- terminal semantic kind (`REJECTED`, `CANCELED`, `EXPIRED`, or status-derived terminal kind)

Justification:
- `symbol`: present on active producers and required by consumers
- `orderId`: strong venue identity when present
- `clientOrderId`: strong internal/exchange correlation when present
- `rid`: only lineage fallback on thin reject and watchdog paths
- event surface: prevents conflating reject with state-change
- terminal semantic kind: prevents conflating canceled, expired, and rejected

Exact/degraded/weak policy:
- exact: `symbol + orderId + clientOrderId + event + terminal kind`
- degraded: `symbol + one order identifier + event + terminal kind`
- weak: `symbol + rid + event + terminal kind`

## 12. Changes implemented
- added `apps/reference/domains/execution_position/terminal_order_contracts.py`
  - shared canonical normalization helper for both targeted verbs
- added `apps/reference/domains/execution_position/schemas/order_rejected_v1.json`
  - schema-backed contract for reject events
- added `apps/reference/domains/execution_position/schemas/order_state_changed_v1.json`
  - schema-backed contract for state-change events
- updated `apps/reference/dictionaries/verb_registry_v1.yaml`
  - registered both schemas
- updated `apps/reference/adapters/binance_ws_client.py`
  - canonicalized WS payloads before emit
- updated `apps/reference/domains/execution_position/watchdog.py`
  - canonicalized watchdog terminal state payloads before emit
- updated `apps/reference/domains/execution_position/open_executor.py`
  - canonicalized all active reject emits before send/WAL path
- updated `apps/reference/domains/execution_position/fsm.py`
  - canonicalized adapter-error reject payload
- updated `vfoundation/core/fsm_core.py`
  - added shared compatibility normalization before schema validation
- updated `apps/reference/domains/decision_making/md_amr_handler.py`
  - consumer now prefers `reject_reason_normalized`
- updated `apps/reference/telemetry/shadow_journal.py`
  - shadow fragments keep canonical identity/reason/compatibility fields

## 13. Compatibility matrix
| event | old payload shape | canonical payload shape | producer | consumer(s) | translation rule | visibility mechanism | retirement status | operational risk if translation removed |
|---|---|---|---|---|---|---|---|---|
| `EVT:ORDER_REJECTED` | `reason` only | add `reject_reason_normalized`, `reject_reason_source`, canonical ids, `terminal_state_kind=REJECTED` | WS maker-only reject, open executor reject paths | `md_amr_handler`, monitoring, audit paths | preserve `reason`; add canonical fields | shadow payload fragment + tests | Transitional active | consumer retry logic may stop matching rejects consistently |
| `EVT:ORDER_REJECTED` | `reject_reason` only | preserve `reject_reason`; add canonical fields | legacy/test and some compatibility callers | `md_amr_handler` | `reject_reason_normalized` copied from `reject_reason` | shadow payload fragment + tests | Transitional active | legacy compatibility tests/consumers could diverge |
| `EVT:ORDER_REJECTED` | `reason_code` + `reason_text` | preserve both; derive canonical normalized reason | adapter-error reject path | monitoring, consumer normalization path | canonical reason derives from code/text pair | shadow payload fragment + smoke/test | Transitional active | canonical interpretation of adapter errors weakens again |
| `EVT:ORDER_STATE_CHANGED` terminal watchdog | `orderId`, `symbol`, `status`, `client_order_id`, `rid=None` | add `clientOrderId`, `order_id`, `event_ts_ms`, `identity_quality`, `canonical_identity_key`, `terminal_non_fill`, `terminal_state_kind`, `compatibility_aliases_retained` | watchdog | state-change consumers, monitoring | preserve old fields, add canonical aliases/semantics | shadow payload fragment + watchdog test | Transitional active | thin fallback path remains ambiguous and weaker than WS path |
| `EVT:ORDER_STATE_CHANGED` terminal WS | richer mixed camel/snake ids, implicit terminal meaning | preserve ids, add explicit terminal semantic fields and canonical identity fields | WS order update path | state-change consumers, monitoring | preserve shape, add explicit semantics | shadow payload fragment + integration tests | Transitional active | terminal meaning returns to implicit status-only inference |
| both targeted verbs through `FSMCore.emit()` | legacy payload without canonical fields | normalized payload before schema validation | any active caller using bus emit | all listeners | normalize only these verbs pre-validation | runtime validation + compatibility smoke | Transitional active | new schemas would fail on legacy shapes and break active callers |

## 14. Observability impact
Normalization and compatibility remain visible because:
- payloads now include:
  - `canonical_identity_key`
  - `identity_quality`
  - `terminal_state_kind`
  - `reject_reason_normalized`
  - `reject_reason_source`
  - `compatibility_aliases_retained`
- `shadow_journal.py` was extended to keep these fields in `payload_fragment`
- compatibility is not hidden; it is declared in-payload rather than silently rewritten with no trace

No new hidden cache or silent translation layer was introduced.

## 15. Validation evidence
### Test commands
```powershell
python -m py_compile apps/reference/domains/execution_position/terminal_order_contracts.py apps/reference/adapters/binance_ws_client.py apps/reference/domains/execution_position/watchdog.py apps/reference/domains/execution_position/open_executor.py apps/reference/domains/execution_position/fsm.py apps/reference/domains/decision_making/md_amr_handler.py apps/reference/telemetry/shadow_journal.py vfoundation/core/fsm_core.py tests/domains/execution_position/test_watchdog.py tests/integration/test_ep01_5_ws_expired_maker_reject.py tests/domains/decision_making/test_order_rejected_payload_normalization.py tests/domains/execution_position/test_terminal_non_fill_order_contracts.py

python -m pytest tests/domains/execution_position/test_terminal_non_fill_order_contracts.py -q
python -m pytest tests/domains/execution_position/test_watchdog.py -k cancelled -q
python -m pytest tests/domains/decision_making/test_order_rejected_payload_normalization.py -q
python -m pytest tests/domains/decision_making/test_event_import_order_rejected.py -q
python -m pytest tests/integration/test_ep01_5_ws_expired_maker_reject.py -q
python -m pytest tests/telemetry/test_shadow_critical_event_journal.py -q
python -m pytest tests/domains/execution_position/test_terminal_non_fill_order_contracts.py tests/domains/execution_position/test_watchdog.py tests/domains/decision_making/test_order_rejected_payload_normalization.py tests/domains/decision_making/test_event_import_order_rejected.py tests/integration/test_ep01_5_ws_expired_maker_reject.py tests/telemetry/test_shadow_critical_event_journal.py -q
```

### Results
```text
py_compile
  succeeded

tests/domains/execution_position/test_terminal_non_fill_order_contracts.py
  4 passed

tests/domains/execution_position/test_watchdog.py -k cancelled
  1 passed, 11 deselected

tests/domains/decision_making/test_order_rejected_payload_normalization.py
  42 passed

tests/domains/decision_making/test_event_import_order_rejected.py
  4 passed

tests/integration/test_ep01_5_ws_expired_maker_reject.py
  8 passed

tests/telemetry/test_shadow_critical_event_journal.py
  5 passed

aggregate subset
  75 passed
```

### Compatibility smoke
```powershell
@'
from vfoundation.core.schema_registry import init_global_registry
from vfoundation.core.fsm_core import FSMCore

init_global_registry(project_root='.')
fsm = FSMCore()
fsm.emit('EVT:ORDER_REJECTED', payload={'symbol':'BTCUSDT','reason':'maker_only_reject','rid':'rid-legacy'}, why='smoke')
fsm.emit('EVT:ORDER_STATE_CHANGED', payload={'symbol':'BTCUSDT','status':'canceled','orderId':'o1'}, why='smoke')
print('terminal_order_contract_smoke_ok')
'@ | python -
```

Result:
```text
terminal_order_contract_smoke_ok
```

### Grep/search proof
Commands:
```powershell
rg -n "EVT:ORDER_REJECTED" apps/reference vfoundation tests -g '!**/__pycache__/**'
rg -n "EVT:ORDER_STATE_CHANGED" apps/reference vfoundation tests -g '!**/__pycache__/**'
rg -n "reject_reason_normalized|canonical_identity_key|compatibility_aliases_retained" apps/reference vfoundation tests -g '!**/__pycache__/**'
```

Proof highlights:
- `apps/reference/adapters/binance_ws_client.py:396-402` producer and canonicalization seam
- `apps/reference/domains/execution_position/watchdog.py:453` watchdog terminal state emit
- `apps/reference/domains/execution_position/terminal_order_contracts.py:144-167` canonical reject fields
- `apps/reference/domains/execution_position/terminal_order_contracts.py:211-229` canonical state-change fields
- `vfoundation/core/fsm_core.py:85` compatibility normalization seam
- `apps/reference/telemetry/shadow_journal.py:423-432` observability capture
- `apps/reference/domains/decision_making/md_amr_handler.py:1051-1056` consumer preference for canonical reject reason

### Targeted manual trace proof
- `tests/integration/test_ep01_5_ws_expired_maker_reject.py` now proves WS maker-only reject emits:
  - `reject_reason_normalized=MAKER_ONLY_REJECT`
  - `terminal_state_kind=REJECTED`
  - `identity_quality=order_identity_exact`
- `tests/domains/execution_position/test_watchdog.py` proves watchdog canceled state emits:
  - `terminal_non_fill=True`
  - `terminal_state_kind=CANCELED`
  - `canonical_identity_key=...`

## 16. Boundary preservation check
Proof of preserved boundaries:
- no warm-state expansion to terminal non-fill states
  - no changes were made to warm-state scope or `truth_hardening.py` logic for non-fill continuity in this package
- no fake replay introduced
  - changes are payload normalization, schemas, and observability only
- no broad `ORDER_STATE_CHANGED` redesign
  - verb remains unchanged; package only hardens the terminal non-fill subset by adding explicit semantic fields
- no FSM migration work done
  - no FSMv2 or orchestrator changes were introduced

## 17. What remains unproven
- full consumer set outside the executed tests
- stronger watchdog lineage than `rid=None` when correlation is absent
- whether future replay will require a dedicated terminal-order event family rather than enriched current verbs
- whether all legacy analytics/log readers tolerate richer payload shapes without any downstream adjustment

## 18. Recommended next step
Narrow next package:
- `CAUSAL_LINEAGE_HARDENING_FOR_TERMINAL_NON_FILL_ORDER_EVENTS`

Reason:
- identity shape is now explicit
- the next remaining weakness is lineage quality, especially watchdog `rid`/correlation quality
- this can be improved without expanding continuity, replay, or FSM scope
