# BTC Score Scale Root Cause

## Hard Verdict

ISOLATED_PRIMARY_REPLAY_GEOMETRY_MISMATCH

## Claim

The remaining BTC score-scale drift is primarily caused by replay calling QuadraticScoringKernel.compute with default admission geometry instead of the live Aurora decision geometry.

## FACTS

- Live decision config sets:
  - decision_geometry.admission_mode=linear
  - decision_geometry.sizing_mode=quadratic
  - decision_geometry.admission_shield_floor=0.75
- Live aurora_decision.py passes those values into QuadraticScoringKernel.compute.
- Repaired replay in tools/calibration/calibrate_aurora_thresholds.py still omits admission_mode, sizing_mode, and admission_shield_floor.
- Live BTC KERNEL_DIAG lines show admission=linear and admission_shield_mult=0.750 on all inspected anchors.
- Replay diagnostic slices exactly match quadratic-admission arithmetic on the same live s_linear values.

## Numeric Proof

### 19:05 anchor

- Live feature log: pillar_sum=-0.19661158041823273.
- Live KERNEL_DIAG: admission=linear, admission_shield_mult=0.750, score=-0.147459.
- Linear admission arithmetic:
  - -0.19661158041823273 * 0.75 = -0.14745868531367456.
- Replay slice: score=-0.02899209, shield_multiplier=0.75.
- Quadratic default arithmetic:
  - -(0.19661158041823273^2) * 0.75 = -0.028992085165916399.
- Result: the replay value is the quadratic transform of the live linear score input, not a threshold-extraction issue.

### 19:15 anchor

- Live feature log again shows pillar_sum=-0.19661158041823273.
- Live KERNEL_DIAG again shows admission=linear and score=-0.147459.
- Replay slice again shows score=-0.02899209.
- Result: the same exact mismatch repeats on a second anchor, which rules out a one-off bar artifact.

### 07:35 anchor

- Live feature log: pillar_sum=-0.1863425974418626.
- Live KERNEL_DIAG: admission=linear, admission_shield_mult=0.750, score=-0.139757.
- Linear admission arithmetic:
  - -0.1863425974418626 * 0.75 = -0.13975694808139694.
- Replay slice: score=-0.03472356, shield_multiplier=1.0.
- Quadratic default arithmetic:
  - -(0.1863425974418626^2) * 1.0 = -0.034723563621380057.
- Result: replay again matches default quadratic admission.

### 07:30 anchor

- Live feature log: pillar_sum=-0.1801065775423327.
- Live KERNEL_DIAG: admission=linear, admission_shield_mult=0.750, score=-0.135080.
- Linear admission arithmetic:
  - -0.1801065775423327 * 0.75 = -0.13507993315674952.
- Replay slice: score=-0.0259507, shield_multiplier=0.8.
- Quadratic default arithmetic:
  - -(0.1801065775423327^2) * 0.8 = -0.025950703419209842.
- Result: the replay score again lands on the quadratic path.

## What This Proves

- The anchored score mismatch is not primarily caused by threshold-surface extraction.
- The anchored score mismatch is not primarily caused by missing pillar features.
- The replay harness is applying the wrong admission geometry at the kernel boundary.
- Shield drift can amplify or attenuate the mismatch on some anchors, but the 19:05 and 19:15 anchors already prove geometry mismatch alone is sufficient.

## Root Cause

- Cause: replay omits the live decision geometry kwargs.
- Mechanism: live passes admission_mode=linear, sizing_mode=quadratic, admission_shield_floor=0.75; replay falls back to kernel defaults.
- Effect: replay compresses large-magnitude sell scores into much smaller quadratic outputs.
- Operational risk: any BTC calibration based on current replay optimizes against the wrong activation and continuation surface.

## Repairability

- Repair class: local and additive.
- Minimal repair:
  - thread admission_mode from live config into replay compute call.
  - thread sizing_mode from live config into replay compute call.
  - thread admission_shield_floor from live config into replay compute call.
- Required revalidation:
  - rerun the same four BTC anchors.
  - rerun canonical BTC control harness.
  - confirm whether hold-state drift collapses automatically.

## UNKNOWNS

- Whether any residual score drift remains after geometry parity is restored.
- Whether later bars still diverge because of shield familiarity state or feature provenance gaps.

## Final Classification

This is the highest-confidence and most repairable remaining replay defect.
