# AGENT_REPORT_V1

## Executive Summary

Phase 1C gap analysis shows an asymmetric state. Mean_reversion already has a usable current search surface for several core aggression knobs, while md_amr today is still a weights-only search engine even though it already extracts a much broader set of YAML parameters. That means md_amr is the decisive tooling blocker for Phase 2. Mean_reversion also remains constrained by scope truth: DOGEUSDT is still an offline dormant candidate, not a live-assigned surface.

Machine-readable gap matrix:

- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.json
- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.csv

## md_amr Dimension Status

| Dimension | Classification | Evidence |
| --- | --- | --- |
| threshold_z | SUPPORTED_WITH_SMALL_PATCH | Already extracted from YAML by `_extract_base_params`; current search does not mutate it. |
| thr_base | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| thr_floor | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| hysteresis_mult | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| volatility_dampening_factor | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| alpha | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| conf_min | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| channel_window_bars | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| atr_window | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| atr_stats_window | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| max_hold_bars | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| target_approach_pct | SUPPORTED_WITH_SMALL_PATCH | Already extracted; current search is weights-only. |
| allowed_regimes | SUPPORTED_WITH_SMALL_PATCH | Asset allowlists are already loaded and enforced but not searched. |
| cooldown_sec | NOT_SUPPORTED | No current md_amr cooldown dimension is extracted or searched by the toolchain. |
| objective-related strategy-local fields | SUPPORTED_WITH_SMALL_PATCH | Progress, setup, hold, context-validity, and hold-edge fields are already extracted but not mutated. |

## mean_reversion Dimension Status

| Dimension | Classification | Evidence |
| --- | --- | --- |
| entry_threshold | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| bb_window | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| bb_num_std | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| min_bb_width | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| max_bb_width | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| RSI contribution | SUPPORTED_WITH_SMALL_PATCH | `confidence_rsi_bonus` is loaded into runtime config but not mutated. |
| allowed_regimes | SUPPORTED_WITH_SMALL_PATCH | Loaded from YAML/asset overrides but not part of current search. |
| cooldown_sec | SUPPORTED_NOW | In current MR `SEARCH_BOUNDS`. |
| target_mult | NOT_SUPPORTED | No current general target multiplier search dimension exists. |
| stop_mult | SUPPORTED_NOW | Covered by `sl_atr_mult`. |
| tp_to_mid | SUPPORTED_WITH_SMALL_PATCH | Loaded and scanned in optional TP/SL surface mode, but not part of the main candidate mutation grid. |
| tp_buffer_pct | SUPPORTED_WITH_SMALL_PATCH | Loaded into runtime config but not mutated. |
| sl_buffer_pct | SUPPORTED_WITH_SMALL_PATCH | Loaded into runtime config but not mutated. |
| liquidity gate fields | NOT_SUPPORTED | Recorder liquidity fields are observable, but MR calibrator does not search liquidity gate knobs. |

## What This Means For Phase 2

- md_amr is not ready for the requested aggression grid as-is. The tool already reads most of the requested parameters, so the required follow-up is a small mutation-surface patch rather than a new framework.
- mean_reversion is closer. A reduced MR-only aggression grid could start immediately on the current supported dimensions, but that would still be an offline dormant-candidate study, not a live calibration package.
- If the next package must preserve the current no-assignment-change rule, then the cleanest next step is a tool patch on md_amr first, not an assignment change.

## Minimal Patch Boundary

The smallest justified Phase 2-enabling patch is:

- extend `calibrate_md_amr_weights.py` so it can mutate selected already-extracted base params in addition to weights;
- serialize those non-weight params into overlay-only candidate artifacts;
- keep the existing fail-closed dataset checks and window coverage checks;
- do not widen into execution or policy logic.

For mean_reversion, an optional later patch can add `confidence_rsi_bonus`, `allowed_regimes`, `tp_to_mid`, and buffer fields to the mutation surface. That is not the main blocker today.

## Readiness Verdict

- Overall Phase 2 readiness: NOT_READY.
- If the work were split strictly by strategy scope, the repo is closer to `READY_FOR_MR_ONLY` than to `READY_FOR_MD_AMR_ONLY`, but the requested combined package is still not ready.

## Recommended Next Package

tool patch
