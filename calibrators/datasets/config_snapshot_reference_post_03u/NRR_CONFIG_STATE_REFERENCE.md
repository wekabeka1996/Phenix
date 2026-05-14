# NRR_CONFIG_STATE_REFERENCE

Authority caveat: CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY

| Gate/Surface | Current Reference State | Runtime Authority? | Notes |
| --- | --- | --- | --- |
| NRR-062 enabled | True | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| NRR-062 enforce_in_modes | testnet, hybrid_live_data_testnet_exec | no | decision_making.low_vol_cost_floor_gate |
| NRR-062 observe_only_in_modes | live, production | no | decision_making.low_vol_cost_floor_gate |
| NRR-062 thresholds | {"target_net_fee_multiple": 2.0, "min_tp_fee_coverage": 3.0, "min_rr": 1.2, "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39}, "min_regime_confidence_overrides_by_strategy_symbol": {"aurora": {"XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45}}, "md_amr": {"XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45}}}, "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}, "min_direction_confidence_overrides_by_strategy_symbol": {"aurora": {"XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}}, "md_amr": {"XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59}}}, "min_raw_score_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}, "min_normalized_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}, "min_raw_score_overrides_by_strategy_symbol": {"aurora": {"XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}}}, "min_normalized_confidence_overrides_by_strategy_symbol": {"md_amr": {"XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59}}}} | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| NRR-062 direction_confidence | {"required": true, "raw_signed_score_sources": ["signal_score", "final_score"], "normalized_confidence_sources": ["strategy_confidence"], "judge_confidence_live_producer_required": false, "missing_policy": "fail_closed"} | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| Selected source/scale family reference | {"raw_signed_score_sources": ["signal_score", "final_score"], "normalized_confidence_sources": ["strategy_confidence"], "threshold_surfaces_present": ["min_raw_score_by_regime", "min_normalized_confidence_by_regime", "min_direction_confidence_by_regime", "min_regime_confidence_by_regime"], "runtime_authority": false, "notes": "Current YAML exposes candidate confidence sources and threshold families, but not frozen runtime-selected source/scale authority."} | no | Current YAML exposes candidate confidence sources and threshold families, but not frozen runtime-selected source/scale authority. |
| NRR-027 | False | no | decision_making.directional_sanity.nrr027_enabled |
| NRR-028 | NOT_PRESENT_IN_CURRENT_REFERENCE | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| NRR-029 | NOT_PRESENT_IN_CURRENT_REFERENCE | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| NRR-030 | NOT_PRESENT_IN_CURRENT_REFERENCE | no | CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY |
| Pydantic model:LowVolCostFloorGateConfig | apps/reference/config/domains/decision_making.py | n/a | Primary Pydantic model for NRR-062 LOW_VOL gate config. |
