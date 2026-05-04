# R7O Shadow Field Map

## Config Contract
| name | source | unit | nullable | event/payload location | null reason semantics |
|---|---|---|---|---|---|
| `shadow_percent_notional_arm.enabled` | YAML `position_policy_sidecar.shadow_percent_notional_arm.enabled` | boolean | no | sidecar config model + mode active snapshot | n/a |
| `shadow_percent_notional_arm.candidate_pcts[]` | YAML `position_policy_sidecar.shadow_percent_notional_arm.candidate_pcts` | percent | no | sidecar config model + mode active snapshot | n/a |
| `shadow_percent_notional_arm.candidate_unit` | runtime literal | percent | no | `sidecar_config_snapshot.shadow_percent_notional_arm.candidate_unit` | n/a |

## Peak Giveback Snapshot Additions
Top path: `peak_giveback_snapshot.peak_giveback_shadow_arms.percent_notional`

| name | source | unit | nullable | event/payload location | null reason semantics |
|---|---|---|---|---|---|
| `enabled` | `config.shadow_percent_notional_arm.enabled` | boolean | no | evaluated/scores/suppressed/recommended/close-request peak snapshot | disabled mode may set top-level `null_reason=shadow_percent_notional_arm_disabled` |
| `candidate_unit` | runtime literal | percent | no | same | always `percent` |
| `giveback_trigger_pct` | `config.peak_giveback_close.giveback_trigger_pct` | percent | no | same | n/a |
| `null_reason` | runtime guard | string | yes | same | `shadow_percent_notional_arm_disabled`, `missing_unrealized_pnl_usdt`, `missing_position_notional_usdt` |
| `candidates[]` | runtime over config candidates | array | no | same | empty only if config candidates empty (contract forbids) |

## Candidate Fields
Path: `peak_giveback_snapshot.peak_giveback_shadow_arms.percent_notional.candidates[]`

| name | source | unit | nullable | event/payload location | null reason semantics |
|---|---|---|---|---|---|
| `candidate_pct` | config candidate value | percent | no | same | n/a |
| `arm_threshold_usd` | `abs(qty)*entry_price*candidate_pct/100` | USDT | yes | same | `missing_position_notional_usdt` |
| `is_armed` | shadow per-candidate state | boolean | no | same | n/a |
| `first_arm_ts_ms` | shadow per-candidate state | ms epoch | yes | same | null if never armed |
| `peak_edge_usd` | shadow per-candidate state | USDT | no | same | defaults `0.0` |
| `giveback_pct` | `(peak_edge-current_edge)/peak_edge*100` | percent | yes | same | `missing_unrealized_pnl_usdt`, `peak_edge_not_positive` |
| `threshold_met_under_current_giveback_trigger_pct` | compare `giveback_pct` with current live trigger | boolean | yes | same | `shadow_percent_notional_arm_disabled`, `missing_unrealized_pnl_usdt`, `missing_position_notional_usdt`, `missing_giveback_pct` |
| `would_trigger` | alias of threshold-met (shadow, non-actionable) | boolean | yes | same | same as threshold-met |
| `state` | runtime explainability label | string | no | same | explicit state even in missing data cases |
| `null_reasons` | runtime diagnostics | map[string,string] | no | same | per-field fail-closed reasons |

## State Labels (current)
- `shadow_percent_notional_disabled`
- `shadow_percent_notional_unavailable_economics_missing`
- `shadow_percent_notional_unavailable_notional_missing`
- `shadow_percent_notional_not_armed_below_edge`
- `shadow_percent_notional_below_trigger`
- `shadow_percent_notional_threshold_met`
