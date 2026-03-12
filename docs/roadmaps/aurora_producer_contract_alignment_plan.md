# Aurora Producer Contract Alignment — Implementation Plan

**Package:** NEO-PRODUCER-CONTRACT-ALIGNMENT-AUDIT-AND-IMPLEMENTATION-PLAN
**Date:** 2026-03-12
**Status:** PLAN ONLY — No implementation in this document
**Branch:** Phenix_v2

---

## Overview

This document defines the dependency-ordered implementation plan for fixing
all 4 hard blockers (HB-1 through HB-4) that prevent execution-aware
neocortex integration with Aurora.

The plan is split into 5 packages. PKG-1 through PKG-4 fix the hard blockers.
PKG-5 is optional hardening for shadow launch hardening.

**Constraint: No neocortex code changes for PKG-1 through PKG-4.**
The neocortex consumer (`order_parser.py`, `transport/adapter.py`) already
expects the fields we are adding. They simply return `None` today because the
fields are absent. Filling them in is sufficient.

---

## Dependency Order (Critical Path)

```
PKG-1: lifecycle_id propagation
  ↓ (establishes per-symbol ikey cache pattern)
PKG-2: structured close identity (trade_id, side)
  ↓ (extends same cache pattern with tradeId)
PKG-3: fees accumulation + net_pnl computation
  ↓ (PKG-1+2+3 together make POSITION_CLOSED complete)
PKG-4: structured close surface replaces regex dependency
  ↓ (verifies reward_complete=True end-to-end)
PKG-5 (optional): POSITION_OPENED event + comparison hardening
```

PKG-1, PKG-2, PKG-3 can be built as a single atomic change to
`event_handlers.py` and `fsm.py` and `intent_builder.py`. Separating them
into packages reflects review/test granularity, not technical dependency.

---

## PKG-1: `lifecycle_id` Propagation

### Objective
Emit a stable `lifecycle_id` in ORDER_INTENT, ORDER_FILLED, and POSITION_CLOSED
log entries, so neocortex can link the full trade lifecycle by a single key that
persists across stages.

### Why Now
HB-1. Without `lifecycle_id`, all execution_quality samples have `source_ref`
derived from fragile symbol+timestamp heuristics. Every other package builds
provenance on top of this identity.

### Files Likely Touched

| File | Change Type | Change Description |
|---|---|---|
| `apps/reference/domains/execution_position/fsm.py` | Additive | Add `_last_lifecycle_ikey_by_symbol: Dict[str, str] = {}` |
| `apps/reference/domains/execution_position/event_handlers.py` | Additive | In `on_order_fill`: cache idempotent_key from order_index; in POSITION_CLOSED write: add `lifecycle_id` field |
| `apps/reference/domains/decision_making/intent_builder.py` | Additive | In ORDER_INTENT log dict: add top-level `"lifecycle_id": trade_intent["idempotent_key"]` |

**Total: 3 files, ≤10 line additions, 0 deletions.**

### Contract Change
`order_log_v1.jsonl` POSITION_CLOSED entries gain top-level `lifecycle_id` field.
ORDER_INTENT entries gain top-level `lifecycle_id` field.
Existing fields unchanged.

### Implementation Notes

1. In `intent_builder.py:357-364`, add to the `order_logger.write()` dict:
   ```python
   "lifecycle_id": trade_intent["idempotent_key"],
   ```

2. In `fsm.py.__init__`, after line 302 add:
   ```python
   self._last_lifecycle_ikey_by_symbol: Dict[str, str] = {}
   ```

3. In `event_handlers.py.on_order_fill`, after the existing cache at line 384,
   look up `idempotent_key` from order_index for this fill. The order_index
   lookup: `oi.get_intent_for_order(clientOrderId)` returns an intent object.
   The `idempotent_key` is stored in `trade_intent["idempotent_key"]` at intent
   time. It must be reachable via order_index.

   > IMPORTANT: `idempotent_key` is stored in the CMD:OPEN payload
   > (`intent_router.py:75: "idempotent_key": pld.get("idempotent_key")`),
   > which flows through to `open_executor.py:135`. The order_index upsert at
   > `open_executor.py:388-395` sets `idempotent_key=str(idem_key)`.
   > So `order_index.get(clientOrderId=entry_id).idempotent_key` should work.

4. In POSITION_CLOSED write at `event_handlers.py:246-261`, add:
   ```python
   "lifecycle_id": self._fsm._last_lifecycle_ikey_by_symbol.pop(sym, ""),
   ```

### Tests to Write First (TDD order)

1. `tests/domains/decision_making/test_lifecycle_id_propagation.py`
   - ORDER_INTENT log must contain `lifecycle_id` at top level
   - `lifecycle_id` must equal `metadata.idempotent_key`

2. `tests/integration/test_lifecycle_id_end_to_end.py`
   - Simulate: intent → fill → position closed
   - Assert ORDER_INTENT `lifecycle_id` == ORDER_FILLED `lifecycle_id` == POSITION_CLOSED `lifecycle_id`
   - Assert no lifecycle_id is ever None for a fully exercised lifecycle

3. `tests/contracts/test_order_log_lifecycle_id_contract.py`
   - Schema contract: ORDER_INTENT and POSITION_CLOSED entries always have `lifecycle_id`
   - POSITION_CLOSED `lifecycle_id` must not be empty string

### Acceptance Criteria

- [ ] ORDER_INTENT log entries have `lifecycle_id` at top level (not buried in metadata)
- [ ] ORDER_FILLED log entries have `lifecycle_id` at top level (same value)
- [ ] POSITION_CLOSED log entries have `lifecycle_id` (not empty, not None)
- [ ] `lifecycle_id` is stable across restart (it's a UUID from the intent)
- [ ] `order_parser.py` unit test shows `entry.lifecycle_id is not None` for all event types
- [ ] No regression in existing ORDER_INTENT/FILLED/CLOSED tests

### Migration Notes
Additive-only. Existing consumers ignore the new field. No schema version bump required
as order_logger schema uses `additionalProperties: true` at write time.

### Rollback Posture
Remove the 3 dict field additions. No structural change. Instant rollback.

---

## PKG-2: Structured Close Identity (`trade_id`, `side`)

### Objective
Emit `trade_id` (Binance `tradeId`) and correct `side` in POSITION_CLOSED log
entries, enabling canonical close-to-fill matching in neocortex.

### Why Now
HB-2. After PKG-1, `lifecycle_id` links intent to close. `trade_id` is the
exchange-canonical close event identifier. `side` is required for directional
analysis. Both are already available at fill time but not cached.

### Files Likely Touched

| File | Change Type | Change Description |
|---|---|---|
| `apps/reference/domains/execution_position/fsm.py` | Additive | Add `_last_trade_id_by_symbol: Dict[str, str] = {}` and `_last_entry_side_by_symbol: Dict[str, str] = {}` |
| `apps/reference/domains/execution_position/event_handlers.py` | Additive | In `on_order_fill`: cache `tradeId` and `side`. In POSITION_CLOSED write: add `trade_id` and correct `side` |

**Total: 2 files, ≤8 line additions, 0 deletions.**

### Implementation Notes

1. In `fsm.py.__init__` add:
   ```python
   self._last_trade_id_by_symbol: Dict[str, str] = {}
   self._last_entry_side_by_symbol: Dict[str, str] = {}
   ```

2. In `event_handlers.py.on_order_fill` (after existing caches at line 384-388):
   ```python
   if symbol:
       self._fsm._last_trade_id_by_symbol[symbol] = str(payload.get("tradeId") or "")
       if payload.get("side"):
           self._fsm._last_entry_side_by_symbol[symbol] = str(payload.get("side", ""))
   ```

3. In POSITION_CLOSED write at `event_handlers.py:246-261`, update entry dict:
   ```python
   "trade_id": self._fsm._last_trade_id_by_symbol.pop(sym, ""),
   "side": self._fsm._last_entry_side_by_symbol.pop(sym, "N/A"),
   ```

### Tests to Write First

1. `tests/domains/decision_making/test_position_closed_identity_fields.py`
   - POSITION_CLOSED must have `trade_id` equal to exchange tradeId from fill
   - POSITION_CLOSED `side` must NOT be "N/A"
   - POSITION_CLOSED `side` must equal the entry side

2. `tests/contracts/test_order_log_position_closed_contract.py`
   - Full POSITION_CLOSED schema contract test: all required identity fields present

### Acceptance Criteria

- [ ] POSITION_CLOSED `trade_id` is non-empty when fill had a `tradeId`
- [ ] POSITION_CLOSED `side` is "BUY" or "SELL" (never "N/A")
- [ ] `order_parser.py` unit test shows `entry.trade_id is not None` for POSITION_CLOSED
- [ ] No regression in existing POSITION_CLOSED tests

### Rollback Posture
Same as PKG-1. Dict field additions only.

---

## PKG-3: Fees Accumulation + `net_pnl` Computation

### Objective
Emit structured `fees` and `net_pnl` in POSITION_CLOSED entries, enabling
`reward_complete=True` in neocortex's execution_quality samples.

### Why Now
HB-3. This is the primary reward truth gap. Without `net_pnl`, `reward_missing`
is always True for execution quality samples.

### Files Likely Touched

| File | Change Type | Change Description |
|---|---|---|
| `apps/reference/domains/execution_position/fsm.py` | Additive | Add `_accumulated_fees_by_symbol: Dict[str, float] = {}` |
| `apps/reference/domains/execution_position/event_handlers.py` | Additive | In `on_order_fill`: accumulate commission; in POSITION_CLOSED: compute and emit fees, net_pnl |

**Total: 2 files, ≤10 line additions, 0 deletions.**

### Multi-Fill Consideration

For partial fills (multiple fill events for one close order), `commission` arrives
per fill. Accumulation must be additive:
```python
self._fsm._accumulated_fees_by_symbol[symbol] = (
    self._fsm._accumulated_fees_by_symbol.get(symbol, 0.0)
    + float(payload.get("commission") or 0.0)
)
```

Reset on POSITION_CLOSED to avoid pollution into next trade.

### Implementation Notes

1. In `fsm.py.__init__` add:
   ```python
   self._accumulated_fees_by_symbol: Dict[str, float] = {}
   ```

2. In `event_handlers.py.on_order_fill` (close fills: SL/TP/CLOSE at line 436):
   ```python
   if symbol and order_kind in ("SL", "TP", "CLOSE", "MARKET_FILLED"):
       self._fsm._accumulated_fees_by_symbol[symbol] = (
           self._fsm._accumulated_fees_by_symbol.get(symbol, 0.0)
           + float(payload.get("commission") or 0.0)
       )
   ```

3. In POSITION_CLOSED write path, after computing `pos_pnl`:
   ```python
   accumulated_fees = self._fsm._accumulated_fees_by_symbol.pop(sym, 0.0)
   net_pnl = pos_pnl - accumulated_fees
   ```
   Add to the `order_logger.write()` dict:
   ```python
   "metadata": {
       "close_price": ...,
       "realized_pnl": pos_pnl,
       "fees": accumulated_fees,
       "net_pnl": net_pnl,
   }
   ```

### Tests to Write First

1. `tests/domains/decision_making/test_position_closed_reward_fields.py`
   - POSITION_CLOSED `metadata.fees` is non-zero when fills had non-zero commission
   - POSITION_CLOSED `metadata.net_pnl` equals `realized_pnl - fees`
   - Multiple fills: fees are accumulated (test with 2 partial fills)

2. `tests/contracts/test_reward_completeness_contract.py`
   - When POSITION_CLOSED has `net_pnl` and `trade_id` and `lifecycle_id`:
     neocortex's reward extraction returns `reward_complete=True`

3. `tests/integration/test_fees_accumulation_multiclosure.py`
   - Partial fill sequence: 3 fills for same close → fees = sum of all commissions
   - After close, `_accumulated_fees_by_symbol[sym]` is reset to 0

### Acceptance Criteria

- [ ] POSITION_CLOSED `metadata.fees` present and ≥ 0.0
- [ ] POSITION_CLOSED `metadata.net_pnl` present and equals realized_pnl - fees
- [ ] Fees are accumulated across partial fills (not just last fill)
- [ ] Accumulator is reset after close emission (no pollution into next trade)
- [ ] neocortex test: execution_quality sample has `reward_complete=True`
  when given a fully-formed POSITION_CLOSED fixture from PKG-1+2+3

### Rollback Posture
Same. Dict field additions + accumulator init.

---

## PKG-4: Structured Close Surface — Retire Regex Dependency

### Objective
Ensure neocortex's `core_parser.py` never needs the regex path for reward
extraction. Achieved by: (a) verifying PKG-1+2+3 make the structured path
fire for every POSITION_CLOSED, and (b) explicitly deprecating the regex path
with a code comment.

### Why Now
HB-4. This is the validation package that confirms the reward pipeline is
end-to-end clean. Also deprecates the fragile text parsing path.

### Files Likely Touched

| File | Change Type | Change Description |
|---|---|---|
| `apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py` | Comment-only | Add `# DEPRECATED: regex fallback — should never fire for POSITION_CLOSED after PKG-4` to POSITION_CLOSED_PATTERN |
| `apps/reference/telemetry/trade_lifecycle_logger.py` | Additive | Add `trade_id: str = ""` to `TradeRecord`; wire `trade_id` in `on_fill()`; compute `net_pnl` in `_flush()` |

**Note:** No neocortex code changes beyond a deprecation comment in the parser.
The `trade_lifecycle_logger.py` change is optional for PKG-4 but unlocks PKG-5.

### Validation Focus

PKG-4 is primarily a verification package. The TDD focus is:
1. Build a representative fixture set from order_log_v1.jsonl with PKG-1+2+3 fields
2. Run neocortex's `order_parser.py` against the fixture
3. Confirm ALL POSITION_CLOSED entries produce non-None `lifecycle_id`, `trade_id`
4. Confirm ALL POSITION_CLOSED entries produce a closed episode with `reward_complete=True`
5. Confirm `core_parser.py` structured path IS used and regex fallback is NOT exercised

### Tests to Write First

1. `tests/contracts/test_order_log_producer_contract_v2.py`
   - Full fixture-based test: generate a complete lifecycle sequence
     (ORDER_INTENT → ORDER_PLACED → ORDER_FILLED → POSITION_CLOSED)
   - Assert each event has all required neocortex fields
   - Assert neocortex parser produces clean `OrderLogEntry` objects with all fields

2. `tests/contracts/test_core_parser_structured_path.py`
   - When POSITION_CLOSED entry has `trade_id`, `fees`, `net_pnl` embedded:
     structured path fires (NOT regex fallback)
   - Verify `CoreLogEntry.realized_pnl_net` is populated from structured feed

3. `tests/integration/test_execution_quality_reward_complete.py`
   - End-to-end: simulated lifecycle → neocortex adapter → assert no
     `NO_STRUCTURED_REWARD_RECEIVED` alerts → assert `reward_complete=True`

4. `tests/contracts/test_lifecycle_logger_trade_id.py`
   - `trade_lifecycle.jsonl` CLOSED records include `trade_id`
   - `net_pnl` is computed correctly in flushed record

### Acceptance Criteria

- [ ] 0 POSITION_CLOSED entries trigger regex fallback path after PKG-1+2+3
- [ ] 100% of POSITION_CLOSED entries produce `reward_complete=True` in neocortex
  when feeds have non-zero pnl
- [ ] `core_parser.py` POSITION_CLOSED_PATTERN has deprecation comment
- [ ] `trade_lifecycle.jsonl` records include `trade_id` and `net_pnl` (optional)
- [ ] All PKG-1+2+3 tests still pass

### Migration Note
The regex path in `core_parser.py` is NOT deleted in PKG-4. It is only
deprecated. Deletion is deferred to a future cleanup package once it's confirmed
that no log replay (for historical data before PKG-1) would silently miss closes.

---

## PKG-5 (Optional): POSITION_OPENED + Comparison Hardening

### Objective
Add an authoritative `POSITION_OPENED` event and persist decision traces,
enabling neocortex's shadow comparison corpus to operate deterministically.

### Why Now / Why Optional
This is NOT required for offline replay or basic shadow runtime. It is required
for the full acceptance campaign (shadow comparison corpus with 100+ episodes).
Schedule after PKG-1 to PKG-4 are verified.

### Files Likely Touched

| File | Change | Description |
|---|---|---|
| `apps/reference/domains/execution_position/event_handlers.py` | Additive | Emit `POSITION_OPENED` to order_log at fill time when entry detected |
| `apps/reference/domains/decision_making/intent_builder.py` | Additive | Persist DECISION_TRACE to a jsonl file (currently only emitted to bus) |

### Tests to Write First

1. `tests/domains/decision_making/test_position_opened_event.py`
   - After ENTRY ORDER_FILLED, a POSITION_OPENED entry appears in order_log
   - POSITION_OPENED has `lifecycle_id`, `trade_id`, `side`, `entry_price`

2. `tests/domains/decision_making/test_decision_trace_persistence.py`
   - Decision trace is written to `logs/decision_trace.jsonl`
   - Entry has `symbol`, `regime`, `strategy_id`, `score`, `ts_ms`

### Acceptance Criteria

- [ ] POSITION_OPENED event emitted after entry fill with all identity fields
- [ ] Decision trace JSONL written per-tick with full scoring context
- [ ] neocortex shadow gate G-SHADOW tests pass with full episode corpus

---

## Testing Strategy

### Test Taxonomy

#### 1. Producer Contract Tests (highest priority)
Location: `tests/contracts/`

These tests validate that Aurora's producer surface emits what neocortex expects.
They test `order_logger.write()` output format against the required contract.

Priority tests (write before each PKG):
- `test_order_log_lifecycle_id_contract.py` (PKG-1)
- `test_order_log_position_closed_contract.py` (PKG-2)
- `test_reward_completeness_contract.py` (PKG-3)
- `test_order_log_producer_contract_v2.py` (PKG-4)

#### 2. Unit Tests (per-component)
Location: `tests/domains/decision_making/`, `tests/domains/execution_position/`

Test individual caches and log writes in isolation:
- `test_lifecycle_id_propagation.py` — intent → fill → close identity chain
- `test_position_closed_identity_fields.py` — trade_id, side not N/A
- `test_position_closed_reward_fields.py` — fees, net_pnl math
- `test_fees_accumulation_multiclosure.py` — partial fill accumulation

#### 3. Integration Tests
Location: `tests/integration/`

Simulate a complete trade lifecycle with mocked adapter:
- `test_lifecycle_id_end_to_end.py` — full lifecycle, lifecycle_id stable
- `test_execution_quality_reward_complete.py` — full e2e → reward_complete=True

#### 4. Parser Contract Tests
Location: `tests/` or `tests/contracts/`

Use fixture files (JSONL with known content) to test parsers:
- `test_core_parser_structured_path.py` — structured path fires, not regex
- `test_order_parser_lifecycle_fields.py` — parser extracts new fields correctly

#### 5. Backward Compatibility / Transitional Tests
For each PKG: verify existing tests still pass. The additive-only approach means
no breaking changes. Add a regression marker in each test to catch accidental
regression.

#### 6. Fail-Closed Tests
- Test that if accumulator is missing, POSITION_CLOSED still emits (with 0.0 fees)
- Test that if tradeId is absent from fill, POSITION_CLOSED still emits (with "" trade_id)
- Test that if lifecycle_ikey lookup fails, POSITION_CLOSED still emits (with "" lifecycle_id)
All fail-closed: no exception propagation, no missing log entries.

### Fixture Strategy

Create canonical fixture files in `tests/fixtures/producer_contract/`:
- `order_log_lifecycle_pre_pkg1.jsonl` — current state (no lifecycle_id)
- `order_log_lifecycle_post_pkg4.jsonl` — target state (all fields present)
- `position_closed_complete.json` — single POSITION_CLOSED dict with all fields

These fixtures serve as:
1. Regression baseline for before/after PKG comparison
2. Input to neocortex parser contract tests
3. Documentation of the exact expected format

---

## Alternatives Analysis

### HB-1: lifecycle_id

| Option | Preferred | Backup | Rejected |
|---|---|---|---|
| A: Use `idempotent_key` as `lifecycle_id` | ✓ YES | — | — |
| B: Use intent `rid` as `lifecycle_id` | — | ✓ Safe fallback if ikey lookup is hard | — |
| C: New lifecycle_id generator | — | — | ✗ Unnecessary complexity |

**Why A over B:** `idempotent_key` is the correct semantic. `rid` is overloaded
as message envelope identity. `idempotent_key` was designed to be per-intent and
is already indexed in order_index. Using it clarifies the codebase.

### HB-2: trade_id

| Option | Preferred | Rejected |
|---|---|---|
| A: Cache tradeId per-symbol at fill | ✓ YES | — |
| B: Reconstruct from fill ledger | — | ✗ Race + fragile |
| C: Use orderId as proxy | — | ✗ Different semantic |

### HB-3: fees / net_pnl

| Option | Preferred | Valid Alternative | Rejected |
|---|---|---|---|
| A: Accumulate fees per-symbol; emit at close | ✓ YES (order_log) | — | — |
| B: Wire trade_lifecycle.jsonl | — | ✓ PKG-5 path | — |
| C: Post-close reconciliation | — | — | ✗ Race risk |

**Recommendation:** Do Option A (PKG-3) for order_log_v1.jsonl. Optionally also
do Option B as a neocortex long-term SSOT improvement in PKG-5.

### HB-4: structured close surface

| Option | Preferred | Backup | Rejected |
|---|---|---|---|
| A: Emit full fields in order_log POSITION_CLOSED | ✓ YES | — | — |
| B: Wire trade_lifecycle.jsonl as primary | — | ✓ After PKG-5 | — |
| C: Better regex | — | — | ✗ Principle violation |

---

## Migration Notes

### Zero-Downtime

All changes are additive dict field additions. No schema version bump needed.
`order_log_v1.jsonl` existing entries are not affected. No reader breakage.

### Historical Data

Pre-PKG-1 WAL and order logs will NOT have `lifecycle_id`, `trade_id`, etc.
Neocortex's parser handles this gracefully (returns `None` for missing fields —
same as today). Historical replay quality remains unchanged.

### Replay Safety

`legacy_rid` bridge in `order_parser.py` remains active during and after PKG-1
to PKG-4. It is retired in a separate cleanup step once the `lifecycle_id` path
is confirmed stable.

### `trade_lifecycle.jsonl` Schema and the `rid`-as-lifecycle_id Issue

Currently `trade_lifecycle_logger.py` uses `rid` as the key for `TradeRecord`.
After PKG-1, the correct key should be `lifecycle_id` (= `idempotent_key`).
This alignment is optional for PKG-4 but required for PKG-5.

---

## Full Acceptance Criteria Summary

### Before any neocortex shadow launch is possible:

- [PKG-1] [ ] ORDER_INTENT, ORDER_FILLED, POSITION_CLOSED all have `lifecycle_id`
- [PKG-2] [ ] POSITION_CLOSED has `trade_id` (non-empty) and correct `side`
- [PKG-3] [ ] POSITION_CLOSED `metadata` has `fees` and `net_pnl`
- [PKG-4] [ ] neocortex unit test confirms `reward_complete=True` for canonical fixture
- [PKG-4] [ ] 0 `NO_STRUCTURED_REWARD_RECEIVED` alerts in test mode
- [PKG-4] [ ] regex path has deprecation comment
- [All]   [ ] All existing tests pass (no regression)
- [All]   [ ] Feature timestamp SP-1 also satisfied (tracked separately)

### Before limited shadow runtime:
- All above + feature `event_ts_ms` in feature logs (SP-1)
- Analytics restore working for neocortex ingest restart gap (SR-7)

### Before full acceptance campaign:
- All above + decision trace JSONL persistence (PKG-5 SR-4)
- POSITION_OPENED event emitted (PKG-5)
- Live WAL replay verified deterministic across 100+ trade episodes

---

## Summary Package Table

| PKG | Objective | HB Fixed | Files | Risk |
|---|---|---|---|---|
| PKG-1 | `lifecycle_id` propagation | HB-1 | intent_builder.py, event_handlers.py, fsm.py | LOW |
| PKG-2 | `trade_id` + `side` in close | HB-2 | event_handlers.py, fsm.py | LOW |
| PKG-3 | `fees` + `net_pnl` in close | HB-3 | event_handlers.py, fsm.py | LOW |
| PKG-4 | Structured close validation | HB-4 | core_parser.py (comment), trade_lifecycle_logger.py (optional) | LOW |
| PKG-5 | POSITION_OPENED + trace persist | SR-2, SR-4 | event_handlers.py, intent_builder.py | MEDIUM |
