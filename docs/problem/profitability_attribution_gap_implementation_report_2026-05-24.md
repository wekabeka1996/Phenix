# Profitability Attribution Gap Implementation Report (2026-05-24)

## Scope

This document records the first implementation slice of the profitability-recovery workstream.

Bounded goal:
- repair the forensic export so that missing local intent linkage fails closed instead of silently producing blank strategy attribution fields in the reconstructed episode dataset.

Out of scope for this slice:
- inferring missing strategy ownership without local proof,
- recalibrating scoring,
- changing trading runtime behavior,
- rewriting historical attribution with speculative joins.

## Proven Facts

1. The active export path for Binance testnet history is [scripts/forensics/binance_testnet_window_audit.py](scripts/forensics/binance_testnet_window_audit.py).

2. Before this change, reconstructed episodes could be emitted with blank `entry_rid`, `strategy_id`, and `regime_hint` when no local `rid -> TRADE_INTENT_PROPOSED` linkage existed.

3. A focused check on the large unattributed BNBUSDT short episode showed:
- symbol: BNBUSDT
- direction: SHORT
- entry_time_utc: 2026-05-14T16:30:05.191000+00:00
- entry_order_id: 1365103081
- entry_client_order_id: ENTRY-d9a5ef89614d
- local export evidence: no matching `ORDER_PLACED` by `order_id` or `client_order_id` in the exported local order log window
- local export evidence: no nearby `EVT:TRADE_INTENT_PROPOSED` in the exported local shadow window for the same symbol and side

4. Therefore, for that episode, the current export artifacts do not prove a local strategy attribution. The previous blank fields were an evidence gap, not a proven strategy assignment.

5. The exporter was updated to emit explicit `local_attribution_status` values for each episode:
- `ATTRIBUTED:LOCAL_INTENT`
- `UNATTRIBUTED:NO_LOCAL_RID`
- `UNATTRIBUTED:RID_NOT_IN_LOCAL_SHADOW`

6. The validation/report output was updated to surface unattributed episode counts and unattributed closed-episode net PnL instead of hiding the gap behind empty strings.

7. The exporter was rerun for 2026-05-13 .. 2026-05-24 after the patch. The regenerated outputs confirmed:
- `episodes.csv` now contains `local_attribution_status`
- the previously blank BNBUSDT rows now carry `UNATTRIBUTED:NO_LOCAL_RID`
- the markdown report now includes unattributed episode counts and net PnL in validation
- the run completed without runtime failure

8. The rerun produced the following explicit validation values:
- unattributed_episode_count: 440
- unattributed_closed_episode_count: 131
- unattributed_closed_episode_net_pnl: -597.93

## Inferences

1. The immediate blocker for honest strategy-level blame is missing local evidence, not only weak downstream episode join logic.

2. Any profitability conclusion that allocates the unattributed loss bucket to a concrete strategy without new upstream evidence would be speculative.

3. The unattributed bucket is large enough to materially distort scoring, regime, and calibrator conclusions if treated as if it were fully attributed.

## Unproven / Open Questions

1. Why the local evidence is missing for those exchange episodes remains unproven.

2. The current data does not yet prove whether the gap came from:
- missing or delayed local logging,
- retention/window mismatch,
- an execution path that bypassed the current shadow/order logs,
- manual or external exchange activity,
- another runtime outside the captured local evidence set.

3. The current data also does not prove which strategy owns any unattributed episode, even if the symbol is assigned to multiple strategies in [config/aurora/strategies.yaml](config/aurora/strategies.yaml).

## Code Change

Implemented in [scripts/forensics/binance_testnet_window_audit.py](scripts/forensics/binance_testnet_window_audit.py):
- added `_resolve_local_intent_attribution(...)`
- emitted explicit per-episode attribution status
- propagated unattributed counts/net PnL into validation summary
- rendered the unattributed gap explicitly in the markdown report

## Runtime Truth Guardrail

Historical runtime truth for the investigated loss window must remain separate from current live-effective SSOT.

In particular, conclusions from this report must not silently assume that the historical runtime matched the current settings in [config/aurora/domains.yaml](config/aurora/domains.yaml).

## Next Steps

1. Trace the unattributed bucket upstream to identify which runtime path failed to leave local evidence.

2. Split unattributed episodes by symbol, date, and order-client-id patterns to isolate whether the gap is systemic or path-specific.

3. Continue regime/scoring/NRR/calibration analysis only on proven-attribution slices, while reporting unattributed losses separately.