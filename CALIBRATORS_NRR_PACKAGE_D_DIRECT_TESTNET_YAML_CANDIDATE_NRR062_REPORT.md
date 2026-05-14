# AGENT_REPORT_V1

## verdict
- YAML_ONLY_SEGMENT_NOT_SUPPORTED_NO_PATCH

## problem_framing
- This package targets a minimal testnet candidate decision for NRR-062, not a production calibration.
- Package B showed mixed replay evidence: the positive surface was concentrated in rejected SELL rows and direction-only failures, while BUY rows and dual regime+direction failures were negative, and the full cohort remained timeout-dominated.
- Because the user explicitly disallowed new runtime code and broad LOW_VOL relaxation, the question here was not whether a lower threshold could help somewhere, but whether the existing YAML contract can isolate that positive segment safely inside testnet and hybrid execution modes.

## facts
- Pre-change git capture stayed on branch main at commit e837f16ff8b6c2fd3fd41a3812c78237cc3a1427 with a dirty worktree before this package began.
- Package A report confirms the canonical NRR-062 reject cohort is 153 rows and all 153 rows carry structured LOW_VOL metadata.
- Package B report confirms replay outcomes TP=33, SL=13, TIMEOUT=107, net proxy +391.0476869715, SELL segment +843.7659235853, BUY segment -452.7182366138, direction-only failure pattern +585.82653016, and dual regime+direction failure pattern -194.7788431885.
- Package B verdict is INCONCLUSIVE_TIMEOUT_DOMINATED, not threshold-patch ready.
- Package C report confirms the current workspace LOW_VOL gate reference is enabled=true, enforce_in_modes=[testnet, hybrid_live_data_testnet_exec], observe_only_in_modes=[live, production], LOW_VOL min_regime_confidence=0.39, LOW_VOL min_direction_confidence=0.25, target_net_fee_multiple=2.0, min_tp_fee_coverage=3.0, and min_rr=1.2.
- Package C report also confirms NRR-027 is false and NRR-028, NRR-029, and NRR-030 are not present in the current YAML surface.
- Config Package B report confirms future NRR-062 freeze captures now retain config snapshots, so the next runtime collection can be config-authoritative.
- The current LOW_VOL YAML contract in [config/aurora/domains.yaml](config/aurora/domains.yaml) exposes:
  - regime-scoped thresholds
  - raw-vs-normalized threshold families
  - strategy+symbol overrides
  - mode lists for enforce_in_modes and observe_only_in_modes
- The matching Pydantic model in [apps/reference/config/domains/decision_making.py](apps/reference/config/domains/decision_making.py) exposes:
  - LowVolCostFloorThresholdsConfig with min_regime_confidence_by_regime, min_direction_confidence_by_regime, min_raw_score_by_regime, min_normalized_confidence_by_regime, and strategy+symbol overrides
  - LowVolCostFloorGateConfig with enforce_in_modes and observe_only_in_modes
  - no side-specific threshold override
  - no mode-specific threshold override inside thresholds
  - no direction-only-failure selector
  - no per-source threshold override for signal_score vs final_score within the raw family
- The model treats min_direction_confidence_by_regime as a migration alias only. When explicit min_raw_score_by_regime is present, raw gating follows that raw map, not the alias.
- Current domains.yaml sets LOW_VOL min_direction_confidence_by_regime.LOW_VOLATILITY=0.25 and min_raw_score_by_regime.LOW_VOLATILITY=0.25.
- The package-level domains.yaml hash before and after this decision is cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962.
- No package-level YAML mutation was applied.

## inferences
- The exact positive replay slice the user wants is effectively SELL-only plus direction-only plus raw-signed-score-selected. The current YAML contract cannot encode that compound segment.
- A change to LOW_VOL raw or direction thresholds in the current YAML would spill across both BUY and SELL within enforced testnet and hybrid modes because the threshold maps are regime-level, not side-level.
- A change only to min_direction_confidence_by_regime would be unsafe as a candidate because it can become a no-op for the raw threshold family while explicit min_raw_score_by_regime remains 0.25.
- A change to both LOW_VOL min_direction_confidence_by_regime and min_raw_score_by_regime would be a broad regime-level relaxation, not the narrow SELL-only candidate requested.
- Because BUY replay was negative, dual-failure replay was negative, accepted LOW_VOL comparison is still blocked, and the replay cohort was timeout-dominated, a broad regime-level relaxation would hide real risk rather than isolate the supported evidence.

## assumptions
- The current workspace domains.yaml remains the operative testnet and hybrid config surface under review for this package.
- The existing dirty worktree on [config/aurora/domains.yaml](config/aurora/domains.yaml) predates this package and was not introduced here.
- Package B segment summaries are the authoritative replay evidence base for this package.

## unknowns
- Whether a future runtime window with config snapshot freeze and admitted LOW_VOL accepted rows will narrow the candidate enough to justify a YAML-only threshold change.
- Whether a future config extension might add side-specific or mode-specific LOW_VOL threshold selectors without runtime complexity that the user wants to avoid in this package.
- Whether the positive SELL direction-only slice would remain positive once compared against accepted LOW_VOL evidence, which is still unavailable.

## yaml_expressiveness
- Classification: ONLY_REGIME_LEVEL_SUPPORTED
- Supported without Python changes:
  - regime=LOW_VOLATILITY
  - threshold family split between raw_signed_score and normalized_confidence
  - strategy+symbol overrides
  - enforcement vs observe-only mode lists at the gate level
- Not supported without Python changes:
  - side=SELL or SHORT only
  - direction-only failure pattern only
  - mode-specific threshold override inside low_vol_cost_floor_gate.thresholds
  - signal_score-only threshold separate from final_score inside the raw family
  - combined SELL + raw family + direction-only segmentation

## patch_applied
- No YAML patch was applied to [config/aurora/domains.yaml](config/aurora/domains.yaml).
- Package-generated artifacts only:
  - [CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_CANDIDATE_DIFF.md](CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_CANDIDATE_DIFF.md)
  - [CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_ROLLBACK.md](CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_ROLLBACK.md)
  - [CALIBRATORS_NRR_PACKAGE_D_DIRECT_TESTNET_YAML_CANDIDATE_NRR062_REPORT.md](CALIBRATORS_NRR_PACKAGE_D_DIRECT_TESTNET_YAML_CANDIDATE_NRR062_REPORT.md)

## why_this_patch
- No patch was the smallest safe outcome.
- Package B does show a positive SELL replay surface and a positive direction-only failure surface.
- But Package B also shows a negative BUY surface and a negative dual regime+direction failure surface.
- The requested narrow candidate therefore depends on selectors the current YAML contract does not have.
- Applying a regime-level LOW_VOL relaxation under those conditions would turn a targeted hypothesis into a broad mixed-signal experiment.

## explicit_risks
- BUY segment replay was negative.
- Dual-failure segment replay was negative.
- The cohort was timeout-dominated.
- Accepted LOW_VOL comparison is still blocked.
- There is still no production authority claim from this package.
- A broad LOW_VOL regime relaxation would therefore risk admitting rows from negative segments that the config cannot isolate away.

## rollback
- No rollback of YAML is required because no YAML mutation was applied.
- Confirm [config/aurora/domains.yaml](config/aurora/domains.yaml) still hashes to cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962.
- See [CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_ROLLBACK.md](CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_ROLLBACK.md).

## validation
- YAML parse and direct model validation:
  - command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -c from pathlib import Path; import hashlib, yaml, json; from apps.reference.config_loader import ConfigLoader; from apps.reference.config.domains.decision_making import LowVolCostFloorGateConfig; ...
  - result: yaml_parse_ok=true, gate_model_validate_ok=true, config_loader_ok=true, low_vol_min_direction=0.25, low_vol_min_raw=0.25, domains_sha256=cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962
- Focused pytest:
  - command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_decision_making_contracts.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/domains/decision_making/test_low_vol_cost_floor_gate.py tests/test_calibrators_import_boundary.py tests/test_calibrate_low_vol_cost_floor.py tests/tools/test_calibrate_nrr062_historical.py -q
  - result: 115 passed in 16.53s

## runtime_behavior_change
- trading behavior changed: no runtime run yet
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- new events/commands added: no
- registry changed: no

## next_runtime_instruction
- Run the next testnet or hybrid_live_data_testnet_exec runtime with config snapshot freeze enabled through the now-patched capture pipeline.
- Collect both NRR-062 rejects and any accepted LOW_VOL rows that appear in the same frozen window.
- Re-run the Package A and Package B style reject ledger and counterfactual analysis on that config-authoritative bundle.
- Compare accepted LOW_VOL versus rejected LOW_VOL before attempting any YAML threshold relaxation.
- If a future candidate is applied, roll it back immediately if BUY losses rise, sidecar fee drag worsens materially, or LOW_VOL adverse fills spike.
