# NRR062_NO_SAFE_EXISTING_FIELD_PATCH

- No requested single-field delta admitted any rows from the 153-row canonical reject cohort.
- No paired sweep was executed because no single-field result was promising enough to justify stage-2 combinations.
- Max observed raw score magnitude in the reject cohort is 0.05373851, while the requested raw threshold sweep stops at 0.15.
- Therefore the requested raw-threshold range never crosses the current reject boundary.
- Geometry fields are live in runtime, but they are not binding for this cohort because every row already exceeds the current gross TP floor, TP fee coverage floor, and RR floor.
- min_direction_confidence_by_regime is a migration alias only for this cohort because runtime resolves threshold_family=raw_signed_score against explicit min_raw_score_by_regime.
- min_normalized_confidence_by_regime is inactive for this cohort because no row resolved selected_scale=normalized_confidence.
- A materially lower raw threshold would be required to admit rows, but that would still be a broad regime-level BUY+SELL relaxation and remains outside this requested sweep plus unsafe without segmented support.
