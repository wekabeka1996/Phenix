# LLM Judge: Bicameral Policy Cortex Concept v1

**Date**: 2026-04-13
**Artifact type**: Governing concept authority
**Artifact status**: Frozen for Phase 1 implementation
**Scope**: Defines the semantic vocabulary, operational modes, ownership constraints, and substrate direction for the LLM Judge initiative.

---

## 1. Purpose

The LLM Judge is a **policy evaluation layer** that provides typed, bounded, timestamped verdicts on trading decisions. It operates as a **bicameral policy cortex**: multiple expert perspectives evaluate evidence independently, their outputs are aggregated in a chamber, and a final verdict is produced.

The LLM Judge is **not** an execution truth owner. It does not directly open, close, or modify positions. It produces advisory or guarded-gate verdicts that downstream systems may consult or enforce, depending on the operational mode.

---

## 2. Entry Verdict Vocabulary

The following entry verdicts are the canonical vocabulary for evaluating proposed trade entries:

| Verdict | Semantics |
|---|---|
| `OPEN_LONG` | Judge recommends long entry |
| `OPEN_SHORT` | Judge recommends short entry |
| `NO_ENTRY` | Judge evaluated and found no actionable signal |
| `SUPPRESS` | Judge actively suppresses a proposed entry |
| `UNKNOWN` | Judge could not form a verdict (stale evidence, quorum failure, LLM timeout) |

Entry verdicts are a distinct contract family. They must not be collapsed into a shared generic enum with lifecycle verdicts.

---

## 3. Lifecycle Verdict Vocabulary

The following lifecycle verdicts are the canonical vocabulary for evaluating open position management:

| Verdict | Semantics |
|---|---|
| `HOLD` | Judge recommends holding current position |
| `PROTECT` | Judge recommends tightening protection (SL adjustment) |
| `EXIT` | Judge recommends closing position |
| `SUPPRESS` | Judge suppresses a proposed lifecycle action |
| `UNKNOWN` | Judge could not form a verdict |

Lifecycle verdicts are a distinct contract family. They must not be collapsed into a shared generic enum with entry verdicts.

---

## 4. Operational Mode Vocabulary

The LLM Judge operates in one of the following modes:

| Mode | Semantics | Phase |
|---|---|---|
| `off` | No evaluation. Contracts exist but no runtime behavior. | Phase 1 |
| `shadow` | Evaluate and log verdicts. Never applied to pipeline. | Phase 2-3 |
| `hybrid_advisory` | Verdicts emitted as advisory signals. Decision_making may consult but is not bound. | Phase 4+ |
| `guarded_entry_authority` | Entry verdicts can suppress signals through StrategyGateway gate. Guarded by symbol/strategy allowlists. | Phase 5+ |
| `guarded_lifecycle_authority` | Lifecycle verdicts can recommend PROTECT/EXIT. Guarded. | Phase 6+ |

The full mode vocabulary must be preserved in the type surface at all times. Runtime admission is phase-gated: Phase 1 admits only `off`.

---

## 5. Substrate Direction

The LLM Judge is **alpha_search-aligned**. Judge contracts, config, and artifacts live under the `alpha_search` domain, following the established shadow substrate pattern. This avoids creating a new top-level domain for a contracts-only Phase 1.

---

## 6. Ownership Constraints (Concept Laws)

1. **LLM is policy judge only**: The LLM never owns execution truth. No direct LLM-to-exchange path exists from Judge contracts.
2. **Additive-only**: Judge rollout must not modify, narrow, or reinterpret existing owner contracts.
3. **Contract-first**: All Judge behavior must be preceded by committed, validated, schema-backed contracts.
4. **Replayability**: All evidence and verdicts must be serializable, timestamped, and replayable.
5. **Shadow-first**: Runtime behavior is always introduced in shadow mode before advisory or authority modes.
6. **No direct LLM-to-exchange path**: Judge verdicts are advisory or guarded-gate. They never directly produce execution commands.
7. **No silent legacy math revival**: Judge must not resurrect deprecated scoring or signal logic.
8. **No mixed mega-contracts**: Entry verdicts and lifecycle verdicts remain separate contract families.
9. **Typed, bounded, timestamped evidence**: Evidence envelopes must be typed, bounded (no raw feature embedding), timestamped, and serializable.

---

## 7. Contract Families

Phase 1 defines the following contract shapes:

| Contract | Purpose |
|---|---|
| `ExpertOutput` | Typed output from one expert perspective |
| `ChamberAggregate` | Aggregation of all expert outputs for one evaluation cycle |
| `JudgeEvidenceEnvelope` | Typed, bounded, timestamped evidence package |
| `JudgeVerdict` | Final judge policy verdict |
| `PositionContextSnapshot` | Current position state for lifecycle evaluation |
| `EnvelopeProvenance` | Traceability metadata for evidence assembly |

---

## 8. Expert Architecture

Experts are independent evaluation modules that produce typed `ExpertOutput` records. Each expert:

- Has a unique `expert_id` and `expert_version`
- Evaluates either entry or lifecycle scope (not both simultaneously)
- Produces a confidence score in [0.0, 1.0]
- Must provide at least one reasoning item
- Fails closed: failure produces `UNKNOWN` with confidence 0.0

The first expert subset is a Phase 2 decision. Phase 1 defines the contract shapes only.

---

## 9. Chamber Architecture

The chamber aggregates expert outputs for a single evaluation cycle:

- Tracks expert count, responding count, and abstaining count
- Determines consensus direction and strength
- Produces an admissibility assessment (ADMISSIBLE, INADMISSIBLE, QUORUM_INSUFFICIENT)
- Preserves all individual expert outputs for replay

---

## 10. Evidence Envelope Architecture

The evidence envelope packages all inputs needed to replay a verdict:

- Links to the chamber aggregate
- Carries bounded references to features (not embedded raw data)
- Includes position context for lifecycle evaluation
- Includes freshness deadline for staleness detection
- Includes provenance for traceability
- Does NOT duplicate transport-envelope metadata already provided by the Message protocol

---

## 11. Verdict Architecture

The final verdict:

- Links to both the evidence envelope and the chamber aggregate
- Carries verdict-scope-consistent XOR semantics (entry OR lifecycle, never both)
- Records whether the verdict was applied and under which authority mode
- Preserves reasoning and dissent information
- Fails closed: failure produces UNKNOWN with confidence 0.0, applied=False

---

## 12. Phase Rollout

| Phase | Scope |
|---|---|
| Phase 1 | Contracts, schemas, verb registry, config models. No runtime. |
| Phase 2 | Shadow evaluation runtime. First expert implementations. |
| Phase 3 | Shadow telemetry integration. Verdict logging. |
| Phase 4 | Hybrid advisory mode. Decision_making consultation. |
| Phase 5 | Guarded entry authority. StrategyGateway gate insertion. |
| Phase 6 | Guarded lifecycle authority. Position management verdicts. |
