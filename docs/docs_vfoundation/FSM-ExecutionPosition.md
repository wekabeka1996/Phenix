# FSM Execution Position — 3 Flow Specification (FSMP-P1-T02)

**Status**: Shadow-mode (stub logic, no live API calls)  
**Domain**: `execution_position`  
**Flows**: `open_flow`, `manage_flow`, `close_flow`  
**Coverage**: ≥90% (unit + e2e)  
**Latency Target**: p95 ≤ 25ms (FSM decisions), p95 ≤ 50ms (overall)

---

## Architecture Overview

```
CMD:OPEN → OpenFlowFSM → DEC:OPEN → ACL-stub → EVT:ORDER_PLACED
                ↓                                      ↓
              WAL                                  WAL
                
EVT:FILL → ManageFlowFSM → DEC:ADJUST (trail/BE/time)
              ↓
            WAL

EVT:REJECTED/EXPIRED → CloseFlowFSM → DEC:CLOSE(reduce_only=true)
                           ↓
                         WAL
```

**Key Principles**:
- **Shadow-mode**: all decisions logged to WAL, but no live orders
- **Fail-closed**: guard failures → ERR, no DEC emission
- **Idempotency**: duplicate CMD with same `idempotent_key` → dedup
- **WHY-discipline**: all messages `why ≤ 80 chars`
- **Metrics**: exported via `/metrics` (p95 latency, decision counts)

---

## Flow 1: Open Flow

### States

```
IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
                              ↓
                           ERROR (guard fail)
```

### Inputs

- **CMD:OPEN**: `symbol, side, qty, price?, order_type, tif`

### Guards (Fail-Closed)

1. **Symbol/Side Presence**: must exist
2. **Qty Bounds**: `MIN_ORDER_QTY (0.001) ≤ qty ≤ MAX_ORDER_QTY (1000.0)`
3. **Price Bounds** (LIMIT only): `MIN_PRICE (0.01) ≤ price ≤ MAX_PRICE (1000000.0)`
4. **Qty Step**: `qty % QTY_STEP (0.001) == 0`
5. **Price Step** (LIMIT): `price % PRICE_STEP (0.01) == 0`
6. **Min Notional** (LIMIT): `qty * price ≥ MIN_NOTIONAL (10.0)`
7. **Cooldown**: `now - last_open_ts ≥ cooldown_sec`

### Outputs

- **DEC:OPEN**: `{symbol, side, qty, price?, order_type, tif}` with `why="OPEN_OK"`
- **ERR**: `{reason}` with `why="OPEN_GUARD_FAIL"` (guard violations)

### Example

```python
CMD:OPEN → {
  symbol: "BTCUSDT",
  side: "BUY",
  qty: "1.5",
  price: "50000.00",
  order_type: "LIMIT",
  tif: "GTC"
}

Guards PASS → DEC:OPEN with why="OPEN_OK"
Guards FAIL → ERR with why="OPEN_GUARD_FAIL" + reason
```

---

## Flow 2: Manage Flow

### States

```
FLAT → OPENED (on FILL) → TRACKING (on UPD) → EMIT_DEC_ADJUST → TRACKING
```

### Inputs

- **EVT:PARTIAL_FILL / FILL**: `symbol, qty, price`
- **UPD:PRICE**: `price` (market data update)

### Rules (Stub Logic)

1. **Trail**: if `current_price > entry_price * (1 + trail_pct/100)` → `DEC:ADJUST(why="ADJUST_TRAIL")`
2. **Breakeven**: if `elapsed_sec > breakeven_after_sec` → `DEC:ADJUST(why="ADJUST_BE")`
3. **Time Stop**: if `elapsed_sec > 3600` → `DEC:ADJUST(why="ADJUST_TIME")`

### Outputs

- **DEC:ADJUST**: `{rule, trigger_price?, elapsed_sec?}` with `why="ADJUST_*"`

### Example

```python
EVT:FILL → position_qty=1.5, entry_price=50000
UPD:PRICE → 50600 (> 50000*1.005=50250) → DEC:ADJUST(why="ADJUST_TRAIL")
```

---

## Flow 3: Close Flow

### States

```
FLAT → OPENED (on FILL) → CLOSE_COND → EMIT_DEC_CLOSE → DONE
```

### Inputs

- **EVT:FILL**: opens position
- **EVT:REJECTED / EXPIRED**: emergency close triggers
- **TIMER:TICK**: periodic check for max_hold_sec

### Rules (Stub Logic)

1. **Max Hold Time**: if `elapsed_sec > max_hold_sec (7200)` → `DEC:CLOSE(why="CLOSE_RULE")`
2. **Emergency**: if `EVT:REJECTED or EVT:EXPIRED` → `DEC:CLOSE(why="CLOSE_EMERGENCY")`

### Outputs

- **DEC:CLOSE**: `{reduce_only: true}` with `why="CLOSE_RULE"|"CLOSE_EMERGENCY"`

### Example

```python
EVT:FILL → position_active=True
TIMER:TICK (after 7300 sec) → DEC:CLOSE(why="CLOSE_RULE", reduce_only=true)
```

---

## Orchestration (fsm.py)

**Router Bindings**:
- `CMD:OPEN` → `open_flow.handle()`
- `EVT:PARTIAL_FILL|FILL|UPD:*` → `manage_flow.handle()` → `close_flow.handle()`
- `EVT:REJECTED|EXPIRED` → `close_flow.handle()`
- `TIMER:*` → `close_flow.handle()`

**WAL Integration**:
- All `DEC:*` messages appended to WAL
- Replay via `/replay?rid=<rid>` returns full chain

**Metrics Aggregation**:
```python
{
  "fsm_decision_ms_p95": <p95 latency>,
  "fsm_open_decisions_total": <count>,
  "fsm_adjust_decisions_total": <count>,
  "fsm_close_decisions_total": <count>,
  "fsm_guard_rejects_total": <count>,
  "fsm_errors_total": <count>
}
```

---

## Contracts & Invariants

### Message Contract

All messages: `{op, verb, src, dst, rid, ts?, why, idempotent_key?, payload}`

- **op**: `CMD | DEC | EVT | UPD | ERR | TIMER`
- **verb**: action-specific (OPEN, CLOSE, ADJUST, FILL, etc.)
- **why**: ≤80 chars (enforced; 400 error if violated)
- **idempotent_key**: deterministic from (op, verb, payload, ts_bucket)

### Decimal Precision

- **Qty**: `Decimal` type, quantized to `QTY_STEP=0.001`
- **Price**: `Decimal` type, quantized to `PRICE_STEP=0.01`
- **No floats**: financial precision enforced via Pydantic V2 validators

### WHY Codes

- `OPEN_OK`: guards passed
- `OPEN_GUARD_FAIL`: guard violation (qty/price/notional/cooldown)
- `ADJUST_TRAIL`: trailing stop triggered
- `ADJUST_BE`: breakeven move triggered
- `ADJUST_TIME`: time-based adjustment
- `CLOSE_RULE`: max_hold_time or other rule
- `CLOSE_EMERGENCY`: REJECTED/EXPIRED event

---

## Testing Strategy

### Unit Tests (per flow)

1. **Open**: valid → DEC, each guard → ERR, cooldown → ERR
2. **Manage**: FILL → OPENED, trail/BE/time → DEC:ADJUST
3. **Close**: max_hold → DEC:CLOSE, REJECTED/EXPIRED → DEC:CLOSE(emergency)

### E2E Tests

1. **Shadow Round-Trip**: CMD → ACL stub → EVT → FSM → DEC → WAL
2. **Idempotency**: 50 parallel CMD with same key → 1 DEC
3. **Metrics**: export p95, totals after activity

### Coverage Target

- **Unit**: ≥90% per file (`fsm_open.py`, `fsm_manage.py`, `fsm_close.py`)
- **E2E**: ≥80% integration paths
- **Overall Repo**: maintain ≥90%

---

## Performance Targets

| Metric                     | Target       | Measurement        |
| -------------------------- | ------------ | ------------------ |
| FSM decision latency (p95) | ≤ 25ms       | `fsm_decision_ms_p95` |
| Router total latency (p95) | ≤ 50ms       | via `/metrics`     |
| WAL append latency         | ≤ 5ms        | `wal_append_ms`    |
| Guard reject rate          | ≤ 5%         | `guard_rejects / open_decisions` |
| Error rate                 | ≤ 1%         | `errors / total_messages` |

---

## Shadow-Mode Guarantees

1. **No live API calls**: all I/O via ACL stub
2. **Decisions logged**: every DEC written to WAL
3. **Replay integrity**: `/replay?rid=<rid>` returns full chain with `integrity_ok=true`
4. **Drift monitoring**: (future T03) shadow vs. live state drift < 1%

---

## Next Steps (P1-T03+)

- **T03**: Drift monitor (shadow vs. live state)
- **T04**: Replay CLI (`vfound replay --shadow`)
- **T05**: Canary cutover (10% single-writer)
- **T06**: Full cutover + DR validation

---

**Last Updated**: 2025-01-13  
**RID**: FSMP-P1-T02  
**Status**: Shadow-mode implementation complete
