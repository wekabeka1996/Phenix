# AGENT_REPORT_V1

## verdict
READONLY_ECONOMICS_COMPLETED_WITH_RESIDUALS

## problem_framing
This package is descriptive economics over a diagnostics-only canonical realized cohort and an observational sidecar close surface. It is not threshold calibration because the canonical close cohort remains sparse, sidecar has no canonical realized close cohort in this window, and 03U did not freeze a config snapshot for authoritative NRR gate-state claims.

## facts
- Pre-analysis repo state: branch `main`, commit `e837f16ff8b6c2fd3fd41a3812c78237cc3a1427`, and dirty worktree before 03V generation.
- The 03U frozen runtime bundle remains `logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z`.
- The canonical realized dataset remains 12 realized rows and 11 exact roundtrips, with `diagnostics_only=true` and `promotion_grade=false`.
- 03V generated `CANONICAL_CLOSED_TRADE_LEDGER.csv`, `CANONICAL_CLOSED_TRADE_LEDGER.md`, `canonical_closed_trade_ledger.json`, `ACCEPTED_CLOSED_TRADE_ECONOMICS_DEEPDIVE.md`, `accepted_closed_trade_economics_deepdive.json`, `SIDECAR_CLOSE_USEFULNESS_DEEPDIVE_READONLY.md`, `sidecar_close_usefulness_deepdive_readonly.json`, `CLOSE_REASON_ECONOMICS_COMPARISON.md`, `close_reason_economics_comparison.json`, `MFE_MAE_PEAK_GIVEBACK_INVENTORY.md`, `mfe_mae_peak_giveback_inventory.json`, and `NRR_CONTEXT_APPENDIX_READONLY.md` under `calibrators/datasets/economics_post_03t_multiday/`.
- Canonical cohort totals are `gross_pnl=171.06727`, `net_pnl=139.18404117`, and `fees=31.88322883`.
- Canonical close reasons are `TP=9`, `SL=1`, and `CLOSE=2`.
- Canonical cohort win/loss counts are `9 wins`, `3 losses`, and `75.0%` win rate.
- Canonical cohort profit factor is `4.6662875634`.
- Fee drag metrics are `fees_per_trade=2.6569357358`, `fees_as_pct_of_total_gross_profit=16.0892371885`, and `fees_as_pct_of_losing_trade_abs_net=28.6212080453`.
- Canonical cohort has `0` gross-positive but net-negative rows, `2` fee-dominated rows, and `0` near-fee-only rows under the explicit descriptive threshold used in 03V.
- Sidecar observational summary is `15 recommendations`, `15 close requests`, `15 reconciled close runtime ids`, `15 observed POSITION_CLOSED rows`, `0 canonical realized sidecar closes`, `observed_net_pnl=-92.86671668`, and `observed_fees=39.27871668`.
- Sidecar observed close reason distribution is `CLOSE=15`.
- Sidecar observed winners/losers are `4 winners` and `11 losers`.
- Sidecar observed fee-dominated closes are `2`.
- MFE/MAE inventory shows `mfe_non_null_rows=0`, `mae_non_null_rows=0`, `peak_edge_non_null_rows=11`, and `giveback_pct_non_null_rows=10`.
- MFE/MAE classification counts are `clean winner=7`, `clean loser=1`, `gave-back winner=2`, and `fee-dominated close=2`.
- NRR appendix confirms `NRR-062 observed_reject_count=153` with structured `selected_source`, `selected_scale`, and `threshold_family` fields present. `NRR-027`, `NRR-028`, `NRR-029`, and `NRR-030` each have `0` observed runtime rejects in this frozen window.
- NRR config provenance remains `live_workspace_yaml` with `frozen_config_snapshot_present=false`.
- Generated 03V JSON artifacts parsed successfully.
- Canonical realized rows were schema-validated successfully against `calibration_realized_trade_dataset_v1`.
- Source snapshot SHA256 checks passed for retained `decision_ledger`, `order_log`, and `trade_lifecycle` files.
- Required pytest passed: `22 passed in 2.90s`.

## inferences
- The canonical realized cohort is sufficient for descriptive economics, but not for promotion-grade calibration decisions.
- TP closes dominate the profitable surface, while canonical `CLOSE` rows are both short BNB trades with negative net pnl and heavy fee drag.
- The sidecar surface remains observational-only because there are no canonical realized sidecar closes and no counterfactual baseline.
- The 03V path-stat inventory is usable only as partial peak-giveback context because canonical MFE/MAE fields remain absent.
- NRR-062 is ready for read-only reject-economics analysis as a runtime cohort, but not for config-authoritative gate-state conclusions or patch promotion.

## assumptions
- `near-fee-only` was defined descriptively as `fees / abs(gross_pnl) >= 0.8` when not already fee-dominated.
- `gave-back winner` was classified only when a joined exact sidecar snapshot had positive `giveback_pct`, `current_edge_usd < peak_edge_usd`, and `peak_edge_usd > gross_pnl`.
- For observed sidecar close rows without explicit gross pnl, `implied_gross_pnl = observed_net_pnl + observed_fees` was used as a descriptive arithmetic reconstruction, not as a new authority surface.
- Regime grouping for canonical realized rows used exact `decision_id`/`rid` matches from frozen decision_ledger, with frozen order_log `ORDER_INTENT` regime fallback when needed.

## unknowns
- Whether a larger post-03T runtime window would materially change the descriptive economics shape.
- Whether alternative terminal-event rows should eventually be canonicalized, since 03V treats only canonical `POSITION_CLOSED` rows as realized closes.
- Whether the current workspace YAML exactly matches the YAML that produced the frozen runtime window.
- Whether observed sidecar closes avoided larger losses or cut winners prematurely, because no counterfactual baseline exists.

## canonical_cohort_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Trade Count | 12 | canonical realized rows only |
| Exact Roundtrip Count | 11 | diagnostics-only cohort |
| Gross PnL | 171.06727 | canonical realized rows only |
| Net PnL | 139.18404117 | canonical realized rows only |
| Fees | 31.88322883 | fees plus commission |
| Win Count | 9 | net pnl > 0 |
| Loss Count | 3 | net pnl < 0 |
| Win Rate | 75.0% | 9 / 12 |
| Profit Factor | 4.6662875634 | sum wins / abs(sum losses) |
| Coverage Grade | SPARSE_DIAGNOSTIC | inherited from 03U realized dataset |
| Promotion Grade | false | builder-valid, not promotion-grade |

## economics_summary
| Segment | Trades | Net PnL | Fees | Win Rate | Profit Factor | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Overall | 12 | 139.18404117 | 31.88322883 | 75.0% | 4.6662875634 | canonical realized cohort |
| BNBUSDT | 5 | 55.79120586 | 14.38529414 | 60.0% | 6.5226135794 | 1 non-exact close present |
| BTCUSDT | 4 | 75.19168914 | 9.88803086 | 100.0% |  | no losing BTC closes in canonical cohort |
| ETHUSDT | 1 | 12.11909301 | 2.56196699 | 100.0% |  | single TP close |
| XRPUSDT | 2 | -3.91794684 | 5.04793684 | 50.0% | 0.859374669 | fees exceed abs(net pnl) |
| TP | 9 | 177.14725021 | 21.01769979 | 100.0% |  | dominant profitable segment |
| SL | 1 | -27.86088972 | 3.37640972 | 0.0% | 0.0 | single XRP long stop-loss |
| CLOSE | 2 | -10.10231932 | 7.48911932 | 0.0% | 0.0 | both are short BNB closes |

## fee_drag_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Total Fees | 31.88322883 | canonical realized cohort only |
| Fees Per Trade | 2.6569357358 | mean per canonical trade |
| Fees as % of Total Gross Profit | 16.0892371885 | descriptive only |
| Fees as % of Losing Trade Abs Net | 28.6212080453 | descriptive only |
| Gross Positive but Net Negative Rows | 0 | no strict fee-flip rows |
| Fee-Dominated Rows | 2 | fees >= abs(gross pnl) |
| Near-Fee-Only Rows | 0 | threshold `fees / abs(gross_pnl) >= 0.8` |

## sidecar_observational_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Sidecar Recommendations | 15 | frozen trade_lifecycle observational surface |
| Sidecar Close Requests | 15 | frozen trade_lifecycle observational surface |
| Reconciled Close Runtime IDs | 15 | frozen sidecar runtime ids |
| Observed POSITION_CLOSED Rows | 15 | order_log rows with `ppsreq:` rid |
| Canonical Realized Sidecar Closes | 0 | remains observational-only |
| Observed Net PnL | -92.86671668 | observational surface only |
| Observed Fees | 39.27871668 | observational surface only |
| Observed Implied Gross PnL | -53.588 | net + fees when explicit gross absent |
| Winner Count | 4 | observational surface only |
| Loser Count | 11 | observational surface only |
| Fee-Dominated Count | 2 | observational surface only |
| Close Reason Distribution | CLOSE=15 | all observed sidecar closes are soft CLOSE rows |

## close_reason_comparison
| Close Reason | Count | Net PnL | Fees | Avg PnL | Notes |
| --- | --- | --- | --- | --- | --- |
| TP | 9 | 177.14725021 | 21.01769979 | 19.6830278011 | 3 BNB, 4 BTC, 1 ETH, 1 XRP; all profitable |
| SL | 1 | -27.86088972 | 3.37640972 | -27.86088972 | single XRP long stop-loss |
| CLOSE | 2 | -10.10231932 | 7.48911932 | -5.05115966 | both short BNB closes; one non-exact roundtrip |

## mfe_mae_giveback_summary
| Class | Count | Notes |
| --- | --- | --- |
| clean winner | 7 | positive net pnl without positive giveback signal |
| clean loser | 1 | XRP SL close |
| gave-back winner | 2 | positive giveback snapshot and peak edge above realized gross |
| fee-dominated close | 2 | both canonical CLOSE rows |

## nrr_context_appendix
| Gate | Runtime Cohort | Structured Fields | Config Authority | Patch Ready? |
| --- | --- | --- | --- | --- |
| NRR-062 | 153 observed rejects | selected_source, selected_scale, threshold_family | conditional_live_yaml | false |
| NRR-027 | 0 observed rejects | none | conditional_live_yaml | false |
| NRR-028 | 0 observed rejects | none | conditional_live_yaml | false |
| NRR-029 | 0 observed rejects | none | conditional_live_yaml | false |
| NRR-030 | 0 observed rejects | none | conditional_live_yaml | false |

## readiness_classification
- Economics cohort readiness: DESCRIPTIVE_ONLY
- Sidecar usefulness readiness: OBSERVATIONAL_ONLY
- NRR readiness: NRR062_READONLY_INVENTORY_READY + CONFIG_AUTHORITY_GAP

## changes_made
- Added offline generator `artifacts/_tmp/phenix_03v_readonly_calibration.py`.
- Generated 03V ledger, economics, fee-drag, sidecar, close-reason, MFE/MAE, and NRR appendix artifacts only.
- Created this report only.

## validation
- JSON/schema/hash validation:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -` custom validation pass
  - result: `json_files_valid=8`, `canonical_realized_rows_schema_valid=12`, and all retained source snapshot SHA256 checks passed.
- Pytest:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/calibrators/test_realized_outcome_builder.py tests/calibrators/test_runtime_close_coverage_audit.py tests/calibrators/test_close_surface_reconciliation_audit.py tests/test_calibrators_import_boundary.py -q`
  - result: `22 passed in 2.90s`.
- Editor diagnostics:
  - `artifacts/_tmp/phenix_03v_readonly_calibration.py` reported no errors.

## runtime_behavior_change
- trading behavior changed: no
- order lifecycle semantics changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_NRR_PACKAGE_A_NRR062_READONLY_REJECT_ECONOMICS
