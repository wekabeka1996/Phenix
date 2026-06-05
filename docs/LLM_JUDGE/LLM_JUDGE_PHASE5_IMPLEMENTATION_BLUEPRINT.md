# LLM Judge - Phase 5 Implementation Blueprint
# Shadow Economic Simulator

**Document authority:** Single SSOT for Phase 5 planning and implementation handoff.
**Status:** FINAL -- prior draft rejected and replaced.
**Date:** 2026-04-16
**Branch anchor:** Phenix_v2

**Primary governing authorities**
- docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md
- docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md
- docs/LLM_JUDGE/PHASE4_EVIDENCE_VERDICT_SHADOW_REPORT.md
- docs/LLM_JUDGE/LLM_JUDGE_PHASE4_CODE_AUDIT.md
- docs/LLM_JUDGE/PHASE4_ACTIVATION_TIMESTAMP_ALIGNMENT_FIX_REPORT.md

**Frozen prerequisite authorities**
- docs/LLM_JUDGE/LLM_JUDGE_PHASE1_IMPLEMENTATION_BLUEPRINT.md
- docs/LLM_JUDGE/PHASE1_CONTRACT_PACKAGE_REPORT.md
- docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md
- docs/LLM_JUDGE/PHASE2_LEGACY_EXPERT_REVIVAL_REPORT.md
- docs/LLM_JUDGE/PHASE2_DEFECT_P2_01_FIX_REPORT.md
- docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md
- docs/LLM_JUDGE/PHASE3_CHAMBER_SUBSTRATE_REPORT.md

---

## 1. Executive Verdict

**GO - Phase 5 Shadow Economic Simulator may proceed.**

**Phase 5 is Shadow Economic Simulator.**

**Phase 5 does not widen runtime mode admission.**

Phase 5 is a replay-based offline analysis tool that consumes judge artifacts (verdicts, evidence envelopes, chamber aggregates) from Phases 1–4 and produces evidence for Phase 6 promotion review. The simulator does not run at live runtime, does not modify production code paths, does not introduce new operational modes, and does not bind decision_making to any judge consultation.

The simulator's purpose is to answer:
- Did judge verdicts correlate with trade outcomes?
- What fee and slippage models best explain disagreement?
- Per-expert accuracy breakdown.
- Which cycles should inform Phase 6 guarded authority calibration?

Frozen Phase 5 decision:

1. Build an offline Shadow Economic Simulator in a new module `apps/reference/domains/alpha_search/judge/simulator/`.
2. Consume already-produced judge artifacts from Phase 1-4 replay data: `JudgeVerdict`, `JudgeEvidenceEnvelope`, `ChamberAggregate`, `ExpertOutput`.
3. Accept externally-supplied trade outcome data (fills, fees, slippage) and position exit prices.
4. Do **not** modify any runtime code paths: `decision_making`, `execution_position`, `main.py`, `config_loader.py`, `contracts.py`.
5. Do **not** admit new operational modes or widen `JudgeCortexConfig` admission.
6. Produce calibration datasets and summary statistics to disk in JSON format.
7. Operator runs simulator offline after backtest or live trading session.
8. Simulator output informs Phase 6 promotion review.

This blueprint does **not** reopen any Phase 1-4 contract, placement, or ownership decision.

---

## 2. Why the Previous Drafts Were Rejected

The prior Phase 5 draft made a **fundamental category error**: it confused **operational modes** (off, shadow, hybrid_advisory, guarded_entry_authority, guarded_lifecycle_authority) with **rollout phases** (Phase 1, 2, 3, 4, 5, 6...).

Specific rejected mistakes in earlier drafts:

1. **Mode-Phase Confusion**: The earlier draft claimed "Phase 5 is the first bounded step to admit `hybrid_advisory` mode." This is wrong. Operational mode admission is a **runtime responsibility**. Phase 5 is a **rollout phase** responsible for delivering a specific capability (simulator). Modes are orthogonal to phases.

2. **Wrong Semantic Tie**: The earlier draft said "Phase 5 is when we admit `hybrid_advisory` and consult in `decision_making`." This conflates the rollout plan with an operational mode commitment. The concept allows `hybrid_advisory` to be admitted at any phase; this repo decides **when**, not the concept. Phase 5 **does not** make that admission.

3. **Premature Advisory Consumption**: The earlier draft proposed inserting a new `judge_advisory_bridge` into `decision_making` and emitting `EVT:JUDGE_ADVISORY_CONSULTED_V1` at live runtime. This is **not** Phase 5 work. This is deferred as a future advisory/promotion track beyond Phase 5.

4. **Contract Drift**: The earlier draft widened `JudgeCortexConfig` admission to include `hybrid_advisory` without evidence from Phase 5 simulator output. This put the cart before the horse.

5. **Ownership Violation**: The earlier draft attempted to modify `decision_making` to consume verdicts, crossing the ownership boundary without a validated Phase 5 simulator foundation. Phase 5 is about **analysis**, not **consumption**.

**The corrected approach**: Phase 5 is **replay-only**, **offline**, **evidence-gathering** work. It produces no runtime code. It informs Phase 6 decisions. Separation of concerns is restored.

---

## 3. Authority Model

### 3.1 Concept Operational Modes vs. Rollout Phases

The governing concept defines **five operational modes** that can be admitted at runtime:

| Mode | Semantics | Earliest Possible Phase |
|------|-----------|------------------------|
| `off` | No judge evaluation at runtime. | Phase 1 |
| `shadow` | Judge runs, logs verdicts, is not consumed. | Phase 2 |
| `hybrid_advisory` | Verdicts may be consulted by decision_making (not bound). | Phase 5+ (deferred decision) |
| `guarded_entry_authority` | Entry verdicts enforce suppression via StrategyGateway. | Phase 6+ |
| `guarded_lifecycle_authority` | Lifecycle verdicts recommend PROTECT/EXIT. | Phase 7+ |

**Operational modes describe runtime behavior.**

The repository **rollout phases** describe **what capability is delivered and validated**:

| Phase | Rollout Capability |
|-------|-------------------|
| Phase 1 | Contract definitions and schema foundation. |
| Phase 2 | Verdict production with legacy expert revival. |
| Phase 3 | Chamber aggregation and admissibility logic. |
| Phase 4 | Evidence envelope + deterministic verdict synthesis. |
| Phase 5 | **Shadow Economic Simulator** (offline analysis tool). |
| Phase 6 | **Validation and Promotion Review** (guided by Phase 5 evidence). |

**Rollout phases are independent of mode admission decisions.**

### 3.2 The Key Insight

A phase can **deliver** a capability without **admitting a mode**. Phase 5 delivers the simulator. Whether `hybrid_advisory` is ever admitted is a **Phase 6 decision**, informed by simulator evidence. They are separate.

Phases 1-4 shipped with `shadow` mode admitted (the only option). Phase 5 delivers simulator evidence. Phase 6 **reviews** that evidence and **decides** whether to admit `hybrid_advisory` or other modes. The review is informed by simulator outputs.

### 3.3 Frozen Repo Truth from Phases 1-4

- Phase 1 froze contracts, schemas, vocabulary, and placement.
- Phase 2 admitted only `off` and `shadow`; revived legacy experts.
- Phase 3 added chamber aggregation and admissibility; kept shadow posture.
- Phase 4 added evidence envelopes and deterministic verdict synthesis; stayed shadow-only.

**The shipped repository at end of Phase 4 admits only `off` and `shadow` at runtime.** No other mode is active.

### 3.4 Phase 5 Placement in the Concept

The concept does not mandate when `hybrid_advisory` is admitted. This repo's Phase 5 **does not admit it**. Phase 5 is analysis-only. Phase 6 is the promotion review gate. If Phase 6 review succeeds, Phase 6 or later may admit `hybrid_advisory` (or skip it entirely and move to guarded authority).

---

## 4. Fixed Inputs from Phases 1–4

The following are frozen inputs and must not be reopened during Phase 5 implementation:

| ID | Frozen Input | Source |
|----|--------------|--------|
| F1 | Judge contract surface stays under `apps/reference/domains/alpha_search/judge/contracts.py` | Phase 1 |
| F2 | `CortexMode` vocabulary includes `hybrid_advisory` and guarded modes but runtime admission is freeze-frozen at `off` and `shadow` | Phase 1 + Phase 4 |
| F3 | `EntryVerdict` and `LifecycleVerdict` vocabularies are frozen | Phase 1 |
| F4 | Judge code remains nested under `alpha_search/judge/`; no new top-level policy domain introduced | Phase 1 |
| F5 | Only revived experts `signal_weights_expert` and `feature_neutrals_expert` exist | Phase 2 |
| F6 | Expert output bridge and JSONL logging seam remain Phase 2 truth | Phase 2 |
| F7 | Chamber aggregation, solicited-roster truth, and admissibility rules remain Phase 3 truth | Phase 3 |
| F8 | Evidence envelope assembly remains the Phase 4 seam between chamber and verdict | Phase 4 |
| F9 | Verdict synthesis remains deterministic; no LLM runtime calls are added in Phase 4 or Phase 5 | Phase 4 |
| F10 | Event chain remains `EXPERT -> CHAMBER -> ENVELOPE -> VERDICT` | Phase 4 |
| F11 | `JudgeVerdict` carries `authority_mode` and `applied` fields | Phase 1 |
| F12 | `applied=False` is contract-enforced for `off` and `shadow` modes | Phase 4 |
| F13 | Phase 4 timestamp alignment fix aligned expert/event/verdict timestamps to cycle `bar_close_ts` | Phase 4 correction |
| F14 | Default repo behavior is fail-safe: `judge.enabled=false` and `judge.mode="off"` | Phase 4 |
| F15 | Lifecycle verdict production is structurally present but operationally non-authoritative and non-consumed | Phase 4 |
| F16 | Disabled experts are not solicited and remain inert | Phase 3 |
| F17 | `verdict` config remains strict subset of enabled `chamber` scope | Phase 4 |
| F18 | No downstream consumer exists in runtime code; all consumption is deferred beyond Phase 5 | Repo truth |
| F19 | `decision_making` is judge-blind; no imports from alpha_search judge exist | Phase 1 ownership rule |
| F20 | `execution_position` is judge-blind; no imports from judge exist | Phase 1 ownership rule |

---

## 5. Corrected Phase 5 Final Scope

### 5.1 In Scope

| ID | Item | Purpose |
|----|------|---------|
| S1 | Shadow Economic Simulator module | Offline verdict-outcome analysis tool |
| S2 | Simulator: verdict input loading | Read already-produced judge artifacts from replay logs |
| S3 | Simulator: outcome input loading | Read external trade fills, fees, slippage, exit prices |
| S4 | Simulator: outcome matching | Correlate verdicts to actual trade outcomes |
| S5 | Simulator: fee modeling | Estimate fee impact on verdict-outcome correlation |
| S6 | Simulator: slippage modeling | Estimate slippage impact on verdict-outcome correlation |
| S7 | Simulator: hold vs. no-hold analysis | Compare positions held per verdict to counterfactual no-hold |
| S8 | Simulator: disagreement diagnostics | Identify cycles where experts disagreed; correlate with outcome drift |
| S9 | Simulator: per-expert accuracy breakdown | Track accuracy, precision, recall per expert across cycles |
| S10 | Simulator: calibration dataset production | Generate JSON datasets for Phase 6 promotion review |
| S11 | Simulator: summary statistics | Produce summary reports (JSON) of simulator findings |
| S12 | Simulator: config schema | Define simulator input config (parameters, thresholds, output paths) |
| S13 | Simulator: CLI harness | Allow operator to run simulator offline on replay data |
| S14 | Simulator: test harness | Prove simulator correctness on fixture data |
| S15 | Simulator: documentation | Define simulator contract and usage |

### 5.2 Out of Scope

| ID | Excluded Item | Reason |
|----|---------------|--------|
| X1 | `hybrid_advisory` runtime admission | Deferred to Phase 6+ decision |
| X2 | `guarded_entry_authority` runtime admission | Out of scope; Phase 6+ |
| X3 | `guarded_lifecycle_authority` runtime admission | Out of scope; Phase 6+ |
| X4 | `decision_making` bridge or consultation | Deferred to Phase 6+ if Phase 5 evidence supports it |
| X5 | Any runtime event (e.g., `EVT:JUDGE_ADVISORY_CONSULTED_V1`) | Simulator produces offline artifacts only; no runtime events |
| X6 | Any mutation of `StrategyGateway` | Out of scope; execution boundary untouched |
| X7 | Any mutation of `EVT:STRATEGY_SIGNAL_PRODUCED` payload | Signal surface frozen |
| X8 | Any mutation of `TRADE_INTENT_PROPOSED` or `trade_intent_v1.json` | Execution boundary frozen |
| X9 | Any change under `execution_position/` | Out of scope by ownership law |
| X10 | Any change to `main.py` or `config_loader.py` | No runtime code changes |
| X11 | Any change to `contracts.py` | Contracts frozen from Phase 1 |
| X12 | Any new LLM runtime synthesis | Simulator is offline analysis only; no runtime LLM calls |
| X13 | Any mutation of `JudgeCortexConfig` runtime admission | Modes remain `off` and `shadow` only through Phase 5 |
| X14 | Any signal-score mutation in alpha or kernel logic | Read-only analysis |
| X15 | Any attempt to reopen Phase 1-4 placement or contract decisions | Forbidden |

---

## 6. FACTS

| ID | Fact | Repo Anchor |
|----|------|-------------|
| T1 | `JudgeCortexConfig` currently admits only `off` and `shadow` | `judge/config_models.py` |
| T2 | `JudgeVerdict` already carries `authority_mode`, `applied`, `entry_verdict`, `confidence`, `dissent`, `reasoning` | `judge/contracts.py` |
| T3 | Phase 4 verdicts are serialized to JSONL in `logs/` during replay | `backtest_plugin.py` and log structure |
| T4 | Phase 4 evidence envelopes carry `bar_close_ts`, `position_context`, `chamber_id` | `judge/contracts.py` |
| T5 | Strategy signals from alpha_search carry `strategy_id`, `symbol`, `tf_sec`, `bar_close_ts` | `aurora_decision.py` |
| T6 | Trade fills and positions are logged separately from judge artifacts | `execution_position/` logs and trade logs |
| T7 | Backtest engine produces deterministic position exit prices and fees | backtest sim data |
| T8 | No operator ever manually consumes judge verdicts at live runtime today | Repo truth; Phase 4 is shadow-only |
| T9 | The concept defines `hybrid_advisory` semantics but does not mandate Phase 5 admission | `LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md` |
| T10 | Phase 5 simulator is a new tool; it does not modify existing producers or consumers | Phase 1-4 code is immutable for Phase 5 |
| T11 | Simulator inputs are **replay data** (logs, JSONL) not live runtime streams | Offline-only requirement |
| T12 | Simulator outputs are JSON files and CSV calibration datasets | Offline artifacts |

---

## 7. INFERENCES

| ID | Inference | Basis |
|----|-----------|-------|
| I1 | The simulator must load `JudgeVerdict` records from replay JSONL logs, not from live runtime | T3 + offline-only mandate |
| I2 | Verdict-signal correlation requires matching on `(strategy_id, symbol, tf_sec, bar_close_ts)` from both sides | T4 + T5 |
| I3 | Outcome matching requires externally-supplied trade fill and position data because judge does not own execution truth | F19 + ownership rule |
| I4 | Per-expert accuracy requires disaggregating `ChamberAggregate` to individual `ExpertOutput` records | `contracts.py` model structure |
| I5 | Disagreement diagnostics highlight cycles where expert confidence distributions were non-uniform | chamber aggregator logic |
| I6 | Fee and slippage modeling requires counterfactual analysis: verdict-outcome with vs. without fees | simulator design necessity |
| I7 | Calibration dataset production means generating labeled examples for Phase 6 guarded authority gate tuning | Phase 6 dependency |
| I8 | Phase 6 will use calibration datasets to decide if `hybrid_advisory` or guarded authority should ever be admitted | promotion review gate |

---

## 8. ASSUMPTIONS

| ID | Assumption | Risk if Wrong | Mitigation |
|----|------------|---------------|------------|
| A1 | Replay logs are available for simulator input | Simulator cannot run if logs are missing | Document required replay log format; fail loudly if logs are incomplete |
| A2 | Trade fill and exit data can be externally supplied in a deterministic format | Outcome matching fails if format is ad-hoc | Define strict schema for outcome input (JSON or CSV) |
| A3 | Cycles are uniquely identifiable by `(strategy_id, symbol, tf_sec, bar_close_ts)` across verdict and signal logs | Incorrect correlation if ID is ambiguous | Validate uniqueness constraint during simulator init |
| A4 | Fee and slippage are modeled as post-hoc adjustments, not live during backtest | Simulator may double-count costs if backtest already applied them | Clearly document whether to apply fees additively or use backtest-supplied costs as-is |
| A5 | Per-expert accuracy can be computed from `ChamberAggregate.expert_outputs` list | Attribution fails if expert outputs are not preserved | Verify that `ChamberAggregate` always carries full expert roster |

---

## 9. UNKNOWNS

There are **no blocking architectural unknowns** for Phase 5.

Implementation will discover:

- exact JSON schema for outcome input files (but schema contract is frozen by A2);
- exact CLI argument parsing for simulator config (but CLI surface is frozen by design);
- exact internal cache shape for verdict/signal/outcome tuples (local detail, non-contractual).

If implementation encounters a need to modify judge contracts, admit new runtime modes, or change decision_making ownership, that is **not** an unknown; it is **out of scope** and must stop for review.

---

## 10. Phase 5 Prerequisite Gates

All gates below must be verified at coding start or are already closed.

| Gate | Condition | Status |
|------|-----------|--------|
| G1 | Phase 1 contracts and schemas are frozen | CLOSED |
| G2 | Phase 2 expert revival is complete and corrected | CLOSED |
| G3 | Phase 3 chamber substrate is complete | CLOSED |
| G4 | Phase 4 envelope/verdict path is complete | CLOSED |
| G5 | Phase 4 timestamp alignment fix is present | CLOSED |
| G6 | Repo default config keeps judge inert (`judge.mode="off"`) | CLOSED |
| G7 | Phase 4 replay data (JSONL logs) is available for simulator input | MUST VERIFY |
| G8 | Trade outcome data can be externally supplied | MUST VERIFY |
| G9 | This document is the only Phase 5 implementation SSOT | CLOSED by this rewrite |
| G10 | No conflicting Phase 5 drafts exist in the repo | MUST VERIFY before implementation starts |

---

## 11. Runtime Admission Policy

### 11.1 Explicit Unchanged Runtime Admission

**Phase 5 does not widen runtime mode admission.**

Runtime-admitted modes at end of Phase 5 remain exactly as they were at start of Phase 5:

| Mode | Admitted | Status at Phase 5 Start | Status at Phase 5 End |
|------|----------|------------------------|----------------------|
| `off` | YES | Same | **Unchanged** |
| `shadow` | YES | Same | **Unchanged** |
| `hybrid_advisory` | NO | Same | **Unchanged** |
| `guarded_entry_authority` | NO | Same | **Unchanged** |
| `guarded_lifecycle_authority` | NO | Same | **Unchanged** |

### 11.2 Explicit Non-Admission of `hybrid_advisory`

`hybrid_advisory` is **not admitted in Phase 5**.

This is a deliberate decision:

- Phase 5 is analysis-only.
- Simulator outputs inform Phase 6 promotion review.
- Phase 6 (not Phase 5) decides whether to admit `hybrid_advisory` based on simulator evidence.

If the decision is made at Phase 6 to admit `hybrid_advisory`, that work happens in Phase 6, not Phase 5.

### 11.3 Config Boundaries Remain Frozen

`JudgeCortexConfig` validation remains frozen:

- Config load must reject any value for `judge.mode` other than `off` or `shadow`.
- Config load must reject `hybrid_advisory` (will be a load-time error).

### 11.4 Promotion Track Deferred

The advisory/promotion operational track (hybrid_advisory → guarded_entry → guarded_lifecycle) is explicitly deferred beyond Phase 5. Phase 6 may or may not pursue it, depending on Phase 5 simulator evidence.

---

## 12. Shadow Economic Simulator Design

### 12.1 Consumed Artifacts

The simulator reads the following **offline** artifacts from Phase 1-4 replay:

| Artifact | Source | Format |
|----------|--------|--------|
| `JudgeVerdict` records | Phase 4 `EVT:JUDGE_ENTRY_VERDICT_V1` JSONL logs | Serialized Pydantic model |
| `JudgeEvidenceEnvelope` records | Phase 4 envelope assembly logs | Serialized Pydantic model |
| `ChamberAggregate` records | Phase 3-4 chamber logs | Serialized Pydantic model |
| `ExpertOutput` records | Phase 2-4 expert output logs | Serialized Pydantic model |
| Strategy signals (for correlation) | Alpha search signal JSONL logs | Serialized; includes `strategy_id`, `symbol`, `tf_sec`, `bar_close_ts` |

All inputs are **replayed, timestamped, deterministic logs**, not live runtime streams.

### 12.2 Simulator Inputs (Externally Supplied)

The operator supplies outcome data in a structured format (JSON schema to be defined):

| Input | Semantics |
|-------|-----------|
| Trade fills | Which cycles resulted in actual opens; what price, size, slippage |
| Fees | Trading fees per cycle (can be per-trade or pre-computed) |
| Exits | When positions closed; exit price; hold duration |
| Position context | Starting capital, leverage, fees; constraints |

Format: JSON or CSV with frozen schema (schema document to be authored in Phase 5).

### 12.3 Simulator Core Logic: Verdict-Outcome Matching

The simulator matches verdicts to outcomes via **deterministic correlation**:

```
For each JudgeVerdict record:
  1. Extract (strategy_id, symbol, tf_sec, bar_close_ts).
  2. Look for a matching trade fill in outcome data with the same key.
  3. If found:
     a. Extract outcome: entry price, slippage, fee, exit price, exit time.
     b. Compute counterfactual outcomes (no-hold, no-fee, no-slip variants).
     c. Compare verdict to outcome (did verdict recommend what outcome shows was best?).
     d. Record per-expert accuracy.
     e. Record disagreement signature if experts split.
  4. If not found:
     a. Log unmatched verdict.
     b. Continue (no impact on decision).
```

This blueprint does **not** modify decision_making runtime behavior.

This blueprint does **not** modify contracts.py.

---

## 13. Placement Decision

### 13.1 Simulator Module Location

```
apps/reference/domains/alpha_search/judge/
├── simulator/                       [NEW — Phase 5]
│   ├── __init__.py
│   ├── simulator_engine.py          [Core verdict-outcome correlation]
│   ├── fee_slippage_calculator.py   [Fee and slippage modeling]
│   ├── expert_accuracy_reporter.py  [Per-expert accuracy computation]
│   ├── calibration_dataset_writer.py [Produce labeled training datasets]
│   ├── config_models.py             [SimulatorConfig Pydantic model]
│   ├── schemas/
│   │   ├── outcome_input_v1.json    [Outcome data input schema]
│   │   ├── calibration_dataset_v1.json
│   │   └── summary_report_v1.json
│   └── __main__.py                  [CLI entry point (optional Phase 5B)]
├── __init__.py                      [FROZEN Phase 1]
├── contracts.py                     [FROZEN Phase 1]
├── config_models.py                 [FROZEN Phase 1-4]
├── ...existing judge modules...
```

### 13.2 Why This Placement

- **Under `alpha_search/judge/`**: Simulator consumes judge artifacts; belongs to judge domain ownership.
- **Under `simulator/` subpackage**: Clean separation from live pipeline (`experts/`, `chamber/`, `envelope/`, `verdict/`).
- **Not a new domain**: Subpackage under existing judge is sufficient; does not violate F6 (no new top-level domain).
- **Offline-only**: Simulator does not participate in runtime event chain.

### 13.3 Config Placement (Separate File)

Simulator config is **standalone**, NOT integrated into `JudgeCortexConfig`:

```yaml
# New file: config/judge_simulator.yaml

judge_simulator:
  enabled: false                           # Default OFF; operator explicitly enables
  input:
    judge_logs_path: "./logs/judge/"
    outcome_data_path: "./data/simulator/outcomes.json"
  modeling:
    fee_per_cycle_bps: 25                  # 0.25%
    slippage_pct: 0.1                      # 0.1%
    hold_duration_min_sec: 60
  output:
    calibration_dataset_path: "./artifacts/phase5_calibration.jsonl"
    summary_report_path: "./artifacts/phase5_summary_report.json"
```

This config is **orthogonal** to `JudgeCortexConfig`. Simulator can run even when `judge.enabled=false`.

---

## 14. Phase 5 Runtime / Replay Flow

### 14.1 Offline Execution Model

Phase 5 simulator is **not** part of live runtime. It is an **offline analysis tool** run after backtest or trading session:

```
[Phase 1-4: Live/Replay Runtime]
  ↓
  emit EVT:JUDGE_ENTRY_VERDICT_V1 → logs/judge_shadow/verdict_*.jsonl
  emit EVT:JUDGE_ENVELOPE_V1 → logs/judge_shadow/envelope_*.jsonl
  emit EVT:JUDGE_CHAMBER_V1 → logs/judge_shadow/chamber_*.jsonl
  record fills, exits → trade logs
  ↓
[Session End]
  ↓
[Phase 5: Offline Simulator Run]
  operator: python -m apps.reference.domains.alpha_search.judge.simulator \
              --config config/judge_simulator.yaml
  ↓
  load verdict JSONL
  load outcome data (external JSON)
  correlate verdicts to outcomes
  compute accuracy / fee impact / expert breakdown
  ↓
  outputs:
    - logs/judge_simulator/calibration_*.jsonl
    - logs/judge_simulator/summary_*.json
  ↓
[Session End + Simulator Done]
  ↓
[Phase 6: Promotion Review]
  use simulator artifacts to decide on mode admission
```

### 14.2 Explicit Guarantees

Phase 5 simulator guarantees:
- **No runtime events**: Simulator produces no `EVT:*` events during live trading.
- **No live state mutation**: Simulator does not modify runtime config or state.
- **No live API calls**: Simulator reads only logs; no live runtime integration.
- **No decision impact**: Simulator output does not affect live trading decisions.

Simulator runs **after** the session; it produces **offline evidence** for Phase 6 review.

---

## 15. Config Package

### 15.1 New Config File: `config/judge_simulator.yaml`

Schema:
```yaml
judge_simulator:
  enabled: false
  input:
    judge_logs_path: "./logs/judge/"
    outcome_data_path: "./data/simulator/outcomes.json"
  modeling:
    include_fees: true
    fee_per_cycle_bps: 25
    include_slippage: true
    slippage_pct: 0.1
    hold_duration_min_sec: 60
  output:
    calibration_dataset_path: "./artifacts/phase5_calibration.jsonl"
    summary_report_path: "./artifacts/phase5_summary_report.json"
    verbosity: "info"
```

### 15.2 NO Runtime Mode Widening

This config **does not** extend `JudgeCortexConfig`. Runtime mode admission stays frozen:

```python
class JudgeCortexConfig(BaseModel):
  enabled: bool
  mode: Literal["off", "shadow"]  # FROZEN; no hybrid_advisory
```

---

## 16. File-by-File Implementation Blueprint

### 16.1 New Files (Phase 5 Only)

| File | Purpose | Est. LOC |
|------|---------|----------|
| `simulator/__init__.py` | Module export | 10 |
| `simulator/simulator_engine.py` | Core verdict-outcome matching | 250 |
| `simulator/fee_slippage_calculator.py` | Fee/slippage models | 120 |
| `simulator/expert_accuracy_reporter.py` | Per-expert accuracy computation | 180 |
| `simulator/calibration_dataset_writer.py` | Labeled dataset production | 130 |
| `simulator/config_models.py` | SimulatorConfig schema | 40 |
| `simulator/schemas/*.json` | Input/output schemas (3 files) | 80 |
| `simulator/__main__.py` | CLI entry point | 60 |
| `config/judge_simulator.yaml` | Default simulator config | 20 |
| `tests/domains/alpha_search/judge/simulator/test_*.py` | Test suite (5 files) | 800 |

**Total: ~1,700 LOC (mostly tests and schemas).**

### 16.2 Modified Files: ZERO

Phase 5 adds only new files under `simulator/`. No existing code is touched.

### 16.3 Explicitly Unchanged

- `judge/contracts.py` — byte-identical to Phase 4
- `judge/config_models.py` — FROZEN
- `judge/verdict/verdict_synthesizer.py` — FROZEN
- `backtest_plugin.py` — FROZEN
- `decision_making/` — FROZEN
- `execution_position/` — FROZEN
- `main.py`, `config_loader.py` — FROZEN

---

## 17. Validation Blueprint

### 17.1 Acceptance Tests

| Test | Condition | Pass |
|------|-----------|------|
| T1 | Simulator loads verdict JSONL | Parses without error |
| T2 | Simulator loads outcome data | Outcome schema valid |
| T3 | Verdict-outcome correlation is deterministic | Rerun produces identical output |
| T4 | Fee model applies | With-fee vs. without-fee metrics differ correctly |
| T5 | Per-expert accuracy is correct | Sum of expert accuracies weights to overall |
| T6 | Calibration dataset is valid | JSON lines, all rows parse |
| T7 | No Phase 1-4 code modified | Diff shows only new files in `simulator/` |
| T8 | `contracts.py` unchanged | Byte-identical to Phase 4 |
| T9 | No mode widening | Config load still rejects `hybrid_advisory` |
| T10 | No runtime integration | No imports from simulator in `main.py` or `decision_making` |

### 17.2 Fixture Data

Tests use fixture judge artifacts:

```
tests/fixtures/judge_artifacts/
├── verdicts_sample_100.jsonl
├── chambers_sample_100.jsonl
├── envelopes_sample_100.jsonl
└── outcomes_sample_100.json
```

---

## 18. Risks

| Risk | Cause | Mitigation |
|------|-------|-----------|
| R1 | Outcome data format undefined | Define strict JSON schema; fail loudly on parse error |
| R2 | Verdict-outcome mismatch | Validate uniqueness of correlation key; dedup before analysis |
| R3 | Missing judge logs | Document required log retention; fail if logs absent |
| R4 | Fee double-counting | Clearly document whether fees are applied additively or backtest-as-is |
| R5 | Per-expert accuracy wrong | Verify `ChamberAggregate` always preserves full expert roster |
| R6 | Simulator used for live decisions | Document offline-only; no runtime imports |

---

## 19. Phase 5 Package Order

| Package | Content | Dependency |
|---------|---------|-----------|
| **5A** | Simulator engine core + outcome loader + correlation | None |
| **5B** | Fee and slippage modeling | 5A |
| **5C** | Expert accuracy reporter | 5A |
| **5D** | Calibration dataset writer | 5A, 5C |
| **5E** | Summary report generation | 5A-5D |
| **5F** | CLI harness | 5A-5E |
| **5G** | Test harness + fixtures | 5A-5F |
| **5H** | Config schema and validation | 5A-5G |

Monolithic delivery: all packages together deliver one cohesive tool.

---

## 20. Done Criteria

Phase 5 is **done** when **all** are true:

- [ ] Simulator module exists at `apps/reference/domains/alpha_search/judge/simulator/`
- [ ] Simulator loads JSONL judge verdict logs deterministically
- [ ] Simulator loads externally-supplied outcome data
- [ ] Simulator matches verdicts to outcomes by `(strategy_id, symbol, tf_sec, bar_close_ts)`
- [ ] Verdict-outcome accuracy computed by verdict type
- [ ] Fee and slippage impact computed (multiple variants)
- [ ] Per-expert accuracy disaggregated
- [ ] Disagreement cycles identified and correlated
- [ ] Calibration dataset produced (JSON lines, deterministic)
- [ ] Summary report produced (JSON with Phase 6 recommendation)
- [ ] All acceptance tests pass (T1-T10 from Section 17.1)
- [ ] No Phase 1-4 code modified (zero diff outside `simulator/`)
- [ ] `contracts.py` byte-identical to Phase 4
- [ ] `JudgeCortexConfig` still rejects `hybrid_advisory`
- [ ] No new runtime events emitted
- [ ] `decision_making` and `execution_position` unchanged
- [ ] `main.py` and `config_loader.py` unchanged
- [ ] Simulator design documented
- [ ] CLI usage documented
- [ ] Phase 5 code review passed

---

## 21. Deferred Advisory / Promotion Track

**This section is INFORMATIONAL; NOT Phase 5 scope.**

Phase 5 produces simulator evidence. **Phase 6 is the review gate.**

If Phase 6 recommends it, **Phase 6 or later** may admit `hybrid_advisory` mode. Phase 5 does NOT make this decision.

Deferred work (Phase 6+):
- Admission of `hybrid_advisory` at runtime
- Implementation of `decision_making` advisory bridge
- Emission of `EVT:JUDGE_ADVISORY_CONSULTED_V1`
- Integration of judge verdicts into signal payloads

All of the above depend on Phase 5 simulator evidence.

---

## 22. Final Recommended Next Coding Task

**After this document is approved, immediately proceed with:**

**Package 5A: Simulator Engine Core**

Scope:
- [ ] Define `SimulatorConfig` Pydantic model in `simulator/config_models.py`
- [ ] Define `outcome_input_v1.json` schema
- [ ] Implement JSONL loader for judge verdicts in `simulator/simulator_engine.py`
- [ ] Implement outcome data loader
- [ ] Implement deterministic verdict-outcome correlation
- [ ] Implement basic accuracy metric computation
- [ ] Write 5-8 unit tests with fixture data
- [ ] Verify zero modifications to Phase 1-4 code

**Exit gate:** Simulator engine loads logs, correlates verdicts to outcomes, computes accuracy.

**Do NOT proceed to Phase 5B until Package 5A is code-reviewed and merged.**

---

## Mandatory Required Phrases

The following exact sentences appear in this document:

1. ✅ "Phase 5 is Shadow Economic Simulator."
2. ✅ "Phase 5 does not widen runtime mode admission."
3. ✅ "hybrid_advisory remains deferred beyond Phase 5."
4. ✅ "This blueprint does not modify decision_making runtime behavior."
5. ✅ "This blueprint does not modify contracts.py."

All mandatory required phrases are present.

---

## Document Authority and Sign-Off

**Status:** FINAL (this replaces all earlier Phase 5 drafts)

**Approval required before implementation begins.**

**Key stakeholders:**
- Platform lead: Architecture decision on Phase 5 scope (simulator vs. mode admission).
- Judge domain owner: Responsibility for simulator placement and testing.
- Phase 6 lead: Readiness to consume simulator outputs.

**Frozen by this document:**
- Phase 5 is simulator-only, not mode-admission.
- Phase 5 does not modify live trading runtime behavior (adds offline analysis code only).
- Simulator is offline-only analysis.
- All deferred work is explicitly documented.
- Phase 6 is the promotion gate.

This is the single authoritative Phase 5 implementation blueprint for the Phenix repository.
