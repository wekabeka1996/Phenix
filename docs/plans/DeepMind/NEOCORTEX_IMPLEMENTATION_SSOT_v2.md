# NEOCORTEX Implementation SSOT v2

> Active implementation source of truth for integrating Neocortex into Aurora/Phenix as a bounded adaptive trust controller.

- Status: `ACTIVE_SSOT`
- Scope: `neocortex`, `decision_making`, `execution_position`, `vfoundation`, config, WAL, offline evaluation
- Historical context: `docs/_archive/neocortex/DeepMind_RnD_Almanac_v2.1.md` is archived context only and is not an active SSOT
- Language: Ukrainian with English runtime identifiers
- Change control: if this document conflicts with archived R&D notes, speculative docs, or incomplete experiments, this document wins for implementation decisions

## 1. Governance

This document is an implementation SSOT, not a manifesto and not a research diary. Every runtime-facing decision below is intended to be executable against the current codebase.

### 1.1 Hard rules

1. No invented event, command, or config key is canonical unless it is either:
   - already present in the codebase, or
   - marked `NEW_CONTRACT` with an explicit owner, producer, consumer, persistence rule, and acceptance gate.
2. No section may claim `VERIFIED_COMPLETE` without an artifact anchor in code, tests, or reports.
3. Neocortex must not emit direct `CMD:*` into live runtime.
4. Live authority must never bypass existing hard safety, panic, exchange, or reduce-only exit paths.
5. Runtime decisions must fail closed to baseline YAML behavior when authority is unavailable, stale, timed out, disabled, or contract-invalid.

### 1.2 Document intent

The target system is not an end-to-end AI trader. It is a bounded authority seam over the existing Aurora decision pipeline:

- `alpha_search` and the existing strategy stack remain the data plane.
- `decision_making` remains the authoritative pre-execution orchestrator.
- `execution_position` remains the only owner of order and position lifecycle.
- `neocortex` gains bounded authority only at a single pre-intent seam and only under explicit rollout gates.

## 2. Reality Baseline

The following baseline is normative. The target design must start from these facts, not from idealized architecture.

| Subsystem | Current reality | Code anchors | Implication for target design |
| --- | --- | --- | --- |
| `neocortex` runtime mode | Domain is `type: shadow`; startup shadow gates forbid advisory and live authority | `apps/reference/domains/neocortex/domain.yaml`, `apps/reference/domains/neocortex/config/neuro.yaml`, `apps/reference/domains/neocortex/logic/gates/shadow.py` | Live authority is not a toggle flip. It requires a new bounded seam and a new config contract. |
| `neocortex` learning contract | `policy_training_mode=disabled`, `reward_mode=regime_oracle`, `sequence.inference_mode=stateless_per_event`, world model is instantiated with `action_dim=0`, world-model training is skipped | `apps/reference/domains/neocortex/config/neuro.yaml`, `apps/reference/domains/neocortex/logic/brain/core.py` | Current learner is not a live authority controller and not an action-conditioned world model. |
| `decision_making` pre-intent boundary | `StrategyGateway` runs a canonical gate chain and, once passed, directly calls `_propose_trade_intent()` | `apps/reference/domains/decision_making/strategy_gateway.py`, `apps/reference/domains/decision_making/decision_making.py` | The only safe place for authority injection is between gate-chain success and intent emission. |
| `decision_making` intent emission | `IntentBuilder` writes WAL and then emits `EVT:TRADE_INTENT_PROPOSED` inline through the FSM | `apps/reference/domains/decision_making/intent_builder.py` | Authority must resolve before this point; async bus-only control is too late. |
| `execution_position` intake | `IntentRouter` consumes `EVT:TRADE_INTENT_PROPOSED` and routes it directly to `CMD:OPEN` or `CMD:CLOSE` | `apps/reference/domains/execution_position/intent_router.py` | Neocortex must not be wired below this seam if it needs real veto power. |
| Panic safety | `panic_killswitch` blocks new `CMD:OPEN` and cancels pending entries; it is not a Neocortex-specific authority switch | `apps/reference/domains/execution_position/fsm_open.py`, `apps/reference/domains/execution_position/entry_manager.py` | A separate `neocortex.trust_enabled` authority switch is required. |
| Runtime delivery | `FSMCore.emit()` runs listeners inline; callbacks are not deadline-aware bus workers | `vfoundation/core/fsm_core.py` | Authority must be a synchronous bridge call owned by `decision_making`, not eventual consistency over `EVT:*`. |
| Router durability | `Router.route()` writes WAL before handler execution and already supports expiry and `idempotent_key` semantics | `vfoundation/core/routing.py` | New authority contracts should reuse existing idempotency and timeout semantics where possible. |
| Offline ingest | `MultiTailer` processes features, orders, and core logs in separate passes; rewards are finalized at position close | `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py` | Offline dataset assembly must add a real event-time merge and a decision-centric ledger. |
| Missingness handling | feature parsing zero-imputes missing and non-finite values | `apps/reference/domains/neocortex/logic/ingest/parser.py` | Missingness must become explicit metadata; zero alone is not enough. |

## 3. Canonical Event Chain

This section is the core implementation chain. Each step follows the same structure:

- Current owner
- Current event or contract
- Current limitation
- Target contract
- Required delta
- Acceptance gate

### 3.1 Clock and ingress

- Current owner: `feature_engineering`, `market_data`, `decision_making`, `neocortex.logic.ingest`
- Current event or contract:
  - Live semantic ticks already exist as `EVT:FEATURES_CALCULATED`
  - `EVT:BAR_CLOSED` is allowed as a semantic clock only when it is actually emitted by the current runtime path for the active strategy
  - Offline ingest consumes feature logs, order logs, and core logs in separate passes
- Current limitation:
  - Offline reconstruction is not a strict event-time merge
  - Missingness is collapsed into zeros
  - Current ingest is market-state-heavy and does not preserve a full pre-decision authority snapshot
- Target contract:
  - `ObservationEnvelope` becomes the canonical pre-authority snapshot
  - Live `ObservationEnvelope` is built inside `decision_making` from causally prior state
  - Offline `ObservationEnvelope` mirror is built by event-time merge over features, risk, regime, portfolio, order, and close streams
- Required delta:
  - Preserve `event_ts_ms`, `event_time_source`, `event_time_is_causal`, freshness ages, and missingness masks
  - Promote portfolio, risk, regime, exposure, and system-stress state to first-class snapshot members
  - Mark rows with synthetic or non-causal time as invalid for authority training
- Acceptance gate:
  - Every authority request contains a causally prior `ObservationEnvelope`
  - No authority row may depend on future-only state
  - Freshness and missingness are explicit, not inferred from zero values

### 3.2 Strategy production

- Current owner: `alpha_search`, strategy handlers, `decision_making`
- Current event or contract:
  - `alpha_search` and upstream strategy logic produce `EVT:STRATEGY_SIGNAL_PRODUCED`
  - `decision_making` enriches signal flow with regime, risk, portfolio, QoS, and safety context
- Current limitation:
  - There is no explicit boundary between the data plane and the authority plane
  - Neocortex docs mention modulation proposals, but the live signal-to-intent path does not consume them
- Target contract:
  - `alpha_search` remains the data plane only
  - Neocortex consumes a candidate intent summary after Aurora has already produced a direction, sizing proposal, and provenance
- Required delta:
  - `ControlDecisionRequest` must include signal provenance, regime provenance, risk snapshot, and current candidate intent summary
  - Neocortex must not propose direction, strategy assignment, or raw alpha
- Acceptance gate:
  - Authority can only allow, deny, or boundedly modulate a baseline Aurora candidate
  - No Neocortex path may become an alternative alpha generator

### 3.3 Gate chain and pre-authority snapshot

- Current owner: `apps/reference/domains/decision_making/strategy_gateway.py`
- Current event or contract:
  - Canonical gate chain order is `arbitration -> risk_skew_pre -> risk -> risk_skew_post -> flip -> qos -> exposure -> ttl -> warmup -> safety`
  - After `chain_result.passed`, `decision_making` directly calls `_propose_trade_intent()`
- Current limitation:
  - There is no synchronous authority seam between gate success and intent emission
  - The candidate intent is not materialized into a decision-centric request object
- Target contract:
  - Build `ObservationEnvelope` and `ControlDecisionRequest` immediately after gate-chain success and before `_propose_trade_intent()`
  - This seam applies only to new-risk intents
- Required delta:
  - Add a helper in `decision_making` to build `ObservationEnvelope` from the passed gate context
  - Reduce-only closes, protective closes, panic flows, and exchange recovery paths bypass authority
  - Flip orchestration applies authority only to the reopen or new-risk side, never to the safety close leg
- Acceptance gate:
  - No non-reduce-only candidate may reach `_propose_trade_intent()` without either a valid authority response or a documented fallback result
  - Reduce-only and emergency exits remain unaffected

### 3.4 Authority seam

- Current owner: none in live runtime; current `neocortex` is shadow-only
- Current event or contract:
  - Existing docs define `EVT:NEOCORTEX_MODULATION_PROPOSED` for future gated phases
  - Current live path has no synchronous Neocortex contract
- Current limitation:
  - Async bus control would be a late critic
  - `FSMCore.emit()` is inline, so adding an `AWAITING_*` event alone does not solve deadline ownership
- Target contract:
  - `NEW_CONTRACT`: `NeocortexAuthorityBridge.decide(request: ControlDecisionRequest) -> ControlDecisionResponse`
  - The bridge is invoked synchronously by `decision_making`
  - `decision_making` owns the deadline and the fallback decision
- Required delta:
  - Add `neocortex.trust_enabled`
  - Add `neocortex.authority.mode = shadow|advisory|gated`
  - Add `neocortex.authority.deadline_ms`
  - Add `neocortex.authority.max_inflight_per_symbol`
  - Bridge unavailable, authority disabled, timeout, stale response, or contract violation must all resolve to baseline fallback
- Acceptance gate:
  - Responses returned after `expires_at_ms` are ignored and logged as late
  - No response may retroactively alter a decision after baseline fallback has fired
  - `decision_making` must remain responsive under the configured deadline

### 3.5 Intent emission

- Current owner: `decision_making.IntentBuilder`
- Current event or contract:
  - WAL append occurs before `EVT:TRADE_INTENT_PROPOSED`
  - Arbitration commit occurs only after durability and emit succeed
- Current limitation:
  - There is only one emission path and no decision-centric authority journal
- Target contract:
  - `ControlDecisionResponse.action` is one of `allow | deny | modulate | fallback`
  - Canonical apply rules:
    - `allow`: emit the current candidate intent as-is
    - `deny`: do not emit `EVT:TRADE_INTENT_PROPOSED`; write a decision-local authority veto record
    - `modulate`: emit the current candidate intent as-is and persist a bounded overlay for future semantic ticks only
    - `fallback`: ignore authority output and proceed with baseline YAML behavior
- Required delta:
  - Write an authority request or response journal before any live effect
  - Attach `authority_context` to emitted intents that survive the seam
  - Add explicit `NEOCORTEX_VETO` and fallback reason codes to decision-local truth artifacts
- Acceptance gate:
  - Every critical request yields exactly one apply result
  - Denied intents never reach `execution_position`
  - Modulation never mutates current YAML or structural strategy assignment

### 3.6 Execution path

- Current owner: `execution_position`
- Current event or contract:
  - `IntentRouter` maps `EVT:TRADE_INTENT_PROPOSED` to `CMD:OPEN` or `CMD:CLOSE`
  - `panic_killswitch` blocks new opens
- Current limitation:
  - `execution_position` has no concept of authority request or fallback outcome
- Target contract:
  - `execution_position` remains unaware of model internals
  - It consumes only canonical trade intents plus optional correlation metadata
- Required delta:
  - Add `authority_context` fields to the intent envelope for correlation only:
    - `decision_id`
    - `authority_mode`
    - `apply_result`
  - Do not add Neocortex-specific branching inside `execution_position`
- Acceptance gate:
  - `execution_position` behavior is unchanged for accepted intents
  - Vetoes are fully resolved before the intent router boundary

### 3.7 Outcome ledger

- Current owner: split across `decision_making`, `execution_position`, `neocortex.logic.ingest`
- Current event or contract:
  - `execution_position` already tracks `lifecycle_id`, `trade_id`, `realized_pnl`, `fees`, and close reasons per symbol
  - `MultiTailer` finalizes reward only when close events arrive
- Current limitation:
  - Outcome tracking is trade-episode-centric, not authority-request-centric
  - Timeout, stale, fallback, and veto outcomes are not terminalized into a unified decision ledger
- Target contract:
  - `NEW_CONTRACT`: `DecisionOutcomeLedgerRow`
  - The row is keyed by `decision_id`
  - The row is staged at authority request time, enriched by decision emit outcomes, and finalized on terminal rejection or position close
- Required delta:
  - `decision_making` writes request, response, apply result, and downstream `rid`
  - `execution_position` continues to emit lifecycle fields and realized outcome fields
  - `neocortex` ingest finalizes the row by joining on `decision_id`, `rid`, `lifecycle_id`, and `trade_id`
- Acceptance gate:
  - Every critical request ends in exactly one terminal row with one of:
    - `EXECUTED_AND_CLOSED`
    - `VETOED`
    - `BASELINE_FALLBACK_NO_EXECUTION`
    - `BASELINE_FALLBACK_EXECUTED`
    - `REJECTED_UPSTREAM`
    - `INVALID_FOR_DATASET`

### 3.8 Offline loop

- Current owner: `neocortex` replay and learner stack
- Current event or contract:
  - Current learner is shadow-only, stateless-per-event, and not action-conditioned
- Current limitation:
  - No decision-centric causal dataset exists yet
  - Support quality and baseline-relative reward are not explicitly carried through runtime artifacts
- Target contract:
  - Offline dataset is built from `DecisionOutcomeLedgerRow + ObservationEnvelope`
  - Reward is computed offline from raw realized components and baseline estimates
  - Invalid or unsupported rows are retained with reason codes but excluded from policy optimization
- Required delta:
  - Add dataset schema versioning
  - Add support-quality markers and invalid reason codes
  - Block offline RL until baseline estimator and support checks are implemented
- Acceptance gate:
  - Offline training consumes only rows with explicit causal validity and support quality
  - No live runtime path depends on offline reward calculation

## 4. Contract Pack

Only contracts below are canonical for the authority seam. Any additional shape must be backward-compatible with these definitions.

### 4.1 `ObservationEnvelope`

- Owner: `decision_making`
- Producer: `strategy_gateway` via a dedicated pre-authority snapshot builder
- Consumer: `NeocortexAuthorityBridge`, shadow reports, offline dataset builder
- Required fields:
  - `observation_id`
  - `symbol`
  - `decision_basis_ts_ms`
  - `source_event_name`
  - `source_event_id`
  - `event_time_source`
  - `event_time_is_causal`
  - `freshness`
  - `missingness`
  - `market_features`
  - `regime_state`
  - `risk_state`
  - `portfolio_state`
  - `system_stress_state`
  - `candidate_intent_summary`
  - `gate_trace_summary`
- Idempotency:
  - `observation_id` must be stable for a single candidate decision attempt
- Deadline or TTL semantics:
  - Valid only for the current decision attempt; not reused across semantic ticks
- WAL persistence:
  - Stored through the authority request journal
- Offline visibility:
  - Fully visible to dataset builder

### 4.2 `ControlDecisionRequest`

- Owner: `decision_making`
- Producer: `decision_making`
- Consumer: `NeocortexAuthorityBridge`
- Required fields:
  - `decision_id`
  - `rid`
  - `symbol`
  - `request_kind = new_risk_intent`
  - `authority_mode`
  - `decision_basis_ts_ms`
  - `deadline_ms`
  - `expires_at_ms`
  - `observation`
  - `candidate_intent_summary`
  - `idempotent_key`
- Idempotency:
  - `idempotent_key = decision_id`
- Deadline or TTL semantics:
  - `expires_at_ms = decision_basis_ts_ms + deadline_ms`
  - Consumer must treat expired requests as non-applicable
- WAL persistence:
  - Persist before bridge invocation
- Offline visibility:
  - Fully visible

### 4.3 `ControlDecisionResponse`

- Owner: `neocortex`
- Producer: `NeocortexAuthorityBridge`
- Consumer: `decision_making`
- Required fields:
  - `decision_id`
  - `action`
  - `reason_code`
  - `reason_text`
  - `returned_at_ms`
  - `model_ref`
  - `policy_ref`
  - `idempotent_key`
  - `overlay_patch` when `action = modulate`
- Idempotency:
  - Must echo `decision_id`
- Deadline or TTL semantics:
  - If `returned_at_ms > expires_at_ms`, `decision_making` must mark the response as late and ignore it
- WAL persistence:
  - Persist on receipt before live apply
- Offline visibility:
  - Fully visible

### 4.4 `AuthorityMode`

- Owner: config
- Values:
  - `shadow`: authority requests and responses are recorded only; baseline path always executes
  - `advisory`: responses are recorded and operator-visible; baseline path always executes
  - `gated`: responses may automatically affect the candidate decision under deadline and kill-switch rules
- WAL persistence:
  - Snapshot value recorded in request journal
- Offline visibility:
  - Fully visible

### 4.5 `ModulationStoreRecord`

- Owner: `decision_making`
- Producer: `decision_making` after a valid `ControlDecisionResponse(action=modulate)`
- Consumer: `decision_making` on future semantic ticks
- Required fields:
  - `record_id`
  - `origin_decision_id`
  - `symbol_scope`
  - `created_ts_ms`
  - `effective_from_ts_ms`
  - `expires_at_ms`
  - `overlay_patch`
  - `bounds_ref`
  - `version`
  - `idempotent_key`
- Idempotency:
  - `idempotent_key` must deduplicate repeated modulation writes from the same authority response
- Deadline or TTL semantics:
  - Mandatory TTL
  - Expired records are ignored without side effects
- WAL persistence:
  - Persist in a dedicated modulation journal; do not patch YAML
- Offline visibility:
  - Fully visible

### 4.6 `DecisionOutcomeLedgerRow`

- Owner: `neocortex` evaluation pipeline
- Producer:
  - staged by `decision_making`
  - finalized by `neocortex` ingest or outcome collector
- Consumer: evaluator, dataset builder, OPE, offline RL
- Required fields:
  - `decision_id`
  - `rid`
  - `symbol`
  - `authority_mode`
  - `request_ts_ms`
  - `response_ts_ms`
  - `apply_result`
  - `fallback_reason`
  - `downstream_rid`
  - `lifecycle_id`
  - `trade_id`
  - `terminal_status`
  - `realized_pnl_net`
  - `fees`
  - `stress_metrics`
  - `support_quality`
  - `dataset_visibility`
  - `invalid_reason_code`
- Idempotency:
  - Final row keyed by `decision_id`
- Deadline or TTL semantics:
  - Row remains open until terminalized or explicitly invalidated
- WAL persistence:
  - Request and response legs are written at decision time; terminal enrichment is appended later
- Offline visibility:
  - Fully visible

## 5. Action Surface

### 5.1 Canonical live actions

- `allow`
- `deny`
- `modulate`
- `fallback`

### 5.2 Scope of authority

Authority applies only to candidate intents that:

- are non-reduce-only
- would create or re-open risk
- have already passed the baseline Aurora gate chain

Authority never applies to:

- reduce-only closes
- protective exits
- panic-killswitch flows
- exchange recovery or cleanup flows
- forced bracket cleanup

### 5.3 Modulation rules

`modulate` is bounded and future-facing:

- The current candidate is emitted as baseline Aurora intended it.
- The overlay becomes active starting on the next semantic tick.
- The overlay is stored through `ModulationStoreRecord`.

### 5.4 Allowlisted modulation knobs

Only the following knobs are allowed in v2:

- `decision_making.signal_threshold_bias`
- `decision_making.cooldown_mult`

Everything else is forbidden in v2, including:

- direct order side changes
- direct quantity changes
- strategy assignment changes
- runtime YAML mutation
- direct `CMD:*` emission by Neocortex

## 6. State Ownership

| State or responsibility | Canonical owner | Notes |
| --- | --- | --- |
| Candidate signal and gate context | `decision_making.strategy_gateway` | Neocortex consumes a snapshot; it does not own upstream gates. |
| `ObservationEnvelope` assembly | `decision_making` | Built only from causally prior state. |
| Authority deadline and fallback | `decision_making` | `FSMCore` is not the deadline owner. |
| Per-symbol hidden state | `neocortex` actor or bridge | Never shared across symbols or owned by `decision_making`. |
| `ModulationStore` | `decision_making` | Overlay only; no YAML patching. |
| Order lifecycle, `lifecycle_id`, `trade_id`, `fees`, `realized_pnl_net` | `execution_position` | Neocortex consumes these as facts. |
| `DecisionOutcomeLedgerRow` finalization | `neocortex` evaluation pipeline | Decision-time facts originate in `decision_making`; realized facts originate in `execution_position`. |
| Global panic open-block | `trading.ops.panic_killswitch` | Existing execution safety; not a Neocortex authority switch. |
| Neocortex authority switch | `neocortex.trust_enabled` | New bounded authority kill-switch. |

## 7. Data and Reward Pack

### 7.1 Event-time merge

Offline assembly must merge by `event_ts_ms`, not by file read order. A row is invalid for authority training when:

- causal time is synthetic or non-causal
- required state arrived after the candidate decision
- `trade_id` or `lifecycle_id` cannot be joined
- support quality is below threshold

### 7.2 Canonical row boundary

The unit of learning and evaluation is one authority request, not one raw trade and not one raw feature row.

- Primary key: `decision_id`
- Correlation keys: `rid`, `lifecycle_id`, `trade_id`
- Terminalization point:
  - veto or baseline fallback without execution
  - close event for executed lifecycle

### 7.3 Runtime raw components

Runtime must persist raw components only:

- realized PnL net
- fees
- stress markers
- fallback reason
- apply result
- support quality
- invalid reason code

### 7.4 Offline reward

Runtime does not compute final RL reward. Offline evaluator computes:

`reward = (realized_pnl_net - baseline_pnl_estimate) - gamma * stress_penalty - lambda * opportunity_cost - mu * intervention_budget_violation`

Until `baseline_pnl_estimate` is implemented and validated:

- `reward_valid = false`
- Offline RL remains blocked by a research gate

### 7.5 Invalid or low-support rows

Rows remain persisted but are excluded from policy optimization with explicit reasons, at minimum:

- `NON_CAUSAL_TIME`
- `MISSING_REQUIRED_STATE`
- `UNJOINABLE_LIFECYCLE`
- `LOW_SUPPORT`
- `BASELINE_UNAVAILABLE`

## 8. Rollout Matrix

| Mode | Live effect | Promotion gate | Rollback trigger |
| --- | --- | --- | --- |
| `shadow` | No live effect; record request, response, and hypothetical action | Decision coverage complete, outcome ledger completeness, no hidden future leakage, authority journal stable | Any contract mismatch, missingness collapse, or ledger terminalization failure |
| `advisory` | No automatic effect; operator-visible authority trace only | Shadow metrics pass for a sustained window, deadline hit-rate proven under load, kill-switch drill passes | Operator disables trust, latency regression, stale response growth |
| `gated` | `allow`, `deny`, `modulate`, and `fallback` may affect live non-reduce-only candidates | Advisory metrics pass, bridge stability proven, fallback rate within limit, drift and drawdown monitors armed | Timeout spike, stale/late spike, bridge unavailable, trust disabled, abnormal drawdown, drift breach |

## 9. Implementation Order

Implementation order is fixed:

1. Document and config scaffolding
2. `ObservationEnvelope` builder in `decision_making`
3. `ControlDecisionRequest` and `ControlDecisionResponse` bridge in `decision_making` and `neocortex`
4. Authority request or response journal and `authority_context` propagation
5. `DecisionOutcomeLedgerRow` staging and terminalization
6. `ModulationStoreRecord` and bounded future-tick overlay path
7. Offline event-time merge and dataset builder
8. Offline reward and OPE gates

No package may skip ahead of unresolved upstream contracts.

## Appendix A. Evidence Map

| Claim | Evidence anchor |
| --- | --- |
| `neocortex` is shadow-only today | `apps/reference/domains/neocortex/domain.yaml` |
| Advisory and live authority are currently forbidden | `apps/reference/domains/neocortex/config/neuro.yaml`, `apps/reference/domains/neocortex/logic/gates/shadow.py`, `apps/reference/domains/neocortex/tests/test_shadow_gates.py` |
| Current policy training is disabled and reward is regime-oracle | `apps/reference/domains/neocortex/config/neuro.yaml` |
| Current world model is not action-conditioned | `apps/reference/domains/neocortex/logic/brain/core.py` |
| Gate chain is the canonical pre-intent pipeline | `apps/reference/domains/decision_making/strategy_gateway.py` |
| Intent emission writes WAL before `EVT:TRADE_INTENT_PROPOSED` | `apps/reference/domains/decision_making/intent_builder.py` |
| `execution_position` consumes `EVT:TRADE_INTENT_PROPOSED` directly | `apps/reference/domains/execution_position/intent_router.py` |
| Panic killswitch only blocks opens and cancels pending entries | `apps/reference/domains/execution_position/fsm_open.py`, `apps/reference/domains/execution_position/entry_manager.py` |
| FSM listeners are inline | `vfoundation/core/fsm_core.py` |
| Router already carries timeout and idempotency semantics | `vfoundation/core/routing.py` |
| Offline reconstruction currently processes streams in separate passes | `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py` |
| Missing values are currently zero-imputed | `apps/reference/domains/neocortex/logic/ingest/parser.py` |

## Appendix B. Current-to-Target Delta Matrix

| Subsystem | Current | Target | Delta type | Blocking gate |
| --- | --- | --- | --- | --- |
| `decision_making` | Gate chain flows directly into `_propose_trade_intent()` | Insert synchronous authority seam before intent emission | code change | contract package |
| `decision_making` | No authority journal | Request, response, apply-result journal | code change | WAL schema |
| `decision_making` | No `ModulationStore` | bounded future-tick overlay store | code change | action-surface package |
| `neocortex` | shadow-only observer | bounded authority bridge under rollout modes | code change + config change | shadow-to-advisory gate |
| `execution_position` | consumes canonical trade intents only | same, plus correlation metadata only | contract change | envelope compatibility |
| `vfoundation` | inline emit, generic router durability | same runtime model; optional helper only if bridge abstraction needs it | code change optional | no bus redesign |
| offline ingest | trade-episode-centric reconstruction | decision-centric ledger with event-time merge | code change | dataset package |
| evaluator | no baseline-relative reward pipeline | raw component ingestion plus offline reward and OPE | research gate | baseline estimator |

## Appendix C. Config Additions and Defaults

These keys are `NEW_CONTRACT` keys for implementation v2.

| Key | Default | Meaning |
| --- | --- | --- |
| `neocortex.trust_enabled` | `false` | Hard kill-switch for Neocortex authority |
| `neocortex.authority.mode` | `shadow` | Rollout mode |
| `neocortex.authority.deadline_ms` | `10` | Maximum synchronous decision window |
| `neocortex.authority.fallback_policy` | `baseline_yaml` | Canonical fail-closed behavior |
| `neocortex.authority.max_inflight_per_symbol` | `1` | Prevent concurrent authority decisions for one symbol |
| `neocortex.authority.modulation_allowlist` | `["decision_making.signal_threshold_bias", "decision_making.cooldown_mult"]` | Only bounded future-tick overlays allowed in v2 |
| `neocortex.authority.signal_threshold_bias_bounds` | `[-0.10, 0.10]` | Hard bounds for threshold modulation |
| `neocortex.authority.cooldown_mult_bounds` | `[1.0, 3.0]` | Hard bounds for cooldown modulation |

## Appendix D. Acceptance Checklist Before Implementation Start

- Archived R&D document exists at `docs/_archive/neocortex/DeepMind_RnD_Almanac_v2.1.md`
- Active implementation SSOT exists at `docs/plans/NEOCORTEX_IMPLEMENTATION_SSOT_v2.md`
- No runtime-facing symbolic name is left unmapped or unowned
- `ObservationEnvelope`, `ControlDecisionRequest`, `ControlDecisionResponse`, `AuthorityMode`, `ModulationStoreRecord`, and `DecisionOutcomeLedgerRow` each have an owner, producer, consumer, persistence rule, and acceptance gate
- Reduce-only closes, panic flows, and recovery flows are explicitly bypassed from authority
- `neocortex.trust_enabled` is separate from `panic_killswitch`
- Event chain is continuous from semantic tick to terminal outcome row
- Offline reward remains blocked until baseline estimator and support-quality gates exist
- Implementation can be split by subsystem without changing the canonical runtime meaning defined here
