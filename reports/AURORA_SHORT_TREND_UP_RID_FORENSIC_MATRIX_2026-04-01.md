# Aurora SHORT Under TREND_UP Accepted RID Forensic Matrix

Date: 2026-04-01

Scope:
- 7 accepted Aurora RIDs only
- Symbols limited to BTCUSDT, ETHUSDT, SOLUSDT
- Runtime evidence first; code used only to interpret runtime gaps
- No code changes, no tuning, no redesign

## 1. Executive Verdict

FACT: All 7 target RIDs are accepted upstream SELL decisions under TREND_UP before lifecycle finalization. Decision-side proof exists in [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451), [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234), [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970), [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602), [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403), [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629), and [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099). Boundary proof exists in DecisionMaking ORDER_INTENT at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102), [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193), [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201), [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229), [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239), [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249), and [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253).

FACT: No RID proves a first liar inside detector, handler-local remap, or downstream packaging. The earliest repeated proven seam is observability loss at EVT:DECISION_TRACE_EMITTED schema validation: [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460), [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244), [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979), [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611), [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412), [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638), and [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109).

INFERENCE: The accepted SHORT/TREND_UP population is most consistent with a permitted countertrend short branch, because safety_gates has an explicit soft short allow at [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251) and hard_veto_consecutive_bars is 2 at [domains.yaml#L97](../config/aurora/domains.yaml#L97). This remains an inference, not per-RID runtime proof, because trend_run_length is present in emit code at [intent_builder.py#L312](../apps/reference/domains/decision_making/intent_builder.py#L312) and [decision_making.py#L399](../apps/reference/domains/decision_making/decision_making.py#L399), but the runtime trace rejects it before persistence.

FACT: Only aurora_ETHUSDT_1775013603304 proves an execution defect after an accepted decision, via ORDER_TIMEOUT at [order_log_v1.jsonl#L257](../logs/order_log_v1.jsonl#L257), ORDER_CANCELLED at [order_log_v1.jsonl#L258](../logs/order_log_v1.jsonl#L258), and websocket CANCELED state at [aurora_events.jsonl#L47](../logs/aurora_events.jsonl#L47).

FACT: ORPHANED_TTL is logger policy, not execution truth by itself. The lifecycle logger marks still-open records as ORPHANED_TTL at [trade_lifecycle_logger.py#L219](../apps/reference/telemetry/trade_lifecycle_logger.py#L219) and assigns TTL_EXPIRED_* close reasons at [trade_lifecycle_logger.py#L220](../apps/reference/telemetry/trade_lifecycle_logger.py#L220). This is corroborated by filled or canceled target rows still ending as ORPHANED_TTL at [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9), [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18), [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19), [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20), [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21), [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22), and [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23).

ASSUMPTION: The text timestamps in aurora_core.log* are interpreted as UTC+3 relative to epoch-based JSONL timestamps. This assumption is used only for before/after sequencing and never to replace direct RID-based causality.

## 2. RID-by-RID Matrix

FACT: The matrix is rendered as one vertical record per RID because the evidence cells are citation-heavy. The exact field names requested by the task are preserved and kept in the requested order.

### aurora_BTCUSDT_1774931703505

- rid: aurora_BTCUSDT_1774931703505
- symbol: BTCUSDT
- intent_ts_utc: FACT: 2026-03-31T04:35:03.667Z via [trade_lifecycle#L9](../logs/trade_lifecycle.jsonl#L9)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via logged detector transition [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697)
- detector_last_proven_confidence_before_intent: FACT: 0.2868374982793305678625570979 via [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.5581152708665025 from nearest DM boundary [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451)
- decision_score: FACT: -0.139757 via [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451)
- threshold_context: FACT: thr_buy=0.01620 and thr_sell=0.01620 via [aurora_core.log.28#L10452](../logs/aurora_core.log.28#L10452)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460)
- nearby_reject_prev: FACT: aurora_BTCUSDT_1774931403631, NRR-029, about 5 minutes earlier at [order_log_v1.jsonl#L99](../logs/order_log_v1.jsonl#L99)
- nearby_reject_next: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.28#L10455](../logs/aurora_core.log.28#L10455)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102)
- execution_outcome: FACT: FILLED via [aurora_events.jsonl#L7](../logs/aurora_events.jsonl#L7)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: detector heartbeat payload between [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697) and the decision boundary

### aurora_ETHUSDT_1774982101125

- rid: aurora_ETHUSDT_1774982101125
- symbol: ETHUSDT
- intent_ts_utc: FACT: 2026-03-31T18:35:01.327Z via [trade_lifecycle#L18](../logs/trade_lifecycle.jsonl#L18)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via logged detector transition [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482)
- detector_last_proven_confidence_before_intent: FACT: 0.7347285789182831961231632493 via [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.824102531120249 from nearest DM boundary [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234)
- decision_score: FACT: -0.141663 via [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234)
- threshold_context: FACT: thr_buy=0.022100 and thr_sell=0.022100 via [aurora_core.log.14#L23235](../logs/aurora_core.log.14#L23235)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244)
- nearby_reject_prev: FACT: aurora_ETHUSDT_1774981801253, NRR-029, about 5 minutes earlier at [order_log_v1.jsonl#L191](../logs/order_log_v1.jsonl#L191)
- nearby_reject_next: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.14#L23239](../logs/aurora_core.log.14#L23239)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193)
- execution_outcome: FACT: FILLED via [aurora_events.jsonl#L13](../logs/aurora_events.jsonl#L13)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: detector heartbeat payload between [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482) and the decision boundary

### aurora_BTCUSDT_1774986900860

- rid: aurora_BTCUSDT_1774986900860
- symbol: BTCUSDT
- intent_ts_utc: FACT: 2026-03-31T19:55:01.087Z via [trade_lifecycle#L19](../logs/trade_lifecycle.jsonl#L19)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via logged detector transition [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_last_proven_confidence_before_intent: FACT: 0.4148753312659917962844561821 via [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.535576592494976 from nearest DM boundary [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970)
- decision_score: FACT: -0.132430 via [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970)
- threshold_context: FACT: thr_buy=0.01620 and thr_sell=0.01620 via [aurora_core.log.13#L38971](../logs/aurora_core.log.13#L38971)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979)
- nearby_reject_prev: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- nearby_reject_next: FACT: aurora_BTCUSDT_1774987201885, NRR-027, about 5 minutes later at [order_log_v1.jsonl#L205](../logs/order_log_v1.jsonl#L205)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.13#L38974](../logs/aurora_core.log.13#L38974)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201)
- execution_outcome: FACT: FILLED via [aurora_events.jsonl#L14](../logs/aurora_events.jsonl#L14)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: detector heartbeat payload between [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782) and the decision boundary

### aurora_SOLUSDT_1774991109696

- rid: aurora_SOLUSDT_1774991109696
- symbol: SOLUSDT
- intent_ts_utc: FACT: 2026-03-31T21:05:09.749Z via [trade_lifecycle#L20](../logs/trade_lifecycle.jsonl#L20)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via logged detector transition [aurora_core.log.12#L113](../logs/aurora_core.log.12#L113)
- detector_last_proven_confidence_before_intent: FACT: 0.2967338336856360136893547119 via [aurora_core.log.12#L113](../logs/aurora_core.log.12#L113)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.706606373449315 from nearest DM boundary [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602)
- decision_score: FACT: -0.185824 via [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602)
- threshold_context: FACT: thr_buy=0.023200 and thr_sell=0.023200 via [aurora_core.log.11#L4603](../logs/aurora_core.log.11#L4603)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611)
- nearby_reject_prev: FACT: aurora_SOLUSDT_1774990804384, NRR-027, about 5 minutes earlier at [order_log_v1.jsonl#L227](../logs/order_log_v1.jsonl#L227)
- nearby_reject_next: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.11#L4606](../logs/aurora_core.log.11#L4606)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229)
- execution_outcome: FACT: FILLED via [aurora_events.jsonl#L15](../logs/aurora_events.jsonl#L15)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: detector heartbeat payload between [aurora_core.log.12#L113](../logs/aurora_core.log.12#L113) and the decision boundary

### aurora_BTCUSDT_1774992000648

- rid: aurora_BTCUSDT_1774992000648
- symbol: BTCUSDT
- intent_ts_utc: FACT: 2026-03-31T21:20:00.695Z via [trade_lifecycle#L21](../logs/trade_lifecycle.jsonl#L21)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via last visible BTC detector transition [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_last_proven_confidence_before_intent: FACT: 0.4148753312659917962844561821 via [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.7833148900691568 from nearest DM boundary [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403)
- decision_score: FACT: -0.141647 via [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403)
- threshold_context: FACT: thr_buy=0.01620 and thr_sell=0.01620 via [aurora_core.log.11#L15404](../logs/aurora_core.log.11#L15404)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412)
- nearby_reject_prev: FACT: aurora_BTCUSDT_1774991700584, NRR-027, about 5 minutes earlier at [order_log_v1.jsonl#L235](../logs/order_log_v1.jsonl#L235)
- nearby_reject_next: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.11#L15407](../logs/aurora_core.log.11#L15407)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239)
- execution_outcome: FACT: FILLED via [aurora_events.jsonl#L16](../logs/aurora_events.jsonl#L16)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: no later visible BTC detector transition is logged before this intent in scanned aurora_core.log.13-.9

### aurora_BTCUSDT_1774994703487

- rid: aurora_BTCUSDT_1774994703487
- symbol: BTCUSDT
- intent_ts_utc: FACT: 2026-03-31T22:05:03.568Z via [trade_lifecycle#L22](../logs/trade_lifecycle.jsonl#L22)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via last visible BTC detector transition [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_last_proven_confidence_before_intent: FACT: 0.4148753312659917962844561821 via [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782)
- detector_evidence_gap_yes_no: FACT: YES
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629)
- handler_regime_confidence_used_for_decision: INFERENCE: 0.8141249074544116 from nearest DM boundary [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249); exact handler-local cache read is not logged
- decision_side: FACT: SELL via [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629)
- decision_score: FACT: -0.138671 via [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629)
- threshold_context: FACT: thr_buy=0.01620 and thr_sell=0.01620 via [aurora_core.log.10#L7630](../logs/aurora_core.log.10#L7630)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638)
- nearby_reject_prev: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- nearby_reject_next: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.10#L7633](../logs/aurora_core.log.10#L7633)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249)
- execution_outcome: FACT: PARTIALS to FILLED via [aurora_events.jsonl#L17](../logs/aurora_events.jsonl#L17) and final FILLED at [aurora_events.jsonl#L46](../logs/aurora_events.jsonl#L46)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638)
- decision_vs_execution_split: FACT: neither proven
- proof_grade: FACT: MEDIUM
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: no later visible BTC detector transition is logged before this intent in scanned aurora_core.log.13-.9

### aurora_ETHUSDT_1775013603304

- rid: aurora_ETHUSDT_1775013603304
- symbol: ETHUSDT
- intent_ts_utc: FACT: 2026-04-01T03:20:03.460Z via [trade_lifecycle#L23](../logs/trade_lifecycle.jsonl#L23)
- detector_last_proven_regime_before_intent: FACT: TREND_UP via logged detector transition [aurora_core.log.5#L35098](../logs/aurora_core.log.5#L35098)
- detector_last_proven_confidence_before_intent: FACT: 0.4995014854396267200107450058 via [aurora_core.log.5#L35098](../logs/aurora_core.log.5#L35098)
- detector_evidence_gap_yes_no: FACT: NO
- handler_regime_used_for_decision: FACT: TREND_UP via [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099)
- handler_regime_confidence_used_for_decision: FACT: 0.49950148543962675 at the DM boundary [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253), numerically matched to detector evidence at [aurora_core.log.5#L35098](../logs/aurora_core.log.5#L35098); exact handler-local cache read is not separately logged
- decision_side: FACT: SELL via [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099)
- decision_score: FACT: -0.165975 via [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099)
- threshold_context: FACT: thr_buy=0.022100 and thr_sell=0.022100 via [aurora_core.log.5#L35100](../logs/aurora_core.log.5#L35100)
- allow_or_block_path_proven: FACT: NO
- allow_or_block_path_description: UNKNOWN: exact runtime allow basis is absent. INFERENCE: a soft countertrend short remains code-consistent via [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251), but accepted-trace rationale is lost when EVT:DECISION_TRACE_EMITTED fails at [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109)
- nearby_reject_prev: FACT: none within 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl)
- nearby_reject_next: FACT: aurora_ETHUSDT_1775014204129, NRR-027, about 10 minutes later at [order_log_v1.jsonl#L256](../logs/order_log_v1.jsonl#L256)
- strategy_signal_proven_yes_no: FACT: YES via SELL signal processing at [aurora_core.log.5#L35104](../logs/aurora_core.log.5#L35104)
- trade_intent_proven_yes_no: FACT: YES via DM ORDER_INTENT at [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253)
- execution_outcome: FACT: ORDER_PLACED at [order_log_v1.jsonl#L255](../logs/order_log_v1.jsonl#L255), then ORDER_TIMEOUT at [order_log_v1.jsonl#L257](../logs/order_log_v1.jsonl#L257), ORDER_CANCELLED at [order_log_v1.jsonl#L258](../logs/order_log_v1.jsonl#L258), and final CANCELED venue state at [aurora_events.jsonl#L47](../logs/aurora_events.jsonl#L47)
- lifecycle_final_status: FACT: ORPHANED_TTL via [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23)
- lifecycle_close_reason: FACT: TTL_EXPIRED_3600s via [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23)
- first_proven_seam_if_any: FACT: decision-trace observability loss at [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109)
- decision_vs_execution_split: FACT: execution defect proven
- proof_grade: FACT: HIGH
- remaining_unknowns: UNKNOWN: exact trend_run_length; UNKNOWN: why_short; UNKNOWN: raw strategy-signal payload; UNKNOWN: venue-side cause of fill_timeout beyond the timeout/cancel facts

## 3. Proven Regime Provenance Findings

aurora_BTCUSDT_1774931703505. FACT: The last visible detector transition before intent is [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697), UNCERTAIN to TREND_UP, confidence 0.2868374982793305678625570979. FACT: The decision trace is already TREND_UP at [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.5581152708665025 at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102) and [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9). INFERENCE: The confidence increase is consistent with detector heartbeat emission at [regime_detector.py#L705](../apps/reference/domains/regime_detector/regime_detector.py#L705), stable_confidence refresh at [regime_detector.py#L734](../apps/reference/domains/regime_detector/regime_detector.py#L734), and handler cache update at [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545). UNKNOWN: The exact heartbeat payload consumed by the handler is absent.

aurora_ETHUSDT_1774982101125. FACT: The last visible detector transition before intent is [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482), HIGH_VOLATILITY to TREND_UP, confidence 0.7347285789182831961231632493. FACT: The decision trace is TREND_UP at [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.824102531120249 at [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193) and [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18). INFERENCE: This is another confidence-granularity gap that code can explain, but runtime does not close per RID. UNKNOWN: The exact heartbeat or cache-refresh event between the logged transition and the intent is absent.

aurora_BTCUSDT_1774986900860. FACT: The last visible detector transition before intent is [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782), UNCERTAIN to TREND_UP, confidence 0.4148753312659917962844561821. FACT: The decision trace is TREND_UP at [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.535576592494976 at [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201) and [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19). INFERENCE: The mismatch is compatible with heartbeat/stable_confidence refresh. UNKNOWN: No per-RID detector heartbeat payload survives to prove the exact update path.

aurora_SOLUSDT_1774991109696. FACT: The last visible detector transition before intent is [aurora_core.log.12#L113](../logs/aurora_core.log.12#L113), UNCERTAIN to TREND_UP, confidence 0.2967338336856360136893547119. FACT: The decision trace is TREND_UP at [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.706606373449315 at [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229) and [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20). FACT: A later visible transition to UNCERTAIN exists after this RID at [aurora_core.log.11#L15373](../logs/aurora_core.log.11#L15373), so the detector was not permanently stuck. INFERENCE: The confidence gap still looks like logging granularity, not a proven stale cache. UNKNOWN: The exact detector payload seen by the handler at entry time is absent.

aurora_BTCUSDT_1774992000648. FACT: The last visible BTC detector transition before intent remains [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782). FACT: The decision trace is TREND_UP at [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.7833148900691568 at [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239) and [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21). FACT: In the scanned visible BTC transition set, no later BTC Regime updated line appears before this intent. INFERENCE: Heartbeat-driven stable_confidence refresh remains the best code-consistent explanation. UNKNOWN: The detector-to-handler continuity between [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782) and the decision boundary is not directly logged.

aurora_BTCUSDT_1774994703487. FACT: The last visible BTC detector transition before intent still remains [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782). FACT: The decision trace is TREND_UP at [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629). FACT: DM ORDER_INTENT and lifecycle both carry TREND_UP with confidence 0.8141249074544116 at [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249) and [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22). FACT: In the scanned visible BTC transition set, no later BTC Regime updated line appears before this intent. INFERENCE: Heartbeat-driven stable_confidence refresh remains the best code-consistent explanation. UNKNOWN: The exact detector heartbeat sequence between the old logged transition and this late-BTC decision is absent.

aurora_ETHUSDT_1775013603304. FACT: The detector transitions to TREND_UP only 161 ms before the decision at [aurora_core.log.5#L35098](../logs/aurora_core.log.5#L35098), with confidence 0.4995014854396267200107450058. FACT: The decision trace is TREND_UP at [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099). FACT: DM ORDER_INTENT and lifecycle carry the same boundary confidence at [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253) and [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23). FACT: A later visible ETH transition back to UNCERTAIN exists at [aurora_core.log.4#L2733](../logs/aurora_core.log.4#L2733). FACT: This RID is the cleanest detector-to-decision regime chain in the sample. UNKNOWN: The raw heartbeat event object itself is still not persisted, but no mismatch is proven here.

## 4. Proven Side Provenance Findings

aurora_BTCUSDT_1774931703505. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451). FACT: The gateway processes a SELL signal at [aurora_core.log.28#L10455](../logs/aurora_core.log.28#L10455). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102). UNKNOWN: The exact allow basis for why a SHORT under TREND_UP was permitted is not preserved because the trace emit fails at [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460).

aurora_ETHUSDT_1774982101125. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234). FACT: The gateway processes a SELL signal at [aurora_core.log.14#L23239](../logs/aurora_core.log.14#L23239). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244).

aurora_BTCUSDT_1774986900860. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970). FACT: The gateway processes a SELL signal at [aurora_core.log.13#L38974](../logs/aurora_core.log.13#L38974). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979).

aurora_SOLUSDT_1774991109696. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602). FACT: The gateway processes a SELL signal at [aurora_core.log.11#L4606](../logs/aurora_core.log.11#L4606). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611).

aurora_BTCUSDT_1774992000648. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403). FACT: The gateway processes a SELL signal at [aurora_core.log.11#L15407](../logs/aurora_core.log.11#L15407). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412).

aurora_BTCUSDT_1774994703487. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629). FACT: The gateway processes a SELL signal at [aurora_core.log.10#L7633](../logs/aurora_core.log.10#L7633). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638).

aurora_ETHUSDT_1775013603304. FACT: Side first becomes explicit SELL in the upstream decision trace at [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099). FACT: The gateway processes a SELL signal at [aurora_core.log.5#L35104](../logs/aurora_core.log.5#L35104). FACT: DM ORDER_INTENT is SELL at [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253). UNKNOWN: The exact allow basis is not preserved because the trace emit fails at [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109).

FACT: The code path that could explain these SELL decisions under TREND_UP is a soft countertrend short at [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251). INFERENCE: That path is the best interpretation for the accepted sample. UNKNOWN: No RID has a persisted runtime trend_run_length or why_short proving that path directly.

## 5. Reject Neighbor Consistency Findings

aurora_BTCUSDT_1774931703505. FACT: The nearest same-symbol reject is aurora_BTCUSDT_1774931403631, NRR-029, at [order_log_v1.jsonl#L99](../logs/order_log_v1.jsonl#L99), about 5 minutes earlier. FACT: NRR-029 is a flash-up short block, not the same code as NRR-027. INFERENCE: This is better classified as expected branch difference than direct inconsistency. UNKNOWN: The accepted RID's exact allow rationale is still missing.

aurora_ETHUSDT_1774982101125. FACT: The nearest same-symbol reject is aurora_ETHUSDT_1774981801253, NRR-029, at [order_log_v1.jsonl#L191](../logs/order_log_v1.jsonl#L191), about 5 minutes earlier. FACT: This is another flash-up short block, not a direct NRR-027 contradiction. INFERENCE: This is better classified as expected branch difference than direct inconsistency. UNKNOWN: The accepted RID's exact allow rationale is still missing.

aurora_BTCUSDT_1774986900860. FACT: The nearest same-symbol reject is aurora_BTCUSDT_1774987201885, NRR-027, at [order_log_v1.jsonl#L205](../logs/order_log_v1.jsonl#L205), about 5 minutes later. FACT: The code explicitly permits soft countertrend short before hard_veto_consecutive_bars at [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251) and hard_veto_consecutive_bars is 2 at [domains.yaml#L97](../config/aurora/domains.yaml#L97). FACT: Direct inconsistency is therefore not proven. UNKNOWN: This neighbor relation remains unresolved ambiguity because the accepted RID's trend_run_length is missing.

aurora_SOLUSDT_1774991109696. FACT: The nearest same-symbol reject is aurora_SOLUSDT_1774990804384, NRR-027, at [order_log_v1.jsonl#L227](../logs/order_log_v1.jsonl#L227), about 5 minutes earlier. FACT: The same soft-versus-hard split in [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251) prevents this from proving direct inconsistency. UNKNOWN: This neighbor relation remains unresolved ambiguity because the accepted RID's trend_run_length is missing.

aurora_BTCUSDT_1774992000648. FACT: The nearest same-symbol reject is aurora_BTCUSDT_1774991700584, NRR-027, at [order_log_v1.jsonl#L235](../logs/order_log_v1.jsonl#L235), about 5 minutes earlier. FACT: The code allows a soft short path before hard veto, so direct inconsistency is not proven. UNKNOWN: This neighbor relation remains unresolved ambiguity because the accepted RID's trend_run_length is missing.

aurora_BTCUSDT_1774994703487. FACT: No same-symbol NRR-026, NRR-027, NRR-029, or NRR-030 reject is visible within plus or minus 15 minutes in scanned [order_log_v1.jsonl](../logs/order_log_v1.jsonl). FACT: There is therefore no neighbor-based inconsistency test for this RID.

aurora_ETHUSDT_1775013603304. FACT: The nearest same-symbol reject is aurora_ETHUSDT_1775014204129, NRR-027, at [order_log_v1.jsonl#L256](../logs/order_log_v1.jsonl#L256), about 10 minutes later. FACT: The code still allows a soft-to-hard branch difference over that interval, so direct inconsistency is not proven. UNKNOWN: This neighbor relation remains unresolved ambiguity because the accepted RID's trend_run_length is missing.

## 6. Confidence Provenance Findings

aurora_BTCUSDT_1774931703505. FACT: Last logged detector confidence is 0.2868374982793305678625570979 at [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697). FACT: DM ORDER_INTENT and lifecycle confidence are 0.5581152708665025 at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102) and [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9). INFERENCE: This looks like a logging-granularity artifact that code can explain via heartbeat emission [regime_detector.py#L705](../apps/reference/domains/regime_detector/regime_detector.py#L705), stable_confidence refresh [regime_detector.py#L734](../apps/reference/domains/regime_detector/regime_detector.py#L734), and handler caching [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545). UNKNOWN: The exact detector payload consumed by the handler is absent.

aurora_ETHUSDT_1774982101125. FACT: Last logged detector confidence is 0.7347285789182831961231632493 at [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482). FACT: DM ORDER_INTENT and lifecycle confidence are 0.824102531120249 at [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193) and [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18). INFERENCE: The same heartbeat/stable_confidence explanation is available. UNKNOWN: The exact intermediate confidence updates are not logged.

aurora_BTCUSDT_1774986900860. FACT: Last logged detector confidence is 0.4148753312659917962844561821 at [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782). FACT: DM ORDER_INTENT and lifecycle confidence are 0.535576592494976 at [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201) and [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19). INFERENCE: The mismatch is consistent with heartbeat-driven confidence refresh. UNKNOWN: No per-RID heartbeat payload closes the gap.

aurora_SOLUSDT_1774991109696. FACT: Last logged detector confidence is 0.2967338336856360136893547119 at [aurora_core.log.12#L113](../logs/aurora_core.log.12#L113). FACT: DM ORDER_INTENT and lifecycle confidence are 0.706606373449315 at [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229) and [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20). INFERENCE: The difference is large but still code-consistent with stable_confidence refresh, not a proven stale cache. UNKNOWN: The exact refresh sequence is absent.

aurora_BTCUSDT_1774992000648. FACT: Last visible BTC detector confidence before intent remains 0.4148753312659917962844561821 at [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782). FACT: DM ORDER_INTENT and lifecycle confidence are 0.7833148900691568 at [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239) and [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21). INFERENCE: The mechanism is still compatible with heartbeat/stable_confidence refresh. UNKNOWN: No later visible BTC detector transition is logged before this intent, so the continuity is not runtime-proven.

aurora_BTCUSDT_1774994703487. FACT: Last visible BTC detector confidence before intent remains 0.4148753312659917962844561821 at [aurora_core.log.13#L17782](../logs/aurora_core.log.13#L17782). FACT: DM ORDER_INTENT and lifecycle confidence are 0.8141249074544116 at [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249) and [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22). INFERENCE: The mechanism is still compatible with heartbeat/stable_confidence refresh. UNKNOWN: No later visible BTC detector transition is logged before this intent, so the continuity is not runtime-proven.

aurora_ETHUSDT_1775013603304. FACT: Detector confidence 0.4995014854396267200107450058 at [aurora_core.log.5#L35098](../logs/aurora_core.log.5#L35098) matches the DM ORDER_INTENT and lifecycle boundary confidence 0.49950148543962675 at [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253) and [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23). FACT: This RID does not exhibit a confidence mismatch.

FACT: The separate regime confidence gate is 0.42 at [domains.yaml#L93](../config/aurora/domains.yaml#L93). FACT: This explains why some nearby rejects are NRR-026 while accepted cases carry materially higher boundary confidence. No accepted RID in this sample is blocked by the confidence gate.

## 7. Decision vs Execution Split

aurora_BTCUSDT_1774931703505. FACT: Decision accepted at [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451) and [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102). FACT: Order placed at [order_log_v1.jsonl#L105](../logs/order_log_v1.jsonl#L105) and filled at [aurora_events.jsonl#L7](../logs/aurora_events.jsonl#L7). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_ETHUSDT_1774982101125. FACT: Decision accepted at [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234) and [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193). FACT: Order placed at [order_log_v1.jsonl#L195](../logs/order_log_v1.jsonl#L195) and filled at [aurora_events.jsonl#L13](../logs/aurora_events.jsonl#L13). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_BTCUSDT_1774986900860. FACT: Decision accepted at [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970) and [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201). FACT: Order placed at [order_log_v1.jsonl#L203](../logs/order_log_v1.jsonl#L203) and filled at [aurora_events.jsonl#L14](../logs/aurora_events.jsonl#L14). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_SOLUSDT_1774991109696. FACT: Decision accepted at [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602) and [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229). FACT: Order placed at [order_log_v1.jsonl#L231](../logs/order_log_v1.jsonl#L231) and filled at [aurora_events.jsonl#L15](../logs/aurora_events.jsonl#L15). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_BTCUSDT_1774992000648. FACT: Decision accepted at [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403) and [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239). FACT: Order placed at [order_log_v1.jsonl#L242](../logs/order_log_v1.jsonl#L242) and filled at [aurora_events.jsonl#L16](../logs/aurora_events.jsonl#L16). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_BTCUSDT_1774994703487. FACT: Decision accepted at [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629) and [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249). FACT: Order placed at [order_log_v1.jsonl#L251](../logs/order_log_v1.jsonl#L251) and venue state progresses from PARTIALLY_FILLED at [aurora_events.jsonl#L17](../logs/aurora_events.jsonl#L17) to FILLED at [aurora_events.jsonl#L46](../logs/aurora_events.jsonl#L46). FACT: decision defect proven is NO. FACT: execution defect proven is NO. FACT: classification is neither proven.

aurora_ETHUSDT_1775013603304. FACT: Decision accepted at [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099) and [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253). FACT: Order placed at [order_log_v1.jsonl#L255](../logs/order_log_v1.jsonl#L255), then times out at [order_log_v1.jsonl#L257](../logs/order_log_v1.jsonl#L257), is cancelled at [order_log_v1.jsonl#L258](../logs/order_log_v1.jsonl#L258), and ends CANCELED at [aurora_events.jsonl#L47](../logs/aurora_events.jsonl#L47). FACT: decision defect proven is NO. FACT: execution defect proven is YES. FACT: classification is execution defect proven.

FACT: For the first six RIDs, lifecycle ORPHANED_TTL is a separate lifecycle/finalization symptom and is not itself evidence of execution failure.

## 8. Top Proven Defects / Seams

1. Decision-trace observability loss.
Symptom: Accepted and rejected decisions attempt to emit trend_run_length, but runtime rejects the payload.
First observed location: [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460), repeated at [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244), [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979), [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611), [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412), [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638), and [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109).
Possible mechanism: Allow-trace code includes trend_run_length at [intent_builder.py#L312](../apps/reference/domains/decision_making/intent_builder.py#L312) and emits EVT:DECISION_TRACE_EMITTED at [intent_builder.py#L321](../apps/reference/domains/decision_making/intent_builder.py#L321); deny-trace code does the same at [decision_making.py#L399](../apps/reference/domains/decision_making/decision_making.py#L399) and [decision_making.py#L409](../apps/reference/domains/decision_making/decision_making.py#L409).
Operational effect: The decisive per-RID allow-versus-deny rationale is unavailable for audit.
Proof status: FACT for the seam. UNKNOWN for the exact schema contract location not inspected in this report.

2. Lifecycle TTL terminalization seam.
Symptom: Filled or canceled records still finalize as ORPHANED_TTL with TTL_EXPIRED_3600s.
First observed location: [trade_lifecycle.jsonl#L9](../logs/trade_lifecycle.jsonl#L9), [trade_lifecycle.jsonl#L18](../logs/trade_lifecycle.jsonl#L18), [trade_lifecycle.jsonl#L19](../logs/trade_lifecycle.jsonl#L19), [trade_lifecycle.jsonl#L20](../logs/trade_lifecycle.jsonl#L20), [trade_lifecycle.jsonl#L21](../logs/trade_lifecycle.jsonl#L21), [trade_lifecycle.jsonl#L22](../logs/trade_lifecycle.jsonl#L22), and [trade_lifecycle.jsonl#L23](../logs/trade_lifecycle.jsonl#L23).
Possible mechanism: The logger marks any stale record not already CLOSED or CANCELLED as ORPHANED_TTL at [trade_lifecycle_logger.py#L219](../apps/reference/telemetry/trade_lifecycle_logger.py#L219) and assigns a TTL_EXPIRED reason at [trade_lifecycle_logger.py#L220](../apps/reference/telemetry/trade_lifecycle_logger.py#L220).
Operational effect: lifecycle final status cannot be treated as terminal execution truth without cross-checking order and shadow logs.
Proof status: FACT for the seam.

3. ETH-specific execution timeout seam.
Symptom: Accepted decision, placed order, then timeout and cancellation without fill.
First observed location: [order_log_v1.jsonl#L257](../logs/order_log_v1.jsonl#L257), [order_log_v1.jsonl#L258](../logs/order_log_v1.jsonl#L258), and [aurora_events.jsonl#L47](../logs/aurora_events.jsonl#L47).
Possible mechanism: fill_timeout handling in ExecPosFSM, evidenced by the timeout/cancel event chain, not by strategy rejection.
Operational effect: No execution despite a valid accepted SELL decision.
Proof status: FACT, but only for aurora_ETHUSDT_1775013603304.

4. Detector confidence visibility gap.
Symptom: For 6 of 7 RIDs, the last visible logged detector confidence differs from the boundary confidence seen in DM ORDER_INTENT and lifecycle.
First observed location: for example [aurora_core.log.29#L6697](../logs/aurora_core.log.29#L6697) versus [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102), and [aurora_core.log.15#L39482](../logs/aurora_core.log.15#L39482) versus [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193).
Possible mechanism: heartbeat emission on every basis bar at [regime_detector.py#L705](../apps/reference/domains/regime_detector/regime_detector.py#L705), stable_confidence refresh at [regime_detector.py#L734](../apps/reference/domains/regime_detector/regime_detector.py#L734), and handler caching at [aurora_handler.py#L545](../apps/reference/domains/decision_making/aurora_handler.py#L545).
Operational effect: It can resemble stale cache or packaging drift even when no such defect is proven.
Proof status: FACT for the symptom, INFERENCE for the mechanism, UNKNOWN as a defect.

## 9. What Remains Unproven

- UNKNOWN: The exact per-RID trend_run_length for all 7 accepted cases.
- UNKNOWN: The exact per-RID why_short text for all 7 accepted cases.
- UNKNOWN: Whether any accepted RID had already crossed hard_veto_consecutive_bars=2 at the moment of acceptance.
- UNKNOWN: The exact detector heartbeat payload consumed by the handler for the six RIDs that have a detector evidence gap.
- UNKNOWN: The raw EVT:STRATEGY_SIGNAL_PRODUCED payload keyed by RID or lifecycle_id for the seven accepted cases.
- UNKNOWN: The precise venue/book reason why aurora_ETHUSDT_1775013603304 remained unfilled until timeout, beyond the timeout and cancel facts.
- UNKNOWN: Whether lifecycle ORPHANED_TTL reflects missing close/cancel callbacks, missing state reconciliation, or merely a logger-state ownership gap.

## 10. Missing Logs / Artifacts Needed For Closure

- A persisted EVT:DECISION_TRACE_EMITTED artifact that accepts trend_run_length and why_short for both allow and deny outcomes.
- A persisted EVT:REGIME_DETECTED heartbeat journal or JSONL keyed closely enough to reconstruct the exact detector payload seen by the handler at each accepted RID.
- A raw EVT:STRATEGY_SIGNAL_PRODUCED payload keyed by RID or lifecycle_id, so strategy_signal lineage does not have to rely on gateway processing logs.
- Execution-position or venue book snapshots around aurora_ETHUSDT_1775013603304, so the fill_timeout can be tied to concrete marketability evidence rather than only timeout/cancel events.
- Lifecycle logger transition artifacts showing why filled and canceled entries were not moved into CLOSED or CANCELLED before TTL flush.
