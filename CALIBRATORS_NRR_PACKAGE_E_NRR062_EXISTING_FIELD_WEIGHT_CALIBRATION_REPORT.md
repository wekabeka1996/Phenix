# AGENT_REPORT_V1

## verdict
NO_SAFE_EXISTING_FIELD_PATCH

## problem_framing
This package calibrates only existing LOW_VOL scalar fields. It does not expand YAML schema, does not add side-specific selectors, does not change Pydantic models, and does not modify runtime behavior. The task is to test whether the existing scalar contract can move the 153-row NRR-062 reject boundary safely, not to redesign the gate.

## facts
- branch: main
- commit_sha: captured externally in Phase 0
- Package A canonical reject rows: 153
- Package B replay summary: TP=33, SL=13, TIMEOUT=107, net=391.0476869715
- Observed selected_scale counts: {"raw_signed_score": 153}
- Observed threshold_family counts: {"raw_signed_score": 153}
- Boundary counts: {"direction_only_failure": 101, "regime+direction_failure": 52}
- Max raw score magnitude in reject cohort: 0.05373851
- Requested raw-threshold sweep floor: 0.15
- Domains hash during package: cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962

## inferences
- The requested raw-threshold sweep never crosses the current reject boundary because every observed raw-signed-score magnitude is below 0.05 while the sweep floor stops at 0.15.
- Geometry fields are runtime-live but non-binding for the 153-row cohort; lowering them cannot admit rows while the raw threshold remains above all observed magnitudes.
- min_direction_confidence_by_regime and min_normalized_confidence_by_regime are not effective levers for this cohort because runtime resolved all rows through raw_signed_score family with explicit min_raw_score_by_regime present.
- No safe existing-field candidate exists within the requested scalar ranges, so no YAML candidate patch should be proposed for application.

## assumptions
- The Package A reject ledger and Package B replay results remain the authoritative 153-row calibration surface for this package.
- Strategy+symbol override maps remain unchanged because this package calibrates only the explicitly requested scalar fields.
- Existing-field calibration is evaluated against the current blocked baseline where these 153 rows were all rejected.

## unknowns
- Whether a much lower raw threshold below 0.05 would create a positive testnet-only segment after penalties; that range is outside this requested sweep.
- Whether accepted LOW_VOL comparison would change the risk tolerance for broader regime-level scalar relaxation.
- Whether future runtime windows will preserve the same raw-score distribution as the current 153-row cohort.

## existing_field_inventory
| Field | Current Value | Used By Runtime? | Risk |
| --- | --- | --- | --- |
| target_net_fee_multiple | 2 | True | HIGH |
| min_tp_fee_coverage | 3 | True | HIGH |
| min_rr | 1.2 | True | HIGH |
| min_regime_confidence_by_regime.LOW_VOLATILITY | 0.39 | True | HIGH |
| min_direction_confidence_by_regime.LOW_VOLATILITY | 0.25 | False | LOW_FOR_CURRENT_COHORT_NOOP |
| min_raw_score_by_regime.LOW_VOLATILITY | 0.25 | True | HIGH |
| min_normalized_confidence_by_regime.LOW_VOLATILITY | 0.25 | False | LOW_FOR_CURRENT_COHORT_NOOP |

## boundary_reconstruction
| Failure Type | Rows | Notes |
| --- | --- | --- |
| direction_only_failure | 101 | raw threshold fails, regime passes |
| regime+direction_failure | 52 | both regime and raw threshold fail |
| geometry_failure | 0 | geometry thresholds fail |
| unknown | 0 | fallback bucket |

## sweep_summary
| Candidate | Newly Admitted | Net Proxy | BUY Net | SELL Net | Timeout Share | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| BASELINE_CURRENT | 0 | 0 | 0 | 0 |  | NO_CHANGE_BEST |
| MIN_RR_1.0 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_RR_1.1 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_TP_FEE_COVERAGE_2.0 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| MIN_TP_FEE_COVERAGE_2.5 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.15 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.18 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.20 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.22 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| RAW_LOW_VOL_0.23 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| REGIME_LOW_VOL_0.33 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| REGIME_LOW_VOL_0.35 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| REGIME_LOW_VOL_0.37 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| TARGET_NET_FEE_MULTIPLE_1.6 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |
| TARGET_NET_FEE_MULTIPLE_1.8 | 0 | 0 | 0 | 0 |  | INSUFFICIENT_EDGE |

## selected_candidate
No candidate selected. The requested existing-field sweep produced no non-baseline candidate with any admitted rows.

## candidate_patch
No patch file was produced.
State explicitly: not applied.

## risks
- Broad regime-level changes affect BUY and SELL together.
- Accepted LOW_VOL comparison is still missing.
- Replay remains timeout dominated at the cohort level.
- Any future scalar candidate would still be a testnet-only hypothesis, not production authority.

## validation
- Generated inventory, boundary, sweep, ranking, and no-safe artifacts from existing Package A/B artifacts and current YAML contract only.
- JSON parse validation and domains hash validation are run separately in Phase 7.

## runtime_behavior_change
- trading behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
STOP_NRR062_PATCHING_NO_SAFE_FIELD
