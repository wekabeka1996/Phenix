# REPORT: MR V1 Runtime Wiring Fix

## Package: MR-V1-WIRING-SUBPACK-A
## Date: 2026-03-30
## Status: DONE

---

## Problem

`price_motion` data (multi-window returns `ret_10s`, `ret_60s`, `ret_300s`) was computed by Feature Engineering but **never included** in the `CMD:PROCESS_STRATEGY` payload. The handler's `_check_microstructure_veto()` read `features.get("price_motion", {})`, which always returned `{}` because `features` dict does not contain `price_motion` — it is a separate top-level block.

### Impact

With `price_motion` always empty:
- `recent_ret` is always `None`
- `has_favorable_rebound = False` always
- `has_adverse_continuation = False` always
- Veto defaults to **ambiguous block** on any adverse TFI — never differentiates toxic continuation from absorption

## Root Cause

Three gaps in the data pipeline:

1. **FE emission** (`feature_engineering.py`): `cmd_payload` dict at the CMD:PROCESS_STRATEGY emission site did not include `price_motion`. The `pm_block` was computed and included in `EVT:FEATURES_CALCULATED` payload but omitted from `cmd_payload`.

2. **CMD schema** (`cmd_process_strategy_v1.json`): Had `"additionalProperties": false`, so even if `price_motion` were added to the payload, schema validation would reject it.

3. **Handler consumption** (`mean_reversion_handler.py`): Read `price_motion` from `self._last_cmd_features[symbol]` (the features sub-dict), but `price_motion` was never in `features` — it's a separate top-level field.

## Fix (3 files)

### 1. FE Emission
**File:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Change:** Added `"price_motion": pm_block` to `cmd_payload` dict.

### 2. CMD Schema
**File:** `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`
**Change:** Added `price_motion` property definition with anyOf (object with `ret_10s`/`ret_60s`/`ret_300s` required, or null).

### 3. Handler Cache
**File:** `apps/reference/domains/decision_making/mean_reversion_handler.py`
**Changes:**
- Added `self._last_cmd_price_motion: Dict[str, Dict[str, Any]] = {}` at init
- Added caching block in `_on_process_strategy()` to extract `price_motion` from top-level CMD payload
- Changed `_check_microstructure_veto()` line 751 to read from `self._last_cmd_price_motion.get(symbol, {})` instead of `features.get("price_motion", {})`

## Canonical Contract

`price_motion` is a **top-level field** in `CMD:PROCESS_STRATEGY`, separate from `features`:
```json
{
  "symbol": "DOGEUSDT",
  "features": {"tfi": "-0.3", "obi": "0.1", ...},
  "price_motion": {"ret_10s": -0.001, "ret_60s": -0.002, "ret_300s": 0.003}
}
```

## Tests

All 16 existing helper-level tests pass after the fix (backward-compatible `_make_handler` extracts `price_motion` from features dict for legacy tests).

## FACTS
1. `pm_block` was computed at FE lines 1769-1793 but never added to `cmd_payload` [PROVEN by code inspection]
2. `features` dict (line 1427) does NOT contain `price_motion` [PROVEN by code inspection]
3. Handler now reads from dedicated `_last_cmd_price_motion` cache [PROVEN by code + tests]

## INFERENCES
1. The veto was effectively always in "ambiguous block" mode for adverse TFI without absorption evidence [INFERRED from empty price_motion]

## ASSUMPTIONS
None.

## UNKNOWNS
None.
