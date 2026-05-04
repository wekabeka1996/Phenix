# R7C Runtime Field Map

## Startup Row

| Field | Event(s) | Source | Null allowed | Null semantics |
| --- | --- | --- | --- | --- |
| `sidecar_config_snapshot.mode` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | `self.mode.value` | No | N/A |
| `sidecar_config_snapshot.peak_giveback_close.enabled` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.peak_giveback_close.edge_arm_usd` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.peak_giveback_close.giveback_trigger_pct` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.freshness.portfolio_max_age_ms` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.freshness.features_max_age_ms` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.freshness.regime_max_age_ms` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.freshness.order_state_max_age_ms` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | typed config | No | N/A |
| `sidecar_config_snapshot.source_config_path` | `POSITION_POLICY_SIDECAR_MODE_ACTIVE` | optional config metadata attribute | Yes | `null` means no source-path metadata was attached to the config object |

## Policy Rows

Events carrying `peak_giveback_snapshot`:

- `POSITION_POLICY_SIDECAR_EVALUATED`
- `POSITION_POLICY_SIDECAR_SCORES`
- `POSITION_POLICY_SIDECAR_SUPPRESSED`
- `POSITION_POLICY_SIDECAR_RECOMMENDED`
- `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`

| Field | Source | Null allowed | Null semantics |
| --- | --- | --- | --- |
| `peak_giveback_snapshot.policy_enabled` | typed config `peak_giveback_close.enabled` | No | N/A |
| `peak_giveback_snapshot.mark_price` | `position_snapshot.mark_price` | Yes | `null_reasons.mark_price` explains missing mark price |
| `peak_giveback_snapshot.entry_price` | `position_snapshot.entry_price`, fallback `portfolio_entry_price` | Yes | `null_reasons.entry_price` explains missing entry price |
| `peak_giveback_snapshot.position_qty` | `position_snapshot.position_qty`, fallback absolute `portfolio_position_amt` | Yes | `null_reasons.position_qty` explains missing quantity |
| `peak_giveback_snapshot.side` | `position_snapshot.side` | Yes | `null_reasons.side` explains missing side |
| `peak_giveback_snapshot.unrealized_pnl_usdt` | `position_snapshot.unrealized_pnl_usdt` | Yes | `null_reasons.unrealized_pnl_usdt` explains missing current economic edge |
| `peak_giveback_snapshot.unrealized_pnl_pct` | `position_snapshot.unrealized_pnl_pct` | Yes | `null_reasons.unrealized_pnl_pct` explains missing percent view |
| `peak_giveback_snapshot.peak_edge_usd` | sidecar symbol state | No | `0.0` is the tracked state value before any armed edge exists |
| `peak_giveback_snapshot.current_edge_usd` | current `unrealized_pnl_usdt` | Yes | `null_reasons.current_edge_usd` explains why the current edge is unavailable |
| `peak_giveback_snapshot.giveback_pct` | derived from `peak_edge_usd` and `current_edge_usd`, or trigger result | Yes | `null_reasons.giveback_pct` distinguishes missing current edge from non-positive peak edge |
| `peak_giveback_snapshot.is_armed` | sidecar symbol state | No | N/A |
| `peak_giveback_snapshot.arm_threshold_usd` | typed config `edge_arm_usd` | No | N/A |
| `peak_giveback_snapshot.giveback_trigger_pct` | typed config `giveback_trigger_pct` | No | N/A |
| `peak_giveback_snapshot.threshold_crossed` | derived from current giveback state or trigger result | Yes | `null_reasons.threshold_crossed` means threshold evaluation was not possible |
| `peak_giveback_snapshot.peak_giveback_state` | derived observability marker | No | N/A |
| `peak_giveback_snapshot.reason_codes` | derived marker set | No | N/A |
| `peak_giveback_snapshot.null_reasons` | per-field null explanation map | No | Empty object means no null-economics explanation was needed |

## Peak-Giveback State Markers

- `peak_giveback_disabled`: config disabled.
- `peak_giveback_not_armed_below_edge`: economics present, peak tracked, arm threshold not reached.
- `peak_giveback_armed`: companion marker emitted when the position is armed.
- `peak_giveback_below_trigger`: armed, but giveback remains below the configured trigger.
- `peak_giveback_threshold_met`: configured giveback trigger crossed.
- `peak_giveback_suppressed_close_in_progress`: evaluation surface existed but close-in-progress suppression prevented action.
- `peak_giveback_suppressed_stale_inputs`: stale or missing runtime inputs prevented trustworthy evaluation.
- `peak_giveback_not_ready`: another non-stale suppression blocked evaluation.
- `peak_giveback_unavailable_economics_missing`: open-lifecycle row existed but economic inputs were insufficient for peak-giveback evaluation.

## Trigger Provenance Fields

| Field | Event(s) | Purpose |
| --- | --- | --- |
| `policy_source=position_policy_sidecar` | standard `POSITION_POLICY_SIDECAR_RECOMMENDED` | explicit provenance for score-based recommendations |
| `policy_source=position_policy_sidecar:peak_giveback` | peak-giveback `POSITION_POLICY_SIDECAR_RECOMMENDED`, `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED` | explicit provenance for trigger-driven recommendations and requests |
| `peak_giveback_detail.peak_edge_usd` | peak-giveback recommendation/request | exact tracked peak edge at trigger time |
| `peak_giveback_detail.current_edge_usd` | peak-giveback recommendation/request | exact current edge at trigger time |
| `peak_giveback_detail.giveback_pct` | peak-giveback recommendation/request | exact derived giveback percent at trigger time |
| `peak_giveback_detail.threshold_pct` | peak-giveback recommendation/request | exact configured trigger threshold applied to the decision |
| `score_snapshot.current_edge_usd` | peak-giveback recommendation/request | searchable trigger snapshot in the existing score block |
| `score_snapshot.giveback_trigger_pct` | peak-giveback recommendation/request | searchable configured threshold in the existing score block |
