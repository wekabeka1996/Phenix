# TASK50: Quantity Normalization Contract — DONE

## 🎯 Goal

Одне джерело істини для qty, fail-closed семантика, жодних silent bump-ups.

**Інваріант:**
> `qty_sent == qty_ack(origQty) == qty_used_in_risk_math` (within step rounding)

---

## 📊 Root Cause Analysis

### Evidence from Logs

```
ORDER_PLACED:
  quantity: 0.27      ← what DecisionMaking calculated
  origQty: "1"        ← what exchange ACK returned
```

### Root Cause

`binance_adapter.py:quantize_quantity()` (lines 727-730, 757-760):

```python
# OLD CODE - SILENT BUMP-UP
if q < min_qty_d:
    q = min_qty_d  # ← BUG: silent bump to minQty!

if current_notional < min_notional_d:
    q = (min_notional_d / mark_d).quantize(...)  # ← BUG: silent notional bump!
```

For SOLUSDT testnet:
- `step_size = 1` (not 0.01 as incorrectly configured!)
- `min_qty = 1`
- `min_notional = 5`

So 0.27 → `floor(0.27/1)*1 = 0` → bumped to 1 → exchange ACK shows `origQty=1`.

---

## ✅ Solution

### 1. qty_normalizer.py — Single Source of Truth

**File:** [qty_normalizer.py](apps/reference/domains/execution_position/qty_normalizer.py)

```python
def normalize_qty(
    *,
    raw_qty: Decimal,
    price: Decimal,
    step_size: Decimal,
    min_qty: Decimal,
    min_notional: Optional[Decimal] = None,
) -> QtyNormalizeResult:
```

**Rules (strict, no bump-ups):**
1. `rounded_qty = floor(raw_qty / step_size) * step_size`
2. if `rounded_qty <= 0` → fail `NRR-QTY-ROUNDED-TO-ZERO`
3. if `rounded_qty < min_qty` → fail `NRR-QTY-BELOW-MIN_QTY`
4. if `notional < min_notional` → fail `NRR-NOTIONAL-BELOW-MIN`
5. return ok=True only when ALL pass

### 2. Wire at Dispatch Boundary

**File:** [fsm.py](apps/reference/domains/execution_position/fsm.py#L1545)

```python
# Get instrument spec from config (SSOT)
instrument_spec = self.config.instruments.get(symbol)
step_size = instrument_spec.step_size
min_qty = instrument_spec.min_qty
min_notional = instrument_spec.min_notional

# TASK50: Normalize qty - fail-closed
norm_result = normalize_qty(
    raw_qty=raw_qty,
    price=mark,
    step_size=step_size,
    min_qty=min_qty,
    min_notional=min_notional,
)

if not norm_result.ok:
    # Emit rejection, log, return
    order_logger.log(event_type="QTY_NORMALIZE_REJECTED", ...)
    return

qty = str(norm_result.qty)  # Use normalized qty
```

### 3. Remove Double Rounding

**File:** [binance_adapter.py](apps/reference/adapters/binance_adapter.py#L984)

```python
# OLD: qty = await self.quantize_quantity(symbol, quantity)  # ← REMOVED
# NEW: qty is already normalized by caller
params = {"quantity": quantity}  # Pass directly
```

### 4. Updated instruments.yaml

**File:** [instruments.yaml](config/aurora/instruments.yaml)

```yaml
instruments:
  SOLUSDT:
    step_size: "1"        # FIXED: was 0.01, actual is 1
    min_qty: "1"          # NEW: required for validation
    min_notional: "5"     # NEW: required for validation
```

### 5. Enhanced Logging

ORDER_PLACED now includes:
- `qty_raw` — original from sizing
- `qty_normalized` — after normalization
- `step_size`, `min_qty`, `min_notional`
- `qty_notional_usd`

---

## 🧪 Tests

### Unit Tests: test_task50_qty_normalizer.py

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestNormalizeQtyBasicRounding | 4 | step rounding |
| TestNormalizeQtyFailClosed | 4 | SOL incident, no bump-up |
| TestNormalizeQtyMinNotional | 5 | notional validation |
| TestNormalizeQtyEdgeCases | 5 | edge cases |
| TestNormalizeQtyResultFields | 3 | result structure |
| TestVerifyAckQty | 4 | ACK verification |
| TestRealWorldScenarios | 4 | BTC, SOL, DOGE |
| **Total** | **29** | ✅ |

### Critical Tests

```python
def test_solusdt_incident_case_fails():
    """raw=0.27, step=1 → MUST FAIL (not bump to 1)"""
    result = normalize_qty(raw_qty="0.27", step_size="1", min_qty="1", ...)
    assert result.ok is False
    assert result.why == NRR_QTY_ROUNDED_TO_ZERO
    assert result.qty is None  # NO BUMP-UP!

def test_no_bump_up_to_min_qty():
    """raw=0.8, min_qty=1.0 → MUST fail, NOT bump to 1.0"""
    result = normalize_qty(raw_qty="0.8", min_qty="1.0", ...)
    assert result.ok is False
    assert result.qty is None
```

---

## 📋 Validation Results

```
tests/domains/execution_position/test_task50_qty_normalizer.py — 29 passed ✅
tests/domains/decision_making/test_task40_one_open_order_guard.py — 3 passed ✅
tests/domains/execution_position/test_task49_atomic_entry_reserve.py — 17 passed ✅
```

---

## 📝 Sample Log Payload

```json
{
  "event_type": "ORDER_PLACED",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.002,
  "qty_raw": 0.00234,
  "qty_normalized": 0.002,
  "step_size": "0.001",
  "min_qty": "0.001",
  "min_notional": "100",
  "qty_notional_usd": 200.0,
  "client_order_id": "ENTRY-abc123",
  "order_id": "12345678"
}
```

For rejection:
```json
{
  "event_type": "QTY_NORMALIZE_REJECTED",
  "symbol": "SOLUSDT",
  "side": "BUY",
  "quantity": "0.27",
  "why": "NRR-QTY-ROUNDED-TO-ZERO",
  "adapter_response": {
    "ok": false,
    "raw_qty": "0.27",
    "rounded_qty": "0",
    "step_size": "1",
    "min_qty": "1"
  }
}
```

---

## 🔒 Contracts Enforced

| Contract | Before | After |
|----------|--------|-------|
| Qty normalization | Multiple places, bump-ups | Single boundary, fail-closed |
| Min qty violation | Silent bump to minQty | NRR-QTY-BELOW-MIN_QTY |
| Min notional violation | Silent bump qty | NRR-NOTIONAL-BELOW-MIN |
| instruments.yaml | Missing min_qty/min_notional | Complete filters |
| Logging | Basic qty | Full normalization context |

---

## ✅ Definition of Done

- [x] Single qty normalization boundary (fsm.py:_execute_decision)
- [x] Mismatch case (0.27 → 1) is impossible without explicit policy
- [x] Tests prove normalization, minQty, minNotional, rounding
- [x] Logs include normalization context for forensics
- [x] No double rounding (removed from binance_adapter.py)

**Status:** ✅ COMPLETE
