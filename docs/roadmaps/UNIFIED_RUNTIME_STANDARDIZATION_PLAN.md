# UNIFIED RUNTIME STANDARDIZATION PLAN

Date: 2026-03-11
Status: v1.1 draft SSOT-aligned plan
Scope: Aurora / Phenix active runtime under config/aurora
Intent: standardize runtime contracts before further Quadratic rollout

## 1. Purpose

The main problem is not the scoring math itself. The main problem is the absence of one honest runtime contract spanning:

- startup hydration
- readiness
- restart recovery
- strategy isolation
- regime semantics
- execution lifecycle

The repository already contains major Phase 9 and Quadratic pieces, but it still cannot answer one operationally critical question with code-level honesty:

"At this exact moment, is the system truly ready to trade under the intended runtime mode?"

This document defines the target contract and the migration path needed to answer that question deterministically.

## 2. Evidence Base

This plan is derived from the following current-state audits and SSOT anchors:

- Copilot_Master_Roadmap.md
- apps/reference/dictionaries/verb_registry_v1.yaml
- docs/audits/current_warmup_quadratic_scoring_decision_lifecycle_audit_2026-03-10.md
- docs/audits/runtime_bar_consumption_audit_2026-03-11.md
- docs/audits/regime_architecture_decision_audit_2026-03-11.md
- docs/audits/md_amr_mean_reversion_impact_under_quadratic_rollout_2026-03-11.md

Contract-relevant runtime verbs already present in registry:

- EVT:BAR_CLOSED, owner=market_data
- EVT:FEATURES_CALCULATED, owner=feature_engineering
- EVT:HTF_BARS_IMPORTED, owner=feature_engineering
- CMD:PROCESS_STRATEGY, owner=strategies
- EVT:REGIME_DETECTED, owner=regime_detector or decision downstream consumer path by usage

## 3. Master Problem Register

### P0. Critical system breaks

1. Quadratic is not an active live runtime yet even though the repo looks nearly ready.
2. Startup hydration is not a closed loop. Pillar backfill and HTF ingest hooks exist, but active startup does not prove M15/H4/D1 are lifted before the first decision cycle.
3. Restart restores execution state better than analytics state.
4. FeatureEngineering full_ready is not equivalent to Quadratic-ready.
5. Runtime is not restart-safe as an analytics pipeline.

### P1. Contract and logic bugs

6. Aurora decision behavior is not fully self-contained because scoring can depend on side-cache state outside CMD:PROCESS_STRATEGY.
7. Live, replay, and warmup semantics are not proven to be one contract.
8. Gaps are detected but not repaired.
9. Bar identity and close timestamp semantics are still ambiguous.
10. Execution consumes stale or missing derived context indirectly through FEATURES_CALCULATED and REGIME_DETECTED caches.

### P2. Regime architecture drift

11. Structural regime is already effectively per-symbol, while parts of execution and risk still behave as if regime were global.
12. Exposure adaptation still leaks globally through shared directional ratio behavior.
13. Shared latest_regime and latest_warmup last-writer-wins state are not acceptable SSOT.
14. Regime flip enforcement and live detector vocabulary are not fully aligned.
15. Microstructure must not be pushed directly into the core structural regime classifier.

### P3. Rollout risks for mean_reversion and md_amr

16. Mean reversion and md_amr do not use Quadratic directly, but they are exposed through shared contracts.
17. Expanding one global FeatureEngineering readiness contract for Quadratic can accidentally starve mean reversion of CMD:PROCESS_STRATEGY.
18. md_amr already has local startup hydration and local warmup semantics that must not be broken by Aurora-centric bootstrap.
19. Mean reversion and md_amr must keep separate readiness sufficiency contracts.

### P4. Config and runtime drift

20. YAML, Pydantic, and runtime knobs still contain fields that imply behavior not actually implemented in the active path.
21. Scoring aliases and config drift still create operator-level false expectations.

## 4. Target Runtime Decision

Before any further rollout, the repository must declare one explicit target runtime mode:

- Mode A: remain on Aurora v2 as the active live standard while standardization work lands
- Mode B: enter Quadratic rollout mode, but only behind explicit readiness and bootstrap gates

Recommendation:

- keep live trading semantics on Aurora v2 until the standardization layers below are implemented and verified
- treat Quadratic as a gated rollout target, not as an implied near-ready default

This is necessary because the codebase currently contains both working legacy runtime and partially wired next-stage runtime. Without an explicit target mode, operators and future contributors will misread repository readiness.

## 5. Canonical Readiness Model

Replace one flat ready/not-ready notion with a layered readiness contract.

### 5.0 Ownership model

Each canonical readiness scope must have one SSOT owner. Other domains may consume or derive policy from that scope, but they must not silently redefine it.

| Scope | SSOT owner | Consumers | Owner responsibility |
| --- | --- | --- | --- |
| basis_bar_ready | market_data for bar continuity facts, feature_engineering for strategy-facing sufficiency view | regime_detector, strategies, hydration planner | publish canonical bar continuity facts and expose enough evidence for downstream sufficiency checks |
| regime_ready | regime_detector | feature_engineering, decision_making, execution_position | declare whether structural regime is sufficiently warm, fresh, and policy-usable |
| quadratic_htf_ready | feature_engineering, computed from hydration planner outputs and FE pillar state | Aurora / Quadratic path, policy arbiter | declare whether Quadratic HTF dependencies are satisfied under canonical hydration rules |
| microstructure_ready | feature_engineering | strategy handlers, policy arbiter | declare fast-context sufficiency for strategies that depend on it |
| strategy_ready_per_symbol | decision_making strategy-aware readiness evaluator | strategy_gateway, policy arbiter | evaluate whether a конкретна strategy-symbol pair has its minimum viable sufficiency |
| execution_context_ready | execution_position with risk/exposure inputs | policy arbiter, gateway | declare whether the runtime may safely manage or open risk from the execution side |
| trading_ready | policy arbiter at the final permission layer | strategy_gateway, operator-facing surfaces | make the final allow/block decision for new risk based on layered readiness and policy |

Ownership invariant:

- one scope, one owner
- consumers may cache, but not redefine owner truth
- any override must be explicit, attributed, and observable

### 5.1 Canonical readiness fields

Every symbol and strategy combination should expose these canonical states:

- basis_bar_ready
- regime_ready
- quadratic_htf_ready
- microstructure_ready
- strategy_ready_per_symbol
- execution_context_ready
- trading_ready

### 5.1A Canonical readiness state model

Boolean-only semantics are not sufficient. Each readiness scope must expose a structured state object.

Minimum shape:

- state
- why
- updated_at
- source
- evidence_ref

Recommended state enum:

- READY
- COLD
- PARTIAL
- BLOCKED
- INVALIDATED_GAP

Semantic rules:

- READY means the owner asserts the scope is sufficient for its intended use.
- COLD means the scope has not yet been restored or built to a usable baseline.
- PARTIAL means some required evidence exists, but the scope is not yet sufficient for the intended use.
- BLOCKED means policy or hard dependency failure prevents use even if some data exists.
- INVALIDATED_GAP means previously valid state was made unsafe by continuity loss.

Field rules:

- why must be machine-readable enough for operator-facing reason chains
- updated_at must use canonical exchange-aligned or runtime time semantics as defined by the owning domain
- source must identify the producing subsystem or policy layer
- evidence_ref must point to the relevant canonical identity, replay token, or hydration action where applicable

### 5.2 Semantics

#### basis_bar_ready

Meaning:

- the required primary bar stream for the strategy exists, is monotonic enough, and has sufficient local history for the basis timeframe
- owner-facing truth includes continuity facts, not just derived strategy sufficiency

Examples:

- Aurora structural regime needs basis 5m bars
- legacy mean_reversion needs 5m bars with local minimum bar count
- md_amr needs 15m bars with its local startup hydration semantics

#### regime_ready

Meaning:

- the structural regime classifier has enough history to emit stable, policy-acceptable per-symbol labels
- the current regime payload is fresh enough for downstream use

Owner:

- regime_detector

This is separate from feature and pillar readiness.

#### quadratic_htf_ready

Meaning:

- all Quadratic-required higher-timeframe state is available under the canonical contract
- M15/H4/D1 requirements are satisfied through backfill, replay, or a declared cold state

Owner:

- feature_engineering, using planner-evaluated hydration evidence rather than ad hoc local guesses

This field must remain optional for strategies that do not use Quadratic.

#### microstructure_ready

Meaning:

- the fast FeatureEngineering context required by a specific strategy is available and healthy enough

Owner:

- feature_engineering

This must not silently become a prerequisite for all strategies.

#### strategy_ready_per_symbol

Meaning:

- the symbol-strategy pair has all of its own minimum viable prerequisites satisfied

Owner:

- strategy-aware readiness evaluator inside decision_making, consuming owner scopes rather than redefining them

This is the key isolation field and must be strategy-aware, not globally flattened.

#### execution_context_ready

Meaning:

- execution-side safety context is valid enough to allow new order placement
- this includes portfolio, exposure, pending-order, and stale-context protections

Owner:

- execution_position, with risk-management inputs treated as dependencies, not parallel truth owners

#### trading_ready

Meaning:

- final permission to open new risk
- derived from the conjunction of the layers above plus deployment mode and operator policy

Owner:

- final policy arbiter layer, not FeatureEngineering and not any single strategy handler

### 5.3 Layer model

The target standard is:

- Layer 1: Data continuity
- Layer 2: Analytics continuity
- Layer 3: Strategy sufficiency
- Layer 4: Execution safety
- Layer 5: Trading permission

Mapping:

| Layer | Required canonical outputs |
| --- | --- |
| Data continuity | basis_bar_ready, gap_state, replay_consistency |
| Analytics continuity | regime_ready, quadratic_htf_ready, microstructure_ready |
| Strategy sufficiency | strategy_ready_per_symbol |
| Execution safety | execution_context_ready |
| Trading permission | trading_ready |

### 5.4 Protective risk vs new risk invariant

The runtime must explicitly distinguish:

- can_manage_existing_risk
- can_open_new_risk

Policy invariant:

- a system may be not ready for new entries while still being required to protect existing positions
- restart with open positions must preserve protective behavior even when trading_ready is false
- no readiness model may collapse these two permissions into one boolean gate

Operational consequences:

- position reduction, stop adjustment, stale-order cancel, and protective exits can remain allowed under protect-only mode
- new entries require both can_open_new_risk and trading_ready

### 5.5 Degraded mode policy

Degraded mode is a formal policy layer, not an accidental side effect.

Each degraded mode decision must define:

- what is degraded
- what remains allowed
- what is forbidden
- who decided it
- whether it is config-driven or hard-coded safety policy

Default degraded policy examples:

| Condition | Allowed | Forbidden | Policy owner |
| --- | --- | --- | --- |
| basis-bar gap on active strategy tf | protect existing risk, observe, rebuild continuity | new entries | policy arbiter using market_data continuity facts |
| analytics cold, execution restored | protect-only behavior | new entries, strategy-driven expansion of risk | policy arbiter |
| Quadratic HTF absent | non-Quadratic strategies may continue if their own scopes are READY | Aurora Quadratic entries | strategy-aware readiness evaluator |
| microstructure cold | bar-only strategies may continue if policy allows | liquidity-sensitive entries | strategy-aware readiness evaluator plus policy arbiter |

## 6. Canonical Startup and Restart Contracts

The runtime must standardize four startup classes.

### 6.1 Cold start

Definition:

- no restored analytics state is trusted
- no restored execution state is assumed

Required behavior:

- declare all continuity layers cold
- run hydration planning before strategy emission is allowed
- emit explicit cold-state reasons rather than implicitly waiting

### 6.2 Warm restart

Definition:

- recent state may exist on disk and can be restored under canonical replay identity

Required behavior:

- rebuild analytics continuity first
- then rebuild strategy sufficiency
- then re-enable execution permission

### 6.3 Restart with open positions

Definition:

- execution state and live positions must be restored without pretending analytics continuity also exists

Required behavior:

- restore positions and execution FSMs
- mark analytics layers as restored, partial, or cold explicitly
- block new entries until execution_context_ready and strategy_ready_per_symbol are both honest
- allow position-protective behavior even when opening-new-risk is disabled
- expose the resulting protect-only vs open-new-risk split in operator-visible telemetry

### 6.4 Restart after data gap

Definition:

- bars or upstream market data continuity are known broken or uncertain

Required behavior:

- carry explicit gap metadata into continuity state
- either repair missing bar ranges or downgrade the affected strategy-symbol pair to non-trading mode
- never infer readiness from post-gap bars alone

## 7. Canonical Bar and Replay Contract

This is the foundation layer and must be standardized before any further rollout.

### 7.1 Canonical bar identity

Every runtime bar identity must be formalized with one unambiguous tuple:

- symbol
- timeframe_sec
- bar_start_ts_ms
- bar_end_ts_ms
- close_boundary_ts_ms
- source_mode

Where:

- bar_end_ts_ms is the last included millisecond in the bar payload
- close_boundary_ts_ms is the semantic boundary close timestamp used for replay, dedup, freshness, and command identity
- source_mode is one of live, replay, warmup_import, or synthetic_repair

Rationale:

- current runtime mixes end_ts_ms, bar_close_ts, close_ts, event ts, and extracted timestamps across consumers
- these must be related formally rather than implicitly

### 7.2 Canonical replay identity

Replay identity must be built from bar identity, not from ad hoc downstream timestamps.

Minimum replay identity fields:

- symbol
- timeframe_sec
- close_boundary_ts_ms
- source_mode
- replay_generation

### 7.3 Required replay guarantees

- live and replay must produce the same downstream bar-close meaning for the same bar identity
- dedup must happen on canonical replay identity, not on handler-local heuristics only
- warmup-imported bars must carry their source_mode explicitly
- repaired gap bars must be distinguishable from native live bars

## 8. Analytics Restore and Hydration Foundation

The next foundation requirement is a full analytics restore path.

### 8.1 Objects that must become restorable

- completed bars by symbol and timeframe
- current partial bar state where contractually safe
- FeatureEngineering last_bar and dependent caches
- regime detector per-symbol buffers and last regime state
- pillar state for M15/H4/D1
- DecisionMaking feature caches relevant to freshness and scoring
- strategy-local startup state where required, especially md_amr local warmup state

### 8.2 Restore modes

For each restorable object, the runtime must support one of three explicit states:

- restored
- cold
- invalidated_due_to_gap

No silent implicit defaulting.

### 8.3 Startup hydration planner

Introduce one planner that computes required hydration work before trading permission is granted.

Planner inputs:

- active strategies
- active symbols
- required basis timeframe per strategy
- required HTFs per strategy
- required bar counts
- available restored state
- missing delta ranges
- detected gaps
- deployment mode

Planner outputs:

- hydration actions by strategy-symbol pair
- continuity state by layer
- reasons blocking trading_ready
- allowed degraded modes if any

The planner must coordinate multiple strategies, not only Aurora.

### 8.4 Component boundaries

The hydration planner must not become a new god-object.

Required decomposition:

- Planner: computes what is required and what is missing
- Hydrator or Importer: fetches or imports needed data
- Replayer: reconstructs runtime state from canonical replay inputs
- Readiness evaluator: computes layered readiness from owner scopes
- Policy arbiter: decides whether protect-only, degraded, or full trading is allowed

Boundary invariant:

- the planner may plan, but it must not silently fetch, replay, set final policy flags, and own readiness truth in one monolith

## 9. Strategy Isolation Rules

Shared plumbing is allowed. Shared sufficiency criteria are not.

### 9.1 Isolation principles

1. Strategy transport can be shared.
2. Strategy execution plumbing can be shared.
3. Readiness sufficiency must be strategy-aware and symbol-aware.
4. Quadratic-only readiness must not block non-Quadratic strategies by default.
5. Strategy-local warmup and startup contracts must remain explicit and testable.

### 9.2 Required protected paths

#### Aurora / Quadratic

- may require quadratic_htf_ready
- may require structural regime_ready and microstructure_ready
- must not declare global readiness on behalf of other strategies

#### mean_reversion

- must keep its own basis-bar sufficiency and regime semantics
- must not depend on Quadratic HTF readiness unless config explicitly says so
- must not lose CMD:PROCESS_STRATEGY due to Quadratic-only global FE expansion

#### md_amr

- is a compatibility perimeter for the new standard
- must preserve its local startup hydration semantics or replace them with an explicitly equivalent contract
- must not be double-gated by both local warmup and new global bootstrap without formal design

### 9.3 Strategy compatibility matrix

Implementation packages must derive from one explicit compatibility matrix, not from prose interpretation alone.

Minimum matrix columns:

- strategy
- active symbols
- required basis tf
- required HTF
- needs regime
- needs microstructure
- needs execution_context
- local hydration contract
- can run in degraded mode
- can protect open positions while not entry-ready
- blocked by Quadratic-only readiness by default

Current baseline matrix:

| Strategy | Active symbols | Required basis tf | Required HTF | Needs regime | Needs microstructure | Needs execution_context | Local hydration contract | Can run degraded | Protect while not entry-ready | Blocked by Quadratic-only readiness by default |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Aurora v2 | Aurora-assigned symbols | 5m | none mandatory today | yes | yes | yes | no proven shared startup hydration | limited | yes | no |
| Aurora Quadratic | Aurora-assigned symbols | 5m | M15, H4, D1 | yes | yes | yes | requires canonical HTF hydration under new planner | only if policy explicitly allows degraded non-entry state | yes | yes, for Quadratic path only |
| mean_reversion | DOGEUSDT in current config | 5m | none | yes, via current regime mapping | may depend on selected FE context but must not inherit Quadratic-only sufficiency | yes | needs 5m local bar sufficiency, no proven startup hydrator today | yes, if its own scopes are READY | yes | no |
| md_amr | XRPUSDT, BNBUSDT in current config | 15m | none for Quadratic pillars | yes | yes | yes | existing local REST hydration plus local warmup semantics | yes, under explicit policy | yes | no |

## 10. Regime Architecture Standard

### 10.1 Declare the current live classifier honestly

The current live detector should be formally named:

- per-symbol structural regime

This avoids pretending the current classifier is global or microstructure-aware when it is not.

### 10.2 Target layered regime architecture

Target layers:

- global backdrop regime
- per-symbol structural regime
- execution micro regime

Rules:

- structural regime remains bar-driven
- microstructure belongs in execution micro regime or execution-context gating, not in the core structural classifier
- downstream consumers must know which regime layer they are consuming

### 10.3 Leakage removal targets

Priority leakage targets:

- shared global exposure adaptation triggered by one symbol regime event
- shared latest_regime and latest_warmup last-writer-wins caches
- regime flip logic that assumes one label vocabulary while the detector emits another semantic contract

## 11. Phased Implementation Roadmap

### Phase A. Contract standardization

Goal:

- define the canonical runtime vocabulary and stop further rollout drift

Deliverables:

1. explicit target runtime declaration: Aurora v2 live standard or Quadratic rollout mode
2. canonical layered readiness schema
3. canonical startup and restart mode definitions
4. canonical bar identity and replay identity schema
5. strategy-isolation rules written as enforceable contracts
6. ownership table for every readiness scope
7. state enum and readiness payload model

Exit criteria:

- every downstream team can answer what ready means for its domain without code archaeology
- no remaining ambiguity about whether one readiness field is global or strategy-specific

### Phase B1. Bar identity and gap policy foundation

Goal:

- make canonical continuity semantics explicit before restore logic is implemented

Deliverables:

1. canonical bar identity implementation
2. canonical replay identity implementation
3. formal gap policy: repair, invalidate, or degrade
4. source_mode contract for live, replay, warmup_import, synthetic_repair

Exit criteria:

- replay and live produce the same canonical bar-close identity
- no downstream package has to guess what bar identity or gap invalidation means

### Phase B2. Analytics restore and hydration foundation

Goal:

- make runtime continuity reconstructable on top of the canonical identity layer

Deliverables:

1. analytics replay and restore path for bars, FE, regime, pillars, and feature caches
2. startup hydration planner with per-strategy planning output
3. component split between planner, hydrator, replayer, readiness evaluator, and policy arbiter
4. explicit protect-only behavior for restart with open positions

Exit criteria:

- restart with open positions does not pretend analytics are restored when they are not
- protect-existing-risk and open-new-risk permissions are independently observable

### Phase C. Strategy isolation hardening

Goal:

- ensure Aurora rollout cannot regress mean_reversion or md_amr

Deliverables:

1. strategy-aware readiness evaluation
2. symbol-aware required-ready contracts
3. preserved md_amr local hydration behavior under unified planner
4. protected mean_reversion CMD path independent of Quadratic-only sufficiency
5. maintained compatibility matrix with executable test coverage

Exit criteria:

- Quadratic-only readiness cannot starve MR paths unless config explicitly opts in
- md_amr remains valid under the new planner without duplicate gating

### Phase D. Regime architecture repair

Goal:

- align runtime behavior with the actual regime model already present in code

Deliverables:

1. declare structural regime as per-symbol SSOT
2. remove or isolate global regime leakage points
3. introduce execution micro regime as a separate downstream concept if needed
4. optionally add a global backdrop layer later

Exit criteria:

- regime consumers no longer confuse structural and execution semantics
- one symbol cannot silently remap execution posture for all symbols without explicit policy

### Phase E. Safe Quadratic rollout

Goal:

- activate Quadratic only after the contracts it depends on are real

Deliverables:

1. startup HTF hydration under canonical planner
2. explicit Quadratic readiness gate based on quadratic_htf_ready
3. first-valid-Quadratic-cycle integration test
4. controlled config migration from scoring_version=v2 to Quadratic mode
5. explicit rollback mechanism from Quadratic mode back to v2 mode

Exit criteria:

- first live or testnet Quadratic decision cycle can be proven valid under the new readiness model
- activation is a config flip backed by already-verified contracts, not by hopeful wiring

## 12. Migration Path: Aurora v2 to Quadratic

### Step 1. Freeze live target semantics

- keep Aurora v2 as the live truth while contracts are standardized
- forbid implicit interpretation that Quadratic is nearly production-ready just because code exists

### Step 2. Standardize shared contracts without changing strategy behavior

- add canonical readiness fields
- add canonical startup and restart state reporting
- add canonical bar and replay identity

### Step 3. Introduce analytics restore without changing entry logic

- restore bars, FE, regime, and strategy-local caches first
- verify parity in replay and restart tests

### Step 4. Enable strategy-aware sufficiency

- move from one global FE full_ready interpretation to strategy-aware sufficiency evaluation
- preserve legacy strategy expectations unless explicitly migrated

### Step 5. Activate Quadratic in shadow or constrained mode

- hydrate HTFs through the canonical planner
- keep Quadratic behind explicit gates
- compare its first valid cycles to expected continuity contracts

### Step 6. Flip active config only after integration proof

- change active scoring mode only when the planner, replay identity, and readiness contracts are already green

### Step 7. Keep rollback one-step and tested

- rollback from Quadratic to v2 must be one explicit, verified mechanism
- rollback trigger conditions must be telemetry-backed, not ad hoc operator intuition

## 13.1 Rollback policy for Quadratic rollout

Rollback is a first-class rollout requirement.

Required rollback properties:

- one explicit mechanism, ideally config-driven
- one clear owner for declaring rollback condition
- one operator-visible trigger set
- no hidden dependency on manual state surgery unless explicitly documented

Minimum rollback trigger classes:

- readiness chain failure that persists beyond policy threshold
- replay or hydration parity mismatch
- unexpected strategy starvation for mean_reversion or md_amr
- observability evidence that Quadratic scopes oscillate between READY and BLOCKED without stable continuity

Rollback invariant:

- rollback must disable Quadratic new-entry permission without disabling protect-existing-risk behavior

## 13. Must-Fix Before Next Live or Testnet Expansion

1. Standardize canonical bar identity and canonical replay identity.
2. Implement analytics restore or explicit analytics-cold truth after restart.
3. Separate FeatureEngineering full_ready from Quadratic-specific sufficiency.
4. Remove or formalize Aurora cached side-channel dependence in scoring.
5. Make startup hydration planner strategy-aware and symbol-aware.
6. Preserve md_amr local hydration semantics inside the unified standard.
7. Remove global regime leakage from execution exposure adaptation.
8. Replace shared latest_regime and latest_warmup last-writer-wins state with symbol-scoped SSOT.
9. Define a formal gap policy: repair, invalidate, or non-trading downgrade.
10. Prove first valid Quadratic cycle with an integration test before flipping live config.
11. Add operator-visible readiness, hydration, and rollback telemetry.
12. Make rollback from Quadratic to v2 explicit and tested.

## 13.1 Observability and telemetry requirements

Observability is not optional. It is part of the contract.

Required operator-visible outputs:

- readiness snapshot per strategy-symbol pair
- full blocking reason chain, not just ready=false
- hydration actions planned and executed
- restored, cold, partial, and invalidated counts by scope
- gap states by symbol and timeframe
- replay lag and hydration lag where applicable
- last canonical bar identity per symbol and timeframe
- last regime freshness per symbol
- last pillar freshness for Quadratic scopes
- current protect-only vs open-new-risk policy state
- active rollout mode and rollback-armed status

Delivery surfaces may include metrics, WAL, reports, or debug endpoints, but the contract must specify where operators can read them.

## 14. Acceptance Criteria

This plan is complete only when all of the following are true:

1. The runtime can declare, per strategy and per symbol, why trading is or is not allowed.
2. Restart with open positions can restore execution state without falsely implying analytics continuity.
3. Live, replay, and warmup bars share one canonical identity contract.
4. Quadratic readiness is explicit and cannot be confused with generic FeatureEngineering readiness.
5. mean_reversion and md_amr remain operable under the unified planner without Aurora-only coupling.
6. Structural regime semantics are per-symbol and downstream consumers no longer rely on accidental global leakage.
7. The config flip from v2 to Quadratic becomes the last step, not the first.
8. After restart with open positions, the runtime can protect positions without being forced to allow new entries.
9. Every readiness scope has one owner, one state enum, and one why-chain.
10. The hydration planner cannot block a strategy that does not depend on the missing scope.
11. mean_reversion and md_amr pass compatibility tests under the new readiness model.
12. Rollback from Quadratic to v2 is one explicit verified mechanism.
13. Operator-visible telemetry exposes exact blocking chains and continuity state.

## 15. Immediate Next Documents

This plan should be followed by implementation-facing companion documents:

1. URS-A1 Readiness Schema and State Model
2. URS-A2 Canonical Bar Identity and Replay Identity Specification
3. URS-B1 Gap Policy
4. URS-B2 Analytics Restore
5. URS-B3 Startup Hydration Planner Design
6. URS-C1 Strategy Compatibility and Isolation Matrix
7. URS-D1 Regime Layering
8. URS-E1 Quadratic Shadow Rollout and Rollback Specification

## 16. Final Position

The correct next move is not to push more scoring logic into a shaky runtime. The correct next move is to finish the runtime contract so the system can make one truthful statement:

- what is restored
- what is cold
- what is strategy-ready
- what is execution-safe
- what is allowed to trade

Until that contract exists, Phase 9 and Quadratic will continue to look closer to production than they really are.
