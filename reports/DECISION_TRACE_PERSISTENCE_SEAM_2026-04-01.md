# Decision Trace Persistence Seam Forensics

Date: 2026-04-01

## 1. Scope

Question in scope: Why does EVT:DECISION_TRACE_EMITTED fail to persist the exact allow or deny rationale for Aurora decisions, and which fields are lost at runtime?

Scope boundaries:
- Runtime evidence first
- Code and schemas used only to interpret runtime behavior
- Focused on the decision-trace seam, not strategy redesign
- Accepted sample limited to the 7 SHORT under TREND_UP RIDs already established in [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](./AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md)

## 2. Pipeline Map

FACT: Accepted Aurora decisions assemble a decision-trace payload inside [intent_builder.py#L309](../apps/reference/domains/decision_making/intent_builder.py#L309) and emit EVT:DECISION_TRACE_EMITTED at [intent_builder.py#L321](../apps/reference/domains/decision_making/intent_builder.py#L321).

FACT: Safety-gate denials assemble a sibling trace payload inside [decision_making.py#L395](../apps/reference/domains/decision_making/decision_making.py#L395) and emit EVT:DECISION_TRACE_EMITTED at [decision_making.py#L409](../apps/reference/domains/decision_making/decision_making.py#L409).

FACT: vFoundation validates payloads before listener dispatch and before any shadow journal capture at [fsm_core.py#L105](../vfoundation/core/fsm_core.py#L105), [fsm_core.py#L130](../vfoundation/core/fsm_core.py#L130), and [fsm_core.py#L141](../vfoundation/core/fsm_core.py#L141).

FACT: The verb registry binds EVT:DECISION_TRACE_EMITTED to [verb_registry_v1.yaml#L119](../apps/reference/dictionaries/verb_registry_v1.yaml#L119) and [verb_registry_v1.yaml#L122](../apps/reference/dictionaries/verb_registry_v1.yaml#L122), which resolve to [decision_trace_emitted_v1.json#L1](../schemas/decision_trace_emitted_v1.json#L1).

FACT: For DENY only, DecisionMaking writes a separate ORDER_REJECTED journal row after the best-effort trace emit at [decision_making.py#L417](../apps/reference/domains/decision_making/decision_making.py#L417). No symmetric allow-rationale mirror exists on the accepted path.

## 3. Proven Failure Mode

FACT: The schema declares additionalProperties false at [decision_trace_emitted_v1.json#L7](../schemas/decision_trace_emitted_v1.json#L7).

FACT: Both emitters include trend_run_length in the payload at [intent_builder.py#L312](../apps/reference/domains/decision_making/intent_builder.py#L312) and [decision_making.py#L399](../apps/reference/domains/decision_making/decision_making.py#L399).

FACT: The schema does not define trend_run_length anywhere in [decision_trace_emitted_v1.json](../schemas/decision_trace_emitted_v1.json).

FACT: Runtime repeatedly rejects the event with the same validation error, for example at [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460), [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244), [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611), and [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109): Additional properties are not allowed, trend_run_length was unexpected.

VERDICT: The first proven persistence failure is a schema mismatch caused by payload evolution without an additive schema update.

FACT: A second, separate observability weakness also exists: the trace contract omits rid and lifecycle_id from the payload schema in [decision_trace_emitted_v1.json](../schemas/decision_trace_emitted_v1.json), and the emit calls do not pass rid at [intent_builder.py#L321](../apps/reference/domains/decision_making/intent_builder.py#L321) or [decision_making.py#L409](../apps/reference/domains/decision_making/decision_making.py#L409).

CLASSIFICATION: Multiple simultaneous issues.
- Fatal persistence break: schema mismatch on trend_run_length.
- Non-fatal but real auditability gap: no rid or lifecycle_id in the trace contract, and full why_chain is not persisted in payload.

## 4. Exact Field Loss

FACT: The intended trace payload fields are assembled as:
- symbol
- ts
- intent_side
- signal_score
- regime
- regime_confidence
- trend_dir
- trend_run_length
- delta_price
- pm_norm_10s
- pm_norm_60s
- pm_norm_300s
- vol_pct_10s
- vol_pct_60s
- vol_pct_300s
- gate_outcome
- deny_reason
- why

FACT: Because validation fails before dispatch at [fsm_core.py#L105](../vfoundation/core/fsm_core.py#L105) to [fsm_core.py#L141](../vfoundation/core/fsm_core.py#L141), none of those fields persist as a surviving EVT:DECISION_TRACE_EMITTED event.

FACT: trend_run_length is the field that triggers rejection. It is therefore both present in the intended runtime payload and absent from the allowed schema.

FACT: The exact allow or deny rationale is still lost more broadly than one field.
- Accepted path: gate_outcome, why, trend_dir, trend_run_length, delta_price, pm_norm_10s, pm_norm_60s, pm_norm_300s, vol_pct_10s, vol_pct_60s, vol_pct_300s, and signal_score have no surviving accepted-path journal mirror.
- Denied path: nrr_code and short why survive in ORDER_REJECTED at [order_log_v1.jsonl#L2](../logs/order_log_v1.jsonl#L2), [order_log_v1.jsonl#L7](../logs/order_log_v1.jsonl#L7), [order_log_v1.jsonl#L20](../logs/order_log_v1.jsonl#L20), and [order_log_v1.jsonl#L48](../logs/order_log_v1.jsonl#L48), but trend_dir, trend_run_length, delta_price, price-motion fields, vol fields, and signal_score still do not survive.

FACT: The event also does not preserve exact correlation truth because rid is absent from both payload schema and emit envelope.

FACT: Full why_chain is not in the payload schema. It is passed only as data_ref side metadata at [intent_builder.py#L322](../apps/reference/domains/decision_making/intent_builder.py#L322) and [decision_making.py#L410](../apps/reference/domains/decision_making/decision_making.py#L410). Since validation fails before shadow capture or listener dispatch, that side-channel does not survive the rejected emit either.

## 5. Accepted RID Trace Status

FACT: All 7 accepted SHORT under TREND_UP RIDs show the same pattern already established in [AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md](./AURORA_SHORT_TREND_UP_RID_FORENSIC_MATRIX_2026-04-01.md).

aurora_BTCUSDT_1774931703505:
- accepted SELL under TREND_UP at [aurora_core.log.28#L10451](../logs/aurora_core.log.28#L10451)
- trace emit rejected at [aurora_core.log.28#L10460](../logs/aurora_core.log.28#L10460)
- surviving downstream truth: ORDER_INTENT with side, regime, regime_confidence at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_ETHUSDT_1774982101125:
- accepted SELL under TREND_UP at [aurora_core.log.14#L23234](../logs/aurora_core.log.14#L23234)
- trace emit rejected at [aurora_core.log.14#L23244](../logs/aurora_core.log.14#L23244)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_BTCUSDT_1774986900860:
- accepted SELL under TREND_UP at [aurora_core.log.13#L38970](../logs/aurora_core.log.13#L38970)
- trace emit rejected at [aurora_core.log.13#L38979](../logs/aurora_core.log.13#L38979)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_SOLUSDT_1774991109696:
- accepted SELL under TREND_UP at [aurora_core.log.11#L4602](../logs/aurora_core.log.11#L4602)
- trace emit rejected at [aurora_core.log.11#L4611](../logs/aurora_core.log.11#L4611)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_BTCUSDT_1774992000648:
- accepted SELL under TREND_UP at [aurora_core.log.11#L15403](../logs/aurora_core.log.11#L15403)
- trace emit rejected at [aurora_core.log.11#L15412](../logs/aurora_core.log.11#L15412)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_BTCUSDT_1774994703487:
- accepted SELL under TREND_UP at [aurora_core.log.10#L7629](../logs/aurora_core.log.10#L7629)
- trace emit rejected at [aurora_core.log.10#L7638](../logs/aurora_core.log.10#L7638)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

aurora_ETHUSDT_1775013603304:
- accepted SELL under TREND_UP at [aurora_core.log.5#L35099](../logs/aurora_core.log.5#L35099)
- trace emit rejected at [aurora_core.log.5#L35109](../logs/aurora_core.log.5#L35109)
- surviving downstream truth: ORDER_INTENT at [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253)
- lost exact allow proof: why, gate_outcome, trend_run_length, trend context

## 6. Nearby Rejected Comparison

FACT: Nearby rejected short cases preserve more deny truth than accepted cases because DecisionMaking mirrors DENY into ORDER_REJECTED after the failed trace emit at [decision_making.py#L417](../apps/reference/domains/decision_making/decision_making.py#L417).

NRR-026 examples:
- [order_log_v1.jsonl#L2](../logs/order_log_v1.jsonl#L2)
- [order_log_v1.jsonl#L8](../logs/order_log_v1.jsonl#L8)

NRR-027 examples:
- [order_log_v1.jsonl#L7](../logs/order_log_v1.jsonl#L7)
- [order_log_v1.jsonl#L21](../logs/order_log_v1.jsonl#L21)

NRR-029 examples:
- [order_log_v1.jsonl#L20](../logs/order_log_v1.jsonl#L20)
- [order_log_v1.jsonl#L27](../logs/order_log_v1.jsonl#L27)

NRR-030 examples:
- [order_log_v1.jsonl#L6](../logs/order_log_v1.jsonl#L6)
- [order_log_v1.jsonl#L48](../logs/order_log_v1.jsonl#L48)

FACT: These rejected rows preserve normalized deny_reason and a short human why string.

FACT: The accepted rows at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102), [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193), [order_log_v1.jsonl#L201](../logs/order_log_v1.jsonl#L201), [order_log_v1.jsonl#L229](../logs/order_log_v1.jsonl#L229), [order_log_v1.jsonl#L239](../logs/order_log_v1.jsonl#L239), [order_log_v1.jsonl#L249](../logs/order_log_v1.jsonl#L249), and [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253) preserve no equivalent allow rationale.

CONCLUSION: Rejects are only partially recoverable; accepts are not recoverable at the safety-gate rationale level.

## 7. Operational Impact

FACT: The accepted decision journal proves that a SELL intent under TREND_UP happened, but does not prove why it was allowed. The surviving ORDER_INTENT rows contain side, regime, and regime_confidence, but not gate_outcome, why, or trend_run_length, as shown at [order_log_v1.jsonl#L102](../logs/order_log_v1.jsonl#L102), [order_log_v1.jsonl#L193](../logs/order_log_v1.jsonl#L193), and [order_log_v1.jsonl#L253](../logs/order_log_v1.jsonl#L253).

FACT: This is exactly why the 7 accepted SHORT under TREND_UP RIDs cannot be closed to a proven soft countertrend branch even though code offers that branch at [safety_gates.py#L249](../apps/reference/domains/decision_making/safety_gates.py#L249) to [safety_gates.py#L251](../apps/reference/domains/decision_making/safety_gates.py#L251).

FACT: The default shadow journal does not provide a fallback for this event because EVT:DECISION_TRACE_EMITTED is absent from DEFAULT_CRITICAL_EVENTS at [shadow_journal.py#L15](../apps/reference/telemetry/shadow_journal.py#L15).

FACT: The failure is therefore operationally material for audit even when trading continues correctly. Decision truth continues into ORDER_INTENT and execution journals, but the decisive allow-versus-deny rationale does not.

## 8. Strongest Proven Seam And Remaining Unknowns

Strongest proven seam:
- FACT: EVT:DECISION_TRACE_EMITTED fails at schema validation before persistence or listener dispatch because trend_run_length is emitted but not allowed by schema.

Remaining unknowns:
- UNKNOWN: Exact trend_run_length for each of the 7 accepted RIDs.
- UNKNOWN: Exact safety-gate why_short text for each accepted RID.
- UNKNOWN: Whether any accepted RID had already crossed hard_veto_consecutive_bars at decision time.
- UNKNOWN: Full detector-to-handler trend context for each nearby rejected neighbor beyond the compact ORDER_REJECTED reason.

Important non-unknown:
- FACT: The missing proof is an observability failure, not a proven strategy defect in the accepted 7-RID sample.

## 9. Verdict

Final answer:
- EVT:DECISION_TRACE_EMITTED fails to persist because the emitted payload contains trend_run_length while the registered schema forbids extra properties and does not define that field.
- Because validation happens before dispatch and before any shadow journal capture, the entire trace event disappears.
- The exact allow or deny rationale is therefore lost at the decision-trace boundary.
- Rejected decisions retain only a partial fallback through ORDER_REJECTED with nrr_code and short why.
- Accepted decisions have no equivalent fallback, so their exact allow rationale is not persisted anywhere proven in repo scope.
- Even if the schema mismatch were removed, the trace contract would still be audit-weak because it omits rid and lifecycle_id and carries only a compact why string while full why_chain lives in non-payload metadata.

Closure status: The strongest proven root seam is the schema mismatch on trend_run_length. The strongest proven auditability asymmetry is that DENY has a partial ORDER_REJECTED mirror while ALLOW has no equivalent rationale mirror.
