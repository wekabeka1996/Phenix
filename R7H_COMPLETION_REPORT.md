# R7H Completion Report

## What Is Now Proven
- Symbol-scoped economics are exportable from the portfolio-state boundary.
- PositionTracking now emits `markPrice`, `unrealizedPnl`, and `unrealizedPnlPct` when a fresh mark price exists.
- The authoritative source for `markPrice` is the fresh symbol mark cache populated from market ticks.
- Sidecar already consumes the new canonical fields without any threshold, routing, or close-math changes.
- The validated slice proves long, short, and missing-mark cases behave as intended.

## What Remains Unproven Until Runtime
- A live runtime slice with the verified build still needs to show fresh market ticks and actual symbol economics in production-like traffic.
- The next runtime observation must prove that the new fields are populated in real events, not only in unit tests.
- If the live mark feed is stale or absent, the export will remain null and Sidecar will continue to fail closed.

## Residual Risk
- The change is additive and fail-closed, but live feed cadence and symbol coverage are still runtime dependencies.
- No Sidecar thresholds, trigger math, or close routing were changed; any future divergence must come from runtime evidence, not assumptions.
- Downstream consumers outside the validated Sidecar path may still need their own compatibility check if they parse position objects strictly.

## Recommendation
- The next package should be R7I runtime observation to confirm the new fields appear in a live slice and flow into Sidecar peak-giveback snapshots.

ECONOMICS_EXPORTED_READY_FOR_RUNTIME_OBSERVATION
