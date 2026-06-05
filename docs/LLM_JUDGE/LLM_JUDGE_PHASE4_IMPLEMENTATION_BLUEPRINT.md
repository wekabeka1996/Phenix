# LLM Judge Phase 4 — Evidence Envelope + Shadow Verdict Path — Implementation Blueprint

**Date**: 2026-04-15
**Artifact type**: Final implementation blueprint (SSOT for Phase 4 coding)
**Artifact status**: Ready for implementation handoff
**Branch**: Phenix_v2

---

## 1. Executive Verdict

**GO-WITH-CONSTRAINTS**

Phase 4 may proceed. All Phase 1-3 prerequisite gates are CLOSED.

Constraints:
- C1: Phase 4 runtime admission remains `shadow` only. `hybrid_advisory` is NOT admitted at runtime; it exists only in the type surface.
- C2: No `decision_making`, `execution_position`, `main.py`, or `config_loader.py` changes.
- C3: Lifecycle verdict path is partially operational: evidence envelope is assembled with the lifecycle chamber stub, but verdict is always `UNKNOWN` because no lifecycle experts exist. This is correct behavior, not a deferral.
- C4: Phase 4 is deterministic verdict assembly. No LLM runtime calls. No external API calls. The "LLM" in "LLM Judge" refers to the future Phase 5+ path. Phase 4 is a deterministic pre-judge that maps chamber consensus to typed verdicts.

---

## 2. Authority Model

### 2.1 Supplied semantic authority
- `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` (governing concept)
  - Defines verdict vocabulary, modes, ownership constraints, contract families, phase rollout

### 2.2 Frozen prior-phase authority
- Phase 1 blueprint + report: contracts, schemas, verb registry, config
- Phase 2 blueprint + report: legacy expert revival, shadow emission
- Phase 2 audit + defect fix: provider integration, bridge completion
- Phase 3 blueprint + report: chamber substrate, admissibility, aggregation

### 2.3 Repo-resident truth
- `apps/reference/domains/alpha_search/judge/contracts.py`: 6 Pydantic models + 3 type aliases (frozen)
- `apps/reference/domains/alpha_search/judge/config_models.py`: Phase 1-3 config surface
- `apps/reference/domains/alpha_search/judge/chamber/`: admissibility + aggregator
- `apps/reference/domains/alpha_search/judge/experts/`: two experts + bridge
- `apps/reference/domains/alpha_search/backtest_plugin.py`: orchestration with chamber integration
- `config/alpha_search.yaml`: YAML SSOT
- `apps/reference/dictionaries/verb_registry_v1.yaml`: 5 judge verbs registered
- 4 JSON schemas under `judge/schemas/`
- 292 judge tests passing

### 2.4 Operator-profile policy
- Governed by this document, Section 10
- Operator must opt in via `judge.mode: "shadow"` and `judge.enabled: true` to activate Phase 4 path
- Default YAML ships with `judge.enabled: false` / `judge.mode: "off"` — this is intentional for safe rollout
- Recommended shadow profile defined below (Section 10.3)

---

## 3. Fixed Inputs from Phases 1-3

The following are frozen and must NOT be reopened:

1. **contracts.py**: All 6 Pydantic models (ExpertOutput, ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict, PositionContextSnapshot, EnvelopeProvenance) + 3 type aliases (EntryVerdict, LifecycleVerdict, CortexMode). No modifications.
2. **JSON schemas**: 4 files under `judge/schemas/`. No modifications.
3. **Expert modules**: `signal_weights_expert.py`, `feature_neutrals_expert.py`. No modifications.
4. **Expert output bridge**: `expert_output_bridge.py`. Phase 3 additions frozen (write_jsonl_chamber_log).
5. **Chamber module**: `admissibility.py`, `chamber_aggregator.py`. No modifications.
6. **Phase 1-3 config models**: SignalWeightsExpertConfig, FeatureNeutralsExpertConfig, JudgeExpertsConfig, JudgeShadowLogConfig, ChamberConfig. All frozen. New Phase 4 config is additive only.
7. **Verb registry**: 5 existing judge verbs (JUDGE_ENTRY_VERDICT_V1, JUDGE_LIFECYCLE_VERDICT_V1, JUDGE_EVIDENCE_ASSEMBLED_V1, JUDGE_CHAMBER_AGGREGATED_V1, JUDGE_EXPERT_PRODUCED_V1). No modifications to existing entries; note update for newly-emitting verbs.
8. **alpha_search placement**: all judge code lives under `apps/reference/domains/alpha_search/judge/`.
9. **No new top-level domain**: no `policy_cortex/` domain.
10. **No surrogate verdict enums**: entry and lifecycle verdicts remain separate contract families.
11. **No live Aurora scoring changes**: quadratic kernel untouched.
12. **No decision_making changes**.
13. **No execution_position changes**.
14. **No main.py changes**.
15. **No config_loader.py changes**.
16. **ChamberAggregate is operational substrate**: Phase 3 made it a live shadow artifact, not just a contract.
17. **Roster-truth accounting**: `enabled: false` expert is NOT part of solicited roster.
18. **Layer separation**: Layer 1 (scoring) → Layer 2 (bridge/emission) → Layer 3 (aggregation) → Layer 4 (envelope/verdict, NEW).

---

## 4. Phase 4 Final Scope

### 4.1 In-scope

1. **Evidence envelope assembly module** (`judge/envelope/`) — assembles `JudgeEvidenceEnvelope` from ChamberAggregate + contextual metadata
2. **Verdict synthesis module** (`judge/verdict/`) — maps chamber consensus + admissibility to typed `JudgeVerdict` in shadow mode
3. **Entry verdict path** — fully operational in shadow: evidence envelope → deterministic verdict → shadow emission + JSONL log
4. **Lifecycle verdict path** — structurally operational: envelope assembled → verdict always `UNKNOWN` (no lifecycle experts) → shadow emission + JSONL log (only when `lifecycle_enabled: true`)
5. **Verdict config surface** — `VerdictConfig` added to `JudgeCortexConfig` controlling verdict assembly behavior
6. **Orchestration integration** — `_run_chamber_aggregation()` extended to call envelope assembly + verdict synthesis after chamber aggregation
7. **New shadow events emitted**: `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1`, `EVT:JUDGE_ENTRY_VERDICT_V1`, `EVT:JUDGE_LIFECYCLE_VERDICT_V1`
8. **JSONL shadow logs** for envelopes and verdicts
9. **Domain dict + verb registry updates** — status progression for newly-emitting verbs
10. **Tests** — envelope, verdict, integration, end-to-end shadow path

### 4.2 Out-of-scope

1. LLM runtime calls (no API calls, no prompt assembly, no model inference)
2. `hybrid_advisory` runtime admission (type surface only)
3. StrategyGateway gate insertion
4. `decision_making` authority or consultation
5. `execution_position` authority or mutation
6. `main.py` / `config_loader.py` changes
7. New top-level domain creation
8. Position management (PROTECT/EXIT applied)
9. Contract modifications (contracts.py is frozen)
10. Schema modifications
11. Expert module modifications
12. Chamber module modifications

---

## 5. FACTS

- **F1**: `JudgeEvidenceEnvelope` contract exists in `contracts.py` with fields: `envelope_id`, `symbol`, `tf_sec`, `ts_ms`, `verdict_scope`, `chamber_aggregate`, `strategy_id`, `regime`, `regime_confidence`, `features_ref`, `position_context`, `freshness_deadline_ms`, `provenance`, `schema_version`.
- **F2**: `JudgeVerdict` contract exists in `contracts.py` with fields: `verdict_id`, `envelope_id`, `chamber_id`, `symbol`, `tf_sec`, `ts_ms`, `verdict_scope`, `entry_verdict`, `lifecycle_verdict`, `suppression_reason`, `suppression_code`, `confidence`, `reasoning`, `dissent_noted`, `authority_mode`, `applied`, `strategy_id`, `schema_version`.
- **F3**: `JudgeVerdict` has validator `validate_applied_mode_consistency`: `authority_mode in ("off", "shadow") → applied=False`. Phase 4 runs in shadow → `applied` is always `False`.
- **F4**: `JudgeEvidenceEnvelope` has validator `validate_lifecycle_requires_position`: `verdict_scope="LIFECYCLE" → position_context required`.
- **F5**: `EVT:JUDGE_ENTRY_VERDICT_V1` and `EVT:JUDGE_LIFECYCLE_VERDICT_V1` are registered in verb_registry with status `experimental` and schema `judge/schemas/judge_verdict_v1.json`.
- **F6**: `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1` is registered in verb_registry with status `experimental` and schema `judge/schemas/judge_evidence_envelope_v1.json`.
- **F7**: `ChamberAggregate` (Phase 3 output) contains: `chamber_id`, `symbol`, `tf_sec`, `ts_ms`, `verdict_scope`, `expert_outputs`, `expert_count`, `responding_count`, `abstaining_count`, `consensus_direction`, `consensus_strength`, `admissibility`.
- **F8**: `backtest_plugin.py` currently calls `_run_chamber_aggregation()` after provider loop, which emits `EVT:JUDGE_CHAMBER_AGGREGATED_V1` and writes chamber JSONL.
- **F9**: `_run_chamber_aggregation()` has access to: `symbol`, `tf_sec`, `bar_close_ts`, `solicited_expert_ids`, `judge_expert_outputs`, `self.config`, `self.event_bus`.
- **F10**: `EnvelopeProvenance` requires `cortex_version` (str) and `assembly_source` (str). `prompt_template_id` and `model_version` are optional (Phase 2+).
- **F11**: `PositionContextSnapshot` is required by envelope when `verdict_scope="LIFECYCLE"`. The backtest plugin has no access to live position state. For shadow-mode lifecycle stubs, a synthetic no-position snapshot is appropriate.
- **F12**: Both experts currently produce ENTRY-only outputs (`entry_verdict` set, `lifecycle_verdict=None`). No lifecycle expert exists.
- **F13**: Guarded surfaces (`decision_making/`, `execution_position/`, `main.py`, `config_loader.py`) contain zero references to the judge sub-package.
- **F14**: The concept document (Section 12) defines Phase 4 as "Hybrid advisory mode. Decision_making consultation." This is the concept's stated aspiration, not a hard implementation requirement for the first Phase 4 delivery.
- **F15**: The concept document (Section 4) defines `hybrid_advisory` as: "Verdicts emitted as advisory signals. Decision_making may consult but is not bound."

---

## 6. INFERENCES

- **I1**: The concept's Phase 4 aspiration (Section 12: "Hybrid advisory mode. Decision_making consultation.") represents the full Phase 4 vision. The shadow verdict path is the necessary first step. `hybrid_advisory` runtime admission and decision_making consultation are deferred to a later Phase 4b or Phase 5, because: (a) concept Law 5 requires shadow-first; (b) advisory consumption requires decision_making changes; (c) user operational intent says "keep this line inside shadow environment."
- **I2**: Deterministic verdict assembly (mapping chamber consensus to JudgeVerdict) is the correct Phase 4a approach. No LLM call is needed. The chamber already aggregates expert opinions; the verdict synthesizer maps: ADMISSIBLE + consensus → typed verdict; INADMISSIBLE/QUORUM_INSUFFICIENT → UNKNOWN.
- **I3**: Evidence envelope assembly can operate entirely within `backtest_plugin.py`'s orchestration scope. Required inputs: ChamberAggregate (available from Phase 3), strategy_id (derivable from config), regime metadata (available from features cache entry if present, else None). No cross-domain data access is needed.
- **I4**: `features_ref` in the envelope should be a typed reference string (e.g., `"bar:{symbol}:{tf_sec}:{bar_close_ts}"`) rather than embedded feature data. This satisfies concept Law 9 ("bounded evidence — no raw feature embedding").
- **I5**: The entry verdict mapping is: `ADMISSIBLE` + `consensus_direction=LONG` → `OPEN_LONG`; `SHORT` → `OPEN_SHORT`; `NEUTRAL` → `NO_ENTRY`; `SPLIT` → `NO_ENTRY` (conservative); `INADMISSIBLE/QUORUM_INSUFFICIENT` → `UNKNOWN`.
- **I6**: `dissent_noted` should be `True` when `consensus_direction=SPLIT` or when any expert verdict diverges from the consensus verdict.
- **I7**: Phase 4 keeps `lifecycle_enabled: false` in default YAML. When operator explicitly sets `lifecycle_enabled: true`, the lifecycle verdict path runs but always produces `UNKNOWN` (no lifecycle experts, zero quorum → QUORUM_INSUFFICIENT → UNKNOWN verdict). This is correct, observable, and truthful.

---

## 7. ASSUMPTIONS

- **A1**: `strategy_id` for the envelope can be derived as `"aurora"` (the primary alpha_search-aligned strategy). This is a static constant in Phase 4 shadow mode. If multi-strategy verdict routing is needed later, it becomes a config parameter.
- **A2**: `cortex_version` in provenance is a static string: `"phase4_shadow_v1"`. Updated when the judge runtime evolves.
- **A3**: `freshness_deadline_ms` in the envelope is computed as `ts_ms + max_staleness_ms` from ChamberConfig. This re-uses the existing staleness threshold as the forward-looking deadline.
- **A4**: `assembly_source` in provenance is `"alpha_search_backtest_plugin"`. This identifies the code site that assembled the envelope.
- **A5**: Regime metadata (`regime`, `regime_confidence`) is optional enrichment only. Absence does not block envelope assembly, does not degrade admissibility, and does not affect verdict mapping in Phase 4. Source: `features` dict keys `"regime"` / `"regime_confidence"`. See Section 13.2.1 for the frozen rule.
- **A6**: The `entry_result` ChamberAggregate (already computed in `_run_chamber_aggregation`) is passed directly into the envelope. No re-aggregation needed.

---

## 8. UNKNOWNS

- **U1**: Whether `features_ref` should encode a file path (JSONL location) or a logical reference. **Disposition**: Use logical reference (`"bar:{symbol}:{tf_sec}:{bar_close_ts}"`). The raw data is in the features cache at evaluation time and in JSONL logs post-hoc. No file path coupling needed.
- **U2**: Whether `regime` metadata is always available in the feature cache entry. **Disposition**: RESOLVED. Frozen as non-blocking optional enrichment (Section 13.2.1). Absence → `None`, no effect on admissibility or verdict.
- **U3**: Whether envelope JSONL and verdict JSONL should be in the same log directory as expert JSONL. **Disposition**: Yes, re-use `judge.shadow_log.log_dir`. Prefix files appropriately (`envelope_`, `verdict_`).

---

## 9. Phase 4 Prerequisite Gates

| Gate | Description | Status |
|------|-------------|--------|
| G1 | Phase 1 contracts frozen | CLOSED |
| G2 | Phase 2 experts operational in shadow | CLOSED |
| G3 | Phase 2 audit defect P2-01 fixed | CLOSED |
| G4 | Phase 3 chamber substrate operational | CLOSED |
| G5 | 292 judge tests passing | CLOSED |
| G6 | Guarded surfaces clean of judge references | CLOSED (verified) |

All gates CLOSED. Phase 4 implementation may proceed.

---

## 10. Runtime Admission and Shadow Activation Policy

### 10.1 Admitted modes (Phase 4)

| Mode | Runtime admitted | Rationale |
|------|-----------------|-----------|
| `off` | YES | No-op. Default. |
| `shadow` | YES | Full shadow verdict path. |
| `hybrid_advisory` | NO (type surface only) | Requires decision_making changes not in scope. |
| `guarded_entry_authority` | NO (type surface only) | Phase 5+. |
| `guarded_lifecycle_authority` | NO (type surface only) | Phase 6+. |

The `validate_phase2_mode_admission` validator in `JudgeCortexConfig` already restricts to `{"off", "shadow"}`. No change needed. Phase 4 does not widen runtime admission.

### 10.2 Disabled-vs-solicited rule (FROZEN)

- An expert with `enabled: false` in config is NOT instantiated as a provider.
- A non-instantiated expert is NOT included in `solicited_expert_ids`.
- A non-solicited expert does NOT count toward `expert_count` in the chamber.
- This rule is already implemented in Phase 3 orchestration and is confirmed correct.

### 10.3 Baseline recommended shadow profile

The following is the recommended production shadow profile for full Phase 4 end-to-end activation:

```yaml
judge:
  enabled: true          # Operator opt-in
  mode: "shadow"         # Shadow verdict path active

  experts:
    signal_weights:
      enabled: true      # Solicited: YES
      # ... (existing Phase 2 config unchanged)
    feature_neutrals:
      enabled: true      # Solicited: YES
      # ... (existing Phase 2 config unchanged)

  shadow_log:
    enabled: true
    log_dir: "logs/judge_experts"

  chamber:
    min_quorum: 1
    max_staleness_ms: 30000
    entry_enabled: true
    lifecycle_enabled: false    # No lifecycle experts exist

  verdict:                       # NEW Phase 4
    entry_enabled: true
    lifecycle_enabled: false     # Mirrors chamber.lifecycle_enabled
    strategy_id: "aurora"
    cortex_version: "phase4_shadow_v1"
```

This profile:
- Both experts enabled → both solicited → expert_count=2
- Entry chamber runs → entry envelope assembled → entry verdict synthesized → shadow emission
- Lifecycle chamber off → no lifecycle verdict
- All JSONL logs written (expert, chamber, envelope, verdict)
- Three shadow events emitted per decision cycle: `EVT:JUDGE_CHAMBER_AGGREGATED_V1`, `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1`, `EVT:JUDGE_ENTRY_VERDICT_V1`

### 10.4 Default shipping profile

```yaml
judge:
  enabled: false
  mode: "off"
```

This is the safe default. Operator must opt in to shadow mode.

---

## 11. Envelope and Verdict Placement Decision

### 11.1 Placement

```
apps/reference/domains/alpha_search/judge/
    envelope/
        __init__.py          # Exports assemble_evidence_envelope
        envelope_assembler.py
    verdict/
        __init__.py          # Exports synthesize_verdict
        verdict_synthesizer.py
```

### 11.2 Why this placement

- Follows established pattern: `judge/chamber/` (Phase 3), `judge/experts/` (Phase 2), `judge/envelope/` (Phase 4), `judge/verdict/` (Phase 4).
- Each functional layer gets its own sub-package.
- Layer 4 (envelope + verdict) sits above Layer 3 (chamber), consuming ChamberAggregate as input.
- Remains fully inside `alpha_search` domain.

### 11.3 Rejected alternatives

- **Inline in backtest_plugin.py**: Rejected. Mixes orchestration with policy logic. The plugin calls into envelope/verdict modules but does not contain their logic.
- **Top-level `policy_cortex/` domain**: Rejected. Frozen decision from Phase 1.
- **Single `judge/verdict_engine.py` file**: Rejected. Envelope assembly and verdict synthesis are separate concerns. Envelope is data packaging; verdict is decision mapping. Different test surfaces.

---

## 12. Phase 4 Runtime / Event Flow

### 12.1 Full end-to-end shadow path (per decision cycle)

```
CMD:PROCESS_STRATEGY arrives
  ↓
backtest_plugin._on_decision_score()
  ↓
Build solicited_expert_ids roster (existing Phase 3)
  ↓
Provider loop: each judge expert → ExpertOutput collected (existing Phase 2-3)
  ↓
Each expert: EVT:JUDGE_EXPERT_PRODUCED_V1 + JSONL (existing Phase 2)
  ↓
_run_chamber_aggregation()
  ├── Entry chamber: ChamberAggregate (existing Phase 3)
  │     EVT:JUDGE_CHAMBER_AGGREGATED_V1 + JSONL (existing Phase 3)
  │     ↓
  │   _assemble_and_emit_verdict() [NEW Phase 4]
  │     ├── assemble_evidence_envelope(entry_result, context) → JudgeEvidenceEnvelope
  │     │     EVT:JUDGE_EVIDENCE_ASSEMBLED_V1 + JSONL [NEW]
  │     ├── synthesize_verdict(envelope) → JudgeVerdict
  │     │     EVT:JUDGE_ENTRY_VERDICT_V1 + JSONL [NEW]
  │     └── (end entry path)
  │
  ├── Lifecycle chamber (only if lifecycle_enabled=True): ChamberAggregate (existing Phase 3)
  │     EVT:JUDGE_CHAMBER_AGGREGATED_V1 + JSONL (existing Phase 3)
  │     ↓
  │   _assemble_and_emit_verdict() [NEW Phase 4]
  │     ├── assemble_evidence_envelope(lifecycle_result, context) → JudgeEvidenceEnvelope
  │     │     EVT:JUDGE_EVIDENCE_ASSEMBLED_V1 + JSONL [NEW]
  │     ├── synthesize_verdict(envelope) → JudgeVerdict
  │     │     EVT:JUDGE_LIFECYCLE_VERDICT_V1 + JSONL [NEW]
  │     └── (end lifecycle path)
  │
  └── (end chamber aggregation)
```

### 12.2 Emission table (Phase 4 shadow path)

| Event | Emitted in Phase 4 | Condition | Payload |
|-------|-------------------|-----------|---------|
| `EVT:JUDGE_EXPERT_PRODUCED_V1` | YES (existing) | Per expert, mode=shadow | ExpertOutput |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` | YES (existing) | Entry chamber + lifecycle if enabled | ChamberAggregate |
| `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1` | YES (**NEW**) | After each chamber aggregate | JudgeEvidenceEnvelope |
| `EVT:JUDGE_ENTRY_VERDICT_V1` | YES (**NEW**) | After entry envelope | JudgeVerdict |
| `EVT:JUDGE_LIFECYCLE_VERDICT_V1` | YES (**NEW**, conditional) | After lifecycle envelope, only if lifecycle_enabled | JudgeVerdict |

### 12.3 Replayability

All emitted events carry serializable Pydantic payloads. JSONL logs written for all artifacts (expert, chamber, envelope, verdict). Full chain is reconstructable:
- ExpertOutput → ChamberAggregate (via expert_outputs list)
- ChamberAggregate → JudgeEvidenceEnvelope (via chamber_aggregate field)
- JudgeEvidenceEnvelope → JudgeVerdict (via envelope_id + chamber_id links)

### 12.4 Deferred to Phase 5+

- `hybrid_advisory` runtime path
- decision_making consultation interface
- StrategyGateway gate insertion
- LLM-backed verdict synthesis (replacing deterministic mapping)
- Position-context enrichment from live portfolio state
- Prompt template assembly for LLM judge calls

---

## 13. Evidence Envelope Design

### 13.1 Inputs

| Field | Source | Notes |
|-------|--------|-------|
| `envelope_id` | Generated | `"env_{verdict_scope}_{symbol}_{ts_ms}"` |
| `symbol` | ChamberAggregate.symbol | Passthrough |
| `tf_sec` | ChamberAggregate.tf_sec | Passthrough |
| `ts_ms` | ChamberAggregate.ts_ms | Passthrough |
| `verdict_scope` | ChamberAggregate.verdict_scope | Passthrough |
| `chamber_aggregate` | ChamberAggregate instance | Embedded (frozen Pydantic model) |
| `strategy_id` | VerdictConfig.strategy_id | Default `"aurora"` |
| `regime` | Feature cache entry (if available) | Best-effort, nullable |
| `regime_confidence` | Feature cache entry (if available) | Best-effort, nullable |
| `features_ref` | Constructed | `"bar:{symbol}:{tf_sec}:{bar_close_ts}"` |
| `position_context` | Synthetic for LIFECYCLE | `PositionContextSnapshot(has_position=False)` for shadow stub; `None` for ENTRY |
| `freshness_deadline_ms` | `ts_ms + chamber_config.max_staleness_ms` | Forward-looking deadline |
| `provenance` | Static for Phase 4 | `EnvelopeProvenance(cortex_version, assembly_source)` |

### 13.2 Enrichment

- **Regime**: Extracted from `features` dict key `"regime"` if present in cache entry. Not all feature bars carry regime metadata. Absence → `None`.
- **Regime confidence**: Extracted from `features` dict key `"regime_confidence"` if present. Absence → `None`.
- **features_ref**: Logical reference, not embedded data. Satisfies concept Law 9.
- **position_context**: For ENTRY scope → `None`. For LIFECYCLE scope → `PositionContextSnapshot(has_position=False)` as shadow stub.

### 13.2.1 Regime metadata semantics (FROZEN)

`regime` and `regime_confidence` are **optional enrichment only** in Phase 4. The following rules are frozen:

1. Their absence **does not block** envelope assembly. The envelope is constructed normally with `regime=None` and `regime_confidence=None`.
2. Their absence **does not degrade admissibility**. Admissibility is determined solely by the chamber (R1-R5 rules). Regime metadata is not an admissibility input.
3. Their absence **does not affect verdict mapping**. The deterministic verdict synthesizer (Section 14.1) maps from `admissibility` + `consensus_direction` only. `regime` and `regime_confidence` are not inputs to the verdict function.
4. Their source of truth is `features` dict in the plugin's feature cache entry, keys `"regime"` (str) and `"regime_confidence"` (float). If the keys are missing or the values are `None`, the envelope carries `None`. No fallback, no default, no error.
5. They exist in the envelope for **replay enrichment** and **future Phase 5+ LLM prompt assembly**. In Phase 4 they are purely informational metadata.

### 13.3 Ownership boundaries

The envelope assembler reads only:
- ChamberAggregate (produced by judge/chamber, same domain)
- VerdictConfig (judge config, same domain)
- Best-effort metadata from the features dict passed through orchestration

It does NOT:
- Import from `decision_making`, `execution_position`, `position_tracking`, or any other domain
- Access portfolio state, order state, or exchange state
- Call external APIs

### 13.4 Fail-closed behavior

If envelope assembly fails for any reason:
- Log error at WARNING with symbol context
- Do NOT emit `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1`
- Do NOT proceed to verdict synthesis
- The chamber event (`EVT:JUDGE_CHAMBER_AGGREGATED_V1`) is still emitted (already happened)
- This preserves the invariant: no verdict without a valid envelope

---

## 14. Verdict Design

### 14.1 Entry verdict path

Deterministic mapping from ChamberAggregate fields:

| Admissibility | consensus_direction | Entry Verdict | Confidence | Reasoning |
|--------------|-------------------|---------------|------------|-----------|
| ADMISSIBLE | LONG | OPEN_LONG | consensus_strength | `["chamber_consensus:LONG"]` |
| ADMISSIBLE | SHORT | OPEN_SHORT | consensus_strength | `["chamber_consensus:SHORT"]` |
| ADMISSIBLE | NEUTRAL | NO_ENTRY | consensus_strength | `["chamber_consensus:NEUTRAL"]` |
| ADMISSIBLE | SPLIT | NO_ENTRY | consensus_strength * 0.5 | `["chamber_consensus:SPLIT", "dissent_downweight"]` |
| ADMISSIBLE | None | UNKNOWN | 0.0 | `["no_consensus_direction"]` |
| INADMISSIBLE | any | UNKNOWN | 0.0 | `["inadmissible:{reason}"]` |
| QUORUM_INSUFFICIENT | any | UNKNOWN | 0.0 | `["quorum_insufficient"]` |

Additional verdict fields:
- `dissent_noted`: `True` if consensus_direction is `SPLIT`, or if any expert's entry_verdict disagrees with the mapped verdict.
- `authority_mode`: Always `"shadow"` in Phase 4.
- `applied`: Always `False` in Phase 4 (enforced by contract validator).
- `suppression_reason`: `None` (no SUPPRESS verdict is produced by the deterministic mapper; SUPPRESS requires an explicit expert recommendation, which Phase 4 deterministic logic does not generate).
- `suppression_code`: `None`.

### 14.2 Lifecycle verdict path

When `lifecycle_enabled: true`:
- Chamber aggregation with zero experts → QUORUM_INSUFFICIENT
- Envelope assembled with `position_context=PositionContextSnapshot(has_position=False)`
- Verdict: `UNKNOWN`, confidence 0.0, reasoning `["no_lifecycle_experts"]`
- `dissent_noted`: `False`
- `authority_mode`: `"shadow"`
- `applied`: `False`

This path exists to prove the full chain works end-to-end. It produces truthful output (UNKNOWN because no inputs exist). When lifecycle experts are implemented in a future phase, this path will produce real verdicts without structural changes.

### 14.3 Shadow-only posture

Phase 4 verdicts are emitted as FSM events and written to JSONL. They are:
- Never consumed by `decision_making`
- Never consumed by `execution_position`
- Never applied to any trading pipeline
- `applied=False` enforced by contract validator when `authority_mode="shadow"`

### 14.4 Mapping rules frozen for Phase 4

The deterministic mapping in Section 14.1 is the complete entry verdict logic. There is no "smart" logic, no thresholds, no LLM call. The chamber's consensus IS the verdict in Phase 4. This is by design: Phase 4 proves the plumbing. Phase 5+ adds intelligence.

---

## 15. Config Package

### 15.1 Canonical config path

`config/alpha_search.yaml` under `judge:` block (existing SSOT).

### 15.2 New config surface: VerdictConfig

```python
class VerdictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_enabled: bool = True
    lifecycle_enabled: bool = False
    strategy_id: str = "aurora"
    cortex_version: str = "phase4_shadow_v1"
    split_confidence_discount: float = 0.5

    @field_validator("split_confidence_discount")
    @classmethod
    def split_confidence_in_range(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError("split_confidence_discount must be in [0.0, 1.0]")
        return v
```

Added to `JudgeCortexConfig`:
```python
class JudgeCortexConfig(BaseModel):
    # ... existing fields ...
    verdict: Optional[VerdictConfig] = None  # NEW Phase 4

    @model_validator(mode="after")
    def validate_verdict_subset_of_chamber(self) -> "JudgeCortexConfig":
        """Verdict path must not be wider than chamber path.

        verdict.entry_enabled requires chamber.entry_enabled.
        verdict.lifecycle_enabled requires chamber.lifecycle_enabled.
        Violation is a config load error (fail-closed), not a runtime no-op.
        """
        if self.verdict is not None and self.chamber is not None:
            if self.verdict.entry_enabled and not self.chamber.entry_enabled:
                raise ValueError(
                    "verdict.entry_enabled=true requires chamber.entry_enabled=true"
                )
            if self.verdict.lifecycle_enabled and not self.chamber.lifecycle_enabled:
                raise ValueError(
                    "verdict.lifecycle_enabled=true requires chamber.lifecycle_enabled=true"
                )
        if self.verdict is not None and self.chamber is None:
            raise ValueError(
                "verdict config requires chamber config to be present"
            )
        return self
```

### 15.3 YAML addition

```yaml
judge:
  # ... existing Phase 2-3 config ...
  verdict:
    entry_enabled: true
    lifecycle_enabled: false
    strategy_id: "aurora"
    cortex_version: "phase4_shadow_v1"
    split_confidence_discount: 0.5
```

### 15.4 Validation rules

- `VerdictConfig` uses `extra="forbid"`, `frozen=True` (consistent with all judge config models)
- `split_confidence_discount` in `[0.0, 1.0]` — controls how much SPLIT consensus degrades confidence
- `strategy_id` must be non-empty string (enforced by Pydantic default + type)
- Backward compatible: `verdict: null` or absent → verdict path disabled (existing Phase 3 behavior)

### 15.5 Cross-config invariant: verdict ⊆ chamber (FROZEN)

The verdict path must not be wider than the chamber path. This is enforced at config load time via `model_validator` on `JudgeCortexConfig`, not at runtime:

| Condition | Result |
|-----------|--------|
| `verdict.entry_enabled=true` + `chamber.entry_enabled=false` | **Config load error** (ValueError) |
| `verdict.lifecycle_enabled=true` + `chamber.lifecycle_enabled=false` | **Config load error** (ValueError) |
| `verdict` present + `chamber` absent | **Config load error** (ValueError) |
| `verdict.entry_enabled=true` + `chamber.entry_enabled=true` | OK |
| `verdict.lifecycle_enabled=false` + `chamber.lifecycle_enabled=true` | OK (verdict narrower than chamber is legal) |
| `verdict` absent + `chamber` present | OK (Phase 3 behavior) |

Rationale: A verdict without a chamber is structurally impossible — there is no ChamberAggregate to put in the envelope. Making this a config-level error (fail-closed) prevents a runtime no-op or silent degradation that would be hard to diagnose.

---

## 16. File-by-File Implementation Blueprint

### Package 4A: Verdict Config
**Entry gate**: 292 judge tests pass
**Exit gate**: Config tests pass, YAML loads, backward compat confirmed

| File | Action | Description |
|------|--------|-------------|
| `judge/config_models.py` | MODIFY | Add `VerdictConfig` class, add `verdict` field to `JudgeCortexConfig` |
| `config/alpha_search.yaml` | MODIFY | Add `verdict:` block under `judge:` |
| `tests/domains/alpha_search/judge/test_config.py` | MODIFY | Add TestVerdictConfig (defaults, validation, frozen, extras) + TestJudgeCortexConfigVerdict (none default, block accepted, backward compat, YAML load) + TestVerdictChamberInvariant (entry wider rejected, lifecycle wider rejected, verdict without chamber rejected, verdict narrower than chamber ok, verdict absent with chamber ok) |

Estimated new tests: ~16

### Package 4B: Envelope Assembly Module
**Entry gate**: Package 4A tests pass
**Exit gate**: Envelope tests pass, all contracts validate

| File | Action | Description |
|------|--------|-------------|
| `judge/envelope/__init__.py` | CREATE | Export `assemble_evidence_envelope` |
| `judge/envelope/envelope_assembler.py` | CREATE | `assemble_evidence_envelope(chamber_aggregate, *, verdict_config, features_ref, regime, regime_confidence, position_context) → JudgeEvidenceEnvelope`. Stateless. Constructs envelope_id, provenance, freshness_deadline. |
| `tests/domains/alpha_search/judge/envelope/__init__.py` | CREATE | Empty |
| `tests/domains/alpha_search/judge/envelope/test_envelope_assembler.py` | CREATE | Tests: basic entry, lifecycle with position, freshness calculation, scope consistency validation, envelope_id format, provenance fields, nil regime, fail-closed on invalid chamber |

Estimated new tests: ~14

### Package 4C: Verdict Synthesis Module
**Entry gate**: Package 4B tests pass
**Exit gate**: Verdict tests pass, all contracts validate

| File | Action | Description |
|------|--------|-------------|
| `judge/verdict/__init__.py` | CREATE | Export `synthesize_verdict` |
| `judge/verdict/verdict_synthesizer.py` | CREATE | `synthesize_verdict(envelope: JudgeEvidenceEnvelope, *, verdict_config: VerdictConfig) → JudgeVerdict`. Deterministic mapping per Section 14.1. |
| `tests/domains/alpha_search/judge/verdict/__init__.py` | CREATE | Empty |
| `tests/domains/alpha_search/judge/verdict/test_verdict_synthesizer.py` | CREATE | Tests: ADMISSIBLE+LONG→OPEN_LONG, ADMISSIBLE+SHORT→OPEN_SHORT, ADMISSIBLE+NEUTRAL→NO_ENTRY, ADMISSIBLE+SPLIT→NO_ENTRY+dissent+discount, ADMISSIBLE+None→UNKNOWN, INADMISSIBLE→UNKNOWN, QUORUM_INSUFFICIENT→UNKNOWN, lifecycle UNKNOWN stub, shadow applied=False, verdict_id format, dissent detection |

Estimated new tests: ~16

### Package 4D: Orchestration Integration + Bridge Extension
**Entry gate**: Packages 4B+4C tests pass
**Exit gate**: Integration tests pass, full shadow path end-to-end

| File | Action | Description |
|------|--------|-------------|
| `judge/experts/expert_output_bridge.py` | MODIFY | Add `write_jsonl_envelope_log()` and `write_jsonl_verdict_log()` (same pattern as existing chamber/expert JSONL writers) |
| `backtest_plugin.py` | MODIFY | Import envelope_assembler + verdict_synthesizer. Extend `_run_chamber_aggregation()` to call new `_assemble_and_emit_verdict()` method after each chamber result. Extract regime from features for enrichment. |
| `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | MODIFY | Add tests: verdict event emitted, envelope event emitted, verdict payload valid JudgeVerdict, envelope payload valid JudgeEvidenceEnvelope, no verdict without chamber, lifecycle verdict when enabled, verdict JSONL written, envelope JSONL written, no verdict when verdict config absent |

Estimated new tests: ~12

### Package 4E: Domain Dict + Verb Registry Update
**Entry gate**: Package 4D tests pass
**Exit gate**: Registry tests still pass, domain_dict accurate

| File | Action | Description |
|------|--------|-------------|
| `domain_dict.json` | MODIFY | Add envelope + verdict components, update description, add phase 4 SSOT note |
| `verb_registry_v1.yaml` | MODIFY | Update notes for JUDGE_ENTRY_VERDICT_V1, JUDGE_LIFECYCLE_VERDICT_V1, JUDGE_EVIDENCE_ASSEMBLED_V1 from "Phase 1 contract registration only" to "Phase 4 shadow emission" |

### Package 4F: Full Test Suite + Report
**Entry gate**: Packages 4A-4E complete
**Exit gate**: All judge tests pass, report written

| File | Action | Description |
|------|--------|-------------|
| Full test suite run | VERIFY | Target: ~350+ judge tests (292 existing + ~54 new) |
| `docs/LLM_JUDGE/PHASE4_EVIDENCE_VERDICT_SHADOW_REPORT.md` | CREATE | Completion report |

### Files explicitly NOT touched

| File | Reason |
|------|--------|
| `judge/contracts.py` | Frozen Phase 1 |
| `judge/schemas/*.json` | Frozen Phase 1 |
| `judge/experts/signal_weights_expert.py` | Frozen Phase 2 |
| `judge/experts/feature_neutrals_expert.py` | Frozen Phase 2 |
| `judge/chamber/admissibility.py` | Frozen Phase 3 |
| `judge/chamber/chamber_aggregator.py` | Frozen Phase 3 |
| `apps/reference/main.py` | Guarded |
| `apps/reference/config_loader.py` | Guarded |
| `apps/reference/domains/decision_making/*` | Guarded |
| `apps/reference/domains/execution_position/*` | Guarded |

---

## 17. Validation Blueprint

### 17.1 Test matrix

| Category | File | Tests | Focus |
|----------|------|-------|-------|
| Verdict config | test_config.py | ~16 | VerdictConfig defaults, validation, JudgeCortexConfig integration, verdict⊆chamber invariant |
| Envelope assembly | test_envelope_assembler.py | ~14 | Contract compliance, field population, scope validation, fail-closed |
| Verdict synthesis | test_verdict_synthesizer.py | ~16 | All mapping cases, dissent, confidence, lifecycle stub, applied=False |
| Integration | test_expert_provider_integration.py | ~12 | End-to-end shadow path, event emission, JSONL, no-verdict-without-config |
| Existing regression | All existing test files | 292 | Zero regressions |
| **Total** | | **~350+** | |

### 17.2 Proof artifacts

1. All ~350+ tests pass with 0 failures
2. Entry verdict JSONL file contains valid JudgeVerdict records
3. Envelope JSONL file contains valid JudgeEvidenceEnvelope records
4. Three new events emitted in shadow mode end-to-end
5. Lifecycle path produces UNKNOWN when enabled (truthful)
6. No events emitted when `verdict: null` (backward compat)
7. No imports of judge sub-package in guarded surfaces
8. `applied=False` in every verdict (contract-enforced)

### 17.3 Acceptance gates

| Gate | Criterion |
|------|-----------|
| AG1 | VerdictConfig loads from YAML, validates, freezes |
| AG2 | `assemble_evidence_envelope()` produces valid JudgeEvidenceEnvelope for entry and lifecycle |
| AG3 | `synthesize_verdict()` produces valid JudgeVerdict for all admissibility + consensus combinations |
| AG4 | End-to-end: CMD:PROCESS_STRATEGY → expert events → chamber event → envelope event → verdict event |
| AG5 | JSONL logs written for envelopes and verdicts |
| AG6 | Zero regressions across 292 existing tests |
| AG7 | Guarded surfaces (decision_making, execution_position, main.py, config_loader.py) remain clean |
| AG8 | `applied=False` for every Phase 4 verdict (contract-enforced, tested) |

---

## 18. Risks

### R1: Envelope assembly scope creep

- **Cause**: Future phases may want live position context, portfolio state, or real-time features in the envelope.
- **Mechanism**: Temptation to import from position_tracking or execution_position.
- **Effect**: Cross-domain coupling, violation of ownership boundaries.
- **Operational severity**: LOW in Phase 4 (all static/best-effort).
- **Mitigation**: Phase 4 envelope uses only data already available in backtest_plugin scope. Position context is a shadow stub. Features are a reference string. No cross-domain imports.

### R2: Deterministic verdict perceived as "real" signal

- **Cause**: Operators may see OPEN_LONG/OPEN_SHORT verdicts in logs and mistake them for actionable signals.
- **Mechanism**: Shadow verdict looks like authority verdict in JSONL.
- **Effect**: Operator confusion, manual trade based on shadow output.
- **Operational severity**: LOW (applied=False, authority_mode="shadow" in every record).
- **Mitigation**: `authority_mode` and `applied` fields clearly mark shadow status. Logs prefixed with "shadow". Documentation.

### R3: Lifecycle path produces only UNKNOWN

- **Cause**: No lifecycle experts exist. Phase 3 lifecycle chamber has zero expert_count.
- **Mechanism**: Lifecycle verdict is always UNKNOWN with confidence 0.0.
- **Effect**: Log noise if lifecycle_enabled=true.
- **Operational severity**: LOW (lifecycle_enabled defaults to false).
- **Mitigation**: Default off. When operator enables, UNKNOWN is truthful output. Documentation states this is expected.

### R4: Backward compatibility break if operator omits verdict config

- **Cause**: Existing Phase 3 deployments have no `verdict:` block in YAML.
- **Mechanism**: If code requires VerdictConfig, existing configs break.
- **Effect**: Startup failure.
- **Operational severity**: MEDIUM.
- **Mitigation**: `verdict: Optional[VerdictConfig] = None`. When None, verdict path is skipped entirely. Existing Phase 3 behavior preserved.

---

## 19. Phase-4 Package Order

```
4A: Verdict Config
  Entry: 292 tests pass
  Exit: Config tests pass, YAML loads
      ↓
4B: Envelope Assembly Module
  Entry: 4A exit gate
  Exit: Envelope unit tests pass
      ↓
4C: Verdict Synthesis Module
  Entry: 4B exit gate
  Exit: Verdict unit tests pass
      ↓
4D: Orchestration Integration + Bridge Extension
  Entry: 4B + 4C exit gates
  Exit: Integration tests pass, end-to-end verified
      ↓
4E: Domain Dict + Verb Registry Update
  Entry: 4D exit gate
  Exit: Registry tests pass, domain_dict accurate
      ↓
4F: Full Test Suite + Report
  Entry: 4A-4E complete
  Exit: ~350+ tests pass, report written
```

---

## 20. Done Criteria

### 20.1 Planning done (this document)

- [x] Phase 4 runtime admission policy frozen (shadow only)
- [x] Baseline shadow activation profile concrete
- [x] Disabled-vs-solicited semantics frozen
- [x] Envelope and verdict path concrete
- [x] Test matrix concrete
- [x] Package order concrete
- [x] No decision_making authority smuggled in
- [x] No execution_position authority smuggled in
- [x] No LLM runtime calls in Phase 4
- [x] All frozen Phase 1-3 decisions preserved
- [x] Cross-config invariant verdict ⊆ chamber frozen (fail-closed at config level)
- [x] Regime metadata frozen as optional non-blocking enrichment
- [x] Model count in contracts.py verified (6 models + 3 type aliases)

### 20.2 Implementation done (for later coding agent)

- [ ] Package 4A: VerdictConfig + YAML + config tests
- [ ] Package 4B: Envelope assembler + unit tests
- [ ] Package 4C: Verdict synthesizer + unit tests
- [ ] Package 4D: Orchestration integration + bridge + integration tests
- [ ] Package 4E: Domain dict + verb registry
- [ ] Package 4F: Full suite pass (~350+ tests) + completion report
- [ ] Guarded surface verification: zero judge imports in decision_making, execution_position, main.py, config_loader.py
- [ ] Every verdict has `applied=False` and `authority_mode="shadow"`

---

## 21. Final Recommended Next Coding Task

**Package 4A — VerdictConfig**

Add `VerdictConfig` to `judge/config_models.py`, add `verdict` field to `JudgeCortexConfig`, add `verdict:` block to `config/alpha_search.yaml`, add config tests. Verify backward compatibility (existing configs without `verdict:` block still load). Run full test suite.

This is the foundation for all Phase 4 code. No envelope or verdict logic can be written until the config surface exists.

---

## 22. Tightening Changelog

Fixes applied during owner review before blueprint freeze:

1. **REQUIRED: Cross-config invariant verdict ⊆ chamber** (Section 15.2, 15.5). Added `model_validator` on `JudgeCortexConfig` enforcing that `verdict.*_enabled` must not be wider than `chamber.*_enabled`. Fail-closed at config load time (ValueError), not a runtime no-op. Also enforces `verdict` requires `chamber` to be present. Rationale: a verdict without a chamber is structurally impossible; inconsistent config must never silently degrade.
2. **REQUIRED: Regime metadata frozen as optional non-blocking enrichment** (Section 13.2.1, A5, U2). Explicitly froze 5 rules: absence does not block envelope assembly, does not degrade admissibility, does not affect verdict mapping, source is features dict only, purpose is replay enrichment and future Phase 5+ LLM prompt assembly. Rationale: without this, a coding agent could invent a blocking rule or admissibility degradation from missing regime.
3. **Minor: Model count correction** (Sections 2.3, 3.1). Changed "7 Pydantic models" to "6 Pydantic models + 3 type aliases". contracts.py contains 6 `class ... (BaseModel)` definitions (PositionContextSnapshot, EnvelopeProvenance, ExpertOutput, ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict) plus 3 `Literal` type aliases (EntryVerdict, LifecycleVerdict, CortexMode).
