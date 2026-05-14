# R7U_FEE_AWARE_SHADOW_COLLECTION_REPORT

## Executive Summary

Verdict: COLLECTION_STARTED_WITH_OBSERVABILITY_GAPS.

The new fee-aware shadow arm surface is live in runtime and produced first evidence without crossing authority boundaries. Between 2026-05-09T22:26:14.279Z and 2026-05-10T16:03:51.754Z, 48 fee-aware shadow events were emitted across 4 lifecycles and 4 symbols. Safety held cleanly: authority_applied never became true, no_effect never became false, shadow_only never became false, and no fee-aware event was observed as a direct close-command source. The collection did not start clean because 48/48 events were present only in logs/trade_lifecycle.jsonl and 0/48 reached logs/shadow_critical_event_journal_v1.jsonl.

## FACTS

- Exact requested context files were not present on disk: R7T_VALIDATION_RECHECK_REPORT.md and R7T_FEE_AWARE_FORWARD_COLLECTION_PLAN.md.
- Adjacent validated evidence files were present and used as contextual support only: POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md, SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md, POST_RUNTIME_A1_A6_VALIDATION_REPORT.md.
- 48 fee-aware shadow arm events were found in logs/trade_lifecycle.jsonl.
- First event timestamp: 2026-05-09T22:26:14.279Z.
- Last event timestamp: 2026-05-10T16:03:51.754Z.
- Event transition counts: 24 ARMED, 24 TRIGGERED.
- Symbols observed: BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT.
- Runtime identities observed: 4 unique rid values and 4 unique lifecycle_id values.
- Missing economics count on emitted event rows: 0.
- Malformed payload count on emitted event rows: 0.
- Shadow critical journal copies: 0.
- domain_execution_position text hits for the event string: 0.
- Exact duplicate event signatures: 0.
- Candidate sequence anomalies: 0.
- All 48 emitted events were joinable to closed lifecycles once the close-request chain was bridged.
- Broader denominator scan across sidecar fee-aware candidate rows in the runtime window found 512136 candidate snapshots across 85356 sidecar rows.
- Broader denominator fee_source distribution was: realized_lifecycle_fee 119172, order_log_fee 73524, null 319440.
- Broader denominator dominant state was shadow_fee_aware_unavailable_economics_missing with 393108 candidate rows.
- Broader denominator dominant missing reason was missing_unrealized_pnl_usdt with 393108 candidate rows.

## Event Presence Audit

| Metric | Value |
| --- | --- |
| First timestamp | 2026-05-09T22:26:14.279Z |
| Last timestamp | 2026-05-10T16:03:51.754Z |
| Total emitted events | 48 |
| Symbols observed | 4 |
| Lifecycle ids observed | 4 |
| Transition types observed | ARMED=24, TRIGGERED=24 |
| Arm count | 24 |
| Trigger count | 24 |
| Missing economics count | 0 |
| Malformed payload count | 0 |

Per-runtime identity distribution was stable: each of the 4 observed rid values carried 12 fee-aware events, with no exact duplicates and no sequence anomaly on candidate_key + transition ordering.

## Sink Consistency Audit

| Classification | Count | Evidence |
| --- | ---: | --- |
| BOTH_SINKS_OK | 0 | No event copy found in shadow_critical_event_journal_v1.jsonl |
| TRADE_LIFECYCLE_ONLY | 48 | All emitted rows exist in trade_lifecycle.jsonl only |
| CRITICAL_JOURNAL_ONLY | 0 | No journal-only copy found |
| MISSING_FROM_EXPECTED_SINK | 0 | Not observed as a standalone classification in this pass |
| MALFORMED_OR_UNJOINABLE | 0 | Event payloads were parseable and joinable |

Observed sink fact: the event surface is currently visible only in trade_lifecycle.jsonl. No copies were found in shadow_critical_event_journal_v1.jsonl, and no textual copies were found in domain_execution_position.log*.

## Lifecycle Join And Raw-vs-Fee Comparison

| Symbol | Lifecycle ID | Raw arm | Fee arm | Raw trigger | Fee trigger | Live sidecar decision | Terminal close | Realized net | Premature-trigger avoidance | Missed protection |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| BNBUSDT | 30000f91-7dd6-4fd3-8b02-7ffe963fa482 | 2026-05-10T02:18:07.763Z | 2026-05-10T02:18:07.763Z | 2026-05-10T02:21:12.605Z | 2026-05-10T02:21:12.605Z | Yes, position_policy_sidecar at 2026-05-10T04:30:04.009Z | CLOSE at 2026-05-10T04:30:06.054Z | -10.69017132 | UNPROVEN | OBSERVED_SHADOW_SIGNAL_NO_PROTECTION |
| BTCUSDT | cc7a9e64-0f4b-47fc-a9b7-6c46b11eb047 | 2026-05-09T22:26:14.280Z | 2026-05-09T22:26:14.280Z | 2026-05-09T22:26:20.114Z | 2026-05-09T22:26:20.114Z | Yes, position_policy_sidecar at 2026-05-10T14:05:24.009Z | CLOSE at 2026-05-10T14:05:32.093Z | -9.761633 | UNPROVEN | OBSERVED_SHADOW_SIGNAL_NO_PROTECTION |
| ETHUSDT | 26762b1a-412b-4383-a705-5594d6373f0a | 2026-05-10T15:54:59.886Z | 2026-05-10T15:55:29.547Z | 2026-05-10T15:55:05.718Z | 2026-05-10T16:03:51.754Z | Yes, position_policy_sidecar at 2026-05-10T16:25:01.271Z | CLOSE at 2026-05-10T16:25:03.372Z | -16.51806786 | POSSIBLE_NOT_PROVEN | OBSERVED_SHADOW_SIGNAL_NO_PROTECTION |
| XRPUSDT | a38c5227-7285-450b-bd9d-cb9ba6022c5a | 2026-05-10T09:06:48.259Z | 2026-05-10T09:06:48.259Z | 2026-05-10T09:07:11.659Z | 2026-05-10T09:07:11.659Z | No live sidecar decision in joined runtime chain | SL at 2026-05-10T11:22:28.476Z | -37.48071128 | UNPROVEN | OBSERVED_SHADOW_SIGNAL_NO_PROTECTION |

Additional lifecycle facts:

- BNBUSDT peak_pnl_before_trigger_usdt was 2.86 and pnl_at_fee_trigger_usdt was 1.32.
- BTCUSDT peak_pnl_before_trigger_usdt was 9.84 and pnl_at_fee_trigger_usdt was 0.37.
- ETHUSDT peak_pnl_before_trigger_usdt was 12.69 and pnl_at_fee_trigger_usdt was 6.17.
- XRPUSDT peak_pnl_before_trigger_usdt was 14.39 and pnl_at_fee_trigger_usdt was 0.13.
- ETHUSDT was the only lifecycle where raw and fee-aware timing separated materially in this sample. Raw armed about 29.661 seconds earlier, and raw triggered about 8 minutes 46.036 seconds earlier than fee-aware.
- BNBUSDT, BTCUSDT, and XRPUSDT showed identical raw and fee-aware arm/trigger timestamps in this sample.

## Denominator And Missing Economics Audit

Important: the denominator classifications below are not mutually exclusive. They describe the broader fee-aware candidate surface inside sidecar evaluation rows, not only emitted fee-aware arm-state events.

| Denominator metric | Count |
| --- | ---: |
| Sidecar rows in runtime window | 85356 |
| Fee-aware candidate rows in runtime window | 512136 |
| ECONOMICS_READY | 118866 |
| REALIZED_FEE_AVAILABLE | 119172 |
| ESTIMATED_FEE_ONLY | 73524 |
| MISSING_FEE_SOURCE | 319440 |
| MISSING_UNREALIZED_PNL | 393108 |
| DENOMINATOR_BIAS_RISK | 393270 |
| startup-window missing economics | 31350 |

Fee source distribution:

| Fee source | Count |
| --- | ---: |
| realized_lifecycle_fee | 119172 |
| order_log_fee | 73524 |
| null | 319440 |

State distribution:

| Candidate state | Count |
| --- | ---: |
| shadow_fee_aware_below_trigger | 16254 |
| shadow_fee_aware_not_armed_below_edge | 3586 |
| shadow_fee_aware_threshold_met | 99188 |
| shadow_fee_aware_unavailable_economics_missing | 393108 |

Null reason facts:

- Dominant missing reason value was missing_unrealized_pnl_usdt.
- Dominant field-level null pairs were giveback_pct=missing_unrealized_pnl_usdt and would_trigger_under_current_giveback_trigger_pct=missing_unrealized_pnl_usdt.
- Emitted fee-aware arm-state rows did not themselves carry missing-economics payloads; the missing-economics burden sits on the broader evaluation denominator surface.

## Safety Verdict

Safety verdict: SAFETY_OK.

Verified safety facts:

- authority_applied=true count: 0.
- no_effect=false count: 0.
- shadow_only=false count: 0.
- fee-aware close-command source count: 0.
- order_log fee-aware text hits: 0.
- exact duplicate event count: 0.
- event storm detected: false.
- schema drift detected on emitted fee-aware rows: false.

## INFERENCES

- The new fee-aware shadow surface is active in runtime and behaves as an observational-only surface, not a live authority path.
- The primary observability defect in this pass is sink incompleteness, not authority leakage: the event exists in trade_lifecycle but does not fan out into shadow_critical_event_journal.
- Event cadence is consistent with edge-based emission rather than per-tick spam. The observed shape, 4 identities x 12 events with zero exact duplicates and zero sequence anomalies, fits the expected 6 candidate keys x 2 transitions model.
- The current sample does not support any claim that fee-aware logic would improve realized live outcomes if promoted. All four joined lifecycles ended with non-positive realized net outcomes, and 3 of the 4 lifecycles later had live sidecar recommendations that still resolved negatively.
- ETHUSDT is the only observed case where fee-aware may have delayed a raw trigger, but the terminal outcome was still negative. That makes premature-trigger avoidance possible, not proven.

## ASSUMPTIONS

- rid plus same-trace sidecar context is the valid runtime bridge from fee-aware event rows to lifecycle truth because lifecycle_id is not serialized on the emitted event row itself.
- order_log lifecycle rows and sidecar close-request chains are both acceptable runtime truth surfaces for terminal outcome reconstruction in this audit.
- The absence of the exact named R7T report/plan files does not invalidate the runtime collection pass because the requested runtime logs and adjacent validated reports were sufficient to answer the operational questions in scope.

## UNKNOWNS

- Whether the missing shadow_critical_event_journal fanout is an intentional design choice or a localized sink defect.
- Whether fee-aware thresholds improve realized outcomes after slippage and sequencing if ever promoted beyond shadow mode.
- Whether denominator bias should be normalized before comparing candidate rates across startup, flat-position, and active-lifecycle windows.
- Whether a longer forward-collection window will reveal positive net outcomes on lifecycles where fee-aware armed or triggered early.

## Contradictions / Evidence Gaps

- The exact files R7T_VALIDATION_RECHECK_REPORT.md and R7T_FEE_AWARE_FORWARD_COLLECTION_PLAN.md were absent from disk in this workspace state.
- trade_lifecycle.jsonl contained 5 malformed non-event lines during the broad parse, although none intersected the 48 emitted fee-aware event rows.
- shadow_critical_event_journal_v1.jsonl contained no copies of the new fee-aware shadow arm event during the observed runtime window.

## Operational Risk

Observability Gap.

The fee-aware surface is proving runtime existence and safety, but it is not yet fully sink-complete. This weakens collection redundancy and makes the current forward-collection phase dependent on trade_lifecycle.jsonl as the authoritative evidence source for the event itself.

## Files / Areas Touched

- R7U_FEE_AWARE_SHADOW_COLLECTION_REPORT.md
- r7u_fee_aware_event_inventory.json
- r7u_fee_aware_sink_consistency_matrix.json
- r7u_fee_aware_lifecycle_join_matrix.json
- r7u_fee_aware_safety_audit.json
- scratch/r7u_fee_aware_collection_analysis.py

## Validation Performed

- Executed: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe scratch/r7u_fee_aware_collection_analysis.py
- Verified generated artifacts and re-ran after repairing lifecycle close-chain joins.
- Verified final summary:
  - verdict = COLLECTION_STARTED_WITH_OBSERVABILITY_GAPS
  - safety_verdict = SAFETY_OK
  - total events = 48
  - sink classification = TRADE_LIFECYCLE_ONLY for all 48 rows
  - join classification = JOINED_TO_CLOSED_LIFECYCLE for all 48 rows

## Residual Risk

- Forward collection can continue safely, but journal-level redundancy is currently absent for this event surface.
- Broader denominator statistics are heavily influenced by flat/no-economics windows, so any rate comparison against emitted event rows must be normalized before it is used for threshold claims.

## What Remains Unproven

- Profitability improvement from fee-aware promotion.
- Whether the ETH timing separation is beneficial in a longer holdout window.
- Whether the journal fanout gap is contractual drift or intentional exclusion.

## Minimal Safe Verdict

Forward collection may continue, but only under the verdict COLLECTION_STARTED_WITH_OBSERVABILITY_GAPS.

The next smallest safe step is:

1. Localize why POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE never reaches shadow_critical_event_journal_v1.jsonl.
2. If journal fanout is contract-required, patch only the sink path without changing fee-aware authority, sidecar thresholds, or policy logic.
3. Continue passive collection from trade_lifecycle.jsonl while that sink gap is being localized.

## AGENT_REPORT_V1

```text
AGENT_REPORT_V1

task: AURORA_R7U_FEE_AWARE_SHADOW_COLLECTION_MONITORING
verdict: COLLECTION_STARTED_WITH_OBSERVABILITY_GAPS
runtime_authority_changed: false
execution_behavior_changed: false
config_policy_changed: false
runtime_window:
  start: 2026-05-09T22:26:14.279000Z
  end: 2026-05-10T16:03:51.754000Z
event_counts:
  total: 48
  armed: 24
  triggered: 24
  missing_economics: 0
symbols:
  - BNBUSDT
  - BTCUSDT
  - ETHUSDT
  - XRPUSDT
artifacts:
  - R7U_FEE_AWARE_SHADOW_COLLECTION_REPORT.md
  - r7u_fee_aware_event_inventory.json
  - r7u_fee_aware_sink_consistency_matrix.json
  - r7u_fee_aware_lifecycle_join_matrix.json
  - r7u_fee_aware_safety_audit.json
proven:
  - The fee-aware shadow arm surface emitted 48 runtime events in trade_lifecycle.jsonl.
  - All emitted rows remained shadow_only=true, authority_applied=false, and no_effect=true.
  - No fee-aware event was observed as a direct close-command source.
  - All 48 emitted rows were joinable to closed lifecycles.
  - No copies of the event reached shadow_critical_event_journal_v1.jsonl in the observed runtime window.
unproven:
  - Profitability improvement from fee-aware promotion.
  - Whether the missing journal fanout is by design or defect.
  - Whether ETH's delayed fee-aware trigger is beneficial in a larger sample.
safety:
  authority_leak_detected: false
  event_storm_detected: false
  schema_drift_detected: false
next_step:
  - Localize why POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE never reaches shadow_critical_event_journal_v1.jsonl while continuing passive collection from trade_lifecycle.jsonl.
```
