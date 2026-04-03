# Bucket D DOGEUSDT Post-Watchdog Internal Sub-Hop Micro-Forensic - 2026-04-01

## 1. Executive Verdict
FACT: The current micro-forensic scope is limited to the 7 Bucket D DOGEUSDT mean_reversion rows already proven to have websocket FILLED, websocket correlation miss, watchdog POLLING DETECTED FILL, and later ORPHANED_TTL.

FACT: The deepest per-RID runtime-proven reached point inside the requested chain is the watchdog fill branch itself, evidenced by the POLLING DETECTED FILL line for each row.

FACT: Global startup logs prove the watchdog hooks were connected before these rows occurred:
- logs/domain_execution_position.log.2:16-17
- logs/aurora_core.log.39:58-59

FACT: No per-RID runtime artifact proves crossing from the watchdog fill branch into any later requested sub-hop: no proven emit_fn invocation, no proven emit_trade_executed entry, no proven emit_compat entry, no proven FSMCore.emit entry, and no proven shadow_journal.record_bus_emit execution.

FACT: No runtime markers were found for the failure branches that would normally expose later-chain reachability problems:
- no Failed to emit EVT:TRADE_EXECUTED
- no emit_compat failed
- no FSM has no 'emit' method
- no Payload validation failed for EVT:TRADE_EXECUTED
- no Schema validation system error for EVT:TRADE_EXECUTED
- no Shadow journal emit capture failed for EVT:TRADE_EXECUTED
- no TRADE_EXECUTED hardening failed open
- no Suppressed duplicate EVT:TRADE_EXECUTED

INFERENCE: Among the user-proposed alternatives, the strongest supported answer is closest to watchdog never invoking emit_fn, with the more precise evidence-bounded wording: no runtime proof shows execution crossed the watchdog callsite into emit_trade_executed for any of the 7 rows.

INFERENCE: The earliest proven missing internal sub-hop is watchdog fill branch -> emit_fn invocation.

UNKNOWN: The current artifacts do not prove whether the miss was caused by emit_fn being falsey, an exception during fill_payload assembly, cancellation/interruption before the awaited call, or another uninstrumented pre-wrapper branch.

## 2. Expected Internal Sub-Hop Map
FACT: The expected code-path inside scope is:
1. watchdog fill branch entered
2. emit_fn truthy and invoked
3. emit_trade_executed wrapper entered
4. emit_compat entered
5. FSMCore.emit(Message) entered
6. shadow_journal.record_bus_emit executed

| sub-hop | code contract | runtime artifact expected if reached | current evidence |
|---|---|---|---|
| watchdog fill branch entered | watchdog.py logs POLLING DETECTED FILL after status in (FILLED, PARTIALLY_FILLED) and executed_qty > 0 | watchdog fill log | FACT: Yes for all 7 rows |
| emit_fn bound | watchdog.py only assigns emit_fn at init None and set_hooks(); startup logs prove set_hooks executed globally | startup hook-binding logs | FACT: Yes globally; UNKNOWN per RID at call moment |
| emit_fn invoked | watchdog.py calls await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload) if self.emit_fn | direct entry log does not exist; downstream wrapper/journal/error markers should appear if call succeeds | FACT: No per-RID runtime proof |
| emit_trade_executed entered | fsm.py builds Message and calls emit_compat(self.fsm, msg, logger=LOG) | wrapper entry log, wrapper failure log, or downstream journal/validation markers | FACT: No per-RID runtime proof |
| emit_compat entered | fsm_emit_compat.py first tries emit(msg), then fallbacks only on failure | emit_compat failure/fallback logs if compatibility breaks | FACT: No per-RID runtime proof |
| FSMCore.emit(Message) entered | fsm_core.py accepts Message directly, normalizes payload, validates schema, then journals bus ingress | either EVT:TRADE_EXECUTED journal event or EVT:TRADE_EXECUTED validation/failure log | FACT: No per-RID runtime proof |
| shadow_journal.record_bus_emit executed | fsm_core.py calls record_bus_emit before hardening and listeners | shadow_critical_event_journal_v1.jsonl event record for EVT:TRADE_EXECUTED | FACT: No per-RID runtime proof |

FACT: emit_compat first-hop compatibility is deterministic for a valid FSMCore bus because FSMCore.emit accepts Message directly.

INFERENCE: If execution had reached emit_trade_executed with the expected FSMCore object, later proof should normally have appeared as either journal ingress or explicit failure logs.

## 3. RID-by-RID Internal Sub-Hop Matrix
FACT: In this matrix, emit_fn_bound_code_yes_no = Yes means code-bound plus startup-proven global hook connection. It is not proof of per-event invocation.

FACT: proof_grade = Moderate means the watchdog anchor and later contract gap are well supported, but the exact cause inside the pre-wrapper window is not directly instrumented.

| rid | watchdog_fill_anchor | emit_fn_bound_code_yes_no | runtime_emit_fn_invocation_proven_yes_no | runtime_emit_trade_executed_entry_proven_yes_no | runtime_emit_compat_entry_proven_yes_no | runtime_fsm_core_emit_entry_proven_yes_no | runtime_record_bus_emit_proven_yes_no | earliest_internal_missing_subhop | strongest_supported_explanation | proof_grade | remaining_unknowns |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rid-4c44c9b4e85b0009 | logs/aurora_core.log.35:1891 order=762701737 @ 2026-03-31 00:25:04,680 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-2aec3be5c5b62d7d | logs/aurora_core.log.34:29717 order=762784661 @ 2026-03-31 02:05:06,562 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-d866f7ca1e390571 | logs/aurora_core.log.32:19915 order=762849386 @ 2026-03-31 03:50:02,278 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-9e015bd410455284 | logs/aurora_core.log.29:3362 order=762995235 @ 2026-03-31 06:25:05,797 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-e5adcc2a7d67ffcb | logs/aurora_core.log.26:4664 order=763146229 @ 2026-03-31 09:25:06,402 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-d8cebaa4f1499864 | logs/aurora_core.log.26:26040 order=763184591 @ 2026-03-31 09:55:03,563 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |
| rid-cc0c2230ed591c29 | logs/aurora_core.log.24:20572 order=763343279 @ 2026-03-31 11:45:05,360 | Yes | No | No | No | No | No | watchdog fill branch -> emit_fn invocation | No runtime proof crosses the watchdog callsite into the wrapper chain; later failure contracts are absent | Moderate | emit_fn falsey vs fill_payload-build exception vs interruption before wrapper entry |

## 4. Runtime Artifact Findings
FACT: The 7 rows have the expected pre-gap watchdog anchors already established in the earlier boundary report:
- websocket FILLED exists
- websocket correlation miss exists
- watchdog POLLING DETECTED FILL exists

FACT: For these 7 identities, shadow_critical_event_journal_v1.jsonl contains ORDER_INDEX and EVT:ORDER_PLACED records, proving that the journal subsystem and identity extraction were active for the same rows.

FACT: For these 7 identities, shadow_critical_event_journal_v1.jsonl contains no EVT:TRADE_EXECUTED record keyed by rid, order_id, or client_order_id.

FACT: Searches across logs found no per-order polling error markers for these 7 rows:
- no Error polling order 762701737
- no Error polling order 762784661
- no Error polling order 762849386
- no Error polling order 762995235
- no Error polling order 763146229
- no Error polling order 763184591
- no Error polling order 763343279
- no Error in REST polling

FACT: Searches across logs found no later-chain failure markers for EVT:TRADE_EXECUTED in the relevant runtime set:
- no Failed to emit EVT:TRADE_EXECUTED
- no emit_compat failed
- no FSM has no 'emit' method
- no Payload validation failed for EVT:TRADE_EXECUTED
- no Schema validation system error for EVT:TRADE_EXECUTED
- no Shadow journal emit capture failed for EVT:TRADE_EXECUTED
- no TRADE_EXECUTED hardening failed open
- no Suppressed duplicate EVT:TRADE_EXECUTED

FACT: The same logs do contain validation failures for other events, especially EVT:ACCOUNT_UPDATE_RECEIVED, proving that this runtime does expose validation failures when they happen.

INFERENCE: The absence of EVT:TRADE_EXECUTED-specific failure markers weakens the case for a later failure after successful wrapper entry.

## 5. Hook Binding vs Runtime Use
FACT: Startup logs prove the intended hook wiring existed globally before the 7 rows:
- logs/domain_execution_position.log.2:16 = OrderTimeoutWatchdog REST polling hooks connected
- logs/domain_execution_position.log.2:17 = Watchdog REST polling hooks connected to adapter functions
- mirrored in logs/aurora_core.log.39:58-59

FACT: In watchdog.py, the only local assignments to emit_fn are:
- self.emit_fn = None at initialization
- self.emit_fn = emit_fn inside set_hooks()

FACT: This proves the runtime was configured for the intended watchdog -> wrapper path at startup.

UNKNOWN: No per-RID runtime artifact proves that self.emit_fn remained truthy and was actually invoked at each of the 7 watchdog fill moments.

FACT: A contrast DOGE control shows why hook binding must not be confused with runtime use. For rid-d38a93e3c667b0d7 / order 763098610:
- logs/aurora_core.log.28:31375-31380 show websocket ORDER FILLED, websocket Emitting EVT:TRADE_EXECUTED, and Handling EVT:TRADE_EXECUTED at 08:05:01.xxx
- shadow_critical_event_journal_v1.jsonl:16275-16278 shows websocket EVT:TRADE_EXECUTED and downstream portfolio truth at ts_ms 1774933501365-1774933501447
- logs/aurora_core.log.28:31403 shows a later watchdog POLLING DETECTED FILL at 08:05:02,816

INFERENCE: Coexistence of watchdog fill logs and downstream EVT:TRADE_EXECUTED artifacts elsewhere is not proof that the watchdog-origin chain succeeded. The DOGE control demonstrates that websocket truth can already be durable before a later watchdog poll observes the same order.

## 6. Earliest Proven Missing Internal Sub-Hop
FACT: For all 7 rows, the deepest runtime-proven reached point is the watchdog POLLING DETECTED FILL line inside the FILLED/PARTIALLY_FILLED branch.

FACT: Immediately after that log, the next scoped internal work is:
1. build fill_payload
2. evaluate if self.emit_fn
3. await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)

FACT: No runtime artifact proves crossing from that watchdog point into any later scoped hop.

FACT: Later hypotheses are less supported by contract:
- if FSMCore.emit had been reached and succeeded, record_bus_emit should have written an EVT:TRADE_EXECUTED journal record before listeners
- if FSMCore.emit had been reached and validation failed, EVT:TRADE_EXECUTED validation errors should have appeared
- if emit_trade_executed had raised around emit_compat, Failed to emit EVT:TRADE_EXECUTED should have appeared

INFERENCE: The earliest proven missing internal sub-hop is watchdog fill branch -> emit_fn invocation.

UNKNOWN: The current artifacts do not distinguish whether the miss occurred before evaluating if self.emit_fn, during fill_payload assembly, or during an uninstrumented step between the watchdog line and wrapper entry.

## 7. Strongest Supported Explanation
FACT: ExecPosFSM production wiring is fail-closed: outside shadow_mode it requires an FSM-like object with listen and emit, otherwise startup raises BUS-FAILCLOSED-01 instead of silently falling back to LocalBus.

FACT: The watchdog wrapper in fsm.py constructs a Message and calls emit_compat(self.fsm, msg, logger=LOG).

FACT: emit_compat first tries emit(msg), and FSMCore.emit directly supports Message input.

FACT: FSMCore.emit normalizes EVT:TRADE_EXECUTED, runs schema validation, then calls shadow_journal.record_bus_emit before hardening and before listeners.

FACT: No evidence was found for any of the failure contracts that would normally appear if the chain had already reached emit_trade_executed, emit_compat, or FSMCore.emit but then failed.

INFERENCE: The strongest supported explanation is that the 7 rows never achieved a runtime-proven successful crossing past the watchdog callsite into emit_trade_executed. In practical terms, the loss is best localized at or before emit_fn invocation, not deeper inside emit_compat, FSMCore.emit, or record_bus_emit.

UNKNOWN: This is still an evidence-bounded inference, not a direct proof that emit_fn was definitively skipped.

## 8. Plausible but Unproven Internal Failure Modes
UNKNOWN: self.emit_fn may have been falsey at one or more watchdog fill moments despite the earlier startup binding.

UNKNOWN: An exception may have occurred during fill_payload assembly after the watchdog log but before the awaited emit_fn call. The current code would route that through Error polling order ..., but no such per-order marker was found in the inspected logs.

UNKNOWN: Task cancellation or interruption may have occurred between the watchdog log and the awaited emit_fn call without leaving a scoped artifact in the current logs.

UNKNOWN: emit_trade_executed may have been entered but failed before a visible failure marker was flushed. This is lower support because the expected failure logs are absent.

UNKNOWN: self.fsm may have been replaced or altered after startup, making emit_compat behavior diverge from the expected FSMCore path. This is very low support because production wiring is fail-closed and no emit_compat or bus capability errors were found.

## 9. What Additional Instrumentation Would Close The Gap
FACT: One info-level trace immediately before the watchdog callsite would close the first ambiguity:
- order_id
- client_order_id
- rid
- emit_fn_is_set
- about_to_emit_trade_executed=true

FACT: One info-level trace at emit_trade_executed entry would close the second ambiguity:
- order_id
- client_order_id
- rid
- why
- payload keys

FACT: One trace inside emit_compat before and after emit(msg) would close the compatibility ambiguity:
- fsm_type
- branch=message_api
- success_or_exception

FACT: One trace at the start of FSMCore.emit for EVT:TRADE_EXECUTED, before schema validation and before record_bus_emit, would close the bus-entry ambiguity.

FACT: One explicit watchdog error log around fill_payload assembly, promoted above debug for this path, would distinguish payload-build failure from emit_fn non-invocation.

INFERENCE: Any one of the first two traces would likely be sufficient to determine whether the true miss is emit_fn non-invocation or a deeper pre-journal wrapper failure.
