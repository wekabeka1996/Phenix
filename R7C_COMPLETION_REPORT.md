# R7C Completion Report

## Scope Outcome

R7C completed the bounded observability hardening requested for peak-giveback. The package stayed local to the Sidecar runtime payload surface, Sidecar schemas, and focused tests. No business behavior, thresholds, close routing, or action scope were changed.

## What Is Now Proven

- The runtime bootstrap row can disclose the loaded `peak_giveback_close` config and relevant freshness limits.
- Every touched sidecar policy row can now expose the economic context needed to evaluate peak-giveback behavior, or emit explicit null-reason semantics when that context is unavailable.
- Runtime rows can now distinguish these cases directly:
  - disabled
  - not armed below edge
  - armed but below trigger
  - threshold met
  - suppressed because close is already in progress
  - suppressed because inputs are stale
  - unevaluable because economics are missing
- Peak-giveback recommendation and close-request rows now carry explicit `policy_source` provenance and trigger-threshold inputs.

## What Remains Unproven Until The Next Runtime Slice

- Whether real runtime traffic produces the expected mix of `peak_giveback_not_armed_below_edge`, `peak_giveback_below_trigger`, and `peak_giveback_threshold_met` rows for live symbols.
- Whether operator workflows want additional aggregated summaries beyond the row-level fields added here.
- Whether config loader metadata will populate a non-null `sidecar_config_snapshot.source_config_path` in production runtime.

## Recommendation

The next package should be R7D runtime observation, not more contract work, unless the next slice exposes a concrete operator query that the new row-level fields still cannot answer.

## Validation Summary

- Focused peak-giveback runtime tests passed.
- Sidecar runtime + contract tests passed.
- Existing forensic validator tests passed with the richer row shape.
