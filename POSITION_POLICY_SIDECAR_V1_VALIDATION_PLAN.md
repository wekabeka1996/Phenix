# POSITION_POLICY_SIDECAR_V1_VALIDATION_PLAN

## Validation Scope

This plan validates a Phase-1 recommendation-only sidecar for already-open position life management.

The plan does not validate:

- exact close-by-id
- direct action emission
- bracket mutation
- partial reduce execution
- TP extension or replacement

## 1. Shadow-Mode Validation

### Goal

Prove that the sidecar can evaluate, suppress, and recommend consistently without becoming noisy, opaque, or redundant.

### Required shadow outputs

- evaluation count by symbol and strategy
- suppression count by reason
- recommendation count by symbol and regime bucket
- recommendation score snapshots
- overlap markers with incumbent close events

### Pass criteria

- every recommendation has a complete score snapshot
- every suppression has an explicit suppression reason
- no recommendation is emitted after authoritative close reconcile
- no recommendation is emitted while `_closing_position` is active

## 2. Replay / Backtest Validation

### Goal

Measure whether recommendation-only Phase 1 identifies materially adverse open-position states without excessive premature-close suggestions.

### Replay requirements

- use event-order-faithful replay with:
  - `EVT:FEATURES_CALCULATED`
  - `EVT:REGIME_DETECTED`
  - `EVT:ORDER_FILL`
  - `EVT:ORDER_STATE_CHANGED`
  - `EVT:PORTFOLIO_STATE_UPDATED`
  - `EVT:EXECUTION_CLOSE_RECONCILED`
- retain current incumbent behavior unchanged
- compute counterfactual metrics from sidecar recommendation timestamps

### Replay outputs

- recommendation timestamp
- position state at recommendation
- subsequent price path over fixed horizons
- actual incumbent close path and timing
- whether recommendation preceded or followed incumbent close logic

## 3. False Positive Close Analysis

### Goal

Quantify how often a sidecar recommendation would have closed too early.

### False-positive definition

A Phase-1 soft-close recommendation is counted as premature when:

- the position was flat-to-losing at recommendation time, but
- the next validation horizon would have recovered sufficiently without incumbent close need

### Required review slices

- by symbol
- by strategy
- by local regime
- by confidence bucket
- by microstructure pressure bucket

## 4. Overlap Analysis Against `ExitManager`

### Goal

Separate legitimate additive signal from duplicate Aurora post-entry policy.

### Required overlap buckets

- sidecar recommended, `ExitManager` silent
- sidecar silent, `ExitManager` active
- both active in same direction
- sidecar active after incumbent close already started

### Required findings

- rate of overlap with `ExitManager`
- rate of same-bar overlap with regime-flip close
- rate of overlap with max-hold close
- rate of overlap with bracket terminal exits

## 5. Core Metrics

### Early saved loss

- estimated loss avoided if a recommendation had been honored at the recommendation timestamp versus actual realized outcome

### Premature close rate

- fraction of recommendations that would have exited before subsequent favorable recovery beyond a predefined threshold

### Duplicate action suppression

- count and rate of evaluations suppressed because incumbent owners already had control

### Recommendation-to-execution consistency

- Phase 1 target: recommendation-only
- future Phase-2 readiness metric: how often a recommendation would have mapped cleanly to a single symbol-scoped close request without identity ambiguity

### Explainability completeness

- fraction of recommendation/suppression events with complete required trace fields

## 6. Promotion Gates

Phase 1 may only be considered successful if all are true:

- recommendation traces are complete
- suppression rules work consistently
- overlap against incumbent close owners is explainable
- premature close rate is within acceptable bounds
- no hidden macro/BTC dependency appears in action-bearing logic

## 7. Rollback Posture

- single feature flag or registration switch disables the sidecar
- shadow traces remain safe to keep even if recommendation logic is disabled
- no incumbent execution path depends on the sidecar in Phase 1

## 8. Phase-2 Readiness Checks

Before any EP-internal request posture is enabled, the following must be proven:

- recommendation quality is stable
- incumbent suppression is reliable
- request-to-outcome attribution fields exist
- sidecar/`ExitManager` overlap has been characterized
- symbol-scoped close is still sufficient for the intended business action
