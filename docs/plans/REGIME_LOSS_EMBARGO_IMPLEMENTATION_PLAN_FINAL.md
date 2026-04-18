# Regime Loss Embargo - Final Implementation Plan

## 1. Purpose

This package adds a narrow per-symbol entry lockout for one specific business rule:

- while the symbol remains in the same stable regime epoch, new entries are allowed
- after the first terminal net losing trade that was opened in that stable regime epoch, new entries for that symbol must be blocked
- the block resets only when the next stable regime epoch begins

The desired behavior is causal, not heuristic.

Naive interpretations are wrong:

- `close_reason == SL` is not the trigger because the rule is about terminal net loss, not exit label
- close-time regime is not the causal key because a trade can close after the regime that caused its entry has already changed
- `structural_regime_ref` is not a valid epoch identity because it is a detector event ref, not a stable business epoch key

The package is additive-only, contract-first, and must keep YAML + Pydantic as SSOT. No silent fallbacks are allowed.

## 2. Final architectural decision

`decision_making` owns the stable regime epoch interpretation and the embargo policy.

`execution_position` owns terminal close truth and emits the terminal close event.

`StrategyGateway` owns the shared entry gate that blocks new entries when the policy says the symbol is blocked.

This ownership split is the final architectural decision for the package.

Alternative placements are rejected:

- per-handler enforcement is rejected because the rule is cross-strategy and would be duplicated
- `execution_position`-owned policy latch is rejected because it moves business policy into the execution truth owner
- sidecar-owned logic is rejected because this is a first-class admission rule, not advisory logic
- `regime_detector`-owned epoch semantics are rejected because detector owns raw regime signals, not business-policy epoch interpretation

### Isolated component design

The policy core must live in one dedicated `decision_making` component, for example:

- `apps/reference/domains/decision_making/regime_loss_embargo.py`

That component owns:

- stable regime epoch maintenance for the policy
- terminal close evaluation for embargo purposes
- fail-closed unresolved-context handling
- latch and reset decisions
- entry-block decisions and reject context construction

Other touched files are integration hooks only:

- `event_handlers.py` forwards normalized regime and close facts into the policy core
- `decision_making.py` instantiates the policy core and wires thin listener delegates
- `strategy_gateway.py` asks the policy core whether a symbol must be blocked
- `intent_builder.py` propagates `regime_epoch_ref`
- `execution_position` caches entry-time epoch context and forwards terminal close truth

The plan must be implemented so the business logic is centralized in the dedicated policy core, not copied into multiple files.

## 3. Causal model

Close-time regime is wrong because the regime at close may differ from the regime that caused the trade to open. Using close-time regime would let a losing trade from an earlier regime poison the current regime.

`structural_regime_ref` is wrong as epoch identity because it is a timestamped detector event ref that changes on heartbeat emissions. It is not a stable business epoch key.

`stable_regime_epoch_ref` is a `decision_making`-owned business key representing the current stable regime epoch for one symbol.

It is minted in `decision_making` policy state:

- when the first stable regime is seen for the symbol
- whenever `EVT:REGIME_DETECTED.changed == true`

It does not change when `changed == false`. That is what keeps it stable across same-regime heartbeats.

`stable_regime_epoch_ref` must not be recomputed later from detector provenance. It must be minted once, persisted in `decision_making` policy state, and retained there until the next `changed == true` transition.

`regime_epoch_ref` is the entry-time copy of that business key carried over the `TRADE_INTENT_PROPOSED` boundary and then forwarded by `execution_position` on terminal close.

### Fail-closed invariants

The package must obey these invariants:

- if required causal identity is missing, do not infer it
- do not reconstruct regime epoch from detector provenance after the fact
- do not silently continue as if the feature were disabled
- if the feature is enabled and a symbol enters a state where embargo evaluation requires missing critical causal context, new entries for that symbol must be blocked until the next stable regime epoch reset restores a provable state

For this package, critical causal context includes:

- missing or null `entry_regime_epoch_ref` on a terminal close fact that reaches embargo evaluation
- missing current `stable_regime_epoch_ref` when the policy needs to evaluate a close fact or answer an entry-block decision
- incompatible or absent terminal close context for the symbol after the event has passed the execution boundary

Contract-invalid close events should fail at the contract boundary and not be treated as normal runtime inputs. If accepted runtime inputs still leave the policy unable to prove causal state for a symbol, the policy blocks new entries for that symbol until the next stable regime epoch reset.

## 4. Runtime data flow

1. `decision_making.on_regime()` forwards normalized regime facts into the dedicated embargo policy core, which maintains `stable_regime_epoch_ref`.
2. `TRADE_INTENT_PROPOSED` carries additive field `regime_epoch_ref`.
3. `execution_position` caches entry-time `regime_epoch_ref` together with existing entry-time regime context.
4. Terminal full close emits `EVT:POSITION_CLOSED` from `execution_position`.
5. `decision_making.on_position_closed()` forwards terminal close facts into the policy core.
6. The policy core latches embargo only when all of the following are true:
   - the close is terminal because it came from `EVT:POSITION_CLOSED`
   - `realized_pnl_net < -min_loss_threshold_net`
   - `entry_regime_epoch_ref == current stable_regime_epoch_ref`
7. If the feature is enabled and the policy core cannot prove required causal context for the symbol, it puts that symbol into a fail-closed blocked state until the next stable regime epoch reset.
8. `StrategyGateway` asks the policy core whether new entries must be blocked for the symbol.
9. The next stable regime epoch resets both:
   - a normal loss-triggered embargo latch
   - a fail-closed unresolved-context block

## 5. Contract changes

Only the following contract changes are required.

`EVT:TRADE_INTENT_PROPOSED`

- add additive top-level field `regime_epoch_ref`
- this field carries the `decision_making`-owned stable regime epoch at entry time
- schema update is mandatory because the trade-intent schema is strict

`EVT:POSITION_CLOSED`

- promote the existing partial event into a real `execution_position` contract
- keep it as a general-purpose execution event, not a DM-only event
- do not narrow its semantics with `dst="decision_making"`

Required `EVT:POSITION_CLOSED` fields:

- `symbol`
- `trade_id`
- `close_reason`
- `close_ts_ms`
- `realized_pnl_net`
- `fees`
- `entry_regime_epoch_ref`

`trade_id` is not only a required field. It is runtime-critical for existing consumers that already resolve close identity by trade id rather than symbol-only matching.

Strict schema expectations:

- schema must be explicit and contract-first
- `entry_regime_epoch_ref` should be schema-required as a field-presence contract, but may be nullable for compatibility paths
- omission is a contract violation; null means explicitly unavailable
- schema-invalid close facts must fail at the contract boundary, not degrade silently into normal runtime processing

Registry and dictionary updates:

- register schema ownership for `EVT:POSITION_CLOSED` in `verb_registry_v1.yaml`
- export `EVT:POSITION_CLOSED` from `execution_position/domain_dict.json`
- import `EVT:POSITION_CLOSED` into `decision_making/domain_dict.json`

No speculative future contracts are included in the first package.

## 6. Required file changes

### decision_making

`apps/reference/domains/decision_making/regime_loss_embargo.py`

- Why: dedicated policy core module
- Change: add the isolated component that owns epoch maintenance, close evaluation, fail-closed unresolved-context handling, latch/reset logic, and entry-block decisions
- Mandatory: yes

`apps/reference/domains/decision_making/event_handlers.py`

- Why: regime and close facts arrive here
- Change: keep only thin integration hooks that forward normalized regime facts and close facts into the policy core
- Mandatory: yes

`apps/reference/domains/decision_making/decision_making.py`

- Why: listener registration and component composition live here
- Change: instantiate the policy core and register thin facade delegates for regime and close events
- Mandatory: yes

`apps/reference/domains/decision_making/strategy_gateway.py`

- Why: shared cross-strategy entry gate lives here
- Change: replace direct embargo logic with a thin policy-core query that decides whether the symbol must be blocked
- Mandatory: yes

`apps/reference/domains/decision_making/intent_builder.py`

- Why: entry-time epoch context must cross the DM -> EP boundary
- Change: propagate additive top-level field `regime_epoch_ref`
- Mandatory: yes

`apps/reference/domains/decision_making/schemas/trade_intent_v1.json`

- Why: the schema is strict
- Change: add additive top-level field `regime_epoch_ref`
- Mandatory: yes

`apps/reference/domains/decision_making/normalized_reject_reasons.py`

- Why: gateway rejection needs a canonical NRR
- Change: add one new NRR code for regime-loss-embargo entry blocking
- Mandatory: yes

`apps/reference/config_models.py`

- Why: YAML + Pydantic are SSOT
- Change: add the minimal hard-switch config under `DecisionMakingDomainConfig`
- Mandatory: yes

### execution_position

`apps/reference/domains/execution_position/open_executor.py`

- Why: entry-time epoch context must be cached in execution truth
- Change: cache `regime_epoch_ref` together with existing entry-time regime data
- Mandatory: yes

`apps/reference/domains/execution_position/event_handlers.py`

- Why: terminal close truth is constructed here
- Change: emit `EVT:POSITION_CLOSED` after the existing terminal close truth path, including `entry_regime_epoch_ref`
- Mandatory: yes

`apps/reference/domains/execution_position/schemas/position_closed_v1.json`

- Why: promoted close event requires a strict schema
- Change: add the new schema file
- Mandatory: yes

### contracts / schemas / registry

`apps/reference/dictionaries/verb_registry_v1.yaml`

- Why: the close event must become a real owned contract
- Change: set owner, status, and schema for `EVT:POSITION_CLOSED`
- Mandatory: yes

`apps/reference/domains/execution_position/domain_dict.json`

- Why: execution_position must export the event it owns
- Change: add `EVT:POSITION_CLOSED`
- Mandatory: yes

`apps/reference/domains/decision_making/domain_dict.json`

- Why: decision_making must declare the imported event
- Change: add `EVT:POSITION_CLOSED`
- Mandatory: yes

### docs

`docs/plans/REGIME_LOSS_EMBARGO_IMPLEMENTATION_PLAN_FINAL.md`

- Why: implementation SSOT for this package
- Change: this final plan document
- Mandatory: yes

Additional docs after implementation lands:

- update any README, dependency document, or operator-facing contract note that enumerates `EVT:POSITION_CLOSED`, entry-gate behavior, or the new embargo semantics
- Mandatory: yes, when implementation is performed

## 7. Config surface

The first-package config is a hard kill switch plus one explicit numeric threshold.

Expected config:

- `enabled: bool`
- `min_loss_threshold_net: float`

Meaning:

- `enabled=false` means the feature is fully disabled and no embargo behavior runs
- `enabled=true` means production blocking behavior is active
- `min_loss_threshold_net` is the explicit net-PnL epsilon in quote currency used to ignore dust and rounding noise

When `enabled=false`, the policy core must not latch, must not enter unresolved-context blocked state, and must always report `not blocked`.

The following fields must not exist in the first package:

- `mode`
- `shadow`
- `enforce`
- `scope`
- `apply_to_strategies`

The runtime posture is binary:

- off
- on

## 8. Reject semantics

The gateway must use one new canonical NRR code for entry blocks caused by this feature.

That NRR means:

- the symbol is blocked by the regime loss embargo policy

The policy may block for two explicit reasons:

- `LOSS_LATCHED`
- `CAUSAL_CONTEXT_UNPROVEN`

The NRR stays the same. The distinction must appear in reject context, not in hidden behavior.

`CAUSAL_CONTEXT_UNPROVEN` is not an observability-only state. While the feature is enabled, it is an active production fail-closed entry-block reason.

Reject `why` must include:

- the embargo gate token
- the current epoch ref when available
- the block reason

Reject `details` must include:

- `block_reason`
- `epoch_ref`
- `latched_ts_ms`
- `trigger_pnl_net`
- `trigger_close_reason`

`trigger_pnl_net` and `trigger_close_reason` may be null only when the block reason is `CAUSAL_CONTEXT_UNPROVEN`.

When the feature is enabled, there is no advisory path and no shadow-only path. A blocked symbol is rejected in production behavior.

## 9. Latch state model

The policy core owns one per-symbol state record. If it is stored in shared `decision_making` symbol state, it should be stored under a dedicated policy-owned key and other modules must treat it as opaque.

Minimum state:

- `latched`
- `block_reason`
- `epoch_ref`
- `latched_ts_ms`
- `trigger_pnl_net`
- `trigger_close_reason`

State rules:

- `latched=true` means the symbol is blocked by this feature
- `block_reason` is one of:
  - `LOSS_LATCHED`
  - `CAUSAL_CONTEXT_UNPROVEN`
- `epoch_ref` is the `stable_regime_epoch_ref` associated with the current block
- `trigger_pnl_net` and `trigger_close_reason` are populated for `LOSS_LATCHED`
- `trigger_pnl_net` and `trigger_close_reason` may be null for `CAUSAL_CONTEXT_UNPROVEN`
- the next stable regime epoch reset clears the blocked state

No decorative or future fields should be added in the first package.

## 10. Validation plan

### Contract tests

Verify:

- `TRADE_INTENT_PROPOSED` accepts additive field `regime_epoch_ref`
- `EVT:POSITION_CLOSED` requires the mandatory close-truth fields
- `trade_id` remains present for existing consumers
- `entry_regime_epoch_ref` is field-required and nullable only by explicit contract
- registry and domain-dictionary updates are consistent

What would falsify the design:

- producer/schema drift
- missing `trade_id` on normal close path
- schema-invalid close facts reaching normal policy evaluation

### Unit tests

Verify:

- the policy core mints epoch on first stable regime
- the policy core changes epoch only when `changed == true`
- same-regime heartbeats preserve the existing epoch
- qualifying current-epoch net loss latches the symbol
- previous-epoch loss does not latch the current epoch
- missing or null `entry_regime_epoch_ref` causes `CAUSAL_CONTEXT_UNPROVEN` block when the feature is enabled
- missing current `stable_regime_epoch_ref` causes fail-closed block when the feature is enabled
- disabling the feature with `enabled=false` fully disables embargo behavior

What would falsify the design:

- epoch changing on heartbeat
- detector provenance being used to reconstruct epoch after the fact
- missing critical context being silently ignored while entries continue

### Integration tests

Verify:

- `regime_epoch_ref` propagates from DM intent to EP cached entry truth
- terminal close event includes `entry_regime_epoch_ref`
- DM close hook forwards facts into the policy core without re-implementing policy logic
- gateway blocks only new entries, not reduce-only close-management flows
- next stable epoch reset clears both normal latches and fail-closed blocked state

What would falsify the design:

- runtime propagation happening before schema support exists
- close facts missing epoch context on the normal path
- gateway containing duplicated policy logic instead of a thin policy-core query

### Boundary-order / replay checks

Verify:

- close event arriving after same-regime heartbeats still maps to the original entry epoch
- previous-epoch close does not poison the new epoch
- unresolved-context block clears on the next stable epoch reset
- replay or ordered scenario does not produce durable cross-epoch poisoning

What would falsify the design:

- same-regime heartbeat changing comparison outcome
- unresolved-context block persisting past a valid epoch reset
- boundary ordering creating permanent false embargo

### Manual production-admission verification

Before enabling the feature in production behavior, verify:

- representative replay or test environment close events carry `entry_regime_epoch_ref`
- representative replay or test environment preserves `trade_id` on `EVT:POSITION_CLOSED`
- qualifying net-loss closes trigger blocks only in the correct epoch
- non-qualifying closes do not trigger blocks
- missing critical context causes explicit fail-closed block, not silent continuation
- `enabled=false` cleanly disables the feature and serves as the rollback switch

What would falsify the design:

- widespread unresolved-context blocks on otherwise healthy data paths
- inability to disable the feature cleanly with the kill switch
- evidence that current production close paths do not reliably carry the required causal context

## 11. Risks / unproven areas

Regime-boundary ordering risk:

- a close from the previous epoch may be processed near a new regime event boundary
- replay and ordered-scenario validation are required to prove this does not create durable false blocks

Same-label consecutive epoch support is absent:

- this package defines epoch transitions from `changed == true`
- same-label consecutive epoch modeling is a separate upstream problem and is out of scope here

Compatibility paths may produce null entry epoch:

- older or incomplete paths may not yet propagate `regime_epoch_ref`
- when the feature is enabled, that must become an explicit fail-closed blocked state for the symbol, not a silent skip

Production behavior risk:

- once enabled, this package blocks live entries
- the rollback mechanism is the hard kill switch `enabled=false`
- production admission criteria must therefore be satisfied before enablement

## 12. Out of scope

The following are explicitly out of scope:

- same-label consecutive epoch redesign
- sidecar expansion
- per-strategy scope
- broad `regime_detector` redesign
- `execution_position`-owned policy latch
- code implementation in this document

## 13. Implementation sequence

1. Contract surfaces
- Purpose: define strict contracts before runtime propagation depends on them
- Affected files: `trade_intent_v1.json`, `position_closed_v1.json`, `verb_registry_v1.yaml`, `execution_position/domain_dict.json`, `decision_making/domain_dict.json`
- Validation target: schema acceptance, required field coverage, registry ownership, dictionary consistency

2. Dedicated embargo module
- Purpose: centralize the policy core in one isolated `decision_making` component
- Affected files: `decision_making/regime_loss_embargo.py`, `config_models.py`, `normalized_reject_reasons.py`
- Validation target: one policy module owns epoch, latch, fail-closed, and block-decision logic; config surface stays minimal

3. DM epoch maintenance hook
- Purpose: forward regime facts into the policy core without smearing policy logic into event handlers
- Affected files: `decision_making/event_handlers.py`, `decision_making/decision_making.py`
- Validation target: regime hook is thin; epoch minting and reset logic live in the dedicated module

4. Intent propagation
- Purpose: carry entry-time epoch context across the DM -> EP boundary
- Affected files: `decision_making/schemas/trade_intent_v1.json`, `decision_making/intent_builder.py`, `execution_position/open_executor.py`
- Validation target: schema update is a prerequisite, not a follow-up; the strict trade-intent schema must accept `regime_epoch_ref` before runtime propagation, and the field must then be present on the normal open path and cached in EP state

5. EP close event emission
- Purpose: expose terminal close truth plus cached entry epoch through a real execution contract
- Affected files: `execution_position/event_handlers.py`, `execution_position/schemas/position_closed_v1.json`, `verb_registry_v1.yaml`, `execution_position/domain_dict.json`
- Validation target: `EVT:POSITION_CLOSED` is emitted on terminal close with required fields, including runtime-critical `trade_id`

6. DM integration hook for close facts
- Purpose: forward terminal close facts into the policy core and let it decide latch vs fail-closed block
- Affected files: `decision_making/event_handlers.py`, `decision_making/decision_making.py`
- Validation target: close hook is thin; policy core owns the business decision

7. Gateway integration hook
- Purpose: enforce the policy at the shared entry gate
- Affected files: `decision_making/strategy_gateway.py`
- Validation target: gateway queries the policy core, rejects only new entries, and does not duplicate business logic

8. Tests
- Purpose: prove contracts, unit behavior, integration flow, and boundary-order handling
- Affected files: targeted tests in `tests/domains/decision_making/`, `tests/domains/execution_position/`, and contract-schema test coverage
- Validation target: all contract, unit, integration, and replay checks are green

9. Production admission criteria
- Purpose: define the enablement gate for a feature that blocks live entries when on
- Affected files: docs, release notes, and deployment config when implementation lands
- Validation target: required causal context proven on representative paths, fail-closed behavior understood, kill switch verified, and operator documentation updated before enablement

## 14. Definition of ready-for-implementation

This plan is ready for implementation when all of the following are true:

- the contract surface is agreed: additive `regime_epoch_ref` on trade intent and promoted `EVT:POSITION_CLOSED`
- the ownership split is fixed: `decision_making` owns epoch semantics and policy, `execution_position` owns terminal close truth, `StrategyGateway` owns enforcement
- the dedicated policy module boundary is accepted
- the config surface is reduced to `enabled` and `min_loss_threshold_net`
- fail-closed symbol-level behavior is explicit and accepted
- test coverage is defined for contracts, unit behavior, integration, and boundary ordering
- production admission criteria are defined before enablement
