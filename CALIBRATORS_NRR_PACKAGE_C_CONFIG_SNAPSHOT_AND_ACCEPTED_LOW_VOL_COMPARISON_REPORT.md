# AGENT_REPORT_V1

## verdict
CONFIG_SNAPSHOT_CONTRACT_READY_ACCEPTED_LOW_VOL_BLOCKED

## problem_framing
Package B improved the rejected LOW_VOL evidence surface, but it still could not authorize threshold patching. The rejected replay remained mixed and timeout-dominated, the 03U bundle still lacked a frozen config snapshot, and the accepted canonical realized cohort still did not provide an admitted LOW_VOL comparison surface. Package C therefore stayed strictly read-only and focused on authority repair plus accepted LOW_VOL coverage audit rather than threshold mutation.

## facts
- Added offline helper `artifacts/_tmp/phenix_nrr062_package_c_config_snapshot_and_low_vol_audit.py` and focused tests `tests/tools/test_nrr062_package_c_config_snapshot_and_low_vol_audit.py`.
- Generated future-run contract artifacts `calibrators/datasets/config_snapshot_contract/CONFIG_SNAPSHOT_FREEZE_CONTRACT.md` and `calibrators/datasets/config_snapshot_contract/config_snapshot_manifest_schema.json`.
- Generated current-workspace reference snapshot at `calibrators/datasets/config_snapshot_reference_post_03u/` with authority caveat `CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY`.
- The current reference manifest captured branch `main`, commit `e837f16ff8b6c2fd3fd41a3812c78237cc3a1427`, dirty_worktree=true, and the same top-level config dirtiness already present before package C.
- The current reference manifest recorded `required_files=8`, `required_present=8`, `optional_present=3`, `missing_configs=[]`, and `parse_status_counts={PARSED_MAPPING: 11}`.
- Eleven current-workspace config files were copied into `calibrators/datasets/config_snapshot_reference_post_03u/config_snapshot/`, each with size, sha256, modified_time_utc, parse_status, and top-level keys.
- The extracted current-reference NRR state shows `decision_making.low_vol_cost_floor_gate.enabled=true`, `enforce_in_modes=[testnet, hybrid_live_data_testnet_exec]`, `observe_only_in_modes=[live, production]`, `regimes=[LOW_VOLATILITY]`, `target_net_fee_multiple=2.0`, `min_tp_fee_coverage=3.0`, `min_rr=1.2`, `min_regime_confidence_by_regime.LOW_VOLATILITY=0.39`, `min_direction_confidence_by_regime.LOW_VOLATILITY=0.25`, `min_raw_score_by_regime.LOW_VOLATILITY=0.25`, and `min_normalized_confidence_by_regime.LOW_VOLATILITY=0.25`.
- The extracted current-reference direction-confidence surface shows `raw_signed_score_sources=[signal_score, final_score]`, `normalized_confidence_sources=[strategy_confidence]`, `judge_confidence_live_producer_required=false`, and `missing_policy=fail_closed`.
- The extracted current-reference directional-sanity surface shows `nrr027_enabled=false`; `NRR-028`, `NRR-029`, and `NRR-030` were not present in the current reference YAML surface.
- The relevant discoverable Pydantic model path is `apps/reference/config/domains/decision_making.py` for `LowVolCostFloorGateConfig`.
- The accepted LOW_VOL evidence audit reported `accepted_economics_low_vol_trade_count=0`, `realized_rows_total=12`, `objective_rows_total=334`, `order_log_rows_total=761`, `decision_ledger_rows_total=334`, and `regime_confidence_audit_low_vol_rows=1684`.
- Accepted LOW_VOL audit class counts are `CANONICAL_ACCEPTED_LOW_VOL_CLOSE=0`, `ACCEPTED_LOW_VOL_DECISION_NO_CLOSE=0`, `LOW_VOL_CLOSE_NON_CANONICAL=0`, `LOW_VOL_SIDE_CAR_CLOSE_ONLY=0`, `LOW_VOL_DIAGNOSTIC_ONLY=1`, and `NO_LOW_VOL_ACCEPTED_EVIDENCE=0`.
- The single diagnostic-only row is `rid=aurora_BTCUSDT_1778669703907`, `symbol=BTCUSDT`, `side=short`, `realized_pnl_net=11.472228600000001`, with data quality `LOW_VOL_REFERENCE_INFERENCE_CONFLICTS_WITH_ACCEPTED_ECONOMICS_REGIME_SUMMARY`.
- The rejected-vs-accepted comparison artifact classified `comparison_status=ACCEPTED_LOW_VOL_COMPARISON_BLOCKED` with reason `No accepted LOW_VOL close or accepted-decision evidence was found in canonical or runtime-adjacent surfaces.`
- The same comparison artifact preserved package B segment facts: rejected LOW_VOL `SELL` segment rows=114 with `estimated_net_pnl_quote=843.7659235853`; rejected LOW_VOL `BUY` segment rows=39 with `estimated_net_pnl_quote=-452.7182366138`; direction-only failure segment rows=101 with `estimated_net_pnl_quote=585.82653016`; dual failure segment rows=52 with `estimated_net_pnl_quote=-194.7788431885`.

## inferences
- The future config snapshot contract is now defined concretely enough to remove this blocker on the next frozen runtime capture, but it does not retroactively make 03U config-authoritative.
- Current-workspace config hashes are useful only as a comparison reference. They cannot prove what config produced the 03U runtime window because the 03U bundle did not freeze them at runtime start.
- Accepted LOW_VOL comparison remains blocked on authoritative evidence, not on missing parsing or missing runtime surfaces. The package found only one diagnostic-only low-vol inference and zero admitted LOW_VOL closes or accepted LOW_VOL decision rows.
- That single diagnostic-only row is not strong enough to reopen comparison because it conflicts with the authoritative accepted-economics regime summary, which still reports zero accepted LOW_VOL canonical closes.
- Threshold patching remains blocked. Package B already showed mixed rejected replay, and package C still lacks both historical config authority for 03U and an admitted LOW_VOL comparison cohort.

## assumptions
- `accepted_closed_trade_economics_deepdive.json` remains the authoritative accepted canonical realized regime summary for the current post-03T window.
- Explicit LOW_VOL markers joined through frozen order_log and decision_ledger are stronger evidence than ambient `regime_confidence_audit_v1.jsonl` rows when classifying accepted LOW_VOL candidates.
- The current-workspace reference snapshot is intended for future diffing and capture-pipeline hardening, not as retroactive proof for 03U.

## unknowns
- Why `aurora_BTCUSDT_1778669703907` yields a LOW_VOL diagnostic-only inference while the accepted-economics regime summary still reports zero accepted LOW_VOL canonical closes.
- Whether a future runtime window with a frozen config snapshot will produce admitted LOW_VOL closes or admitted LOW_VOL decision rows.
- Whether `NRR-028`, `NRR-029`, and `NRR-030` are absent by design from the current runtime config surface or defined elsewhere outside the audited YAML surface.

## config_snapshot_contract
| Config | Required | Snapshot Status | Parse Status | Notes |
| --- | --- | --- | --- | --- |
| config/aurora/domains.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | LOW_VOL gate thresholds and decision-making config present |
| config/aurora/trading.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | trading envelope config present |
| config/aurora/strategies.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | strategy routing config present |
| config/aurora/strategies/aurora.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | aurora strategy config present |
| config/aurora/strategies/md_amr.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | md_amr strategy config present |
| config/aurora/strategies/mean_reversion.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | mean_reversion strategy config present |
| config/aurora/regime.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | regime config present |
| config/aurora/observability.yaml | yes | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | observability config present |
| config/alpha_search.yaml | optional | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | optional alpha_search config present |
| config/judge_review.yaml | optional | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | optional judge_review config present |
| config/judge_simulator.yaml | optional | COPIED_TO_CURRENT_REFERENCE | PARSED_MAPPING | optional judge_simulator config present |

## current_config_reference
Caveat: `CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY`.

| Config | SHA256 | Notes |
| --- | --- | --- |
| config/aurora/domains.yaml | cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962 | top-level keys: debug, decision_making, execution_position, feature_engineering, objective_engine, position_tracking, risk_management, shadow_telemetry, ta_features |
| config/aurora/trading.yaml | 82831ed38641795e082f5145262b1ae55a5075e50bcd6ba57fe7d14fe753fbbc | top-level keys: binance_api, trading |
| config/aurora/strategies.yaml | 23984d9512aa93a218abfa91c3c85046f7513afccf2eab51bfd2b271122a21be | top-level keys: arbitration, assignments, version |
| config/aurora/strategies/aurora.yaml | 9e3e7f44a68c899471693ce6e928f7df4eecc21a23441bdd6762f8975e9615be | top-level keys: aurora |
| config/aurora/strategies/md_amr.yaml | 390979c1d75881c98080de96f2eeccec92af295505b7cc2bc3d67c44ce1d06d7 | top-level keys: md_amr |
| config/aurora/strategies/mean_reversion.yaml | d2393c2fe243ee73c6d93266a7a1ffdd141dc5b2fc246f5804b3afb3ccc7acbb | top-level keys: mean_reversion |
| config/aurora/regime.yaml | e2d9cb49d02f74cbe1122c0157aee9e6493ad8e2b392e311646f3ef04ecf2396 | regime detector config |
| config/aurora/observability.yaml | 5479754806940ed74f7262ac6d8a5d21c7b8511084617fa2011437bbb9cc1f6c | observability config |
| config/alpha_search.yaml | 24d41e098dda6c613f2e6faf2dcb4409b62ab7fea78952e92b83d1c191a34494 | optional alpha_search config |
| config/judge_review.yaml | a82a911f28b32bc033e29be99ad4ba128511ded8f8a2ede298d423df7857f233 | optional judge_review config |
| config/judge_simulator.yaml | e6bade3522d247f1f7b3f65bf89e029e0cb51d4da46cd9e74972d3910bdf8d68 | optional judge_simulator config |

## nrr_config_state_reference
| Gate/Surface | Current Reference State | Runtime Authority? | Notes |
| --- | --- | --- | --- |
| NRR-062 enabled | true | no | current-workspace reference only |
| NRR-062 enforce_in_modes | testnet, hybrid_live_data_testnet_exec | no | from `decision_making.low_vol_cost_floor_gate` |
| NRR-062 observe_only_in_modes | live, production | no | from `decision_making.low_vol_cost_floor_gate` |
| NRR-062 thresholds | target_net_fee_multiple=2.0; min_tp_fee_coverage=3.0; min_rr=1.2; LOW_VOL min_regime=0.39; LOW_VOL min_direction=0.25 | no | current-workspace reference only |
| NRR-062 source/scale family | raw sources=signal_score, final_score; normalized sources=strategy_confidence; threshold surfaces=min_raw_score_by_regime, min_normalized_confidence_by_regime, min_direction_confidence_by_regime, min_regime_confidence_by_regime | no | YAML exposes candidate families, not frozen runtime-selected authority |
| NRR-027 enabled | false | no | `decision_making.directional_sanity.nrr027_enabled` |
| NRR-028 enabled | NOT_PRESENT_IN_CURRENT_REFERENCE | no | key not found in current YAML surface |
| NRR-029 enabled | NOT_PRESENT_IN_CURRENT_REFERENCE | no | key not found in current YAML surface |
| NRR-030 enabled | NOT_PRESENT_IN_CURRENT_REFERENCE | no | key not found in current YAML surface |
| Pydantic model path | apps/reference/config/domains/decision_making.py :: LowVolCostFloorGateConfig | n/a | discoverable implementation anchor |

## accepted_low_vol_audit
| Class | Count | Notes |
| --- | --- | --- |
| CANONICAL_ACCEPTED_LOW_VOL_CLOSE | 0 | no admitted LOW_VOL canonical close found |
| ACCEPTED_LOW_VOL_DECISION_NO_CLOSE | 0 | no admitted LOW_VOL decision without close found |
| LOW_VOL_CLOSE_NON_CANONICAL | 0 | no non-canonical LOW_VOL close found |
| LOW_VOL_SIDE_CAR_CLOSE_ONLY | 0 | no sidecar-only LOW_VOL close found |
| LOW_VOL_DIAGNOSTIC_ONLY | 1 | `aurora_BTCUSDT_1778669703907` conflicts with authoritative accepted-economics regime summary |
| NO_LOW_VOL_ACCEPTED_EVIDENCE | 0 | not used because one diagnostic-only inference exists |

## rejected_vs_accepted_low_vol
Comparison status: `ACCEPTED_LOW_VOL_COMPARISON_BLOCKED`.

Reason:
- No accepted LOW_VOL close or accepted-decision evidence was found in canonical or runtime-adjacent surfaces.
- The only non-zero accepted-side class is `LOW_VOL_DIAGNOSTIC_ONLY=1`, which is not authoritative enough for a rejected-vs-accepted regime-surface comparison.
- Therefore rejected LOW_VOL `SELL` vs accepted LOW_VOL `SELL`, rejected LOW_VOL `BUY` vs accepted LOW_VOL `BUY`, direction-only failure rows vs accepted LOW_VOL analogs, and dual-failure rows vs accepted LOW_VOL analogs all remain blocked.

## calibration_readiness
- CONFIG_AUTHORITY_READY_FOR_FUTURE_RUNS: yes
- CURRENT_03U_CONFIG_AUTHORITY_GAP_REMAINS: yes
- ACCEPTED_LOW_VOL_COMPARISON_AVAILABLE: no
- ACCEPTED_LOW_VOL_COMPARISON_BLOCKED: yes
- PATCH_READY: no
- PATCH_BLOCKED: yes

Blockers:
- 03U still lacks a frozen config snapshot, so its gate-state authority cannot be upgraded retroactively.
- Accepted LOW_VOL comparison remains unavailable because there are zero admitted LOW_VOL canonical closes and zero admitted LOW_VOL decision rows in current authoritative surfaces.
- Package B rejected replay remains mixed and timeout-dominated, so absent accepted LOW_VOL analogs there is still no safe threshold-patch justification.

## changes_made
- Added offline helper `artifacts/_tmp/phenix_nrr062_package_c_config_snapshot_and_low_vol_audit.py`.
- Added focused tests `tests/tools/test_nrr062_package_c_config_snapshot_and_low_vol_audit.py`.
- Generated contract artifacts under `calibrators/datasets/config_snapshot_contract/`.
- Generated current-workspace reference snapshot plus NRR reference artifacts under `calibrators/datasets/config_snapshot_reference_post_03u/`.
- Generated accepted LOW_VOL audit and blocked comparison artifacts under `calibrators/datasets/nrr062_accepted_low_vol_comparison/`.
- Created this report only.

## validation
- Focused helper tests:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/tools/test_nrr062_package_c_config_snapshot_and_low_vol_audit.py -q`
  - result: `5 passed in 0.86s`.
- Package C generation:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe artifacts/_tmp/phenix_nrr062_package_c_config_snapshot_and_low_vol_audit.py`
  - result: `required_present=8`, `required_files=8`, `accepted_low_vol_status=LOW_VOL_DIAGNOSTIC_ONLY_ROWS_PRESENT`, `comparison_status=ACCEPTED_LOW_VOL_COMPARISON_BLOCKED`.
- JSON/YAML/hash integrity:
  - custom Python validation over generated JSON and copied config snapshot
  - result: `json_files_valid=5`, `manifest_entries_verified=11`, `yaml_module_available=true`, `yaml_files_safe_parsed=11`.
- Import boundary regression:
  - `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/test_calibrators_import_boundary.py -q`
  - result: `1 passed in 2.47s`.
- Top-level config dirtiness check:
  - `git status --short -- config`
  - result remained `M config/aurora/domains.yaml`, `M config/aurora/observability.yaml`, `M config/aurora/strategies.yaml`, `M config/aurora/trading.yaml`, matching the pre-package baseline without new top-level config dirtiness.

## runtime_behavior_change
- trading behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_recommended_package
CALIBRATORS_CONFIG_PACKAGE_B_FREEZE_CONFIG_IN_RUNTIME_CAPTURE_PIPELINE
