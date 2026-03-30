# MR Test Proof Matrix (Independent)

Legend for strength:

- `direct`: directly exercises the exact contract surface it claims
- `indirect`: useful evidence, but only through a helper or simplified setup
- `weak`: assertion is too shallow for the claim being made
- `stale`: report claim no longer matches current test file

## tests/config/test_mr_microstructure_veto_config.py

| Test file | Test name | Exact claim report says it proves | What it actually proves | Strength | Trustworthy? |
|---|---|---|---|---|---|
| tests/config/test_mr_microstructure_veto_config.py | test_valid_config_loads | valid V1 config loads | direct Pydantic instantiation works | direct | yes - exact config-model proof |
| tests/config/test_mr_microstructure_veto_config.py | test_extra_field_rejected | V1 is strict / extra forbidden | unknown fields are rejected by Pydantic | direct | yes - exact strictness proof |
| tests/config/test_mr_microstructure_veto_config.py | test_tfi_threshold_zero_rejected | tfi lower bound enforced | rejects zero threshold | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_tfi_threshold_above_one_rejected | tfi upper bound enforced | rejects threshold above one | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_obi_threshold_zero_rejected | obi lower bound enforced | rejects zero threshold | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_obi_threshold_above_one_rejected | obi upper bound enforced | rejects threshold above one | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_absorption_rebound_equals_continuation_rejected | rebound must be below continuation | validator rejects equality | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_absorption_rebound_exceeds_continuation_rejected | rebound must be below continuation | validator rejects larger rebound threshold | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_missing_policy_invalid_value_rejected | only allowed missing_policy values accepted | arbitrary invalid literal rejected | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_missing_policy_skip_rejected | skip removed from active contract | current model rejects `skip` | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_readiness_min_bars_zero_rejected | readiness lower bound enforced | zero rejected | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_tfi_ema_span_below_minimum_rejected | EMA span lower bound enforced | one rejected | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_yaml_load_wires_microstructure_veto | YAML path wires V1 globally | `MeanReversion1mStrategyConfig` accepts V1 block in synthetic data | indirect | yes - model wiring only, not full loader |
| tests/config/test_mr_microstructure_veto_config.py | test_yaml_load_without_microstructure_veto | V1 block optional | config accepts absent block | direct | yes |
| tests/config/test_mr_microstructure_veto_config.py | test_per_asset_microstructure_veto_override | per-asset override wiring works | override model accepts nested V1 block | direct | yes |

## tests/domains/decision_making/test_mr_microstructure_veto.py

| Test file | Test name | Exact claim report says it proves | What it actually proves | Strength | Trustworthy? |
|---|---|---|---|---|---|
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_toxic_flow_down_blocks_long | adverse sell flow plus downside continuation blocks LONG | helper `_check_microstructure_veto()` blocks for handcrafted TFI and nested price_motion | indirect | yes - helper branch proof only |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_toxic_flow_up_blocks_short | adverse buy flow plus upside continuation blocks SHORT | helper blocks for handcrafted inputs | indirect | yes - helper branch proof only |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_absorption_long_allows | lower-wick absorption allows LONG | helper allows handcrafted wick-absorption case | indirect | yes - helper branch proof only |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_absorption_short_allows | upper-wick absorption allows SHORT | helper allows handcrafted wick-absorption case | indirect | yes - helper branch proof only |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_missing_tfi_blocks_when_policy_block | missing TFI fail-closes | helper blocks when TFI absent | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_skip_policy_rejected_at_config_level | skip no longer allowed | V1 config builder rejects `skip` | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_missing_obi_blocks_when_confirm_enabled | missing OBI fail-closes when confirm enabled | helper blocks missing OBI | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_warmup_not_ready_blocks | readiness warmup blocks | helper returns NOT_READY below bar threshold | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_obi_confirm_only_not_sole_driver | OBI is confirm-only | helper allows when TFI adverse but OBI does not confirm | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_obi_confirms_adverse_flow_blocks | adverse OBI confirmation participates in block | helper blocks when both TFI and OBI are adverse | indirect | yes - helper-level only |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_non_adverse_tfi_allows | non-adverse TFI does not veto | helper allows below threshold | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_veto_disabled_always_allows | disabled or absent veto allows | helper returns allow when config absent | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_rebound_allows_despite_adverse_tfi | favorable rebound allows absorption path | helper allows when handcrafted nested `features.price_motion.ret_60s` rebounds | indirect | no - runtime payload shape is not proven for MR CMD |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_no_features_cached_blocks | no cached features fail-close | helper blocks when feature cache missing | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_invalid_tfi_blocks_unconditionally | invalid TFI always blocks | helper blocks non-numeric TFI | direct | yes |
| tests/domains/decision_making/test_mr_microstructure_veto.py | test_zero_range_bar_blocks | zero-range bars block | helper blocks zero-range bar | direct | yes |

## tests/config/test_mr_directional_bias_config.py

| Test file | Test name | Exact claim report says it proves | What it actually proves | Strength | Trustworthy? |
|---|---|---|---|---|---|
| tests/config/test_mr_directional_bias_config.py | test_valid_config_loads | valid V2 config loads | direct Pydantic instantiation works | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_extra_field_rejected | V2 is strict / extra forbidden | unknown fields rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_base_long_below_clamp_min_rejected | long threshold must respect clamp floor | rejects below-floor base long | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_base_short_above_clamp_max_rejected | short threshold must respect clamp ceiling | rejects above-ceiling base short | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_clamp_min_equals_clamp_max_rejected | clamp min < clamp max invariant | equality rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_clamp_min_exceeds_clamp_max_rejected | clamp min < clamp max invariant | inverted range rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_funding_shift_magnitude_negative_rejected | shift magnitude lower bound enforced | negative value rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_funding_shift_magnitude_too_large_rejected | shift magnitude upper bound enforced | oversized value rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_funding_normalization_zero_rejected | normalization scale must be positive | zero rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_funding_deadband_negative_rejected | deadband lower bound enforced | negative deadband rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_funding_deadband_above_one_rejected | deadband upper bound enforced | deadband above one rejected | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_yaml_wires_directional_bias | YAML path wires V2 globally | synthetic config accepts V2 block | indirect | yes - model wiring only |
| tests/config/test_mr_directional_bias_config.py | test_yaml_without_directional_bias | V2 block optional | config accepts absent V2 block | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_per_asset_directional_bias_override | per-asset V2 override wiring works | override model accepts nested V2 block | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_symmetric_thresholds_accepted | legacy symmetric split remains legal | equal thresholds accepted | direct | yes |
| tests/config/test_mr_directional_bias_config.py | test_asymmetric_thresholds_accepted | asymmetric split is legal | unequal thresholds accepted | direct | yes |

## tests/domains/decision_making/test_mr_directional_bias.py

| Test file | Test name | Exact claim report says it proves | What it actually proves | Strength | Trustworthy? |
|---|---|---|---|---|---|
| tests/domains/decision_making/test_mr_directional_bias.py | test_static_split_without_funding | missing funding falls back to static split | helper sets base thresholds when funding absent | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_positive_funding_shifts | positive funding shifts long/short thresholds correctly | helper computes `0.08` and `0.12` thresholds | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_negative_funding_shifts | negative funding shifts long/short thresholds correctly | helper computes `0.12` and `0.08` thresholds | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_clamp_prevents_too_low | clamp floor works | helper clamps long to floor | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_clamp_prevents_too_high | clamp ceiling works | helper clamps short to ceiling | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_deadband_suppresses_noise | deadband suppresses small funding | helper zeros small normalized funding | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_missing_funding_returns_static | missing funding yields static split | helper sets base thresholds | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_missing_funding_does_not_block_strategy | missing funding does not block trading | only proves thresholds are not `None`; does not drive a real signal or handler flow | weak | no - claim is overstated |
| tests/domains/decision_making/test_mr_directional_bias.py | test_no_bias_config_clears_overrides | no bias config clears overrides | helper sets both overrides to `None` | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_split_thresholds_affect_long_signal | split thresholds affect LONG signal path | does not assert actual signal boundary or signal outcome; only preserves config values after bar feeding | weak | no - does not prove signal path |
| tests/domains/decision_making/test_mr_directional_bias.py | test_split_thresholds_affect_short_signal | split thresholds affect SHORT signal path | does not assert actual signal boundary or signal outcome; only checks config fields | weak | no - does not prove signal path |
| tests/domains/decision_making/test_mr_directional_bias.py | test_invalid_funding_degrades_to_static | invalid funding degrades to static split | helper sets base thresholds on parse failure | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_zero_funding_no_shift | zero funding yields no shift | helper preserves base thresholds | direct | yes |
| tests/domains/decision_making/test_mr_directional_bias.py | test_trigger_boundary_positive_funding | positive funding trigger geometry is correct | computes threshold-derived boundaries, not full strategy signal firing | indirect | yes - good math evidence, not full end-to-end proof |
| tests/domains/decision_making/test_mr_directional_bias.py | test_trigger_boundary_negative_funding | negative funding trigger geometry is correct | computes threshold-derived boundaries, not full strategy signal firing | indirect | yes - good math evidence, not full end-to-end proof |
| tests/domains/decision_making/test_mr_directional_bias.py | test_cross_symbol_no_contamination | cross-symbol isolation proven | helper uses separate strategy instances and different symbol feature maps | indirect | yes - supportive, but not real `_on_process_strategy` flow |
| tests/domains/decision_making/test_mr_directional_bias.py | test_cross_symbol_missing_funding_does_not_inherit | missing funding does not inherit stale thresholds | helper proves separate objects keep separate state | indirect | yes - supportive |
| tests/domains/decision_making/test_mr_directional_bias.py | test_interleaved_symbol_processing_order | interleaving symbols does not leak state | helper-level interleaving on separate strategies | indirect | yes - supportive |
| tests/domains/decision_making/test_mr_directional_bias.py | test_thresholds_cleared_after_on_bar_simulation | actual finally cleanup is proven | only simulates manual clearing after helper call; does not execute real finally block | weak | no - not actual call-site proof |

## Matrix summary

### Strongest evidence

1. Config-model strictness and validators for both vectors.
2. Helper-level V1 branch behavior for missing/invalid inputs, warmup, OBI confirmation, and zero-range handling.
3. Helper-level V2 threshold formulas, clamp behavior, and deadband behavior.

### Weakest evidence

1. V1 runtime payload compatibility with real FE -> CMD shape.
2. V2 tests claiming real signal-path proof from split thresholds.
3. V2 cleanup proof for the actual try/finally call site.

### Overall test-proof verdict

The suite is useful and non-trivial, but it is not strong enough to justify the more ambitious report claims about full runtime integration or complete proof of enablement safety.
