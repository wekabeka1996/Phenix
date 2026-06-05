# LLM Judge Phase 1 Plan Review and Correction Report

Date: 2026-04-13
Artifact reviewed: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_CONTRACT_PACKAGE_PLAN.md`
Review mode: independent repo-grounded audit
Code changes: none

## 1. Executive Verdict

**RETURN FOR REVISION**

The current draft is not safe to use as an implementation basis. It contains several correct repo observations, but it also freezes unproven concept semantics, substitutes generic verdict/mode vocabulary, chooses a new domain path without authority, and claims Phase-1 startup behavior that the repo does not prove.

A corrected planning artifact is possible, but it must:

- treat the named concept SSOT as missing from the checked-out repo,
- stop freezing verdict and mode enums that cannot be verified,
- keep the placement/substrate fork explicit,
- and remove runtime/startup claims that are not tied to a proven owner path.

## 2. Scope of Review

Reviewed against:

- `VFOUNDATION_METAFSM2_ROADMAP_SSOT_v1.md`
- `ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md`
- `position_policy_sidecar_roadmap_v_1.md`
- `config/docs/llm_microstructure_strategy_passport.md`
- `config/docs/strategies_passport.md`
- `config/docs/domains_passport.md`
- `config/docs/trading_passport.md`
- `config/docs/system_passport.md`
- `apps/reference/config_models.py`
- `apps/reference/config_loader.py`
- `apps/reference/main.py`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `vfoundation/core/protocol.py`
- `vfoundation/core/schema_registry.py`
- `apps/reference/domains/decision_making/`
- `apps/reference/domains/execution_position/`
- `apps/reference/domains/feature_engineering/`
- `apps/reference/domains/alpha_search/`
- `apps/reference/domains/shadow_telemetry/`
- `apps/reference/domains/strategies/`
- the current draft itself

Special authority check performed:

- working-tree search for `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` and related names
- reachable git history search for the same concept file name

## 3. FACTS

- The checked-out repository contains exactly one LLM Judge planning artifact: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_CONTRACT_PACKAGE_PLAN.md`.
- No file matching `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md`, `*bicameral*`, `*llm*judge*`, or `*cortex*concept*` exists in the current working tree.
- A `git log --all --name-only` search produced no hit for `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md`. The current clone does not prove that the concept file ever existed on a reachable branch.
- `apps/reference/config_models.py:4550-4569` shows `DomainsConfig` as the typed container for `config.domains.*`. It currently has no `policy_cortex` field.
- `apps/reference/config_models.py:4193-4219` defines `PositionPolicySidecarConfig` inside `ExecutionPositionDomainConfig`, not as a standalone top-level domain.
- `apps/reference/config_models.py:4038-4043` defines the current sidecar mode surface as `disable | shadow | enable`.
- `apps/reference/domains/execution_position/fsm.py:785-787` explicitly creates the sidecar and calls `announce_mode_active()`.
- `apps/reference/domains/execution_position/fsm.py:3474-3479` returns `None` when `position_policy_sidecar.mode == disable`; the sidecar is not instantiated in disable mode.
- `apps/reference/domains/execution_position/position_policy_sidecar.py:291-306` emits `EVT:POSITION_POLICY_SIDECAR_MODE_ACTIVE` only because the owning execution-position runtime explicitly calls it.
- `position_policy_sidecar_roadmap_v_1.md:164-165` places the sidecar in `execution_position` and defines its config mode surface as `disable | shadow | enable`.
- `position_policy_sidecar_roadmap_v_1.md:186-237` defines Phase 1 as a contract/config package with startup wiring reflecting config mode and mode reflected in startup diagnostics.
- `apps/reference/domains/alpha_search/config_models.py:311-400` defines a separate strict config model loaded from `config/alpha_search.yaml`.
- `apps/reference/main.py:926-937` loads `config/alpha_search.yaml` directly and registers the alpha-search plugin in startup code.
- `apps/reference/domains/alpha_search/docs/ATLAS.md:4-57` documents alpha_search as a standalone signal-generation domain emitting `EVT:ALPHA_SCORE_CALCULATED`.
- `apps/reference/config_models.py:5470-5484` defines `LLMOrchestrationConfig` with modes `baseline | hybrid_advisory | llm_primary`.
- `config/docs/llm_microstructure_strategy_passport.md:8,164,201,276-278,330` and `apps/reference/domains/shadow_telemetry/main_bridge.py:137-241` show that the current external LLM path is `CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1` and bypasses the normal `decision_making` strategy-signal path.
- `apps/reference/domains/decision_making/docs/ATLAS.md:4,50,77,85` identifies `decision_making` as the owner that produces `EVT:TRADE_INTENT_PROPOSED`.
- `apps/reference/dictionaries/verb_registry_v1.yaml` already contains alpha-search, sidecar, neocortex, and LLM-ingress verb families, including `POSITION_POLICY_SIDECAR_MODE_ACTIVE` and `ALPHA_SCORE_CALCULATED`.
- `vfoundation/core/schema_registry.py:33-139` proves registry-backed schema compilation is active and additive registry changes become real runtime contract changes.
- `vfoundation/core/protocol.py:27-56` shows the message envelope already carries `rid`, `span_id`, `parent_span_id`, `ts`, `ttl_ms`, `idempotent_key`, `why`, `mode`, `mode_contract`, and `corr_id`.
- `VFOUNDATION_METAFSM2_ROADMAP_SSOT_v1.md:16-18,30-31,37,78-80` and `ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md:24,68,76-108` establish the repo's governing laws: contract-first, additive-only, replayable, explainable, and owner-safe.
- `ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md:68,76-108,1169-1177` explicitly rejects ownership leakage from policy layers into execution truth.
- No repo artifact defines the official LLM Judge entry verdict enum, lifecycle verdict enum, or operational mode enum.
- No repo artifact proves that `alpha_search` is already the frozen Judge substrate. The current repo only proves that alpha_search exists as an independent shadow substrate.

## 4. INFERENCES

- The current draft relied on the task brief as a surrogate concept SSOT. That is insufficient for freezing code-facing enums, schemas, verb names, or config placement.
- A new top-level `policy_cortex` domain is not repo-proven. It is only one design option that would need separate authority.
- Startup diagnostics such as a hypothetical `CORTEX_MODE_ACTIVE_V1` are only believable when a concrete owner creates the component and calls the emission path. Sidecar proves this pattern; it does not prove a generic Judge startup hook.
- If the missing concept later confirms `alpha_search` as the chamber substrate, the draft's `policy_cortex` recommendation would be an architecture deviation, not a neutral implementation detail.
- The current repo's LLM ingress modes (`baseline | hybrid_advisory | llm_primary`) are specific to external-intent orchestration and cannot be elevated to Judge concept authority.
- Because the concept file is absent, the safest corrected plan must treat exact Judge verdict/mode vocabulary as unresolved and must block premature registry/schema freezing.

## 5. ASSUMPTIONS

- The user brief is accurate that a concept named `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` exists outside the current checkout and is intended to be the primary SSOT.
- The concept distinguishes entry semantics from lifecycle semantics.
- The concept has official verdict and mode vocabulary richer than the generic abstractions used in the current draft.
- Any later implementation is expected to remain shadow-first, additive-only, replayable, explainable, and non-owner with respect to execution truth.

## 6. UNKNOWNS

Blocking unknowns:

- Whether the missing concept artifact is merely absent from this checkout, absent from reachable git history, or not yet committed anywhere visible from this repo.
- Whether that missing artifact is already approved as SSOT or merely intended to become SSOT.
- The official concept-level entry verdict vocabulary.
- The official concept-level lifecycle verdict vocabulary.
- The official concept-level operational mode vocabulary.
- Whether the concept explicitly freezes chamber work onto `alpha_search`.

Non-blocking but still unresolved:

- Which concrete expert classes belong to the first implementation subset.
- Whether entry and lifecycle will share one envelope family or remain strictly separate contract families.
- Whether startup diagnostics are part of the approved Judge contract surface or merely a later observability option.

## 7. What the current draft got right

- It correctly reports that the concept file is absent from the current working tree.
- It correctly identifies `shadow_telemetry` as a separate external LLM ingress path that bypasses `decision_making`.
- It correctly treats runtime interception of the strategy-to-intent path as Phase 2+ rather than Phase 1.
- It correctly identifies `DomainsConfig`, the verb registry, the schema registry, the message envelope, alpha_search, and the sidecar rollout as relevant precedent surfaces.
- It correctly recognizes that owner boundaries, replayability, explainability, and additive-only rollout are mandatory house rules.

## 8. Proven defects in the current draft

### D1. Missing concept, but concept-derived contract authority still claimed

- Claim in current draft:
  - `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_CONTRACT_PACKAGE_PLAN.md:17` says the concept file does not exist in repo.
  - `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_CONTRACT_PACKAGE_PLAN.md:121-153` then treats concept contract names and concept semantics as authoritative.
- Evidence checked:
  - working-tree search found no concept file
  - reachable git-history search found no concept file
  - no adjacent repo document restates the Judge concept's exact enums or contract list
- Verdict: **unproven**
- Why it matters operationally:
  - It turns a missing authority source into a pseudo-authority and makes later field, enum, verb, and placement choices look settled when they are not.

### D2. Generic verdict substitution freezes unproven semantics

- Claim in current draft:
  - `ExpertOutput.verdict: Literal["ALLOW", "DENY", "ABSTAIN"]`
  - `JudgeVerdict.action: Literal["ALLOW", "SUPPRESS", "ABSTAIN"]`
  - multiple fail-closed rules then depend on those values
- Evidence checked:
  - no concept file in repo
  - no adjacent repo artifact defines Judge verdict enums
  - the user brief explicitly warns against degrading richer concept semantics into generic allow/deny abstractions
- Verdict: **unproven**
- Why it matters operationally:
  - Registry entries, schemas, WAL records, and future adapters would hard-freeze the wrong semantic contract and make later correction expensive.

### D3. Mode vocabulary is invented, then treated as if Phase-1-ready

- Claim in current draft:
  - `mode: Literal["off", "shadow"]`
  - future `advisory` and `authoritative` modes are declared and rejected in Phase 1
  - a `JudgeVerdict.authority_mode` enum is also invented
- Evidence checked:
  - current repo only proves mode surfaces for other systems:
    - sidecar: `disable | shadow | enable`
    - llm_orchestration: `baseline | hybrid_advisory | llm_primary`
  - no repo artifact proves the Judge mode vocabulary
- Verdict: **unproven**
- Why it matters operationally:
  - It silently shrinks or substitutes the concept's official mode surface instead of preserving the full typed surface and separately defining a Phase-1-admitted subset.

### D4. `policy_cortex` is presented as the natural placement without proof

- Claim in current draft:
  - `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_CONTRACT_PACKAGE_PLAN.md:108-109,498-505` recommends a new top-level `domains.policy_cortex` path
- Evidence checked:
  - `DomainsConfig` proves that new domains are possible, not that they are correct
  - sidecar precedent is embedded under `execution_position`
  - alpha-search precedent is a separate standalone shadow substrate with its own config file and startup registration
  - no concept artifact is available to prove or reject `alpha_search` as the intended substrate
- Verdict: **unproven**
- Why it matters operationally:
  - This is the largest architecture fork in the whole package. Locking the wrong placement would distort config ownership, docs, registry shape, and later runtime wiring.

### D5. Startup diagnostic emission is claimed without a proven owner path

- Claim in current draft:
  - Phase 1 should register and emit `CORTEX_MODE_ACTIVE_V1`
  - `startup_diagnostics.emit_mode_active: true` is proposed
  - `apps/reference/main.py` is simultaneously listed as "do not touch in Phase 1"
- Evidence checked:
  - sidecar emission works only because `ExecPosFSM` explicitly creates the sidecar and calls `announce_mode_active()`
  - there is no existing Judge owner, constructor, or startup hook in repo
  - disable-mode sidecar does not instantiate and therefore does not emit a mode-active event
- Verdict: **unproven and internally inconsistent**
- Why it matters operationally:
  - It promises observable Phase-1 runtime behavior while also forbidding the owner wiring needed to make that behavior real.

### D6. The draft invents detailed field-level contracts that the repo does not authorize

- Claim in current draft:
  - dozens of exact fields are specified for `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, and `JudgeVerdict`
  - runtime-oriented placeholders such as prompt metadata, cost fields, and aggregation semantics are embedded into the Phase-1 blueprint
- Evidence checked:
  - none of those contracts exist in repo
  - the concept file that would authorize those fields is absent
  - the draft itself notes that envelope-level tracing already lives in `Message`, then duplicates `rid` and `idempotent_key` inside the proposed verdict payload
- Verdict: **unproven**
- Why it matters operationally:
  - Premature field invention is how semantic drift enters schemas, tests, and later WAL/replay surfaces.

### D7. The expert-taxonomy diagnosis is overstated

- Claim in current draft:
  - "`The "expert" taxonomy is not defined`"
  - "`the concept does not enumerate which experts exist`"
- Evidence checked:
  - the concept is missing, so the claim about what the concept does or does not enumerate is not provable
  - the repo already contains candidate expert-like producer classes and surfaces:
    - alpha-search providers
    - neocortex shadow outputs
    - regime/risk/feature domains
  - what is actually missing is a formal Judge-owned expert registry and an approved initial subset
- Verdict: **unproven at concept level; overstated at repo level**
- Why it matters operationally:
  - It frames the problem as total absence instead of a narrower registry/admission decision, which invites unnecessary redesign.

### D8. The draft is too implementation-eager for the amount of authority actually available

- Claim in current draft:
  - Phase 1 is marked `GO-WITH-CONSTRAINTS`
  - registry edits, config edits, new domain package creation, and new schemas are recommended immediately after the concept is committed or waived
- Evidence checked:
  - the core semantic and placement questions are still open
  - the concept authority gap is not just a packaging issue; it affects enums, verb names, config location, and startup claims
- Verdict: **disproven as implementation-ready**
- Why it matters operationally:
  - It would freeze wrong nouns and wrong boundaries into the repo before the governing vocabulary is even recoverable.

## 9. Severity assessment

| Defect | Severity | Reason |
|---|---|---|
| D1. Missing concept but claimed authority | Critical | Invalid authority model for the whole package |
| D2. Generic verdict substitution | Critical | Freezes wrong semantics into contracts and events |
| D3. Invented mode vocabulary | Critical | Can silently shrink or replace the concept surface |
| D4. Premature `policy_cortex` placement | Critical | Chooses the main architecture fork without proof |
| D5. Unproven startup diagnostic emission | High | Creates a runtime promise without a proven owner path |
| D6. Detailed contract invention | High | Hardens semantic drift into schemas/tests |
| D7. Overstated expert-taxonomy absence | Medium | Misframes a bounded registry problem as total absence |
| D8. Implementation-readiness overstatement | High | Encourages premature registry/config freeze |

## 10. Correction decisions

1. Treat concept authority as missing from the repo until the named artifact is committed or supplied verbatim in a governing appendix.
2. Remove all invented Judge verdict and mode enums from the canonical Phase-1 plan.
3. Keep entry semantics and lifecycle semantics distinct; do not let a generic normalization layer become the primary contract.
4. Reframe `policy_cortex` as only one placement option, not the recommended default.
5. Keep the substrate/placement fork explicit and compare:
   - alpha-search-aligned rollout,
   - new dedicated domain,
   - embedding under an existing owner.
6. Remove any claim that Phase 1 emits startup diagnostics unless the exact owner wiring is proven in the chosen branch.
7. Reframe the expert-taxonomy issue as:
   - candidate expert classes exist,
   - approved Phase-1 subset is unresolved,
   - formal Judge registry is absent.
8. Block registry/schema/config freezes until exact concept vocabulary and placement are closed.

## 11. What remains genuinely unresolved

- Primary unresolved design fork:
  - whether the future chamber package is aligned to `alpha_search` or placed under an existing decision owner such as `decision_making`
- Authority gaps:
  - exact official entry verdict vocabulary
  - exact official lifecycle verdict vocabulary
  - exact official operational modes
  - whether `alpha_search` is explicitly frozen by the concept as the chamber substrate
- Design details that should stay open until the authority gap is closed:
  - initial expert allowlist
  - exact verb family names
  - whether startup diagnostics are part of the contract package
  - whether a new dedicated top-level domain should be reopened at all; the corrected plan rejects it as a default path unless new authority explicitly authorizes it

## 12. Recommendation on whether the corrected plan is implementation-ready

The corrected plan is ready as a control document for later implementation planning.

It is **not** ready as a code implementation brief until all three gates below are closed:

1. the concept artifact is present in the repo, or its exact vocabulary is supplied verbatim in a governing appendix,
2. the placement/substrate fork is explicitly decided,
3. the plan states which startup/runtime claims are in scope and which remain deferred.
