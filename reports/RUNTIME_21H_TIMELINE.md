# RUNTIME_21H_TIMELINE

Window anchor used in this forensic package:
- start_ts_ms: 1775850999747
- end_ts_ms: 1775925057020
- duration: ~20.57h

## Segment 1: Startup / Bootstrap Window
- 1775850999747: shadow journal restore marker (RESTORE:EXECUTION_TRUTH_HARDENING_RESET).
- 1775850999991: trade_lifecycle sidecar mode active (shadow, phase1_recommendation_only).
- 1775851801349: order_log BOOT marker.
- 1775852220xxx - 1775852230xxx: feature_engineering warmup not full_ready logs; fail_fast rejection for most symbols; explicit degraded-eligible bypass seen for XRPUSDT and BNBUSDT.

## Segment 2: Early Warmup Window
- FE emits repeated FE_WARMUP full_ready=False transitions with reasons including insufficient history and macro_sync constraints.
- Multiple CMD:PROCESS_STRATEGY warmup rejects recorded for non-degraded-eligible paths.
- FE transitions to full_ready=True as sample counts/history accumulate.

## Segment 3: First Stable Runtime Window
- Decision path and execution truth confirm open/filled flows in order_log and aurora_events.
- XRPUSDT md_amr path observed with handler sizing/qty, gateway pass, and TRADE_INTENT_PROPOSED emission.
- BNBUSDT entry fills observed (multi-partial completion to 10.08).

## Segment 4: Later Runtime Window
- DECISION_INTENT_REJECTED continues with dominant classes NRR-027 and NRR-026.
- NRR-026 appears more prominent in later slices where regime confidence drops under threshold.
- No ORDER_REJECTED evidence in this window.

## Segment 5: Final Observed State
- trade_lifecycle and shadow journal tail show portfolio/exposure updates still active.
- Final portfolio snapshot in shadow journal includes open BNBUSDT and XRPUSDT long inventory presence at tail timestamp.
- Sidecar suppression records remain present (startup_grace and stale/no_active_lifecycle suppressions observed in sampled evidence).

## Evidence Notes
FACT:
- Startup markers and timestamps above come from JSONL lines with ts_ms fields.
- FE warmup fail_fast and bypass lines are present in domain_feature_engineering logs.
- XRP md_amr handler/gateway/intent-proposed chain appears in domain_decision_making logs.
- Exchange-level ORDER_REJECTED not observed in sampled and searched order_log records.

INFERENCE:
- Relative prevalence shift from NRR-027 to NRR-026 across later window slices is inferred from sampled extraction and grouped rejects.

UNKNOWN:
- Full uncapped distribution of all trade_lifecycle event types beyond sampled extraction tool limits.
