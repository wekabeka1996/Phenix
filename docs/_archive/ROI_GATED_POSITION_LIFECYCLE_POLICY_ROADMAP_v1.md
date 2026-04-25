# OFFICIAL ROADMAP v1.0
## ROI-Gated Position Lifecycle Policy
### Aurora / Phenix — Contract-safe post-entry continuation, protection, and exit policy

**Status:** Working SSOT roadmap / implementation governance artifact  
**Date:** 2026-04-03  
**Scope owner:** Aurora / Phenix architecture  
**Applies to:** `decision_making`, `execution_position`, `position_tracking`, `feature_engineering`, `regime_detector`, runtime observability, contract registry, YAML/Pydantic SSOT

---

# 1. Final Goal

The end goal is **not** to add “just another exit heuristic.”

The real end goal is:

> **build a contract-safe, explainable, replayable post-entry policy layer** that continuously re-evaluates already-open positions and decides whether the system should:
> - continue holding,
> - protect accrued profit,
> - or exit,
>
> based on continuation quality, degradation, exhaustion, and time-decay,
> **without violating current ownership boundaries of decision-making vs execution truth**.

This initiative exists to solve a very specific economic defect:

> a position becomes profitable,
> the system does not adequately protect that edge,
> market quality degrades,
> and the trade gives back realized opportunity into a large avoidable loss.

---

# 2. Architectural Position

## 2.1 What this module is

This module is a **post-entry policy layer**.

It is responsible for answering this question repeatedly over the life of an already-open position:

> **Does continued holding still have positive expected value right now?**

## 2.2 What this module is not

This module is **not**:

- a new entry engine,
- a replacement for strategy math,
- a replacement for execution-position FSM ownership,
- a duplicate position-truth state machine,
- a blind TP-shortening heuristic,
- a one-off threshold tweak.

## 2.3 Ownership boundaries

### Strategy layer
Owns entry-side alpha generation, regime-conditioned signal logic, and signal production.

### Decision-making layer
Owns policy interpretation, gating, intent formation, why-codes, and lifecycle policy decisions.

### Execution-position layer
Owns execution truth, order lifecycle, bracket mechanics, reconciliation, and position-tracking continuity.

### Position lifecycle policy
Must live **with decision-making ownership semantics**, not inside execution-position execution truth.

---

# 3. Core Architectural Laws

These rules are frozen unless explicitly superseded by a later approved SSOT artifact.

## LAW-1 — No split-brain ownership
The new lifecycle policy must **not** become a second competing owner of position truth.

- `execution_position` remains the owner of execution/order lifecycle truth.
- `ManageFlowFSM` remains runtime SSOT for position tracking.
- lifecycle policy may hold **policy state**, but not replace execution state.

## LAW-2 — Contract-first only
No hidden policy decisions.

Every newly introduced command/event/config surface must have:
- explicit contract,
- registry entry if evented,
- schema where appropriate,
- typed config if configurable,
- documented owner,
- clear fail-closed behavior.

## LAW-3 — Additive-only evolution
No big-bang rewrite of existing execution lifecycle.

Implementation proceeds through:
- shadow evaluation,
- observability,
- recommendation-first behavior,
- guarded action rollout,
- bounded cutover.

## LAW-4 — Runtime truth before optimization
No calibration or optimization of lifecycle policy before:
- policy inputs are observable,
- policy outputs are explainable,
- decisions are replayable,
- false positives / false negatives are measurable.

## LAW-5 — No silent fallback business logic
No hidden “default compress” / “magic ROI values” / “best-effort assumptions” in runtime behavior.

All thresholds, ladders, policies, and routing choices must be:
- explicit in YAML, or
- explicit in typed defaults documented as runtime SSOT.

## LAW-6 — Action safety dominates feature richness
The first production-capable version must prefer:
- fewer actions,
- stronger guarantees,
- clearer proofs,
- lower blast radius.

Therefore the initial action set is:
- `HOLD`
- `PROTECT`
- `EXIT`

not immediate full support for partial close / complex dynamic bracket surgery.

---

# 4. Problem Statement

## 4.1 Symptom
Profitable positions sometimes revert into large losses because post-entry protection is too passive, too late, too weak, or insufficiently context-aware.

## 4.2 Root cause class
The root problem is not only stop placement.
The deeper problem is:

> **the system does not yet have a first-class runtime policy for continuation confidence and exhaustion-aware position management.**

## 4.3 Contributing factors
Potential contributing factors the implementation must be able to measure explicitly:

- local microstructure deterioration,
- weakening directional flow,
- lower reward-per-risk quality after entry,
- regime maturity / exhaustion,
- dead-trade time decay,
- rise in noise without progress,
- drawdown from peak unrealized PnL,
- spread/liquidity degradation,
- overstay after initial edge realization.

## 4.4 Anti-goals
The implementation must not:
- blindly wait for TP,
- treat any brief weakening as immediate full exit,
- silently mutate execution truth,
- introduce parallel “hidden FSM” ownership,
- rely on legacy/non-runtime config surfaces,
- ship action-capable logic before shadow proof.

---

# 5. Operational End-State

A fully implemented and validated lifecycle policy should provide:

1. **replayable post-entry policy decisions**;
2. **explainable rationale** for each hold/protect/exit action;
3. **bounded protection behavior** once profit exists;
4. **time-decay handling** for dead trades;
5. **degradation/exhaustion awareness**;
6. **instrumented false-positive / false-negative analysis**;
7. **contract-safe handoff** from policy to execution;
8. **no ambiguity** about which layer owns truth.

---

# 6. Vocabulary and Canonical Semantics

## 6.1 Canonical policy actions

### `HOLD`
Continue the position without tightening protection beyond already-active protection policy.

### `PROTECT`
Move the trade into profit-defense mode.

V1 allowed semantics:
- tighten stop,
- move to breakeven,
- lock minimum positive outcome,
- switch to stricter bracket management policy,
- emit recommendation or bounded execution command depending on rollout phase.

V1 explicitly excludes mandatory broad partial-close support.

### `EXIT`
Terminate the position because continued holding no longer has sufficient expected value or because degradation/exhaustion is confirmed.

## 6.2 Internal policy modes
These are **policy-layer modes**, not execution-truth states.

- `OBSERVE`
- `EXPAND_OK`
- `PROTECT`
- `EXIT_RECOMMENDED`
- `EXIT_COMMITTED`

These must not be confused with execution FSM states.

## 6.3 Key derived quantities

### `continuation_score`
Estimated quality of continued holding from now forward.

### `protection_urgency_score`
Estimated urgency of defending already-accrued edge.

### `exhaustion_score`
Estimated probability that the move is mature / degrading / no longer paying for risk.

### `time_decay_score`
Penalty reflecting that the trade is not developing fast enough relative to expected life profile.

### `peak_giveback_ratio`
Fraction of peak unrealized edge already lost from MFE (max favorable excursion).

---

# 7. Required Input Surface

The policy module must not invent context from thin air. It must consume an explicit typed input envelope.

## 7.1 Required runtime inputs (minimum)

### Position state
- symbol
- side
- entry price
- current mark / reference price
- quantity
- open timestamp
- realized PnL if partially reduced in future versions
- unrealized PnL
- ROI / return-to-margin metric

### Position path statistics
- MFE since entry
- MAE since entry
- current drawdown from MFE
- time in trade
- bars since entry
- best ROI achieved
- best price achieved in trade direction

### Market / feature context
- latest feature vector relevant to symbol
- regime label
- regime confidence
- price-motion context
- liquidity / spread context
- microstructure continuation inputs

### Freshness and validity context
- timestamps for all key upstream dependencies
- readiness flags
- degraded-context flags
- missing-input why-codes

## 7.2 Recommended feature families for v1/v2

### V1 families
- OBI / TFI / delta-price / absorption-derived continuation evidence
- price motion (`ret_*`, `pm_norm_*`, `vol_pct_*`)
- liquidity/spread (`liquidity_kappa`, `spread_bps`)
- regime + regime_confidence
- time-in-trade and trade-path statistics

### V2 families
- trend maturity markers
- continuation failure streaks
- volatility compression after impulse
- symbol-relative and market-relative exhaustion signals
- optional BTC-led contextual overlays only if explicitly configured

---

# 8. Configuration Philosophy

This module must be driven by explicit SSOT config.

## 8.1 New config surface
Target canonical location:

- strategy-local or policy-local YAML surface under decision-making / strategy profile namespace,
- typed with Pydantic,
- `extra='forbid'`.

## 8.2 Mandatory config sections

### `position_lifecycle_policy.enabled`
Hard gate for the policy layer.

### `position_lifecycle_policy.mode`
Allowed values:
- `off`
- `shadow`
- `recommendation`
- `protect_only`
- `protect_and_exit`

### `position_lifecycle_policy.roi_checkpoints`
Ordered checkpoint ladder.

Example:
- `0.05`
- `0.10`
- `0.15`

These are evaluation triggers, not actions by themselves.

### `position_lifecycle_policy.actions`
Capabilities allowlist.

V1 allowed defaults:
- `hold`
- `protect`
- `exit`

### `position_lifecycle_policy.thresholds`
Contains thresholds for:
- continuation high/medium/low,
- protection urgency,
- exhaustion,
- time decay,
- peak giveback,
- dead-trade timeout,
- minimum profit before protect is legal.

### `position_lifecycle_policy.time_decay`
Contains:
- expected progress rules,
- stagnation timeout,
- dead-trade timeout,
- late-stage penalties,
- optional per-strategy or per-symbol overrides.

### `position_lifecycle_policy.protect_policy`
Contains:
- BE rules,
- minimum locked-profit rules,
- max adjustment frequency,
- repeated-protect cooldown,
- whether protect can be re-issued.

### `position_lifecycle_policy.exit_policy`
Contains:
- confirmed degradation rules,
- exhaustion-confirmation bars/windows,
- giveback threshold rules,
- mandatory exit conditions.

## 8.3 Forbidden configuration patterns
- silent hidden constants in code,
- mixed ownership between `trading.yaml` and strategy YAML for same policy knobs,
- legacy fields reused without proof of active consumer,
- per-symbol overrides that bypass global typed validation.

---

# 9. Rollout Strategy

This initiative must be delivered through staged rollout.

## Phase R0 — Governance Freeze and Scope Lock
**Status target:** immediate

### Objective
Freeze architecture rules, ownership boundaries, and allowed rollout strategy.

### Deliverables
- this roadmap document,
- accepted architectural constraints,
- policy naming freeze for v1,
- explicit ban on embedding lifecycle ownership into `execution_position`.

### DoD
- roadmap saved in repo/docs or equivalent persistent artifact,
- owner boundaries documented,
- initial action set frozen (`HOLD/PROTECT/EXIT`),
- forbidden shortcuts documented.

### Test / Validation
- architecture review checklist completed,
- no-code audit note produced,
- contradiction review against existing domain passports performed.

### Fail conditions
- roadmap accepted but ownership ambiguity remains,
- roadmap speaks of “new FSM” without clarifying policy-vs-truth separation,
- rollout stages not frozen.

---

## Phase R1 — Surface Discovery and Evidence Baseline
**Status target:** mandatory before implementation

### Objective
Discover the actual current runtime surfaces needed to support lifecycle policy.

### Key questions
- What exact position-truth fields already exist and where?
- What path statistics are already persisted or reconstructable?
- What feature freshness guarantees exist at decision time after entry?
- What close/protect mechanisms are already available and proven?
- What observability gaps currently hide profitable-to-loss giveback transitions?

### Deliverables
- implementation surface map,
- current-state contract audit,
- gap matrix:
  - already exists,
  - exists but weakly observable,
  - missing,
  - dangerous/unclear ownership.

### DoD
- each required input surface is classified,
- each required action surface is classified,
- each observability gap is named and tied to owner,
- no assumption is left unlabeled.

### Required evidence
- concrete file paths,
- event names,
- schema references,
- runtime owner references,
- test references,
- examples from live or replay traces if available.

### Test / Validation
- doc-level audit review,
- contradiction sweep versus verb registry,
- contradiction sweep versus domain passports,
- proof that no required field is assumed without source.

### Fail conditions
- “probably available” surfaces accepted without proof,
- protect path assumed because `DEC:ADJUST` exists in name only,
- trade-path statistics assumed but not traced.

---

## Phase R2 — Contract Design (Policy Envelope + Event Surface)
**Status target:** design-only, no action rollout yet

### Objective
Design the explicit contracts for lifecycle policy.

### Work packages

#### R2-A — Policy input model
Create typed model for lifecycle evaluation inputs.

#### R2-B — Policy decision model
Create typed output model containing:
- action,
- scores,
- rationale,
- evidence vector,
- freshness/degraded flags,
- checkpoint metadata.

#### R2-C — Observability events
Add lifecycle-policy event surface, for example:
- `EVT:POSITION_POLICY_EVALUATED`
- `EVT:POSITION_POLICY_PROTECT_RECOMMENDED`
- `EVT:POSITION_POLICY_EXIT_RECOMMENDED`
- `EVT:POSITION_POLICY_BLOCKED`

#### R2-D — Why-code vocabulary
Add canonical why-codes for:
- stale context,
- insufficient path stats,
- dead trade,
- giveback breach,
- confirmed exhaustion,
- protect cooldown,
- action not allowed by mode.

#### R2-E — YAML + Pydantic config surface
Add strict typed config.

### DoD
- all new public surfaces are typed,
- all new event verbs are registered,
- schemas exist where needed,
- no policy action is semantically ambiguous,
- protect and exit are distinguishable in contract,
- shadow mode behavior is explicit.

### Test / Validation

#### Contract tests
- valid config loads,
- unknown fields rejected,
- invalid thresholds rejected,
- duplicate / unsorted checkpoints rejected,
- conflicting mode/action combinations rejected.

#### Registry tests
- new verbs present,
- schema paths valid,
- owner fields correct,
- no shadow undocumented event names.

#### Serialization tests
- policy decision/event payload roundtrip,
- stable JSON serialization,
- missing required fields fail closed.

### Fail conditions
- contract design leaks execution-owner semantics into policy payload,
- output action names map to multiple runtime meanings,
- config allows silently impossible combinations.

---

## Phase R3 — Observability First (No Live Actions)
**Status target:** action-disabled shadow policy

### Objective
Make post-entry policy evaluation visible before it is allowed to act.

### Work packages

#### R3-A — Evaluation trigger wiring
Trigger evaluations on:
- position open,
- ROI checkpoint hit,
- periodic post-entry timer,
- regime change,
- strong motion deterioration,
- trade age milestones.

#### R3-B — Trace emission
Emit evaluation traces with:
- position snapshot,
- path stats,
- feature snapshot refs,
- scores,
- proposed action,
- reasons,
- policy mode,
- freshness flags.

#### R3-C — Monitoring views
Create forensic views / logs / summaries that show:
- profitable trades that later hit SL,
- first checkpoint reached,
- first protect recommendation timing,
- first exit recommendation timing,
- giveback size before exit / SL.

### DoD
- every evaluation is observable,
- every blocked evaluation has a why-code,
- no “silent no-op” shadow evaluation remains invisible,
- trace IDs can join evaluation → decision → execution events.

### Test / Validation

#### Runtime event tests
- evaluation event emitted on checkpoint hit,
- blocked event emitted when inputs stale,
- no duplicate spam under repeated trigger conditions.

#### Replay tests
- same input trace produces same evaluation output,
- deterministic ordering across repeated runs,
- policy event timestamps/order remain stable.

#### Forensic tests
- joinability with `TRADE_EXECUTED`, `ORDER_STATE_CHANGED`, `EXPOSURE_SUMMARY_UPDATED`, and regime/feature events.

### Fail conditions
- evaluation occurs but is not emitted,
- trace lacks actionable rationale,
- trigger ordering is nondeterministic.

---

## Phase R4 — Data Truth and Path Statistics Hardening
**Status target:** before action-capable rollout

### Objective
Ensure the policy is using trustworthy trade-path statistics rather than guessed or lossy values.

### Work packages

#### R4-A — Path-stat state model
Introduce or harden canonical state for:
- MFE,
- MAE,
- best ROI,
- drawdown from peak,
- bars/time since entry,
- checkpoint hit history.

#### R4-B — Restart behavior
Define what happens on restart:
- exact restore,
- degraded restore,
- unknown state.

#### R4-C — Freshness policy
Define acceptable staleness for:
- features,
- regime,
- position snapshot,
- price reference.

### DoD
- path stats are explicitly owned,
- restart semantics are documented,
- degraded/unknown states are visible,
- policy refuses to act on insufficient truth when configured fail-closed.

### Test / Validation

#### Stateful tests
- path stats update correctly through rising/falling prices,
- peak giveback computed correctly,
- checkpoint history monotonic and idempotent.

#### Restart tests
- warm restart exact restore,
- degraded restore marked as degraded,
- unknown restore cannot silently act in strict mode.

#### Fault-injection tests
- missing feature snapshot,
- delayed regime update,
- partial position info,
- conflicting timestamps.

### Fail conditions
- path stats reconstructed by implicit guessing,
- restart produces false confidence,
- stale context still allows protect/exit silently.

---

## Phase R5 — Shadow Quality Evaluation Against Historical Recorder / Live Logs
**Status target:** prove policy value before actioning

### Objective
Quantify whether lifecycle policy would have helped.

### Core evaluation questions
- how many profitable trades later hit full SL?
- how much peak unrealized edge was given back?
- when would protect have triggered?
- when would exit have triggered?
- how often would shadow exits cut winners too early?
- how often would shadow protect reduce catastrophic giveback?

### Required datasets
- recorder/bar data,
- order lifecycle logs,
- trade lifecycle traces,
- position outcomes,
- optionally screenshot/manual forensic annotations for ambiguous cases.

### Deliverables
- baseline vs shadow-policy comparison,
- symbol-level analysis,
- regime-level analysis,
- false-positive and false-negative cases,
- recommended initial thresholds/modes.

### DoD
- evidence exists across multiple symbols / regimes / weeks,
- edge preservation and opportunity loss both measured,
- recommendations are tied to data, not intuition,
- report separates proven gains from speculative gains.

### Test / Validation

#### Historical replay tests
- shadow policy on archived runs,
- checkpoint hit detection correctness,
- deterministic metrics across reruns.

#### Counterfactual evaluation
- baseline realized outcome,
- policy-adjusted hypothetical outcome,
- careful separation of “could protect” vs “would execute exactly.”

#### Adversarial evaluation
- fast spike then continuation,
- fake exhaustion then second-leg trend,
- dead chop after entry,
- illiquid spread widening,
- regime flip while in profit.

### Fail conditions
- shadow benefit claimed without execution-feasibility caveat,
- only aggregate PnL shown without case breakdown,
- early-exit damage hidden.

---

## Phase R6 — Protect-Only Recommendation Rollout
**Status target:** zero autonomous execution mutation

### Objective
Enable lifecycle policy as recommendation-only for `PROTECT`, while keeping execution unchanged.

### Work packages
- recommendation surface in logs/alerts,
- operator-facing summaries,
- optional dry-run “what would have been adjusted” traces.

### DoD
- protect recommendations visible in real time,
- repeated recommendation spam bounded,
- recommendations explainable and replayable,
- no order mutation occurs.

### Test / Validation
- no accidental `DEC:ADJUST` or close commands emitted,
- recommendation cooldown verified,
- protect eligibility requires minimum conditions,
- live/shadow consistency checks.

### Fail conditions
- recommendation mode mutates orders,
- protect recommendation cannot be audited later,
- unclear difference between recommend and commit.

---

## Phase R7 — Protect-Only Action Rollout (Bounded)
**Status target:** first real action-capable stage

### Objective
Allow **bounded protect actions** under strict conditions.

### V1 scope
Only allow one or more of the following if already contract-safe and execution-proven:
- move stop to breakeven,
- move stop to locked positive threshold,
- tighten protective stop under bounded monotonic rules.

No broad partial-close dependency required for entry.

### Hard constraints
- protect may only tighten risk, never loosen it,
- protect cannot mutate truth invisibly,
- protect command frequency bounded,
- protect only valid after minimum accrued edge,
- protect must be idempotent or safely deduplicated.

### DoD
- protect actions emit canonical events,
- action path is replayable,
- protect action cannot widen loss,
- protect rollback switch exists,
- post-action state remains consistent with execution truth.

### Test / Validation

#### Execution integration tests
- protect command -> order mutation path,
- repeated protect command dedupe,
- exchange rejection handling,
- bracket sync after protect.

#### Property tests
- monotonic stop tightening,
- no protect action worsens max loss,
- protect cooldown obeyed.

#### Failure-path tests
- adapter reject,
- bracket missing,
- partially stale position snapshot,
- race with fill / close / stop hit,
- restart during protect command.

#### Shadow-vs-live comparison
- compare recommended protect and executed protect behavior.

### Fail conditions
- protect action widens risk,
- bracket state desync emerges,
- repeated protect thrashes orders,
- rollback unavailable.

---

## Phase R8 — Exit Recommendation Rollout
**Status target:** shadow/recommendation only

### Objective
Enable explainable exit recommendations based on degradation and exhaustion.

### Work packages
- exit recommendation triggers,
- reasoning vectors,
- confidence vs urgency separation,
- giveback-aware exit advisories.

### DoD
- exit recommendations visible and reviewable,
- why-code taxonomy stable,
- recommendations classified by source:
  - time decay,
  - confirmed exhaustion,
  - continuation collapse,
  - giveback breach,
  - stale context block.

### Test / Validation
- deterministic recommendation replay,
- no silent recommendation gaps,
- classification correctness on curated scenarios,
- counterfactual damage analysis.

### Fail conditions
- exit recommendations mix multiple meanings without precedence,
- recommendation rationale missing,
- no distinction between soft concern and mandatory exit.

---

## Phase R9 — Exit Action Rollout (Guarded)
**Status target:** production trial under strongest controls

### Objective
Allow policy-driven exit actions once shadow evidence is strong enough.

### Hard prerequisites
- protect-only rollout stable,
- exit recommendation quality reviewed,
- false-positive damage acceptable,
- live observability complete,
- rollback proven.

### Guardrails
- initially limited to allowlisted symbols/strategies/regimes,
- limited daily activation cap,
- kill-switch available,
- action emitted only from explicit `protect_and_exit` mode,
- mandatory action trace.

### DoD
- exit actions are bounded and reversible operationally,
- false-positive incidents diagnosable,
- policy reasons visible at execution boundary,
- no unowned close-path mutation.

### Test / Validation

#### End-to-end action tests
- exit recommendation -> intent/command -> execution close path,
- concurrent stop-hit vs policy-exit race,
- double-close prevention,
- reconciliation consistency.

#### Adversarial tests
- fast reversal after exit recommendation,
- recovery after fake exhaustion,
- regime stale mismatch,
- delayed feature update.

#### Operational soak tests
- several days of live shadow/live compare,
- action counters,
- incident review sample.

### Fail conditions
- unexplained exits occur,
- action path bypasses observability,
- double-close / race defects appear,
- rollback not immediate.

---

## Phase R10 — Expand Action Vocabulary (Optional, Later)
**Status target:** only after v1 proven

### Objective
Extend beyond basic protect/exit if justified.

### Candidate extensions
- partial scale-out,
- dynamic re-protect ladder,
- regime-conditioned hold expansion,
- symbol-specific continuation curves,
- hierarchical checkpoint ladders,
- portfolio-aware protect prioritization.

### DoD
- each new action has its own contract,
- each new action has execution proof,
- no semantic overloading of existing actions.

### Test / Validation
- separate package-level tests for each new action,
- exchange behavior proofs,
- restart and race coverage,
- operator interpretability review.

### Fail conditions
- overloading `PROTECT` into multiple hidden sub-actions,
- adding partial close without safe ownership model,
- feature richness outrunning observability.

---

# 10. Testing Standard (Mandatory)

This project must not accept “green tests” as proof by themselves.

The testing standard for this initiative has four layers.

## 10.1 Layer A — Contract Tests
Prove schema, typing, config validation, registry correctness.

Mandatory coverage:
- Pydantic validation,
- forbidden unknown fields,
- invalid threshold combinations,
- unsupported modes/actions,
- unsorted/duplicate ROI ladders,
- missing required event fields,
- serialization stability.

## 10.2 Layer B — Deterministic Logic Tests
Prove pure policy logic on controlled inputs.

Mandatory coverage:
- checkpoint detection,
- continuation/protection/exit thresholds,
- precedence rules,
- giveback logic,
- dead-trade timeout,
- stale input blocking,
- protect cooldown,
- mode gating.

## 10.3 Layer C — Stateful / Integration Tests
Prove interaction with runtime state and domain boundaries.

Mandatory coverage:
- decision_making integration,
- exposure summary consumption,
- trade executed/open position tracking linkage,
- regime updates while position open,
- feature freshness changes,
- protect/exit path handoff,
- trace id continuity,
- restart / restore behavior,
- idempotency under duplicate events.

## 10.4 Layer D — Adversarial / Fault / Replay Tests
Prove behavior under messy reality.

Mandatory coverage:
- missing/stale features,
- late regime update,
- race with fill/close,
- duplicate evaluation trigger,
- restart mid-action,
- adapter reject on protect/exit,
- shadow/live mismatch,
- trend resumes after fake exhaustion,
- noise chop after first checkpoint,
- low-liquidity widening spreads.

---

# 11. Mandatory Test Matrix

Every package must explicitly state which rows are covered.

## 11.1 Scenario classes
- immediate winner continuation,
- immediate winner then fade,
- slow profitable grind,
- dead trade without progress,
- fast adverse reversal after checkpoint,
- checkpoint hit with stale inputs,
- high-liquidity vs low-liquidity environment,
- high-confidence regime vs weak regime,
- strong continuation but temporary pullback,
- fake exhaustion followed by second leg.

## 11.2 Symbol / strategy coverage
At minimum:
- Aurora representative symbol,
- Mean Reversion representative symbol,
- MD-AMR representative symbol,
- at least one symbol with historically noisy path behavior.

## 11.3 Temporal coverage
At minimum:
- calm regime,
- high-vol regime,
- transition regime,
- weekend/thin-liquidity segment if applicable,
- multi-day replay.

## 11.4 Failure coverage
At minimum:
- startup with policy enabled but missing config,
- restart with degraded path stats,
- duplicate event delivery,
- action mode mismatch,
- registry omission,
- schema omission,
- downstream execution reject.

---

# 12. Evidence Standard and REPORT Requirements

A package is not done until it ships a **REPORT**.

## 12.1 Every REPORT must contain
- objective,
- exact files changed,
- contracts added/modified,
- schemas/registry changes,
- config changes,
- tests added,
- tests executed,
- replay or runtime evidence,
- known limits,
- rollback note,
- explicit verdict:
  - DONE
  - DONE WITH RESERVATIONS
  - NOT DONE

## 12.2 Required validation evidence categories
At least one of the following per meaningful package, and usually more than one:
- unit/property test output,
- integration test output,
- replay output,
- live/shadow runtime trace sample,
- forced-fault sample,
- event lineage sample,
- controlled before/after comparison.

## 12.3 Forbidden acceptance patterns
- “tests green” without scenario matrix,
- “works locally” without evidence,
- “probably safe” without failure-path proof,
- “shadow looked okay” without reproducible output,
- merged code without REPORT.

---

# 13. Risk Register

## RISK-1 — Split-brain lifecycle ownership
If policy state is treated as position truth, system semantics become ambiguous.

**Mitigation:** policy mode != execution state, explicit owner docs, integration tests.

## RISK-2 — `DEC:ADJUST` semantic weakness
The verb exists but may be too weakly formalized today to carry broad protect semantics safely.

**Mitigation:** start with recommendation mode; prove bounded protect path first; add schema if action path is formalized.

## RISK-3 — Over-eager exits
Policy may cut winners too early.

**Mitigation:** shadow evaluation, adversarial tests, false-positive review, staged rollout.

## RISK-4 — Invisible no-ops / silent blocks
Policy could evaluate and do nothing without observability.

**Mitigation:** mandatory evaluated/blocked events and why-codes.

## RISK-5 — Restart truth degradation
Path stats after restart may be weak or guessed.

**Mitigation:** explicit degraded/unknown semantics and strict-mode blocking.

## RISK-6 — Config sprawl / dual SSOT
Policy knobs may leak into wrong YAML surfaces.

**Mitigation:** single canonical config surface, typed validation, docs update.

## RISK-7 — Order thrashing under protect
Repeated protect actions may spam adjustments or destabilize brackets.

**Mitigation:** cooldown, idempotency, bounded monotonic protect rules.

---

# 14. Implementation Sequence (Recommended Order)

The following order is recommended and should be treated as default unless hard evidence requires deviation.

1. **R0 Governance Freeze**
2. **R1 Surface Discovery / Context Audit**
3. **R2 Contract Design**
4. **R3 Observability First**
5. **R4 Path-Stats Hardening**
6. **R5 Historical / Shadow Quality Evaluation**
7. **R6 Protect Recommendation Rollout**
8. **R7 Protect Action Rollout**
9. **R8 Exit Recommendation Rollout**
10. **R9 Exit Action Rollout**
11. **R10 Optional Extensions**

The sequence is intentionally conservative because protect-path safety is easier to prove than autonomous exit correctness.

---

# 15. Minimal Acceptable v1

The minimum acceptable version that may be considered “real” is:

- strict typed config,
- typed policy input/output,
- registry-backed observability events,
- shadow evaluation,
- explainable rationale,
- replayable policy traces,
- bounded `PROTECT` behavior,
- optional but controlled `EXIT` action only after evidence,
- no hidden ownership violations.

Anything below this is not a mature implementation, only an experiment.

---

# 16. Final Acceptance Criteria for the Initiative

This initiative can be considered materially implemented only when all of the following are true:

1. The system can **evaluate open positions repeatedly** using explicit typed inputs.
2. The system can **explain** why it held, protected, or exited.
3. The policy is **observable and replayable**.
4. The protect path is **bounded, monotonic, and test-proven**.
5. The exit path, if enabled, is **staged, auditable, and rollback-safe**.
6. The implementation respects **decision-making ownership** and does not steal truth from execution-position.
7. All major packages have **REPORT + validation evidence**.
8. Historical and/or live evidence shows that the policy **reduces avoidable giveback without unacceptable opportunity destruction**.

---

# 17. Executive Summary

The correct way to implement ROI-gated position lifecycle logic in Aurora / Phenix is **not** as a second position FSM and **not** as an execution hack.

It must be built as a **decision-owned, contract-safe, replayable post-entry policy layer** that:
- re-evaluates continuation quality,
- protects accrued edge,
- exits when holding no longer makes mathematical sense,
- and hands off action cleanly to execution-position without violating runtime truth ownership.

The implementation must proceed through:
- discovery,
- contracts,
- observability,
- path-truth hardening,
- historical/shadow proof,
- recommendation rollout,
- guarded action rollout,
- and only later richer action vocabulary.

That is the only path that is both economically useful and architecturally honest.
