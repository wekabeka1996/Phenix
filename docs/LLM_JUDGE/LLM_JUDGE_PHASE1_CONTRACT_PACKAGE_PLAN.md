# LLM Judge Phase 1 Contract Package Plan

Date: 2026-04-13
Plan mode: corrected repo-grounded blueprint
Code changes: none

## 1. Executive Verdict

**GO-WITH-CONSTRAINTS**

This document is acceptable as the basis for a later, narrower implementation prompt only because it fails closed on the missing authority gaps. It is not permission to add schemas, registry entries, config keys, startup hooks, or runtime wiring yet.

Implementation planning may proceed only after all three gates below are closed:

1. the concept authority gap is closed by committing the named concept artifact or by adding an approved governing appendix that quotes the exact official Judge entry verdicts, lifecycle verdicts, modes, and substrate statement,
2. the placement/substrate decision is frozen,
3. the plan explicitly states whether startup diagnostics are in scope or deferred.

## 2. Phase 1 Scope

Phase 1 is a contract-package preparation step, not a runtime integration step.

In scope:

- recover and freeze authority for the official Judge vocabulary,
- compare repo-grounded placement variants without silently choosing one,
- define what the future package may freeze and what it must leave open,
- define validation gates for additive-only, replayable, explainable rollout,
- define the future file touch points for a later implementation task.

Out of scope:

- runtime code changes,
- Pydantic model implementation,
- schema files,
- registry edits,
- startup or plugin wiring,
- owner-path interception,
- execution-position integration,
- external LLM ingress rewiring,
- Phase 2+ adjudication or enforcement design.

## 3. FACTS

- No file matching `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` exists in the current working tree.
- A reachable `git log --all --name-only` search produced no hit for that concept file name in this clone.
- The repo currently proves three relevant rollout precedents:
  - embedded sidecar rollout under an existing owner,
  - standalone shadow substrate rollout in `alpha_search`,
  - external LLM ingress rollout in `shadow_telemetry` plus `trading.llm_orchestration`.
- `apps/reference/config_models.py` contains typed `DomainsConfig`, but no `policy_cortex` field currently exists.
- `apps/reference/config_models.py` places `position_policy_sidecar` under `execution_position`, not as a new top-level domain.
- `apps/reference/config_models.py` proves sidecar mode vocabulary `disable | shadow | enable`.
- `apps/reference/config_models.py` proves `LLMOrchestrationConfig.mode` vocabulary `baseline | hybrid_advisory | llm_primary`.
- `apps/reference/main.py` loads `config/alpha_search.yaml` and registers `alpha_search` as a startup-time plugin.
- `apps/reference/domains/execution_position/fsm.py` creates the position-policy sidecar and emits `POSITION_POLICY_SIDECAR_MODE_ACTIVE` only because the owner runtime explicitly instantiates the sidecar and calls the emission method.
- `apps/reference/domains/shadow_telemetry/main_bridge.py` proves the current external LLM path bypasses the normal `decision_making` strategy-signal route.
- `apps/reference/domains/decision_making/docs/ATLAS.md` identifies `decision_making` as the owner that produces `EVT:TRADE_INTENT_PROPOSED`.
- `vfoundation/core/protocol.py` already provides message-envelope tracing and replay fields such as `rid`, `span_id`, `parent_span_id`, `ts`, `ttl_ms`, `idempotent_key`, `why`, `mode`, `mode_contract`, and `corr_id`.
- `vfoundation/core/schema_registry.py` proves schema-registry changes are real runtime contract changes, not harmless placeholders.
- Governing roadmaps in `VFOUNDATION_METAFSM2_ROADMAP_SSOT_v1.md` and `ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md` require contract-first, additive-only, replayable, explainable, owner-safe rollout.
- No checked-in repo artifact defines the official Judge entry verdict vocabulary.
- No checked-in repo artifact defines the official Judge lifecycle verdict vocabulary.
- No checked-in repo artifact defines the official Judge operational mode vocabulary.
- No checked-in repo artifact proves that the Judge chamber substrate is already frozen to `alpha_search`.

## 4. INFERENCES

- The corrected Phase-1 artifact must preserve concept semantics by refusing to invent them where the concept is unavailable.
- The largest unresolved design fork is placement, not field naming.
- The repo proves patterns that can be reused as precedents, but those patterns do not themselves authorize Judge nouns, enums, or config ownership.
- Any Phase-1 plan that freezes verdict enums, mode enums, verb families, or startup events before the concept authority gap is closed is unsafe.
- The safe near-term output is a control blueprint that narrows future implementation work, not a code-ready package specification.

## 5. ASSUMPTIONS

- The user brief is accurate that a concept artifact named `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` exists outside the current checkout and is intended to be authoritative.
- That concept distinguishes entry verdict semantics from lifecycle verdict semantics.
- That concept defines an official operational mode surface.
- That concept may already name candidate expert classes and may already state whether chamber work belongs on the `alpha_search` rollout path.
- Any future implementation must remain additive-only, shadow-safe, replayable, explainable, and non-owner with respect to execution truth.

## 6. UNKNOWNS

Blocking unknowns:

- whether the concept artifact exists outside this checkout and, if so, whether it is already approved as SSOT,
- the official entry verdict vocabulary,
- the official lifecycle verdict vocabulary,
- the official operational mode vocabulary,
- whether the concept explicitly freezes the chamber substrate to `alpha_search`,
- whether startup diagnostics are part of the intended Phase-1 contract package.

Non-blocking unknowns:

- the first approved expert subset,
- the exact split between common evidence-envelope fields and domain-specific payload fields,
- the eventual verb family names,
- the eventual static package directory name if the chosen placement is not `alpha_search`.

## 7. Current Repo Truth Relevant to Phase 1

### 7.1 Governing Laws

- The repo requires contract-first rollout.
- The repo requires additive-only evolution.
- Policy outputs must remain replayable and explainable.
- Policy logic must not silently seize execution ownership.

### 7.2 Owner and Substrate Baselines

- `decision_making` is the current owner of trade-intent proposal.
- `execution_position` already hosts an embedded sidecar precedent, but governance documents explicitly warn against letting policy layers mutate execution truth without clear ownership.
- `alpha_search` already exists as a standalone shadow substrate with separate config and startup registration.
- `shadow_telemetry` plus `trading.llm_orchestration` prove external LLM ingress exists, but that stack is not evidence for Judge chamber semantics.

### 7.3 Repo-Proven Facts from the Replaced Draft

The prior draft was correct on the following points:

- the named concept artifact is missing from the current repo checkout,
- `shadow_telemetry` is a separate ingress path,
- sidecar and alpha-search surfaces are relevant rollout precedents,
- Phase 1 should avoid runtime interception of the live strategy-to-intent path.

### 7.4 Speculative Substitutions from the Replaced Draft

The prior draft was not justified in freezing any of the following:

- generic verdict abstractions such as `ALLOW / DENY / ABSTAIN`,
- invented Judge modes such as `off / shadow / advisory / authoritative`,
- a new default top-level `policy_cortex` domain,
- a startup event like `CORTEX_MODE_ACTIVE_V1`,
- detailed field lists for `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, or `JudgeVerdict`.

### 7.5 Direct Answers to the Critical Review Questions

- Does the concept document exist and already define authority for Phase 1?
  - Not provable from the repo. The file is absent from the working tree and from reachable git-history hits in this clone.
- What are the official concept-level operational modes?
  - Unknown from repo evidence.
- What are the official entry verdict semantics?
  - Unknown from repo evidence.
- What are the official lifecycle verdict semantics?
  - Unknown from repo evidence.
- Does the concept explicitly choose `alpha_search` as the chamber substrate?
  - Not provable from repo evidence.
- Is a new top-level domain like `policy_cortex` repo-proven for Phase 1?
  - No. It is only one possible design branch.
- Which parts of the prior draft were repo-proven facts?
  - Missing concept in checkout, separate LLM ingress path, relevant precedent surfaces, and Phase-1 avoidance of live interception.
- Which parts were speculative substitutions?
  - Generic verdicts, invented modes, `policy_cortex` default placement, startup event claims, and detailed field-level schemas.
- Which parts must be corrected before implementation?
  - Semantic vocabulary, placement, startup-scope claims, and field-level contract freezing.
- What exact unresolved design fork remains after correction?
  - The primary fork is `alpha_search`-aligned placement versus owner-aligned placement under an existing decision owner. A new dedicated domain is not approved by default.

## 8. Correct Contract Surface Proposal

### 8.1 Canonical Rule

Phase 1 may freeze contract roles and validation gates. It may not freeze Judge-specific field enums or transport nouns that the repo cannot currently prove.

### 8.2 Surface Roles That May Be Preserved Now

The following names may be used as planning placeholders because they express package roles, not yet-final wire contracts:

| Surface | What Phase 1 may freeze now | What Phase 1 must not freeze yet |
|---|---|---|
| `ExpertOutput` | One expert-sourced opinion record exists; it must carry enough provenance to support replay and later explanation. | Exact verdict enum, exact score scale, exact rationale fields, exact prompt/cost fields, exact transport schema. |
| `ChamberAggregate` | A multi-expert aggregation surface exists; it must preserve support, dissent, and evidence lineage. | Exact vote algorithm, exact aggregation fields, exact confidence math, exact conflict-resolution semantics. |
| `JudgeEvidenceEnvelope` | There is a reusable evidence bundle for carrying the inputs needed to replay a verdict. | Duplicated transport metadata already provided by `Message`; exact field set before concept recovery. |
| `JudgeVerdict` | Final Judge output exists as a distinct contract family; entry and lifecycle verdicts must remain distinct. | Generic action enums, exact field names, exact event nouns, exact authority-mode vocabulary. |

### 8.3 Rules for the Future Typed Surface

- Entry verdict contracts and lifecycle verdict contracts must remain separate canonical vocabularies unless the concept explicitly unifies them.
- The full typed surface must preserve the concept's official modes verbatim once recovered.
- If Phase 1 later admits only a subset of modes at runtime, that subset must be documented as a runtime admission rule, not as a shrinkage of the canonical type surface.
- Replay and explanation requirements are mandatory.
- Existing `Message` envelope tracing fields must be reused rather than duplicated inside Judge payloads unless a later proof shows a clear need.
- No Phase-1 contract may imply authority to open, mutate, or close positions directly.

## 9. Correct Verdict Mapping Proposal

### 9.1 Canonical Contract Rule

The canonical Judge contract must use the concept's exact verdict vocabulary once that vocabulary is recovered. Until then, no verdict enum should be committed to schemas, registry files, or config.

### 9.2 Entry and Lifecycle Handling

- Entry verdicts must map to the concept's entry vocabulary only.
- Lifecycle verdicts must map to the concept's lifecycle vocabulary only.
- A shared generic `action` field is not an acceptable substitute for either family.

### 9.3 If a Coarse Mapping Layer Is Later Needed

If downstream metrics, dashboards, or adapters later need coarse buckets, the mapping must be explicitly secondary:

1. canonical concept verdict,
2. optional coarse bucket,
3. consumer-specific behavior.

That secondary layer must be documented as a translation layer. It must not replace the canonical contract.

### 9.4 Fail-Closed Rule

If the concept vocabulary cannot be recovered, implementation must stop rather than commit surrogate enums.

## 10. Correct Config / Placement Proposal

### 10.1 Placement Variants Compared

| Variant | Repo evidence for it | Benefits | Rejection risk |
|---|---|---|---|
| `alpha_search`-aligned package | `alpha_search` already exists as a standalone shadow substrate with its own config model, config file, docs, and startup registration. | Reuses the strongest existing shadow-substrate precedent; avoids inventing a new top-level domain by default; aligns with the task brief's warning not to override an `alpha_search` substrate direction if the concept already chose it. | Current repo does not prove that Judge belongs there; alpha-search today is signal-generation, not bicameral adjudication. |
| New dedicated top-level domain such as `policy_cortex` | `DomainsConfig` proves new domains are possible in principle. | Clean separation if separately authorized. | No repo or concept evidence currently proves this is the right Phase-1 owner path; highest risk of freezing the wrong config and package boundary. |
| Existing owner-aligned placement under `decision_making` | `decision_making` is the current owner of `EVT:TRADE_INTENT_PROPOSED`; governance favors keeping policy with decision ownership rather than execution truth. | Strong owner safety if the concept frames Judge as decision policy rather than independent substrate. | The current LLM ingress path bypasses this route; the missing concept may instead place chamber work upstream on `alpha_search`. |

`execution_position` is not recommended as a primary placement candidate for Judge contracts. The sidecar precedent is real, but the lifecycle-policy roadmap explicitly warns against letting policy layers collapse into execution truth ownership.

### 10.2 Recommendation

Recommended planning baseline:

- treat the `alpha_search`-aligned branch as the provisional comparison baseline,
- reject a new dedicated `policy_cortex` domain as the default Phase-1 choice,
- keep `decision_making`-aligned placement as the only serious fallback,
- block implementation until the authority source confirms or rejects the `alpha_search` direction.

This is a planning recommendation, not a claim that `alpha_search` is already approved. It is the least destructive baseline because it preserves the possibility that the concept already froze `alpha_search`, while avoiding premature creation of a new root domain.

### 10.3 Config Discipline

- Do not reuse `trading.llm_orchestration.mode` as Judge mode authority.
- Do not infer Judge config shape from position-policy sidecar config names.
- Do not add top-level config keys until placement is frozen.
- If the chosen branch later needs startup diagnostics, those diagnostics must be tied to a proven owner load path.

## 11. File-by-File Future Implementation Blueprint

This section defines future touch points only. It is not authorization to edit them now.

### 11.1 Gate 0: Authority Recovery

Required before any code task:

- restore `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` into the repo, or
- add an approved appendix that quotes:
  - official entry verdicts,
  - official lifecycle verdicts,
  - official modes,
  - substrate/placement statement,
  - any named expert classes relevant to Phase 1.

Expected files:

- `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` or equivalent governing appendix,
- this plan,
- `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_PLAN_REVIEW_AND_CORRECTION_REPORT.md`.

### 11.2 Gate 1: Placement Freeze

Expected outcome:

- one of the two serious branches is approved:
  - `alpha_search`-aligned,
  - `decision_making`-aligned.

Files likely to matter by branch:

Alpha-search branch:

- `apps/reference/domains/alpha_search/`
- `apps/reference/domains/alpha_search/config_models.py`
- `config/alpha_search.yaml`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `apps/reference/main.py` only if later startup/runtime scope is explicitly admitted

Decision-making branch:

- `apps/reference/domains/decision_making/`
- `apps/reference/config_models.py`
- `config/aurora/domains.yaml`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `apps/reference/main.py` only if later startup/runtime scope is explicitly admitted

Dedicated new-domain branch:

- not approved by this plan,
- may only be reopened if the recovered concept or another governing artifact explicitly authorizes it.

### 11.3 Gate 2: Static Contract Package

Only after Gates 0 and 1 close:

- define exact canonical verdict vocabularies,
- define exact canonical mode vocabularies,
- define exact package-local schemas,
- register only the nouns that the recovered authority source explicitly supports,
- keep runtime behavior out unless separately approved.

Potential future file classes:

- schema package files under the chosen owner path,
- package-local README or passport surfaces,
- `apps/reference/dictionaries/verb_registry_v1.yaml`,
- any schema-registry registration surface actually used by the chosen path.

### 11.4 Files Explicitly Out of Bounds for Phase 1

- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/position_policy_sidecar.py`
- `apps/reference/domains/shadow_telemetry/main_bridge.py`
- live strategy execution handlers
- runtime enforcement hooks

Those files only become relevant in a later runtime-integration phase.

## 12. Validation Blueprint

Implementation readiness must be validated in this order:

1. Authority validation
   - Confirm the exact concept vocabulary is present in repo or quoted in an approved appendix.
2. Placement validation
   - Confirm the chosen owner path is explicitly approved and documented.
3. Contract-surface validation
   - Confirm entry and lifecycle verdicts remain distinct.
   - Confirm the full typed mode surface is preserved verbatim.
   - Confirm no surrogate enums remain.
4. Config validation
   - Confirm config lives with the chosen owner path and does not borrow unrelated mode vocabularies.
5. Replay/explainability validation
   - Confirm the package preserves provenance and references existing message-envelope tracing instead of duplicating it.
6. Runtime-scope validation
   - Confirm no startup event, startup diagnostic, or runtime hook is promised unless a concrete owner path proves it.
7. Additive-only validation
   - Confirm no existing owner contracts are silently reinterpreted or narrowed.

## 13. Risks

- Missing concept authority can create false precision if the future implementation prompt is written too aggressively.
- Wrong placement would freeze the wrong config ownership and make later correction expensive.
- Generic verdict substitution would cause semantic drift in WAL, observability, and downstream adapters.
- Startup diagnostic promises can become fake behavior if no owner path is assigned.
- Expert-taxonomy sprawl is likely if Phase 1 does not freeze an initial allowlist after authority is restored.

## 14. Open Design Decisions

| Decision | Current state | Decision criteria |
|---|---|---|
| Exact entry verdict vocabulary | Open | Must come from the recovered concept or approved appendix. |
| Exact lifecycle verdict vocabulary | Open | Must come from the recovered concept or approved appendix. |
| Exact operational modes | Open | Must come from the recovered concept or approved appendix; Phase-1 runtime subset, if any, must be declared separately. |
| Primary placement branch | Open between `alpha_search`-aligned and `decision_making`-aligned | Choose the branch that matches the recovered substrate statement while preserving owner safety and additive rollout. |
| Startup diagnostics in Phase 1 | Open | Admit only if the chosen owner path includes explicit startup wiring in scope. |
| Initial expert subset | Open | Freeze only after the authority source names or constrains the first admissible expert classes. |

The prior `policy_cortex` top-level domain proposal is not treated as an open default branch. It is rejected unless new authority reopens it.

## 15. Recommended Phase-1 Package Breakdown

### Package 1A: Authority Recovery

- recover the missing concept or approved appendix,
- quote the exact verdict and mode vocabularies,
- quote the exact substrate statement,
- record approval status.

### Package 1B: Placement Freeze

- choose `alpha_search`-aligned or `decision_making`-aligned placement,
- document why the rejected branch was rejected,
- state whether startup diagnostics are deferred or admitted.

### Package 1C: Static Contract Package

- define exact schemas only after Packages 1A and 1B close,
- keep entry and lifecycle verdict families distinct,
- preserve replay/explainability fields,
- avoid any runtime or startup wiring unless separately approved.

## 16. Final Recommended Next Implementation Task

No code implementation task should be issued yet.

The next task should be a narrow authority-recovery and placement-freeze task:

1. restore or attach the authoritative Judge concept text inside the repo,
2. extract the exact official entry verdicts, lifecycle verdicts, modes, and substrate statement into a governed appendix,
3. record the placement decision between `alpha_search`-aligned and `decision_making`-aligned rollout,
4. state explicitly whether Phase-1 startup diagnostics are deferred or included.

Only after that should a new implementation prompt be issued, and that prompt should be limited to the static contract package under the chosen owner path.
