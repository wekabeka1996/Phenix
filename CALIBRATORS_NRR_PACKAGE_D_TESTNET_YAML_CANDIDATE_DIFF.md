# CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_CANDIDATE_DIFF

## package_verdict
- YAML_ONLY_SEGMENT_NOT_SUPPORTED_NO_PATCH

## target_surface
- [config/aurora/domains.yaml](config/aurora/domains.yaml)

## classification
- ONLY_REGIME_LEVEL_SUPPORTED

## baseline_hash
- domains.yaml sha256 before package decision: cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962

## post_decision_hash
- domains.yaml sha256 after package decision: cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962

## package_level_yaml_diff
- none

## why_no_yaml_diff
- The current LOW_VOL gate contract can express regime-level thresholds, raw-vs-normalized threshold families, and strategy+symbol overrides.
- It cannot express the requested SELL or SHORT-only slice.
- It cannot express a direction-only-failure-only slice.
- It cannot express a mode-specific threshold override inside low_vol_cost_floor_gate.thresholds.
- Because the gate is explicitly enforced in both testnet and hybrid_live_data_testnet_exec, lowering the shared LOW_VOL threshold without a narrower selector would spill across both BUY and SELL inside those enforced modes.
- The user instruction explicitly disallowed a broad LOW_VOL relaxation when the requested narrow segment cannot be isolated safely.

## exact_yaml_diff
```diff
No package-level change was applied to config/aurora/domains.yaml.
```
