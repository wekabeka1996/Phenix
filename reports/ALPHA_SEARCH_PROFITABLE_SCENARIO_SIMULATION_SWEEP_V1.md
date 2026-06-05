# ALPHA_SEARCH_PROFITABLE_SCENARIO_SIMULATION_SWEEP_V1

Authority boundary:
- shadow_only=true
- authority_applied=false
- no_effect=true
- No real ORDER_INTENT, CMD:OPEN, CMD:CLOSE, or config changes were emitted.

## Facts
- Latest runtime session analyzed: 20260517_171326
- Candidate scenarios selected for sweep: S03_AURORA_15M_APPROX, S05_AURORA_MACRO_RESIDUAL, S06_AURORA_ETH_CALIBRATED, S20_AURORA_MICROSTRUCTURE_DEPTH
- Best cost-aware combined variant by newest runtime truth: S05_AURORA_MACRO_RESIDUAL / top_50_pct / MEAN_REVERSION_only / per_symbol_best_threshold / no_SELL_in_TREND_UP / fixed_tp_15_sl_8 / maker_fee_0_02_pct / 1_bps
- Best variant avg net expectancy: 16.7795 bps
- Best variant total net pnl: 201.3536 bps
- Best variant signal count: 12
- Best variant avoided real SL count: 1
- Best variant false skip TP count: 0
Previous report anchor: ALPHA_SEARCH_PNL_FINANCIAL_ANALYSIS_20260517.md exists, but newest runtime truth was used for this sweep because latest signal counts and side mix drifted materially from the older 1-bar summary.

## Inferences
- Latest runtime still shows gross edge in the original aurora candidates, but net edge is highly sensitive to transaction costs and to whether BTC/HIGH_VOL/TREND_UP side conflicts are filtered out.
- Thresholds above the runtime's current operating range reduce noise but can quickly collapse sample size; percentile thresholds are more stable than fixed 0.12-0.25 gates on the newest logs.
- S20 remains usable only when BTC toxicity and HIGH_VOL pockets are explicitly filtered; otherwise its BUY clusters in BTC TREND_UP/HIGH_VOL remain unstable.

## Answers
1. Scenarios remaining profitable after fees/slippage: S05_AURORA_MACRO_RESIDUAL.
2. Is S03 still best after costs? no.
3. Is S05 safer after costs? yes.
4. Is S20 useful after removing HIGH_VOL and BTC? no.
5. Does no-SELL-in-TREND_UP improve results? yes.
6. Which threshold gives best net expectancy? top_50_pct.
7. Which regime filter gives best result? MEAN_REVERSION_only.
8. Which symbol filter gives best result? per_symbol_best_threshold.
9. Which exit model is best? fixed_tp_15_sl_8.
10. Are there enough samples to trust the candidate? LOW_SAMPLE_WARNING.
11. Would the best variant have avoided real SL cases? 1 confirmed cases in the available comparison window.
12. Would the best variant have falsely skipped real TP cases? 0 confirmed cases in the available comparison window.
13. What should be promoted to deeper shadow collection? S05_AURORA_MACRO_RESIDUAL.
14. What should be discarded? none.

## Promote
- 1. S05_AURORA_MACRO_RESIDUAL | thr=top_50_pct | regime=MEAN_REVERSION_only | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=fixed_tp_15_sl_8 | fee=maker_fee_0_02_pct | slip=1_bps | avg_net=16.7795 bps | n=12
- 2. S05_AURORA_MACRO_RESIDUAL | thr=top_30_pct | regime=MEAN_REVERSION_only | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=fixed_tp_15_sl_8 | fee=maker_fee_0_02_pct | slip=1_bps | avg_net=16.7795 bps | n=12
- 3. S05_AURORA_MACRO_RESIDUAL | thr=top_50_pct | regime=MEAN_REVERSION_only | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=fixed_tp_15_sl_8 | fee=maker_fee_0_02_pct | slip=volatility_scaled_slippage | avg_net=16.4267 bps | n=12
- 4. S05_AURORA_MACRO_RESIDUAL | thr=top_30_pct | regime=MEAN_REVERSION_only | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=fixed_tp_15_sl_8 | fee=maker_fee_0_02_pct | slip=volatility_scaled_slippage | avg_net=16.4267 bps | n=12
- 5. S05_AURORA_MACRO_RESIDUAL | thr=top_50_pct | regime=MEAN_REVERSION_only | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=fixed_tp_15_sl_8 | fee=maker_fee_0_02_pct | slip=2_bps | avg_net=15.7795 bps | n=12

## Discard
- S05_AURORA_MACRO_RESIDUAL | regime=regime_confidence_ge_0_60 | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=horizon_12_bar | avg_net=-0.7855 bps | n=54
- S05_AURORA_MACRO_RESIDUAL | regime=regime_confidence_ge_0_60 | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=microstructure_reversal_exit | avg_net=-0.7855 bps | n=54
- S05_AURORA_MACRO_RESIDUAL | regime=regime_confidence_ge_0_45 | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=horizon_12_bar | avg_net=-0.7855 bps | n=54
- S05_AURORA_MACRO_RESIDUAL | regime=regime_confidence_ge_0_45 | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=microstructure_reversal_exit | avg_net=-0.7855 bps | n=54
- S05_AURORA_MACRO_RESIDUAL | regime=regime_confidence_ge_0_60 | symbol=per_symbol_best_threshold | side=no_SELL_in_TREND_UP | exit=horizon_6_bar | avg_net=-1.1726 bps | n=54

## Verdict Codes
- NET_PROFITABLE_VARIANT_FOUND
- S05_SAFEST_AFTER_COSTS
- NO_SELL_TREND_UP_CONFIRMED
- EXIT_MODEL_EDGE_FOUND
- PARTIAL
- LOW_SAMPLE_ONLY