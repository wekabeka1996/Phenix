# NRR062_J_TO_L_SIDECAR_CONFIG_DIFF

## Summary

- Package J and Package L were captured on the same tracked commit: `34a3b0cce8db834a6550e8087478cf6327d2df9d`.
- `config/aurora/strategies/aurora.yaml` was identical between the J and L snapshots: `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85`.
- `config/aurora/domains.yaml` changed from `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477` in J to `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` in L.
- On the inspected sidecar authority surface, the J-to-L behavior delta is `execution_position.position_policy_sidecar.mode: shadow -> enable`.
- The workspace observed at package start matched the J `domains.yaml` hash and sidecar mode; after baseline restore it matches the L hash and mode.

## J to L Sidecar Surface

| Field | J Snapshot | L Snapshot | Current | Meaning |
| --- | --- | --- | --- | --- |
| `config/aurora/domains.yaml.sha256` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477` | `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477 -> 3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | Whole-file drift is real; after restore the workspace matches the accepted clean-snapshot hash. |
| `config/aurora/strategies/aurora.yaml.sha256` | `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85` | `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85` | `67cbe3b6f4263aa6a335813bd6940b8b97294f6a2657c185f5a14e70fa791882` | J and L strategy surface is unchanged; current local strategy drift exists but is outside the sidecar authority seam. |
| `execution_position.position_policy_sidecar.mode` | `shadow` | `enable` | `shadow -> enable` | This is the authority-relevant drift: `shadow` suppresses live close command emission while `enable` allows the bounded soft-close path. |
| `execution_position.position_policy_sidecar.peak_giveback_close.enabled` | `false` | `false` | `false` | Peak-giveback remained disabled in both snapshots and after restore; it is not the source of the J-to-L authority change. |
| `execution_position.position_policy_sidecar.shadow_percent_notional_arm.enabled` | `true` | `true` | `true` | Shadow percent-of-notional telemetry arm stayed enabled throughout. |
| `execution_position.position_policy_sidecar.shadow_fee_aware_arm.enabled` | `true` | `true` | `true` | Shadow fee-aware telemetry arm stayed enabled throughout. |
| `execution_position.position_policy_sidecar.allowed_actions.soft_close_symbol_current_net_only` | `true` | `true` | `true` | The bounded action scope itself did not widen; only mode changed whether that bounded soft-close path can emit live close requests. |
| `execution_position.position_policy_sidecar.allowed_actions.partial_reduce` | `false` | `false` | `false` | Forbidden authority remained forbidden. |
| `execution_position.position_policy_sidecar.allowed_actions.bracket_mutation` | `false` | `false` | `false` | Forbidden authority remained forbidden. |
| `execution_position.position_policy_sidecar.allowed_actions.exact_targeting` | `false` | `false` | `false` | Forbidden authority remained forbidden. |

## Snapshot Cleanliness

| Package | Commit | `dirty_config_paths` contains `config/aurora/domains.yaml` | Interpretation |
| --- | --- | --- | --- |
| J | `34a3b0cce8db834a6550e8087478cf6327d2df9d` | yes | J sidecar mode came from a dirty workspace copy, not a clean tracked baseline. |
| L | `34a3b0cce8db834a6550e8087478cf6327d2df9d` | no | L sidecar mode reflects the tracked baseline at the same commit. |

## Minimal Conclusion

The J-to-L sidecar drift is mode-only on the inspected authority seam. The mode delta is material because it changes whether the already-bounded sidecar soft-close path can emit live close commands.
