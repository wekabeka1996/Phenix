# AGENT_REPORT_V1

## Executive Summary
Current inspected runtime evidence says the visible "trend conflict" storm is primarily real decision-layer safety-gate denial, not a hidden stale-long or open-order conflict. Separate execution/exposure blocker families do exist, but they surface with different codes, different logs, and different symbols.

## Proven Facts
- DecisionMaking invokes safety gates before intent building at apps/reference/domains/decision_making/decision_making.py:312.
- The human-readable strings in question are emitted directly by safety gates:
  - apps/reference/domains/decision_making/safety_gates.py:211 -> "downtrend blocks long"
  - apps/reference/domains/decision_making/safety_gates.py:213 -> "uptrend blocks short"
  - apps/reference/domains/decision_making/safety_gates.py:267 -> "price_motion flash insufficient"
  - apps/reference/domains/decision_making/safety_gates.py:275 -> "flash up blocks short"
  - apps/reference/domains/decision_making/safety_gates.py:280 -> "bleed down blocks long"
- The authoritative code mapping is:
  - apps/reference/domains/decision_making/normalized_reject_reasons.py:48 -> NRR-026
  - apps/reference/domains/decision_making/normalized_reject_reasons.py:49 -> NRR-027
  - apps/reference/domains/decision_making/normalized_reject_reasons.py:50 -> NRR-028
  - apps/reference/domains/decision_making/normalized_reject_reasons.py:51 -> NRR-029
  - apps/reference/domains/decision_making/normalized_reject_reasons.py:52 -> NRR-030
- Order-in-flight is a separate mechanism in intent construction, not a trend gate:
  - apps/reference/domains/decision_making/intent_builder.py:144 uses order_index.try_reserve_entry(symbol, rid)
  - apps/reference/domains/decision_making/intent_builder.py:148 logs TRADE_INTENT_DEFERRED: NRR-ORDER-IN-FLIGHT
- Position/exposure-side conflict handling is a separate execution-position mechanism:
  - apps/reference/domains/execution_position/exposure_manager.py:66 initializes is_flip
  - apps/reference/domains/execution_position/exposure_manager.py:77 sets is_flip=True for opposite-side live position
  - apps/reference/domains/execution_position/exposure_manager.py:82 calls exposure_guard.can_open(..., is_flip=is_flip)
  - apps/reference/domains/execution_position/exposure_manager.py:113 logs EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED
- Venue-side maker-only rejection is a separate execution-stage family:
  - apps/reference/domains/execution_position/open_executor.py:362 logs MAKER_ONLY_REJECT
  - apps/reference/domains/execution_position/open_executor.py:365 writes ORDER_REJECTED with NRR-018
- Canonical order log dominance in the inspected window from logs/order_log_v1.jsonl:
  - NRR-027 = 42 rejects
  - NRR-029 = 7 rejects
  - NRR-028 = 2 rejects
  - NRR-026 = 2 rejects
  - NRR-018 = 1 reject
  - NRR-030 = 1 reject
- By symbol in the same inspected window from logs/order_log_v1.jsonl:
  - SOLUSDT NRR-027 = 15
  - ETHUSDT NRR-027 = 14
  - BNBUSDT NRR-027 = 9
  - ETHUSDT NRR-029 = 5
  - XRPUSDT NRR-027 = 4
  - SOLUSDT NRR-029 = 2
- Source ownership in the same inspected window from logs/order_log_v1.jsonl:
  - DecisionMaking owns all NRR-026/027/028/029/030 rejects in the canonical order log
  - ExecPosFSM owns the single NRR-018 maker-only reject
- Successful placements exist in the same inspected window:
  - DOGEUSDT ORDER_PLACED in logs/order_log_v1.jsonl:15
  - XRPUSDT ORDER_PLACED in logs/order_log_v1.jsonl:64
- In the inspected runtime logs, explicit exposure fail-closed rejects were observed for 1000PEPEUSDT, not for BTCUSDT, ETHUSDT, or SOLUSDT:
  - logs/domain_execution_position.log:7964
  - logs/domain_execution_position.log:8018
  - logs/domain_execution_position.log:8130
  - logs/domain_execution_position.log:8289
  - logs/domain_execution_position.log:8328
  - logs/domain_execution_position.log:8387
- In the inspected runtime logs, NRR-ORDER-IN-FLIGHT and order_in_flight matches were zero.
- In the inspected runtime logs, BTCUSDT, ETHUSDT, and SOLUSDT had zero matches for:
  - EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED
  - NRR-ORDER-IN-FLIGHT
  - order_in_flight
  - EXTERNAL_OPEN_REJECTED
  - IntentBoundaryAudit terminal reject

## Inferred Findings
- The current user-visible "trend conflict" phrases are true decision-layer safety-gate messages with direct code provenance, not aliases for stale position state.
- The dominant blocker family in the inspected window is directional sanity, especially short attempts denied against an UP regime/trend on ETHUSDT and SOLUSDT.
- ETHUSDT and SOLUSDT suppression in the current inspected window is primarily upstream of execution. The denial happens before order placement, exposure routing, or venue submission.
- The stale-long or open-order hypothesis is not supported for BTCUSDT, ETHUSDT, or SOLUSDT in the inspected runtime window. This is a bounded inference based on the logs inspected, not a project-wide impossibility claim.
- BNBUSDT shows a mixed picture:
  - most BNBUSDT suppression in the canonical order log is still NRR-027 decision-layer denial
  - one BNBUSDT case does pass guards, reaches execution, and then fails as maker-only venue reject NRR-018
- 1000PEPEUSDT demonstrates that execution-position conflicts are real in this system, but when they happen they are explicit and materially different from the trend-conflict family.
- IntentBoundaryAudit terminal rejects are a downstream observability symptom that can follow an execution/external rejection path. They should not be treated as the root blocker when an earlier concrete reject already exists.

## Contradictions / Evidence Gaps
- No evidence in the inspected window shows ETHUSDT or SOLUSDT trend-conflict cases caused by a stale long, stale open order, or exposure fail-closed branch.
- This audit is bounded to the inspected runtime artifacts and current visible log window. It is not proof about all historical sessions.
- The absence of NRR-ORDER-IN-FLIGHT or exposure markers in the inspected ETHUSDT/SOLUSDT/BTCUSDT window does not prove those families never occur. It proves they were not found in the inspected evidence set.
- Some aurora_trades.log lines collapse different downstream outcomes into generic guard/boundary wording. That wording is less specific than order_log_v1.jsonl and domain_execution_position.log.

## Root Cause Candidates
- Primary observed root cause family for current suppression:
  - DecisionMaking directional sanity deny, where intent side opposes computed trend direction with sufficient confidence.
- Secondary observed root cause family:
  - DecisionMaking price-motion deny, where recent flash or bleed metrics oppose the attempted side.
- Tertiary observed root cause family:
  - Execution venue reject for maker-only GTX placement, observed on BNBUSDT.
- Separate but not dominant in the inspected ETH/SOL/BTC storm:
  - Execution-position exposure fail-closed soft limit below clip minimum, observed on 1000PEPEUSDT.

## Operational Risk
- Runtime
- Correctness
- Observability Gap

## Blocker Taxonomy
| blocker_family | code_or_event | domain_owner | stage | depends_on_position_state | depends_on_regime_state | depends_on_price_motion | observed_runtime_evidence | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regime confidence gate | NRR-026 | DecisionMaking | pre-intent safety gate | No direct evidence | Yes | No | logs/order_log_v1.jsonl:2,4 | True directional/regime gate |
| Directional sanity gate | NRR-027 | DecisionMaking | pre-intent safety gate | No direct evidence | Yes | Indirect only through trend build | logs/order_log_v1.jsonl:5,6 and dominant counts | True directional gate |
| Price-motion readiness gate | NRR-028 | DecisionMaking | pre-intent safety gate | No | No | Yes | logs/order_log_v1.jsonl:11,12 | True price-motion gate |
| Flash motion gate | NRR-029 | DecisionMaking | pre-intent safety gate | No | No | Yes | logs/order_log_v1.jsonl:9 and ETH/SOL counts | True price-motion gate |
| Bleed motion gate | NRR-030 | DecisionMaking | pre-intent safety gate | No | No | Yes | logs/order_log_v1.jsonl:16 | True price-motion gate |
| One-open-order CAS guard | NRR-ORDER-IN-FLIGHT | DecisionMaking plus OrderIndex | intent build | Yes | No | No | zero hits in inspected logs | Separate hidden-state family exists in code, not observed here |
| Exposure fail-closed | EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED and EXTERNAL_OPEN_REJECTED | ExecutionPosition | post-intent / pre-placement | Yes | No | No | logs/domain_execution_position.log:7964,8018,8130,8289,8328,8387 | Explicit position/exposure family |
| Venue maker-only reject | NRR-018 / MAKER_ONLY_REJECT | ExecPosFSM / venue | placement | No proven dependency | No | No | logs/order_log_v1.jsonl:56 and logs/domain_execution_position.log:8429 | Explicit execution/venue family |
| Boundary terminal reject | NRR-EXECUTION-NO-DOWNSTREAM-EVENT / trade_intent_boundary_audit | IntentBoundaryAudit | downstream observability | Mixed | Mixed | Mixed | logs/domain_execution_position.log:8431 and multiple 1000PEPEUSDT lines | Symptom/terminal wrapper, not root cause by itself |

## Incident Timelines
### Incident 1: BTCUSDT regime-confidence deny
- 2026-03-21 01:30:01.769: DecisionMaking processes SELL signal rid=aurora_BTCUSDT_1774049401766 in logs/domain_decision_making.log.1:10076.
- 2026-03-21 01:30:01.773: Canonical reject recorded as ORDER_REJECTED NRR-026 with why="SAFETY_GATES:FIX-CONF-GATE-01: regime_confidence=0.4013297485171084 < min=0.42" in logs/order_log_v1.jsonl:4.
- Proven stage: pre-intent decision safety gate.

### Incident 2: ETHUSDT directional-sanity deny
- 2026-03-21 02:50:02.140: DecisionMaking processes SELL signal rid=aurora_ETHUSDT_1774054202136 in logs/domain_decision_making.log.1:14458.
- 2026-03-21 02:50:02.143: Canonical reject recorded as ORDER_REJECTED NRR-027 with why="SAFETY_GATES:uptrend blocks short" in logs/order_log_v1.jsonl:5.
- Proven stage: pre-intent decision safety gate.
- No inspected evidence for order-in-flight, exposure fail-closed, or boundary reject on this ETHUSDT case.

### Incident 3: ETHUSDT flash-motion deny
- 2026-03-21 03:35:00.420: DecisionMaking processes SELL signal rid=aurora_ETHUSDT_1774056900416 in logs/domain_decision_making.log.1:16921.
- 2026-03-21 03:35:00.427: Canonical reject recorded as ORDER_REJECTED NRR-029 with why="SAFETY_GATES:flash up blocks short" in logs/order_log_v1.jsonl:9.
- Proven stage: pre-intent decision safety gate.
- This is price-motion conflict, not position-state conflict.

### Incident 4: SOLUSDT directional-sanity deny
- 2026-03-21 03:05:03.121: DecisionMaking processes SELL signal rid=aurora_SOLUSDT_1774055103119 in logs/domain_decision_making.log.1:15273.
- 2026-03-21 03:05:03.123: Canonical reject recorded as ORDER_REJECTED NRR-027 with why="SAFETY_GATES:uptrend blocks short" in logs/order_log_v1.jsonl:6.
- Proven stage: pre-intent decision safety gate.
- No inspected evidence for order-in-flight, exposure fail-closed, or boundary reject on this SOLUSDT case.

### Incident 5: BNBUSDT mixed chain, execution reject after passing guards
- 2026-03-21 09:45:05.614: DecisionMaking processes SELL signal rid=mdamr-928db2e77a75188e in logs/domain_decision_making.log:14104.
- 2026-03-21 09:45:05.663: Execution open guard passes in logs/domain_execution_position.log:8421.
- 2026-03-21 09:45:05.709: Canonical ORDER_INTENT is written in logs/order_log_v1.jsonl:55.
- 2026-03-21 09:45:06.437: open_executor logs MAKER_ONLY_REJECT code=-5022 for BNBUSDT in logs/domain_execution_position.log:8429.
- 2026-03-21 09:45:06.438: Canonical reject recorded as ORDER_REJECTED NRR-018 why="MAKER_ONLY_REJECT" in logs/order_log_v1.jsonl:56.
- 2026-03-21 09:45:10.996: IntentBoundaryAudit emits terminal wrapper reject NRR-EXECUTION-NO-DOWNSTREAM-EVENT in logs/domain_execution_position.log:8431.
- Proven interpretation: root cause is venue maker-only reject; boundary reject is downstream symptom.

### Incident 6: 1000PEPEUSDT explicit exposure-family reject
- 2026-03-21 09:04:43.535: exposure_manager logs EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED rid=5b63d068-84a9-4d9e-a0bb-8ef4498dc93a symbol=1000PEPEUSDT side=SELL reason=SOFT_LIMIT_BELOW_CLIP_MIN in logs/domain_execution_position.log:7964.
- 2026-03-21 09:04:43.548: intent_router logs EXTERNAL_OPEN_REJECTED reason=exposure_fail_closed_soft_limit_below_clip_min in logs/domain_execution_position.log:7967.
- 2026-03-21 09:04:48.795: IntentBoundaryAudit emits terminal wrapper reject in logs/domain_execution_position.log:7969.
- Proven interpretation: this is what a real position/exposure execution-family block looks like in current logs. It is explicit and not mislabeled as NRR-027/029/030.

### Control Case: XRPUSDT placement reached venue and fill detection
- 2026-03-21 10:15:01.616: DecisionMaking processes BUY signal rid=mdamr-d84a14505de9a852 in logs/domain_decision_making.log:15780.
- 2026-03-21 10:15:01.708: execution guard passes in logs/domain_execution_position.log:8796.
- 2026-03-21 10:15:01.774: canonical ORDER_INTENT recorded in logs/order_log_v1.jsonl:63.
- 2026-03-21 10:15:02.391: open_executor logs successful LIMIT placement for order_id=1567523345 in logs/domain_execution_position.log:8805.
- 2026-03-21 10:15:02.457: canonical ORDER_PLACED recorded in logs/order_log_v1.jsonl:64.
- 2026-03-21 10:16:05.127: watchdog logs detected fill for order 1567523345 in logs/domain_execution_position.log:8818.
- Proven interpretation: when a case passes gates and execution, the system does produce normal downstream order placement and fill evidence.

## Files / Areas Touched
- REPORT_BLOCKERS_GATES_AND_TREND_CONFLICT_FORENSIC.md

## Validation Performed
- Read SSOT/reporting protocol files:
  - docs/ai/LLM_REASONING_CONSTITUTION.md
  - docs/ai/AGENT_REPORT_SCHEMA.md
  - docs/ai/DONE_CRITERIA.md
- Read code paths for decision, intent, exposure, and execution ownership.
- Queried logs/order_log_v1.jsonl for reject counts and placements.
- Queried runtime logs for explicit exposure, in-flight, maker-only, and boundary markers.
- Reconstructed incident chains across BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, 1000PEPEUSDT, and XRPUSDT.

## Residual Risk
- Operators can still misread boundary/audit wrapper events as root cause if they do not correlate them back to canonical order log and domain-specific logs.
- If there are older rotated logs outside the inspected window, some historical counterexample could exist. That remains unproven here.
- The system currently exposes multiple blocker families across different logs with unequal specificity, which increases forensic ambiguity during live ops.

## What Remains Unproven
- Whether any historical ETHUSDT or SOLUSDT trend-conflict case outside the inspected window was actually downstream of stale position or stale order state.
- Whether every trade_intent_boundary_audit wrapper always has a unique earlier root reject. That was not exhaustively proven for all nine boundary events.
- Whether current documentation fully explains the operator-facing difference between safety-gate rejects and execution/exposure rejects.

## Minimal Safe Verdict
For the inspected runtime window, treat:
- "uptrend blocks short" and "downtrend blocks long" as genuine directional safety-gate denies.
- "flash up blocks short", "bleed down blocks long", and "price_motion flash insufficient" as genuine price-motion safety-gate denies.
- execution-position conflicts as a separate family that currently appears explicitly as exposure_fail_closed or maker-only rejection, not as NRR-027/029/030.

The current hypothesis "the system thinks a long is already open, therefore it logs trend conflict" is not supported by the inspected evidence for BTCUSDT, ETHUSDT, or SOLUSDT.
