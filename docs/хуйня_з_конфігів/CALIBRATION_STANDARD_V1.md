# CALIBRATION_STANDARD_V1

## Purpose

This standard defines the minimum governance contract for calibration work in this repository.

The goal is to separate:
- candidate generation from promotion
- production-aligned runtime surfaces from legacy or research surfaces
- stage-1 surface calibration from stage-2 bundle or objective orchestration

This document is normative for new calibration work and for any run that claims production alignment.

## Calibration Classes

### Production calibrator

A production calibrator targets an active runtime surface that is materially consumed by the current runtime path.

A production class does not imply GO, promotability, or automatic rollout.
It only means the tool is scoped to an active runtime surface rather than a legacy or synthetic surface.

### Research calibrator

A research calibrator targets one or more of the following:
- legacy surfaces
- deprecated surfaces
- partially proven or unproven runtime surfaces
- exploratory labels or proxy objectives that are not sufficient for production restart or promotion

Research outputs are advisory only and must not be promoted directly without separate active-surface proof and validation.

### Meta or stage-2 calibrator

A meta or stage-2 calibrator does not tune a single live strategy surface directly.
It bundles, ranks, or re-optimizes outputs produced by stage-1 calibrators or execution datasets.

Meta or stage-2 tools are not stage-1 production calibrators.

## Production Invariants

Any run that claims production alignment must satisfy these invariants.

1. It targets active runtime surfaces only.
2. It does not mutate canonical YAML directly.
3. It emits overlay artifacts only.
4. It emits a report.
5. It emits explicit non-goals.
6. It defines a guardrail contract.
7. It compares baseline versus candidate.
8. It records validation evidence.
9. It keeps candidate generation separate from promotion.

If a tool targets an active surface but a specific run does not satisfy the invariants above, that run is still NO_GO.

## Standard Artifact Contract

Recommended stable artifacts for a production-aligned run:

1. candidate overlay YAML
2. run_manifest.json
3. baseline_metrics.json
4. candidate_metrics.json
5. report.md

Strategy-specific filenames are allowed, but the semantics must stay explicit.

Required artifact semantics:

- candidate overlay YAML: additive overlay only; no canonical writeback
- run_manifest.json: class, scope, verdict, runtime truth anchors, non-goals, artifact paths
- baseline_metrics.json: current surface metrics used for comparison
- candidate_metrics.json: candidate metrics and guardrail outcomes
- report.md: human-readable audit trail

## Standard Report Sections

The report for a production-aligned run should contain, at minimum:

1. Scope
2. Runtime truth anchors
3. Dataset audit
4. Candidate search method
5. Guardrails
6. Baseline versus candidate
7. Facts / Inferences / Assumptions / Unknowns
8. Risks
9. Verdict
10. Next action

## Fail-Closed Rules

The following outcomes are mandatory.

1. Missing active-surface proof means research-only classification.
2. Insufficient data evidence means NO_GO.
3. No candidate means NO_GO.
4. Guardrail failure means NO_GO.
5. Missing validation evidence means NO_GO.
6. Canonical YAML auto-write is forbidden.

Candidate artifacts may still be emitted under NO_GO, but they remain non-promotable.

## Aurora Scope Freeze

For current Aurora runtime truth, production Aurora calibration is limited to:
- assets.<SYMBOL>.signal_threshold.value
- assets.<SYMBOL>.regime_thresholds

For current Aurora runtime truth, the following are not production Aurora calibration surfaces:
- signal_weights
- direction_strength_scoring
- feature_neutrals

These legacy Aurora surfaces are research-only unless runtime evidence changes and is re-proven.

## Promotion Boundary

Promotion is a separate decision from calibration.

A production-aligned calibrator run may still be NO_GO.
No report or overlay may imply automatic rollout, canonical writeback, or production promotion without separate approval and evidence.
