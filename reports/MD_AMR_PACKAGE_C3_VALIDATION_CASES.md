# MD_AMR Package C.3 Validation Cases

## Scope

Deterministic evidence cases for `md_amr` Package C.3 (`time_decay`, `progress_deficit`, `hold_quality`) computed from the live strategy helper:

- code owner: `apps/reference/domains/feature_engineering/md_amr_strategy.py`
- helper: `MDAMRStrategyV11._compute_hold_quality_overlay(...)`
- config surface:
  - `expected_progress_grace_frac = 0.25`
  - `time_decay_weight = 0.35`
  - `progress_deficit_weight = 0.45`
  - `max_hold_bars = 16`

## Cases

| Case | bars_held | hold_health | progress_pct | elapsed_hold_frac | expected_progress_pct | progress_deficit | time_decay | hold_quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `healthy_mid_hold` | 6 | 0.70 | 0.55 | 0.3750 | 0.1667 | 0.0000 | 0.1687 | 0.7909 |
| `balanced_mid_hold` | 8 | 0.50 | 0.25 | 0.5000 | 0.3333 | 0.0833 | 0.3750 | 0.5813 |
| `lagging_late_hold` | 12 | 0.40 | 0.10 | 0.7500 | 0.6667 | 0.5667 | 0.6750 | 0.2088 |
| `stale_late_hold` | 14 | 0.70 | 0.05 | 0.8750 | 0.8333 | 0.7833 | 0.8312 | 0.2066 |

## What The Cases Show

- `time_decay` rises as timeout room shrinks while progress remains incomplete.
- `progress_deficit` is `0.0` when actual progress is on or ahead of schedule and grows when lagging.
- `hold_quality` remains bounded in `[0.0, 1.0]`.
- Healthy mid-hold cases score materially above stale late-hold cases without changing exit ownership.
