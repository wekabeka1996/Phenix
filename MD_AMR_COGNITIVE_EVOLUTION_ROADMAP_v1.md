# MD_AMR_COGNITIVE_EVOLUTION_ROADMAP_v1

**Status:** Working engineering roadmap / SSOT planning artifact  
**Scope:** `md_amr` next evolution after repair phase  
**Focus:** Additive cognitive overlay, not broad rewrite  
**Format:** Engineering roadmap in Markdown  
**Baseline truth date:** 2026-04-10

---

## 1. Purpose of this document

This document defines the next engineering roadmap for strategy `md_amr` after the completed repair line:

- forensic truth reconstruction,
- math and logic audit,
- proof pass,
- empirical replay,
- remediation roadmap,
- `Package A + A.1`,
- `Package B + B.1`.

The purpose of this roadmap is **not** to continue generic repair work.
The purpose is to move `md_amr` from a **repaired but still cognitively primitive mean-reversion engine** toward a more capable, context-aware, explainable strategy layer.

This roadmap is intentionally built around:

- additive-only evolution,
- YAML + Pydantic SSOT,
- contract discipline,
- replay-driven validation,
- explicit package boundaries,
- evidence-proportional scope.

---

## 2. Current accepted truth-base

### 2.1 Accepted baseline state

The following is treated as the current accepted truth-base:

1. `Package A + A.1` is the accepted baseline repair.
2. `Package B` is accepted as **code capability**, not as an accepted default baseline.
3. `Package B.1` rejected `COMBINED` as economically acceptable default state.
4. The safe current baseline should be treated as the `Package A.1` state.

### 2.2 What is already fixed

The following is considered already resolved enough for the purposes of this roadmap:

- the old `conf_ratio`-driven exit conflict,
- the pre-`Package A` killswitch vs scaleout failure mode,
- the hardcoded `hold_edge_min` debt,
- the silent runtime/config drift around `conf_min` in exit semantics,
- the deployment ambiguity around `Package B` through `B.1` economic validation.

### 2.3 What remains structurally weak

The following is **not** considered fixed:

- setup-quality discrimination at entry,
- progress-aware hold intelligence,
- reward-to-go awareness,
- context-validity assessment,
- meaningful confidence semantics,
- memory of failed setup archetypes,
- richer post-entry belief management.

### 2.4 Current safe operating assumption

Until a future package proves otherwise via replay and economic normalization, the strategy should be treated as operating from:

- `max_hold_bars = 16`
- `target_approach_pct = 0.0`

That is the effective safe baseline for all future comparisons.

---

## 3. Problem statement for the next evolution phase

`md_amr` is no longer broken in the same way it was before `Package A`, but it remains limited by a shallow decision structure.

Today the strategy can approximately answer:

- “Did price move far enough outside the channel?”
- “Does directional score still structurally agree?”
- “Did we hit target or timeout?”

It still answers poorly or not at all:

- “Was this entry actually a good mean-reversion setup?”
- “Is this position making real progress toward the original thesis?”
- “Is the market context still supportive of mean reversion?”
- “Is the trade getting stale?”
- “How much edge remains versus time and cost?”
- “Should I still believe this trade?”

This roadmap exists to add those missing layers **without** collapsing architecture boundaries.

---

## 4. Design laws for this roadmap

All future packages in this roadmap must obey the following laws.

### 4.1 SSOT law

All new business semantics must be externalized through:

- YAML config,
- Pydantic model,
- explicit wiring.

No hidden business constants. No silent defaults buried in strategy math.

### 4.2 Additive-first law

A package should prefer:

- new trace fields,
- new optional config blocks,
- new overlay scores,
- new replay validations,

before changing or deleting existing contract surfaces.

### 4.3 Contract isolation law

Do not mix:

- strategy math,
- handler state,
- gateway validation,
- execution lifecycle truth.

Each proposal must explicitly state where it lives.

### 4.4 Replay truth law

A package is not accepted only because the logic sounds elegant.
A package must survive:

- replay,
- matched-cohort analysis,
- normalized economic comparison,
- regression checks.

### 4.5 No broad rewrite law

This roadmap does **not** authorize rewriting `md_amr` into a new strategy from scratch.
The goal is staged evolution, not identity replacement.

### 4.6 Explainability law

Every new cognitive layer must remain explainable through:

- trace fields,
- parameter blocks,
- replay casebooks,
- deterministic logic.

---

## 5. Out of scope for this roadmap cycle

The following items are explicitly **out of scope** for the immediate next cycle:

1. broad rewrite of `MDAMRStrategyV11`,
2. neural / ML / RL replacement logic,
3. full `conf_ratio` contract cleanup in the same package,
4. gateway shape redesign,
5. execution-position policy redesign,
6. pseudo-MTF rewrite as part of the first cognitive package,
7. volatility dampening redesign,
8. broad cross-symbol orchestration,
9. live self-learning / online adaptation.

These may become later tracks, but they are not part of the next accepted engineering package.

---

## 6. Engineering target for the next package line

The next package line should be:

# **Package C — Cognitive Overlay v1**

The package should add four explainable cognitive dimensions:

1. **Anchored Target + Progress Tracking**
2. **Minimal Setup Quality Score**
3. **Hold Quality / Soft Decay**
4. **Lightweight Context Validity**

This package should remain:

- additive,
- contract-safe,
- replay-testable,
- compatible with the repaired baseline.

---

## 7. Roadmap phases

---

# PHASE 1 — Baseline Freeze and Repo Reconciliation

## Objective

Ensure that repository truth, configuration truth, and accepted document truth are aligned before any new cognitive work begins.

## Why this phase exists

Documentation already established that `Package B` is code-capable but economically rejected as default state.
That means the repo must be verified against the accepted baseline, not assumed.

## Required work

1. Inspect current `md_amr.yaml` and confirm actual defaults.
2. Confirm whether repo state matches accepted baseline:
   - `max_hold_bars = 16`
   - `target_approach_pct = 0.0`
3. If not, perform a narrow reconciliation patch.
4. Record current accepted baseline snapshot.
5. Record whether `Package B` code support remains present but dormant.

## Deliverables

- `MD_AMR_BASELINE_STATUS_SNAPSHOT.md`
- optional narrow reconciliation patch if needed

## Validation

- config matches accepted baseline,
- replay baseline can be reproduced,
- no ambiguity remains around “current default state”.

## Exit gate

This phase is complete only when repo truth and accepted roadmap truth no longer disagree.

## Non-goals

- no new strategy logic,
- no threshold experiments,
- no shape cleanup,
- no new package work.

---

# PHASE 2 — Distribution Analysis for Cognitive Calibration

## Objective

Build the empirical calibration base needed for `Package C` so that new cognitive fields are not tuned blindly.

## Core idea

Before adding new intelligence, quantify the geometry and trajectory of current trades.

## Required analysis surfaces

### 2.1 Entry distributions

Collect and analyze distributions for:

- penetration depth beyond channel,
- band width,
- channel width as % of price,
- ATR and ATR z-score,
- dir-score margin above threshold,
- directional coherence between HTF/LTF components,
- channel slope / drift,
- regime-conditioned entry outcomes.

### 2.2 Hold trajectory distributions

Collect and analyze:

- bars-to-scaleout,
- bars-to-timeout,
- progress-to-target over time,
- hold-edge trajectories,
- profitable late reversions,
- stagnating holds,
- fast failed reversions,
- symbol-specific differences (XRP vs BNB).

### 2.3 Exit archetype distributions

Separate cohorts:

- healthy scaleouts,
- stale holds,
- late profitable zombies,
- invalidated holds,
- high-volatility fades,
- narrow-channel fake setups.

## Deliverables

- `MD_AMR_PACKAGE_C_DISTRIBUTION_ANALYSIS.md`
- supporting CSV / notebook artifacts if helpful

## Validation

The phase is successful when the strategy team can point to actual observed distributions for:

- channel sanity,
- directional coherence,
- progress patterns,
- time-to-completion,
- regime-conditioned outcomes.

## Exit gate

Do not start Package C parameter design until the team has these distributions.

## Non-goals

- no code changes,
- no new package logic,
- no silent threshold tuning.

---

# PHASE 3 — Package C.1: Anchored Target + Progress Tracking

## Objective

Give the position an explicit memory of:

- the entry contract,
- the original target,
- the realized progress toward that target.

This is the structural answer to the “moving target” problem that made simple tolerance-based fixes economically dangerous.

## Problem this phase addresses

The current rolling `avg_close` target behaves as a moving reference. Positions that are genuinely progressing can still fail to “catch” the live target. Conversely, tolerance-based early exits can cut profitable slow reversions too early.

## Design principle

Do **not** replace rolling channel logic globally.
Instead, add an anchored position-level semantic:

- what target did the trade commit to at entry,
- how much of that thesis has already been completed.

## Core changes

### 3.1 New state fields

At minimum introduce position-level state for:

- `entry_price`
- `entry_target_price`
- `entry_progress_basis`

Exact hosting layer should be decided explicitly:

- preferably handler or position-context layer,
- not a blind rewrite of math-core global assumptions.

### 3.2 New trace fields

Add at least:

- `trace.entry_price`
- `trace.entry_target_price`
- `trace.progress_pct`
- `trace.progress_state`

### 3.3 Progress semantics

Define a deterministic `progress_pct` that measures how much of the original reversion thesis has been completed.

### 3.4 Progress state classification

At minimum define a compact explainable state such as:

- `NOT_STARTED`
- `PARTIAL_PROGRESS`
- `NEAR_COMPLETION`
- `COMPLETE`
- `REVERSING_AGAINST`

## Design constraints

- do not touch `MDAMRSignal` shape,
- do not change Gateway contract,
- do not reintroduce old killswitch logic,
- do not introduce hidden constants.

## Validation

Replay must show that the new progress surface helps distinguish:

- healthy slow reversions,
- flat stagnation,
- structurally failed holds.

Matched-cohort validation is mandatory.

## Deliverables

- code patch,
- tests,
- replay before/after,
- `MD_AMR_PACKAGE_C1_ANCHORED_TARGET_REPORT.md`

## Exit gate

This phase is complete only if:

- progress is stable and explainable in traces,
- late profitable reversions are better represented,
- no contract drift occurs.

---

# PHASE 4 — Package C.2: Minimal Setup Quality Score

## Objective

Add a first orthogonal entry-quality layer so that `md_amr` stops treating all threshold-passing setups as equally worthy.

## Problem this phase addresses

The current entry path is too close to:

- “score crossed threshold, therefore open”.

This causes weak, noisy, or structurally poor mean-reversion candidates to be treated too similarly to high-quality setups.

## Design principle

`setup_quality` must be:

- minimal in v1,
- explainable,
- orthogonal to existing `score`,
- not a giant super-score.

## Recommended v1 components

Use only a minimal set, such as:

1. penetration margin,
2. channel quality / band sanity,
3. directional coherence,
4. volatility context.

## Required surfaces

### 4.1 YAML block

Introduce a dedicated config block, for example:

- `setup_quality.enabled`
- `setup_quality.min_threshold`
- `setup_quality.weights.*`
- optional component-specific thresholds

### 4.2 Trace additions

Add:

- `trace.setup_quality`
- `trace.setup_quality_components.*`

### 4.3 Usage semantics

In v1, `setup_quality` may be used only as:

- a weak suppressor,
- a veto for clearly poor setups,
- a sizing attenuator.

It should **not** replace the base trigger entirely in the first version.

## Design constraints

- no `conf_ratio` shape rewrite,
- no broad signal shape changes,
- no twelve-factor monster score.

## Validation

Run ablation for:

- trigger-only baseline,
- trigger + setup-quality gate,
- trigger + setup-quality sizing attenuation.

Compare:

- trade count,
- false-entry reduction,
- pnl/bar,
- economic normalization, not just raw hit-rate.

## Deliverables

- code patch,
- YAML + Pydantic extension,
- tests,
- replay ablation,
- `MD_AMR_PACKAGE_C2_SETUP_QUALITY_REPORT.md`

## Exit gate

The phase is successful only if `setup_quality` provides useful discrimination without opaque trade starvation.

---

# PHASE 5 — Package C.3: Hold Quality / Soft Decay

## Objective

Introduce a continuous notion of hold-health that reflects:

- structural support,
- progress deficit,
- time decay.

## Problem this phase addresses

Post-`Package A`, the strategy no longer kills good trades too early, but it still lacks a mature answer to:

- stale holds,
- non-progressing holds,
- “the thesis still exists structurally, but the trade is rotting”.

## Design principle

Do not replace `hold_edge`.
Layer a new additive field over it.

## Required semantics

At minimum define:

- `time_decay`
- `progress_deficit`
- `hold_quality`

`hold_quality` should be an explainable function of:

- `hold_edge`
- `progress_pct`
- elapsed hold time

## Optional state labels

You may classify hold states into:

- `HEALTHY`
- `STALLED`
- `DEGRADING`
- `EXHAUSTED`

Keep the first version compact.

## Design constraints

- no state-machine explosion,
- no reintroduction of old conf-ratio-killswitch semantics,
- no execution-layer dependency.

## Validation

Replay must show that:

- zombie trajectories are softened intelligently,
- late but valid reversions are not systematically cut,
- capital efficiency is not destroyed,
- Package B failure mode is not repeated.

## Deliverables

- code patch,
- tests,
- replay validation,
- `MD_AMR_PACKAGE_C3_HOLD_QUALITY_REPORT.md`

## Exit gate

This phase is complete only if hold-quality produces a healthier separation between:

- healthy holds,
- stale holds,
- invalidating holds.

---

# PHASE 6 — Package C.4: Lightweight Context Validity Layer

## Objective

Add a lightweight context-validity layer that helps answer:

> “Is the environment currently supportive of mean reversion?”

## Problem this phase addresses

The strategy currently checks regime compatibility too bluntly and too statically. It lacks a fine-grained way to penalize entry or hold in contexts where mean reversion is structurally weak.

## Design principle

This layer must remain:

- lightweight,
- additive,
- non-duplicative,
- not a second full regime engine.

## Suggested ingredients

At minimum consider:

- channel slope / drift,
- band stability,
- volatility abnormality,
- local oscillation vs drift hints,
- regime compatibility signal.

## Usage semantics

In v1, `context_validity` should be only:

- a penalty,
- an attenuator,
- a veto in obvious bad context.

It must **not** become the new dominant brain of the strategy.

## Trace additions

Add:

- `trace.context_validity`
- `trace.context_penalty_reason`

## Design constraints

- no duplication of external regime detector as a second SSOT,
- no full pseudo-regime engine in v1.

## Validation

Measure:

- false-entry reduction,
- opportunity suppression cost,
- interaction with setup quality,
- regime-conditioned behavior.

## Deliverables

- code patch,
- tests,
- replay validation,
- `MD_AMR_PACKAGE_C4_CONTEXT_VALIDITY_REPORT.md`

## Exit gate

The phase is complete only if context validity helps filter clearly bad context without becoming a second unstable regime engine.

---

# PHASE 7 — Integrated Package C Validation

## Objective

Validate the full `Package C` stack as a coherent cognitive overlay, not just as isolated local improvements.

## Required validation modes

### 7.1 Ablation ladder

At minimum compare:

1. Package A.1 baseline
2. C.1 only
3. C.1 + C.2
4. C.1 + C.2 + C.3
5. full Package C

### 7.2 Economic normalization

Mandatory metrics:

- pnl/bar-in-position,
- pnl/hour-in-position,
- net pnl / 1k bars,
- fee drag / 1k bars,
- turnover proxy,
- holding duration distribution,
- exit reason distribution.

### 7.3 Matched cohort casebook

At least 15–20 matched cases across XRP and BNB, comparing baseline versus new overlay behavior.

### 7.4 Symbol split

Do not accept only aggregate improvement. Check:

- XRP-specific behavior,
- BNB-specific behavior,
- whether gains are driven by one symbol while the other degrades.

## Deliverable

- `MD_AMR_PACKAGE_C_ECONOMIC_VALIDATION.md`

## Exit gate

Package C is accepted only if it is:

- mechanically healthier,
- economically non-degrading on normalized metrics,
- explainable in matched cohorts,
- free from new silent contract drift.

If Package C is only partially successful, keep it as capability, not default.

---

# PHASE 8 — Promotion Decision

## Objective

Decide what, if anything, becomes the new accepted baseline state.

## Decision options

1. **Promote full Package C** to default state.
2. Promote only part of Package C.
3. Keep Package C as code capability only.
4. Reject Package C as default state and keep Package A.1 baseline.

## Required output

This decision must explicitly state:

- what gets merged as capability,
- what gets promoted to default config,
- what remains experimental,
- what is still deferred.

## Deliverable

- `MD_AMR_PACKAGE_C_PROMOTION_DECISION.md`

## Exit gate

No ambiguity must remain between:

- accepted baseline,
- experimental capability,
- deferred research.

---

# PHASE 9 — Post-C Research Tracks (Package D and beyond)

## Objective

Open the next layer of strategy intelligence only after Package C has either stabilized or been partially promoted.

## Candidate tracks

### 9.1 Reward-to-Go formalization

A more mature economic exit intelligence layer beyond simple progress and soft decay.

### 9.2 Adaptive exit ladder

Multi-zone monetization with explicit salvage / core / stretch behavior.

### 9.3 Replay-derived archetype memory

Explainable memory of failed setup types and toxic local archetypes.

### 9.4 Structure + timing split

Potential future separation between:

- structural setup detection,
- local timing approval.

### 9.5 Conf-ratio cleanup / shape migration

Only after the system is stable enough to justify changing:

- `MDAMRSignal` semantics,
- Gateway required fields,
- Objective Engine adapters.

## Deliverable

- `MD_AMR_PACKAGE_D_RESEARCH_TRACKS.md`

---

## 8. Preferred sequencing summary

### Immediate next sequence

1. Phase 1 — Baseline Freeze / Repo Reconciliation
2. Phase 2 — Distribution Analysis
3. Phase 3 — Package C.1 Anchored Target + Progress
4. Phase 4 — Package C.2 Minimal Setup Quality
5. Phase 5 — Package C.3 Hold Quality / Soft Decay
6. Phase 6 — Package C.4 Lightweight Context Validity
7. Phase 7 — Integrated Package C Validation
8. Phase 8 — Promotion Decision

### Deferred sequence

9. Phase 9 — Package D / Research Extensions

---

## 9. Package boundaries summary

### Package C core

Must include:

- Anchored Target + Progress
- Minimal Setup Quality
- Hold Quality / Soft Decay
- Lightweight Context Validity

### Package C must not include

- conf_ratio shape cleanup,
- broad rewrite,
- pseudo-MTF rewrite,
- volatility dampening redesign,
- neural/ML components,
- full stateful memory system,
- gateway shape changes.

---

## 10. Main engineering risks

### Risk 1 — Overbuilding too early

Trying to ship all brainstorm ideas at once would likely produce a semi-living monster instead of a stronger strategy.

### Risk 2 — Hidden contract drift

Adding cognitive fields without clean YAML + Pydantic + trace discipline will re-create the exact debt that `A.1` had to clean up.

### Risk 3 — Mechanical improvement without economic proof

Package B already demonstrated that a mechanically cleaner exit distribution can still be economically worse. Every new overlay must be normalized economically, not only mechanically.

### Risk 4 — Duplicating regime logic

A context-validity layer can accidentally become a second regime engine if not scoped carefully.

### Risk 5 — Premature shape cleanup

Cleaning up `conf_ratio` too early could trigger unnecessary contract churn before the new cognitive layers are validated.

---

## 11. Explicit do-not-do list

1. Do not rewrite `md_amr` from scratch.
2. Do not delete `conf_ratio` shape in Package C.
3. Do not promote any new defaults without B.1-style validation.
4. Do not reintroduce the old killswitch semantics.
5. Do not use black-box ML in this roadmap cycle.
6. Do not move execution logic back into strategy math.
7. Do not make context validity a second unbounded regime engine.
8. Do not tune thresholds blindly without Phase 2 distributions.

---

## 12. Final roadmap verdict

The next accepted engineering direction for `md_amr` should be:

# **Package C — Cognitive Overlay v1**

This package is justified because it addresses the real remaining weakness of the strategy:

- not broken exit hygiene,
- but insufficient entry / hold / exit cognition.

The correct next move is therefore **not** another generic repair package and **not** a broad rewrite.
It is a staged, additive, explainable overlay that teaches the strategy four new abilities:

1. remember its original trade contract,
2. judge setup quality,
3. judge hold quality over time,
4. judge context validity.

Only after that layer is built and economically validated should the project move toward:

- reward-to-go engines,
- adaptive ladders,
- archetype memory,
- broader cognitive state machines.

---

## 13. Short operational summary

If the team wants the shortest possible execution order:

### Do now
- Freeze baseline truth
- Run distribution analysis
- Build Anchored Target + Progress
- Build Minimal Setup Quality
- Build Hold Quality / Soft Decay
- Add Lightweight Context Validity
- Replay-validate economically

### Do later
- reward-to-go
- laddered monetization
- archetype memory
- `conf_ratio` shape migration

### Do not do now
- broad rewrite
- ML
- pseudo-MTF rewrite
- Gateway/Execution redesign

