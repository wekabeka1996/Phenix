# SIDECAR_CLOSE_COMMAND_CONTRACT_AND_EXITMANAGER_OVERLAP_REPORT

## 1. Executive Summary

This audit finds that current Aurora/Phenix runtime does have a reusable close path, but that path is narrower than the operator's current mental model.

- `CMD:CLOSE` today means: symbol-scoped close request that is translated into a reduce-only close decision and then executed against the current live net symbol position.
- `CMD:CLOSE` does not currently mean: close exact order by ID, close exact lifecycle by ID, or close exact position object by ID.
- Current close execution derives the target from `symbol` plus current exchange position state, with optional `qty` for partial reduction.
- Lifecycle-like identifiers exist for correlation and observability, but not as executable close targets.
- Aurora `ExitManager` already occupies part of the same policy territory a future sidecar would want to enter. Its "exit" branches are not a clean standalone flat-close command path; they currently materialize through opposite-side signal forcing and flip orchestration into reduce-only close flow.
- The safest narrow starting mode for a future standalone sidecar is not "close exact lifecycle by ID" because that contract is not real today. The safest narrow mode is:
  - recommendation-only if the sidecar is outside `execution_position`, or
  - an internal `execution_position`-local recommendation/request surface if the sidecar lives there and reuses existing owners.

### Final high-level verdict

- Can a future separate sidecar safely act through the current close path: `YES`, but only for symbol-scoped reduce-only close semantics.
- Can it close "that exact lifecycle/order/position by ID": `NOT SUPPORTED`.
- Does it overlap with existing Aurora post-entry exit logic: `YES`, materially, especially with `ExitManager`, regime-flip close, max-hold close, trailing stop replacement, bracket fills, and duplicate-close suppression.

## 2. FACTS

- `IntentRouter` converts reduce-only `EVT:TRADE_INTENT_PROPOSED` messages into `CMD:CLOSE` with `symbol`, `reason`, `idempotent_key`, `retry_key`, `qty`, and `trace`.
- `CloseFlowFSM` receives `CMD:CLOSE` and always emits `DEC:CLOSE` with `reduce_only=True`.
- `CloseExecutor.execute_close()` requires `symbol`, optionally uses `qty`, and closes via `adapter.place_market_reduce_only(...)` against the current exchange position snapshot.
- `CloseExecutor` does not accept or route by `orderId`, `clientOrderId`, `rid`, `lifecycle_id`, or `position_id`.
- `OrderIndex` tracks order correlation: `rid <-> idempotent_key <-> clientOrderId <-> exchangeOrderId`.
- `ManageFlowFSM` keeps local lifecycle state such as `position_qty`, `position_side`, bracket order ids, and `_closing_position`.
- `ManageFlowFSM` does not make `CMD:CLOSE` lifecycle-targeted; current close routing remains symbol/effective-position based.
- `ExecPosFSM` hardens duplicate closes by symbol, requested qty, and effective portfolio position signature, not by lifecycle identity.
- `ExitManager.check_exit()` can return:
  - force-close branches,
  - tighten-stop branch,
  - or no action.
- In Aurora flow, force-close branches become opposite-side effective signal, then go through flip orchestration, which emits reduce-only close intent and defers reopen.
- The tighten-stop branch only proves signal payload mutation (`stop_loss_override` / emitted `tpsl_result` override). Execution-side mutation of an already-live bracket by that branch is `UNPROVEN`.
- `CMD:CLOSE` and `DEC:CLOSE` both have `schema: null` in the registry.
- No `position_id` contract was proven in the traced runtime/code/schema surface.

## 3. INFERENCES

- A sidecar can reuse the current close path only if its intended target is "the current net live position for this symbol" rather than "that exact lifecycle instance."
- If a future sidecar must target a specific lifecycle instance, current runtime needs a new executable identity contract or an internal owner-mediated selection step.
- A sidecar placed in `decision_making` would overlap more heavily with `ExitManager` because both would be post-entry policy evaluators.
- A sidecar placed near `execution_position` can reuse existing close owners more safely because it can respect `_closing_position`, bracket state, reconciliation, and duplicate-close hardening.
- Public event streams are not currently sufficient to guarantee race-free external sidecar closes, because not every close initiation is surfaced as a stable public event before execution proceeds.

## 4. UNKNOWNS

- Whether the command-oriented compatibility helper `FlipOrchestrator.initiate_flip_close()` has a meaningful live runtime caller beyond compatibility/test surface is `UNPROVEN`.
- Whether `ExitManager` stop tightening leads to deterministic exchange-side bracket replacement in Aurora runtime is `UNPROVEN`.
- Whether an external event-only sidecar could always observe "close already in progress" before it emits its own request is `UNPROVEN`.
- Whether partial-reduce sidecar behavior could be made safe using current public contracts alone is `UNPROVEN`.

## 5. Exact Meaning of Current `CMD:CLOSE`

### FACTS

Cause:
- `IntentRouter` routes reduce-only proposed trade intents into `CMD:CLOSE`.

Mechanism:
- `CMD:CLOSE` is consumed by `CloseFlowFSM`.
- `CloseFlowFSM` emits `DEC:CLOSE` with `reduce_only=True`.
- `CloseExecutor` executes a reduce-only market close against the current symbol position.

Effect:
- Current runtime interprets `CMD:CLOSE` as "attempt to reduce or flatten current live symbol exposure."

Operational risk:
- Treating it as lifecycle-targeted would cause false confidence and potential wrong-target closes.

### Field-level contract table

| Surface | Required today | Optional today | Ignored for target selection |
| --- | --- | --- | --- |
| `CMD:CLOSE` input | `symbol` in practice for execution usefulness | `reason`, `qty`, `idempotent_key`, `retry_key`, `trace`, `rid` | `idempotent_key`, `retry_key`, `rid`, `trace` |
| `DEC:CLOSE` payload | `symbol`, `reduce_only=True` | `qty`, `reason`, `trigger`, `trace` | any lifecycle-like field not consumed by executor |
| `CloseExecutor` | `symbol` | `qty` | `idempotent_key`, `rid`, any notional lifecycle key |

### Supported close targeting modes

| Targeting mode | Status | Evidence-backed meaning today |
| --- | --- | --- |
| By symbol | `SUPPORTED` | Executor loads current open position by `symbol` and closes/reduces it |
| By symbol + qty | `SUPPORTED` | Partial reduce if requested qty is less than current open qty |
| By order ID | `NOT SUPPORTED` | No `DEC:CLOSE`/`CMD:CLOSE` routing branch consumes order id |
| By client order ID | `NOT SUPPORTED` | Close executor does not use `clientOrderId` to select target |
| By `rid` | `NOT SUPPORTED` | `rid` is correlation/idempotency context, not close target selector |
| By `lifecycle_id` / `idempotent_key` | `NOT SUPPORTED` | Used for correlation/client id generation, not target selection |
| By `position_id` | `NOT SUPPORTED` | No proven runtime `position_id` contract |

## 6. Close-by-ID Feasibility Audit

### Lifecycle identity audit

| Identifier | Exists | Stability across lifecycle | Current role | Can current close path execute against it |
| --- | --- | --- | --- | --- |
| `rid` | Yes | Per message/request | correlation | No |
| `idempotent_key` | Yes | stable enough for request/order family correlation | correlation, client id generation, observability | No |
| `clientOrderId` | Yes | per exchange order | order correlation | No for close target |
| `exchangeOrderId` | Yes | per exchange order | order correlation | No for close target |
| `tradeId` | Yes | per fill/trade | observability | No |
| `lifecycle_id` | Yes, derived | symbol-scoped cached correlation, not authoritative state key | observability | No |
| `entry_order_id` | Yes, local | first entry order for local tracking | local lifecycle observability | No |
| `entry_client_order_id` | Yes, local | first entry client order for local tracking | local lifecycle observability | No |
| `position_id` | No proof | n/a | n/a | No |

### FACTS

Cause:
- Current runtime maintains order identities and derived lifecycle correlation, but the close executor selects a target from the current symbol position snapshot.

Mechanism:
- `OrderIndex` and event handlers preserve correlation.
- `CloseExecutor` re-reads exchange positions by symbol and uses current `positionAmt`.

Effect:
- Identity is preserved for tracing, not for exact executable targeting.

Operational risk:
- A sidecar assuming close-by-id exists could close the wrong live exposure after fills, partial TPs, retries, or delayed reconcile.

### Verdict

`NOT SUPPORTED` for "close exact lifecycle by ID."

This verdict is based on three proven limits:

1. No executable `position_id` or lifecycle-target field exists in the current close command contract.
2. `CloseExecutor` derives the close target from current symbol state, not identity fields.
3. Duplicate suppression is keyed by symbol/effective-state, not by lifecycle instance.

## 7. `ExitManager` End-to-End Execution Mapping

### Branch map

| `ExitManager.check_exit()` branch | Immediate output | Downstream Aurora effect | Proven execution effect |
| --- | --- | --- | --- |
| Danger-zone force close | `should_exit=True`, reason `EXIT_DANGER_ZONE:ForceClose` | `aurora_decision` forces opposite effective side | flip orchestration emits reduce-only close intent; runtime-proven |
| Trailing exit | `should_exit=True` | same as above | same as above; runtime-proven as indirect close path |
| Time-limit exit | `should_exit=True` | same as above | same as above; runtime-proven as indirect close path |
| Signal reversal exit | `should_exit=True` | same as above | same as above; runtime-proven as indirect close path |
| Danger-zone tighten | `should_exit=False`, `new_sl` | signal payload stop override only | exchange-side bracket mutation from this branch is `UNPROVEN` |
| No exit | no action | no forced close | n/a |

### FACTS

Cause:
- Aurora embeds post-entry exit evaluation inside decision-making before signal emission.

Mechanism:
- `aurora_decision` calls `exit_manager.check_exit(...)`.
- Exit branches flip the emitted side.
- `StrategyGateway` and `FlipOrchestrator` convert that into reduce-only close flow.

Effect:
- `ExitManager` already causes real close execution, but indirectly.

Operational risk:
- A future sidecar could unknowingly duplicate current post-entry exit policy and generate competing closes.

### Proof status by branch

| Branch family | Proof status | Why |
| --- | --- | --- |
| Full-exit branches -> reduce-only close path | `runtime-proven` | traced through `aurora_decision`, `StrategyGateway`, `FlipOrchestrator`, `IntentRouter`, `CloseFlowFSM`, `CloseExecutor` |
| Tighten-only branch -> emitted stop override in signal payload | `runtime-proven` | payload mutation is explicit in `aurora_decision` |
| Tighten-only branch -> live bracket replacement | `UNPROVEN` | no traced end-to-end proof from override to adapter-side bracket mutation |
| Compatibility direct `CMD:CLOSE` helper in flip orchestration | `test-proven` / partially runtime-proven | helper exists and emits command, but live hot-path use is unproven |

## 8. Sidecar Overlap / Precedence Matrix

| Overlap surface | Current owner | What future sidecar would collide with | Conflict type | Required precedence | Severity |
| --- | --- | --- | --- | --- | --- |
| Bracket SL/TP fills | `ManageFlowFSM` + exchange fills | closing same symbol while bracket already resolved it | duplicate action | bracket/execution truth must win | Critical |
| Existing `DEC:CLOSE` execution | `CloseExecutor` | second close attempt during same effective state | duplicate action | existing hardening must remain final arbiter | Critical |
| Duplicate-close suppression | `ExecPosFSM` hardening | sidecar assuming lifecycle-level idempotence | ownership conflict | symbol/effective-state guard stays single-owner | Critical |
| Reconcile / tidy cleanup | `OrderGuardian` | sidecar interpreting tidy aftermath as business close trigger | duplicate policy / wrong attribution | reconciliation owner stays single-owner | High |
| Max-hold close | `ManageFlowFSM` | sidecar emitting concurrent close for same position | duplicate policy/action | max-hold or close-in-progress state must suppress later sidecar action | High |
| Aurora `ExitManager` full exits | `decision_making` | sidecar evaluating similar regime/time/trailing logic | duplicate policy | one policy must have explicit precedence or sidecar must scope itself away | High |
| Regime-flip close path | `FlipOrchestrator` | sidecar reacting to same regime deterioration | duplicate policy/action | regime-flip owner must be visible to sidecar before sidecar acts | High |
| Trailing stop replacement | `ManageFlowFSM` | sidecar also trying to "tighten" or close based on same movement | duplicate policy | stop-management owner must remain single-owner | High |
| TP1/TP2 bracket logic | `ManageFlowFSM` + bracket manager | sidecar extending/replacing target while TP plan already armed | ownership conflict | target management must not silently fork | High |
| External observability of close-in-progress | no single public event owner | sidecar failing to notice close already started | race/masking | requires new attribution or internal access | High |

### Single-owner only surfaces

- live bracket mutation and replacement
- close execution authority
- duplicate-close suppression
- reconciliation and tidy aftermath
- authoritative "position is closing / position is closed" truth

## 9. Sidecar Output Contract Options

| Option | Current compatibility | Needs new schema | Preserves SSOT boundaries | Can safely target correct lifecycle today | Blast radius | Debugging difficulty |
| --- | --- | --- | --- | --- | --- | --- |
| Recommendation-only event | High | likely yes if formalized | Yes | No exact target, but safe as advisory | Low | Medium |
| Internal `execution_position`-local recommendation object | High if sidecar lives inside EP | not necessarily external schema | Yes if translated by current owners | Better than external, but still no native close-by-id | Low-Medium | Medium |
| Direct current `CMD:CLOSE` | Partial | No | Yes only if treated as symbol-scoped request | No for exact lifecycle targeting | Medium | High |
| Reduce-only request via current intent path | Partial | No | Yes | No exact lifecycle targeting | Medium | High |
| New close-targeting contract required | Not currently compatible | Yes | Potentially yes if owner-mediated | Yes, if designed later | High | High |

### Safest narrow starting option

The safest narrow starting option is:

- `internal execution_position-local recommendation object` if the sidecar is implemented as a separate file inside `execution_position`, because that allows the existing owner to decide whether to translate the recommendation into current symbol-scoped close flow.

If the sidecar must remain fully external/public-event driven, the safest narrow starting option is:

- `recommendation-only event`.

### Most dangerous option

- Pretending current `CMD:CLOSE` already means "close this exact lifecycle/order/position by ID."

### Exact blocker for close-by-ID

- no executable lifecycle target field in current close contract
- no proven `position_id`
- executor selects by `symbol` plus current exchange position
- public observability is not sufficient to prove exact-target close attribution

## 10. Minimum Viable Subscription Set

### Minimum viable set

| Event | Why it is needed | Current payload sufficiency | Blocking gap |
| --- | --- | --- | --- |
| `EVT:PORTFOLIO_STATE_UPDATED` | know whether symbol exposure is actually open/flat | partial | does not by itself say who initiated close |
| `EVT:ORDER_FILL` | detect entry fill, bracket fills, partial reductions | partial | correlation is present, but not executable targeting |
| `EVT:ORDER_STATE_CHANGED` | detect close order progress / bracket cancellation states | partial | not a universal "close started" event |
| `EVT:EXECUTION_CLOSE_RECONCILED` | know business close cleanup completed | partial | late event; too late to prevent race |
| `EVT:REGIME_DETECTED` | regime pressure input | sufficient for policy input | not enough for close ownership |
| `EVT:FEATURES_CALCULATED` | microstructure / pressure input | feature-dependent, generally sufficient for policy input | freshness/field selection is a policy problem, not a lifecycle target proof |

### Nice-to-have set

- `EVT:TRADE_EXECUTED` for cleaner position-open correlation if the sidecar uses execution fills rather than portfolio snapshots alone
- `EVT:EXIT_MATCH_ATTEMPTED` / `EVT:EXIT_MATCH_FAILED` for bracket-close forensic context
- `EVT:EXECUTION_GUARD_BLOCKED` to understand duplicate suppression and guard refusal

### Missing fields that still make a sidecar unsafe

- universal close-initiation event or equivalent
- initiator/source attribution for every close path
- explicit `close_in_progress` public state
- executable target identity if exact lifecycle targeting is desired

## 11. Observability / Forensic Gaps

### Coverage already present

- `EVT:ORDER_FILL` and `POSITION_CLOSED` style logs can carry `lifecycle_id` and `trade_id`
- `EVT:EXIT_MATCH_ATTEMPTED` / `EVT:EXIT_MATCH_FAILED` explain bracket matching attempts
- `EVT:EXECUTION_CLOSE_RECONCILED` distinguishes business-close reconciliation from tidy-only cleanup
- duplicate-close hardening emits execution guard blocking telemetry

### Missing pieces

Cause:
- close initiation is not uniformly represented as a stable public, structured event.

Mechanism:
- internal reduce-only intent routing can become `CMD:CLOSE` and `DEC:CLOSE` without a universally externalized close-init contract.

Effect:
- operators cannot always answer "who closed first and why" across `ExitManager`, regime-flip, max-hold, bracket fill, sidecar, and cleanup aftermath.

Operational risk:
- future sidecar rollout would be difficult to debug and could be blamed or exonerated incorrectly.

### Minimum future trace fields required before safe rollout

- close policy source
- close request id
- target symbol
- requested qty
- whether close was business-close vs tidy-only aftermath
- whether an existing close was already in progress
- suppression reason if sidecar action was ignored
- if a future executable lifecycle id is introduced, that id must be logged consistently from request through reconcile

## 12. What Must Not Be Changed Yet

- Do not reinterpret current `CMD:CLOSE` as close-by-id. That is not the contract today.
- Do not move lifecycle truth ownership away from `ManageFlowFSM`, `CloseExecutor`, and `OrderGuardian`.
- Do not treat `lifecycle_id` or `idempotent_key` as executable position identifiers.
- Do not let a future sidecar mutate bracket truth, duplicate-close hardening, or reconciliation ownership implicitly.
- Do not assume `ExitManager` stop override already owns live bracket replacement.
- Do not blur recommendation with command in the first iteration of design discussion.

## 13. Final Verdict

The current runtime can support a future separate sidecar only if the design stays additive and respects present contracts.

- Reusing current close execution is feasible for symbol-scoped reduce-only close.
- Exact lifecycle/order/position close-by-id is not a current runtime capability.
- `ExitManager` already overlaps the sidecar problem space and must be treated as a real incumbent, not background noise.
- The safest first contract is advisory or EP-internal recommendation, not a pretend lifecycle-targeted `CMD:CLOSE`.
- Exact lifecycle targeting, race-proof external subscription, and unambiguous forensics remain blocked by missing identity and attribution contracts.
