# AGENT_REPORT_V1

## verdict
READONLY_COUNTERFACTUAL_REPLAY_DATASET_WITH_TIMEOUT_DOMINATED_SIGNAL

## problem_framing
This package builds the first explicit offline counterfactual replay dataset for the 153 canonical NRR-062 LOW_VOL_COST_FLOOR rejects identified in package A. The package is still read-only. It uses frozen reject-row geometry from the 03U order log, frozen decision_ledger quantity when present, and later recorder OHLC bars only after the reject timestamp. The output is a deterministic causal proxy, not live execution truth, and it is intended to tighten calibration readiness rather than authorize a threshold patch.

## facts
- Package B was executed on branch `main` at commit `e837f16ff8b6c2fd3fd41a3812c78237cc3a1427` with an already-dirty worktree; this package did not modify any YAML or runtime production surfaces.
- Inputs used were `calibrators/datasets/nrr062_readonly_reject_economics/nrr062_reject_ledger.json`, `calibrators/datasets/nrr062_readonly_reject_economics/nrr062_counterfactual_availability_audit.json`, frozen `logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/order_log_v1.jsonl`, frozen `logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/shadow_telemetry/decision_ledger_v1.jsonl`, and recorder CSVs under `data/recorder/2026-05-11`, `2026-05-12`, and `2026-05-13`.
- The replay contract uses reject-row `metadata.low_vol_cost_floor.entry_price` as the entry geometry anchor.
- Replay scanning starts only at the first full recorder bar whose inferred open time is strictly greater than the reject timestamp, so mixed bars containing pre-reject time are excluded.
- TP uses raw reject-row `target_price` when present, else derives from entry plus gross TP bps. SL uses raw reject-row `stop_price` when present, else derives from entry plus explicit SL bps or gross TP bps divided by min RR.
- The replay timeout horizon is explicit at 120 minutes, and timeout exits use the first recorder bar close whose close timestamp is at or beyond the horizon.
- Same-bar TP and SL ambiguity is handled explicitly as `COUNTERFACTUAL_AMBIGUOUS_TP_SL` with no gross or net assignment, but this package observed zero such rows.
- All 153 canonical reject rows were replay-ready, all 153 had recorder market path coverage, and all 153 selected the 180-second recorder timeframe.
- Result distribution is `COUNTERFACTUAL_TP=33`, `COUNTERFACTUAL_SL=13`, `COUNTERFACTUAL_TIMEOUT=107`, `COUNTERFACTUAL_AMBIGUOUS_TP_SL=0`, `COUNTERFACTUAL_NO_MARKET_PATH=0`, and `COUNTERFACTUAL_INVALID_INPUT=0`.
- Aggregate replay economics are `estimated_gross_pnl_quote=966.9646780049`, `estimated_net_pnl_quote=391.0476869715`, `estimated_fees_quote=460.7335928272`, `estimated_win_rate=51.633987`, and `profit_factor=1.4120756633`.
- Symbol replay net proxy is `BTCUSDT=341.7965353265`, `ETHUSDT=44.5422742194`, and `XRPUSDT=4.7088774256`.
- Side replay net proxy is sharply asymmetric: `SELL=843.7659235853` versus `BUY=-452.7182366138`.
- Violation-pattern replay net proxy is also asymmetric: `direction_confidence_below_threshold=585.82653016` versus `regime_confidence_below_threshold+direction_confidence_below_threshold=-194.7788431885`.
- Regime-confidence segmentation is mixed: `>=0.39` is materially positive at `603.6808718121`, while `0.25-0.35` is negative at `-161.274376603` and `0.15-0.25` is negative at `-26.0351046684`.
- The final protective-vs-overblocking classification is `INCONCLUSIVE_TIMEOUT_DOMINATED` with rationale `timeout rows dominate the replay surface, so directional conclusions remain weak`.

## inferences
- Package B closes the main package A blocker: the canonical 153-row NRR-062 cohort now has an explicit deterministic counterfactual replay dataset instead of recorder-path availability only.
- The replay surface is not data-quality-limited. There are zero invalid-input rows, zero missing-market-path rows, and zero same-bar ambiguity rows under the strict first-full-bar policy.
- The strongest positive replay proxy sits on rejected SELL rows and on the direction-only failure pattern. The BUY side is strongly negative, and the dual regime-plus-direction failure pattern is also negative.
- The overall cohort is therefore not one-sided. The combined replay proxy is net positive, but the surface is heavily timeout-dominated at 107 of 153 rows, so a broad overblocking claim would overstate what this contract proves.
- Package B weakens any blanket protective reading from package A because a non-trivial positive replay proxy exists on a large subset of rows, especially SELL and direction-only failures.
- Package B still does not authorize threshold patching because the evidence is mixed by segment, dominated by timeout outcomes, and the 03U config surface remains unfrozen.

## assumptions
- Entry price is the structured reject-row LOW_VOL entry reference, not a live fill price.
- Recorder bars are close-timestamped OHLC bars, so the replay deliberately starts only once a full post-reject bar exists.
- Quote-unit PnL, fee, and slippage proxies are computed from decision_ledger quantity when present and use explicit bps costs from LOW_VOL metadata.
- Timeout close uses bar close as a deterministic proxy and does not claim intrabar execution fidelity.
- This package makes no claim that the replayed result would match live exchange execution, queue position, or spread dynamics.

## unknowns
- Whether the current 120-minute replay horizon is the economically decisive horizon for production calibration, given that 107 rows timed out before TP or SL.
- Whether a frozen config snapshot of the exact 03U runtime surface would materially alter enablement or threshold interpretation for these rows.
- Whether a longer frozen runtime window would produce enough accepted LOW_VOL closes to support a like-for-like accepted-versus-rejected comparison.
- Whether the positive SELL-side replay proxy would survive stricter fill modeling, broader fee treatment, or a different horizon contract.

## replay_contract_summary
| Metric | Value | Notes |
| --- | --- | --- |
| Canonical Replay Rows | 153 | same strict package A reject cohort |
| Replay Ready Rows | 153 | zero missing geometry or timestamp rows |
| Recorder Market Path Rows | 153 | zero missing first-full-bar or horizon-bar rows |
| Recorder Timeframe | 180s for 153 | no fallback to 300s or 900s needed |
| Entry Price Source | reject-row low_vol entry_price | geometry anchor only |
| Bar Start Rule | first full bar after reject | avoids pre-reject leakage |
| TP/SL Ambiguity Rows | 0 | explicit conservative ambiguity policy still observed zero hits |
| Timeout Horizon | 120m | explicit contract, not a silent default |
| Fee Model | structured round_trip_fee_bps | explicit LOW_VOL metadata |
| Slippage Model | structured slippage_buffer_bps | explicit LOW_VOL metadata |

## replay_outcome_summary
| Outcome Class | Count | Share | Notes |
| --- | --- | --- | --- |
| COUNTERFACTUAL_TP | 33 | 21.568627% | target hit before stop or timeout |
| COUNTERFACTUAL_SL | 13 | 8.496732% | stop hit before target or timeout |
| COUNTERFACTUAL_TIMEOUT | 107 | 69.934641% | neither TP nor SL within 120m horizon |
| COUNTERFACTUAL_AMBIGUOUS_TP_SL | 0 | 0.0% | same-bar ambiguity did not occur |
| COUNTERFACTUAL_NO_MARKET_PATH | 0 | 0.0% | recorder coverage complete |
| COUNTERFACTUAL_INVALID_INPUT | 0 | 0.0% | reject geometry complete |

## replay_economics_by_segment
| Segment | Rows | TP | SL | Timeout | Net PnL Quote | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| overall | 153 | 33 | 13 | 107 | 391.0476869715 | net-positive aggregate, but timeout-dominated |
| symbol:BTCUSDT | 47 | 12 | 1 | 34 | 341.7965353265 | strongest positive symbol surface |
| symbol:ETHUSDT | 76 | 15 | 7 | 54 | 44.5422742194 | large surface, only weakly positive after costs |
| symbol:XRPUSDT | 30 | 6 | 5 | 19 | 4.7088774256 | nearly flat after costs |
| side:SELL | 114 | 33 | 6 | 75 | 843.7659235853 | dominant positive surface |
| side:BUY | 39 | 0 | 7 | 32 | -452.7182366138 | materially negative surface |
| violation:direction_confidence_below_threshold | 101 | 25 | 4 | 72 | 585.82653016 | positive replay proxy on direction-only failures |
| violation:regime_confidence_below_threshold+direction_confidence_below_threshold | 52 | 8 | 9 | 35 | -194.7788431885 | negative replay proxy on dual failures |

## protective_vs_overblocking
Classification: INCONCLUSIVE_TIMEOUT_DOMINATED.

Evidence:
- The cohort is no longer missing counterfactual truth. All 153 rows were replayed under one explicit causal contract.
- The replay result is not uniformly protective because aggregate net proxy is positive, SELL rows are strongly positive, and direction-only failures are positive.
- The replay result is not safely overblocking either because 107 of 153 rows timed out within the explicit 120m horizon and BUY rows are strongly negative.
- The bounded conclusion is therefore mixed and timeout-dominated rather than purely protective or purely excessive.

## calibration_readiness
Readiness classification: NEEDS_CONFIG_SNAPSHOT_FREEZE + NEEDS_ACCEPTED_LOW_VOL_COMPARISON.

Threshold patching:
- PATCH_READY: no
- READONLY_ONLY: yes

Primary blockers:
- The replay surface is mixed by segment and dominated by timeout outcomes, so it does not yet justify a one-way threshold move.
- The 03U runtime bundle still lacks a frozen config snapshot, so gate-state authority remains conditional on live workspace YAML.
- The accepted canonical realized cohort from 03V still contains zero LOW_VOL closes, so this package cannot compare blocked LOW_VOL rejects against accepted LOW_VOL admissions on the same regime surface.

Secondary note:
- Longer runtime is no longer the primary blocker for package B itself because all 153 rows replayed successfully, but a longer window may still be the only practical path to a non-empty accepted LOW_VOL close cohort if accepted-low-vol comparison remains required.

## changes_made
- Added offline helper `artifacts/_tmp/phenix_nrr062_counterfactual_replay_dataset.py`.
- Added focused tests `tests/tools/test_nrr062_counterfactual_replay_dataset.py`.
- Generated `nrr062_counterfactual_replay_contract.json`, `NRR062_COUNTERFACTUAL_REPLAY_CONTRACT.md`, `nrr062_counterfactual_replay_inputs.json`, `NRR062_COUNTERFACTUAL_REPLAY_INPUTS.csv`, `NRR062_COUNTERFACTUAL_REPLAY_INPUTS.md`, `nrr062_counterfactual_replay_results.json`, `NRR062_COUNTERFACTUAL_REPLAY_RESULTS.csv`, `NRR062_COUNTERFACTUAL_REPLAY_RESULTS.md`, `nrr062_counterfactual_replay_economics.json`, `NRR062_COUNTERFACTUAL_REPLAY_ECONOMICS.md`, `nrr062_protective_vs_overblocking_readonly.json`, and `NRR062_PROTECTIVE_VS_OVERBLOCKING_READONLY.md` under `calibrators/datasets/nrr062_counterfactual_replay_dataset/`.
- Created this report only.

## validation
- Focused replay pytest:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/tools/test_nrr062_counterfactual_replay_dataset.py -q`
  - result: `6 passed in 0.56s`.
- Replay dataset generation:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe artifacts/_tmp/phenix_nrr062_counterfactual_replay_dataset.py`
  - result: `input_rows=153`, `ready_rows=153`, `COUNTERFACTUAL_TP=33`, `COUNTERFACTUAL_SL=13`, `COUNTERFACTUAL_TIMEOUT=107`, `classification=INCONCLUSIVE_TIMEOUT_DOMINATED`, `estimated_net_pnl_quote=391.0476869715`.
- Import boundary regression:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/neocortex/contract/test_causal_time_provenance.py::TestPhase0BoundaryRegression::test_causal_time_import_does_not_load_legacy_modules -q`
  - result: `1 passed in 1.65s`.
- No YAML, runtime config, or production registry files were edited by this package.

## runtime_behavior_change
- trading behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_NRR_PACKAGE_C_CONFIG_SNAPSHOT_AND_ACCEPTED_LOW_VOL_COMPARISON
