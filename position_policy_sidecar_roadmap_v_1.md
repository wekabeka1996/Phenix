# OFFICIAL ROADMAP v1.0
## Position Policy Sidecar — Toward Explainable Open-Position Life Management

### Status
Working implementation roadmap / SSOT planning artifact

### Scope
This roadmap covers only one initiative:

> **implementation of a separate Position Policy Sidecar module for already-open positions**

This initiative is explicitly about:
- open-position life evaluation,
- soft early-loss governance,
- conviction decay,
- regime exhaustion as policy interpretation,
- recommendation-first rollout,
- later guarded evolution toward action-capable behavior.

This roadmap is **not** about:
- rewriting execution_position FSMs,
- rewriting RegimeDetector,
- BTC-led regime mutation,
- TP extension in the first package,
- exact close-by-id in the first packages,
- broad decision_making refactors.

---

# 1. Final Goal

The end goal is **not** to add “just another exit heuristic.”

The real end goal is:

> **build a contract-safe, explainable, replayable, additive open-position policy layer**
> that can evaluate the health of already-open positions,
> suppress itself under incumbent ownership,
> and later, if proven safe, influence symbol-scoped close behavior through existing execution contracts.

The sidecar must become:
- explainable,
- bounded,
- replay-testable,
- shadow-first,
- additive-only,
- and operationally survivable.

---

# 2. Architectural Laws

These are frozen for the whole initiative.

## 2.1 Ownership laws
- `ManageFlowFSM` remains the local SSOT for open-position and bracket lifecycle.
- `CloseExecutor` remains the close executor.
- `OrderGuardian` remains reconcile / tidy owner.
- `OrderIndex` remains order correlation owner.
- The sidecar is never allowed to become the new lifecycle truth owner.

## 2.2 Contract laws
- YAML + Pydantic remain the SSOT.
- No silent fallbacks.
- No hidden business constants.
- No fake close-by-id semantics.
- No untyped config switches.
- No bracket mutation in early rollout packages.

## 2.3 Safety laws
- Recommendation-first.
- Action later only with explicit validation evidence.
- Fail closed if freshness / ownership / state ambiguity is not proven.
- Suppress under incumbent close-in-progress or terminal lifecycle conditions.
- Prefer silence over wrong action.

## 2.4 Scope laws
- Phase 1 handles **soft early-loss governance only**.
- Positive-position optimization is deferred.
- TP extension / target replacement is deferred.
- Stop-tightening ownership remains with existing incumbents in early rollout.
- Macro/BTC/anchor context is excluded from Phase-1 action-bearing logic.

---

# 3. Current Proven Runtime Truth

This section must be treated as design baseline.

## 3.1 What the current close contract really is
Current close execution is:
- symbol-scoped,
- reduce-only,
- based on current live net symbol position,
- optionally qty-based for partial reduce,
- **not** lifecycle-targeted,
- **not** order-id-targeted,
- **not** position-id-targeted.

## 3.2 What already exists in the project
The system already has:
- TP1 / TP2 / SL bracket lifecycle,
- trailing stop replacement,
- max-hold close,
- regime-flip close,
- Aurora `ExitManager`,
- duplicate close hardening,
- reconcile / tidy distinction,
- portfolio and feature streams sufficient for additive evaluation.

## 3.3 What is missing
The system still lacks:
- a dedicated open-position health evaluator,
- unified position-health observability,
- exact executable lifecycle identity,
- public close-initiation attribution,
- safe Phase-1 action contract for anything beyond recommendation-only.

---

# 4. Program Strategy

We will implement this initiative through **progressive hardening packages**, not one big patch.

The sequence is:

1. **Governance Freeze**
2. **Contract & Config Package**
3. **Shadow Sidecar Core Package**
4. **Forensic Logging & Observability Package**
5. **Shadow Validation Package**
6. **Policy Calibration Package**
7. **Action-Readiness Gate Review**
8. **Phase-2 Action Package (only if admitted)**
9. **Post-Action Stabilization Package**
10. **Deferred Future Extensions**

No package is considered done without:
- implementation,
- tests,
- validation evidence,
- REPORT,
- explicit statement of what remains unproven.

---

# 5. Delivery Phases

---

## PHASE 0 — Governance Freeze
### Goal
Freeze the architectural meaning of the project before implementation starts.

### Deliverables
- this roadmap,
- explicit package order,
- frozen Phase-1 scope,
- explicit non-goals,
- explicit ownership rules,
- explicit testing doctrine.

### Required decisions
- sidecar location: `execution_position`
- config mode surface: `disable | shadow | enable`
- Phase-1 scope: soft early-loss governance only
- Phase-1 output posture: recommendation-only
- primary forensic log: `trade_lifecycle.jsonl`

### DoD
Done only when:
- roadmap is saved,
- operator agrees on frozen Phase-1 scope,
- no active ambiguity remains about owner boundaries,
- future implementation packages can reference this roadmap as SSOT.

### Testing requirements
No code testing here.
Validation instead must confirm:
- roadmap is internally consistent,
- ownership boundaries are explicit,
- no package requires forbidden Phase-1 behavior.

---

## PHASE 1 — Contract & Config Package
### Goal
Introduce strict typed config and wiring contract for the sidecar without yet implementing business logic.

### Implementation scope
- Add typed config model under canonical SSOT.
- Preferred canonical location:
  - `domains.execution_position.position_policy_sidecar`
- Add strict mode enum:
  - `disable`
  - `shadow`
  - `enable`
- Add typed settings for:
  - freshness requirements,
  - startup grace,
  - profitability guard,
  - thresholds,
  - logging options,
  - allowed action scope.
- Wire config loading and validation.
- Add startup / registration behavior without business evaluation yet.

### Must NOT do
- no action logic,
- no event evaluation,
- no telemetry scoring,
- no sidecar decisioning,
- no fake future fields without typed usage rationale.

### DoD
Done only when:
- typed config exists,
- YAML config exists,
- invalid values fail closed,
- unknown fields are rejected,
- mode enum is validated,
- startup wiring reflects config mode,
- REPORT states exact config path and semantics.

### Required testing
#### Contract tests
- valid modes accepted,
- invalid mode rejected,
- missing required fields rejected,
- extra fields rejected,
- threshold/freshness constraints validated.

#### Wiring tests
- `disable` → sidecar not active,
- `shadow` → sidecar wiring active,
- `enable` → sidecar wiring active,
- mode reflected in startup diagnostics.

#### Negative tests
- malformed YAML rejected,
- wrong enum case rejected,
- missing nested config rejected if required.

### REPORT requirements
- files changed,
- config model summary,
- YAML snippet,
- test list and outputs,
- any remaining config ambiguities.

---

## PHASE 2 — Shadow Sidecar Core Package
### Goal
Implement the new separate module as a derived-context evaluator in recommendation-only posture.

### Implementation scope
Create a new separate module, tentatively:
- `apps/reference/domains/execution_position/position_policy_sidecar.py`

The sidecar must:
- subscribe to required runtime events,
- maintain derived per-symbol local cache only,
- detect whether an already-open position is eligible for evaluation,
- compute bounded scores,
- emit evaluation / suppression / recommendation traces,
- never emit execution action in this package.

### Required event subscriptions
Minimum viable:
- `EVT:PORTFOLIO_STATE_UPDATED`
- `EVT:ORDER_FILL`
- `EVT:ORDER_STATE_CHANGED`
- `EVT:EXECUTION_CLOSE_RECONCILED`
- `EVT:REGIME_DETECTED`
- `EVT:FEATURES_CALCULATED`

Optional only if evidence supports it cleanly:
- `EVT:TRADE_EXECUTED`
- `EVT:EXIT_MATCH_ATTEMPTED`
- `EVT:EXIT_MATCH_FAILED`

### Derived local cache allowed
- latest portfolio snapshot by symbol,
- latest regime snapshot by symbol,
- latest feature snapshot by symbol,
- local timestamps,
- local last evaluation state,
- local suppression markers.

### Derived local cache forbidden
- no authoritative lifecycle truth,
- no replacement of `_closing_position`,
- no replacement of bracket ownership,
- no replacement of reconcile truth.

### Required internal signals
Implement bounded signals such as:
- `position_health_score`
- `exit_pressure_score`
- `hold_confidence`
- `soft_close_pressure`
- `regime_exhaustion_hint`
- `microstructure_adverse_pressure`

### Phase-1 scoring rules
- bounded ranges only,
- capped contributions,
- stale context collapses to neutral/suppressed,
- profitable guard suppresses action-bearing recommendation,
- no macro/BTC/anchor inputs in action-bearing logic,
- no absorption dependency unless proven stable enough,
- no tick-only dependency.

### Suppression rules
Sidecar must remain silent when:
- no open lifecycle proven,
- `_closing_position` or equivalent close-in-progress visible,
- reconcile already happened,
- latest features are stale/missing,
- latest regime is stale/missing,
- warmup is incomplete,
- startup grace not elapsed,
- position clearly profitable,
- local state ambiguous after terminal/partial transitions.

### DoD
Done only when:
- new separate sidecar file exists,
- sidecar subscribes correctly,
- sidecar computes bounded derived scores,
- sidecar emits no action,
- sidecar suppresses correctly,
- no incumbents lose ownership,
- REPORT includes honest explanation of all implemented signals and suppression rules.

### Required testing
#### Unit tests
- score calculation bounds,
- stale data suppression,
- profitable guard suppression,
- no-lifecycle suppression,
- close-in-progress suppression,
- reconcile suppression,
- neutral behavior under missing data.

#### Integration tests
- event subscription works,
- sidecar sees actual open position transitions,
- sidecar does not evaluate after authoritative close,
- sidecar does not fire during bracket terminal resolution.

#### Conflict tests
- no sidecar recommendation while max-hold close already in progress,
- no recommendation during duplicate-close suppressed state,
- no recommendation after terminal bracket fill.

#### Negative tests
- malformed event payload handled fail-closed,
- stale timestamps handled fail-closed,
- missing feature block handled fail-closed.

### REPORT requirements
- exact module path,
- exact subscriptions,
- internal cache design,
- score formula summary,
- suppression matrix,
- full test evidence.

---

## PHASE 3 — Forensic Logging & Observability Package
### Goal
Make sidecar behavior explainable and replay-auditable.

### Implementation scope
Add structured logging / trace emission for:
- evaluation started,
- evaluation completed,
- suppression reason,
- recommendation emitted,
- mode active,
- score snapshot,
- freshness snapshot,
- incumbent precedence detection,
- action skipped because Phase-1 recommendation-only.

### Primary log target
- `trade_lifecycle.jsonl`

### Secondary log target
- `order_log_v1.jsonl` only for events that are truly order-centric.

### Required record kinds
- `POSITION_POLICY_SIDECAR_EVALUATED`
- `POSITION_POLICY_SIDECAR_SUPPRESSED`
- `POSITION_POLICY_SIDECAR_RECOMMENDED`
- `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`
- `POSITION_POLICY_SIDECAR_MODE_ACTIVE`

### Required fields
- `trace_id`
- `symbol`
- `sidecar_version`
- `mode`
- `evaluation_mode`
- `reason_codes`
- `position_snapshot`
- `feature_ref`
- `regime_ref`
- `score_snapshot`
- `freshness_snapshot`
- `suppression_reason`
- `incumbent_owner` if applicable

### Must NOT do
- no fake exact-target identifiers,
- no misleading `position_id`,
- no silent drops of suppression reason,
- no dumping position-policy events into wrong order log semantics.

### DoD
Done only when:
- sidecar traces are structurally present,
- suppression always has a reason,
- recommendation always has a score snapshot,
- mode always appears in runtime trace,
- `trade_lifecycle.jsonl` becomes the authoritative forensic surface for this feature,
- REPORT includes sample records.

### Required testing
#### Log schema tests
- all required fields present,
- missing required fields fail tests,
- record kinds emitted in correct situations.

#### Behavioral logging tests
- suppressed evaluation emits suppression record,
- recommendation emits recommendation record,
- disable mode does not emit evaluation trace,
- shadow mode emits evaluation but not action.

#### Forensic coherence tests
- recommendation not emitted after reconcile,
- suppression includes incumbent owner when applicable,
- trace_id persists across evaluation and recommendation for same cycle.

### REPORT requirements
- example records,
- log placement rationale,
- field dictionary,
- any observability gaps still unresolved.

---

## PHASE 4 — Shadow Validation Package
### Goal
Validate recommendation quality and overlap under real event order without action risk.

### Validation scope
Shadow only.
No direct close requests.
No bracket mutation.
No partial reduce.

### Required validation layers
#### A. Event-faithful replay validation
Replay must preserve event order for:
- features,
- regime,
- order fills,
- order state changes,
- portfolio snapshots,
- close reconcile.

#### B. Live shadow validation
Run sidecar in shadow mode during actual runtime and collect forensic outputs.

#### C. Overlap validation
Measure overlap with:
- `ExitManager`
- regime-flip close
- max-hold close
- bracket terminal exits
- duplicate close suppression windows

### Required metrics
- evaluation count by symbol,
- suppression count by reason,
- recommendation count,
- overlap count with incumbent close events,
- estimated early saved loss,
- premature close rate,
- explainability completeness,
- recommendation-to-incumbent timing relation.

### Required review slices
- by symbol,
- by strategy,
- by regime,
- by confidence bucket,
- by microstructure pressure bucket,
- by position age bucket.

### DoD
Done only when:
- replay validation executed,
- live shadow traces collected,
- false positive / premature close analysis completed,
- overlap with incumbents quantified,
- explainability completeness measured,
- REPORT concludes whether Phase-1 policy is promising or noisy.

### Required testing / validation evidence
This package is not only “green tests”. It requires:
- replay outputs,
- trace samples,
- side-by-side case reviews,
- quantitative summary,
- operator-readable error taxonomy.

### REPORT requirements
- validation method,
- metrics summary,
- best/worst examples,
- overlap diagnosis,
- recommendation on whether to calibrate, revise, or halt.

---

## PHASE 5 — Policy Calibration Package
### Goal
Tune thresholds and composite logic after shadow evidence exists.

### Implementation scope
- adjust thresholds,
- refine score weighting/caps,
- refine suppression rules,
- refine freshness windows,
- refine startup grace,
- refine profitability guard.

### Must NOT do
- no action enablement yet,
- no new contract semantics,
- no macro/BTC injection,
- no bracket mutation,
- no partial reduce.

### DoD
Done only when:
- calibration changes are evidence-driven,
- before/after validation comparison exists,
- premature close rate is reduced or controlled,
- explainability remains complete,
- REPORT states exact changes and why.

### Required testing
- regression tests from previous phases,
- threshold edge-case tests,
- calibration snapshot comparisons,
- replay before/after comparison,
- adverse-case scenario rechecks.

### REPORT requirements
- old vs new thresholds,
- why changed,
- before/after metrics,
- unresolved risk areas.

---

## PHASE 6 — Action-Readiness Gate Review
### Goal
Decide whether Phase 2 action mode is admissible at all.

### Review questions
- Is recommendation quality stable enough?
- Is overlap with `ExitManager` sufficiently understood?
- Are suppression rules reliable?
- Are traces sufficient for race forensics?
- Is symbol-scoped close enough for the actual business need?
- Is there acceptable false-positive risk?

### Possible outcomes
#### Outcome A — Promote to Phase 2
Only if evidence is strong.

#### Outcome B — Stay in shadow
If recommendation quality is still unclear.

#### Outcome C — Rework Phase 1
If overlap/noise is too high.

### DoD
Done only when:
- explicit admission decision recorded,
- rationale documented,
- promotion or hold decision based on evidence, not intuition.

### Required validation evidence
- final shadow metrics,
- overlap matrix,
- selected case reviews,
- operator signoff or rejection note.

---

## PHASE 7 — Phase-2 Action Package (Conditional)
### Goal
Allow guarded action only if Phase 1 is admitted.

### Allowed Phase-2 scope
- EP-internal request path only,
- symbol-scoped soft-close action only,
- still no close-by-id,
- still no bracket mutation,
- still no TP extension,
- still no partial reduce unless separately admitted.

### Preferred action model
- sidecar emits EP-internal request,
- existing EP owner translates request into current symbol-scoped close path,
- sidecar still does not become executor.

### Required new contracts before activation
At minimum:
- explicit policy source attribution,
- request-to-outcome linkage,
- suppression reason linkage,
- outcome trace from request through reconcile.

### DoD
Done only when:
- action path implemented under feature flag / mode,
- action only uses current valid close semantics,
- all action events are attributable,
- sidecar remains non-owner,
- REPORT states exact action contract truth.

### Required testing
#### Unit tests
- action request only in `enable`,
- no action in `shadow`,
- no action in `disable`,
- suppression prevents action under incumbent precedence.

#### Integration tests
- action request reaches current close path,
- no fake target identity introduced,
- no duplicate action when incumbents already closing,
- close request logs policy source.

#### Simulation / replay tests
- action counterfactual vs actual,
- duplicate suppression correctness,
- request-to-reconcile linkage.

#### Failure-mode tests
- stale state in enable mode → fail closed,
- missing regime/features in enable mode → fail closed,
- existing close in progress → suppress action.

### REPORT requirements
- exact enable semantics,
- action examples,
- suppression examples,
- risks still unresolved.

---

## PHASE 8 — Post-Action Stabilization Package
### Goal
Harden the action-capable system after initial enablement.

### Implementation scope
- refine suppression,
- refine observability,
- refine overlap handling,
- remove noisy cases,
- formalize request/outcome attribution,
- strengthen diagnostics.

### DoD
Done only when:
- action traces are forensic-grade,
- false-positive action rate acceptable,
- no unexplained duplicate closes,
- overlap with incumbents understandable,
- rollback remains trivial.

### Required testing
- regression suite,
- live shadow vs enable comparisons,
- action attribution tests,
- duplicate suppression tests,
- recovery/rollback tests.

---

## PHASE 9 — Deferred Future Extensions
This phase is explicitly not part of the first implementation wave.

Possible later topics:
- partial reduce policy,
- profitable runner governance,
- TP extension,
- TP replacement,
- stop-tightening ownership contract,
- macro-aware additive policy,
- exact lifecycle/position targeting,
- executable `position_id` contract.

### Admission rule
None of these may start until:
- current sidecar is stable,
- observability is strong,
- overlap with incumbents is well-characterized,
- and required new contracts are explicitly designed.

---

# 6. Testing Doctrine

This initiative may not rely on “green tests” as its proof of correctness.

## 6.1 Required test categories
Every implementation package must explicitly declare which of these it covers:

### A. Contract validation tests
- strict schema,
- strict enum behavior,
- invalid config rejection,
- unknown field rejection.

### B. Unit tests
- pure score logic,
- pure suppression logic,
- local cache state transitions,
- freshness logic,
- profitability guard.

### C. Integration tests
- event subscription,
- runtime wiring,
- interaction with EP internals,
- no ownership violation,
- mode-specific behavior.

### D. Conflict tests
- incumbent precedence,
- no recommendation during close-in-progress,
- no evaluation after reconcile,
- no post-terminal duplicate behavior.

### E. Replay tests
- event-faithful replays,
- recommendation timing review,
- false positive analysis,
- overlap analysis.

### F. Forensic tests
- trace completeness,
- suppression reason presence,
- recommendation snapshot presence,
- log record correctness,
- trace_id continuity.

### G. Failure-mode tests
- stale inputs,
- missing inputs,
- malformed payloads,
- startup grace,
- ambiguous state.

### H. Rollback tests
- feature flag/mode disable,
- no incumbent dependency on sidecar,
- safe no-op when disabled.

## 6.2 Evidence requirement
A package is not accepted by “pytest passed” alone.

Acceptance requires:
- test list,
- test outputs,
- scenario matrix,
- representative forensic samples,
- edge-case analysis,
- explicit statement of what remains unproven.

---

# 7. Definition of Done Policy

## Global DoD for the initiative
The initiative is only considered successfully implemented when:
- the sidecar exists as a separate module,
- strict config exists,
- shadow mode is fully explainable,
- recommendation quality has been validated,
- incumbent overlaps are understood,
- action mode, if admitted, uses only valid current contracts,
- no fake lifecycle targeting was smuggled in,
- and each package has REPORT + validation evidence.

## Package-level DoD rule
Every package must end with:
- files changed,
- exact behavior added,
- tests added/updated,
- evidence outputs,
- operational risks,
- unproven items,
- explicit admission to next package or stop recommendation.

---

# 8. What Must Never Happen

These are fail conditions.

- Sidecar becomes a second lifecycle truth owner.
- Sidecar silently mutates bracket state in early phases.
- Sidecar claims exact close-by-id without a new identity contract.
- Sidecar duplicates `ExitManager` without explicit precedence.
- Sidecar uses macro/BTC signals as hidden action-bearing inputs in Phase 1.
- Sidecar emits action in `shadow`.
- Sidecar stays active after reconcile or close-in-progress.
- Logging is incomplete or ambiguous.
- A package is called done without REPORT and evidence.

---

# 9. Immediate Execution Order

This is the concrete order to follow now.

## Package 1
Contract & Config Package

## Package 2
Shadow Sidecar Core Package

## Package 3
Forensic Logging & Observability Package

## Package 4
Shadow Validation Package

## Package 5
Policy Calibration Package

## Package 6
Action-Readiness Gate Review

Only after explicit admission:

## Package 7
Phase-2 Action Package

## Package 8
Post-Action Stabilization Package

Deferred later:

## Package 9+
Future extensions

---

# 10. Final Operational Posture

The correct posture for this initiative is:

> **narrow, evidence-driven, additive, recommendation-first, contract-honest implementation**

We are not trying to “make it smart fast.”
We are trying to make it:
- survivable,
- explainable,
- measurable,
- and only then stronger.

That is the roadm