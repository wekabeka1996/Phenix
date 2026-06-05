# R7Z_FEE_AWARE_SHADOW_ECONOMIC_EFFECTIVENESS_REPORT

## Executive Summary

Verdict: FEE_AWARE_ECONOMIC_SIGNAL_POSITIVE_BUT_NOT_PROMOTABLE.

This read-only package evaluated fee-aware shadow-arm economics against matched raw percent-notional peak-giveback shadow candidates over 2026-05-26T14:57:21.345000Z -> 2026-05-29T18:00:30.126000Z. The live peak_giveback path remained disabled in runtime snapshots, but the shadow percent_notional baseline and fee_aware candidate states were both retained in trade_lifecycle peak_giveback_snapshot, which made direct candidate-level comparison possible without changing authority or execution behavior.

Observed fee-aware event count was 108 in trade_lifecycle and 108 in shadow_critical_event_journal across 6 symbols and 9 fee-aware lifecycles. Closed lifecycles with complete order-log economics were 8; another 1 lifecycles only had estimated or fallback economics. Aggregate confidence was MEDIUM.

## FACTS

- Clean post-R7X boundary remained 2026-05-22T07:46:31Z.
- Analysis window was 2026-05-26T14:57:21.345000Z -> 2026-05-29T18:00:30.126000Z.
- Fee-aware shadow events in trade_lifecycle: 108.
- Matching fee-aware rows in shadow_critical_event_journal: 108.
- Observed symbols in scope: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, XRPUSDT.
- Fee-aware lifecycle count: 9.
- Closed lifecycles with complete economics: 8.
- Counterfactual rows with HIGH confidence: 48.
- Denominator economics_ready_ratio: 0.177177.
- Dominant fee source: None.

## Window And Sufficiency

- Window start: 2026-05-26T14:57:21.345000Z
- Window end: 2026-05-29T18:00:30.126000Z
- Window extended beyond accepted R7Y end: true
- Symbols: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, XRPUSDT
- Lifecycles: 9
- Fee-aware events: 108
- Closed lifecycles: 9
- Sufficient for economic analysis: true

## Lifecycle Table

| Symbol | Entry | Close | Close reason | Actual net | Lifecycle class | Assessment |
| --- | --- | --- | --- | ---: | --- | --- |
| 1000PEPEUSDT | 2026-05-28T23:05:11.160000Z | 2026-05-28T23:09:54.217000Z | CLOSE | -8.056076 | CLOSED_WITH_COMPLETE_ECONOMICS | INCONCLUSIVE |
| BNBUSDT | 2026-05-29T18:00:10.802000Z | 2026-05-29T18:52:23.942000Z | SL | -14.775830 | CLOSED_WITH_COMPLETE_ECONOMICS | INCONCLUSIVE |
| BTCUSDT | 2026-05-26T14:51:38.645000Z | 2026-05-26T15:22:56.018000Z | TP | 3.229712 | CLOSED_WITH_COMPLETE_ECONOMICS | INCONCLUSIVE |
| DOGEUSDT | 2026-05-26T20:08:38.616000Z | 2026-05-27T00:55:07.935000Z | SL | -13.478203 | CLOSED_WITH_COMPLETE_ECONOMICS | FALSE_TRIGGER_REDUCTION_SUPPORTED |
| DOGEUSDT | 2026-05-29T13:55:29.351000Z | 2026-05-29T14:52:00.885000Z | SL | -14.881983 | CLOSED_WITH_COMPLETE_ECONOMICS | INCONCLUSIVE |
| ETHUSDT | 2026-05-26T20:15:28.362000Z | 2026-05-27T04:31:27.932000Z | TP | 25.251316 | CLOSED_WITH_COMPLETE_ECONOMICS | BOTH_MIXED |
| ETHUSDT | 2026-05-28T18:19:43.580000Z | n/a | n/a | -14.601000 | CLOSED_WITH_ESTIMATED_ECONOMICS | FALSE_TRIGGER_REDUCTION_SUPPORTED |
| ETHUSDT | 2026-05-28T22:05:41.603000Z | 2026-05-29T02:44:11.821000Z | TP | 24.164153 | CLOSED_WITH_COMPLETE_ECONOMICS | FALSE_TRIGGER_REDUCTION_SUPPORTED |
| XRPUSDT | 2026-05-28T23:00:09.737000Z | 2026-05-29T02:54:48.793000Z | TP | 15.896207 | CLOSED_WITH_COMPLETE_ECONOMICS | INCONCLUSIVE |

## Raw vs Fee-Aware Comparison

| Symbol | Raw pct | Fee x | Fee pct floor | Raw trigger | Fee trigger | Delta fee-aware vs raw | Class | Confidence |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- | --- |
| 1000PEPEUSDT | 0.02 | 1.0 | 0.02 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| 1000PEPEUSDT | 0.02 | 1.5 | 0.02 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| 1000PEPEUSDT | 0.02 | 2.0 | 0.02 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| 1000PEPEUSDT | 0.05 | 1.0 | 0.05 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| 1000PEPEUSDT | 0.05 | 1.5 | 0.05 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| 1000PEPEUSDT | 0.05 | 2.0 | 0.05 | 2026-05-28T23:05:21.619000Z | 2026-05-28T23:05:21.619000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.02 | 1.0 | 0.02 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.02 | 1.5 | 0.02 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.02 | 2.0 | 0.02 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.05 | 1.0 | 0.05 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.05 | 1.5 | 0.05 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BNBUSDT | 0.05 | 2.0 | 0.05 | 2026-05-29T18:00:30.126000Z | 2026-05-29T18:00:30.126000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.02 | 1.0 | 0.02 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.02 | 1.5 | 0.02 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.02 | 2.0 | 0.02 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.05 | 1.0 | 0.05 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.05 | 1.5 | 0.05 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| BTCUSDT | 0.05 | 2.0 | 0.05 | 2026-05-26T14:58:14.425000Z | 2026-05-26T14:58:14.425000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 1.0 | 0.02 | 2026-05-26T20:17:03.268000Z | 2026-05-26T20:17:03.268000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 1.5 | 0.02 | 2026-05-26T20:17:03.268000Z | 2026-05-26T20:17:03.268000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 2.0 | 0.02 | 2026-05-26T20:17:03.268000Z | 2026-05-26T20:18:43.897000Z | 0.300000 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| DOGEUSDT | 0.05 | 1.0 | 0.05 | 2026-05-26T20:18:43.897000Z | 2026-05-26T20:18:43.897000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.05 | 1.5 | 0.05 | 2026-05-26T20:18:43.897000Z | 2026-05-26T20:18:43.897000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.05 | 2.0 | 0.05 | 2026-05-26T20:18:43.897000Z | 2026-05-26T20:18:43.897000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 1.0 | 0.02 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 1.5 | 0.02 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.02 | 2.0 | 0.02 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.05 | 1.0 | 0.05 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.05 | 1.5 | 0.05 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| DOGEUSDT | 0.05 | 2.0 | 0.05 | 2026-05-29T14:08:17.269000Z | 2026-05-29T14:08:17.269000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| ETHUSDT | 0.02 | 1.0 | 0.02 | 2026-05-26T20:15:37.672000Z | 2026-05-26T20:15:37.672000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| ETHUSDT | 0.02 | 1.5 | 0.02 | 2026-05-26T20:15:37.672000Z | 2026-05-26T20:16:27.755000Z | -0.032815 | FEE_AWARE_LATER_AND_WORSE | HIGH |
| ETHUSDT | 0.02 | 2.0 | 0.02 | 2026-05-26T20:15:37.672000Z | 2026-05-26T20:23:46.510000Z | 1.317185 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.05 | 1.0 | 0.05 | 2026-05-26T20:16:27.755000Z | 2026-05-26T20:16:27.755000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| ETHUSDT | 0.05 | 1.5 | 0.05 | 2026-05-26T20:16:27.755000Z | 2026-05-26T20:16:27.755000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| ETHUSDT | 0.05 | 2.0 | 0.05 | 2026-05-26T20:16:27.755000Z | 2026-05-26T20:23:46.510000Z | 1.350000 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.02 | 1.0 | 0.02 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:20:25.181000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | MEDIUM |
| ETHUSDT | 0.02 | 1.5 | 0.02 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:22:11.929000Z | 0.840000 | FEE_AWARE_LATER_AND_BETTER | MEDIUM |
| ETHUSDT | 0.02 | 2.0 | 0.02 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:22:11.929000Z | 0.840000 | FEE_AWARE_LATER_AND_BETTER | MEDIUM |
| ETHUSDT | 0.05 | 1.0 | 0.05 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:20:25.181000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | MEDIUM |
| ETHUSDT | 0.05 | 1.5 | 0.05 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:22:11.929000Z | 0.840000 | FEE_AWARE_LATER_AND_BETTER | MEDIUM |
| ETHUSDT | 0.05 | 2.0 | 0.05 | 2026-05-28T18:20:25.181000Z | 2026-05-28T18:22:11.929000Z | 0.840000 | FEE_AWARE_LATER_AND_BETTER | MEDIUM |
| ETHUSDT | 0.02 | 1.0 | 0.02 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.02 | 1.5 | 0.02 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.02 | 2.0 | 0.02 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.05 | 1.0 | 0.05 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.05 | 1.5 | 0.05 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| ETHUSDT | 0.05 | 2.0 | 0.05 | 2026-05-28T22:06:16.227000Z | 2026-05-29T00:00:49.312000Z | 9.893543 | FEE_AWARE_LATER_AND_BETTER | HIGH |
| XRPUSDT | 0.02 | 1.0 | 0.02 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| XRPUSDT | 0.02 | 1.5 | 0.02 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| XRPUSDT | 0.02 | 2.0 | 0.02 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| XRPUSDT | 0.05 | 1.0 | 0.05 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| XRPUSDT | 0.05 | 1.5 | 0.05 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |
| XRPUSDT | 0.05 | 2.0 | 0.05 | 2026-05-28T23:01:53.470000Z | 2026-05-28T23:01:53.470000Z | 0.000000 | FEE_AWARE_SAME_AS_RAW | HIGH |

## Counterfactual Confidence Levels

- HIGH: 48
- MEDIUM: 6
- LOW: 0
- UNKNOWN: 0

## Denominator Audit

- Candidate rows total: 1815606
- Economics-ready ratio: 0.177177
- Dominant fee source: None
- realized_lifecycle_fee count: 235650
- order_log_fee count: 529404
- estimated_fee count: 529404
- null fee_source count: 1050552
- missing_unrealized_pnl_usdt count: 162
- Denominator classification: FEE_SOURCE_TOO_WEAK

## INFERENCES

- Comparable fee-aware candidates more often delayed trigger to a stronger estimated net than the matched raw percent-notional candidate, but the evidence remains bounded to the observed cohort.
- Denominator quality remained limited by fee_source_too_weak, so aggregate economics should be treated as bounded evidence rather than a promotion signal.

## ASSUMPTIONS

- Lifecycle identity was reconstructed from sidecar position_snapshot symbol + side + position_open_ts + entry_price + position_qty_abs because fee-aware shadow rows do not carry rid or lifecycle_id directly.
- When order_log POSITION_CLOSED rows were mapped by symbol and open-interval, realized_pnl_net was treated as the authoritative actual-exit net outcome.
- When raw shadow exits were estimated, gross current_edge_usd was reduced by the best same-snapshot fee estimate available from the fee-aware candidate surface; this is an approximation, not an executed fill.

## UNKNOWNS

- No claim is made that fee-aware logic is live-ready or promotable without a separate gate.
- Any lifecycle with ambiguous or missing close mapping remains economically incomplete.
- The live execution source for actual closes was not reclassified here; this package only evaluates shadow economics versus raw shadow candidates and actual outcomes.

## Final Verdict

FEE_AWARE_ECONOMIC_SIGNAL_POSITIVE_BUT_NOT_PROMOTABLE

## AGENT_REPORT_V1

```text
AGENT_REPORT_V1

task: AURORA_R7Z_FEE_AWARE_SHADOW_ECONOMIC_EFFECTIVENESS_ANALYSIS
verdict: FEE_AWARE_ECONOMIC_SIGNAL_POSITIVE_BUT_NOT_PROMOTABLE
runtime_authority_changed: false
execution_behavior_changed: false
config_policy_changed: false
analysis_window:
  start: 2026-05-26T14:57:21.345000Z
  end: 2026-05-29T18:00:30.126000Z
lifecycles:
  total: 9
  closed_with_complete_economics: 8
  incomplete_or_unjoinable: 0
symbols:
  - 1000PEPEUSDT
  - BNBUSDT
  - BTCUSDT
  - DOGEUSDT
  - ETHUSDT
  - XRPUSDT
timing_comparison:
  fee_aware_same_as_raw: 40
  fee_aware_later: 14
  fee_aware_later_better_possible: 13
  fee_aware_later_worse_possible: 1
  inconclusive: 0
counterfactuals:
  computable_high_confidence: 48
  computable_medium_confidence: 6
  computable_low_confidence: 0
  not_computable: 0
denominator:
  economics_ready_ratio: 0.177177
  dominant_fee_source: None
  denominator_bias_detected: true
safety:
  authority_leak_detected: false
  fee_aware_close_source_detected: false
artifacts:
  - R7Z_FEE_AWARE_SHADOW_ECONOMIC_EFFECTIVENESS_REPORT.md
  - r7z_fee_aware_lifecycle_economics_matrix.json
  - r7z_raw_vs_fee_aware_timing_matrix.json
  - r7z_counterfactual_exit_estimates.json
  - r7z_fee_source_denominator_audit.json
  - r7z_summary_metrics.json
proven:
  - Clean post-R7X boundary remained 2026-05-22T07:46:31Z.
  - Analysis window was 2026-05-26T14:57:21.345000Z -> 2026-05-29T18:00:30.126000Z.
  - Fee-aware shadow events in trade_lifecycle: 108.
  - Matching fee-aware rows in shadow_critical_event_journal: 108.
  - Observed symbols in scope: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, XRPUSDT.
  - Fee-aware lifecycle count: 9.
inferences:
  - Comparable fee-aware candidates more often delayed trigger to a stronger estimated net than the matched raw percent-notional candidate, but the evidence remains bounded to the observed cohort.
  - Denominator quality remained limited by fee_source_too_weak, so aggregate economics should be treated as bounded evidence rather than a promotion signal.
unproven:
  - No claim is made that fee-aware logic is live-ready or promotable without a separate gate.
  - Any lifecycle with ambiguous or missing close mapping remains economically incomplete.
  - The live execution source for actual closes was not reclassified here; this package only evaluates shadow economics versus raw shadow candidates and actual outcomes.
next_step:
  - Keep fee-aware logic shadow-only and, if a larger current-window cohort is needed, rerun the same read-only package after more closed lifecycles accumulate.
```
