# MD_AMR Integrated Validation Report

## Scope
- Objective: compare accepted safe baseline A.1 against current integrated C.1/C.2/C.3/C.4 line.
- Symbols: XRPUSDT, BNBUSDT
- Validation surface: recorder-based md_amr strategy-core replay plus asset TP/SL projection.
- Output artifacts:
  - reports/md_amr_integrated_validation_by_symbol.csv
  - reports/md_amr_integrated_validation_cohorts.csv
  - reports/md_amr_integrated_validation_summary.csv

## FACT
- Current YAML still holds the accepted A.1 baseline values: max_hold_bars=16, target_approach_pct=0.0.
- Package C.3 and C.4 remain advisory-only at package boundary; they do not own exit or execution truth.
- Runtime forensic evidence already proves md_amr activity on XRPUSDT and BNBUSDT in the 21h report.
- XRPUSDT: recorder range 2026-02-08..2026-04-13, exact trade match rate=1.0000, net-return delta=0.0000.
- BNBUSDT: recorder range 2026-03-05..2026-04-13, exact trade match rate=1.0000, net-return delta=0.0000.
- Combined exact trade match rate=1.0000; trade-count delta=0; net-return delta=0.0000.
- Combined timeout delta=0; avg-holding delta=0.0000.
- XRPUSDT integrated overlay coverage: observed_overlay_trades=200, exit_hold_quality_mean=0.2611, exit_context_validity_mean=0.3166.
- BNBUSDT integrated overlay coverage: observed_overlay_trades=118, exit_hold_quality_mean=0.2168, exit_context_validity_mean=0.2988.

## INFERENCE
- Explainability without economic harm is supported at the recorder core-replay layer because the integrated arm preserved exact trade parity while exposing additional C.1/C.3/C.4 trace state.
- Trade-quality improvement is not proven as a realized economic outcome because the integrated overlays are advisory-only and therefore do not change entry/exit behavior.
- Stale/zombie reduction is not proven as a realized runtime effect because timeout counts and trade lifecycles remain unchanged between arms.
- XRPUSDT profitable slow reversions remain present under the integrated line: trade_count=11, avg_holding_bars=16.5455, exit_hold_quality_mean=0.2513, exit_context_validity_mean=0.3515.
- BNBUSDT profitable slow reversions remain present under the integrated line: trade_count=8, avg_holding_bars=14.8750, exit_hold_quality_mean=0.3538, exit_context_validity_mean=0.3457.
- That profitable slow-reversion cohort is the main promotion risk: if C.3/C.4 are promoted into hard gating without broader evidence, valid slow mean reversions could be cut early.

## Cohort Readout
- XRPUSDT WEAK_CONTEXT_EXIT: trade_count=200, net_return_ratio=-0.2345, win_rate=0.5000.
- BNBUSDT WEAK_CONTEXT_EXIT: trade_count=118, net_return_ratio=-0.0836, win_rate=0.4407.

## ASSUMPTION
- This validation replays md_amr strategy-core decisions plus asset TP/SL projection from recorder OHLCV bars.
- It uses recorder regime/regime_conf columns as the handler-owned context feed for the integrated arm.
- It does not reconstruct full live warmup, objective-engine, gateway, or exchange-side state machines.

## UNKNOWN
- Full end-to-end economic impact under the complete DecisionMaking/Execution stack remains unknown because the repo does not contain a general md_amr backtest engine or config-isolation harness for A.1 vs integrated overlays.
- Post-patch live or testnet runtime economics for integrated C.1/C.2/C.3/C.4 remain unknown beyond the existing 21h forensic activation proof.

## Verdict
- Economic promotion: not justified from this package. The integrated line is economically neutral on the bounded recorder replay surface, not economically superior.
- Explainability: justified. The integrated line adds interpretable trade-state segmentation without measured economic drift on the bounded replay surface.
- Stale/zombie reduction: not proven because overlays are advisory-only.
- Over-penalization risk: still open if future promotion turns hold/context overlays into hard gates.
