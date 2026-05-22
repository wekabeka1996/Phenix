# NRR062_SIDECAR_MODE_COMPARABILITY_MATRIX

## Classification

`COMPARABILITY_COHORT_SPLIT_REQUIRED`

Cross-cohort rule: do not compare NRR-062 economics apples-to-apples across `enable` and `shadow` sidecar cohorts. Treat packages H and L plus the restored current baseline as the `enable` cohort. Treat packages I and J as the dirty `shadow` cohort.

## Package Matrix

| Package | Sidecar Mode | Snapshot Hash | Matches Accepted Baseline | Comparable With | Notes |
| --- | --- | --- | --- | --- | --- |
| H | `enable` | `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | yes | H, L, restored current baseline, future enable-cohort packages | Clean snapshot on `34a3...`; `dirty_config_paths` did not include `config/aurora/domains.yaml`. |
| I | `shadow` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477` | no | I, J | Dirty `domains.yaml` on the same tracked commit; must be labeled as a shadow-drift cohort. |
| J | `shadow` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477` | no | I, J | Same dirty shadow hash as I and current pre-action workspace; Package L already reported the resulting comparability caveat. |
| L | `enable` | `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | yes | H, L, restored current baseline, future enable-cohort packages | Clean snapshot on the same tracked commit; aligns with accepted baseline. |

## Impact Notes

- The package-L finding that the 24 J diagnostics-only rows are downstream no-effect confirmed still stands because those rows never reached submit, fill, or close evidence.
- The package-level economics surface is still not apples-to-apples across H/L versus I/J because sidecar mode changes whether the bounded live close path can emit authority-bearing close requests.
- Future NRR-062 collection can rejoin the clean `enable` cohort after the baseline restore, but historical I/J evidence must stay explicitly labeled as `shadow` cohort evidence.
