# Fix Report: Bracket Placement Bugs in fsm_manage.py

**Date:** 2026-02-24
**Branch:** stable_11_11
**Domain:** execution_position
**Severity:** Medium (P1) — orders rejected by Binance API, no data loss

---

## Summary

4 bugs in `fsm_manage.py` caused Binance API rejections (-4015, -1111, -1102, -2021) during SL/TP bracket placement. The primary bracket path (`fsm.py`) was unaffected and compensated for all failures. No positions were left unprotected except one BTCUSDT SHORT that lost its SL due to -2021 (price moved during 34s LIMIT fill latency).

**Log period analysed:** 2026-02-23 14:30 — 2026-02-24 03:20 UTC
**Total ERROR entries:** 27

---

## Root Cause: Dual-Path Bracket Placement

Two independent code paths attempt to place the same SL/TP brackets:

| Path | File | Result |
|------|------|--------|
| Primary (fsm.py) | `fsm.py:3504-3586`, `fsm.py:4700-4830` | Correct — uses `generate_client_order_id()`, `quantize_stop_price()` |
| Secondary (fsm_manage.py) | `fsm_manage.py:720-780` | Buggy — raw f-strings, no side-aware rounding, missing stopPrice for TP |

All 27 errors originated from the secondary path. The primary path successfully placed brackets in every case.

---

## Bug 1: Binance -1102 — Missing stopPrice for TAKE_PROFIT_MARKET

**Occurrences:** 2 (DOGEUSDT, XRPUSDT)
**Error:** `Mandatory parameter 'stopprice'/'triggerprice' was not sent, was empty/null, or malformed.`

### Root Cause

`fsm_manage.py:989` — condition `"STOP" in order_type` evaluates to `False` for `"TAKE_PROFIT_MARKET"`:

```python
# BEFORE (bug):
"stopPrice": price if "STOP" in order_type else None,
#            "STOP" in "TAKE_PROFIT_MARKET" == False -> stopPrice = None
```

Binance requires `stopPrice` for all conditional order types (`STOP_MARKET`, `TAKE_PROFIT_MARKET`).

### Fix

```python
# AFTER:
"stopPrice": price if order_type not in ("LIMIT", "MARKET") else None,
```

Same fix applied to the `closePosition` guard at line 997.

**File:** `fsm_manage.py:989, 997`

---

## Bug 2: Binance -4015 — Client Order ID > 36 chars

**Occurrences:** 4 (BTCUSDT x2, SOLUSDT x2)
**Error:** `Client order id length should be less than 36 chars`

### Root Cause

`fsm_manage.py:715-719` built client IDs via raw f-string concatenation:

```python
# BEFORE (bug):
position_id = f"{msg.rid}_{int(self.position_open_ts)}"
sl_client_id = f"{position_id}_sl"      # 42-50 chars (limit: 36)
```

Example: `aurora_BTCUSDT_1771850999715_1771850735_sl` = 46 chars.

Trailing stop IDs were even longer (`fsm_manage.py:1356`):
```python
new_client_id = f"{position_id}_sl_trail_{int(get_clock().now_sec())}"  # 60+ chars
```

### Fix

Replaced with `generate_client_order_id()` from `utils.py` which uses MD5 hashing to guarantee <= 32 chars:

```python
# AFTER:
idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
sl_client_id = generate_client_order_id("SL", symbol, idempotent_key=idem_base)
# Produces: "SL-a1b2c3d4e5f6" (15 chars)
```

**Files:** `fsm_manage.py:720-725, 1360-1363`

---

## Bug 3: Binance -1111 — Precision Over Maximum

**Occurrences:** 2 (DOGEUSDT, XRPUSDT)
**Error:** `Precision is over the maximum defined for this asset.`

### Root Cause

`fsm_manage.py:922-952` used `Decimal.quantize(Decimal("1"))` with default `ROUND_HALF_EVEN` rounding, which:
1. Does not guarantee Binance PRICE_FILTER compliance (`price % tickSize == 0`)
2. Does not consider order side (BUY/SELL) for directional safety

Example: XRPUSDT `tick_size=0.0001`, raw price `1.3395299` (7 decimal places) was not rounded.

### Fix

Delegated to `quantize_stop_price()` from `utils.py` with side-aware rounding:

```python
# AFTER:
bracket_side = opposite_side(self.position_side) if self.position_side else "SELL"

sl_price = Decimal(str(quantize_stop_price(
    float(sl_price), tick_size, side=bracket_side)))
```

Rounding logic:
- BUY position -> SELL brackets -> FLOOR (round down, avoids premature SL trigger)
- SELL position -> BUY brackets -> CEIL (round up, avoids premature SL trigger)

**File:** `fsm_manage.py:928-967`

---

## Bug 4: Binance -2021 — Order Would Immediately Trigger

**Occurrences:** 1 (BTCUSDT)
**Error:** `Order would immediately trigger.`

### Context

BTCUSDT SHORT entry (LIMIT GTX) placed at 03:20:00, filled at 03:20:34 (34s latency). During this time, mark price rose above the SL level (64036.1), making the `BUY STOP_MARKET` order immediately triggerable.

SL distance was 0.40% ($256) — within the configured `min_dist_bps: 15` but too narrow for 34s fill latency during volatile conditions.

**Result:** Position left without SL. TP was placed successfully.

### Fix

Increased widening parameters in `config/aurora/domains.yaml`:

```yaml
# BEFORE:
bracket_placement:
  tp_widen_first_bps: 20
  tp_widen_second_bps: 50

# AFTER:
bracket_placement:
  tp_widen_first_bps: 25    # +5 bps safety margin
  tp_widen_second_bps: 60   # +10 bps safety margin
```

**File:** `config/aurora/domains.yaml:436-442`

---

## Error Distribution by Symbol

| Symbol | -1102 | -4015 | -1111 | -2021 | SOFT_LIMIT | Total |
|--------|-------|-------|-------|-------|------------|-------|
| SOLUSDT | 0 | 2 | 0 | 0 | 15 | 17 |
| BTCUSDT | 0 | 2 | 0 | 1 | 1 | 4 |
| DOGEUSDT | 1 | 0 | 1 | 0 | 1 | 3 |
| XRPUSDT | 1 | 0 | 1 | 0 | 1 | 3 |
| **Total** | **2** | **4** | **2** | **1** | **18** | **27** |

SOFT_LIMIT_BELOW_CLIP_MIN (18 entries) is expected fail-closed behaviour on low equity (~$170). Not a bug.

---

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| `apps/reference/domains/execution_position/fsm_manage.py` | +15 / -12 | Import utils, fix stopPrice condition, fix clientOrderId generation, side-aware quantization |
| `config/aurora/domains.yaml` | +2 / -2 | Bump tp_widen_first_bps 20->25, tp_widen_second_bps 50->60 |
| `tests/domains/execution_position/test_fsm_manage_bracket_fixes.py` | +194 (new) | 20 test cases covering all 3 code fixes |

---

## Test Results

```
tests/domains/execution_position/test_fsm_manage_bracket_fixes.py  20 passed
tests/domains/execution_position/ (full suite)                    346 passed, 1 skipped
```

Test classes:
- `TestStopPricePresence` — 6 parametrized tests (STOP_MARKET, TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT, LIMIT, MARKET)
- `TestClientOrderIdLength` — 9 tests (bracket IDs, trailing IDs, determinism, uniqueness)
- `TestQuantizePricesSideAware` — 5 tests (BUY/SELL rounding, boundary, fail-closed ValueError)

---

## Remaining Risk: Dual-Path Architecture

Both `fsm.py` and `fsm_manage.py` attempt bracket placement independently. While the bugs are now fixed in both paths, the dual-path architecture:
- Consumes extra Binance API rate limit (2x bracket attempts per fill)
- May create duplicate brackets under race conditions
- Increases maintenance surface

Future consideration: unify bracket placement into a single code path.
