# LLM Judge Phase 3 — Implementation Blueprint

**Date**: 2026-04-15
**Artifact type**: Implementation-ready planning SSOT for Phase 3 coding work
**Branch**: Phenix_v2
**Authority chain**: Concept v1 -> Phase 1 Blueprint -> Phase 2 Blueprint -> Phase 1-2 Audit -> DEFECT-P2-01 Fix Report -> this document

---

## 1. Executive Verdict

**GO-WITH-CONSTRAINTS**

Phase 3 implementation may proceed. All prerequisite gates from Phase 1 and Phase 2 are resolvable within the current session. One hard entry gate exists: DEFECT-P2-01 must be proven closed before Phase 3 code that consumes `EVT:JUDGE_EXPERT_PRODUCED_V1` is written. That fix was completed on 2026-04-15 with 234 judge tests and 268 alpha_search tests passing (see Section 9 — Prerequisite Gates).

Phase 3 scope is the **chamber substrate**: Entry Chamber aggregation, Lifecycle Chamber stub, admissibility filtering, aggregation metrics, and shadow-only emission of `EVT:JUDGE_CHAMBER_AGGREGATED_V1`. This is NOT the LLM judge runtime, NOT verdict formation, NOT StrategyGateway insertion, and NOT decision_making authority.

---

## 2. Authority Model

### 2.1 Supplied Semantic Authority

| Document | Role |
|---|---|
| `docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` | Governing concept. Defines chamber architecture (Section 9), evidence envelope (Section 10), verdict architecture (Section 11), phase rollout (Section 12), ownership constraints (Section 6). |

### 2.2 Frozen Prior-Phase Authority

| Document | Role |
|---|---|
| `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_IMPLEMENTATION_BLUEPRINT.md` | Phase 1 planning SSOT. Defines all contract shapes, schemas, verbs, and alpha_search placement. |
| `docs/LLM_JUDGE/PHASE1_CONTRACT_PACKAGE_REPORT.md` | Phase 1 completion evidence. 125 tests, 0 failures. DONE. |
| `docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md` | Phase 2 planning SSOT. Defines expert modules, provider integration, bridge, JSONL logging, shadow mode admission. |
| `docs/LLM_JUDGE/PHASE2_LEGACY_EXPERT_REVIVAL_REPORT.md` | Phase 2 completion evidence. 222 tests, 0 failures. DONE. |

### 2.3 Repo-Resident Truth

| Artifact | Path | Status |
|---|---|---|
| Contract models | `alpha_search/judge/contracts.py` | Frozen. 9 models including ChamberAggregate, JudgeEvidenceEnvelope, JudgeVerdict. |
| Config models | `alpha_search/judge/config_models.py` | JudgeCortexConfig admits `off` and `shadow`. JudgeExpertsConfig, JudgeShadowLogConfig exist. |
| Expert modules | `alpha_search/judge/experts/` | signal_weights_expert.py, feature_neutrals_expert.py, expert_output_bridge.py. All Layer 1 pure scoring. |
| Verb registry | `verb_registry_v1.yaml` | 5 judge verbs registered. `EVT:JUDGE_CHAMBER_AGGREGATED_V1` registered Phase 1 with `status: experimental`. |
| JSON schemas | `alpha_search/judge/schemas/` | 4 schemas. `chamber_aggregate_v1.json` exists and is valid. |
| Provider integration | `alpha_search/backtest_plugin.py` | Judge expert routing via `_process_judge_expert_score()`. DEFECT-P2-01 fixed. |
| YAML config | `config/alpha_search.yaml` | `judge:` block with `enabled: false`, `mode: "off"`, both experts configured, shadow_log configured. |
| Tests | `tests/domains/alpha_search/judge/` | 234 tests passing (Phase 1 + Phase 2 + DEFECT-P2-01 fix). |

### 2.4 Audit Dependency Gate

| Document | Role |
|---|---|
| `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_PHASE2_CODE_AUDIT.md` | Audit authority. Identified DEFECT-P2-01 (bridge not called from provider path). Stated Phase 3 implementation must not proceed until emission gap is proven closed. |
| `docs/LLM_JUDGE/PHASE2_DEFECT_P2_01_FIX_REPORT.md` | Fix report. DEFECT-P2-01 DONE. 234 judge tests, 268 alpha_search tests, 0 failures. `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted, `EVT:ALPHA_SCORE_CALCULATED` suppressed for judge experts, JSONL logging operational. |

---

## 3. Fixed Inputs from Phase 1 and Phase 2

The following are frozen and must NOT be reopened in Phase 3:

### 3.1 Phase 1 Frozen

1. **Contract shapes**: `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, `JudgeVerdict`, `PositionContextSnapshot`, `EnvelopeProvenance` — all fields, validators, and constraints as defined in `contracts.py`.
2. **Vocabulary types**: `EntryVerdict`, `LifecycleVerdict`, `CortexMode` — exact Literal values.
3. **JSON schemas**: All 4 schemas under `judge/schemas/` — additive evolution only.
4. **Verb registry**: 4 Phase 1 verbs (`JUDGE_ENTRY_VERDICT_V1`, `JUDGE_LIFECYCLE_VERDICT_V1`, `JUDGE_EVIDENCE_ASSEMBLED_V1`, `JUDGE_CHAMBER_AGGREGATED_V1`) + 1 Phase 2 verb (`JUDGE_EXPERT_PRODUCED_V1`). All `owner: alpha_search`, `status: experimental`.
5. **Placement**: All Judge artifacts under `apps/reference/domains/alpha_search/judge/`. No top-level `policy_cortex`. No `decision_making` embedding.
6. **Config integration**: `judge: Optional[JudgeCortexConfig]` on `AlphaSearchConfig`. Config loaded from `config/alpha_search.yaml`.

### 3.2 Phase 2 Frozen

7. **Expert modules**: `signal_weights_expert.py` and `feature_neutrals_expert.py` are Layer 1 pure scoring. No modification.
8. **Expert output bridge**: `expert_output_bridge.py` handles `AlphaScore -> ExpertOutput` translation and JSONL logging. No modification except potential new callers.
9. **Provider integration**: `_create_judge_expert()` and `_process_judge_expert_score()` in `backtest_plugin.py`. Judge experts route through bridge, emit `EVT:JUDGE_EXPERT_PRODUCED_V1`, write JSONL.
10. **Shadow mode admission**: `JudgeCortexConfig` validator admits `{"off", "shadow"}`.
11. **Layer separation**: Layer 1 = pure scoring in expert modules. Layer 2 = integration/emission/logging in bridge and plugin.
12. **No live Aurora contamination**: `quadratic_scoring_kernel.py`, `aurora_decision.py`, `aurora_handler.py` — zero judge references.

### 3.3 Immutable Boundaries

13. No `main.py` changes.
14. No `config_loader.py` changes.
15. No root `config_models.py` changes.
16. No `decision_making` changes.
17. No `execution_position` changes.
18. No `quadratic_scoring_kernel.py` changes.
19. No LLM judge runtime.
20. No StrategyGateway authority insertion.
21. No live execution mutation.

---

## 4. Phase 3 Final Scope

### 4.1 In Scope

1. **Entry Chamber runtime**: Aggregation module that collects `ExpertOutput` records scoped to `verdict_scope="ENTRY"`, computes admissibility and consensus metrics, produces a `ChamberAggregate`.
2. **Lifecycle Chamber stub**: Structural equivalent of Entry Chamber scoped to `verdict_scope="LIFECYCLE"`. In Phase 3, no lifecycle experts exist, so this is a code-ready stub that correctly handles zero-expert input (returns `QUORUM_INSUFFICIENT`).
3. **Admissibility filter**: Evaluate freshness, completeness, scope matching, and quorum before accepting a chamber cycle as `ADMISSIBLE`.
4. **Aggregation metrics**: Compute `consensus_direction`, `consensus_strength`, `responding_count`, `abstaining_count` from expert outputs.
5. **Chamber orchestration in backtest_plugin**: After collecting judge expert outputs for a given `(symbol, tf_sec, bar_close_ts)` decision cycle, assemble them into a `ChamberAggregate` and emit `EVT:JUDGE_CHAMBER_AGGREGATED_V1`.
6. **Shadow-only emission**: `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted for logging/replay. Never consumed by decision_making or execution_position.
7. **Chamber config**: Config models for admissibility rules (min quorum, freshness window) and aggregation parameters.
8. **JSONL chamber shadow log**: Append `ChamberAggregate` to JSONL files alongside expert logs.
9. **Tests**: Unit tests for chamber logic, integration tests for orchestration, regression tests for non-judge providers.
10. **Phase 3 completion report**.

### 4.2 Out of Scope

1. **JudgeEvidenceEnvelope assembly**: Deferred to Phase 4. The envelope requires `features_ref`, `regime`, `regime_confidence`, `provenance`, and `position_context` enrichment that depends on cross-domain data not available in the alpha_search shadow substrate.
2. **JudgeVerdict formation**: Deferred to Phase 4. No verdict-producing logic in Phase 3.
3. **`EVT:JUDGE_ENTRY_VERDICT_V1` emission**: Deferred. No verdict = no verdict event.
4. **`EVT:JUDGE_LIFECYCLE_VERDICT_V1` emission**: Deferred.
5. **`EVT:JUDGE_EVIDENCE_ASSEMBLED_V1` emission**: Deferred to Phase 4 (envelope assembly).
6. **LLM judge calls**: Phase 4+.
7. **StrategyGateway gate insertion**: Phase 5+.
8. **Decision_making consultation**: Phase 4+.
9. **Execution_position integration**: Phase 6+.
10. **Lifecycle expert implementations**: Phase 3 provides the lifecycle chamber stub; actual lifecycle experts are Phase 4+.
11. **`normalize_mode="signed_v2"` implementation**: Orthogonal to chamber work.
12. **New top-level domains or config files**: No `policy_cortex`, no `config/judge.yaml`.

---

## 5. FACTS

**F1.** `ChamberAggregate` contract exists in `contracts.py` (lines 114-159) with: `chamber_id`, `symbol`, `tf_sec`, `ts_ms`, `verdict_scope`, `expert_outputs: List[ExpertOutput]`, `expert_count`, `responding_count`, `abstaining_count`, `consensus_direction`, `consensus_strength`, `admissibility`, `schema_version`. Two validators: count consistency and scope consistency.

**F2.** `EVT:JUDGE_CHAMBER_AGGREGATED_V1` is already registered in `verb_registry_v1.yaml` (Phase 1) with `owner: alpha_search`, `status: experimental`, `schema: .../chamber_aggregate_v1.json`. No runtime emission exists.

**F3.** `chamber_aggregate_v1.json` schema exists under `judge/schemas/` and is validated by Phase 1 cross-validation tests.

**F4.** Phase 2 experts are ENTRY-only. Both `signal_weights_expert` and `feature_neutrals_expert` produce entry-scoped `ExpertOutput` (entry_verdict set, lifecycle_verdict None).

**F5.** `backtest_plugin.py:_process_judge_expert_score()` emits `EVT:JUDGE_EXPERT_PRODUCED_V1` per expert per `(symbol, bar_close_ts)` decision cycle. After DEFECT-P2-01 fix, this is the proven shadow emission path.

**F6.** The concept (Section 9) states: chamber "tracks expert count, responding count, and abstaining count; determines consensus direction and strength; produces an admissibility assessment: one of ADMISSIBLE, INADMISSIBLE, QUORUM_INSUFFICIENT; preserves all individual expert outputs for replay."

**F7.** The concept (Section 12) defines Phase 3 as "Shadow telemetry integration. Verdict logging." The `shadow` operational mode spans Phase 2-3.

**F8.** `decision_making/` contains 48 Python files. Zero semantic references to `judge`. `execution_position/` contains 52 Python files. Zero references to `judge`.

**F9.** `backtest_plugin.py` iterates providers in `_on_decision_score()`, calling `_process_score()` or `_process_judge_expert_score()` per provider. Judge expert outputs are individually emitted. No collection/aggregation step exists.

**F10.** `JudgeEvidenceEnvelope` requires fields not available in alpha_search context: `strategy_id`, `regime`, `regime_confidence`, `position_context`, `freshness_deadline_ms`, `provenance` (with `cortex_version`, `assembly_source`). Some of these require cross-domain data.

**F11.** `_emit_fail_closed_score()` suppresses judge expert events entirely (DEFECT-P2-01 Change 4). A fail-closed judge expert produces NO event and NO `ExpertOutput`. The chamber therefore cannot distinguish "expert returned UNKNOWN" from "expert never executed" unless it receives external roster information.

---

## 6. INFERENCES

**I1.** Chamber aggregation must be a post-scoring collection step in `backtest_plugin.py`. After all judge expert providers have been scored for a given `(symbol, tf_sec, bar_close_ts)` cycle, their `ExpertOutput` results must be collected and passed to the chamber.

**I2.** The Entry Chamber and Lifecycle Chamber are not fundamentally different modules — they are the same aggregation logic parameterized by `verdict_scope`. Phase 3 implements a single `ChamberAggregator` class that accepts a `verdict_scope` parameter. The Entry Chamber instance has `verdict_scope="ENTRY"`; the Lifecycle Chamber instance has `verdict_scope="LIFECYCLE"`.

**I3.** In Phase 3, the Lifecycle Chamber will always produce `QUORUM_INSUFFICIENT` because no lifecycle experts exist. This is correct behavior — the stub proves the architecture works for both scopes.

**I4.** The most natural Phase 3 orchestration path is: collect `ExpertOutput` objects in-memory during the judge expert scoring loop, then pass the collection to the chamber aggregator after the loop completes. This avoids event-bus round-tripping and keeps the chamber within the same `_on_decision_score()` call boundary.

**I5.** `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emission is the Phase 3 analog of `EVT:JUDGE_EXPERT_PRODUCED_V1` emission — shadow-only, logged, never consumed by downstream systems.

**I6.** Chamber JSONL logging reuses the same pattern as expert JSONL logging: append one JSON line per cycle to a date-partitioned file under the shared `judge.shadow_log.log_dir`.

**I7.** Chamber accounting must use an **external roster** (solicited expert IDs) as ground truth for `expert_count`, not the count of returned `ExpertOutput` objects. Without this, fail-closed suppressions and provider-path crashes become invisible to the chamber, causing `expert_count` to be understated and quorum/admissibility to be artificially inflated. This is a direct consequence of F11 (fail-closed suppression produces no output) and the fail-closed philosophy established in Phases 1-2.

---

## 7. ASSUMPTIONS

**A1.** A single `ChamberAggregator` class can serve both ENTRY and LIFECYCLE scopes. The scope is a constructor parameter, not a subclass distinction. **Why**: The concept describes one chamber shape (`ChamberAggregate`), not two separate contract families.

**A2.** The in-memory collection pattern (collect expert outputs during the provider loop, aggregate after) is preferred over consuming `EVT:JUDGE_EXPERT_PRODUCED_V1` events from the bus. **Why**: Consuming events would require the chamber to subscribe and buffer asynchronously, adding unnecessary complexity for a synchronous scoring loop. The `ExpertOutput` objects are already constructed in `_process_judge_expert_score()`.

**A3.** Phase 3 does not add new providers to `config/alpha_search.yaml`. The same two expert providers produce outputs; the chamber collects and aggregates them. **Why**: Chamber is aggregation, not scoring.

**A4.** `chamber_id` will be generated as `"entry_{symbol}_{bar_close_ts}"` or `"lifecycle_{symbol}_{bar_close_ts}"`. **Why**: Deterministic, replayable, unique per evaluation cycle.

**A5.** `JudgeEvidenceEnvelope` assembly requires `strategy_id`, `regime`, `regime_confidence`, and `provenance` — data not available purely within alpha_search shadow context. Full envelope assembly is therefore correctly deferred to Phase 4. **Why**: Alpha_search does not own strategy identity or regime state.

**A6.** Minimum quorum of 1 responding expert is sufficient for `ADMISSIBLE` in Phase 3 (only two experts exist, both ENTRY). A quorum of 0 yields `QUORUM_INSUFFICIENT`. **Why**: Simple, correct default for the existing expert count.

---

## 8. UNKNOWNS

| Unknown | Blocking? | Disposition |
|---|---|---|
| Exact consensus_direction algorithm when experts disagree (one LONG, one SHORT) | No | Phase 3 implements majority vote; tie = SPLIT. Two experts with opposing directions = SPLIT. |
| Whether `consensus_strength` should be average confidence or weighted | No | Phase 3 implements simple mean of responding expert confidences. |
| Optimal freshness window for admissibility | No | Phase 3 uses a configurable `max_staleness_ms` defaulting to 30000 (30s). |
| Whether lifecycle experts will share the same `ChamberAggregator` code path | No | Phase 3 designs for it; Phase 4 confirms with real lifecycle experts. |
| Whether `EVT:JUDGE_CHAMBER_AGGREGATED_V1` should carry a `bar_close_ts` field | No | Use the existing `ChamberAggregate.ts_ms` field which timestamps the aggregation moment. `bar_close_ts` can be carried in the `chamber_id` for traceability. |

---

## 9. Phase 3 Prerequisite Gates

### Gate G1: Phase 1 Contracts Complete

**Status**: CLOSED. Phase 1 report confirms DONE with 125 tests. `ChamberAggregate` contract, `chamber_aggregate_v1.json` schema, and `EVT:JUDGE_CHAMBER_AGGREGATED_V1` verb all exist.

### Gate G2: Phase 2 Expert Revival Complete

**Status**: CLOSED. Phase 2 report confirms DONE with 222 tests. Both experts produce `ExpertOutput`. Shadow mode admission operational.

### Gate G3: DEFECT-P2-01 Resolution

**Status**: CLOSED. Fix report dated 2026-04-15 confirms:
- `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted from provider path (12 integration tests prove this)
- `EVT:ALPHA_SCORE_CALCULATED` suppressed for judge experts
- JSONL logging operational from provider path
- 234 judge tests, 268 alpha_search tests, 0 failures

**Verification**: The DEFECT-P2-01 fix is committed on the current branch. Phase 3 implementation may proceed.

### Gate G4: No Decision_Making Contamination

**Status**: CLOSED. Verified: 48 files in `decision_making/`, 0 semantic references to `judge`. `quadratic_scoring_kernel.py` has 0 references to any judge artifact.

---

## 10. Chamber Placement Decision

### 10.1 Chosen Location

```
apps/reference/domains/alpha_search/judge/chamber/
    __init__.py
    chamber_aggregator.py          # ChamberAggregator class
    admissibility.py               # Admissibility filter functions
```

### 10.2 Why Chosen

- Consistent with alpha_search-aligned placement (Concept Section 5, Phase 1 Blueprint Section 9).
- `judge/` already contains `experts/` sub-package; `chamber/` is the parallel aggregation sub-package.
- Matches the concept architecture: experts produce -> chamber aggregates -> (later) envelope assembles -> (later) verdict forms.
- Keeps chamber code isolated from expert scoring code (Layer separation: Layer 1 = experts, Layer 3 = chamber aggregation, Layer 2 = integration bridge between them).

### 10.3 Rejected Alternatives

| Alternative | Why Rejected |
|---|---|
| `alpha_search/chamber.py` (flat file) | Chamber + admissibility logic warrants a sub-package for test isolation and future lifecycle expansion. |
| `alpha_search/judge/experts/chamber.py` | Chamber is not an expert. Semantic confusion. |
| `policy_cortex/` (new top-level domain) | Frozen out. Phase 1 Blueprint Section 9 explicitly rejected this. |
| `decision_making/judge/` | Frozen out. No decision_making changes in Phase 3. |

---

## 11. Chamber Design

### 11.1 ChamberAggregator Class

**File**: `alpha_search/judge/chamber/chamber_aggregator.py`

```
class ChamberAggregator:
    """Aggregates ExpertOutput records into a ChamberAggregate.

    Stateless. Instantiated with verdict_scope and config.
    Called once per evaluation cycle with a list of ExpertOutput records
    AND the roster of solicited expert IDs for that cycle.
    """

    __init__(self, verdict_scope: Literal["ENTRY", "LIFECYCLE"], config: ChamberConfig)
    aggregate(
        self,
        expert_outputs: List[ExpertOutput],
        *,
        expected_expert_ids: List[str],
        symbol: str,
        tf_sec: int,
        ts_ms: int,
    ) -> ChamberAggregate
```

**`aggregate()` logic**:

1. **Determine solicited roster**: `expert_count = len(expected_expert_ids)`. This is the count of experts that SHOULD have responded, derived from the judge provider configs that were solicited during this decision cycle. This number is invariant — it does not depend on how many actually returned.
2. Filter inputs by scope: keep only `ExpertOutput` records matching `verdict_scope`. If `verdict_scope="ENTRY"`, keep only those with `entry_verdict is not None`. If `verdict_scope="LIFECYCLE"`, keep only those with `lifecycle_verdict is not None`.
3. Classify experts:
   - **Responding**: `confidence > 0.0` AND verdict is not `UNKNOWN`.
   - **Abstaining**: `confidence == 0.0` OR verdict is `UNKNOWN`.
4. **Fail-closed accounting**: `responding_count = len(responding)`, `abstaining_count = expert_count - responding_count`. This ensures silent failures (experts that were solicited but crashed, timed out, or never produced output) are counted as abstentions, not invisible. A solicited expert that produced no `ExpertOutput` at all is treated identically to one that returned `UNKNOWN` — both inflate the abstaining count and reduce the responding ratio.
5. **Invariant**: `responding_count + abstaining_count == expert_count` always holds. This is validated by the frozen `ChamberAggregate` Pydantic validator.
6. Run admissibility filter (see 11.5).
7. Compute consensus direction and strength (see 11.6).
8. Generate `chamber_id`: `f"{verdict_scope.lower()}_{symbol}_{ts_ms}"`.
9. Return `ChamberAggregate(...)`.

**Why `expected_expert_ids` and not just `len(expert_outputs)`**: If a solicited expert crashes in the provider path, fails in the bridge, or is suppressed by fail-closed logic, the chamber never sees its `ExpertOutput`. Counting only from returned outputs would understate `expert_count`, inflate the responding ratio, and make quorum artificially easier to meet. This violates fail-closed semantics. The roster is the external ground truth that the chamber cannot derive from its inputs alone.

### 11.2 Entry Chamber

- `verdict_scope = "ENTRY"`.
- In Phase 3: receives outputs from `signal_weights_expert` and `feature_neutrals_expert`.
- Both experts produce entry verdicts (`OPEN_LONG`, `OPEN_SHORT`, `NO_ENTRY`, `SUPPRESS`, `UNKNOWN`).
- With 2 experts, possible consensus outcomes:
  - Both LONG -> `consensus_direction="LONG"`
  - Both SHORT -> `consensus_direction="SHORT"`
  - Both NO_ENTRY -> `consensus_direction="NEUTRAL"`
  - Mixed LONG/SHORT -> `consensus_direction="SPLIT"`
  - Mixed LONG/NO_ENTRY -> `consensus_direction="LONG"` (responding expert wins over neutral)
  - One responding + one UNKNOWN -> direction follows the responding expert
  - Both UNKNOWN -> `consensus_direction=None`, `QUORUM_INSUFFICIENT`

### 11.3 Lifecycle Chamber

- `verdict_scope = "LIFECYCLE"`.
- In Phase 3: **does NOT execute in default config** (`lifecycle_enabled: false`). The code exists, is tested, but is gated by the config flag. Default runtime path skips it entirely.
- When explicitly enabled (`lifecycle_enabled: true`): receives zero experts (none exist in Phase 3). Always produces `expert_count=0`, `responding_count=0`, `admissibility="QUORUM_INSUFFICIENT"`, `consensus_direction=None`, `consensus_strength=0.0`.
- Tests exercise the lifecycle chamber by explicitly setting `lifecycle_enabled: true`. This proves the architecture handles both scopes without producing false emissions in default operation.
- No `EVT:JUDGE_CHAMBER_AGGREGATED_V1` with `verdict_scope="LIFECYCLE"` is emitted in default config. Operators will not see lifecycle chamber output unless they opt in.

### 11.4 Input Surfaces

**Primary inputs**:
1. In-memory `List[ExpertOutput]` collected during the `_on_decision_score()` provider loop in `backtest_plugin.py`.
2. **Solicited expert roster** `List[str]` — the `expert_id` values of all judge expert providers that were **scheduled to run** in this decision cycle, regardless of whether they produced output.

The collection mechanism:
1. In `_on_decision_score()`, before the provider loop, initialize `judge_expert_outputs: List[ExpertOutput] = []` AND `solicited_expert_ids: List[str] = []`.
2. For each provider where `cfg.judge_expert is not None`, append the expected `expert_id` to `solicited_expert_ids` **before** calling `_process_judge_expert_score()`. This captures the roster even if scoring fails.
3. In `_process_judge_expert_score()`, after constructing the `ExpertOutput` via bridge, return it to the caller and append to `judge_expert_outputs`.
4. If `_process_judge_expert_score()` raises or the expert is fail-closed (suppressed), the solicited roster still includes that expert, but `judge_expert_outputs` does not. The chamber sees the gap via `len(expected_expert_ids) > len(expert_outputs)` and accounts for it in `abstaining_count`.
5. After the provider loop completes, pass both `judge_expert_outputs` and `solicited_expert_ids` to `ChamberAggregator.aggregate()`.

This is in-memory, synchronous, deterministic. No event-bus round-tripping. The roster is the **external ground truth** — the chamber never has to guess how many experts were supposed to answer.

### 11.5 Admissibility Filtering

**File**: `alpha_search/judge/chamber/admissibility.py`

```
def evaluate_admissibility(
    expert_outputs: List[ExpertOutput],
    responding_count: int,
    expected_expert_count: int,
    *,
    min_quorum: int,
    max_staleness_ms: int,
    cycle_ts_ms: int,
) -> Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]
```

**Rules** (evaluated in order, first match wins):

| Rule | Condition | Result |
|---|---|---|
| R1: Quorum | `responding_count < min_quorum` | `QUORUM_INSUFFICIENT` |
| R2: Silent failure | `len(expert_outputs) < expected_expert_count` (at least one solicited expert produced no output) | `INADMISSIBLE` |
| R3: Freshness | Any `expert_output.ts_ms < cycle_ts_ms - max_staleness_ms` | `INADMISSIBLE` |
| R4: Scope mismatch | Any expert output has wrong verdict scope (should not happen if collection is correct, but defense-in-depth) | `INADMISSIBLE` |
| R5: Default | All checks pass | `ADMISSIBLE` |

**Config defaults**:
- `min_quorum: int = 1` — at least 1 responding expert required.
- `max_staleness_ms: int = 30000` — expert outputs older than 30s relative to cycle timestamp are stale.

**Duplicate/conflicting expert handling**: If the same `expert_id` appears more than once in the collected `expert_outputs`, the chamber declares the cycle `INADMISSIBLE`. Duplicate expert outputs indicate a config error (two providers wrapping the same expert type) or a collection bug — either way, the aggregate cannot be trusted. Admissibility rule R2.5 (inserted between R2 and R3):

| Rule | Condition | Result |
|---|---|---|
| R2.5: Duplicate | `len(set(eo.expert_id for eo in expert_outputs)) < len(expert_outputs)` | `INADMISSIBLE` |

This is a hard chamber-time rejection. Config-time validation is _also_ desirable (Phase 3 Package 3A should add a validator that rejects duplicate `expert_type` values across judge providers), but the chamber-time check is the fail-safe.

### 11.6 Aggregation Metrics

**Consensus Direction**:

Extract the `signal_direction` from each responding expert's output. Map to vote:
- `"LONG"` -> LONG vote
- `"SHORT"` -> SHORT vote
- `"NEUTRAL"` -> no directional vote (abstain from direction, but still counted as responding for quorum)

Tally:
- If `long_count > short_count` -> `consensus_direction = "LONG"`
- If `short_count > long_count` -> `consensus_direction = "SHORT"`
- If `long_count > 0 and long_count == short_count` -> `consensus_direction = "SPLIT"`
- If `long_count == 0 and short_count == 0` -> `consensus_direction = "NEUTRAL"`
- If `responding_count == 0` -> `consensus_direction = None`

**Consensus Strength**:

Mean of responding expert `confidence` values. If no responding experts, `consensus_strength = 0.0`.

```
consensus_strength = sum(eo.confidence for eo in responding) / len(responding) if responding else 0.0
```

This is a simple, auditable metric. Phase 4 may introduce weighted confidence or more sophisticated aggregation.

### 11.7 Output Surfaces

**Primary output**: `ChamberAggregate` Pydantic model (from frozen Phase 1 contracts).

**Event emission**: `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted on the event bus with `payload = chamber_aggregate.model_dump()`.

**JSONL logging**: One JSON line per `ChamberAggregate` appended to `{shadow_log.log_dir}/chamber_{symbol}_{date}.jsonl`.

**Shadow-only posture**: The chamber aggregate event is emitted for logging and replay. No consumer in `decision_making` or `execution_position` listens for it. The event is `status: experimental` in the verb registry. If `judge.mode == "off"`, no chamber runs. If `judge.mode == "shadow"`, chamber runs but output is logged only.

### 11.8 Shadow-Only Posture Enforcement

- Chamber code only executes when `self.config.judge` is not None AND `self.config.judge.mode == "shadow"`.
- `EVT:JUDGE_CHAMBER_AGGREGATED_V1` carries no execution semantics. It is a telemetry event.
- The verb registry notes it as experimental, contract-registration-only (Phase 1).
- Phase 3 does not widen mode admission beyond `{"off", "shadow"}`.

---

## 12. Phase 3 Runtime / Event Flow

### 12.1 Full Phase 3 Event Flow (per decision cycle)

```
CMD:PROCESS_STRATEGY
  └─> backtest_plugin._on_decision_score()
        ├─> Build solicited expert roster: solicited_expert_ids[]              [NEW Phase 3]
        ├─> [non-judge providers] -> _process_score() -> EVT:ALPHA_SCORE_CALCULATED    (unchanged)
        ├─> [judge expert providers] -> _process_judge_expert_score()
        │     ├─> expert.calculate_alpha()                                              (Layer 1)
        │     ├─> alpha_score_to_expert_output()                                        (Layer 2 bridge)
        │     ├─> EVT:JUDGE_EXPERT_PRODUCED_V1                                          (Phase 2)
        │     ├─> JSONL expert shadow log                                               (Phase 2)
        │     └─> return ExpertOutput to caller [NEW Phase 3]
        └─> [after provider loop, if solicited roster non-empty] [NEW Phase 3]
              ├─> ChamberAggregator.aggregate(entry_outputs, expected_expert_ids=roster)
              ├─> EVT:JUDGE_CHAMBER_AGGREGATED_V1                                       [NEW Phase 3]
              ├─> JSONL chamber shadow log                                              [NEW Phase 3]
              └─> (only if lifecycle_enabled: lifecycle chamber stub, empty list, expected=[] → QUORUM_INSUFFICIENT, logged) [NEW Phase 3]
```

### 12.2 What Is Emitted in Phase 3

| Event | Phase Added | Emitted? | Consumer |
|---|---|---|---|
| `EVT:ALPHA_SCORE_CALCULATED` | Pre-Phase 1 | Yes (non-judge only) | alpha_search internal |
| `EVT:JUDGE_EXPERT_PRODUCED_V1` | Phase 2 | Yes (per judge expert) | None (shadow log) |
| `EVT:JUDGE_CHAMBER_AGGREGATED_V1` | Phase 3 | Yes (per chamber cycle) | None (shadow log) |
| `EVT:JUDGE_ENTRY_VERDICT_V1` | Phase 1 (registered) | No (Phase 4) | — |
| `EVT:JUDGE_LIFECYCLE_VERDICT_V1` | Phase 1 (registered) | No (Phase 4) | — |
| `EVT:JUDGE_EVIDENCE_ASSEMBLED_V1` | Phase 1 (registered) | No (Phase 4) | — |

### 12.3 Replayability

All Phase 3 outputs are replayable:
- `ChamberAggregate` is a frozen Pydantic model with `model_dump() / model_validate()` round-trip proven by Phase 1 serialization tests.
- JSONL log files are append-only, date-partitioned, parseable.
- `chamber_id` is deterministic from `(verdict_scope, symbol, ts_ms)`.

### 12.4 Deferred to Phase 4

- `JudgeEvidenceEnvelope` assembly (requires `strategy_id`, `regime`, `provenance`).
- `JudgeVerdict` formation (requires envelope + verdict logic).
- `EVT:JUDGE_ENTRY_VERDICT_V1` / `EVT:JUDGE_LIFECYCLE_VERDICT_V1` emission.
- `hybrid_advisory` mode admission.
- LLM judge runtime.

---

## 13. Config Package

### 13.1 Canonical Config Path

`config/alpha_search.yaml` under the existing `judge:` block. No new config file.

### 13.2 New Config Models

**File**: `alpha_search/judge/config_models.py` (modify existing)

Add `ChamberConfig` and extend `JudgeCortexConfig`:

```python
class ChamberConfig(BaseModel):
    """Config for chamber aggregation."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_quorum: int = 1                    # Minimum responding experts for ADMISSIBLE
    max_staleness_ms: int = 30000          # Maximum expert output age in ms
    entry_enabled: bool = True             # Enable entry chamber
    lifecycle_enabled: bool = False        # Enable lifecycle chamber (stub in Phase 3)
```

Extend `JudgeCortexConfig`:

```python
class JudgeCortexConfig(BaseModel):
    # ... existing fields ...
    experts: Optional[JudgeExpertsConfig] = None
    shadow_log: Optional[JudgeShadowLogConfig] = None
    chamber: Optional[ChamberConfig] = None          # NEW Phase 3
```

### 13.3 YAML Config Addition

```yaml
judge:
  enabled: false
  mode: "off"
  experts: { ... }    # existing
  shadow_log: { ... } # existing
  chamber:            # NEW Phase 3
    min_quorum: 1
    max_staleness_ms: 30000
    entry_enabled: true
    lifecycle_enabled: false
```

### 13.4 Validation Rules

- `min_quorum >= 0`. Value of 0 means `QUORUM_INSUFFICIENT` is never returned (everything is admissible from quorum perspective).
- `max_staleness_ms > 0`.
- `entry_enabled` and `lifecycle_enabled` are independent booleans.
- `chamber` block is optional; if None, chambers do not run (backward compatible with Phase 2 config).

---

## 14. File-by-File Implementation Blueprint

### Package 3A: Chamber Config

**Entry gate**: Phase 2 complete, DEFECT-P2-01 fixed, current tests passing.

| Action | File | Change |
|---|---|---|
| Modify | `alpha_search/judge/config_models.py` | Add `ChamberConfig` class. Add `chamber: Optional[ChamberConfig] = None` to `JudgeCortexConfig`. |
| Modify | `config/alpha_search.yaml` | Add `chamber:` block under `judge:`. |
| Modify | `tests/domains/alpha_search/judge/test_config.py` | Add tests for `ChamberConfig` validation (min_quorum bounds, max_staleness_ms positive, backward compat when chamber is None). |

**Exit gate**: Config tests pass. `load_alpha_search_config("config/alpha_search.yaml")` succeeds with chamber block. Backward compat: succeeds without chamber block.

### Package 3B: Chamber Aggregation Module

**Entry gate**: Package 3A complete.

| Action | File | Change |
|---|---|---|
| Create | `alpha_search/judge/chamber/__init__.py` | Sub-package init. |
| Create | `alpha_search/judge/chamber/admissibility.py` | `evaluate_admissibility()` function. |
| Create | `alpha_search/judge/chamber/chamber_aggregator.py` | `ChamberAggregator` class with `aggregate()` method. |
| Create | `tests/domains/alpha_search/judge/chamber/__init__.py` | Test sub-package init. |
| Create | `tests/domains/alpha_search/judge/chamber/test_admissibility.py` | Tests for admissibility filter. |
| Create | `tests/domains/alpha_search/judge/chamber/test_chamber_aggregator.py` | Tests for aggregator logic. |

**Exit gate**: Chamber aggregator unit tests pass. Admissibility filter tests pass. `ChamberAggregate` output validates against frozen Pydantic contract.

### Package 3C: Orchestration Integration

**Entry gate**: Package 3B complete.

| Action | File | Change |
|---|---|---|
| Modify | `alpha_search/backtest_plugin.py` | (1) Import `ChamberAggregator` and `write_jsonl_shadow_log` (for chamber). (2) Modify `_process_judge_expert_score()` to return `ExpertOutput`. (3) In `_on_decision_score()`, build `solicited_expert_ids` roster from judge provider configs before calling scoring. (4) Collect returned `ExpertOutput` objects during provider loop. (5) After provider loop, if solicited roster non-empty and chamber config permits, run `ChamberAggregator.aggregate()` for entry scope with `expected_expert_ids=solicited_expert_ids`. (6) Emit `EVT:JUDGE_CHAMBER_AGGREGATED_V1`. (7) Write chamber JSONL log. (8) Only if `lifecycle_enabled`: run lifecycle chamber stub (empty outputs, empty roster → QUORUM_INSUFFICIENT, emit + log). |
| Modify | `alpha_search/judge/experts/expert_output_bridge.py` | Add `write_jsonl_chamber_log()` function (same pattern as `write_jsonl_shadow_log` but for chamber aggregates). |
| Modify | `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | Add chamber integration tests: verify `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted, verify chamber payload deserializes to `ChamberAggregate`, verify lifecycle stub produces `QUORUM_INSUFFICIENT` when explicitly enabled, verify lifecycle stub does NOT run when `lifecycle_enabled=false`, verify roster-truth accounting when expert is fail-closed. |

**Exit gate**: Integration tests prove chamber event emitted. Non-judge provider behavior unchanged. All existing tests still pass.

### Package 3D: Domain Dict + Registry (if needed)

**Entry gate**: Package 3C complete.

| Action | File | Change |
|---|---|---|
| Modify | `alpha_search/domain_dict.json` | Add chamber components, update exports to include `EVT:JUDGE_CHAMBER_AGGREGATED_V1` as emitted. |
| Verify | `verb_registry_v1.yaml` | `EVT:JUDGE_CHAMBER_AGGREGATED_V1` already registered (Phase 1). Update note from "contract registration only" to "Phase 3 shadow emission" if warranted. |

**Exit gate**: Registry tests pass. Domain dict valid.

### Package 3E: Full Test Suite

**Entry gate**: Packages 3A-3D complete.

| Action | File | Change |
|---|---|---|
| Run | All `tests/domains/alpha_search/judge/` | Full suite must pass. |
| Run | All `tests/domains/alpha_search/` | Regression suite must pass. |
| Verify | Test count | Target: ~280+ tests (234 existing + ~46 new chamber tests). |

**Exit gate**: All tests pass. 0 failures. 0 regressions.

### Package 3F: Report

**Entry gate**: Package 3E complete.

| Action | File | Change |
|---|---|---|
| Create | `docs/LLM_JUDGE/PHASE3_CHAMBER_SUBSTRATE_REPORT.md` | Completion report with evidence. |

**Exit gate**: Report produced with test evidence.

### Files Explicitly Untouched

| File | Reason |
|---|---|
| `main.py` | Frozen |
| `config_loader.py` | Frozen |
| Root `config_models.py` | Frozen |
| `decision_making/*` | Frozen |
| `execution_position/*` | Frozen |
| `quadratic_scoring_kernel.py` | Frozen |
| `judge/contracts.py` | Phase 1 frozen (no contract changes) |
| `judge/schemas/*` | Phase 1 frozen (no schema changes) |
| `judge/experts/signal_weights_expert.py` | Phase 2 frozen (Layer 1 pure scoring unchanged) |
| `judge/experts/feature_neutrals_expert.py` | Phase 2 frozen (Layer 1 pure scoring unchanged) |
| `aurora.yaml` | No judge interaction |

---

## 15. Validation Blueprint

### 15.1 Test Matrix

| Test File | Tests (est.) | Purpose |
|---|---|---|
| `tests/.../judge/test_config.py` | +6 | ChamberConfig validation, backward compat |
| `tests/.../judge/chamber/__init__.py` | 0 | Package init |
| `tests/.../judge/chamber/test_admissibility.py` | ~14 | Quorum check, freshness filter, scope mismatch, silent failure detection, duplicate expert rejection, default admissible |
| `tests/.../judge/chamber/test_chamber_aggregator.py` | ~20 | Entry chamber: 2 LONG, 2 SHORT, mixed, UNKNOWN handling, empty input, single expert, SPLIT consensus, confidence mean, lifecycle stub quorum_insufficient, roster-vs-outputs gap (solicited but missing), duplicate expert_id INADMISSIBLE |
| `tests/.../judge/test_expert_provider_integration.py` | +6 | Chamber event emitted, chamber payload valid, lifecycle stub, non-judge unaffected, JSONL chamber log |
| Existing judge tests | 234 | Regression |
| Existing alpha_search tests | 268 | Regression |

**Target new test count**: ~46 new tests.
**Target total test count**: ~280+ (234 + 46).

### 15.2 Proof Artifacts

1. `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted with valid `ChamberAggregate` payload.
2. `ChamberAggregate` payload round-trips through `model_dump() / model_validate()`.
3. Entry chamber with 2 responding experts produces `admissibility="ADMISSIBLE"`, correct `consensus_direction` and `consensus_strength`.
4. Entry chamber with 0 responding experts produces `QUORUM_INSUFFICIENT`.
5. Lifecycle chamber with 0 experts produces `QUORUM_INSUFFICIENT`.
6. Stale expert output triggers `INADMISSIBLE`.
7. JSONL chamber log file written when `shadow_log.enabled`.
8. `EVT:ALPHA_SCORE_CALCULATED` still emitted for non-judge providers (regression).
9. No `decision_making` or `execution_position` contamination.
10. **Roster truth**: When 2 experts solicited but only 1 returns output, `expert_count=2`, `abstaining_count>=1`, and admissibility is `INADMISSIBLE` (silent failure rule R2).
11. **Duplicate rejection**: When same `expert_id` appears twice, admissibility is `INADMISSIBLE` (rule R2.5).

### 15.3 Acceptance Gates

| Gate | Criterion |
|---|---|
| G-T1 | All new chamber tests pass |
| G-T2 | All existing 234 judge tests pass (0 regressions) |
| G-T3 | All existing 268 alpha_search tests pass (0 regressions) |
| G-T4 | Chamber config loads from YAML |
| G-T5 | Chamber config absent = backward compatible |
| G-T6 | `grep -r "judge" decision_making/` returns 0 semantic hits |
| G-T7 | `grep -r "judge" execution_position/` returns 0 semantic hits |

---

## 16. Risks

### R1: Orchestration Complexity in backtest_plugin.py

**Cause**: Adding chamber orchestration to `_on_decision_score()` increases the method's responsibility.
**Mechanism**: The method already handles cache lookup, provider iteration, feature normalization, scoring, and virtual trading. Adding chamber collection + aggregation adds another concern.
**Effect**: Method becomes harder to maintain.
**Operational severity**: LOW.
**Mitigation**: Keep chamber orchestration in a clearly delineated section after the provider loop. No interleaving with existing logic. Consider extracting a `_process_judge_chamber()` helper method.

### R2: Expert Output Collection Across Providers

**Cause**: `_process_judge_expert_score()` currently returns None (void). Phase 3 needs it to return `ExpertOutput`.
**Mechanism**: Changing the return type from None to `Optional[ExpertOutput]` requires modifying the call site in `_on_decision_score()`.
**Effect**: Narrow, bounded change within `_on_decision_score()`.
**Operational severity**: LOW.
**Mitigation**: Return type change is additive. Callers that discard the return value are unaffected. Single new call site collects the return.

### R3: Chamber Config Backward Compatibility

**Cause**: Adding `chamber: Optional[ChamberConfig] = None` to `JudgeCortexConfig`.
**Mechanism**: Existing YAML without `chamber:` key must still load correctly.
**Effect**: If `Optional` default is not None, existing configs break.
**Operational severity**: LOW (would be caught by existing config tests).
**Mitigation**: Default is `None`. `JudgeCortexConfig` already has `extra="forbid"` so the new field must either be absent or valid. `Optional[ChamberConfig] = None` is safe.

### R4: Lifecycle Chamber False Promise

**Cause**: Phase 3 implements a lifecycle chamber stub that always returns `QUORUM_INSUFFICIENT`.
**Mechanism**: No lifecycle experts exist. The stub exists to prove architecture works.
**Effect**: Risk of confusion if someone reads logs and sees lifecycle chamber results.
**Operational severity**: LOW.
**Mitigation**: Lifecycle chamber **does not execute by default** (`lifecycle_enabled: false` in Phase 3 config). No lifecycle events are emitted unless an operator explicitly sets `lifecycle_enabled: true`. When enabled, the `chamber_id` prefix `lifecycle_` and the `QUORUM_INSUFFICIENT` admissibility clearly identify it as a stub. Tests exercise the stub with explicit opt-in, not via default flow.

---

## 17. Phase-3 Package Order

| Package | Description | Entry Gate | Exit Gate |
|---|---|---|---|
| **3A** | Chamber config models + YAML | Phase 2 complete + DEFECT-P2-01 fixed + tests passing | Config tests pass, YAML loads |
| **3B** | Chamber aggregation module + admissibility | 3A complete | Unit tests pass, ChamberAggregate validates |
| **3C** | Orchestration integration in backtest_plugin | 3B complete | Integration tests pass, events emitted, JSONL written |
| **3D** | Domain dict + registry note update | 3C complete | Registry tests pass |
| **3E** | Full test suite validation | 3A-3D complete | All ~276+ tests pass, 0 regressions |
| **3F** | Phase 3 report | 3E complete | Report with evidence |

---

## 18. Done Criteria

### 18.1 Phase 3 Planning Complete

This document is the planning SSOT. Planning is complete when:
- [x] Chamber placement frozen (Section 10)
- [x] Chamber input/output path concrete (Section 11.4, 11.7)
- [x] Admissibility filtering concrete (Section 11.5)
- [x] Aggregation metrics concrete (Section 11.6)
- [x] DEFECT-P2-01 dependency resolved (Section 9, Gate G3)
- [x] Test matrix concrete (Section 15)
- [x] Package order concrete (Section 17)
- [x] File-by-file scope concrete (Section 14)

### 18.2 Phase 3 Implementation Complete (for later coding agent)

Phase 3 is done when ALL of the following are true:
- [ ] `ChamberConfig` added to `config_models.py`
- [ ] `config/alpha_search.yaml` updated with `chamber:` block
- [ ] `chamber/__init__.py` exists
- [ ] `chamber/admissibility.py` implements `evaluate_admissibility()`
- [ ] `chamber/chamber_aggregator.py` implements `ChamberAggregator` with `aggregate()`
- [ ] `backtest_plugin.py` collects judge expert outputs and runs chamber aggregation
- [ ] `backtest_plugin.py` builds solicited expert roster before scoring and passes it to chamber
- [ ] `EVT:JUDGE_CHAMBER_AGGREGATED_V1` emitted with valid ChamberAggregate payload
- [ ] Chamber `expert_count` derived from solicited roster, not returned outputs count
- [ ] Silent expert failure (solicited but no output) yields `INADMISSIBLE`
- [ ] Duplicate `expert_id` in outputs yields `INADMISSIBLE`
- [ ] JSONL chamber log written
- [ ] Lifecycle chamber stub produces `QUORUM_INSUFFICIENT` when explicitly enabled
- [ ] Lifecycle chamber stub does NOT execute when `lifecycle_enabled=false` (default)
- [ ] All new chamber tests pass (~46 tests)
- [ ] All existing 234 judge tests pass (0 regressions)
- [ ] All existing 268 alpha_search tests pass (0 regressions)
- [ ] No `decision_making` or `execution_position` contamination
- [ ] Report produced

---

## 19. Final Recommended Next Coding Task

**Task**: Implement Phase 3 Package 3A — add `ChamberConfig` to `alpha_search/judge/config_models.py`, add the `chamber:` YAML block to `config/alpha_search.yaml`, extend `JudgeCortexConfig` with `chamber: Optional[ChamberConfig] = None`, and add 6 config validation tests to `test_config.py`. Verify backward compatibility with existing config loading.

This is the narrowest first step that unlocks Packages 3B-3F.

---

## 20. Blueprint Tightening Changelog

### Revision 2026-04-15 — Owner Review (3 fixes applied)

**Fix 1 (CRITICAL): Chamber accounting uses solicited expert roster as ground truth**

- **Problem**: Original plan counted `expert_count` from returned `ExpertOutput` list only. If a solicited expert crashed, was fail-closed suppressed, or never reached the bridge, the chamber silently undercounted — making quorum artificially easier and admissibility artificially better. Direct violation of fail-closed logic.
- **Resolution**: `aggregate()` now accepts `expected_expert_ids: List[str]` (the roster of experts solicited in this cycle). `expert_count = len(expected_expert_ids)`. `abstaining_count = expert_count - responding_count`. New admissibility rule R2 detects `len(expert_outputs) < expected_expert_count` as `INADMISSIBLE`. Integration layer builds the roster before scoring and passes it to the chamber regardless of scoring outcomes.
- **Sections modified**: 5 (F11), 6 (I7), 11.1, 11.4, 11.5, 12.1, 14 (3C), 15.1, 15.2, 18.2.

**Fix 2 (REQUIRED): Lifecycle stub ambiguity resolved**

- **Problem**: Document simultaneously stated lifecycle stub "exists and runs as part of Phase 3 flow" and "`lifecycle_enabled: false` by default". Contradictory — either it runs by default or it doesn't.
- **Resolution**: **Lifecycle stub does NOT execute in default config.** `lifecycle_enabled: false` means no lifecycle chamber runs, no lifecycle events emitted, no lifecycle JSONL written. Tests exercise the stub by explicitly setting `lifecycle_enabled: true`. The code exists and is tested; the default runtime path skips it.
- **Sections modified**: 11.3, 12.1, 14 (3C), 15.1 (integration tests), 16 (R4), 18.2.

**Fix 3 (DESIRED): Duplicate expert policy hardened**

- **Problem**: Original plan included duplicate `expert_id` outputs in aggregation without penalty. A config error creating two providers with the same expert type could skew consensus artificially.
- **Resolution**: Admissibility rule R2.5 rejects as `INADMISSIBLE` when `len(set(expert_ids)) < len(expert_outputs)`. Additionally, Package 3A config validation should reject duplicate `expert_type` across judge providers at config load time. Chamber-time check is the fail-safe for runtime paths that bypass config validation.
- **Sections modified**: 11.5, 15.1, 15.2, 18.2.
