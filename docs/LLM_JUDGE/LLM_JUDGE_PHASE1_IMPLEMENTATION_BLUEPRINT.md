# LLM Judge Phase 1 — Implementation Blueprint

**Date**: 2026-04-13
**Artifact type**: Final Phase 1 implementation blueprint
**Artifact status**: Implementation-ready planning SSOT for Phase 1 coding work
**Code changes**: None (planning document only)

---

## 1. Executive Verdict

**GO**

All three gates identified by the corrected plan are now closed:

1. **Authority gate**: The supplied concept artifact defines exact entry verdict vocabulary, lifecycle verdict vocabulary, operational mode vocabulary, and alpha_search substrate direction. This document adopts those semantics verbatim.
2. **Placement gate**: alpha_search-aligned placement is frozen for Phase 1. No hard technical blocker was found; the repo proves alpha_search as a standalone shadow substrate with its own config, loader, and plugin pattern.
3. **Startup/runtime gate**: Phase 1 includes no startup diagnostics, no runtime wiring, no event emission. All runtime behavior is explicitly deferred to Phase 2.

Phase 1 implements typed contracts, JSON schemas, verb registry entries, config models, and validation tests. Nothing more.

---

## 2. Authority Model

### 2.1 Supplied Governing Authority

The concept artifact `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` is supplied as task-level authority. It is not committed to the repository. This document treats it as the semantic SSOT for:

- Entry verdict vocabulary
- Lifecycle verdict vocabulary
- Operational mode vocabulary
- Ownership boundaries (LLM = policy judge only)
- Substrate direction (alpha_search-aligned)
- Concept laws (additive-only, contract-first, replayability, shadow-first, no direct LLM-to-exchange path, no silent legacy math revival, no mixed mega-contracts, typed/bounded/timestamped evidence)

### 2.2 Repo-Resident Authority

The repository proves:

- alpha_search exists as a standalone shadow substrate with its own config, loader, and plugin registration (`main.py:922-940`)
- The verb registry, schema registry, and Message protocol are actively enforced at runtime
- Contract-first, additive-only, shadow-first rollout patterns are established by VFOUNDATION and ROI-Gated roadmaps
- No Judge-related contracts, schemas, verbs, or config currently exist anywhere in the repo
- The Message envelope already carries `rid`, `span_id`, `parent_span_id`, `ts`, `ttl_ms`, `idempotent_key`, `why`, `mode`, `mode_contract`, `corr_id`

### 2.3 Adoption Gap

| Item | Supplied Authority Status | Repo Status |
|---|---|---|
| Concept document | Exists as supplied task authority | Not committed |
| Entry verdict vocabulary | Defined in concept | Not in repo |
| Lifecycle verdict vocabulary | Defined in concept | Not in repo |
| Operational modes | Defined in concept | Not in repo |
| alpha_search substrate direction | Stated in concept | alpha_search exists but has no Judge concepts |
| ExpertOutput / ChamberAggregate / JudgeEvidenceEnvelope / JudgeVerdict | Named in concept | Not in repo |

### 2.4 What Is Semantically Frozen Despite Not Being Committed

The following semantics are frozen for this blueprint by supplied authority. They are not guesses, inferences, or repo extrapolations:

- Entry verdicts: `OPEN_LONG`, `OPEN_SHORT`, `NO_ENTRY`, `SUPPRESS`, `UNKNOWN`
- Lifecycle verdicts: `HOLD`, `PROTECT`, `EXIT`, `SUPPRESS`, `UNKNOWN`
- Operational modes: `off`, `shadow`, `hybrid_advisory`, `guarded_entry_authority`, `guarded_lifecycle_authority`
- LLM is policy judge only, never execution truth owner
- Evidence envelopes must be typed, bounded, timestamped, serializable, replayable

---

## 3. Phase 1 Final Scope

### 3.1 In Scope

1. **Pydantic contract models** for `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, `JudgeVerdict`, plus supporting sub-models
2. **JSON schemas** (draft-07) for verdict mapping events, registered in verb registry
3. **Verb registry entries** for Phase 1 verdict events (experimental, schema-backed)
4. **Config models** (Pydantic, `extra='forbid'`) for Judge operational mode surface
5. **Config YAML** additions to `config/alpha_search.yaml`
6. **Validation tests** covering contracts, schemas, config, registry, serialization
7. **domain_dict.json** (new) for formalizing alpha_search's expanded boundary
8. **Concept document** committed as repo-resident authority

### 3.2 Out of Scope (explicitly deferred)

- No startup wiring in `main.py` beyond what alpha_search already has
- No startup diagnostic events (no mode-active emission)
- No runtime evaluation logic (no chamber aggregation, no LLM calls)
- No expert implementations (no TA expert, no microstructure expert)
- No StrategyGateway gate insertion
- No execution_position changes
- No shadow_telemetry integration
- No neocortex integration
- No decision_making handler changes
- No live event emission from Phase 1 contracts
- No advisory or authority mode runtime behavior
- No direct-to-exchange paths
- No position lifecycle verdict enforcement

---

## 4. FACTS

**F1.** alpha_search is loaded at `main.py:922-940` as a standalone plugin, not through `DomainsConfig` or `domains.yaml`. Config lives in `config/alpha_search.yaml`, loaded by its own `load_alpha_search_config()`.

**F2.** `AlphaSearchConfig` (alpha_search/config_models.py:311) uses `extra="forbid"` and has fields: `enabled`, `shadow_mode`, `triggers`, `cache`, `providers: Dict[str, ProviderConfig]`, `virtual_trader`, `objective_feedback`, `legacy`.

**F3.** `ProviderConfig` supports `adapter` (AuroraAlphaAdapter) or `ensemble` (TAEnsembleConfig), validated as mutually exclusive by `validate_provider_type`.

**F4.** alpha_search emits `EVT:ALPHA_SCORE_CALCULATED` (1 verb, active, has schema). It consumes `EVT:FEATURES_CALCULATED`, `EVT:TA_FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY`, `EVT:TRADE_EXECUTED`, `EVT:OBJECTIVE_REALIZED_V1`.

**F5.** alpha_search has no `domain_dict.json`. It has 30+ test files across two locations. It has docs including `ATLAS.md`, `ARCHITECTURE.md`, `EVENT_CONTRACTS.md`.

**F6.** alpha_search has zero hits for `judge`, `verdict`, `chamber`, `expert` in any file.

**F7.** The verb registry uses format: `op`, `verb`, `owner`, `status`, `schema` (path or null), `since`, optional `co_emitters`, `note`, `deprecated_since`.

**F8.** Schema registry compiles `Draft7Validator` for each verb with a non-null schema path. Validation runs synchronously on every `FSMCore.emit()`.

**F9.** Message envelope fields: `rid`, `span_id`, `parent_span_id`, `ts`, `ttl_ms`, `idempotent_key`, `why`, `mode`, `mode_contract`, `corr_id`, `pld`. These are available on every emitted event. Payload schemas should NOT duplicate them.

**F10.** decision_making gate chain in `strategy_gateway.py:215-863` runs gates Pre-0 through 6, then calls `_propose_trade_intent()` → `apply_safety_gates()` → `IntentBuilder.build_and_emit()` → `EVT:TRADE_INTENT_PROPOSED`. A Phase 2 Judge gate would insert in this chain.

**F11.** The sidecar rollout precedent places sidecar config inside the owner domain's config (`execution_position.position_policy_sidecar`), not as a new top-level domain.

**F12.** alpha_search startup registration is fail-open: if init fails, a warning is logged and the system continues (`main.py:936-940`).

---

## 5. INFERENCES

**I1.** Phase 1 contracts placed under alpha_search can be loaded, validated, and tested without touching `main.py`, `config_loader.py`, or any existing domain code. alpha_search's own `load_alpha_search_config()` handles loading. The existing fail-open startup registration means adding new config fields (with defaults) will not break startup.

**I2.** Phase 1 verdict events will be registered in the verb registry with schemas, but no runtime code will emit them in Phase 1. The schemas will be compiled and cached by `VerbSchemaRegistry` at startup. This is a safe, proven pattern: many existing verbs have schemas but are only emitted conditionally (e.g., sidecar verbs when mode=disable).

**I3.** The `providers: Dict[str, ProviderConfig]` architecture in alpha_search is extensible. Phase 2 could add a `judge` provider type. Phase 1 does not add any provider — it only adds the contract shapes and config models that a future judge provider would use.

**I4.** Placing judge contracts under alpha_search follows the concept's alpha_search substrate direction and avoids creating a new top-level domain. It reuses the strongest existing shadow-substrate precedent in the repo.

**I5.** The five operational modes map to a natural Phase rollout: `off` (no-op), `shadow` (Phase 2-3 evaluation), `hybrid_advisory` (Phase 4+), `guarded_entry_authority` (Phase 5+), `guarded_lifecycle_authority` (Phase 6+). Phase 1 config must define the full type surface but only admit `off` at runtime.

---

## 6. ASSUMPTIONS

**A1.** The supplied concept's alpha_search substrate direction means: Judge contract models and Judge config live alongside alpha_search source, in alpha_search's config file, and use alpha_search's loading pattern. It does NOT mean: Judge must be a scoring provider inside `AlphaSearchBacktestPlugin`.

**A2.** Phase 1 contracts are not consumed by any runtime code. They exist as typed shapes that Phase 2 runtime will instantiate, validate, and emit as event payloads.

**A3.** Committing the concept document is a prerequisite for this blueprint's implementation. The blueprint treats concept semantics as frozen, but the document must be repo-resident before code is written.

---

## 7. UNKNOWNS

| Unknown | Blocking? | Status |
|---|---|---|
| Exact expert_id values for the first expert subset | No | Phase 2 decision. Phase 1 uses `str` for expert_id. |
| Whether entry and lifecycle share one evidence envelope or need separate families | No | Phase 1 defines one `JudgeEvidenceEnvelope` with a `verdict_scope` discriminator. Phase 2 may split if needed. |
| Aggregation algorithm for chamber | No | Phase 1 defines the aggregate shape, not the algorithm. |
| LLM prompt/model contract details | No | Phase 1 includes `prompt_template_id` and `model_version` as Optional string fields in provenance. |
| Phase 2 Judge gate insertion point in StrategyGateway | No | Phase 2 design decision. Candidate: between Gate 5 (TTL) and Gate 6 (Warmup). |

No blocking semantic unknowns remain under supplied authority. Repo adoption of that authority (committing the concept document) remains a prerequisite before coding begins.

---

## 8. Frozen Semantic Surface

### 8.1 Entry Verdict Vocabulary

```python
EntryVerdict = Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]
```

- `OPEN_LONG`: Judge recommends long entry
- `OPEN_SHORT`: Judge recommends short entry
- `NO_ENTRY`: Judge evaluated and found no actionable signal
- `SUPPRESS`: Judge actively suppresses a proposed entry
- `UNKNOWN`: Judge could not form a verdict (stale evidence, quorum failure, LLM timeout)

Source: supplied concept authority.

### 8.2 Lifecycle Verdict Vocabulary

```python
LifecycleVerdict = Literal["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"]
```

- `HOLD`: Judge recommends holding current position
- `PROTECT`: Judge recommends tightening protection (SL adjustment)
- `EXIT`: Judge recommends closing position
- `SUPPRESS`: Judge suppresses a proposed lifecycle action
- `UNKNOWN`: Judge could not form a verdict

Source: supplied concept authority.

### 8.3 Operational Modes

```python
CortexMode = Literal["off", "shadow", "hybrid_advisory", "guarded_entry_authority", "guarded_lifecycle_authority"]
```

- `off`: No evaluation. Contracts exist but no runtime behavior.
- `shadow`: Evaluate and log verdicts. Never applied to pipeline. (Phase 2-3)
- `hybrid_advisory`: Verdicts emitted as advisory signals. Decision_making may consult but is not bound. (Phase 4+)
- `guarded_entry_authority`: Entry verdicts can suppress signals through StrategyGateway gate. Guarded by symbol/strategy allowlists. (Phase 5+)
- `guarded_lifecycle_authority`: Lifecycle verdicts can recommend PROTECT/EXIT. Guarded. (Phase 6+)

**Phase 1 runtime admission**: ONLY `off`. All other modes are defined in the type surface but rejected at validation time in Phase 1 config. Phase 2 implementation adds `shadow` admission.

Source: supplied concept authority.

### 8.4 Ownership Constraints

- LLM is policy judge only, never execution truth owner
- No direct LLM-to-exchange path from Judge contracts
- Judge verdicts are advisory or guarded-gate; they never directly produce `CMD:OPEN`, `CMD:CLOSE`, or any execution_position command
- execution_position ownership is not affected by Phase 1
- decision_making ownership of `EVT:TRADE_INTENT_PROPOSED` is not affected by Phase 1

Source: supplied concept authority + repo governance laws.

### 8.5 Substrate Statement

Phase 1 contracts and config live under the alpha_search domain directory, loaded by alpha_search's config path. This follows the concept's alpha_search substrate direction.

Source: supplied concept authority.

---

## 9. Phase 1 Placement Decision

### 9.1 Chosen Placement: alpha_search-aligned

Phase 1 contracts live at `apps/reference/domains/alpha_search/judge/`. Config additions go in `config/alpha_search.yaml`. Verb registry entries use `owner: alpha_search`.

### 9.2 Why alpha_search

1. **Concept direction**: Supplied concept authority states alpha_search substrate alignment.
2. **Proven pattern**: alpha_search is an established standalone shadow substrate with its own config, loader, and plugin. No `DomainsConfig` changes needed. No `config_loader.py` changes needed. No `main.py` startup changes needed for Phase 1.
3. **Additive-only**: Adding a `judge/` subdirectory and config block to alpha_search is purely additive. Existing alpha_search functionality is unchanged.
4. **Minimal blast radius**: Modifies alpha_search config_models.py (additive field) and config/alpha_search.yaml (additive block). Touches no core infrastructure.
5. **No new domain overhead**: No new `DomainsConfig` entry, no new domain_builder path, no new startup wiring.

### 9.3 Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| New `policy_cortex` top-level domain | Not authorized by concept. Requires new `DomainsConfig` field, new domain_builder path, and new startup wiring — all disproportionate for a contracts-only Phase 1. The corrected plan explicitly rejects this as default. |
| Embedded under `decision_making` | DM is the owner of intent proposal. Embedding judge contracts inside DM would conflate the evaluator with the evaluated. The concept explicitly separates these concerns. DM config is already the largest in the system. |
| Embedded under `execution_position` | Governance roadmaps explicitly warn against policy layers collapsing into execution truth. Judge is policy, not execution. |
| Standalone config file (`config/judge.yaml`) detached from any domain | Creates an orphan config with no loader, no domain, and no proven integration path. More risk than benefit. |

---

## 10. Phase 1 Contract Package

### 10.1 `ExpertOutput`

| Attribute | Value |
|---|---|
| **Purpose** | Typed output from one expert perspective on a trading decision |
| **Owner** | alpha_search (judge sub-package) |
| **Canonical location** | `apps/reference/domains/alpha_search/judge/contracts.py` |
| **Schema** | `apps/reference/domains/alpha_search/judge/schemas/expert_output_v1.json` |
| **SSOT** | Pydantic-first; JSON schema kept in sync manually |

**Required fields**:

| Field | Type | Constraint | Source |
|---|---|---|---|
| `expert_id` | `str` | non-empty | Identifies expert module |
| `expert_version` | `str` | semver pattern | Tracks expert code version |
| `symbol` | `str` | non-empty | Trading pair |
| `tf_sec` | `int` | > 0 | Timeframe |
| `ts_ms` | `int` | > 0 | When expert produced output |
| `entry_verdict` | `Optional[EntryVerdict]` | None if not evaluating entry | Concept vocabulary |
| `lifecycle_verdict` | `Optional[LifecycleVerdict]` | None if not evaluating lifecycle | Concept vocabulary |
| `confidence` | `float` | [0.0, 1.0] | Expert's confidence |
| `signal_direction` | `Optional[Literal["LONG", "SHORT", "NEUTRAL"]]` | | Expert's directional view |
| `reasoning` | `list[str]` | minItems 1 | Structured justification |
| `schema_version` | `Literal["1"]` | | Contract versioning |

**Deferred fields** (Phase 2+):
- `latent_features: Optional[dict]` — expert-specific opaque payload
- `cost_estimate_ms: Optional[int]` — computation time
- `evidence_ref: Optional[str]` — pointer to external evidence

**Invariants**:
- Exactly one of `entry_verdict` or `lifecycle_verdict` must be non-None (XOR)
- `confidence` in [0.0, 1.0]
- `reasoning` has at least 1 item
- If `entry_verdict` is `SUPPRESS`, `reasoning` must include a suppression reason

**Fail-closed**: If an expert fails, the consumer must treat it as `UNKNOWN` with confidence 0.0.

**Replay**: (`expert_id`, `symbol`, `tf_sec`, `ts_ms`) uniquely identifies output. `schema_version` enables forward-compatible deserialization.

---

### 10.2 `ChamberAggregate`

| Attribute | Value |
|---|---|
| **Purpose** | Aggregation of all expert outputs for one evaluation cycle |
| **Owner** | alpha_search (judge sub-package) |
| **Canonical location** | `apps/reference/domains/alpha_search/judge/contracts.py` |
| **Schema** | `apps/reference/domains/alpha_search/judge/schemas/chamber_aggregate_v1.json` |

**Required fields**:

| Field | Type | Constraint |
|---|---|---|
| `chamber_id` | `str` | UUID — unique per evaluation cycle |
| `symbol` | `str` | non-empty |
| `tf_sec` | `int` | > 0 |
| `ts_ms` | `int` | > 0, when aggregation completed |
| `verdict_scope` | `Literal["ENTRY", "LIFECYCLE"]` | Which verdict family |
| `expert_outputs` | `list[ExpertOutput]` | May be empty (all abstained) |
| `expert_count` | `int` | >= 0, experts solicited |
| `responding_count` | `int` | >= 0, experts that responded |
| `abstaining_count` | `int` | >= 0, timed out / failed |
| `consensus_direction` | `Optional[Literal["LONG", "SHORT", "NEUTRAL", "SPLIT"]]` | |
| `consensus_strength` | `float` | [0.0, 1.0] |
| `admissibility` | `Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]` | |
| `schema_version` | `Literal["1"]` | |

**Deferred fields**: `weights`, `aggregation_method`, `dissent_summary`.

**Invariants**:
- `responding_count + abstaining_count <= expert_count`
- `consensus_strength` in [0.0, 1.0]
- All `expert_outputs` entries must have matching `verdict_scope` (ENTRY experts in ENTRY chamber, LIFECYCLE experts in LIFECYCLE chamber)

**Fail-closed**: Zero responding experts → `admissibility: QUORUM_INSUFFICIENT`. Inconsistent counts → `admissibility: INADMISSIBLE`.

---

### 10.3 `JudgeEvidenceEnvelope`

| Attribute | Value |
|---|---|
| **Purpose** | Typed, bounded, timestamped evidence package for judge evaluation. Separates evidence from verdict. |
| **Owner** | alpha_search (judge sub-package) |
| **Canonical location** | `apps/reference/domains/alpha_search/judge/contracts.py` |
| **Schema** | `apps/reference/domains/alpha_search/judge/schemas/judge_evidence_envelope_v1.json` |

**Required fields**:

| Field | Type | Constraint |
|---|---|---|
| `envelope_id` | `str` | UUID |
| `symbol` | `str` | non-empty |
| `tf_sec` | `int` | > 0 |
| `ts_ms` | `int` | > 0, when envelope assembled |
| `verdict_scope` | `Literal["ENTRY", "LIFECYCLE"]` | |
| `chamber_aggregate` | `ChamberAggregate` | nested |
| `strategy_id` | `str` | non-empty |
| `regime` | `Optional[str]` | current regime label |
| `regime_confidence` | `Optional[float]` | [0.0, 1.0] |
| `features_ref` | `Optional[str]` | pointer to features payload (rid or hash) — NOT embedded |
| `position_context` | `Optional[PositionContextSnapshot]` | required if verdict_scope == LIFECYCLE |
| `freshness_deadline_ms` | `int` | > 0, max age before stale |
| `provenance` | `EnvelopeProvenance` | nested traceability |
| `schema_version` | `Literal["1"]` | |

**Sub-types** (in same contracts.py):

```
PositionContextSnapshot:
  has_position: bool
  side: Optional[Literal["LONG", "SHORT"]]
  unrealized_pnl_pct: Optional[float]
  hold_duration_sec: Optional[int]
  bracket_state: Optional[str]  # "ACTIVE", "PENDING", "NONE"

EnvelopeProvenance:
  cortex_version: str
  prompt_template_id: Optional[str]  # Phase 2+
  model_version: Optional[str]        # Phase 2+
  assembly_source: str                # e.g. "alpha_search.judge.assembler"
```

**Design note on non-duplication**: The envelope does NOT duplicate `rid`, `span_id`, `ts`, `why`, `idempotent_key`, or `mode` from the Message envelope. Those fields are already present in every FSM event emission via `vfoundation.core.protocol.Message`. The payload schema only contains domain-specific fields that are not in the transport envelope.

**Invariants**:
- If `verdict_scope == LIFECYCLE`, `position_context` must not be None
- `freshness_deadline_ms > 0`
- `chamber_aggregate.verdict_scope` must match `verdict_scope`
- `features_ref` must not embed raw feature data (bounded-size constraint)

**Fail-closed**: Stale envelope (age > `freshness_deadline_ms`) → judge must produce `UNKNOWN` verdict.

**Replay**: `envelope_id` is the primary replay key. `provenance.cortex_version` tracks code version. `features_ref` allows joining to source features without embedding.

---

### 10.4 `JudgeVerdict`

| Attribute | Value |
|---|---|
| **Purpose** | Final judge policy verdict for a specific evaluation |
| **Owner** | alpha_search (judge sub-package) |
| **Canonical location** | `apps/reference/domains/alpha_search/judge/contracts.py` |
| **Schema** | `apps/reference/domains/alpha_search/judge/schemas/judge_verdict_v1.json` |

**Required fields**:

| Field | Type | Constraint |
|---|---|---|
| `verdict_id` | `str` | UUID |
| `envelope_id` | `str` | links to JudgeEvidenceEnvelope |
| `chamber_id` | `str` | links to ChamberAggregate |
| `symbol` | `str` | non-empty |
| `tf_sec` | `int` | > 0 |
| `ts_ms` | `int` | > 0, when verdict formed |
| `verdict_scope` | `Literal["ENTRY", "LIFECYCLE"]` | |
| `entry_verdict` | `Optional[EntryVerdict]` | required if verdict_scope == ENTRY |
| `lifecycle_verdict` | `Optional[LifecycleVerdict]` | required if verdict_scope == LIFECYCLE |
| `suppression_reason` | `Optional[str]` | required if verdict is SUPPRESS |
| `suppression_code` | `Optional[str]` | structured code |
| `confidence` | `float` | [0.0, 1.0] |
| `reasoning` | `list[str]` | minItems 1 |
| `dissent_noted` | `bool` | whether any expert disagreed |
| `authority_mode` | `CortexMode` | mode at time of verdict |
| `applied` | `bool` | whether verdict was applied |
| `strategy_id` | `str` | non-empty |
| `schema_version` | `Literal["1"]` | |

**Invariants**:
- If `verdict_scope == ENTRY`, `entry_verdict` must be non-None, `lifecycle_verdict` must be None
- If `verdict_scope == LIFECYCLE`, `lifecycle_verdict` must be non-None, `entry_verdict` must be None
- If verdict is `SUPPRESS`, `suppression_reason` must be non-empty
- If `authority_mode == "off"`, `applied` must be False
- If `authority_mode == "shadow"`, `applied` must be False
- `confidence` in [0.0, 1.0]
- `reasoning` has at least 1 item
- `ts_ms >= envelope.ts_ms` (verdict is after evidence)

**Fail-closed**: Judge failure → emit verdict with entry_verdict=`UNKNOWN` or lifecycle_verdict=`UNKNOWN`, confidence=0.0, applied=False.

**Replay**: `verdict_id` → `envelope_id` → `chamber_id` → `expert_outputs` provides full replay chain. `authority_mode` + `applied` distinguish shadow from live.

---

## 11. Verdict Mapping Package

### 11.1 Canonical Mapping Principles

1. Entry verdicts and lifecycle verdicts are distinct contract families. They are never collapsed into a shared generic enum.
2. If downstream consumers need coarse buckets, a secondary translation layer is acceptable, documented as such, and never replaces the canonical vocabulary.
3. Verbs use the `JUDGE_` prefix (not `CORTEX_`) to match the concept naming. Owner is `alpha_search`.
4. All Phase 1 verbs are registered as `experimental` with `schema` paths.
5. No Phase 1 verb will be emitted at runtime. Registration ensures schema compilation and validation.

### 11.2 Candidate Events

| Event | Op | Verb | Owner | Status | Schema | Phase |
|---|---|---|---|---|---|---|
| `EVT:JUDGE_ENTRY_VERDICT_V1` | EVT | `JUDGE_ENTRY_VERDICT_V1` | alpha_search | experimental | `apps/reference/domains/alpha_search/judge/schemas/judge_verdict_v1.json` | 1 (register) |
| `EVT:JUDGE_LIFECYCLE_VERDICT_V1` | EVT | `JUDGE_LIFECYCLE_VERDICT_V1` | alpha_search | experimental | `apps/reference/domains/alpha_search/judge/schemas/judge_verdict_v1.json` | 1 (register) |
| `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1` | EVT | `JUDGE_EVIDENCE_ASSEMBLED_V1` | alpha_search | experimental | `apps/reference/domains/alpha_search/judge/schemas/judge_evidence_envelope_v1.json` | 1 (register) |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` | EVT | `JUDGE_CHAMBER_AGGREGATED_V1` | alpha_search | experimental | `apps/reference/domains/alpha_search/judge/schemas/chamber_aggregate_v1.json` | 1 (register) |

### 11.3 Frozen Now vs Deferred

| Item | Frozen in Phase 1 | Deferred |
|---|---|---|
| 4 verb entries above | YES | — |
| 4 JSON schemas above | YES | — |
| Per-expert event (JUDGE_EXPERT_PRODUCED) | — | Phase 2 (too noisy, register when runtime exists) |
| Verdict-applied event (JUDGE_VERDICT_APPLIED) | — | Phase 3+ (only meaningful when authority modes exist) |
| Startup mode event (JUDGE_MODE_ACTIVE) | — | Phase 2 (requires runtime wiring with proven owner path) |

---

## 12. Config Package

### 12.1 Canonical Config Path

`config/alpha_search.yaml` — extended with a `judge:` top-level key.

### 12.2 Full Typed Mode Surface

Added to `apps/reference/domains/alpha_search/judge/config_models.py`:

```python
CortexMode = Literal["off", "shadow", "hybrid_advisory",
                      "guarded_entry_authority", "guarded_lifecycle_authority"]

class JudgeCortexConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    enabled: bool = False
    mode: CortexMode = "off"

    class _ModeValidator:
        # Phase 1 admits only "off"
        # Phase 2 adds "shadow"
        # Later phases add remaining modes
```

### 12.3 Phase 1 Admitted Runtime Subset

Phase 1 Pydantic validator rejects any mode other than `off` with a `ValueError`:

```
"Judge mode '{mode}' is not admitted in the current phase. Only 'off' is allowed."
```

This preserves the full canonical type surface while restricting runtime admission. The full `CortexMode` Literal remains the type definition so that schemas and documentation reflect the complete vocabulary.

### 12.4 Config Registration

The `JudgeCortexConfig` is added as an `Optional` field on `AlphaSearchConfig`:

```python
class AlphaSearchConfig(BaseModel):
    # ... existing fields ...
    judge: Optional[JudgeCortexConfig] = None  # None = judge not configured
```

This means:
- Existing `config/alpha_search.yaml` files without a `judge:` key continue to work (field is Optional with None default)
- Adding `judge: { enabled: false, mode: "off" }` to YAML activates the config surface
- `extra='forbid'` on `JudgeCortexConfig` ensures unknown fields are rejected

### 12.5 Validation Rules

- `mode == "off"` is the only admitted value in Phase 1
- `enabled: true` with `mode != "off"` is rejected
- `enabled: false` with `mode: "off"` is the expected Phase 1 state
- Unknown keys inside `judge:` are rejected by `extra='forbid'`

### 12.6 YAML Addition

```yaml
# In config/alpha_search.yaml
judge:
  enabled: false
  mode: "off"
```

---

## 13. File-by-File Implementation Blueprint

### Package A: Concept Authority (prerequisite)

| File | Action | Purpose |
|---|---|---|
| `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` | NEW | Commit concept as repo-resident authority |

### Package B: Judge Contract Sub-Package (new files)

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/alpha_search/judge/__init__.py` | NEW | Sub-package init |
| `apps/reference/domains/alpha_search/judge/contracts.py` | NEW | ExpertOutput, ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict, PositionContextSnapshot, EnvelopeProvenance, EntryVerdict, LifecycleVerdict, CortexMode type aliases |
| `apps/reference/domains/alpha_search/judge/config_models.py` | NEW | JudgeCortexConfig with mode validation |

### Package C: JSON Schemas (new files)

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/alpha_search/judge/schemas/expert_output_v1.json` | NEW | ExpertOutput JSON Schema (draft-07, additionalProperties: false) |
| `apps/reference/domains/alpha_search/judge/schemas/chamber_aggregate_v1.json` | NEW | ChamberAggregate JSON Schema (draft-07, additionalProperties: false) |
| `apps/reference/domains/alpha_search/judge/schemas/judge_evidence_envelope_v1.json` | NEW | JudgeEvidenceEnvelope JSON Schema (draft-07, additionalProperties: true — extensible evidence) |
| `apps/reference/domains/alpha_search/judge/schemas/judge_verdict_v1.json` | NEW | JudgeVerdict JSON Schema (draft-07, additionalProperties: false) |

### Package D: Registry and Config Integration (modify existing)

| File | Action | Change |
|---|---|---|
| `apps/reference/dictionaries/verb_registry_v1.yaml` | MODIFY | Add 4 new verb entries (JUDGE_ENTRY_VERDICT_V1, JUDGE_LIFECYCLE_VERDICT_V1, JUDGE_EVIDENCE_ASSEMBLED_V1, JUDGE_CHAMBER_AGGREGATED_V1) |
| `apps/reference/domains/alpha_search/config_models.py` | MODIFY | Import JudgeCortexConfig, add `judge: Optional[JudgeCortexConfig] = None` field to AlphaSearchConfig |
| `config/alpha_search.yaml` | MODIFY | Add `judge:` config block |
| `apps/reference/domains/alpha_search/domain_dict.json` | NEW | Formalize alpha_search domain boundaries (imports, exports including new judge verbs) |

### Package E: Tests (new files)

| File | Action | Purpose |
|---|---|---|
| `tests/domains/alpha_search/judge/__init__.py` | NEW | Test sub-package |
| `tests/domains/alpha_search/judge/test_contracts.py` | NEW | Pydantic contract validation |
| `tests/domains/alpha_search/judge/test_schemas.py` | NEW | JSON Schema validation (positive + negative) |
| `tests/domains/alpha_search/judge/test_config.py` | NEW | Config validation (mode admission, unknown fields) |
| `tests/domains/alpha_search/judge/test_registry.py` | NEW | Verb registry integration |
| `tests/domains/alpha_search/judge/test_serialization.py` | NEW | Round-trip serialization + replay chain |

### Files Explicitly Untouched in Phase 1

| File | Reason |
|---|---|
| `apps/reference/main.py` | No startup changes. alpha_search already loads. Config additions have defaults. |
| `apps/reference/config_loader.py` | No changes. alpha_search uses its own loader. |
| `apps/reference/config_models.py` (root) | No changes. No new DomainsConfig entry. |
| `config/aurora/domains.yaml` | No changes. Judge is not a standard domain. |
| `apps/reference/domains/decision_making/*` | No gate wiring in Phase 1. |
| `apps/reference/domains/execution_position/*` | No execution changes. |
| `apps/reference/domains/shadow_telemetry/*` | No integration. |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | No runtime changes. |
| `vfoundation/core/protocol.py` | No changes. |
| `vfoundation/core/schema_registry.py` | No changes (reads verb_registry automatically). |

---

## 14. Validation Blueprint

### 14.1 Test Matrix

| Category | File | Count | Description |
|---|---|---|---|
| **A. Contract Validation** | `test_contracts.py` | 20-25 | Valid construction of all 6 models. Required field enforcement. type validation. Enum validation (EntryVerdict, LifecycleVerdict, CortexMode). XOR invariant (entry_verdict vs lifecycle_verdict). Confidence range. Suppression-requires-reason. Count consistency on ChamberAggregate. Verdict_scope matching across envelope/chamber/verdict chain. |
| **B. Schema Validation** | `test_schemas.py` | 20-25 | Valid payload passes each schema. Unknown field rejected on strict schemas. Missing required field rejected. Invalid enum value rejected. Invalid type rejected. Conditional validation (SUPPRESS requires suppression_reason). Nested object validation (expert_outputs array, provenance object). additionalProperties behavior matches design (false for verdict, true for envelope). |
| **C. Config Validation** | `test_config.py` | 8-12 | Valid config loads. Unknown field rejected (extra='forbid'). Mode "shadow" rejected in Phase 1. Mode "hybrid_advisory" rejected. enabled=true with mode="off" valid. enabled=false with mode="off" valid. None default works (no judge key in YAML). After adding judge key, AlphaSearchConfig still validates. |
| **D. Registry Integration** | `test_registry.py` | 5-8 | All 4 verbs exist in loaded registry. Schema paths resolve. Validators compile (Draft7Validator). Owner is 'alpha_search'. Status is 'experimental'. |
| **E. Serialization / Replay** | `test_serialization.py` | 10-12 | JSON round-trip: Pydantic → model_dump() → json → model_validate(). Schema-validated dict: Pydantic model_dump() validates against JSON schema. Full chain reconstruction: verdict → envelope → chamber → experts. Idempotent key determinism. Provenance preserved through serialization. |
| **F. Negative / Boundary** | (across all files) | 10-15 | Empty expert_id. Negative confidence. Both entry_verdict and lifecycle_verdict set (should fail). Neither set (should fail). SUPPRESS without suppression_reason. LIFECYCLE scope without position_context. applied=True when authority_mode="shadow" (should fail). Invalid schema_version. |

**Total estimated tests**: 73-97

### 14.2 Proof Artifacts

| Artifact | Required |
|---|---|
| All tests pass (pytest output) | YES |
| Schema compilation proof (all 4 schemas compile via Draft7Validator) | YES (covered by test_registry.py) |
| Config integration proof (AlphaSearchConfig validates with judge block) | YES (covered by test_config.py) |
| Cross-validation proof (Pydantic output validates against JSON Schema) | YES (covered by test_serialization.py) |
| Full chain round-trip (expert → chamber → envelope → verdict) | YES (covered by test_serialization.py) |
| Existing alpha_search tests still pass | YES (regression gate) |
| REPORT: `docs/LLM_JUDGE/PHASE1_CONTRACT_PACKAGE_REPORT.md` | YES |

### 14.3 Acceptance Gates

1. Zero test failures in new test suite
2. Zero regressions in existing alpha_search test suite (30+ files)
3. Zero regressions in global test suite
4. Concept document committed to repo
5. All 4 JSON schemas compile in VerbSchemaRegistry
6. AlphaSearchConfig validates with and without `judge:` YAML block
7. REPORT produced with explicit verdict (DONE / DONE WITH RESERVATIONS / NOT DONE)

---

## 15. Risks

### R1. alpha_search config_models.py divergence

| Attribute | Value |
|---|---|
| **Cause** | Adding `judge` field to AlphaSearchConfig while alpha_search is actively developed |
| **Mechanism** | Concurrent PRs modify AlphaSearchConfig; merge conflicts on config_models.py |
| **Effect** | Merge resolution may silently break judge config integration |
| **Severity** | LOW — `Optional[JudgeCortexConfig] = None` is a one-line addition |
| **Mitigation** | Submit the config_models.py change as a minimal, isolated commit |

### R2. Schema drift between Pydantic and JSON Schema

| Attribute | Value |
|---|---|
| **Cause** | Dual-source contracts maintained separately |
| **Mechanism** | Developer updates Pydantic model, forgets JSON Schema |
| **Effect** | Runtime validation (JSON Schema in FSMCore.emit) diverges from Python-side validation |
| **Severity** | MEDIUM |
| **Mitigation** | test_serialization.py cross-validates: Pydantic model_dump() must pass JSON Schema. This is the detection mechanism. Phase 2 may add schema generation tooling. |

### R3. Concept recovery divergence

| Attribute | Value |
|---|---|
| **Cause** | Supplied concept authority may differ from what is eventually committed |
| **Mechanism** | Concept is committed with modified vocabulary |
| **Effect** | Phase 1 contracts must be updated to match committed version |
| **Severity** | LOW — Phase 1 is additive-only; updating enums in contracts.py is straightforward |
| **Mitigation** | The concept MUST be committed before Phase 1 coding begins. If vocabulary changes, contracts.py and schemas are updated in the same commit. |

### R4. alpha_search test pollution

| Attribute | Value |
|---|---|
| **Cause** | Judge tests share the alpha_search test namespace |
| **Mechanism** | Judge test fixtures or conftest.py interfere with existing alpha_search tests |
| **Effect** | False test failures |
| **Severity** | LOW — judge tests are in a separate `tests/domains/alpha_search/judge/` subdirectory |
| **Mitigation** | Judge tests use their own fixtures, no shared conftest.py modifications |

### R5. verb_registry_v1.yaml merge conflict

| Attribute | Value |
|---|---|
| **Cause** | Other work-in-progress may also add verbs |
| **Mechanism** | Concurrent PRs append verbs at different positions |
| **Effect** | YAML merge conflict |
| **Severity** | LOW — verb registry is append-only, conflicts are trivially resolved |
| **Mitigation** | Append new verbs at end of file |

---

## 16. Phase 1 Package Order

### Subpackage 1A: Authority Commit

**Contents**: Commit `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` to `docs/LLM_JUDGE/`.

**Entry gate**: Supplied concept text available.
**Exit gate**: Concept document committed and pushed.

### Subpackage 1B: Contracts + Schemas

**Contents**:
- Create `apps/reference/domains/alpha_search/judge/` directory
- `__init__.py`, `contracts.py` (all Pydantic models, type aliases), `config_models.py`
- 4 JSON schemas in `judge/schemas/`

**Entry gate**: 1A complete (concept committed).
**Exit gate**: All Pydantic models instantiate with valid data. All JSON schemas compile via `Draft7Validator`. Cross-validation (Pydantic → dict → schema) passes.

### Subpackage 1C: Registry + Config Integration

**Contents**:
- Add 4 verbs to `verb_registry_v1.yaml`
- Add `judge: Optional[JudgeCortexConfig] = None` to `AlphaSearchConfig` in alpha_search/config_models.py
- Add `judge:` block to `config/alpha_search.yaml`
- Create `domain_dict.json` for alpha_search

**Entry gate**: 1B complete.
**Exit gate**: `load_alpha_search_config()` succeeds with and without `judge:` block. `VerbSchemaRegistry` loads all 4 new verbs. No existing tests broken.

### Subpackage 1D: Test Suite

**Contents**:
- 6 test files in `tests/domains/alpha_search/judge/`
- Covering: contracts, schemas, config, registry, serialization, negative cases

**Entry gate**: 1C complete.
**Exit gate**: All tests pass. Test count >= 70. No regressions in existing alpha_search tests.

### Subpackage 1E: Report

**Contents**:
- `docs/LLM_JUDGE/PHASE1_CONTRACT_PACKAGE_REPORT.md`

**Entry gate**: 1D complete.
**Exit gate**: Report contains explicit verdict, test evidence, what is proven, what remains unproven.

---

## 17. Done Criteria

### Phase 1 Planning Done Criteria (this document)

- [x] One final document produced
- [x] Concept semantics preserved exactly
- [x] alpha_search-aligned placement frozen
- [x] Startup/runtime scope stated explicitly (deferred)
- [x] File-by-file implementation scope concrete
- [x] Test matrix concrete
- [x] Package order concrete

### Phase 1 Implementation Done Criteria (for later coding agent)

- [ ] Concept document committed to repo
- [ ] All Pydantic contracts compile and validate
- [ ] All 4 JSON schemas compile via Draft7Validator
- [ ] All 4 verb registry entries present and resolved
- [ ] AlphaSearchConfig validates with judge block
- [ ] AlphaSearchConfig validates without judge block (backwards compat)
- [ ] 70+ tests pass with zero failures
- [ ] Zero regressions in existing alpha_search tests
- [ ] Zero regressions in global test suite
- [ ] Cross-validation: Pydantic model_dump() passes JSON Schema for all 4 contracts
- [ ] Full chain round-trip test passes (expert → chamber → envelope → verdict)
- [ ] REPORT produced with verdict

---

## 18. Final Recommended Next Coding Task

**Task**: Implement Subpackage 1A, then Subpackage 1B (strict order).

**Step 1 — Subpackage 1A (authority gate)**: Commit the concept document to `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md`. This is a prerequisite; 1B cannot begin until the concept is repo-resident.

**Step 2 — Subpackage 1B (contracts)**: Create `apps/reference/domains/alpha_search/judge/` with `__init__.py`, `contracts.py` (ExpertOutput, ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict, PositionContextSnapshot, EnvelopeProvenance, EntryVerdict, LifecycleVerdict, CortexMode), `config_models.py` (JudgeCortexConfig), and 4 JSON schemas.

**Acceptance**: Concept document is committed (1A). All Pydantic models instantiate with valid data and reject invalid data. All JSON schemas compile via `Draft7Validator`. Cross-validation passes (1B).

**Hard constraint**: Do not modify `main.py`, `config_loader.py`, root `config_models.py`, or any existing domain code. Do not emit events. Do not wire startup hooks.
