# SCORING TELEMETRY SPEC

## Purpose

Bounded research cannot trust runtime scoring unless the selected engine and fallback behavior are persisted into artifacts.

PKG-5 defines artifact-visible scoring telemetry for every backtest report.

## Raw Report Fields

Top-level field:

- `scoring_telemetry`

Shape:

```json
{
  "quadratic_engine_selected_count": 17724,
  "quadratic_fallback_count": 0,
  "fallback_also_failed_count": 0,
  "selected_engine_counts": {
    "quadratic_v1": 17724
  },
  "observed_engine_counts": {
    "quadratic_v1": 17724
  },
  "engine_names_observed": [
    "quadratic_v1"
  ],
  "per_symbol": {
    "ETHUSDT": {
      "selected_engine_counts": {"quadratic_v1": 8862},
      "observed_engine_counts": {"quadratic_v1": 8862},
      "quadratic_engine_selected_count": 8862,
      "quadratic_fallback_count": 0,
      "fallback_also_failed_count": 0,
      "engine_names_observed": ["quadratic_v1"]
    }
  }
}
```

## Semantics

- `quadratic_engine_selected_count`
  - Count of scoring decisions where the intended engine selection was quadratic.

- `quadratic_fallback_count`
  - Count of decisions where quadratic execution raised and the runtime fell back to legacy Aurora linear scoring.
  - For honest bounded search, the target value is `0`.

- `fallback_also_failed_count`
  - Count of events where the linear fallback also failed after quadratic failure.
  - For honest bounded search, the target value is `0`.

- `selected_engine_counts`
  - Counts based on chosen engine before execution.

- `observed_engine_counts`
  - Counts based on engine actually observed from emitted scoring payload.
  - This protects against situations where intended engine and runtime-emitted engine diverge.

- `engine_names_observed`
  - Deduplicated list of engines actually observed in the run artifact.

- `per_symbol`
  - Same counters broken down by symbol.

## Summary Export

Compact summaries now include a reduced scoring telemetry section with:

- `quadratic_engine_selected_count`
- `quadratic_fallback_count`
- `fallback_also_failed_count`
- `engine_names_observed`
- `observed_engine_counts`

## Fail-Closed Research Rule

PKG-5 harness supports:

- `fail_on_scoring_fallback=true`

When enabled, any run with `quadratic_fallback_count > 0` is rejected by the harness instead of being silently accepted into a search surface.

## PKG-5 Observed Values

Baseline proxy run `20260314_170343`:

- `quadratic_engine_selected_count = 17724`
- `quadratic_fallback_count = 0`
- `fallback_also_failed_count = 0`
- `engine_names_observed = ["quadratic_v1"]`

V1 proxy run `20260314_172657`:

- `quadratic_engine_selected_count = 17723`
- `quadratic_fallback_count = 0`
- `fallback_also_failed_count = 0`
- `engine_names_observed = ["quadratic_v1"]`

Conclusion:

- PKG-5 proxy benchmarks were artifact-proven quadratic-only for the observed run surface.