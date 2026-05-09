# SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT

## Verdict
SEMA_ATOM_POC_03B_STATUS:
COMPLETED

## Scope
- Read-only artifact-driven stability filter between POC_03 validation and POC_04 counterfactual simulation.
- No live logic, YAML policy, gates, enforcement, or PnL simulation.

## Inputs Read
- C:\Users\user\Music\Phenix\SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md

## Parser Validation
- parsed_contexts_total: 37
- expected_contexts_total: 37
- missing_required_fields: 0
- contexts_with_empty_validation_outcomes: 27

## Manifest Summary
- READY_FOR_COUNTERFACTUAL_SIM count: 1
- PROMISING_LOW_SUPPORT count: 5
- REJECTED_FALSE_POSITIVE count: 3
- INCONCLUSIVE_LOW_POWER count: 27
- CONFIRMED_BUT_UNSTABLE count: 1
- CONFIRMED_BUT_UNCLASSIFIED count: 0
- UNKNOWN count: 0
- manifest_total_contexts: 37

## READY_FOR_COUNTERFACTUAL_SIM
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE train_count=10 validation_count=11 train_net_score=-16.461044 validation_net_score=-11.844887

## PROMISING_LOW_SUPPORT
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 verdict=FAVORABLE_CONTEXT validation_result=CONFIRMED train_count=4 validation_count=5
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT validation_result=CONFIRMED train_count=3 validation_count=3
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONFIRMED train_count=3 validation_count=4
- ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=TOXIC_CONTEXT validation_result=CONFIRMED train_count=3 validation_count=3
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT validation_result=CONFIRMED train_count=4 validation_count=4

## REJECTED_FALSE_POSITIVE
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=MIXED_CONTEXT validation_reason=validation_became_directional
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern

## INCONCLUSIVE_LOW_POWER
- BNBUSDT|BUY|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=1
- BNBUSDT|BUY|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BNBUSDT|BUY|aurora|TREND_UP|0.00..0.25 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BNBUSDT|BUY|aurora|TREND_UP|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT train_count=1 validation_count=2
- BNBUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BNBUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=2
- BTCUSDT|BUY|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BTCUSDT|BUY|aurora|TREND_UP|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=1
- BTCUSDT|BUY|aurora|TREND_UP|0.25..0.50 verdict=LOW_SUPPORT train_count=1 validation_count=1
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 verdict=LOW_SUPPORT train_count=1 validation_count=2
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.75..1.00 verdict=LOW_SUPPORT train_count=0 validation_count=1
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=2
- BTCUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=1
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 verdict=LOW_SUPPORT train_count=1 validation_count=2
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.75..1.00 verdict=LOW_SUPPORT train_count=0 validation_count=1
- ETHUSDT|BUY|aurora|TREND_UP|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=1
- XRPUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- XRPUSDT|BUY|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- XRPUSDT|BUY|aurora|TREND_UP|0.25..0.50 verdict=LOW_SUPPORT train_count=0 validation_count=1
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT train_count=1 validation_count=1
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT train_count=0 validation_count=1
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT train_count=1 validation_count=2
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.50..0.75 verdict=LOW_SUPPORT train_count=1 validation_count=1

## OTHER BUCKETS
- CONFIRMED_BUT_UNSTABLE: 1
  ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT validation_result=CONFIRMED
- CONFIRMED_BUT_UNCLASSIFIED: 0
- UNKNOWN: 0

## Residual Risks
- Markdown parsing remains format-sensitive to the POC_03 report layout, so any future report-shape drift should be treated as a parser contract change.
- `contexts_with_empty_validation_outcomes` is expected for skipped low-support contexts and is not itself a failure.
- `READY_FOR_COUNTERFACTUAL_SIM` remains a candidate gate only; POC_03B does not simulate PnL or alter policy.

## Next Recommended Step
- SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION
- Use only contexts from `SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json` bucket `READY_FOR_COUNTERFACTUAL_SIM`.

