# LLM Judge Bicameral Policy Cortex — Phase 1: Contract Package Plan

**Date**: 2026-04-13
**Author**: Automated Research Agent (deep-research planning mode)
**Branch**: Phenix_v2
**Status**: PLANNING ARTIFACT — No code changes
**Scope**: Phase 1 only — contract surface, config surface, verb registration

---

## 1. Executive Verdict

**GO-WITH-CONSTRAINTS**

Phase 1 contract package implementation is feasible. The repository has strong precedents for contract-first, shadow-first, additive-only rollout. The neocortex domain's shadow gate system, the position policy sidecar's config discipline, and the ROI-gated roadmap's contract laws provide direct templates. However, three constraints must be resolved before implementation begins:

1. **The concept document `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` does not exist in the repository.** The task mandate describes the concept in sufficient detail, but the absence of a frozen concept document means there is no SSOT for design decisions. The concept should be committed before Phase 1 implementation so that Phase 1 can reference it as authority.

2. **The "expert" taxonomy is not defined.** Phase 1 must define `ExpertOutput`, but the concept does not enumerate which experts exist. Phase 1 must either (a) define a minimal expert registry with at least 2-3 concrete expert_ids, or (b) define ExpertOutput as a shape contract where expert_id is a free string and the expert enumeration is deferred to Phase 2.

3. **Overlap with neocortex and alpha_search must be explicitly resolved.** Both domains already produce shadow advisory outputs. Phase 1 must state whether neocortex shadow intents and alpha_search scores are future expert inputs to the cortex, or remain entirely separate systems.

---

## 2. Scope of This Phase

### Phase 1 boundary (IN SCOPE)

- Typed Pydantic contracts: `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, `JudgeVerdict`
- JSON schemas for the above (registered in `verb_registry_v1.yaml`)
- Verdict mapping events registered in verb registry (shadow-only, experimental status)
- Typed YAML + Pydantic config surface for cortex mode (`off`, `shadow`, future modes declared but fail-closed)
- domain_dict.json for the new domain surface
- Contract validation tests, schema validation tests, registry tests

### Explicit non-goals (OUT OF SCOPE)

- No chamber runtime logic (expert scoring, aggregation algorithms)
- No LLM judge runtime calls (no API integration, prompt engineering, inference)
- No expert implementations (no TA expert, no microstructure expert, no regime expert)
- No TRADE_INTENT_PROPOSED interception gate wiring
- No execution_position FSM changes
- No direct-to-exchange paths
- No economic simulator or backtesting harness
- No advisory or live authority modes (shadow gate must block)
- No neocortex or alpha_search integration wiring
- No broad decision_making or execution_position refactors
- No Phase 2-6 runtime components

---

## 3. FACTS

Evidence directly observed in repository inspection.

### F1. The concept document does not exist
No file matching `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md`, `*bicameral*`, `*llm*judge*`, or `*cortex*concept*` exists in the repository. The `neocortex` domain exists but is a separate neural network system, not the bicameral policy cortex.

### F2. Neocortex domain provides the strongest shadow-gate precedent
`apps/reference/domains/neocortex/logic/gates/shadow.py` implements `ShadowGateEvaluator` with 10 gates, `ShadowGateResult` (gate_id, status pass/warn/fail, severity, blocking, evidence_anchor), and `ShadowReadinessReport` (overall_status ready/not_ready). Config uses `extra='forbid'`, `frozen=True`. Authority is hard-gated: `allow_advisory_influence: false`, `allow_live_authority: false` enforced at startup.

### F3. Verb registry has 91 entries with established conventions
`apps/reference/dictionaries/verb_registry_v1.yaml` uses format: `op` (EVT/CMD/DEC/UPD/ERR/ASK), `verb` (SCREAMING_SNAKE_CASE), `owner`, `status` (active/experimental/deprecated), `schema` (path or null), `since`, optional `co_emitters`.

### F4. Schema convention is JSON Schema draft-07 with strict `additionalProperties: false`
Core schemas (`trade_intent_v1`, `decision_blocked_v1`) use `additionalProperties: false`. Evolving schemas (sidecar, alpha_search) use `additionalProperties: true`. Decimals are string-encoded. Tracing fields (`ts_ms`, `rid`, `span_id`, `why`/`why_chain`) are standard.

### F5. Config models use `extra='forbid'` Pydantic with DomainsConfig as the domain registration surface
`AuroraConfig` → `DomainsConfig` maps each domain to a typed config. Adding a new domain requires: (a) Pydantic model class, (b) new field on `DomainsConfig`, (c) YAML block in `config/aurora/domains.yaml`. No changes needed in `config_loader.py` — domains.yaml is loaded wholesale.

### F6. Decision-making owns the strategy-to-intent pipeline
`CMD:PROCESS_STRATEGY` → Strategy Handlers → `EVT:STRATEGY_SIGNAL_PRODUCED` → StrategyGateway (7 gates) → SafetyGates → IntentBuilder → `EVT:TRADE_INTENT_PROPOSED`. An LLM Judge gate would logically insert in StrategyGateway between Gate 1.5 (Risk Skew) and Gate 2 (Flip). This is a Phase 2+ concern.

### F7. Four rejection event classes already exist
- `EVT:DECISION_BLOCKED` (pre-strategy, config/data)
- `EVT:STRATEGY_DECISION_BLOCKED` (strategy-side gates)
- `EVT:TRADE_INTENT_REJECTED` (intent-level, with NRR codes)
- `EVT:INTENT_DEFERRED` (retryable, currently never fires)

### F8. LLM external intent ingress already exists via shadow_telemetry
`shadow_telemetry` owns `EVT:LLM_INTENT_RECEIVED_V1`, `EVT:LLM_INTENT_ACCEPTED_V1`, `EVT:LLM_INTENT_REJECTED_V1`, `CMD:LLM_INTENT_SUBMIT_V1` (all experimental, no schemas). The LLM path **bypasses decision_making entirely** and routes through `CMD:EXTERNAL_OPEN_REQUEST_V1` directly to `execution_position`. This is the existing LLM-to-exchange path and is architecturally separate from the proposed Judge system.

### F9. LLM orchestration config exists in trading.yaml
`LLMOrchestrationConfig` with `mode: Literal["baseline", "hybrid_advisory", "llm_primary"]`, `symbols_llm`, `allowlist_symbols`, `intent_policy`. Currently set to `mode: hybrid_advisory` for 1000PEPEUSDT. This governs the external intent ingress, not the proposed Judge system.

### F10. alpha_search domain emits `EVT:ALPHA_SCORE_CALCULATED` in shadow mode
Multi-provider scoring (aurora adapter, TA ensemble) with virtual trader tracking. Config in separate `config/alpha_search.yaml`. Schema is loose (`additionalProperties: true`, only `symbol` required).

### F11. Position policy sidecar follows the most rigorous contract-first discipline
10-phase roadmap, Phase 1 is entirely config-first. 8 mandatory test categories. `PositionPolicySidecarConfig` embedded in `AuroraConfig.domains.execution_position.position_policy_sidecar` with mode `disable`/`shadow`/`enable`. 7 dedicated schemas in `execution_position/schemas/position_policy_sidecar_*.json`. 7 dedicated verb registry entries (all experimental).

### F12. Schema registry validates payloads at emission time
`VerbSchemaRegistry` loads `verb_registry_v1.yaml`, pre-compiles `Draft7Validator` per verb. `FSMCore.emit()` calls validation on every emission. Missing schema = deprecation warning. Schema violation = `InvalidMessagePayloadError`.

### F13. Protocol Message envelope includes: rid, span_id, parent_span_id, ts, ttl_ms, idempotent_key, why, mode, mode_contract, corr_id
These are available to all events and do not need to be duplicated in payload schemas. Payload schemas should focus on domain-specific fields.

---

## 4. INFERENCES

### I1. The Judge system is architecturally distinct from the shadow_telemetry LLM path
shadow_telemetry provides an external intent ingress that bypasses decision_making. The Judge system intercepts the normal decision_making pipeline as a policy overlay. These are orthogonal: one injects intents, the other evaluates them. They should not share a config surface.

### I2. The Judge domain should not live inside decision_making or execution_position
Given the concept's "LLM is policy judge only, never execution truth owner" law, and the "no mixed entry+lifecycle+execution mega-contract" law, the Judge contracts belong in a dedicated domain surface. Precedent: neocortex is a separate domain; alpha_search is a separate domain; position_policy_sidecar is embedded in execution_position but has its own config sub-tree and schema family. The Judge is more like neocortex/alpha_search (separate observer) than sidecar (embedded evaluator).

### I3. The most natural domain name is `policy_cortex` or `judge`
Following the repo's domain naming convention (snake_case, 1-2 words, descriptive): `decision_making`, `execution_position`, `feature_engineering`, `alpha_search`, `shadow_telemetry`, `position_tracking`, `regime_detector`. Candidates: `policy_cortex`, `llm_judge`, `bicameral_cortex`, `judge_cortex`. Recommendation: `policy_cortex` — it describes the function (policy evaluation) without coupling to implementation (LLM).

### I4. Phase 1 schemas should use `additionalProperties: false` for core contracts, `additionalProperties: true` for evidence envelope
`ExpertOutput`, `ChamberAggregate`, `JudgeVerdict` should be strict (prevent drift). `JudgeEvidenceEnvelope` should be extensible (different expert types produce different evidence shapes). This follows the repo pattern: core contracts (trade_intent, decision_blocked) are strict; aggregation/scoring contracts (alpha_score, sidecar) are loose.

### I5. Config should enter in Phase 1 to establish the mode gate
The sidecar and neocortex both introduce config in their Phase 1. Without a config surface, Phase 2 implementation would have nowhere to declare `mode: shadow` and startup gates could not enforce shadow-only. Config should be minimal: `enabled`, `mode` (with only `off` and `shadow` allowed in Phase 1), and basic identity fields.

---

## 5. ASSUMPTIONS

### A1. The concept document's contract list (`ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, `JudgeVerdict`) is authoritative
Source: task mandate. The concept document does not exist, so this is assumed from the task description.

### A2. "Expert" refers to a deterministic or LLM-backed scoring module that produces typed output for a single perspective
Source: inferred from the concept's "chamber" metaphor (multiple experts feed a chamber that aggregates for the judge). No code definition exists.

### A3. The Judge will intercept the strategy-to-intent pipeline in decision_making (Phase 2+)
Source: inferred from concept law "LLM is policy judge only, never execution truth owner" + StrategyGateway gate architecture. The exact interception point is a Phase 2 design decision.

### A4. The verb prefix `JUDGE_` in event names is acceptable per repo conventions
Source: inferred from existing prefixes (`NEOCORTEX_`, `POSITION_POLICY_SIDECAR_`, `ALPHA_SCORE_`). Domain-specific prefixes are the pattern.

### A5. Phase 1 does not need to define the LLM API contract (prompt format, model version, inference endpoint)
Source: concept law "shadow-first rollout" — Phase 1 is contracts only, no runtime.

---

## 6. UNKNOWNS

### U1. (BLOCKING) Which experts will exist?
The concept defines `ExpertOutput` but does not enumerate expert types. Phase 1 must decide whether expert_id is a free string or an enum. **Mitigation**: Define expert_id as a non-empty string in Phase 1; defer the expert registry enum to Phase 2 when concrete experts are implemented.

### U2. (BLOCKING) What is the formal relationship between neocortex shadow intents and the cortex Expert model?
Neocortex already emits `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` with confidence, value, why[], latent_state. Is this a future expert input? **Mitigation**: Phase 1 should define ExpertOutput broadly enough that NEOCORTEX_SHADOW_INTENT_PROPOSED could be adapted to an ExpertOutput in Phase 2, but Phase 1 should NOT wire the adapter.

### U3. (NON-BLOCKING) What aggregation algorithm will the chamber use?
Phase 1 only defines the ChamberAggregate shape, not the runtime algorithm. The shape must accommodate weighted voting, simple majority, and ranked preferences.

### U4. (NON-BLOCKING) What is the prompt/version traceability contract for LLM calls?
Phase 1 should include placeholder fields (`prompt_template_id`, `model_version`) in JudgeEvidenceEnvelope but not define the runtime traceability system.

### U5. (NON-BLOCKING) Whether the Judge evaluates entry-only or also lifecycle (hold/exit)
The concept mentions both entry and lifecycle verdicts. Phase 1 defines the contract shapes to accommodate both via a `verdict_scope` field, but only the entry scope needs concrete schema validation.

### U6. (NON-BLOCKING) Whether costs/latency constraints on LLM inference need Phase 1 config
Deferred. Phase 1 config is mode-only. Inference budgets are a Phase 2 concern.

---

## 7. Current Repo Truth Relevant to Phase 1

### 7.1 Ownership Map

| Domain | Owner of | Boundary |
|---|---|---|
| `decision_making` | `EVT:TRADE_INTENT_PROPOSED`, strategy signals, rejection events | No imports from EP; read-only OrderIndex query |
| `execution_position` | Order lifecycle, bracket management, position FSM | Consumes TRADE_INTENT_PROPOSED; never makes decisions |
| `feature_engineering` | `EVT:FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY` | Upstream data producer |
| `alpha_search` | `EVT:ALPHA_SCORE_CALCULATED` (shadow) | Shadow-only multi-provider scoring |
| `shadow_telemetry` | `EVT:LLM_INTENT_*_V1`, `CMD:LLM_INTENT_SUBMIT_V1` | External LLM intent ingress (bypasses DM) |
| `neocortex` | `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED`, alerts, state | Neural net shadow advisor (PPO/VAE) |
| `regime_detector` | `EVT:REGIME_DETECTED` | Deterministic regime classification |
| `risk_management` | `EVT:RISK_ASSESSMENT_COMPLETED` | Risk scoring |
| `position_tracking` | `EVT:PORTFOLIO_STATE_UPDATED` | Portfolio state |

### 7.2 Current Event/Contract Map Relevant to Judge

| Event | Owner | Schema | Status | Relevance |
|---|---|---|---|---|
| `EVT:TRADE_INTENT_PROPOSED` | decision_making | `trade_intent_v1.json` | active | Judge would evaluate before or after this |
| `EVT:TRADE_INTENT_REJECTED` | decision_making | yes | experimental | Precedent for rejection events |
| `EVT:STRATEGY_DECISION_BLOCKED` | decision_making | `str_decision_blocked_v1.json` | experimental | Precedent for blocking events |
| `EVT:ALPHA_SCORE_CALCULATED` | alpha_search | `alpha_score_calculated_v1.json` | active | Potential expert input |
| `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` | neocortex | no | experimental | Potential expert input |
| `EVT:POSITION_POLICY_SIDECAR_EVALUATED` | execution_position | `position_policy_sidecar_evaluated_v1.json` | experimental | Structural template for verdict events |
| `EVT:POSITION_POLICY_SIDECAR_SUPPRESSED` | execution_position | `position_policy_sidecar_suppressed_v1.json` | experimental | Structural template for suppression events |
| `EVT:LLM_INTENT_RECEIVED_V1` | shadow_telemetry | no | experimental | Existing LLM surface (separate path) |

### 7.3 Current Config Map Relevant to Judge

| Config Surface | Path | Purpose | Overlap Risk |
|---|---|---|---|
| `trading.llm_orchestration` | `config/aurora/trading.yaml` | External LLM intent ingress mode | LOW — governs shadow_telemetry path, not Judge |
| `domains.shadow_telemetry` | `config/aurora/domains.yaml` | Shadow telemetry domain toggle | NONE — separate domain |
| `strategies.llm_microstructure` | `config/aurora/strategies/llm_microstructure.yaml` | LLM microstructure strategy profile | LOW — governs external intent, not Judge |
| `domains.decision_making` | `config/aurora/domains.yaml` | DM gates, arming, QoS | MEDIUM — Judge gate in Phase 2 would interact with these |

### 7.4 Existing LLM/Shadow/External-Intent Precedent Map

| Surface | Pattern | Reusable? |
|---|---|---|
| Neocortex shadow gates | ShadowGateEvaluator + ShadowReadinessReport + per-gate evidence | YES — template for Judge startup gates |
| Neocortex config `extra='forbid'`, `frozen=True` | Strict Pydantic models | YES — standard for all new config |
| Neocortex provenance (DatasetSampleProvenance, 16 fields) | Typed provenance tracking | YES — template for evidence provenance |
| Neocortex idempotent_key pattern | `neocortex:r2:{symbol}:{action}:{ts}:{hash}` | YES — template for verdict dedup |
| Sidecar config discipline (Phase 1 = config only) | Config-first before logic | YES — exact rollout pattern |
| Sidecar schema family (7 schemas, 7 verbs) | Per-event schemas | YES — template for verdict event family |
| alpha_search `shadow_mode` flag | Shadow-only execution | YES — simple shadow pattern |
| shadow_telemetry bearer auth + rate limits | External API hardening | DEFERRED — Phase 1 has no external API |

---

## 8. Contract Surface Proposal

### 8.1 `ExpertOutput`

| Attribute | Value |
|---|---|
| **Purpose** | Typed output from a single expert (deterministic scorer, TA module, or LLM-backed evaluator). Represents one perspective on a trading decision. |
| **Owner** | `policy_cortex` domain |
| **Canonical location (Pydantic)** | `apps/reference/domains/policy_cortex/contracts.py` |
| **Canonical location (JSON Schema)** | `apps/reference/domains/policy_cortex/schemas/expert_output_v1.json` |
| **Shape** | Dual: Pydantic model (runtime) + JSON Schema (registry validation) |
| **SSOT** | Pydantic-first. JSON Schema derived/kept in sync manually (following sidecar precedent). |

**Required fields**:
```
expert_id           : str (non-empty, identifies the expert module)
expert_version      : str (semver, e.g., "1.0.0")
symbol              : str (trading pair)
tf_sec              : int (timeframe seconds)
ts_ms               : int (epoch ms when expert produced output)
verdict             : Literal["ALLOW", "DENY", "ABSTAIN"]
confidence          : float (0.0 to 1.0)
signal_direction    : Optional[Literal["LONG", "SHORT", "NEUTRAL"]]
reasoning           : list[str] (min 1 item — structured why)
evidence_ref        : Optional[str] (pointer to evidence envelope or raw data)
schema_version      : Literal["1"]
```

**Deferred fields** (Phase 2+):
```
latent_features     : dict (expert-specific opaque payload)
cost_estimate       : float (computation cost for budget tracking)
freshness_ttl_ms    : int (how long this output is valid)
```

**Invariants**:
- `confidence` must be in [0.0, 1.0]
- `verdict` must be one of the enum values
- `ts_ms` must be positive integer
- `reasoning` must have at least 1 item
- `expert_id` must be non-empty string
- If `verdict` is DENY, `reasoning` must include at least one denial reason code

**Fail-closed behavior**: If an expert fails to produce valid output within its TTL, the chamber must treat it as an ABSTAIN with confidence 0.0 (Phase 2 runtime concern, but contract must accommodate this via the ABSTAIN verdict).

**Replay/forensic requirements**: All fields are serializable to JSON. The combination (`expert_id`, `symbol`, `tf_sec`, `ts_ms`) must be unique per evaluation cycle. `schema_version` enables forward-compatible deserialization.

---

### 8.2 `ChamberAggregate`

| Attribute | Value |
|---|---|
| **Purpose** | Typed aggregation of all expert outputs for one evaluation cycle. Represents the collective evidence package before judge evaluation. |
| **Owner** | `policy_cortex` domain |
| **Canonical location (Pydantic)** | `apps/reference/domains/policy_cortex/contracts.py` |
| **Canonical location (JSON Schema)** | `apps/reference/domains/policy_cortex/schemas/chamber_aggregate_v1.json` |
| **Shape** | Dual: Pydantic + JSON Schema |
| **SSOT** | Pydantic-first |

**Required fields**:
```
chamber_id          : str (unique per evaluation cycle — UUID or deterministic hash)
symbol              : str
tf_sec              : int
ts_ms               : int (epoch ms of aggregation)
bar_close_ts_ms     : Optional[int] (bar that triggered this evaluation)
expert_outputs      : list[ExpertOutput] (min 0 — empty is valid if all experts abstained)
expert_count        : int (number of experts solicited)
responding_count    : int (number that produced valid output)
abstaining_count    : int (number that abstained or timed out)
consensus_direction : Optional[Literal["LONG", "SHORT", "NEUTRAL", "SPLIT"]]
consensus_strength  : float (0.0 to 1.0, derived from expert agreement)
admissibility       : Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]
schema_version      : Literal["1"]
```

**Deferred fields**:
```
weights             : dict[str, float] (per-expert weight, Phase 2 calibration)
aggregation_method  : str (Phase 2 — "weighted_vote", "ranked", etc.)
dissent_summary     : list[str] (Phase 3 — structured dissent descriptions)
```

**Invariants**:
- `expert_count >= responding_count + abstaining_count`
- `consensus_strength` in [0.0, 1.0]
- If `admissibility` is INADMISSIBLE, the Judge must ABSTAIN (Phase 2 enforcement)
- `responding_count + abstaining_count <= expert_count`

**Fail-closed behavior**: If aggregation fails or produces inconsistent counts, `admissibility` must be set to INADMISSIBLE. Zero responding experts = QUORUM_INSUFFICIENT.

**Replay/forensic requirements**: `chamber_id` provides replay correlation. `expert_outputs` list provides full expert-level traceability. The aggregate is self-contained.

---

### 8.3 `JudgeEvidenceEnvelope`

| Attribute | Value |
|---|---|
| **Purpose** | Typed, bounded, timestamped, serializable, replayable evidence package that the judge receives. Separates evidence collection from verdict formation. |
| **Owner** | `policy_cortex` domain |
| **Canonical location (Pydantic)** | `apps/reference/domains/policy_cortex/contracts.py` |
| **Canonical location (JSON Schema)** | `apps/reference/domains/policy_cortex/schemas/judge_evidence_envelope_v1.json` |
| **Shape** | Dual: Pydantic + JSON Schema |
| **SSOT** | Pydantic-first |

**Required fields**:
```
envelope_id         : str (UUID)
symbol              : str
tf_sec              : int
ts_ms               : int (epoch ms of envelope assembly)
verdict_scope       : Literal["ENTRY", "LIFECYCLE"] (what the judge is evaluating)
chamber_aggregate   : ChamberAggregate
market_context      : MarketContextSnapshot (frozen feature snapshot)
regime_context      : RegimeContextSnapshot (regime + confidence)
position_context    : Optional[PositionContextSnapshot] (only for LIFECYCLE scope)
strategy_id         : str
strategy_signal     : Optional[dict] (sanitized copy of strategy signal, no execution fields)
intent_reference    : Optional[str] (rid of the TRADE_INTENT being evaluated, if any)
freshness_deadline_ms : int (max age before envelope is considered stale)
assembled_at_ms     : int (when assembly completed)
provenance          : EnvelopeProvenance (traceability metadata)
schema_version      : Literal["1"]
```

**Sub-types** (Pydantic models, defined in same contracts.py):
```python
class MarketContextSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    features_ts_ms: int
    features_source: str  # "EVT:FEATURES_CALCULATED" or similar
    # Specific feature values are NOT embedded — only a ref
    features_ref: Optional[str]  # pointer to features payload (e.g., hash or rid)

class RegimeContextSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    regime: str  # e.g., "TREND_UP", "MEAN_REVERTING"
    regime_confidence: float
    regime_ts_ms: int

class PositionContextSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    has_position: bool
    side: Optional[Literal["LONG", "SHORT"]]
    unrealized_pnl_pct: Optional[float]
    hold_duration_sec: Optional[int]
    bracket_state: Optional[str]  # "ACTIVE", "PENDING", "NONE"

class EnvelopeProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    cortex_version: str        # policy_cortex package version
    prompt_template_id: Optional[str]  # LLM prompt template identifier (Phase 2+)
    model_version: Optional[str]        # LLM model identifier (Phase 2+)
    assembly_source: str       # "policy_cortex.assembler"
```

**Deferred fields**:
```
cost_context        : dict (cost/fee context for economic evaluation)
historical_verdicts : list (recent past verdicts for the same symbol)
```

**Invariants**:
- `assembled_at_ms >= ts_ms`
- `assembled_at_ms >= chamber_aggregate.ts_ms`
- `freshness_deadline_ms > 0`
- If `verdict_scope` is LIFECYCLE, `position_context` must not be None
- `strategy_signal` must NOT contain execution-sensitive fields (order qty, bracket details)

**Fail-closed behavior**: If any snapshot is stale beyond `freshness_deadline_ms`, the envelope must be marked stale and the Judge must ABSTAIN.

**Replay/forensic requirements**: The envelope is the primary replay artifact. `envelope_id` + `provenance` enable full reconstruction. `features_ref` allows joining back to the original features payload without embedding it (bounded size).

---

### 8.4 `JudgeVerdict`

| Attribute | Value |
|---|---|
| **Purpose** | Typed output of the judge's policy evaluation. Maps to a concrete action on the decision pipeline. |
| **Owner** | `policy_cortex` domain |
| **Canonical location (Pydantic)** | `apps/reference/domains/policy_cortex/contracts.py` |
| **Canonical location (JSON Schema)** | `apps/reference/domains/policy_cortex/schemas/judge_verdict_v1.json` |
| **Shape** | Dual: Pydantic + JSON Schema |
| **SSOT** | Pydantic-first |

**Required fields**:
```
verdict_id          : str (UUID)
envelope_id         : str (links to JudgeEvidenceEnvelope)
chamber_id          : str (links to ChamberAggregate)
symbol              : str
tf_sec              : int
ts_ms               : int (epoch ms when verdict was formed)
verdict_scope       : Literal["ENTRY", "LIFECYCLE"]
action              : Literal["ALLOW", "SUPPRESS", "ABSTAIN"]
suppression_reason  : Optional[str] (required if action == SUPPRESS)
suppression_code    : Optional[str] (structured code, e.g., "JUDGE_CONFIDENCE_LOW")
confidence          : float (0.0 to 1.0 — judge's confidence in its own verdict)
reasoning           : list[str] (min 1 — structured justification)
dissent_noted       : bool (whether any expert disagreed with the verdict)
authority_mode      : Literal["shadow", "advisory", "authoritative"]
applied             : bool (whether this verdict was actually applied to the pipeline)
strategy_id         : str
rid                 : str (request ID for correlation with upstream events)
idempotent_key      : str (deterministic: "cortex:{symbol}:{scope}:{ts_ms}:{hash}")
schema_version      : Literal["1"]
```

**Deferred fields**:
```
economic_impact_estimate : float (Phase 3 — estimated PnL impact)
prompt_tokens_used       : int (Phase 2 — LLM cost tracking)
inference_latency_ms     : int (Phase 2 — performance tracking)
verdict_quality_label    : Optional[str] (Phase 4 — post-hoc quality annotation)
```

**Invariants**:
- If `action` is SUPPRESS, `suppression_reason` must be non-empty
- If `authority_mode` is "shadow", `applied` must be False
- `confidence` in [0.0, 1.0]
- `ts_ms >= envelope.assembled_at_ms` (verdict is after evidence)
- `idempotent_key` must be deterministic and reproducible

**Fail-closed behavior**: If the judge fails to produce a verdict, the system must continue as if verdict was ABSTAIN with `applied: False`. The judge must NEVER block the pipeline via failure.

**Replay/forensic requirements**: `verdict_id` → `envelope_id` → `chamber_id` → `expert_outputs` provides full replay chain. `idempotent_key` enables deduplication. `authority_mode` + `applied` distinguish shadow observation from live impact.

---

## 9. Verdict Mapping Proposal

### 9.1 Candidate Events (from concept)

| Concept Name | Assessment |
|---|---|
| `EVT:JUDGE_ENTRY_VERDICT` | Good for entry verdicts |
| `EVT:JUDGE_ENTRY_SUPPRESSED` | Redundant — suppression is a field on verdict, not a separate event |
| `EVT:JUDGE_LIFECYCLE_VERDICT` | Good for lifecycle verdicts |
| `EVT:JUDGE_LIFECYCLE_SUPPRESSED` | Redundant — same reason |

### 9.2 Recommended Final Naming

Following repo conventions (domain-prefixed, SCREAMING_SNAKE_CASE, function-descriptive):

| Event | Op | Verb | Owner | Status | Schema | Phase |
|---|---|---|---|---|---|---|
| `EVT:CORTEX_ENTRY_VERDICT_V1` | EVT | `CORTEX_ENTRY_VERDICT_V1` | `policy_cortex` | experimental | `judge_verdict_v1.json` | 1 (register) |
| `EVT:CORTEX_LIFECYCLE_VERDICT_V1` | EVT | `CORTEX_LIFECYCLE_VERDICT_V1` | `policy_cortex` | experimental | `judge_verdict_v1.json` | 1 (register only, schema shared with entry) |
| `EVT:CORTEX_EVIDENCE_ASSEMBLED_V1` | EVT | `CORTEX_EVIDENCE_ASSEMBLED_V1` | `policy_cortex` | experimental | `judge_evidence_envelope_v1.json` | 1 (register) |
| `EVT:CORTEX_CHAMBER_AGGREGATED_V1` | EVT | `CORTEX_CHAMBER_AGGREGATED_V1` | `policy_cortex` | experimental | `chamber_aggregate_v1.json` | 1 (register) |
| `EVT:CORTEX_EXPERT_PRODUCED_V1` | EVT | `CORTEX_EXPERT_PRODUCED_V1` | `policy_cortex` | experimental | `expert_output_v1.json` | 2 (defer — per-expert events are noisy, register when runtime exists) |
| `EVT:CORTEX_MODE_ACTIVE_V1` | EVT | `CORTEX_MODE_ACTIVE_V1` | `policy_cortex` | experimental | `cortex_mode_active_v1.json` | 1 (register — startup diagnostic) |

**Naming rationale**:
- Prefix `CORTEX_` rather than `JUDGE_` — matches `NEOCORTEX_`, `POSITION_POLICY_SIDECAR_` domain-prefix pattern. Avoids coupling the event name to the LLM implementation detail.
- `_V1` suffix — follows `LLM_INTENT_RECEIVED_V1`, `EXTERNAL_OPEN_REQUEST_V1` versioning convention for experimental events.
- Separate entry/lifecycle — different verdict_scope may have different downstream consumers.
- No separate SUPPRESSED event — suppression is action=SUPPRESS on the verdict event. This avoids event proliferation (sidecar has 7 events and that is already high).

### 9.3 Phase 1 vs Later Registration

| Verb | Register in Phase 1? | Emit in Phase 1? |
|---|---|---|
| `CORTEX_ENTRY_VERDICT_V1` | YES (with schema) | NO (schema-only, no runtime emitter) |
| `CORTEX_LIFECYCLE_VERDICT_V1` | YES (with schema) | NO |
| `CORTEX_EVIDENCE_ASSEMBLED_V1` | YES (with schema) | NO |
| `CORTEX_CHAMBER_AGGREGATED_V1` | YES (with schema) | NO |
| `CORTEX_EXPERT_PRODUCED_V1` | NO (defer to Phase 2) | NO |
| `CORTEX_MODE_ACTIVE_V1` | YES (with schema) | YES (Phase 1 config wiring emits this on startup) |

---

## 10. Config Proposal

### 10.1 Decision: Config enters in Phase 1

**YES.** Following the sidecar precedent (Phase 1 = config-first) and neocortex precedent (config + shadow gates before any logic), Phase 1 must introduce a typed config surface.

### 10.2 Placement Options Evaluated

| Option | Path | Precedent | Verdict |
|---|---|---|---|
| A. `domains.policy_cortex` | `config/aurora/domains.yaml` → `domains.policy_cortex` | Follows all existing domains (DM, FE, EP, etc.) | **RECOMMENDED** |
| B. `domains.decision_making.policy_cortex` | Nested inside DM config | Follows sidecar pattern (embedded in EP) | REJECTED |
| C. `trading.llm_orchestration.policy_cortex` | Nested inside LLM orchestration | Reuses existing LLM config surface | REJECTED |
| D. `strategies.policy_cortex` | New strategy-level config | Follows strategy profile pattern | REJECTED |
| E. Separate YAML file (`config/policy_cortex.yaml`) | Separate file like alpha_search | Follows alpha_search pattern | REJECTED |

**Option A rationale**: The cortex is a domain-level concern, not a strategy-level concern (it evaluates across strategies) and not an LLM-orchestration concern (that governs external intent ingress). It belongs at the same level as other domains. `DomainsConfig` is the registration surface.

**Option B rejection**: The sidecar is embedded in EP because it evaluates EP's own positions. The cortex evaluates DM's signals from outside — embedding it in DM would violate "no mixed entry+lifecycle+execution mega-contract" and make DM's config surface even larger.

**Option C rejection**: `trading.llm_orchestration` governs the shadow_telemetry external intent path. The cortex is a different system with different semantics. Reusing this path would create confusion about which LLM surface controls what.

**Option D rejection**: The cortex is not a strategy — it does not produce signals. It evaluates signals produced by other strategies.

**Option E rejection**: alpha_search has a separate YAML because it has a complex standalone runtime (scenario matrix, virtual traders). Phase 1 cortex config is simple enough for `domains.yaml`.

### 10.3 Canonical YAML Path

```yaml
# In config/aurora/domains.yaml
domains:
  # ... existing domains ...
  policy_cortex:
    enabled: false
    mode: "off"                      # Literal["off", "shadow"]
    # Phase 2+ modes registered as dead config with fail-closed:
    # "advisory", "authoritative" — rejected at validation in Phase 1
    shadow_gates:
      enforcement: "strict"          # Literal["strict", "report_only"]
    identity:
      domain_version: "1.0.0"
    startup_diagnostics:
      emit_mode_active: true
```

### 10.4 Canonical Pydantic Model Placement

```python
# In apps/reference/domains/policy_cortex/config_models.py

class PolicyCortexShadowGatesConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    enforcement: Literal["strict", "report_only"] = "strict"

class PolicyCortexIdentityConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    domain_version: str = "1.0.0"

class PolicyCortexStartupDiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    emit_mode_active: bool = True

class PolicyCortexConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    enabled: bool = False
    mode: Literal["off", "shadow"] = "off"
    shadow_gates: PolicyCortexShadowGatesConfig = Field(
        default_factory=PolicyCortexShadowGatesConfig)
    identity: PolicyCortexIdentityConfig = Field(
        default_factory=PolicyCortexIdentityConfig)
    startup_diagnostics: PolicyCortexStartupDiagnosticsConfig = Field(
        default_factory=PolicyCortexStartupDiagnosticsConfig)
```

Registration in `config_models.py`:
```python
class DomainsConfig(BaseModel):
    # ... existing fields ...
    policy_cortex: Optional[PolicyCortexConfig] = None  # Optional — absent = not wired
```

### 10.5 Allowed Modes

| Mode | Phase 1 | Behavior |
|---|---|---|
| `off` | ALLOWED (default) | Domain is registered but performs no evaluation. No events emitted except `CORTEX_MODE_ACTIVE_V1` if startup_diagnostics.emit_mode_active is true. |
| `shadow` | ALLOWED | Domain evaluates and emits verdict events but `applied` is always false. Shadow gate enforces: `applied` must be false for all verdicts. |
| `advisory` | NOT ALLOWED | Pydantic validator rejects. Phase 2+ only. |
| `authoritative` | NOT ALLOWED | Pydantic validator rejects. Phase 3+ only. |

---

## 11. File-by-File Implementation Blueprint

### Package A: Domain Directory Structure (new files)

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/policy_cortex/__init__.py` | NEW | Package init |
| `apps/reference/domains/policy_cortex/contracts.py` | NEW | ExpertOutput, ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict, MarketContextSnapshot, RegimeContextSnapshot, PositionContextSnapshot, EnvelopeProvenance Pydantic models |
| `apps/reference/domains/policy_cortex/config_models.py` | NEW | PolicyCortexConfig, sub-configs |
| `apps/reference/domains/policy_cortex/domain_dict.json` | NEW | Domain dictionary (imports, exports, components, documentation) |
| `apps/reference/domains/policy_cortex/README.md` | NEW | Domain documentation (minimal — purpose, scope, concepts) |

### Package B: JSON Schemas (new files)

| File | Action | Purpose |
|---|---|---|
| `apps/reference/domains/policy_cortex/schemas/expert_output_v1.json` | NEW | ExpertOutput schema |
| `apps/reference/domains/policy_cortex/schemas/chamber_aggregate_v1.json` | NEW | ChamberAggregate schema |
| `apps/reference/domains/policy_cortex/schemas/judge_evidence_envelope_v1.json` | NEW | JudgeEvidenceEnvelope schema |
| `apps/reference/domains/policy_cortex/schemas/judge_verdict_v1.json` | NEW | JudgeVerdict schema |
| `apps/reference/domains/policy_cortex/schemas/cortex_mode_active_v1.json` | NEW | Startup diagnostic event schema |

### Package C: Registry and Config Integration (modify existing)

| File | Action | Purpose |
|---|---|---|
| `apps/reference/dictionaries/verb_registry_v1.yaml` | MODIFY | Add 5 new verb entries (4 cortex events + mode_active) |
| `apps/reference/config_models.py` | MODIFY | Add `PolicyCortexConfig` import + add `policy_cortex: Optional[PolicyCortexConfig]` to `DomainsConfig` |
| `config/aurora/domains.yaml` | MODIFY | Add `policy_cortex:` config block |

### Package D: Tests (new files)

| File | Action | Purpose |
|---|---|---|
| `tests/domains/policy_cortex/__init__.py` | NEW | Test package |
| `tests/domains/policy_cortex/test_contracts.py` | NEW | Contract validation tests |
| `tests/domains/policy_cortex/test_schemas.py` | NEW | JSON Schema validation tests |
| `tests/domains/policy_cortex/test_config.py` | NEW | Config validation tests |
| `tests/domains/policy_cortex/test_registry.py` | NEW | Verb registry integration tests |
| `tests/domains/policy_cortex/test_serialization.py` | NEW | Replay/serialization round-trip tests |

### Package E: DO NOT TOUCH in Phase 1

| File | Reason |
|---|---|
| `apps/reference/domains/decision_making/*` | No gate wiring in Phase 1 |
| `apps/reference/domains/execution_position/*` | No execution changes |
| `apps/reference/domains/neocortex/*` | No integration wiring |
| `apps/reference/domains/alpha_search/*` | No integration wiring |
| `apps/reference/domains/shadow_telemetry/*` | No integration wiring |
| `apps/reference/main.py` | No startup wiring (Phase 2) |
| `apps/reference/config_loader.py` | No changes needed (domains.yaml loaded wholesale) |
| `vfoundation/core/schema_registry.py` | No changes needed (reads verb_registry_v1.yaml automatically) |
| `vfoundation/core/protocol.py` | No changes needed |

### Package F: Investigate First (before implementation)

| File | Investigation |
|---|---|
| `apps/reference/domains/decision_making/strategy_gateway.py` | Understand Gate chain to document Phase 2 interception point. Read-only in Phase 1. |
| `apps/reference/domains/decision_making/safety_gates.py` | Understand safety gate interface for Phase 2 design notes. Read-only in Phase 1. |

---

## 12. Validation Blueprint

### 12.1 Test Matrix

| Category | Test File | Tests | Description |
|---|---|---|---|
| **A. Contract Validation** | `test_contracts.py` | 15-20 | Valid construction, required field enforcement, type validation, enum validation, invariant enforcement (confidence range, count consistency, suppression requires reason) |
| **B. Schema Validation** | `test_schemas.py` | 20-25 | Valid payload passes schema, unknown field rejected (additionalProperties: false), missing required field rejected, invalid type rejected, decimal string format, enum mismatch, conditional validation (SUPPRESS requires suppression_reason) |
| **C. Config Validation** | `test_config.py` | 10-15 | Valid config loads, unknown field fails (extra='forbid'), invalid mode rejected (advisory/authoritative fail in Phase 1), enabled=true with mode=off is valid, nested sub-config validation |
| **D. Registry / Verb Registration** | `test_registry.py` | 5-8 | All 5 new verbs exist in registry, schema paths resolve, validators compile, owner is `policy_cortex`, status is `experimental` |
| **E. Serialization / Replay** | `test_serialization.py` | 8-12 | JSON round-trip (Pydantic → dict → JSON → Pydantic), schema validation of Pydantic-generated dict, idempotent_key determinism, envelope_id → chamber_id → expert chain reconstruction |
| **F. Negative Tests** | (across all test files) | 10-15 | Empty expert_id, negative confidence, SUPPRESS without reason, LIFECYCLE scope without position_context, stale envelope detection, invalid schema_version, mode="authoritative" rejection |
| **G. Domain Dict** | `test_registry.py` | 2-3 | domain_dict.json is valid JSON, required keys present, version matches |

**Total estimated tests**: 70-98

### 12.2 Proof Artifacts Required

| Artifact | Format | Required for Phase 1 completion |
|---|---|---|
| All tests pass | `pytest` output | YES |
| Schema compilation proof | All 5 schemas compile via `Draft7Validator` | YES |
| Verb registry integration proof | Global registry loads all 5 new verbs | YES |
| Config validation proof | `AuroraConfig.model_validate()` passes with new policy_cortex block | YES |
| Round-trip serialization proof | At least 1 full chain (expert → chamber → envelope → verdict) serializes and deserializes | YES |
| REPORT document | `reports/PHASE1_CONTRACT_PACKAGE_REPORT.md` | YES |

### 12.3 REPORT Expectations

The Phase 1 completion report must contain:
1. **Explicit verdict**: DONE / DONE WITH RESERVATIONS / NOT DONE
2. **Test results summary**: count, failures, category breakdown
3. **Schema compilation evidence**: all 5 schemas loaded by registry
4. **Config integration evidence**: `AuroraConfig` validates with policy_cortex block
5. **What is proven**: exact contract shapes, serialization, validation
6. **What remains unproven**: runtime wiring, LLM integration, gate interception
7. **Known limitations**: list of Phase 1 boundaries
8. **Open issues**: any discovered during implementation

---

## 13. Risks

### R1. Schema Drift Between Pydantic and JSON Schema

| Attribute | Value |
|---|---|
| **Cause** | Dual-source contracts (Pydantic models + JSON Schemas maintained separately) |
| **Mechanism** | Developer updates Pydantic model and forgets to update JSON Schema, or vice versa |
| **Effect** | Runtime validation passes (Pydantic) but FSM emission fails (JSON Schema), or vice versa |
| **Severity** | MEDIUM — causes silent contract violations or spurious failures |
| **Mitigation** | Phase 1 test suite must include cross-validation: generate dict from Pydantic, validate against JSON Schema. This is a test, not a runtime enforcement. Consider Phase 2 tooling for schema generation from Pydantic. |

### R2. Config Surface Expansion Without Runtime

| Attribute | Value |
|---|---|
| **Cause** | Phase 1 adds config fields that have no runtime consumer |
| **Mechanism** | Config exists in YAML, passes validation, but no code reads it |
| **Effect** | Operator confusion — config changes have no observable effect |
| **Severity** | LOW — this is the intended Phase 1 posture (config-first before logic) |
| **Mitigation** | Phase 1 README must explicitly document: "Config surface only. No runtime evaluation in Phase 1." `CORTEX_MODE_ACTIVE_V1` emission on startup provides minimal observable proof that config is loaded. |

### R3. Naming Collision Risk

| Attribute | Value |
|---|---|
| **Cause** | `CORTEX_` prefix collides with future neocortex expansion |
| **Mechanism** | Neocortex uses `NEOCORTEX_` prefix currently, but "cortex" is semantically close |
| **Effect** | Operator confusion when filtering logs by event prefix |
| **Severity** | LOW — `CORTEX_` and `NEOCORTEX_` are distinct string prefixes |
| **Mitigation** | Use `CORTEX_` consistently for policy_cortex domain. Document the distinction in domain README. |

### R4. Evidence Envelope Size Explosion

| Attribute | Value |
|---|---|
| **Cause** | JudgeEvidenceEnvelope embeds ChamberAggregate which embeds list[ExpertOutput] |
| **Mechanism** | With many experts, each producing verbose reasoning, the envelope becomes very large |
| **Effect** | WAL bloat, FSM emission latency, replay storage pressure |
| **Severity** | LOW in Phase 1 (no runtime), MEDIUM in Phase 2+ |
| **Mitigation** | Phase 1 contracts use `features_ref` (pointer) rather than embedded feature snapshots. Phase 2 should enforce `max_expert_count` and `max_reasoning_items` limits in config. |

### R5. Concept Document Absence

| Attribute | Value |
|---|---|
| **Cause** | `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` does not exist in repo |
| **Mechanism** | Phase 1 is designed from task description, not from a frozen concept SSOT |
| **Effect** | Design decisions may diverge from the original author's intent |
| **Severity** | MEDIUM — affects Phase 2+ design alignment |
| **Mitigation** | Before Phase 1 implementation, commit the concept document. Phase 1 plan references it explicitly. |

### R6. Silent Revival of Legacy Math

| Attribute | Value |
|---|---|
| **Cause** | An expert implementation (Phase 2+) wraps aurora quadratic scoring |
| **Mechanism** | ExpertOutput with expert_id="aurora_quadratic" simply re-runs the same math that StrategyGateway already evaluated |
| **Effect** | Double-counting of aurora signals, or silent reintroduction of disabled math |
| **Severity** | HIGH in Phase 2+ if not guarded |
| **Mitigation** | Phase 1 contract `ExpertOutput.expert_id` must be documented as "must identify a novel evaluation perspective, not a wrapper for existing strategy signals." Phase 2 implementation must enforce this via an expert allowlist in config. |

---

## 14. Open Design Decisions

### OD1. Expert ID: Free String vs Enum

**Options**:
- (A) Free string (`str`, non-empty) — extensible, no config change to add experts
- (B) Registered enum — fail-closed on unknown experts, explicit allowlist

**Recommendation**: (A) for Phase 1 (no experts exist yet). Phase 2 introduces `allowed_expert_ids` config list that acts as a runtime allowlist while keeping the Pydantic field as string.

### OD2. Schema Draft Version

**Options**:
- (A) JSON Schema draft-07 (most existing schemas use this)
- (B) JSON Schema draft/2020-12 (decision_blocked family uses this)

**Recommendation**: (A) draft-07 for consistency with the majority of schemas and with `VerbSchemaRegistry` which pre-compiles `Draft7Validator`.

### OD3. Whether to Create a Standalone config/policy_cortex.yaml

**Options**:
- (A) Inline in `config/aurora/domains.yaml` (simpler, follows most domains)
- (B) Separate `config/policy_cortex.yaml` (follows alpha_search precedent)

**Recommendation**: (A) for Phase 1 (config is minimal). Reassess in Phase 2 if config grows significantly.

### OD4. Whether CORTEX_EVIDENCE_ASSEMBLED_V1 Should Be Registered in Phase 1

The evidence envelope is an intermediate artifact. Registering it as an FSM event means it goes through schema validation on every emission, which is good for rigor but adds overhead.

**Recommendation**: Register in Phase 1 (with schema). The schema validation overhead is irrelevant in shadow mode, and registering it ensures the schema is tested from day one.

---

## 15. Recommended Phase 1 Package Breakdown

### Subpackage 1A: Contracts + Schemas (2-3 days estimated work)

**Entry gate**: Concept document committed (or explicit waiver from operator).
**Contents**:
- Create `apps/reference/domains/policy_cortex/` directory
- `__init__.py`, `contracts.py` (all 8 Pydantic models), `config_models.py`
- 5 JSON schemas in `schemas/`
- `domain_dict.json`
- `README.md`

**Exit gate**: All Pydantic models instantiate with valid data. All JSON schemas compile. Cross-validation (Pydantic → dict → schema) passes.

### Subpackage 1B: Registry + Config Integration (1 day)

**Entry gate**: 1A exit gate passed.
**Contents**:
- Add 5 verbs to `verb_registry_v1.yaml`
- Add `PolicyCortexConfig` to `DomainsConfig` in `config_models.py`
- Add `policy_cortex:` block to `config/aurora/domains.yaml`

**Exit gate**: `AuroraConfig.model_validate()` passes with new block. `VerbSchemaRegistry` loads all 5 new verbs. No existing tests broken.

### Subpackage 1C: Test Suite (1-2 days)

**Entry gate**: 1B exit gate passed.
**Contents**:
- `test_contracts.py` — Pydantic validation tests
- `test_schemas.py` — JSON Schema validation tests (positive + negative)
- `test_config.py` — Config validation tests
- `test_registry.py` — Verb registry + domain_dict tests
- `test_serialization.py` — Round-trip and replay chain tests

**Exit gate**: All tests pass. Test count >= 70. Coverage includes all required fields, all enums, all invariants, all negative cases.

### Subpackage 1D: Documentation + Report (0.5 day)

**Entry gate**: 1C exit gate passed.
**Contents**:
- Complete `README.md` with concept reference, scope, limitations
- Produce `reports/PHASE1_CONTRACT_PACKAGE_REPORT.md`

**Exit gate**: Report contains explicit verdict, test evidence, what is proven, what remains unproven.

---

## 16. Final Recommended Next Task

After this planning document is reviewed and approved:

**Task**: Implement Subpackage 1A — Create `apps/reference/domains/policy_cortex/` with `contracts.py` (8 Pydantic models), `config_models.py` (PolicyCortexConfig), 5 JSON schemas, `domain_dict.json`, and `__init__.py`.

**Pre-requisite**: Commit `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` to the repository as the frozen concept SSOT, or explicitly waive this requirement.

**Acceptance criterion**: All Pydantic models instantiate correctly with valid data and reject invalid data. All JSON schemas compile via `Draft7Validator`. Cross-validation (Pydantic output validates against JSON Schema) passes for all 4 core contracts.

---

## Appendix A: Evidence Citations

| Evidence | Source | Inspection Method |
|---|---|---|
| Verb registry structure | `apps/reference/dictionaries/verb_registry_v1.yaml` | Agent read, full content |
| Config model hierarchy | `apps/reference/config_models.py` | Agent read, grep for class definitions |
| Domain config structure | `config/aurora/domains.yaml` | Agent read |
| Neocortex shadow gates | `apps/reference/domains/neocortex/logic/gates/shadow.py` | Agent read |
| Neocortex config model | `apps/reference/domains/neocortex/config_models.py` | Agent read |
| Neocortex domain.yaml | `apps/reference/domains/neocortex/domain.yaml` | Agent read |
| Decision making pipeline | `apps/reference/domains/decision_making/intent_builder.py`, `strategy_gateway.py`, `safety_gates.py` | Agent read |
| Trade intent schema | `apps/reference/domains/decision_making/schemas/trade_intent_v1.json` | Agent read |
| Sidecar schemas | `apps/reference/domains/execution_position/schemas/position_policy_sidecar_*.json` | Agent read |
| alpha_search config | `apps/reference/domains/alpha_search/config_models.py` (implied from runtime files) | Agent read |
| shadow_telemetry contracts | `apps/reference/domains/shadow_telemetry/contracts.py` | Grep |
| Protocol Message model | `vfoundation/core/protocol.py` | Agent read |
| Schema registry | `vfoundation/core/schema_registry.py` | Agent read |
| LLM orchestration config | `apps/reference/config_models.py` (LLMOrchestrationConfig), `config/aurora/trading.yaml` | Grep, agent read |
| All 11 passport documents | `config/docs/*.md` | Agent read |
| 5 roadmap documents | Root-level `*ROADMAP*.md` | Agent read |
| Domain dictionaries (8) | `apps/reference/domains/*/domain_dict.json` | Agent read |
| 37 JSON schema files | `apps/reference/domains/*/schemas/*.json` | Agent glob + read |

---

## Appendix B: Concept Laws Cross-Reference

| Concept Law | Phase 1 Compliance |
|---|---|
| Additive-only evolution | YES — all files are new; no existing files modified except verb_registry, config_models, domains.yaml (additive additions) |
| Contract-first | YES — entire Phase 1 is contracts only |
| Replayability | YES — all contracts are serializable, have schema_version, envelope chain is reconstructible |
| Shadow-first rollout | YES — only `off` and `shadow` modes allowed; shadow gate blocks advisory/authoritative |
| LLM is policy judge only | YES — contracts define judge output as advisory verdict, never execution command |
| No direct LLM-to-exchange path | YES — JudgeVerdict has no CMD:OPEN or execution fields |
| No silent revival of legacy math | YES — ExpertOutput.expert_id documented as novel perspective requirement; no aurora math wrapped |
| No mixed entry+lifecycle+execution mega-contract | YES — ExpertOutput, ChamberAggregate, JudgeVerdict are separate typed contracts |
| Evidence envelope typed, bounded, timestamped, serializable, replayable | YES — JudgeEvidenceEnvelope meets all criteria |
