# EP_PRECISION_1111_CONTEXT

**Domain:** `execution_position`
**Error:** `PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset`
**Classification:** `NORMALIZER_BYPASS` — post-offset re-quantization missing
**Status:** Root cause confirmed, fix not implemented
**Date:** 2026-02-24

---

## Executive Summary

- **Binance -1111** fires when `stopPrice` (or `price` / `quantity`) carries more decimal places than the exchange's `tickSize` / `stepSize` allows for the given instrument.
- **Violating field is `stopPrice` exclusively** — all 8 observed -1111 occurrences involve `STOP_MARKET` or `TAKE_PROFIT_MARKET` bracket orders whose `stopPrice` has excess decimal precision.
- **Root cause:** In `fsm_manage.py:_place_brackets()`, bracket prices are correctly quantized by `_quantize_prices()`, but a safety offset (`TPSLValidationRules.add_safety_offset`) is then subtracted from `sl_price`. The offset is `max(tick_size, price * 5/10000)` — the percentage branch (`price * 5/10000`) is **NOT a tick_size multiple**, so the subtraction destroys tick alignment. The result is passed as `str(sl_price)` to the Binance adapter without re-quantization.
- **Second path:** `fsm.py:_place_deferred_brackets()` (LIMIT-DEFERRED fill-triggered path) passes `str(sl)` / `str(tp)` directly to the adapter from `bracket_data`. If the stored values originated from the same unquantized calculation, they carry the precision violation into the deferred placement.
- **All 4 affected symbols are mathematically accounted for** — the exact log-observed stopPrice values reproduce precisely from `quantized_sl − offset`, confirming the single root cause.
- **Silent absorption:** generic `except Exception` in the SL placement path logs the error but does NOT retry or re-quantize, leaving positions unprotected (SL/TP absent after fill).
- **Fix scope is small** — a single call to `quantize_stop_price(sl, tick_size, side=bracket_side)` after offset arithmetic in both placement paths eliminates all instances.

---

## Evidence Table

All 8 confirmed -1111 occurrences, reconstructed from log context:

| # | Log File | Lines | Symbol | Side | Order Type | Raw stopPrice in Log | tick_size | Decimals | Max Allowed | Δ |
|---|----------|-------|--------|------|-----------|---------------------|-----------|----------|-------------|---|
| 1 | `.log` | 2808 | BTCUSDT | SELL | STOP_MARKET | `62859.45455` | 0.1 | 5 | 1 | **+4** |
| 2 | `.log` | 2812 | BTCUSDT | SELL | TAKE_PROFIT_MARKET | `63712.8405` | 0.1 | 4 | 1 | **+3** |
| 3 | `.log` | 3759 | DOGEUSDT | SELL | STOP_MARKET | `0.09043476` | 0.00001 | 8 | 5 | **+3** |
| 4 | `.log` | 3760 | DOGEUSDT | SELL | TAKE_PROFIT_MARKET | `0.091495725` | 0.00001 | 9 | 5 | **+4** |
| 5 | `.log` | 4745 | SOLUSDT | SELL | STOP_MARKET | `76.031965` | 0.01 | 6 | 2 | **+4** |
| 6 | `.log` | 4748 | SOLUSDT | SELL | TAKE_PROFIT_MARKET | `76.419035` | 0.01 | 6 | 2 | **+4** |
| 7 | `.log.1` | 5527 | SOLUSDT | SELL | STOP_MARKET | `76.031965` | 0.01 | 6 | 2 | **+4** |
| 8 | `.log.1` | 22963 | XRPUSDT | SELL | STOP_MARKET | `1.3395299` | 0.0001 | 7 | 4 | **+3** |

All occurrences: `side=SELL`, `order_type=STOP_MARKET` or `TAKE_PROFIT_MARKET` → closing bracket orders for LONG positions.

---

## Violating Field: Mathematical Proof

### Root equation
```
raw_stopPrice = quantized_sl - add_safety_offset(sl_price, tick_size, offset_bps=5)
             = quantized_sl - max(tick_size, sl_price * 5 / 10000)
```

When `sl_price * 5 / 10000 > tick_size` (true for any price > `tick_size * 2000`), the offset becomes a percentage fraction with arbitrary decimal length that is **not a multiple of tick_size**.

### Per-symbol reconstruction

**BTCUSDT** (tick_size=0.1, max 1 dp):
```
quantized_sl  = 62890.9
offset        = max(0.1, 62890.9 * 5 / 10000) = max(0.1, 31.44545) = 31.44545
raw_sl        = 62890.9 - 31.44545 = 62859.45455   ← 5 dp, matches log ✓
```

**SOLUSDT** (tick_size=0.01, max 2 dp):
```
quantized_sl  = 76.07
offset        = max(0.01, 76.07 * 5 / 10000) = max(0.01, 0.038035) = 0.038035
raw_sl        = 76.07 - 0.038035 = 76.031965   ← 6 dp, matches log ✓
```

**DOGEUSDT** (tick_size=0.00001, max 5 dp):
```
quantized_sl  = 0.09048
offset        = max(0.00001, 0.09048 * 5 / 10000) = max(0.00001, 0.00004524) = 0.00004524
raw_sl        = 0.09048 - 0.00004524 = 0.09043476   ← 8 dp, matches log ✓
```

**XRPUSDT** (tick_size=0.0001, max 4 dp):
```
quantized_sl  = 1.3402
offset        = max(0.0001, 1.3402 * 5 / 10000) = max(0.0001, 0.00067010) = 0.00067010
raw_sl        = 1.3402 - 0.00067010 = 1.33952990   ← 7 dp, matches log ✓
```

**Conclusion:** `stopPrice` is the sole violating field. `price` and `quantity` fields are not present in bracket orders (they use `closePosition=true`). The offset arithmetic alone produces the excess precision.

---

## Call Graph / Codepath Map

### Path A — ManageFSM bracket placement (market entry)

```
ManageFSM._place_brackets(symbol, side, sl, tp, tick_size, ...)
  │
  ├─ _calculate_bracket_prices()         # returns (sl, tp) from strategy bps
  │    └─ calc_tp_sl_from_mark()         # utils.py — calls _round_to_tick ✓
  │
  ├─ _quantize_prices(sl, tp, tick_size) # Correctly aligns to tick_size ✓
  │
  ├─ sl_offset = TPSLValidationRules.add_safety_offset(sl, tick_size, 5)
  │                # contracts.py — returns max(tick_size, sl*5/10000)
  │                # PROBLEM: result is NOT a tick_size multiple          ⚠️
  │
  ├─ sl = sl - sl_offset                 # Loses tick alignment           ⚠️
  │    [tp arithmetic same path]
  │
  └─ _emit_place_order(symbol, side, "STOP_MARKET", str(sl), ...)
       │                                 # str(sl) = "62859.45455"        ✗
       └─ DEC:PLACE_ORDER → fsm.py handler → adapter.place_stop_market_close_position(
              symbol, sl_side, str(sl), new_client_order_id=sl_id
          )
          → Binance API → -1111
```

### Path B — ExecPosFSM deferred bracket placement (LIMIT entry fill)

```
fill event → _on_fill_received(order_id, ...)
  │
  ├─ bracket_data = self._pending_brackets.get(order_id)
  │    # bracket_data["sl"] stored at LIMIT order submission time
  │    # If stored value came from Path A before fix → carries precision violation
  │
  └─ _submit_async(_place_deferred_brackets(order_id, bracket_data))
       │
       └─ sl = Decimal(bracket_data["sl"])
          tp = Decimal(bracket_data["tp"])
          tick_size = bracket_data["tick_size"]
          │
          ├─ [no re-quantization]                                          ⚠️
          │
          ├─ adapter.place_stop_market_close_position(
          │      symbol, sl_side, str(sl), new_client_order_id=sl_id
          │  )
          │  → Binance API → -1111
          │
          └─ except Exception as e:
               LOG.error(...)    # error logged, no retry, no re-quant    ⚠️
```

---

## SSOT Mapping

Source of truth: `config/aurora/instruments.yaml`

| Symbol | tick_size | step_size | Quantizer function | Enforcement point |
|--------|-----------|-----------|--------------------|-------------------|
| BTCUSDT | `0.1` | `0.001` | `quantize_stop_price(p, 0.1, side=s)` | MISSING after offset |
| SOLUSDT | `0.01` | `1` | `quantize_stop_price(p, 0.01, side=s)` | MISSING after offset |
| DOGEUSDT | `0.00001` | `1` | `quantize_stop_price(p, 0.00001, side=s)` | MISSING after offset |
| XRPUSDT | `0.0001` | `0.1` | `quantize_stop_price(p, 0.0001, side=s)` | MISSING after offset |
| ETHUSDT | `0.01` | `0.001` | `quantize_stop_price(p, 0.01, side=s)` | MISSING after offset |

`quantize_stop_price()` exists in `utils.py` and is called correctly in:
- `utils.py:validate_anti_2021()` — adjusts then re-quantizes ✓
- `utils.py:calc_tp_sl_from_mark()` — quantizes at creation ✓
- `fsm.py` TP -2021 retry path (line ~4858) — quantizes `tp_adj` after widening ✓

It is **NOT called** after offset subtraction in `fsm_manage.py:_place_brackets()` or in `fsm.py:_place_deferred_brackets()` initial placement path.

---

## Ranked Hypotheses

| Rank | Hypothesis | Confirmed / Falsified | Evidence |
|------|-----------|----------------------|---------|
| **H1** | `add_safety_offset()` result destroys tick alignment in `_place_brackets()` | **CONFIRMED** | Mathematical reconstruction matches all 4 symbols |
| **H2** | `bracket_data` WAL values carry pre-existing precision violation into deferred path | **CONFIRMED** (secondary) | SOLUSDT `76.031965` appears in both `.log` and `.log.1` — same value replayed |
| H3 | `BracketOrderPayload` Pydantic validator quantizes stopPrice | **FALSIFIED** | `contracts.py:stop_price` validator only does `Decimal(str(v))` — no tick_size enforcement |
| H4 | `_quantize_prices()` fails silently | **FALSIFIED** | Log shows quantized intermediate values (e.g., `62890.9`) before offset step |
| H5 | `quantity` field violates precision | **FALSIFIED** | All bracket orders use `closePosition=true` — no quantity field sent |

**Falsification method for H1:** Add a `quantize_stop_price(sl, tick_size, side=sl_side)` call after offset arithmetic. If -1111 disappears, H1 is the root cause (predicted pass).

---

## Fix Options

### Option 1 — Re-quantize immediately after offset subtraction (Recommended)

```python
# In fsm_manage.py:_place_brackets(), after:
sl = sl - sl_offset
tp = tp + tp_offset

# ADD:
sl = quantize_stop_price(sl, tick_size, side=sl_side)
tp = quantize_stop_price(tp, tick_size, side=tp_side)
```

**Pros:**
- Minimal change — single insertion, exactly at the codepath proven to be the root cause
- Uses the existing, tested `quantize_stop_price()` function
- Consistent with the -2021 retry path (which already does this on widening)
- Does not affect any other logic

**Cons:**
- Does not fix already-stored WAL bracket_data (requires Path B fix too)
- Does not add a safety net for future bypass scenarios

**Fail-closed implication:** Re-quantization of SL moves the price up by at most `price * 5/10000` fraction of one tick — negligible vs. the safety offset itself. No risk of accidentally touching the mark price.

---

### Option 2 — Re-quantize at the WAL/bracket_data storage point

Fix `_store_pending_brackets()` to quantize before writing to WAL:

```python
bracket_data = {
    "sl": str(quantize_stop_price(sl, tick_size, side=sl_side)),
    "tp": str(quantize_stop_price(tp, tick_size, side=tp_side)),
    ...
}
```

**Pros:**
- Guarantees deferred path (Path B) always receives clean values
- WAL data becomes canonical and human-readable
- Survives restarts / replays

**Cons:**
- Does NOT fix Path A (offset subtraction happens before WAL storage in current code)
- Requires understanding of call order; works correctly only if applied AFTER offset, not before

---

### Option 3 — Add tick_size enforcement inside `BracketOrderPayload.validate_bracket_rules()`

Inject `tick_size` as a validator argument and enforce in Pydantic:

```python
# contracts.py — add tick_size-aware validation to BracketOrderPayload
@model_validator(mode="after")
def validate_stopPrice_precision(self):
    if self.stop_price is not None and self.tick_size is not None:
        quantized = quantize_stop_price(float(self.stop_price), float(self.tick_size), side=...)
        if abs(float(self.stop_price) - quantized) > 1e-10:
            raise ValueError(f"stopPrice {self.stop_price} violates tick_size {self.tick_size}")
```

**Pros:**
- Catches violations at the domain boundary before they reach the adapter
- Acts as a safety net for ALL callers
- Explicit, auditable contracts

**Cons:**
- Requires passing `tick_size` into `BracketOrderPayload` (constructor change, touches all callers)
- Adds latency at every bracket order validation
- More invasive — wrong place to fix (better to fix at source), this is defense-in-depth only

---

### Option 4 — Re-quantize inside adapter before building the request

In `BinanceAdapter.place_stop_market_close_position()`, look up tick_size from exchange info and round stopPrice before sending.

**Pros:**
- Last line of defense — catches ALL callers
- No changes to business logic layer

**Cons:**
- Requires adapter to have tick_size lookup per symbol (coupling concern)
- Hides the root cause rather than fixing it
- Adapter should be a thin wrapper, not a business logic corrector
- Does NOT fix incorrect values stored in WAL

**Recommendation:** Implement **Option 1** (root-cause fix) + **Option 2** (WAL storage fix) simultaneously, and add regression tests. Option 3 (Pydantic guard) is recommended as defense-in-depth in a follow-up, but not as the primary fix.

---

## Repro Log Snippets

### Snippet 1 — BTCUSDT SL + TP (`.log` lines ~2806-2814)
```
INFO  Executing PLACE_ORDER: BTCUSDT SELL STOP_MARKET 0.005 @ None/62859.45455
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.

INFO  Executing PLACE_ORDER: BTCUSDT SELL TAKE_PROFIT_MARKET 0.005 @ None/63712.8405
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.
```
**Correct values after quantization:**
- SL: `quantize_stop_price(62859.45455, 0.1, side="SELL")` → `62859.4`
- TP: `quantize_stop_price(63712.8405, 0.1, side="BUY")` → `63712.9`

---

### Snippet 2 — DOGEUSDT SL + TP (`.log` lines ~3757-3762)
```
INFO  Executing PLACE_ORDER: DOGEUSDT SELL STOP_MARKET 3494.0 @ None/0.09043476
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.

INFO  Executing PLACE_ORDER: DOGEUSDT SELL TAKE_PROFIT_MARKET 3494.0 @ None/0.091495725
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.
```
**Correct values after quantization:**
- SL: `quantize_stop_price(0.09043476, 0.00001, side="SELL")` → `0.09043`
- TP: `quantize_stop_price(0.091495725, 0.00001, side="BUY")` → `0.09150`

---

### Snippet 3 — SOLUSDT SL + TP (`.log` lines ~4743-4750)
```
INFO  Executing PLACE_ORDER: SOLUSDT SELL STOP_MARKET 5.0 @ None/76.031965
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.

INFO  Executing PLACE_ORDER: SOLUSDT SELL TAKE_PROFIT_MARKET 5.0 @ None/76.419035
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.
```
**Correct values after quantization:**
- SL: `quantize_stop_price(76.031965, 0.01, side="SELL")` → `76.03`
- TP: `quantize_stop_price(76.419035, 0.01, side="BUY")` → `76.42`

---

### Snippet 4 — SOLUSDT SL replay in `.log.1` (same value, deferred path)
```
INFO  Executing PLACE_ORDER: SOLUSDT SELL STOP_MARKET 5.0 @ None/76.031965
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.
```
Identical stopPrice `76.031965` appears in both `.log` and `.log.1` — confirms the unquantized value was stored in `bracket_data` WAL and replayed on restart, triggering -1111 again.

---

### Snippet 5 — XRPUSDT SL (`.log.1` line ~22963)
```
INFO  Executing PLACE_ORDER: XRPUSDT SELL STOP_MARKET 290.0 @ None/1.3395299
ERROR PLACE_ORDER failed: [-1111] Precision is over the maximum defined for this asset.
```
**Correct value after quantization:**
- SL: `quantize_stop_price(1.3395299, 0.0001, side="SELL")` → `1.3395`

---

## Proposed Regression Tests

### Test 1: `test_place_brackets_sl_price_precision`
```python
def test_place_brackets_sl_price_precision():
    """After offset arithmetic, sl stopPrice must be a tick_size multiple."""
    # Arrange: BTCUSDT, LONG position, mark=62890.9, tick_size=0.1
    # Act: call _place_brackets() or _place_deferred_brackets()
    # Assert: captured adapter call has stopPrice with <= 1 decimal place
    captured = adapter_mock.place_stop_market_close_position.call_args
    stop_price_str = captured[0][2]  # positional arg
    decimals = len(stop_price_str.split(".")[-1]) if "." in stop_price_str else 0
    assert decimals <= 1, f"BTCUSDT stopPrice {stop_price_str} violates tick_size 0.1"
```

### Test 2: `test_add_safety_offset_result_is_not_tick_aligned`
```python
def test_add_safety_offset_result_is_not_tick_aligned():
    """Documents that add_safety_offset() returns an unaligned Decimal — caller must re-quantize."""
    offset = TPSLValidationRules.add_safety_offset(
        current_price=Decimal("62890.9"),
        tick_size=Decimal("0.1"),
        offset_bps=5
    )
    # offset = 31.44545 — NOT a multiple of 0.1
    remainder = offset % Decimal("0.1")
    assert remainder != 0, "Offset IS a tick multiple (unexpected); double-check offset_bps"
    # This test proves the caller must call quantize_stop_price() after subtraction.
```

### Test 3: `test_bracket_data_wal_stores_quantized_prices`
```python
def test_bracket_data_wal_stores_quantized_prices():
    """bracket_data stored for deferred placement must have tick-aligned prices."""
    # Arrange: trigger _store_pending_brackets with known sl, tp, tick_size
    # Act: inspect stored bracket_data
    stored = fsm._pending_brackets[entry_order_id]
    sl = Decimal(stored["sl"])
    tick = Decimal(stored["tick_size"])
    assert (sl % tick) == 0, f"SL {sl} is not a multiple of tick_size {tick}"
```

### Test 4: `test_place_deferred_brackets_no_precision_error`
```python
async def test_place_deferred_brackets_no_precision_error():
    """_place_deferred_brackets must not trigger -1111 for any supported symbol."""
    for symbol, tick_str in [("BTCUSDT","0.1"),("SOLUSDT","0.01"),("DOGEUSDT","0.00001"),("XRPUSDT","0.0001")]:
        bracket_data = make_bracket_data_with_offset(symbol, tick_size=Decimal(tick_str))
        # Assert no BinanceAPIError(-1111) raised
        await fsm._place_deferred_brackets(entry_order_id, bracket_data)
        # Assert captured stopPrice is quantized
        assert_stop_price_quantized(adapter_mock, tick_str)
```

### Test 5: `test_quantize_stop_price_parametrized`
```python
@pytest.mark.parametrize("raw,tick,side,expected", [
    ("62859.45455", "0.1",     "SELL", "62859.4"),
    ("76.031965",   "0.01",    "SELL", "76.03"),
    ("0.09043476",  "0.00001", "SELL", "0.09043"),
    ("1.3395299",   "0.0001",  "SELL", "1.3395"),
    ("63712.8405",  "0.1",     "BUY",  "63712.9"),
])
def test_quantize_stop_price_parametrized(raw, tick, side, expected):
    result = quantize_stop_price(float(raw), float(tick), side=side)
    assert str(round(result, len(tick.split(".")[-1]) if "." in tick else 0)) == expected
```

---

## Next Steps (no implementation)

1. **EP-ORDER-PRECISION-1111-FIX-A**: In `fsm_manage.py:_place_brackets()`, add `quantize_stop_price(sl, tick_size, side=sl_side)` and corresponding TP call **after** the offset subtraction, before `_emit_place_order()`.

2. **EP-ORDER-PRECISION-1111-FIX-B**: In `_store_pending_brackets()` (or equivalent WAL write point), ensure `sl` and `tp` written to `bracket_data` are already quantized. Search for the WAL write path and add quantization before storage.

3. **EP-ORDER-PRECISION-1111-TEST**: Implement the 5 regression tests above. Tests 1, 3, 5 should be written first (pure unit tests, no adapter mocking needed), then 2 and 4 as integration-level tests.

4. **EP-ORDER-PRECISION-1111-GUARD** (optional, defense-in-depth): Add a precision assertion in `BinanceAdapter.place_stop_market_close_position()` that raises a `PrecisionViolationError` (not a generic exception) if stopPrice decimal places exceed tick_size decimal places. This allows callers to catch and re-quantize rather than getting a -1111 from Binance.

5. **Verify ETHUSDT** is not currently affected (no occurrences in logs) but is theoretically vulnerable to the same bug — add a corresponding test case.

---

*Document created by forensic session 2026-02-24. Root cause mathematically proven. Investigation only — no code changes made.*
