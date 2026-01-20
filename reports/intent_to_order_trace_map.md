# Intent-to-Order Trace Map (INTENT-TO-ORDER-TRACE-SSOT-01)

**Date**: 2026-01-13
**Status**: Forensic Analysis Complete

---

## Executive Summary

**Primary Finding**: Intent-to-order chain is BROKEN at EntryPlan validation stage.

The issue is NOT observability — it's that **signals are rejected before reaching `_propose_trade_intent`** due to missing ATR data in signal payloads.

---

## 1. Stage-by-Stage Trace Map

| Stage | Verb/Event | Persistent? | File/Line Writer | Evidence (2026-01-13) |
|-------|-----------|-------------|------------------|----------------------|
| 1. Strategy emits signal | `EVT:STRATEGY_SIGNAL_PRODUCED` | ❌ No | Not persisted | N/A |
| 2. Gateway log | "All gates passed" | ✅ Log only | [decision_making.py#L963](../apps/reference/domains/decision_making/decision_making.py#L963) | 5+ occurrences |
| 3. EntryPlan validation | `ENTRY_PLAN_ATR_NOT_READY` | ✅ Log only | [decision_making.py#L1017](../apps/reference/domains/decision_making/decision_making.py#L1017) | **5+ occurrences** ← BREAKPOINT |
| 4. Intent rejected | `EVT:TRADE_INTENT_REJECTED` | ✅ WAL + Log | [trade_intent_reject_wal.py](../apps/reference/domains/decision_making/trade_intent_reject_wal.py) | **1417 in WAL** |
| 5. Intent proposed | `EVT:TRADE_INTENT_PROPOSED` | ✅ WAL (code exists) | [decision_making.py#L3165](../apps/reference/domains/decision_making/decision_making.py#L3165) | **0 in WAL** ← NOT REACHED |
| 6. Bridge→ExecPos | `DEC:OPEN` | ✅ WAL | [fsm.py#L1685](../apps/reference/domains/execution_position/fsm.py#L1685) | 8 in WAL |
| 7. Adapter call | `adapter.place_market_entry` | ❌ Not persisted | [fsm.py#L2597](../apps/reference/domains/execution_position/fsm.py#L2597) | Log only |
| 8. Order placed | `ORDER_PLACED` | ✅ order_log (not WAL) | [fsm.py#L2665](../apps/reference/domains/execution_position/fsm.py#L2665) | **0 in order_log** |
| 9. Order rejected | `EVT:ORDER_REJECTED` | ❌ Not in WAL | Not implemented | 0 in WAL |

---

## 2. Critical Breakpoint Analysis

### Breakpoint: Stage 3 (EntryPlan ATR Validation)

**Log Evidence**:
```
2026-01-13 20:40:00,702 - [SOLUSDT] STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED
2026-01-13 20:40:00,702 - [SOLUSDT] STRATEGY_SIGNAL_GATEWAY: REJECT - EntryPlan validation failed: ENTRY_PLAN_ATR_NOT_READY
```

**Root Cause**: MR signal payloads do NOT include `volatility.atr_ready` field.

**Fix Applied**: P0-1 in `dm_strategy_ssot_implement_01.md` — MR now propagates volatility/liquidity.

---

## 3. WAL Counts (2026-01-13)

```
 11475 EVT:ACCOUNT_UPDATE_RECEIVED
  3085 EVT:BAR_CLOSED
  1417 EVT:TRADE_INTENT_REJECTED    ← All intents blocked before PROPOSED
     8 DEC:OPEN                     ← From bridge (manual/other source?)
     4 DEC:CLOSE
     0 EVT:TRADE_INTENT_PROPOSED    ← NEVER written (not reached)
     0 EVT:ORDER_PLACED             ← Not in WAL (only in order_log)
```

---

## 4. order_log_v1.jsonl Counts

```
     3 ORDER_REJECTED (by DecisionMaking safety gates)
     0 ORDER_PLACED
```

---

## 5. Observability Gaps Identified

### Gap A: `EVT:ORDER_PLACED` NOT in WAL

- **Current**: Written to `order_log_v1.jsonl` only
- **Problem**: WAL is SSOT for event replay; order_log is secondary
- **Impact**: WAL replay won't see order placements

### Gap B: `EVT:ORDER_REJECTED` (adapter failure) NOT implemented

- **Current**: No emit when adapter fails
- **Problem**: Silent failure; no evidence in WAL or logs
- **Impact**: Can't trace why order didn't reach exchange

### Gap C: No `EVT:TRADE_INTENT_PROPOSED` when EntryPlan rejects

- **Current**: Goes straight to `EVT:TRADE_INTENT_REJECTED`
- **Actually Correct**: This is fail-closed behavior ✅
- **Improvement**: Add ATR-ready check earlier in pipeline

---

## 6. RID Trace for DEC:OPEN (8 events)

```bash
# Extract RIDs from DEC:OPEN in WAL
grep '"verb":"OPEN"' ops/wal/2026-01-13.jsonl | jq -r '.rid' | head -5
```

Sample RID trace needed to verify full chain.

---

## 7. Recommended Fixes (Observability)

### B1: Emit `EVT:ORDER_PLACED` to WAL (not just order_log)

**File**: [fsm.py#L2665](../apps/reference/domains/execution_position/fsm.py#L2665)

After `order_logger.write()`, add:
```python
wal.append({
    "op": "EVT",
    "verb": "ORDER_PLACED",
    "rid": decision.rid,
    "pld": {...},
    "src": "execution_position",
    ...
})
```

### B2: Emit `EVT:ORDER_REJECTED` on adapter failure

**File**: `fsm.py` in `_execute_decision` exception handler

```python
except Exception as e:
    reject_msg = Message(
        op="EVT",
        verb="ORDER_REJECTED",
        src="execution_position",
        rid=decision.rid,
        pld={"reason": str(e), "symbol": symbol, ...},
    )
    wal.append(reject_msg.model_dump())
    order_logger.write({"event_type": "ORDER_REJECTED", ...})
```

### B3: order_log boot record

Create file on startup with header:
```python
if not log_file.exists():
    order_logger.write({"event_type": "BOOT", "ts_ms": time.time() * 1000})
```

---

## 8. Verification Commands

```bash
# WAL verb counts
python3 -c "
import json
with open('ops/wal/2026-01-13.jsonl') as f:
    verbs = {}
    for line in f:
        r = json.loads(line)
        key = f\"{r.get('op','')}:{r.get('verb','')}\"
        verbs[key] = verbs.get(key, 0) + 1
for k,v in sorted(verbs.items(), key=lambda x: -x[1])[:20]:
    print(f'{v:6d} {k}')
"

# order_log event types
python3 -c "
import json
with open('logs/order_log_v1.jsonl') as f:
    for line in f:
        print(json.loads(line).get('event_type'))
"

# EntryPlan rejects
grep "ENTRY_PLAN_ATR_NOT_READY" logs/aurora_core.log* | wc -l
```

---

## 9. Conclusions

| Question | Answer |
|----------|--------|
| Does `EVT:TRADE_INTENT_PROPOSED` persist in WAL? | ✅ Code exists, but **0 events** (not reached due to ATR reject) |
| Does `EVT:ORDER_PLACED` persist in WAL? | ❌ **NO** — only in order_log |
| Where is the breakpoint? | **EntryPlan ATR validation** — MR signals missing `volatility.atr_ready` |
| Is this observability gap or execution gap? | **Both**: Execution blocked + observability incomplete |

---

*Generated by INTENT-TO-ORDER-TRACE-SSOT-01 forensic phase*
