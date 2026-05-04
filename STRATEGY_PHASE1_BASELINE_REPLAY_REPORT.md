# AGENT_REPORT_V1

## Executive Verdict

ANALYSIS_ONLY

## Executive Summary

Phase 1 baseline replay completed without changing production code, configs, assignments, arbitration, execution, risk, or decision policy. The safe baseline engines were the two calibrators. The live md_amr baseline ran on XRPUSDT only. Offline candidate baselines ran on ETHUSDT and SOLUSDT for md_amr, plus DOGEUSDT for mean_reversion using an explicit offline study registry artifact. All results remain signal-surface and bar-proxy economic approximations only; none should be interpreted as execution-realized PnL.

The current package does not justify Phase 2 yet. Md_amr baseline tooling is good enough to replay the current profile but not enough to search the requested non-weight aggression dimensions without a small patch. Mean_reversion has a workable offline candidate baseline engine, but still has no live-assigned surface under current checked-in SSOT.

## Files Changed

- STRATEGY_CALIBRATION_PHASE1_TOOL_ADEQUACY_REPORT.md
- STRATEGY_PHASE1_BASELINE_REPLAY_REPORT.md
- STRATEGY_PHASE1_AGGRESSION_SEARCH_GAP_REPORT.md
- artifacts/strategy_calibration/phase1/offline_candidate_registry.yaml
- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.json
- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.csv
- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.json
- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.csv
- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.json
- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.csv
- Generated baseline run directories under `artifacts/strategy_calibration/phase1/` for XRPUSDT, ETHUSDT, SOLUSDT, and DOGEUSDT.

## Files Inspected

- config/aurora/strategies.yaml
- config/aurora/strategies/md_amr.yaml
- config/aurora/strategies/mean_reversion.yaml
- tools/calibration/calibrate_mean_reversion_params.py
- tools/forensics/mr_signal_surface_audit.py
- tools/calibration/calibrate_md_amr_weights.py
- tools/analysis/md_amr_integrated_validation.py
- tools/forensics/full_surface_calibration.py
- tests/tools/test_mean_reversion_param_calibrator.py
- tests/tools/test_md_amr_weight_calibrator.py
- tests/tools/test_md_amr_integrated_validation.py
- artifacts/strategy_calibration/phase1/* baseline outputs

## Tools Classified And Verdict Per Tool

| Tool | Verdict |
| --- | --- |
| tools/calibration/calibrate_mean_reversion_params.py | REUSE_AS_IS |
| tools/forensics/mr_signal_surface_audit.py | QUARANTINE |
| tools/calibration/calibrate_md_amr_weights.py | REUSE_AS_IS |
| tools/analysis/md_amr_integrated_validation.py | NOT_RELEVANT |
| tools/forensics/full_surface_calibration.py | QUARANTINE |

Machine-readable adequacy matrix:

- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.json
- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.csv

## Baseline Replay Surfaces Run

| Surface | Live status | Date range | Tool | Tool verdict |
| --- | --- | --- | --- | --- |
| md_amr / XRPUSDT / 900 | LIVE_ASSIGNED | 2026-02-08..2026-05-01 | calibrate_md_amr_weights.py | NO_GO_CANDIDATE |
| md_amr / ETHUSDT / 900 | NOT_LIVE_ASSIGNED | 2026-02-08..2026-05-01 | calibrate_md_amr_weights.py | NO_GO_CANDIDATE |
| md_amr / SOLUSDT / 900 | NOT_LIVE_ASSIGNED | 2026-02-08..2026-05-01 | calibrate_md_amr_weights.py | NO_GO_CANDIDATE |
| mean_reversion / DOGEUSDT / 300 | NOT_LIVE_ASSIGNED | 2026-03-05..2026-05-01 | calibrate_mean_reversion_params.py with explicit study registry | GO_CANDIDATE |

Machine-readable baseline surface summary:

- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.json
- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.csv

## Baseline Summary Per Strategy / Symbol / Regime

### md_amr / XRPUSDT / 900 / LIVE_ASSIGNED

- Baseline rows: 6,533 feature-ready rows across the full recorder range.
- Train baseline: 76 trades, net return ratio `-0.15097`, profit factor `0.5656`, max drawdown ratio `0.17775`.
- Validation baseline: 21 trades, net return ratio `-0.05923`, profit factor `0.3830`.
- Forward baseline: 16 trades, net return ratio `-0.02670`, profit factor `0.4540`, average holding `14.44` bars.
- Regime-level replay: trades concentrated in `MEAN_REVERSION` and `TREND_DOWN`; `LOW_VOLATILITY`, `TREND_UP`, and `UNCERTAIN` were blocked with non-zero regime block counts. Detailed breakdown: `artifacts/strategy_calibration/phase1/md_amr_xrp_live/per_regime_analysis.json`.

### md_amr / ETHUSDT / 900 / NOT LIVE ASSIGNED

- Baseline rows: 6,194 feature-ready rows across the full recorder range.
- Train baseline: 153 trades, net return ratio `-0.26533`, profit factor `0.4768`.
- Validation baseline: 24 trades, net return ratio `-0.05626`, profit factor `0.3426`.
- Forward baseline: 5 trades, net return ratio `+0.00081`, profit factor `1.0852`, average holding `14.00` bars.
- Regime-level replay: sparse trading across `MEAN_REVERSION`, `TREND_DOWN`, and `TREND_UP`; no trades in `LOW_VOLATILITY` or `HIGH_VOLATILITY`. Detailed breakdown: `artifacts/strategy_calibration/phase1/md_amr_eth_candidate/per_regime_analysis.json`.

### md_amr / SOLUSDT / 900 / NOT LIVE ASSIGNED

- Baseline rows: 6,194 feature-ready rows across the full recorder range.
- Train baseline: 15 trades, net return ratio `-0.01297`, profit factor `0.8237`.
- Validation baseline: 4 trades, net return ratio `-0.00189`, profit factor `0.6537`.
- Forward baseline: 0 trades, net return ratio `0.0`; the current profile still emitted 46 forward signals but opened no completed baseline trades.
- Regime-level replay: no completed baseline trades in any regime; `TREND_DOWN`, `TREND_UP`, and `UNCERTAIN` recorded regime block counts. Detailed breakdown: `artifacts/strategy_calibration/phase1/md_amr_sol_candidate/per_regime_analysis.json`.

### mean_reversion / DOGEUSDT / 300 / NOT LIVE ASSIGNED

- Baseline rows: 13,914 recorder rows; calibrator-required contiguous history threshold `66` rows.
- Scope note: current checked-in SSOT still has no active mean_reversion assignment. This run used `artifacts/strategy_calibration/phase1/offline_candidate_registry.yaml` only to define offline candidate scope; it must not be described as live.
- Train baseline: 39 trades, net return ratio `-0.02365`, profit factor `0.3772`.
- Validation baseline: 33 trades, net return ratio `-0.02278`, profit factor `0.3819`.
- Forward baseline: 49 trades, net return ratio `-0.01617`, profit factor `0.6350`, average holding `2.51` bars.
- Regime-level replay: `LOW_VOLATILITY` was the only mildly positive Aurora regime (`+0.00273` net return ratio, PF `1.2171`); `MEAN_REVERSION`, `TREND_DOWN`, and `UNCERTAIN` remained negative on baseline. Detailed breakdown: `artifacts/strategy_calibration/phase1/mr_doge_candidate/per_regime_analysis.json`.
- Additional MR artifacts: `artifacts/strategy_calibration/phase1/mr_doge_candidate/tpsl_surface.json` and `artifacts/strategy_calibration/phase1/mr_doge_candidate/mfe_mae_analysis.json`.

## Machine-Readable Artifact Paths

- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.json
- artifacts/strategy_calibration/phase1/baseline_replay_surfaces.csv
- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.json
- artifacts/strategy_calibration/phase1/tool_adequacy_matrix.csv
- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.json
- artifacts/strategy_calibration/phase1/aggression_search_gap_matrix.csv
- artifacts/strategy_calibration/phase1/md_amr_xrp_live/run_manifest.json
- artifacts/strategy_calibration/phase1/md_amr_eth_candidate/run_manifest.json
- artifacts/strategy_calibration/phase1/md_amr_sol_candidate/run_manifest.json
- artifacts/strategy_calibration/phase1/mr_doge_candidate/run_manifest.json

## Small Patches Made

- None.

## Validation Commands And Outputs

- `python tools/calibration/calibrate_mean_reversion_params.py --symbols DOGEUSDT ...` with current `config/aurora/strategies.yaml` failed closed with `SCOPE_INVALID` as expected.
- `python tools/calibration/calibrate_md_amr_weights.py --symbols XRPUSDT ...` on a short window failed closed with `validation window lacks contiguous history for MD-AMR warmup`, confirming correct warmup enforcement.
- `python -m tools.analysis.md_amr_integrated_validation ...` succeeded and wrote summary/report artifacts.
- `python -m tools.forensics.mr_signal_surface_audit ...` failed because `reports/mean_reversion_real_run_validation_early/run_manifest.json` is missing in the current workspace.
- `pytest tests/tools/test_mean_reversion_param_calibrator.py tests/tools/test_md_amr_weight_calibrator.py tests/tools/test_md_amr_integrated_validation.py` passed: `14 passed in 12.41s`.
- Full baseline runs completed for XRPUSDT, ETHUSDT, SOLUSDT, and DOGEUSDT offline candidate scope.

## What Is Proven

- The two calibrators are reusable today for offline baseline replay on the requested Phase 1 surfaces.
- Current checked-in SSOT still provides only one live md_amr surface: XRPUSDT.
- Current checked-in SSOT still provides no live mean_reversion surface.
- Recorder-only replay can produce bounded trade-count, net-return, drawdown, and holding-bar approximations for the requested surfaces.
- Current md_amr baseline profile did not show a strong forward baseline on XRPUSDT, and ETH/SOL candidate surfaces remain non-promotional under the current profile.
- DOGE mean_reversion can be studied offline without changing production assignments, but only as an explicit dormant candidate scope.

## What Remains Unproven

- Execution-realized PnL, routing effects, portfolio interaction, and exposure-aware economics remain unproven because recorder data has no execution or portfolio truth.
- Full md_amr no-signal reason taxonomy is not available from the current safe baseline engine without tool expansion.
- Mean_reversion still has no live baseline under current SSOT, so no live MR calibration claim is possible.
- The full requested md_amr aggression grid cannot be run safely with current tooling without a small patch that widens the mutation surface beyond weights.

## Whether Phase 2 Aggression Grid Is Ready

NOT_READY

## Recommended Next Package

tool patch

## Minimal Safe Verdict

Phase 1 baseline replay is complete enough to ground the next decision, but not enough to begin the full Phase 2 aggression grid. The immediate blocker is tooling breadth, not data absence: md_amr currently replays well but only searches weights, while the requested grid requires many already-loaded but not-yet-searchable md_amr parameters. Mean_reversion can proceed only as an offline dormant-candidate line unless and until an operator makes an assignment decision.
