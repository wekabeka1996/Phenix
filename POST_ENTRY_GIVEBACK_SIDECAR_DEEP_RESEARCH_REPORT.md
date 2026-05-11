# POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT

## Executive verdict

Current evidence says post-entry lifecycle is a plausible profit blocker, but the proof is narrow and asymmetric.

Fresh runtime logs now prove that PositionPolicySidecar is not only a shadow telemetry shell in the current runtime: config mode is enable, the sidecar can emit bounded close requests, and two sidecar-originated close chains reached close_command_emitted -> execution_submitted -> reconciled. That closes the older "fresh runtime row proof" gap for emission and action-path existence.

It does not prove profit improvement. In the sampled window, both observed sidecar-originated closes finished net negative, both recommendations fired while the position was already losing, and there were zero observed profitable sidecar exits and zero observed peak_giveback policy_source exits. The only completed profitable close in the same window came from the normal bracket TP path, not from sidecar action.

Fee-aware shadow telemetry is alive and materially informative, but it remains explicitly non-authoritative. It highlights smaller protectable edges than the live peak-giveback gate, yet there is no current runtime proof that acting on those shadow arms would have improved realized live outcomes.

Minimal safe verdict: calibrate shadow / no action yet. Current evidence does not support enablement claims, recommendation-readiness claims, or action-readiness claims beyond the already-existing bounded experimental path.

## FACTS

- Evidence basis used in this audit:
  - config/aurora/domains.yaml
  - apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py
  - apps/reference/domains/execution_position/sidecar/position_policy_mediator.py
  - apps/reference/domains/execution_position/fsm.py
  - apps/reference/domains/execution_position/flows/manage/fsm_manage.py
  - apps/reference/domains/execution_position/flows/close/fsm_close.py
  - apps/reference/domains/execution_position/flows/close/close_executor.py
  - apps/reference/domains/execution_position/guardian/order_guardian.py
  - apps/reference/domains/execution_position/flows/manage/bracket_manager.py
  - apps/reference/domains/execution_position/flows/manage/bracket_health.py
  - apps/reference/dictionaries/verb_registry_v1.yaml
  - apps/reference/domains/execution_position/schemas/*.json listed in the prompt
  - logs/trade_lifecycle.jsonl
  - logs/order_log_v1.jsonl
  - logs/shadow_critical_event_journal_v1.jsonl
  - logs/domain_execution_position.log

- Requested roadmap artifact position_policy_sidecar_roadmap_v_1 (2).md was not found on disk. The closest relevant roadmap sources available on disk were PROFIT_ROADMAP_CONTROL_PLAN v2.md and docs/_archive/ROI_GATED_POSITION_LIFECYCLE_POLICY_ROADMAP_v1.md.

- Current sidecar config lives in config/aurora/domains.yaml, not in config/aurora/trading.yaml, config/aurora/strategies/aurora.yaml, config/aurora/instruments.yaml, or config/aurora/observability.yaml. Searches over those files found no sidecar-specific config surfaces.

- Current sidecar mode is enable in config/aurora/domains.yaml.

- Current bounded action scope in config is:
  - soft_close_symbol_current_net_only: true
  - partial_reduce: false
  - bracket_mutation: false
  - exact_targeting: false

- Current live peak-giveback config is:
  - enabled: true
  - edge_arm_usd: 25.0
  - giveback_trigger_pct: 50.0

- Current fee-aware shadow config is:
  - enabled: true
  - fee_source_priority: realized_lifecycle_fee -> order_log_fee -> configured_fee_model
  - candidate_fee_multiples: 1.0, 1.5, 2.0
  - configured_fee_model.enabled: false
  - optional_pct_notional_floor.enabled: true
  - optional_pct_notional_floor.candidate_pcts: 0.02, 0.05

- ExecPosFSM creates the sidecar only when position_policy_sidecar.mode != disable and injects a lifecycle_fee_getter sourced from accumulated symbol fees.

- PositionPolicySidecar runtime behavior is bounded_soft_close_policy and publishes to the internal bus plus trade_lifecycle.jsonl when logging is enabled.

- PositionPolicyMediator rejects anything outside the bounded contract. It suppresses requests unless all of the following hold:
  - policy_source starts with position_policy_sidecar
  - requested_action == SOFT_CLOSE
  - target_mode == symbol_current_net_only
  - requested_qty is empty or zero
  - allowed scope still admits symbol-current-net soft close
  - manage_flow exists and has active lifecycle
  - portfolio state is not UNKNOWN or FLAT
  - execution truth hardening does not suppress the close

- Close execution truth remains owned by execution_position. Sidecar requests go through CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST -> mediator -> CMD:CLOSE -> close flow / close executor -> guardian reconcile. Sidecar does not directly own execution truth.

- CloseExecutor currently emits position_policy close request state transitions for execution_noop and execution_submitted. I did not find a live ACTION_SKIPPED emitter in the current code path.

- ACTION_SKIPPED exists in registry and schema, but I found no code emitter and no runtime instances in the sampled logs.

- Verb registry status:
  - POSITION_POLICY_SIDECAR_MODE_ACTIVE: experimental
  - POSITION_POLICY_SIDECAR_EVALUATED: experimental
  - POSITION_POLICY_SIDECAR_SCORES: experimental
  - POSITION_POLICY_SIDECAR_SUPPRESSED: active
  - POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE: experimental, explicitly noted as observational only / non-authoritative
  - POSITION_POLICY_SIDECAR_RECOMMENDED: experimental
  - CMD POSITION_POLICY_SIDECAR_CLOSE_REQUEST: experimental
  - POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE: experimental

- Fresh runtime logs prove the sidecar is writing real rows. In the sampled window, trade_lifecycle.jsonl contained about 23.3k sidecar rows with this approximate event mix:
  - POSITION_POLICY_SIDECAR_SUPPRESSED: 23036
  - POSITION_POLICY_SIDECAR_SCORES: 54
  - POSITION_POLICY_SIDECAR_EVALUATED: 54
  - POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE: 39
  - POSITION_POLICY_SIDECAR_MODE_ACTIVE: 33
  - POSITION_POLICY_SIDECAR_RECOMMENDED: 2
  - POSITION_POLICY_SIDECAR_CLOSE_REQUESTED: 2
  - POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE: 6

- Top suppression reasons in the sampled window were:
  - no_manage_flow_for_symbol: 17565
  - manage_flow_has_no_active_lifecycle: 2698
  - features_snapshot_missing_or_stale: 2365
  - regime_snapshot_missing_or_stale: 318
  - profitability_guard_active: 151
  - post_fill_grace_active: 28
  - manage_flow_close_in_progress: 2

- This means the vast majority of sidecar rows are not active-lifecycle recommendations. They are suppression telemetry.

- The fee-aware shadow arm emits runtime events with these proven fields:
  - shadow_only: true
  - authority_applied: false
  - no_effect: true
  - trigger_event
  - transitions
  - candidate_state
  - position_snapshot

- In the sampled window, fee-aware shadow arm state events totaled 39 and split into:
  - ARMED-only transitions: 20
  - TRIGGERED-only transitions: 19

- Fee-aware candidate states observed at scale included:
  - shadow_fee_aware_unavailable_economics_missing
  - shadow_fee_aware_below_trigger
  - shadow_fee_aware_threshold_met
  - shadow_fee_aware_not_armed_below_edge

- Runtime fee sources observed in fee-aware candidate snapshots included:
  - realized_lifecycle_fee
  - order_log_fee
  - null

- Runtime missing-economics handling is explicit. Dominant null reasons included:
  - missing_unrealized_pnl_usdt
  - missing_observed_lifecycle_fee
  - missing_order_log_fee
  - configured_fee_model_disabled
  - missing_fee_source
  - missing_position_notional_usdt

- configured_fee_model was disabled in config and I found no runtime proof of configured_fee_model becoming the selected fee source.

- OrderGuardian emits EXECUTION_CLOSE_RECONCILED with business_close_reconciled: true and why: guardian:close_reconciled after cleanup/tidy when no tracked close-position or reduce-only orders remain.

- Completed close outcomes visible in order_log_v1.jsonl during the sampled window were three:
  - BNBUSDT, sidecar-originated explicit close, realized_pnl_net = -10.19342272
  - XRPUSDT, sidecar-originated explicit close, realized_pnl_net = -8.75665749
  - BTCUSDT, exchange TP close, realized_pnl_net = 8.862438

- The two observed sidecar recommendations were:
  - BNBUSDT at ts_ms 1778346608252, trigger_event REGIME_DETECTED, policy_source position_policy_sidecar, soft_close_pressure 0.3451122850869235, unrealized_pnl_usdt -9.3, peak_edge_usd 0.0, peak_giveback_state peak_giveback_not_armed_below_edge
  - XRPUSDT at ts_ms 1778347817840, trigger_event PORTFOLIO_STATE_UPDATED, policy_source position_policy_sidecar, soft_close_pressure 0.30747665120295575, unrealized_pnl_usdt -8.98, peak_edge_usd 6.21, giveback_pct 244.60547504025766, peak_giveback_state peak_giveback_not_armed_below_edge

- I did not observe any recommendation with policy_source position_policy_sidecar:peak_giveback in the sampled window.

- The two observed sidecar close request chains both completed:
  - close_command_emitted
  - execution_submitted
  - reconciled

- There were no sampled close request states with request_state suppressed and no sampled execution_noop close states for sidecar requests in this specific runtime window.

- The two observed sidecar close chains were both tied to recommendations whose position_snapshot.manage_state was BRACKETS_PENDING, not BRACKETS_PLACED or TRACKING.

- Open lifecycles still present at sample time included:
  - ETHUSDT: sidecar-observed MFE 10.66, MAE -5.01, no recommendation yet
  - BTCUSDT second open lifecycle: sidecar-observed MFE 2.26, MAE -4.98, no recommendation yet

- logs/shadow_telemetry/decision_ledger_v1.jsonl was missing in the workspace.

## INFERENCES

- Post-entry lifecycle is a credible profit blocker in the current sample because at least one completed trade, XRPUSDT, achieved a fee-covering favorable edge and still finished as a net loss after full giveback.

- Current live peak-giveback policy is likely too coarse for the sampled small-edge trades. The live arm threshold is 25.0 USD, while sidecar-observed MFE on the completed lifecycles was:
  - BNBUSDT: 1.07
  - XRPUSDT: 7.75
  - BTCUSDT: 15.17
  None of these reaches 25.0, so the live peak-giveback path never had a chance to arm in this sample.

- Fee-aware shadow is materially more sensitive than the live peak-giveback gate. For example:
  - XRPUSDT fee-aware required_edge_usd was observed around 0.7197, 1.0796, 1.4394, or 1.7993 depending on fee multiple and optional floor.
  - BTCUSDT fee-aware required_edge_usd was observed around 0.8060, 1.2090, 1.6120, or 2.0150.
  This means the shadow surface can detect economically relevant small edges that the live peak-giveback gate ignores.

- That does not make fee-aware shadow action-ready. It only proves that the shadow surface is measuring smaller thresholds, not that using those thresholds would improve realized net PnL after slippage and sequencing.

- The two observed sidecar recommendations are late from a profit-protection perspective. Both fired when unrealized PnL was already negative.

- BNBUSDT looks like a fee-insufficient micro-edge rather than a missed large profit-defense opportunity. Sidecar-observed MFE was only 1.07 while realized total fees were 2.16042272. Even a theoretically perfect exit around observed MFE would likely still fail to clear round-trip fees.

- XRPUSDT is the strongest sampled giveback example. Sidecar-observed MFE was 7.75 while realized total fees were 2.16175749. That means the trade appears to have reached a fee-covering edge, yet no authoritative protection converted that edge into a positive realized outcome.

- BTCUSDT shows the opposite archetype: standard bracket TP monetized the trade without sidecar recommendation, even though fee-aware shadow armed and triggered during the hold. This is direct evidence that sidecar benefit is not yet established; the normal bracket path can still produce the only sampled winner.

- The dominance of no_manage_flow_for_symbol, no_active_lifecycle, and stale-input suppressions means raw sidecar row volume should not be mistaken for active policy coverage. Most telemetry in the current log surface is non-actionable suppression noise.

- The fact that both observed sidecar-originated closes happened while manage_state was BRACKETS_PENDING suggests the sidecar can act before the lifecycle settles into a cleaner protective state. That may be intended, but it raises a sequencing question for post-entry evaluation quality.

- Fresh runtime logs now resolve the older profit-roadmap statement that sidecar runtime row emission still needed proof on fresh logs. That specific observability gap is closed. The profit-driving value gap is not closed.

- The current runtime already crosses the boundary from recommendation telemetry into live bounded action because mode is enable and the action path reconciled twice. Therefore the system must not be described as recommendation-only or shadow-only in its current runtime state.

## ASSUMPTIONS

- MFE and MAE values in this report are derived from sidecar position_snapshot.unrealized_pnl_usdt over time, not from a separate authoritative execution lifecycle ledger.

- Max giveback percentages in this report are derived from sidecar peak_giveback_snapshot values. They are observational policy telemetry, not an execution-truth ledger.

- Entry-to-close mapping for sidecar-originated closes uses policy_context.fill_correlation plus order_log POSITION_CLOSED rows. That mapping is strongly supported by current logs, but it is still a reconstruction.

- position_disappearance rows are treated as supporting evidence, not the primary source of realized economics, because order_log POSITION_CLOSED provides the stronger net PnL record.

- Counts in this report reflect a live log surface and can drift if the runtime continues appending after this audit.

## UNKNOWNS

- No authoritative lifecycle ledger currently proves per-trade MFE, MAE, peak giveback, and decision timestamp from an execution-truth surface.

- No sampled runtime evidence proves that fee-aware shadow thresholds would improve realized outcomes if promoted from shadow telemetry to live authority.

- No sampled runtime evidence proves that the current score-based recommendation threshold has positive expectancy.

- No sampled runtime evidence proves the peak_giveback action path itself, because I observed zero position_policy_sidecar:peak_giveback recommendations or closes.

- No sampled runtime evidence proves ACTION_SKIPPED semantics in code or logs, despite the presence of schema and registry surfaces.

- The requested roadmap file position_policy_sidecar_roadmap_v_1 (2).md was missing, so no claims from that artifact could be verified.

- logs/shadow_telemetry/decision_ledger_v1.jsonl was missing, so there is no decision-ledger join for shadow recommendation usefulness in this workspace.

- The exact reason why BNBUSDT and XRPUSDT also show POSITION_DISAPPEARANCE_ATTRIBUTED as unknown_disappearance after sidecar-originated POSITION_CLOSED remains unresolved from the sampled artifacts. That may indicate a remaining attribution seam rather than an execution failure, but it is not proven here.

## Sidecar capability map

| Surface | Current state | Runtime proof in sample | Authority status |
| --- | --- | --- | --- |
| Sidecar bootstrap | Present, mode enable | MODE_ACTIVE rows present | Non-truth collaborator under execution_position |
| Score evaluation | Present | 54 SCORES and 54 EVALUATED rows | Advisory unless action path invoked |
| Score recommendation | Present | 2 RECOMMENDED rows | Advisory event, but currently followed by live close requests in enable mode |
| Bounded close request bridge | Present | 2 close chains reached reconciled | Live bounded action path |
| Peak-giveback live policy | Configured | No sampled peak_giveback recommendation or close | Action-capable in code, unproven in runtime sample |
| Fee-aware shadow arm | Present | 39 fee-aware shadow arm state rows | Explicitly non-authoritative |
| ACTION_SKIPPED | Registry + schema only | No emitter found, no runtime rows | Unproven / likely documentation drift surface |
| Bracket placement | Present | Deferred stored / deferred placed rows present | Execution truth owned by execution_position |
| Guardian close reconcile | Present | EXECUTION_CLOSE_RECONCILED and reconciled close request state rows present | Execution truth owned by execution_position |

## Fee-aware shadow evidence

- Proven emitted runtime fields on fee-aware shadow arm state rows include:
  - fee_multiple
  - estimated_fee_usd
  - fee_source
  - fee_source_confidence
  - optional_pct_floor
  - required_edge_usd
  - current_edge_usd
  - is_armed
  - first_arm_ts_ms
  - peak_edge_usd
  - giveback_pct
  - would_trigger_under_current_giveback_trigger_pct
  - would_trigger
  - state
  - null_reasons

- Proven authority boundary on runtime fee-aware shadow rows:
  - shadow_only = true
  - authority_applied = false
  - no_effect = true

- Runtime fee-source behavior is real, not just contractual:
  - During active lifecycles, fee-aware shadow commonly used realized_lifecycle_fee with confidence observed_symbol_lifecycle_fee.
  - After lifecycle completion or when unrealized economics became unavailable, candidate snapshots were observed falling back to order_log_fee with confidence observed_order_fill_fee.
  - When neither was available and configured_fee_model stayed disabled, candidate snapshots emitted fee_source = null and fee_source_confidence = unavailable with explicit null reasons.

- The shadow surface is already sensitive to small edges. Observed required_edge_usd values were approximately:
  - XRPUSDT: 0.7197, 1.0796, 1.4394, or 1.7993 depending on fee multiple and optional floor.
  - BNBUSDT: 0.7191, 1.0786, 1.4381, or 1.7977 depending on fee multiple and optional floor.
  - BTCUSDT: 0.8060, 1.2090, 1.6120, or 2.0150 depending on fee multiple and optional floor.

- That contrasts sharply with the live peak-giveback arm threshold of 25.0 USD.

- The dominant fee-aware null case in the full telemetry surface is missing_unrealized_pnl_usdt, which produces shadow_fee_aware_unavailable_economics_missing. This means fee-aware telemetry continues to emit explanatory candidate rows even when the position is already flat or economics are absent.

## Lifecycle economics table

Note: MFE, MAE, and max giveback in this table are sidecar-observed policy telemetry, not authoritative execution-truth ledger values.

| Symbol | Close owner/path | Hold sec | Entry px | Close px | Gross PnL | Fees | Net PnL | MFE | MAE | Max giveback pct | Fee floor at peak? | Sidecar note |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| BNBUSDT | Sidecar bounded close | 532.108 | 648.98 | 650.43 | -8.0330 | 2.1604 | -10.1934 | 1.07 | -9.67 | n/a | No. MFE < realized total fees. | Recommendation fired at unrealized -9.3; peak_giveback not armed; fee-aware shadow armed and triggered once each. |
| XRPUSDT | Sidecar bounded close | 3881.216 | 1.4187 | 1.4213 | -6.5949 | 2.1618 | -8.7567 | 7.75 | -8.98 | 244.6055 | Yes. MFE > realized total fees. | Recommendation fired at unrealized -8.98 after prior positive edge; fee-aware shadow armed and triggered six times each. |
| BTCUSDT | Exchange TP bracket | 6742.605 | 80601.6 | 80827.3 | 11.2850 | 2.4226 | 8.8624 | 15.17 | -1.08 | 363.4146 | Yes. | No sidecar recommendation; bracket path captured the winner while fee-aware shadow only observed. |

## Giveback archetypes

- Fee-insufficient micro-edge:
  - BNBUSDT briefly moved favorable, but the observed edge was too small to cover realized round-trip fees.
  - Sidecar still recommended a bounded close only after the position was already materially negative.
  - This is a bad post-entry outcome, but it is not strong proof that a finer protector would have converted the trade into a good trade.

- Protectable edge not protected:
  - XRPUSDT reached a sidecar-observed MFE of 7.75 while realized total fees were only 2.1618.
  - Fee-aware shadow armed and triggered repeatedly, yet no authoritative protection converted the edge into a positive realized outcome.
  - This is the clearest sampled example of earned edge being given back into a low-quality close.

- Bracket winner without sidecar help:
  - BTCUSDT closed via TP with positive net PnL.
  - Sidecar produced no recommendation despite fee-aware shadow activity.
  - This shows the ordinary bracket lifecycle can already capture profitable exits, and current sidecar action is not required for all profitable closures.

- Open but unresolved small-edge lifecycles:
  - ETHUSDT and a second BTCUSDT lifecycle both showed sidecar-observed positive edge without completed close evidence yet.
  - They are informative for collection, but not suitable for outcome claims yet.

## Action-readiness verdict

| Verdict option | Supported by current evidence? | Audit conclusion |
| --- | --- | --- |
| Maintain shadow | Partially | The evidence bar supports shadow semantics, but the current runtime is already enable, not shadow. |
| Calibrate shadow | Yes | Fee-aware shadow is producing useful small-edge evidence and should be treated as an analysis surface, not proof of live benefit. |
| Enable recommendation | No | The runtime already acted twice, and both observed sidecar-driven closes ended net negative. |
| Action readiness review | No | No profitable sidecar close, no peak-giveback close, no scale, and no counterfactual ledger. |
| No action yet | Yes | This is the minimal safe verdict from the current sample. |

## What remains unproven

- Whether a lower live profit-protection threshold would have improved realized net outcomes after slippage.

- Whether fee-aware shadow candidates are early enough and selective enough to avoid over-exiting normal winners.

- Whether the score-based soft_close_pressure threshold is economically sound.

- Whether sidecar should be allowed to act while the manage lifecycle still reports BRACKETS_PENDING.

- Whether the unknown_disappearance attribution on BNBUSDT and XRPUSDT is harmless bookkeeping lag or a remaining close-attribution gap.

- Whether the current stale-input rate materially distorts sidecar timing and suppressions during active holds.

## Next runtime collection requirements

- Add an authoritative lifecycle ledger keyed by entry rid or lifecycle_id with:
  - entry_ts_ms
  - exit_ts_ms
  - entry_price
  - exit_price
  - gross_pnl
  - total_fees
  - net_pnl
  - close_reason
  - close_actor

- Persist authoritative per-lifecycle path statistics in execution truth, not only in sidecar telemetry:
  - MFE
  - MAE
  - peak_giveback_usd
  - peak_giveback_pct
  - first_positive_pnl_ts_ms

- Join sidecar recommendations to realized outcomes with a durable ledger row containing:
  - recommendation_ts_ms
  - request_id
  - recommendation_reason_codes
  - recommendation_unrealized_pnl_usdt
  - eventual_close_ts_ms
  - eventual_close_reason
  - realized_pnl_net_from_recommendation_lifecycle

- Add a fee-aware shadow counterfactual ledger per candidate containing:
  - first_arm_ts_ms
  - first_trigger_ts_ms
  - fee_source
  - required_edge_usd
  - actual_close_ts_ms
  - actual_realized_pnl_net
  - counterfactual_exit_price_reference

- Carry close_reason and authoritative close actor into position disappearance attribution so that unknown_disappearance is not the terminal explanation after already-recorded explicit closes.

- Emit a clean bracket status field at recommendation time:
  - BRACKETS_PENDING
  - BRACKETS_PLACED
  - PROTECTION_MISSING
  - TRACKING
  This currently appears indirectly through position_snapshot.manage_state, but it should be query-friendly and joined to realized outcomes.

- Decide whether ACTION_SKIPPED is a real runtime surface. If yes, emit it. If no, retire the schema and registry entry to remove ambiguity.

- Restore or provide the missing shadow_telemetry/decision_ledger_v1.jsonl surface if recommendation usefulness is expected to be evaluated as a shadow decision product.

- Preserve fresh raw samples whenever sidecar-originated close_request_state reaches reconciled so future audits can compare:
  - recommendation context
  - fee-aware candidate state at recommendation time
  - realized net outcome
  - whether the trade had previously cleared round-trip fees
