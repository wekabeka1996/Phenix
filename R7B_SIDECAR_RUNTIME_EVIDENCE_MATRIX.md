# R7B SIDECAR RUNTIME EVIDENCE MATRIX

| Row | Scope | Runtime evidence | Observed facts | Interpretation |
|---|---|---|---|---|
| 1 | `__DOMAIN__` activation | `trade_lifecycle.jsonl`, `ts_ms=1776883274831`, `event_type=POSITION_POLICY_SIDECAR_MODE_ACTIVE` | `mode=enable`, `evaluation_mode=bounded_soft_close_policy`, `reason_codes=[sidecar_initialized]` | Sidecar boot after restart is directly proven. |
| 2 | Suppressed-only symbols | `1000PEPEUSDT`, `DOGEUSDT`, `ETHUSDT`, `SOLUSDT` in `trade_lifecycle.jsonl` | No evaluated rows; dominant reason is `no_manage_flow_for_symbol`; `SOLUSDT` also shows `startup_grace_active` | These symbols did not produce open lifecycles for peak-giveback observation in this slice. |
| 3 | `XRPUSDT` lifecycle `aurora_XRPUSDT_1776884702659` | evaluated window `1776885003031 -> 1776886515391`, 17 evaluated rows | `side=SELL`, `manage_state=BRACKETS_PENDING`, populated qty/entry/position_amt; `mark_price`/`unrealized_pnl_*` blank | Standard sidecar evaluation is live on a real open lifecycle, but peak-giveback economics are not visible. |
| 4 | `XRPUSDT` terminal ambiguity safety | five suppressions at `1776885306162`, `1776885306321`, `1776885306698`, `1776885309948`, `1776885315793` | `suppression_reason=recent_terminal_order_state_detected`, `incumbent_owner=OrderGuardian`, `portfolio_snapshot_status=present` | Sidecar correctly suppresses under recent terminal order-state ambiguity. |
| 5 | `XRPUSDT` lifecycle `aurora_XRPUSDT_1776907803152` | evaluated window `1776908101822 -> 1776936314371`, 369 evaluated rows | open lifecycle stayed in `BRACKETS_PENDING`; no peak-giveback recommendation/request traces observed | Long active lifecycle proves ongoing evaluation but not arm/trigger correctness. |
| 6 | `XRPUSDT` lifecycle `aurora_XRPUSDT_1776940804421` | evaluated window `1776941405502 -> 1776945915414`, 60 evaluated rows | later SELL lifecycle; first/last snapshots still lack `mark_price` and `unrealized_pnl_*` | Economic trigger inputs remain invisible even in later runtime windows. |
| 7 | `BNBUSDT` lifecycle `aurora_BNBUSDT_1776888006471` | evaluated window `1776888302967 -> 1776888617104`, 8 evaluated rows | `side=SELL`, `manage_state=BRACKETS_PENDING`, real position payload, blank PnL fields | Sidecar observed a short-lived open lifecycle with no trigger evidence. |
| 8 | `BNBUSDT` lifecycle `aurora_BNBUSDT_1776903303598` | evaluated window `1776903602548 -> 1776936314365`, 423 evaluated rows | long SELL lifecycle, repeated evaluation, no recommendation/request events | Strong proof of live evaluation; still no peak-giveback-specific runtime proof. |
| 9 | `BNBUSDT` lifecycle `aurora_BNBUSDT_1776957305906` | evaluated window `1776957603638 -> 1776957615869`, 3 evaluated rows | `side=BUY`, `manage_state=BRACKETS_PENDING`, real position payload, blank PnL fields | The path works across both SELL and BUY lifecycles, but economics are still not exposed. |
| 10 | `BTCUSDT` lifecycle `aurora_BTCUSDT_1776945606579` | evaluated window `1776945900078 -> 1776956112434`, 133 evaluated rows | `side=SELL`, `portfolio_snapshot_status=present`, no valid PnL values | Another real evaluated lifecycle with no direct peak-giveback proof. |
| 11 | Post-close cleanup | reconcile suppressions at `1776886571530`, `1776888653891`, `1776936437416`, `1776936437425`, `1776945998516`, `1776956129098`, `1776957835168` | every row is `POSITION_POLICY_SIDECAR_SUPPRESSED` with `suppression_reason=manage_flow_has_no_active_lifecycle`, `manage_state=FLAT`, `portfolio_snapshot_status=symbol_absent` | Sidecar stops cleanly after close reconciliation and does not linger into duplicate action. |
| 12 | Negative trigger chain scan | no hits in `trade_lifecycle.jsonl`, `domain_execution_position.log*`, `order_log_v1.jsonl`, `shadow_critical_event_journal_v1.jsonl` for `POSITION_POLICY_SIDECAR_RECOMMENDED`, `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`, `position_policy_sidecar:peak_giveback`, `peak_giveback_threshold_met` | zero peak-giveback-specific runtime signatures observed | This slice cannot prove that the new trigger path actually armed or fired. |

## Summary Notes

- Observed evaluated symbols: `BNBUSDT`, `BTCUSDT`, `XRPUSDT`
- Observed evaluated lifecycles: `7`
- Observed terminal suppressions: `5`, all safe
- Observed post-close reconcile suppressions: `7`, all safe
- Observed sidecar recommendations: `0`
- Observed sidecar close requests: `0`
- Observed valid runtime PnL fields in evaluated payloads: `0`
