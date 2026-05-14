# NRR062_EXISTING_FIELD_INVENTORY

## Observed Runtime Surface
| Metric | Value | Notes |
| --- | --- | --- |
| Reject Rows | 153 | canonical Package A reject cohort |
| Selected Scale Counts | {"raw_signed_score": 153} | all observed rows choose the same scale family |
| Threshold Family Counts | {"raw_signed_score": 153} | all observed rows choose the same threshold family |
| Strategy Counts | {"aurora": 153} | single-strategy cohort |
| Symbol Counts | {"ETHUSDT": 76, "XRPUSDT": 30, "BTCUSDT": 47} | XRP rows are partially shadowed by overrides |

## Fields
| Field | Current Value | Config Path | Pydantic Model Field | Used By Runtime? | Affects Raw Rejects? | BUY+SELL Together? | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| target_net_fee_multiple | 2 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.target_net_fee_multiple | LowVolCostFloorThresholdsConfig.target_net_fee_multiple | True | conditional_only_if_geometry_binding | True | HIGH |
| min_tp_fee_coverage | 3 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_tp_fee_coverage | LowVolCostFloorThresholdsConfig.min_tp_fee_coverage | True | conditional_only_if_geometry_binding | True | HIGH |
| min_rr | 1.2 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_rr | LowVolCostFloorThresholdsConfig.min_rr | True | conditional_only_if_geometry_binding | True | HIGH |
| min_regime_confidence_by_regime.LOW_VOLATILITY | 0.39 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_regime_confidence_by_regime.LOW_VOLATILITY | LowVolCostFloorThresholdsConfig.min_regime_confidence_by_regime | True | yes_but_not_xrp_override_rows | True | HIGH |
| min_direction_confidence_by_regime.LOW_VOLATILITY | 0.25 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_direction_confidence_by_regime.LOW_VOLATILITY | LowVolCostFloorThresholdsConfig.min_direction_confidence_by_regime | False | no_for_current_cohort | True | LOW_FOR_CURRENT_COHORT_NOOP |
| min_raw_score_by_regime.LOW_VOLATILITY | 0.25 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_raw_score_by_regime.LOW_VOLATILITY | LowVolCostFloorThresholdsConfig.min_raw_score_by_regime | True | yes_but_not_xrp_override_rows | True | HIGH |
| min_normalized_confidence_by_regime.LOW_VOLATILITY | 0.25 | config/aurora/domains.yaml::decision_making.low_vol_cost_floor_gate.thresholds.min_normalized_confidence_by_regime.LOW_VOLATILITY | LowVolCostFloorThresholdsConfig.min_normalized_confidence_by_regime | False | no_for_current_cohort | True | LOW_FOR_CURRENT_COHORT_NOOP |
