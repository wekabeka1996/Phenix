# AGENT_REPORT_V1

## verdict
FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE_IDENTIFIED

## problem_framing
Existing scalar calibration failed because the positive replay surface from Package B was not expressible through the current LOW_VOL YAML contract without broad regime-level spillover. Package D established that the existing YAML surface cannot isolate SELL-only plus direction-only plus raw-signal-only behavior, and Package E proved that existing scalar sweeps did not cross the observed reject boundary safely. This package therefore stays offline-only and tests whether a minimal deterministic segment rule, built only from existing structured metadata plus Package B replay rows, can separate the positive replay surface from the negative replay surface without changing YAML, Pydantic models, or runtime gate behavior.

## facts
- Phase 0 pre-change capture stayed on branch `main` at commit `e837f16ff8b6c2fd3fd41a3812c78237cc3a1427` with a dirty worktree already containing unrelated `apps/reference` and `config/aurora` changes before this package began.
- Package A established a canonical `NRR-062` reject cohort of 153 rows, all with structured LOW_VOL metadata.
- Package B established replay results of `TP=33`, `SL=13`, `TIMEOUT=107`, `estimated_net_pnl_quote=391.0476869715`, with positive SELL and direction-only slices and negative BUY and dual regime+direction slices.
- Package D established that current YAML cannot encode SELL-only, direction-only-failure-only, or raw-signal-only segmentation inside LOW_VOL thresholds.
- Package E established that requested existing-field scalar sweeps did not admit any rows and therefore produced `NO_SAFE_EXISTING_FIELD_PATCH`.
- The new offline classifier module is [calibrators/policy_gates/nrr062_segment_logic.py](calibrators/policy_gates/nrr062_segment_logic.py).
- The new focused tests are [tests/calibrators/test_nrr062_segment_logic.py](tests/calibrators/test_nrr062_segment_logic.py).
- All 153 rows were classified by the offline segment logic with `classification_rows=153`, `candidate_rows=79`, `excluded_rows=74`, and `candidate_plus_excluded=153`.
- No row was excluded for missing required fields; `required_structured_fields_complete=true` and `excluded_missing_required_fields=0`.
- Segment class counts are `NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE=79`, `EXCLUDED_BUY_OR_LONG=39`, and `EXCLUDED_DUAL_FAILURE=35`.
- Candidate replay metrics are `rows=79`, `TP=25`, `SL=2`, `TIMEOUT=52`, `estimated_gross_pnl_quote=1122.7695276632`, `estimated_net_pnl_quote=825.2672997047`, `estimated_fees_quote=238.0017823673`, `win_rate=70.88607594936708`, `profit_factor=4.92434390438585`, and `timeout_share=0.6582278481012658`.
- Candidate side distribution is `SELL=79`; candidate symbol distribution is `ETHUSDT=37`, `BTCUSDT=31`, and `XRPUSDT=11`.
- Excluded BUY surface metrics are `rows=39`, `TP=0`, `SL=7`, `TIMEOUT=32`, `estimated_net_pnl_quote=-452.7182366138`, `profit_factor=0.0323963298136789`, and `timeout_share=0.8205128205128205`.
- Excluded dual-failure surface metrics are `rows=52`, `TP=8`, `SL=9`, `TIMEOUT=35`, `estimated_net_pnl_quote=-194.77884318850002`, `profit_factor=0.6008643344283967`, and `timeout_share=0.6730769230769231`.
- The readiness artifact classified the candidate as `FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE` and every configured readiness gate passed.
- This package generated only offline calibrator code, tests, datasets, an implementation sketch, and this report. No YAML or runtime production files were edited by this package.

## inferences
- The minimal segment rule isolates the positive replay surface far more cleanly than any existing-field scalar sweep did.
- The positive Package B signal is not uniformly distributed across LOW_VOL rejects; it concentrates in rejected SELL rows that failed direction confidence only while staying on the raw `signal_score` path.
- The negative BUY surface and the negative dual-failure surface remain excluded by the minimal segment rule, which is exactly the separation that current YAML thresholds could not express.
- Timeout risk remains present, but it is not worse than the broad Package B surface. Candidate timeout share fell from `0.6993464052287581` on the broad cohort to `0.6582278481012658` on the candidate.
- Because the segment rule is not currently expressible in YAML/Pydantic, a future implementation would need to be an explicit runtime/testnet change, not a hidden threshold tweak.

## assumptions
- Package A `nrr062_reject_ledger.json` and Package B `nrr062_counterfactual_replay_results.json` remain the authoritative calibration surface for this package.
- Structured LOW_VOL metadata is more authoritative than free-text `why_chain`, so the classifier intentionally uses structured fields and ignores narrative parsing.
- `COUNTERFACTUAL_TIMEOUT` rows remain admissible for measurement but must be penalized through timeout share and readiness gates.

## unknowns
- Whether the same segment will remain positive on a future config-authoritative runtime bundle.
- Whether stricter fill modeling or a different timeout horizon would materially reduce the candidate edge.
- Whether a future accepted LOW_VOL comparison package will strengthen or weaken confidence in this candidate before runtime implementation.

## segment_rule
- Inclusion: `nrr_code == NRR-062`.
- Inclusion: `regime == LOW_VOLATILITY`.
- Inclusion: side normalized to `SELL/SHORT`.
- Inclusion: violation pattern exactly `direction_confidence_below_threshold`.
- Inclusion: not `regime_confidence_below_threshold`.
- Inclusion: `selected_source == signal_score`.
- Inclusion: `selected_scale == raw_signed_score`.
- Inclusion: `threshold_family == raw_signed_score`.
- Inclusion: structured LOW_VOL metadata present and parse quality complete.
- Inclusion: `gross_tp_bps`, `required_gross_tp_bps_floor`, and `min_rr` present.
- Inclusion: replay row present, `replay_status == READY`, and replay outcome not `COUNTERFACTUAL_INVALID_INPUT` or `COUNTERFACTUAL_NO_MARKET_PATH`.
- Exclusion: `BUY/LONG` rows.
- Exclusion: dual `regime_confidence_below_threshold+direction_confidence_below_threshold` rows.
- Exclusion: missing structured metadata or missing required fields.
- Exclusion: ambiguous TP/SL rows by conservative policy, although this cohort had zero such rows.
- Measurement note: timeout rows are included for candidate measurement and penalized through timeout share rather than dropped.

## candidate_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Candidate Name | NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE | offline-only deterministic segment |
| Rows | 79 | candidate_would_allow=true rows |
| TP Count | 25 | retained positive TP surface |
| SL Count | 2 | limited stop-loss surface |
| TIMEOUT Count | 52 | still material but below broad timeout share |
| Estimated Gross PnL Quote | 1122.7695276632 | gross replay proxy |
| Estimated Net PnL Quote | 825.2672997047 | net replay proxy |
| Estimated Fees Quote | 238.0017823673 | fee drag on candidate rows |
| Win Rate | 70.88607594936708 | positive estimated net / rows |
| Profit Factor | 4.92434390438585 | strong positive asymmetry |
| Timeout Share | 0.6582278481012658 | lower than broad Package B timeout share |
| Median Direction Confidence | -0.00991948 | signed raw score median |
| Median Regime Confidence | 0.6384541511 | materially above LOW_VOL threshold |
| Side Distribution | SELL=79 | pure short-side segment |
| Symbol Distribution | ETHUSDT=37, BTCUSDT=31, XRPUSDT=11 | candidate spread across three symbols |

## excluded_risk_summary
| Excluded Segment | Rows | Net Proxy | Reason Excluded |
| --- | --- | --- | --- |
| BUY/LONG | 39 | -452.7182366138 | negative side surface that current YAML cannot isolate away |
| Dual Regime+Direction Failure | 52 | -194.77884318850002 | negative mixed-confidence surface |
| All Non-Candidate Rows | 74 | -434.21961273320005 | aggregate residual surface outside the candidate |

## broad_vs_candidate
| Metric | Broad Package B | Candidate Segment | Interpretation |
| --- | --- | --- | --- |
| Rows | 153 | 79 | candidate keeps a large but narrower subset |
| TP Count | 33 | 25 | candidate retains most TP rows |
| SL Count | 13 | 2 | candidate removes most SL rows |
| TIMEOUT Count | 107 | 52 | timeout burden remains but shrinks in both count and share |
| Estimated Net PnL Quote | 391.0476869715 | 825.2672997047 | candidate surface is materially stronger than broad cohort |
| Profit Factor | 1.4120756633 | 4.92434390438585 | candidate materially improves replay quality |
| Timeout Share | 0.6993464052287581 | 0.6582278481012658 | candidate is less timeout dominated than broad Package B |

## readiness_gates
| Gate | Passed? | Evidence |
| --- | --- | --- |
| candidate_rows_gte_20 | true | candidate_rows=79 |
| candidate_estimated_net_positive | true | candidate_estimated_net_pnl_quote=825.2672997047 |
| candidate_profit_factor_gt_1_2 | true | candidate_profit_factor=4.92434390438585 |
| candidate_timeout_share_lte_broad | true | candidate_timeout_share=0.6582278481012658; broad_timeout_share=0.6993464052287581 |
| buy_excluded_net_negative | true | buy_excluded_net=-452.7182366138 |
| dual_failure_excluded_net_negative | true | dual_failure_excluded_net=-194.77884318850002 |
| required_structured_fields_complete | true | excluded_missing_required_fields=0 |
| no_yaml_or_runtime_mutation_needed | true | offline calibrator only; no config/runtime mutation paths in this package |

## implementation_sketch
The future implementation sketch is written in [calibrators/datasets/nrr062_segment_logic/NRR062_MINIMAL_RUNTIME_IMPLEMENTATION_SKETCH.md](calibrators/datasets/nrr062_segment_logic/NRR062_MINIMAL_RUNTIME_IMPLEMENTATION_SKETCH.md). It identifies [apps/reference/domains/decision_making/gates/low_vol_cost_floor.py](apps/reference/domains/decision_making/gates/low_vol_cost_floor.py) as the likely runtime owner, explicitly warns that hardcoding segment logic would be a business-rule risk outside YAML/Pydantic SSOT, and recommends a future testnet-only explicit operator override if the next package proceeds. No runtime implementation was added here.

## changes_made
- Added offline helper module [calibrators/policy_gates/nrr062_segment_logic.py](calibrators/policy_gates/nrr062_segment_logic.py).
- Added focused tests [tests/calibrators/test_nrr062_segment_logic.py](tests/calibrators/test_nrr062_segment_logic.py).
- Generated classification, evaluation, comparison, readiness, and implementation-sketch artifacts under [calibrators/datasets/nrr062_segment_logic](calibrators/datasets/nrr062_segment_logic).
- Created this report only.

## validation
- Compile check:
  - command: `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m compileall calibrators/policy_gates/nrr062_segment_logic.py`
  - result: compile completed successfully.
- Focused pytest:
  - command: `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_nrr062_segment_logic.py tests/test_calibrators_import_boundary.py -q`
  - result: `9 passed in 2.99s`.
- Artifact generation:
  - command: `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m calibrators.policy_gates.nrr062_segment_logic`
  - result: `classification=FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE`, `candidate_rows=79`, `candidate_net=825.2672997047`, `candidate_timeout_share=0.6582278481012658`.
- JSON/count validation:
  - command: custom Python validation over `nrr062_segment_classification.json`, `nrr062_segment_replay_evaluation.json`, `nrr062_segment_vs_broad_replay.json`, and `nrr062_segment_readiness_gates.json`
  - result: `json_files_valid=4`, `classification_rows=153`, `candidate_rows=79`, `excluded_rows=74`, `candidate_plus_excluded=153`.
- Config/runtime surface check:
  - command: `git status --short -- config/aurora apps/reference calibrators/policy_gates/nrr062_segment_logic.py tests/calibrators/test_nrr062_segment_logic.py calibrators/datasets/nrr062_segment_logic`
  - result: same pre-existing `apps/reference` and `config/aurora` dirtiness remained visible; new package paths were limited to the offline calibrator, tests, and generated dataset directory.

## runtime_behavior_change
- trading behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- runtime Python changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_NRR_PACKAGE_G_NRR062_TESTNET_SEGMENT_LOGIC_IMPLEMENTATION