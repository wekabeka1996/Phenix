# R7F Peak-Giveback Verified Runtime Report

## Problem Framing
This package validates the fresh post-restart runtime slice for the peak-giveback Sidecar path. The question is not whether the source code can emit R7C observability, but whether the verified runtime actually does so, whether the peak-giveback state is reconstructable, and whether any armed/thresholded/actioned case is visible in the runtime evidence.

Evidence base used here:
- [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl)
- [logs/domain_execution_position.log*](logs/domain_execution_position.log)
- [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl)
- [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl)
- [artifacts/r7f_peak_giveback_verified_summary.json](artifacts/r7f_peak_giveback_verified_summary.json)

## Observation Window
- Start: 2026-04-29T08:04:40.830Z
- End: 2026-04-29T21:54:42.308Z

## FACTS
- The fresh runtime slice contains 68426 Sidecar rows in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl).
- 68425 of those rows carry peak_giveback_snapshot; the single missing snapshot is the bootstrap mode-active row, which instead carries sidecar_config_snapshot.
- There are 0 malformed Sidecar rows in the inspected slice.
- The only mode-active row is a POSITION_POLICY_SIDECAR_MODE_ACTIVE bootstrap row at ts_ms 1777449880830, and it contains sidecar_config_snapshot.
- The runtime config snapshot proves the expected policy values: mode=enable, peak_giveback_close.enabled=true, edge_arm_usd=25.0, giveback_trigger_pct=50.0, freshness limits of 60000/15000/30000/15000 ms for portfolio/features/regime/order state.
- Peak-giveback state counts across the full Sidecar stream are: peak_giveback_not_ready 66695, peak_giveback_suppressed_stale_inputs 1497, peak_giveback_unavailable_economics_missing 212, peak_giveback_suppressed_close_in_progress 21.
- No row in the inspected slice exposes non-null mark_price, unrealized_pnl_usdt, or current_edge_usd.
- No row in the inspected slice has a threshold-met timestamp, a recommendation emission, a close-request emission, or a downstream close reconciled directly attributable to Sidecar provenance.
- The rid-linked lifecycle set contains 11 lifecycles. All 11 end in the safe-suppression family; 10 end in peak_giveback_not_ready and 1 ends in peak_giveback_suppressed_stale_inputs.
- No POSITION_POLICY_SIDECAR_RECOMMENDED, no POSITION_POLICY_SIDECAR_CLOSE_REQUESTED, and no position_policy_sidecar:peak_giveback provenance strings were found in the adjacent downstream logs.
- The downstream close path that does exist is EP-owned: ManageFlowFSM / CloseExecutor emits DEC:CLOSE, ORDER_INTENT, ORDER_PLACED, and reconciliation traces.

## INFERENCES
- R7C observability is now present in the verified runtime and is emitted consistently in raw JSONL after restart.
- The peak-giveback path is observable and reconstructable, but it is not proven to be quiet-by-market because the slice contains explicit null reasons rather than usable economics.
- The absence of recommendations and close requests, together with the absence of threshold-met rows, indicates quiet suppression rather than a trigger defect.
- The absence of sidecar provenance in downstream close logs means there is no evidence of a direct Sidecar execution path, ownership violation, or bracket mutation in this slice.
- The BNB continuity tail still shows no_active_lifecycle after flat-state tail rows; that is visible, but it is not a Sidecar safety regression in this package.

## ASSUMPTIONS
- The final observed lifecycle state is the correct basis for the lifecycle classification used in the evidence matrix.
- A tail no_active_lifecycle suppression after the lifecycle goes flat is expected suppression, not a separate Sidecar defect.
- Absence of a close-request or recommendation row is treated as evidence of no emission, not as a logging gap, because the downstream logs were also checked.

## UNKNOWNS
- No lifecycle in this slice exposes usable market economics, so peak edge < 25 or giveback < 50 cannot be proven from live values.
- The source_config_path on the bootstrap config snapshot is null, so the config source path is not part of the runtime proof here.
- The slice does not contain a threshold-met case, so the trigger path remains unexercised in this verified runtime window.

## R7C Field Presence Proof
- sidecar rows total: 68426
- rows with peak_giveback_snapshot: 68425
- rows missing peak_giveback_snapshot: 1
- rows with null_reasons: 68425
- malformed rows: 0
- rows with sidecar_config_snapshot: 1
- rows with peak_giveback_state: 68425

## Runtime Config Snapshot Proof
The bootstrap row proves the expected loaded config values:
- mode: enable
- peak_giveback_close.enabled: true
- peak_giveback_close.edge_arm_usd: 25.0
- peak_giveback_close.giveback_trigger_pct: 50.0
- freshness.portfolio_max_age_ms: 60000
- freshness.features_max_age_ms: 15000
- freshness.regime_max_age_ms: 30000
- freshness.order_state_max_age_ms: 15000

## Peak-Giveback State Distribution
- peak_giveback_not_ready: 66695
- peak_giveback_suppressed_stale_inputs: 1497
- peak_giveback_unavailable_economics_missing: 212
- peak_giveback_suppressed_close_in_progress: 21

By symbol in the broader Sidecar stream:
- BNBUSDT: 10044
- XRPUSDT: 10044
- BTCUSDT: 9981
- ETHUSDT: 9892
- SOLUSDT: 9888
- DOGEUSDT: 9288
- 1000PEPEUSDT: 9288

## Lifecycle Case Split
All rid-linked lifecycles end in case E, Suppressed safely.
- 10 lifecycles end in peak_giveback_not_ready.
- 1 lifecycle ends in peak_giveback_suppressed_stale_inputs.
- 0 lifecycles end in threshold_met.
- 0 lifecycles emit recommendation or close-request evidence.

Representative rid outcomes:
- BNBUSDT rid aurora_BNBUSDT_1777451703445, window 1777451794989..1777475531277, final state peak_giveback_not_ready, final reason codes trigger:portfolio_state_updated / peak_giveback_not_ready / no_active_lifecycle.
- BTCUSDT rid aurora_BTCUSDT_1777487402361, window 1777487403798..1777495000172, final state peak_giveback_suppressed_stale_inputs, final reason codes trigger:order_state_changed / peak_giveback_suppressed_stale_inputs / features_stale.
- XRPUSDT rid aurora_XRPUSDT_1777474204669, window 1777474437289..1777487408780, final state peak_giveback_not_ready, final reason codes trigger:portfolio_state_updated / peak_giveback_not_ready / no_active_lifecycle.

## Trigger / Routing / Safety Analysis
- No threshold-met row was observed.
- No armed lifecycle was observed.
- No recommendation row was observed.
- No close-request row was observed.
- No downstream close row carried Sidecar peak-giveback provenance.
- No duplicate trigger storm was observed.
- No direct exchange action from Sidecar was observed.
- No bracket mutation from Sidecar was observed.
- The downstream close path that exists is still owned by ManageFlowFSM / CloseExecutor, not by Sidecar.

## BNB Post-Fill Continuity Note
The BNB lifecycle tail still shows no_active_lifecycle after the position goes flat. That continuity issue remains visible in the runtime, but it is separate from peak-giveback safety and it does not look like a Sidecar routing defect in this package.

## Final Verdict
The verified runtime is observable and safe, but it is not proven quiet-by-market because economics never became usable in this slice. The correct package verdict is:

PEAK_GIVEBACK_RUNTIME_QUIET_BUT_OBSERVABLE
