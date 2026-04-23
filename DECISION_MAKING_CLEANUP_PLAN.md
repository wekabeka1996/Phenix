# Decision Making Cleanup Plan

## Scope and constraints

This plan is derived from read-only audit evidence only.

Constraints retained from the audit request:

- no broad rewrite
- contract-first and additive-only where possible
- YAML + Pydantic remain SSOT
- docs/comments do not count as runtime proof
- runtime behavior matters more than declarations

No runtime code changes were made while preparing this plan.

## FACTS

### 1. Top 10 cleanup candidates

| Rank | Candidate | Why it ranks here | Smallest safe change shape | Validation target |
| --- | --- | --- | --- | --- |
| 1 | Resolve QUADRATIC_DECISION_TRACE contract gap | Runtime emits it and local metadata exports it, but central verb registry does not register it | Either register the verb centrally with explicit schema/owner or retire/rename the event | Registry search plus targeted handler/event tests |
| 2 | Resolve HANDLER_READINESS_DIAGNOSTICS declaration gap | Central registry and local metadata declare it active, but no runtime emitter was found | Either implement a real emitter or retire the contract from metadata/registry | Workspace grep plus focused runtime/contract test |
| 3 | Resolve ALPHA_SCORE_CALCULATED single-owner story | Runtime proves dual emitters while registry still says alpha_search owns the verb | Choose one owner model: single-owner rename/migration, or explicit multi-producer contract with clear semantics | Registry/schema alignment plus event-contract tests |
| 4 | Unify TRADE_INTENT_REJECTED truth shaping | IntentEmitter is canonical on paper, but strategy-local handlers still bypass it in different ways | Introduce one shared shaping path for strategy-local rejects, or explicitly split pre-intent vs post-intent contracts | Reject contract tests across Aurora, MR, and MD-AMR |
| 5 | Isolate or retire DeferredIntentScheduler | Strongest proven legacy/dead candidate in the namespace | Remove export/metadata references first, then runtime file if no hidden consumers remain | Workspace import search plus targeted scheduler tests |
| 6 | Trim __init__.py public surface | Package export surface mixes active owners, compatibility residue, and stale narrative | Narrow exports or move compatibility aliases into an explicit compatibility module | Import scan plus package surface tests |
| 7 | Retire or quarantine DecisionMakingLogic alias | Alias is compatibility-only and obscures the current public surface | Replace remaining imports, then move alias behind compatibility boundary or delete | Workspace import search |
| 8 | Reconcile domain_dict.json with central registry/runtime | Local metadata currently preserves undeclared and dormant verbs and residue components | Treat domain_dict as generated/verified artifact or reduce it to proven active surfaces | Diff domain_dict against registry and code emission scan |
| 9 | Make gate ownership explicit across strategy-local and general-domain layers | Current layering is active, but who owns the final denial story is not obvious | Add one authoritative contract note and targeted tests before changing logic | Focused scenario tests for blocked/deferred/rejected cases |
| 10 | Complete degraded-context migration and retire legacy fallback keys | New strategy-scoped contracts already exist, but fallback keys remain in runtime extraction/consumption | Prove no config depends on old keys, then remove fallback layers in a bounded package | Config scan plus ReadinessGates tests |

### 2. Top 5 likely bug / contradiction surfaces

| Rank | Surface | Why it is likely bug-prone |
| --- | --- | --- |
| 1 | ALPHA_SCORE_CALCULATED dual-emitter ownership | Same verb is emitted from decision_making and alpha_search while the central registry claims one owner |
| 2 | TRADE_INTENT_REJECTED split truth path | Aurora, MR, MD-AMR, and IntentEmitter do not shape/persist rejects through one clearly authoritative path |
| 3 | QUADRATIC_DECISION_TRACE registry gap | Runtime event exists without central registration, making contract consumers and audits blind by default |
| 4 | HANDLER_READINESS_DIAGNOSTICS dormant contract | Registry and local metadata promise an active diagnostic that the inspected runtime does not emit |
| 5 | Gate ownership overlap across StrategyGateway, DecisionMaking fallback, and Aurora local gates | Multiple layers can block, defer, or narrow decisions with different contexts and reason surfaces |

### 3. Top 5 missing runtime-proof surfaces

| Rank | Missing proof surface | What is missing |
| --- | --- | --- |
| 1 | HANDLER_READINESS_DIAGNOSTICS | No runtime emitter or observed usage was found |
| 2 | DeferredIntentScheduler | No runtime consumer was found beyond tests and package export |
| 3 | QUADRATIC_DECISION_TRACE | No central registry entry or schema-backed contract was found |
| 4 | Unified reject truth | No proof that all strategy-local reject paths produce one canonical event + WAL truth surface |
| 5 | Canonical final denial owner | No executed proof that one layer authoritatively owns the final blocked/deferred/rejected story across general and strategy-local gates |

### 4. Recommended sequencing

#### Package A: Contract cleanup first

1. QUADRATIC_DECISION_TRACE: register or retire.
2. HANDLER_READINESS_DIAGNOSTICS: implement or retire.
3. ALPHA_SCORE_CALCULATED: make ownership explicit.

Why first:

- These are the cleanest contradictions.
- They affect discoverability and observability immediately.
- They can be addressed without redesigning the decision pipeline.

#### Package B: Truth-surface normalization

1. Define the authoritative shaping path for strategy-local rejected intents.
2. Decide whether pre-intent strategy rejects are:
   - canonical TRADE_INTENT_REJECTED,
   - strategy-local blocked-only artifacts,
   - or a deliberately separate contract.
3. Backfill targeted tests for Aurora, MR, and MD-AMR to prove the chosen split.

#### Package C: Residue isolation

1. Remove or quarantine DeferredIntentScheduler.
2. Narrow __init__.py exports.
3. Replace DecisionMakingLogic imports and retire the alias.
4. Reconcile domain_dict.json with actual runtime/registry truth.

#### Package D: Gate ownership clarification

1. Document the intended authority order:
   - strategy-local gates,
   - general gateway gates,
   - facade fallback guards.
2. Prove one scenario each for reject, defer, and pass-through.
3. Only then decide whether any gate layer should be removed or merged.

## INFERENCES

- The right cleanup strategy is bounded normalization, not redesign.
- The highest-value wins are contract integrity and truth-path unification, not moving large files around.
- DeferredIntentScheduler is the strongest candidate for actual removal; most other items need contract clarification before deletion.

## ASSUMPTIONS

- None are required for the ranking itself.

## UNKNOWNS

- No runtime traffic analysis was performed, so ranking is based on contradiction severity and blast radius, not observed production frequency.
- External consumers outside this workspace may still depend on compatibility exports.

## Final verdict

decision_making is active and materially wired. It is not a dead package.

The real problem is not simple obsolescence. The namespace now mixes:

- active general-domain owners
- active strategy-local runtimes
- compatibility residue
- local-metadata drift
- central contract drift

The correct next step is a bounded cleanup program focused on contract normalization and residue isolation. A broad rewrite is not justified by the evidence gathered here.
