# SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT

## Verdict
SEMA_ATOM_POC_03B_STATUS:
COMPLETED

## Scope
- Read-only JSON-sidecar-driven stability filter between POC_03 validation and POC_04 counterfactual simulation.
- Markdown is human-readable only and is not used as transport.
- No live logic, YAML policy, gates, enforcement, or PnL simulation.

## Inputs Read
- Sema_Atom\SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json

## Sidecar Validation
- schema_id: SemaAtomPoc03EvaluationSidecarV01
- schema_version: 1.0.0
- reported_contexts_total: 40
- parsed_contexts_total: 40
- unique_context_keys: 40
- validation_error_count: 0

## Manifest Summary
- READY_FOR_COUNTERFACTUAL_SIM count: 6
- PROMISING_LOW_SUPPORT count: 5
- REJECTED_FALSE_POSITIVE count: 8
- INCONCLUSIVE_LOW_POWER count: 20
- CONFIRMED_BUT_UNSTABLE count: 0
- CONFIRMED_BUT_UNCLASSIFIED count: 1
- UNKNOWN count: 0
- manifest_total_contexts: 40

## READY_FOR_COUNTERFACTUAL_SIM
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT train_count=6 validation_count=6 train_net_score=5.773558 validation_net_score=3.948269
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE train_count=17 validation_count=18 train_net_score=-9.274239 validation_net_score=7.277411
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 verdict=POLICY_TOO_STRICT_CANDIDATE train_count=9 validation_count=10 train_net_score=-0.249928 validation_net_score=-6.135459
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT train_count=10 validation_count=11 train_net_score=0.493415 validation_net_score=12.991174
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 verdict=FAVORABLE_CONTEXT train_count=8 validation_count=8 train_net_score=6.1106 validation_net_score=5.113279
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE train_count=26 validation_count=27 train_net_score=-6.998836 validation_net_score=-4.383504

## PROMISING_LOW_SUPPORT
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 verdict=FAVORABLE_CONTEXT support_quality=BORDERLINE train_count=2 validation_count=3
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=FAVORABLE_CONTEXT support_quality=BORDERLINE train_count=2 validation_count=3
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 verdict=FAVORABLE_CONTEXT support_quality=BORDERLINE train_count=3 validation_count=3
- XRPUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 verdict=FAVORABLE_CONTEXT support_quality=BORDERLINE train_count=3 validation_count=4
- XRPUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 verdict=FAVORABLE_CONTEXT support_quality=BORDERLINE train_count=2 validation_count=3

## REJECTED_FALSE_POSITIVE
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.75..1.00 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.75..1.00 verdict=MIXED_CONTEXT validation_reason=validation_became_directional
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE validation_reason=validation_missing_missed_positive_pattern
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 verdict=MIXED_CONTEXT validation_reason=validation_became_directional
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.75..1.00 verdict=MIXED_CONTEXT validation_reason=validation_became_directional

## INCONCLUSIVE_LOW_POWER
- BNBUSDT|BUY|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BNBUSDT|BUY|aurora|TREND_UP|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.50..0.75 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BNBUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BTCUSDT|BUY|aurora|MEAN_REVERSION|0.50..0.75 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BTCUSDT|BUY|aurora|TREND_UP|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- BTCUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- DOGEUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- ETHUSDT|BUY|aurora|TREND_UP|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- ETHUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|BUY|aurora|TREND_UP|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM
- XRPUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 verdict=LOW_SUPPORT low_power_reason=TRAIN_BELOW_DISPLAY_MINIMUM

## OTHER BUCKETS
- CONFIRMED_BUT_UNSTABLE: 0
- CONFIRMED_BUT_UNCLASSIFIED: 1
  ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.75..1.00 verdict=MIXED_CONTEXT validation_result=CONFIRMED
- UNKNOWN: 0

## Residual Risks
- POC_03B now fails closed when the JSON sidecar is missing or violates the schema contract.
- `BORDERLINE` support never promotes a context into `READY_FOR_COUNTERFACTUAL_SIM`.
- `READY_FOR_COUNTERFACTUAL_SIM` remains a candidate gate only; POC_03B does not simulate PnL or alter policy.

## Next Recommended Step
- SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01
- Preserve `SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json` as the only POC_03B candidate transport for downstream consumers.

