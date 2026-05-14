# R7S-B Extended Fee-Aware Observation Report

## Executive Summary

Verdict: NOT_PROVEN.

Frozen evidence bundle: frozen/r7s_b_extended_fee_aware_observation_20260513T233631Z

The extended runtime window confirms that fee-aware telemetry is present, schema-stable, fully sink-redundant, and safety-clean. However, the candidate-quality result is still not action-ready: fee_x1.0 / 1.5 / 2.0 all behaved identically on this bundle, reduced triggered lifecycles by only 1 versus raw percent, did not reduce harmed proxies at all, and still produced non-positive trigger-net proxies on every closed triggered lifecycle after subtracting actual realized lifecycle fees.

## FACTS

- Runtime window on emitted fee-aware events: 2026-05-11T15:22:06.497000Z to 2026-05-13T13:51:29.489000Z
- Emitted fee-aware event rows: 108 in trade_lifecycle and 108 in shadow_critical_event_journal_v1.jsonl
- Sink consistency: matched=108, trade_only=0, journal_only=0
- Schema stability: trade top-level keysets=1, trade candidate keysets=1, journal top-level keysets=1, journal payload keysets=1
- Missing required fields on fee-aware events: trade={}, candidate_state={}, journal={}, payload={}
- Evaluable cohort used for candidate metrics: 660 non-flat POSITION_POLICY_SIDECAR_EVALUATED rows across 24 active lifecycles, with 20 closed lifecycles carrying terminal outcome truth
- Excluded denominator noise: 250866 suppressed rows, dominated by no_active_lifecycle=216707, peak_giveback_not_ready=218592, and stale-input suppressions
- Fee source coverage on evaluable fee-aware rows: 24/24 active lifecycles and 660/660 candidate rows used realized_lifecycle_fee with confidence observed_symbol_lifecycle_fee
- Fee-aware optional floor behavior: floor 0.02 versus 0.05 changed required_edge_usd but caused zero arm/trigger/state divergence on the 660 evaluable rows; fee_x1.0 / 1.5 / 2.0 can therefore be compared as behaviorally stable bundle-level candidates

## Candidate Quality

| Candidate | Triggered Lifecycles | Triggered Closed | Helped Proxies | Harmed Proxies | Median Trigger Net Proxy |
| --- | --- | --- | --- | --- | --- |
| raw_pct_0_02 | 21 | 17 | 6 | 11 | -4.359728 |
| raw_pct_0_05 | 21 | 17 | 6 | 11 | -4.359728 |
| raw_pct_0_07 | 21 | 17 | 6 | 11 | -4.359728 |
| fee_x1_0 | 20 | 16 | 5 | 11 | -4.304812 |
| fee_x1_5 | 20 | 16 | 5 | 11 | -4.304812 |
| fee_x2_0 | 20 | 16 | 5 | 11 | -4.304812 |

## INFERENCES

- Fee-aware observability is operationally healthy: the earlier sink gap is gone, schemas are stable, and the event surface remains shadow-only.
- Fee-aware candidate quality did not separate materially from raw percent on this bundle. Every fee_x candidate kept the harmed proxy count at 11 while reducing triggered lifecycles by only 1 and helped proxies by 1.
- fee_x1.0 remains too permissive after full realized lifecycle fees. The stricter fee_x1.5 and fee_x2.0 did not create a cleaner behavioral frontier in this window because their arm/trigger behavior never diverged from fee_x1.0.
- The current trigger surface mostly catches late giveback after the edge has already crossed below a net-positive proxy. That is why positive_trigger_net_proxy_count remained 0 for all six compared candidates.

## ASSUMPTIONS

- Proxy net at trigger is computed as current_edge_usd minus authoritative realized lifecycle fees from execution_lifecycle_stats_v1.jsonl.
- Helped/harmed labels are proxy classifications only. They do not claim filled exit truth at the trigger timestamp.

## UNKNOWNS

- Whether a true recommendation-only replay with execution modeling would materially change the proxy balance for any candidate.
- Whether a longer observation window will produce fee_x behavior that diverges from raw percent or from fee_x1.0.
- Whether candidate timing can be improved enough that trigger_net_proxy becomes positive on a non-trivial share of closed lifecycles.

## Minimal Safe Verdict

NOT_PROVEN. Keep the surface observational only. Do not recommend recommendation-only replay from this bundle.
