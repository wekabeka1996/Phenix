# AGENT_REPORT_V1

## verdict
READONLY_NRR062_ANALYSIS_WITH_RESIDUALS

## problem_framing
This package is reject economics and calibration readiness analysis, not threshold calibration. The canonical surface is a frozen runtime reject cohort plus descriptive accepted-close context. Rejected rows do not carry realized PnL, and although later recorder bars are available, no causal replay dataset or realized counterfactual outcome has been built in this package. The 03U bundle also did not freeze the config surface, so gate-state authority remains conditional on live workspace YAML.

## facts
- Pre-analysis repo capture remained branch `main` at commit `e837f16ff8b6c2fd3fd41a3812c78237cc3a1427` with a dirty worktree before package A work began.
- Inputs read for this package were the 03U report, the 03V report, `calibrators/datasets/nrr_inventory_post_03t_multiday/nrr_reject_inventory_readonly.json`, `calibrators/datasets/economics_post_03t_multiday/accepted_closed_trade_economics_deepdive.json`, `artifacts/calibration_datasets/_post_03t_multiday_objective/trade_decisions.jsonl`, and `artifacts/calibration_datasets/_post_03t_multiday_realized_outcome/realized_trades.jsonl`.
- The canonical NRR-062 reject cohort in the frozen 03U order log is exactly 153 `DECISION_INTENT_REJECTED` rows with `nrr_code=NRR-062`.
- The rebuilt row-level ledger accounts for all 153 rejects and matches `observed_reject_count=153` from the authoritative 03U NRR inventory.
- All 153 canonical reject rows contain complete structured LOW_VOL metadata under `order_log.metadata.low_vol_cost_floor`, so `structured_fields_present_rows=153` and `parse_quality=STRUCTURED_METADATA_COMPLETE` for all rows.
- All 153 rows join by `rid` to a frozen decision_ledger row and to an objective trade_decisions row.
- Zero NRR-062 reject rows produced a trade_lifecycle hit in the 03U frozen `trade_lifecycle.jsonl` surface.
- Workspace `data/recorder` exists and retains dated recorder CSVs for `2026-05-11`, `2026-05-12`, and `2026-05-13` for `BTCUSDT`, `ETHUSDT`, and `XRPUSDT`, allowing a later-market-path availability classification for all 153 rows.
- Counterfactual availability class counts are `MARKET_PATH_AVAILABLE_ONLY=153`, `COUNTERFACTUAL_AVAILABLE=0`, `TRACE_ONLY_NO_OUTCOME=0`, `INSUFFICIENT_TIMESTAMP=0`, and `INSUFFICIENT_IDENTITY=0`.
- Reject symbol distribution is `ETHUSDT=76`, `BTCUSDT=47`, and `XRPUSDT=30`.
- Reject side distribution is `SELL=114` and `BUY=39`; normalized position-side distribution is `SHORT=114` and `LONG=39`.
- Reject regime distribution is `LOW_VOLATILITY=153`.
- Selected direction-confidence source is `signal_score` for all 153 rows; selected scale is `raw_signed_score` for all 153 rows; threshold family is `raw_signed_score` for all 153 rows.
- Required gross TP floor falls entirely in the `20-30bps` bucket; gross TP bps falls entirely in the `75-100bps` bucket.
- Direction-confidence buckets are `<0.01=130` and `0.01-0.05=23`.
- Regime-confidence buckets are `>=0.39=103`, `0.25-0.35=31`, `0.15-0.25=12`, and `0.35-0.39=7`.
- Violation patterns are `direction_confidence_below_threshold=101` and `regime_confidence_below_threshold|direction_confidence_below_threshold=52`.
- The accepted canonical realized cohort from 03V remains 12 trades, 11 exact roundtrips, net pnl `+139.18404117`, and fees `31.88322883`.
- Accepted realized symbol distribution is `BNBUSDT=5`, `BTCUSDT=4`, `ETHUSDT=1`, `XRPUSDT=2`.
- Accepted realized normalized side distribution is `LONG=4` and `SHORT=8`.
- Accepted realized regime distribution is `MEAN_REVERSION=6`, `TREND_DOWN=4`, `TREND_UP=2`, and `LOW_VOLATILITY=0`.
- Accepted close reason distribution remains `TP=9`, `SL=1`, and `CLOSE=2`.
- The legacy 03U NRR inventory reported mixed-surface symbol and side totals summing to 234 because it aggregated broader mention surfaces in addition to the canonical reject cohort. This package rebuilds a strict row-level ledger on the canonical 153-row order_log reject surface only.
- Generated JSON outputs parse successfully, row counts reconcile to the source NRR inventory, and focused pytest completed `72 passed in 5.59s` after aligning stale test-only expectations to the current low-vol gate contract.

## inferences
- NRR-062 has a strong descriptive runtime cohort and complete structured reject metadata, so the package is sufficient for read-only reject economics preparation.
- The dominant descriptive failure mode is direction confidence, not missing economics geometry, because all 153 rows carried usable gross TP and RR geometry while 101 rows failed only direction confidence and 52 failed both regime and direction confidence.
- ETHUSDT is the largest blocked surface in this window, while BNBUSDT had accepted canonical closes but no canonical NRR-062 rejects.
- The accepted closed cohort provides context for symbol and side mix, but it does not provide a comparable LOW_VOL accepted-close cohort because accepted LOW_VOL canonical closes are zero in the 03V realized dataset.
- Later market bars are available for every reject row, but this package does not prove any rejected trade would have won, lost, or timed out because no counterfactual replay/outcome join was executed here.
- Protective vs overblocking cannot be resolved from this package alone; only readiness and descriptive structure can be assessed safely.

## assumptions
- `MARKET_PATH_AVAILABLE_ONLY` means a symbol-matched recorder CSV retained bars later than the reject timestamp; it does not imply replayed TP/SL/timeout outcomes.
- BUY rejects were normalized to LONG and SELL rejects to SHORT only for accepted-vs-rejected comparison against the realized close cohort.
- The canonical reject ledger is anchored to frozen `order_log_v1.jsonl` rows only; broader why-chain mention surfaces were treated as supplemental context and not as authoritative row counts.
- Accepted cohort comparisons use the 03V descriptive economics artifact as the authoritative accepted-close summary for this package.

## unknowns
- Whether the 153 later-market-path rows would have produced net-positive, net-negative, or neutral realized outcomes under a causal replay.
- Whether the live workspace YAML exactly matches the config that produced the frozen 03U runtime window.
- Whether a larger LOW_VOL accepted-close cohort would emerge in a longer frozen post-03T window.
- Whether trade_lifecycle intentionally omits this reject class or whether an observability gap remains for rejected attempts.

## reject_cohort_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Canonical Reject Rows | 153 | frozen order_log `DECISION_INTENT_REJECTED` rows with `nrr_code=NRR-062` |
| Structured Fields Present Rows | 153 | all rows parsed from `metadata.low_vol_cost_floor` |
| Parse Quality | STRUCTURED_METADATA_COMPLETE for 153 | no free-text-only rows in canonical ledger |
| Decision Ledger Present Rows | 153 | all rows join by `rid` |
| Objective Rows Present | 153 | all rows join by `rid` |
| Trade Lifecycle Hit Rows | 0 | no reject rows found in frozen trade_lifecycle surface |
| Market Path Available Rows | 153 | later recorder bars exist by symbol/timestamp |
| Selected Source | signal_score for 153 | 100% of canonical reject cohort |
| Selected Scale | raw_signed_score for 153 | 100% of canonical reject cohort |
| Threshold Family | raw_signed_score for 153 | 100% of canonical reject cohort |
| Median Required Gross TP Floor | 26.0 bps | all rows in `20-30bps` bucket |
| Median Gross TP Bps | 79.375 bps | all rows in `75-100bps` bucket |
| Median Min RR | 1.2 | threshold floor from structured metadata |

## reject_distribution
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| symbol:ETHUSDT | 76 | 49.673203% | largest blocked symbol surface |
| symbol:BTCUSDT | 47 | 30.718954% | second-largest blocked symbol surface |
| symbol:XRPUSDT | 30 | 19.607843% | remaining blocked symbol surface |
| side:SELL | 114 | 74.509804% | raw reject side from order_log |
| side:BUY | 39 | 25.490196% | raw reject side from order_log |
| regime:LOW_VOLATILITY | 153 | 100.0% | canonical NRR-062 regime surface |
| selected_source:signal_score | 153 | 100.0% | no alternative selected source observed |
| selected_scale:raw_signed_score | 153 | 100.0% | no normalized scale selected in runtime rejects |
| threshold_family:raw_signed_score | 153 | 100.0% | same threshold family across cohort |
| direction_confidence_bucket:<0.01 | 130 | 84.96732% | dominant micro-score weakness bucket |
| direction_confidence_bucket:0.01-0.05 | 23 | 15.03268% | residual micro-score weakness bucket |
| regime_confidence_bucket:>=0.39 | 103 | 67.320261% | regime threshold often passed while direction still failed |
| violation:direction_confidence_below_threshold | 101 | 66.013072% | direction-only failure pattern |
| violation:regime_confidence_below_threshold+direction_confidence_below_threshold | 52 | 33.986928% | dual-failure pattern |

## accepted_vs_rejected
| Dimension | Accepted Closed | NRR062 Rejected | Notes |
| --- | --- | --- | --- |
| symbol:BNBUSDT | 5 (41.666667%) | 0 (0.0%) | accepted canonical closes exist, no canonical NRR-062 rejects |
| symbol:BTCUSDT | 4 (33.333333%) | 47 (30.718954%) | similar share, but rejected rows have no realized outcome |
| symbol:ETHUSDT | 1 (8.333333%) | 76 (49.673203%) | reject cohort is heavily ETH-skewed |
| symbol:XRPUSDT | 2 (16.666667%) | 30 (19.607843%) | moderate reject share |
| side:LONG | 4 (33.333333%) | 39 (25.490196%) | reject side normalized from BUY |
| side:SHORT | 8 (66.666667%) | 114 (74.509804%) | reject side normalized from SELL |
| strategy_id:aurora | 12 (100.0%) | 153 (100.0%) | single-strategy comparison only |
| regime:LOW_VOLATILITY | 0 (0.0%) | 153 (100.0%) | no canonical accepted LOW_VOL closes in current realized cohort |
| accepted_close_reason:TP | 9 (75.0%) | counterfactual_unavailable | accepted outcome context only |
| accepted_close_reason:SL | 1 (8.333333%) | counterfactual_unavailable | accepted outcome context only |
| accepted_close_reason:CLOSE | 2 (16.666667%) | counterfactual_unavailable | accepted outcome context only |

## counterfactual_availability
| Class | Count | Meaning |
| --- | --- | --- |
| COUNTERFACTUAL_AVAILABLE | 0 | no reject row has causal replay or realized outcome join in this package |
| MARKET_PATH_AVAILABLE_ONLY | 153 | later recorder bars exist, but no replay/outcome join was executed |
| TRACE_ONLY_NO_OUTCOME | 0 | superseded by recorder coverage in this package |
| INSUFFICIENT_TIMESTAMP | 0 | all canonical reject rows retain usable timestamps |
| INSUFFICIENT_IDENTITY | 0 | all canonical reject rows retain usable `rid` identity |

## protective_vs_overblocking
Classification: INCONCLUSIVE_NO_COUNTERFACTUAL.

Evidence:
- 153 canonical reject rows are real runtime rejects with complete structured LOW_VOL metadata.
- 153 rows have later recorder bars, so a replay dataset is feasible.
- 0 rows have realized counterfactual outcomes in this package, 0 rows have reject-specific trade_lifecycle outcomes, and accepted LOW_VOL canonical closes are 0.
- Therefore the package supports neither a protective-signal claim nor an overblocking claim.

Secondary caveat:
- 03U did not freeze config, so enabled/disabled gate-state claims remain conditional on live workspace YAML even though runtime reject rows themselves are authoritative.

## calibration_readiness
Readiness classification: NEEDS_COUNTERFACTUAL_REPLAY + NEEDS_CONFIG_SNAPSHOT_FREEZE.

Blockers:
- No causal replay or realized counterfactual dataset exists for the 153 rows.
- No frozen config snapshot exists for the 03U runtime bundle.
- Accepted LOW_VOL canonical close cohort is empty in the 03V realized dataset.

Patch readiness:
- PATCH_READY: no
- READONLY_ONLY: yes
- NEEDS_MORE_RUNTIME: not the primary blocker for this package; the primary blocker is replayed counterfactual truth

## changes_made
- Added offline helper `artifacts/_tmp/phenix_nrr062_readonly_reject_economics.py`.
- Generated `NRR062_REJECT_LEDGER.csv`, `NRR062_REJECT_LEDGER.md`, `nrr062_reject_ledger.json`, `NRR062_REJECT_DISTRIBUTION.md`, `nrr062_reject_distribution.json`, `NRR062_ACCEPTED_VS_REJECTED_COMPARISON.md`, `nrr062_accepted_vs_rejected_comparison.json`, `NRR062_COUNTERFACTUAL_AVAILABILITY_AUDIT.md`, and `nrr062_counterfactual_availability_audit.json` under `calibrators/datasets/nrr062_readonly_reject_economics/`.
- Created this report only.
- Aligned stale test-only expectations in `tests/tools/test_calibrate_nrr062_historical.py` to the current low-vol gate contract so focused validation could run green without changing runtime behavior.

## validation
- Generation:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe artifacts/_tmp/phenix_nrr062_readonly_reject_economics.py`
  - result: `reject_rows=153`, `inventory_observed_reject_count=153`, `structured_fields_present_rows=153`, `MARKET_PATH_AVAILABLE_ONLY=153`.
- JSON/count validation:
  - custom Python validation pass over `nrr062_reject_ledger.json`, `nrr062_reject_distribution.json`, `nrr062_accepted_vs_rejected_comparison.json`, and `nrr062_counterfactual_availability_audit.json`
  - result: `json_files_valid=4`, `expected_nrr062_reject_rows=153`, `actual_reject_rows=153`, `structured_fields_present_rows=153`.
- Focused pytest:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/test_calibrators_import_boundary.py tests/tools/test_capture_nrr062_fresh_cohort.py tests/tools/test_calibrate_nrr062_historical.py tests/test_calibrate_low_vol_cost_floor.py tests/domains/decision_making/test_low_vol_cost_floor_gate.py -q`
  - result: `72 passed in 5.59s`.
- Editor diagnostics:
  - `artifacts/_tmp/phenix_nrr062_readonly_reject_economics.py` reported no errors.
  - `tests/tools/test_calibrate_nrr062_historical.py` reported no errors.
- No YAML/config files were edited by this package. Existing config/YAML dirtiness remained pre-existing in the repo worktree and was not modified by the package-scoped helper/artifact/report changes above.

## runtime_behavior_change
- trading behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_NRR_PACKAGE_B_NRR062_COUNTERFACTUAL_REPLAY_DATASET
