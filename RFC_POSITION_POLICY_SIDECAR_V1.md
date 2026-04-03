# RFC_POSITION_POLICY_SIDECAR_V1

## 1. Executive Summary

This RFC defines the narrowest survivable v1 for an open-position policy sidecar in Aurora/Phenix.

The recommended Phase-1 shape is:

- location: a new standalone module inside `execution_position`
- role: additive evaluator for already-open positions
- state: derived local cache only
- output: recommendation-only event/trace, not direct execution
- action scope: soft early-loss close recommendations only
- forbidden in Phase 1: exact close-by-id, partial reduce requests, bracket mutation, TP replacement, target extension, stop tightening, regime mutation, and macro/BTC-led action logic

The RFC is intentionally conservative because current runtime truth is conservative:

- `ManageFlowFSM` remains open-position and bracket SSOT
- `CloseExecutor` remains close executor
- `OrderGuardian` remains cleanup/reconcile owner
- current `CMD:CLOSE`/`DEC:CLOSE` is symbol-scoped reduce-only close, not lifecycle-targeted close
- no proven executable `position_id` exists
- `ExitManager` is already an active incumbent in overlapping post-entry territory

The Phase-1 recommendation is therefore:

- ship the sidecar as a separate file/module in `execution_position`
- let it subscribe to existing events and compute bounded derived signals
- let it emit structured recommendations and suppression traces only
- defer any action-bearing behavior to a later phase where an EP-internal request surface and stronger close attribution exist

## 2. FACTS

- `ManageFlowFSM` owns local position/bracket lifecycle truth, including `position_qty`, `position_side`, bracket ids, `position_open_ts`, and `_closing_position`.
- `CloseFlowFSM` is a command-to-decision path for explicit close routing, not an autonomous close-policy engine.
- `CloseExecutor.execute_close()` closes current live symbol exposure using `symbol` plus optional `qty`; it does not target by lifecycle/order/position id.
- `OrderGuardian` owns cleanup and close reconciliation aftermath, and distinguishes tidy-only cleanup from business close reconciliation.
- Current `CMD:CLOSE`/`DEC:CLOSE` semantics are symbol-scoped reduce-only close.
- No proven executable `position_id` contract exists.
- Lifecycle-like identities such as `idempotent_key`, `clientOrderId`, `exchangeOrderId`, and derived `lifecycle_id` are correlation/observability surfaces, not current close targets.
- `ManageFlowFSM` already owns active post-entry mechanisms such as TP1/TP2 handling, SL handling, trailing stop replacement, and max-hold close emission.
- `ExitManager` is a live Aurora post-entry evaluator. Its force-exit branches feed flip orchestration and eventually the current reduce-only close flow.
- `ExitManager` stop-tighten override is proven as signal payload mutation, but exchange-side bracket mutation from that path remains unproven.
- Structural regime truth is symbol-local and detector-owned. The detector does not expose a true onset/mature/peak/fade lifecycle model; only indirect hints are present.
- `EVT:FEATURES_CALCULATED` and `EVT:REGIME_DETECTED` already expose enough local context to derive open-position pressure signals, including regime confidence, raw-vs-stable divergence, OBI, TFI, delta price, liquidity, and price motion.
- BTC/anchor/macro context already exists elsewhere and can already affect decisions indirectly; reintroducing it inside a new sidecar would risk hidden double-counting.

## 3. Problem Statement

Current runtime has execution truth and several incumbent post-entry policies, but it does not have a single, explicit, additive module whose sole responsibility is:

- observe an already-open position,
- combine live execution-local context with local structural regime and local features,
- explain whether the position still deserves to be held,
- and do so without becoming a new state owner or fighting current close logic.

This gap matters most for positions that are already open but not yet in a clearly favorable state. The system already has:

- bracket exits,
- trailing stop logic,
- max-hold close,
- regime-flip close,
- and Aurora `ExitManager`.

What it does not yet have as a first-class component is a bounded, explainable, additive "position life" evaluator focused on soft early-loss governance and conviction decay.

## 4. Goals and Non-Goals

### Goals

- Add a separate module/file for open-position life evaluation.
- Reuse current execution owners rather than replacing them.
- Keep all Phase-1 logic symbol-local and additive-only.
- Make sidecar judgments explainable and replay-friendly.
- Create a narrow v1 that can be validated in shadow mode before any action-bearing rollout.

### Non-Goals

- no new execution FSM
- no new lifecycle truth owner
- no exact close-by-id behavior
- no bracket mutation
- no TP replacement or extension in Phase 1
- no stop tightening in Phase 1
- no detector-level regime mutation
- no macro/BTC context reinvention
- no broad refactor across `decision_making` and `execution_position`

## 5. Hard Constraints

- `ManageFlowFSM` remains the current local SSOT for open-position and bracket lifecycle.
- `CloseExecutor` remains the imperative close execution owner.
- `OrderGuardian` remains cleanup/reconcile owner.
- Current `CMD:CLOSE` / `DEC:CLOSE` semantics remain symbol-scoped reduce-only close.
- No exact close-by-id claim is allowed in this RFC.
- No proven executable `position_id` is assumed.
- `ExitManager` is treated as active overlapping territory.
- The sidecar remains additive-only and derived-context only.
- Phase 1 must not silently override incumbent close owners.
- Phase 1 must not use macro/BTC/anchor context as hidden action-bearing signal.

## 6. Phase-1 Design Decisions

### DESIGN DECISION 1: The sidecar is a separate module inside `execution_position`

Cause:
- The sidecar needs the closest possible access to real open-position truth, bracket state, and close-in-progress state.

Mechanism:
- Create one new module such as `apps/reference/domains/execution_position/position_policy_sidecar.py`.
- The module registers its own event listeners and keeps a derived per-symbol cache.
- It reads incumbent EP state but does not own or overwrite it.

Effect:
- The sidecar sits near the real lifecycle owner while remaining a separate file/module.

Operational risk:
- The module could still become a shadow owner if it starts caching authoritative state.

Why acceptable for Phase 1:
- The RFC explicitly forbids authoritative state ownership and keeps the sidecar recommendation-only.

### DESIGN DECISION 2: Phase 1 output posture is recommendation-only

Cause:
- Current close reuse is safe only for symbol-scoped reduce-only behavior, and current public contracts are not strong enough to support exact-target action safely.

Mechanism:
- The sidecar emits structured recommendation/suppression telemetry only.
- It does not emit `CMD:CLOSE`, `DEC:CLOSE`, or partial-reduce requests in Phase 1.

Effect:
- Phase 1 cannot directly cause a bad close; it can only reveal whether the policy is useful and explainable.

Operational risk:
- Recommendation-only rollout delays business impact.

Why acceptable for Phase 1:
- This is the narrowest diagnosable and reversible posture, and it avoids pretending current contracts are stronger than they are.

### DESIGN DECISION 3: Phase-1 business scope is soft early-loss governance only

Cause:
- Positive-position management overlaps heavily with trailing, TP, and bracket ownership. Losing or flat-to-losing positions are the cleanest first scope.

Mechanism:
- The sidecar only evaluates whether an already-open position that is flat-to-losing is deteriorating enough to justify a soft-close recommendation.
- It does not manage winners, runners, TP extension, or target replacement.

Effect:
- The first version concentrates on reducing avoidable loss rather than optimizing already-profitable lifecycle behavior.

Operational risk:
- Some useful profitable-position management is deferred.

Why acceptable for Phase 1:
- It minimizes overlap with current bracket and trailing owners.

### DESIGN DECISION 4: Action-bearing context remains local-symbol and bar-aligned

Cause:
- Structural regime truth is bar-clocked and local-symbol scoped. Tick-only or macro-heavy policy would add noise and hidden coupling.

Mechanism:
- The sidecar updates caches event-by-event.
- Recommendation-bearing evaluation is only allowed when a fresh local `EVT:FEATURES_CALCULATED` and local `EVT:REGIME_DETECTED` context exists.
- Macro/BTC/anchor features are excluded from Phase-1 action-bearing logic.

Effect:
- The sidecar stays aligned with existing local-symbol regime semantics and replay-friendly bar cadence.

Operational risk:
- Some very fast adverse microstructure transitions may be caught later than a tick-driven design.

Why acceptable for Phase 1:
- Stability and explainability matter more than speed for the first rollout.

### DESIGN DECISION 5: Derived signals are bounded, capped, and advisory

Cause:
- Current runtime does not expose an explicit lifecycle phase model, so the sidecar must derive cautious hints rather than claim new structural truth.

Mechanism:
- Compute bounded derived scores only.
- No single input can dominate the composite pressure signal.
- Stale or weak evidence clamps recommendations toward neutral/silent behavior.

Effect:
- The sidecar behaves as a policy interpreter, not a new truth source.

Operational risk:
- Conservative capping may under-react at first.

Why acceptable for Phase 1:
- Under-reaction in shadow mode is safer than overreaction that would close valid positions.

### Ownership split for Phase 1

| Responsibility | Phase-1 owner |
| --- | --- |
| State owner | `ManageFlowFSM` |
| Evaluator | `PositionPolicySidecar` |
| Action requester | none in Phase 1 |
| Action executor | `CloseExecutor` |
| Reconciliation owner | `OrderGuardian` |
| Observability owner | sidecar for policy traces, existing EP/DM surfaces for execution outcome traces |

## 7. Chosen Owner Location

### Option comparison

| Option | Fit | Why rejected or accepted |
| --- | --- | --- |
| New file inside `execution_position` | Best | closest to live position/bracket truth, lowest SSOT conflict, easiest to suppress against close-in-progress and reconcile state |
| New file inside `decision_making` | Weak for Phase 1 | overlaps `ExitManager`, would need cross-domain truth borrowing, weaker view of bracket/close-in-progress truth |
| Strategy-local overlay | Weak | duplicates logic across strategies and sits too far from execution lifecycle truth |
| Separate domain/service | Worst for Phase 1 | current public contracts are too weak for race-safe external lifecycle actioning |

### Chosen location

`execution_position`

Recommended module path:

- `apps/reference/domains/execution_position/position_policy_sidecar.py`

Rationale:

- It preserves the separate-file concept.
- It keeps the sidecar close to real lifecycle truth without making it the truth owner.
- It reduces overlap and race exposure compared with `decision_making`.

## 8. Chosen Output Contract

### Phase-1 default

Option A: recommendation-only event

### Exact Phase-1 outward contract

The sidecar may emit an internal structured recommendation trace such as:

`EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`

with a payload shape equivalent to:

| Field | Meaning |
| --- | --- |
| `ts_ms` | evaluation timestamp |
| `symbol` | current symbol |
| `sidecar_version` | policy version |
| `evaluation_mode` | `observe_only` |
| `recommended_action` | `HOLD` or `SOFT_CLOSE_RECOMMENDED` |
| `target_mode` | always `symbol_current_net_only` |
| `requested_qty` | always `null` in Phase 1 |
| `reason_codes` | bounded list of human-readable reason keys |
| `position_snapshot` | side, qty, entry price, age |
| `score_snapshot` | derived signal block |
| `regime_ref` | latest local regime fields used |
| `feature_ref` | latest feature timestamps and selected fields |

### What Phase 1 is not allowed to do

- emit `CMD:CLOSE`
- emit `DEC:CLOSE`
- emit partial-reduce requests
- mutate brackets
- mutate trailing state
- claim exact lifecycle targeting

### Deferred safe action posture

The first action-bearing posture is deferred to Phase 2 and should be:

- an EP-internal recommendation object translated by existing EP owner logic into current symbol-scoped `CMD:CLOSE`

That later posture is intentionally not Phase 1.

## 9. Chosen In-Scope Behaviors

### Phase-1 ranking

| Candidate behavior | Phase-1 status | Why |
| --- | --- | --- |
| Soft early loss cut | In scope | narrowest actionable business problem with lowest overlap against bracket owner surfaces |
| Hold-vs-close pressure | In scope | core evaluator output needed to justify soft early-close recommendations |
| Conviction decay | In scope | useful derived interpretation of weakening local evidence |
| Regime exhaustion awareness | In scope as hint only | allowed as policy interpretation of local regime confidence/divergence, not new regime truth |
| Reduce pressure | Diagnostic only | current close contract can reduce by qty, but Phase 1 should not use that action path |
| Target extension | Deferred | overlaps TP/bracket ownership too strongly |
| Target replacement | Out of scope | requires new bracket mutation contract |
| Stop tightening | Out of scope | trailing owner already exists in `ManageFlowFSM` and `ExitManager` overlap is unresolved |
| Runner preservation | Deferred | profitable-position management is not Phase-1-safe scope |

### Phase-1 business question

For a currently open symbol position that is not clearly profitable and has no incumbent close already in progress:

- should the sidecar stay silent, or
- should it emit a soft-close recommendation because local evidence has deteriorated materially?

## 10. Event Subscription Contract

### Required subscriptions

| Event | Fields consumed | Why needed | Freshness requirement | Phase-1 status |
| --- | --- | --- | --- | --- |
| `EVT:PORTFOLIO_STATE_UPDATED` | `positions_last_ts_ms`, `positions[].symbol`, `positions[].net_position`, `positions[].avg_entry_price` | confirm symbol is truly open/flat and recover current net exposure snapshot | must be the latest seen portfolio snapshot for symbol | Required |
| `EVT:ORDER_FILL` | `symbol`, `orderId`/`clientOrderId`, `tradeId`, `side`, `filled_qty`/`qty`, `price`, `ts_ms` | detect entry fills, partial exits, and terminal bracket fills | use latest fill state; stale fills are historical only | Required |
| `EVT:ORDER_STATE_CHANGED` | `symbol`, `status`, `terminal_non_fill`, `terminal_state_kind`, `canonical_identity_key`, `event_ts_ms` | understand terminal/non-fill transitions and close-order progression | must be latest order-state event per symbol/order identity | Required |
| `EVT:EXECUTION_CLOSE_RECONCILED` | `symbol`, `rid`, `source`, `why`, `ts_ms` | stop evaluation after authoritative business-close reconcile | authoritative terminal cleanup signal | Required |
| `EVT:REGIME_DETECTED` | `symbol`, `regime`, `confidence`, `raw_regime`, `raw_confidence`, `stable_confidence`, `changed`, `last_update_ts_ms`, `hysteresis_confirm_count` | local structural regime confirmation and exhaustion hints | action-bearing evaluation requires fresh regime snapshot no older than one bar window | Required |
| `EVT:FEATURES_CALCULATED` | `symbol`, `tf_sec`, `ts`, `features.obi`, `features.tfi`, `features.delta_price`, `features.price`, `features.liquidity_kappa`, `price_motion.ret_10s`, `ret_60s`, `ret_300s`, `pm_norm_10s`, `pm_norm_60s`, `pm_norm_300s`, `warmup.full_ready` | local microstructure and price-adversity context | action-bearing evaluation requires fresh local feature snapshot on current bar clock | Required |

### Optional subscriptions

| Event | Why optional |
| --- | --- |
| `EVT:TRADE_EXECUTED` | cleaner trade-level correlation for entry confirmation and post-trade diagnostics |
| `EVT:EXIT_MATCH_ATTEMPTED` | forensic visibility into bracket match handling |
| `EVT:EXIT_MATCH_FAILED` | forensic visibility when exit fills do not match local expectation |

### Explicit exclusions from Phase-1 action-bearing logic

- `macro_sync`
- `macro_resid`
- anchor/BTC-derived context
- `absorption` as action-bearing input
- tick-only feature events

These may be logged diagnostically later, but they do not contribute to Phase-1 soft-close recommendations.

## 11. Internal Derived Signals

| Signal | Range | Meaning | Phase-1 use | Evidence feeds | Bound/cap |
| --- | --- | --- | --- | --- | --- |
| `position_health_score` | `[-1, 1]` | overall health of the current open position | diagnostic summary | current side vs local regime, confidence, price vs entry, local feature posture | no single component > `0.4` absolute contribution |
| `exit_pressure_score` | `[0, 1]` | aggregate pressure to stop holding | recommendation-bearing | capped blend of microstructure adversity, conviction decay, and regime weakening | capped and neutralized on stale context |
| `hold_confidence` | `[0, 1]` | confidence that hold remains acceptable | diagnostic and suppression aid | inverse of adverse pressure under fresh context | cannot override close-in-progress suppression |
| `reduce_pressure` | `[0, 1]` | signal that a smaller position might be better than full hold | diagnostic only | same evidence as exit pressure with lower threshold semantics | no action in Phase 1 |
| `soft_close_pressure` | `[0, 1]` | pressure specifically supporting a soft close recommendation | recommendation-bearing | non-profitable position + adverse microstructure + weakening local regime | zeroed if position already clearly profitable |
| `regime_exhaustion_hint` | `[0, 1]` | policy hint that local regime support is weakening | diagnostic input | low stable confidence, raw/stable divergence, recent regime change, confidence decay | never treated as structural regime truth |
| `microstructure_adverse_pressure` | `[0, 1]` | short-horizon local deterioration | diagnostic input | OBI, TFI, delta_price, liquidity_kappa, price_motion | capped and disabled on stale feature snapshot |

### Interpretation rules

- No signal becomes structural truth.
- No signal may directly mutate brackets or regime.
- `soft_close_pressure` is only meaningful when the position is flat-to-losing or only trivially profitable.
- Phase-1 recommendations require both:
  - sufficient adverse evidence, and
  - no active incumbent suppression condition.

## 12. Suppression / Precedence Rules

### Incumbents that always win

| Incumbent surface | Rule |
| --- | --- |
| Bracket fill handling | always wins |
| `_closing_position` / local close-in-progress | always wins |
| Existing close hardening / duplicate suppression | always wins |
| Max-hold close | always wins |
| Regime-flip close already in progress inside EP | always wins |
| Trailing stop replacement | always wins |
| Reconcile / tidy aftermath | always wins |

### When the sidecar must stay silent

- no active lifecycle for the symbol
- `_closing_position == true`
- authoritative close reconcile already observed
- bracket exit just matched or terminal exit handling just ran
- latest feature snapshot missing or stale
- latest regime snapshot missing or stale
- feature warmup not ready
- entry stabilization grace window not passed
- position is already clearly profitable
- local state is ambiguous after partial fills or degraded order identity

### Ordering rule

Within `execution_position`, incumbent lifecycle logic must run before sidecar recommendation evaluation on the same symbol event. That means:

1. bracket/terminal fill handling
2. trailing/max-hold incumbent logic
3. close-in-progress and lifecycle truth updates
4. sidecar evaluation

This ordering prevents the sidecar from emitting recommendations against state that incumbents have already resolved.

### Suppression logging

Every silent decision under a live suppression condition must emit a structured suppression trace with:

- `symbol`
- `suppression_reason`
- `incumbent_owner`
- `position_snapshot`
- `latest_feature_ts_ms`
- `latest_regime_ts_ms`
- `trace_id`

## 13. Observability Contract

### Required Phase-1 traces

| Trace surface | Purpose | Required fields |
| --- | --- | --- |
| `EVT:POSITION_POLICY_SIDECAR_EVALUATED` | prove the sidecar actually evaluated | `trace_id`, `ts_ms`, `symbol`, `evaluation_mode`, `position_snapshot`, `feature_ref`, `regime_ref` |
| `EVT:POSITION_POLICY_SIDECAR_SCORES` | show why the recommendation did or did not emerge | `trace_id`, `score_snapshot`, `reason_codes`, `freshness_snapshot` |
| `EVT:POSITION_POLICY_SIDECAR_SUPPRESSED` | explain why the sidecar stayed silent | `trace_id`, `symbol`, `suppression_reason`, `incumbent_owner`, `position_snapshot` |
| `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED` | record the emitted recommendation | `trace_id`, `symbol`, `recommended_action`, `target_mode`, `reason_codes`, `score_snapshot` |

### Minimum fields that matter

- `trace_id`
- `symbol`
- `sidecar_version`
- `evaluation_mode`
- `position_side`
- `position_qty`
- `entry_price`
- `position_age_sec`
- `feature_ts_ms`
- `regime_ts_ms`
- `portfolio_ts_ms`
- `recommended_action`
- `reason_codes`
- all derived scores used in the decision

### What remains impossible in Phase 1

Without a future identity contract, Phase 1 cannot unambiguously claim:

- "this exact lifecycle instance was the target of a close command"
- "this exact order/position was selected by id"

That is acceptable because Phase 1 does not request action.

## 14. Phase Plan

| Phase | Allowed outputs | Forbidden outputs | Required validation | Required observability | Rollback posture |
| --- | --- | --- | --- | --- | --- |
| Phase 1 | recommendation-only telemetry and structured score snapshots | any close/reduce request, bracket mutation, TP mutation, stop mutation | shadow replay and live shadow validation | all sidecar eval/suppression/recommendation traces | disable listener / feature flag off |
| Phase 2 | EP-internal soft-close request for full symbol-scoped close only | close-by-id, partial reduce, bracket mutation, target mutation | shadow-to-request comparison, duplicate suppression verification, overlap audit with `ExitManager` | request trace plus EP acceptance/suppression/outcome linkage | revert to recommendation-only |
| Phase 3 | only after new contracts: possibly partial reduce, target mutation, or richer lifecycle targeting | anything unsupported by newly added contracts | contract tests, replay, failure-mode drills, operator explainability signoff | full request-to-execution-to-reconcile attribution | roll back to Phase 2 posture |

## 15. Rejected Options

- Put the sidecar in `decision_making` for Phase 1.
  - Rejected because it overlaps `ExitManager` too directly and sits too far from execution truth.
- Make the sidecar a separate service/domain immediately.
  - Rejected because current public contracts are not strong enough for race-safe external actioning.
- Let Phase 1 emit direct `CMD:CLOSE`.
  - Rejected because the current close contract is symbol-scoped only and current observability is not yet sufficient.
- Let Phase 1 emit partial-reduce requests.
  - Rejected because partial reduce overlaps target/bracket ownership and would be harder to attribute safely.
- Use macro/BTC/anchor-derived signals in Phase-1 action logic.
  - Rejected because that risks hidden double-counting against existing macro surfaces.
- Use target extension or TP replacement in Phase 1.
  - Rejected because current runtime does not prove a safe bounded contract for it.

## 16. Open Questions / Unknowns

### ASSUMPTIONS

- A bar-aligned, recommendation-only Phase 1 is acceptable even if it captures fewer ultra-fast adverse turns than a tick-driven design.
- Current local feature payloads are sufficiently stable to support recommendation-quality, not execution-quality, pressure scoring.
- Keeping profitable-position management out of Phase 1 is acceptable in exchange for lower overlap risk.

### UNKNOWNS

- Whether `ExitManager` stop-tighten semantics should later map to live bracket mutation remains unresolved.
- Whether a future EP-internal action request needs a new explicit internal schema or can safely use a typed in-process object only remains unresolved.
- Whether exact lifecycle targeting will ever be required for the business goal remains unresolved.
- Whether future partial-reduce behavior should belong to the sidecar at all remains unresolved.

## 17. Final Recommendation

Build Phase 1 as a separate module inside `execution_position`, keep it recommendation-only, and scope it to soft early-loss governance for already-open positions that are not clearly profitable.

Do not let Phase 1 emit direct close commands. Do not let it manage winners. Do not let it touch brackets. Do not let it pretend close-by-id exists.

If Phase 1 produces stable, explainable recommendations with low overlap noise, then Phase 2 can introduce a guarded EP-internal request path that reuses current symbol-scoped close flow. Anything beyond that requires new contracts, especially if the product ambition expands toward partial reduce, bracket mutation, or exact lifecycle targeting.
