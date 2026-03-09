# FORENSIC-AUDIT: Advanced Stale Cancel фактична працездатність

## Executive Summary

`advanced_stale_cancel` у поточному коді фактично працездатний: canonical detector labels, `domains.yaml`, runtime routing і config validation зараз узгоджені на `TREND_UP/TREND_DOWN`. Критичний баг `BULL_TREND/BEAR_TREND` у stale-cancel потоці на цій гілці не відтворюється; натомість виявлено окремий legacy-test drift у DecisionMaking тестах, де ще очікуються `BULL_TREND/BEAR_TREND`, хоча runtime вже працює тільки з canonical labels.

## Evidence

### 1. Canonical regime labels (SSOT)

- `apps/reference/core/types/regime_types.py`: `RegimeLabel = {TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, LOW_VOLATILITY, UNCERTAIN}`
- `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`: `regime.enum` містить той самий список
- `apps/reference/domains/regime_detector/regime_detector.py`: emitter реально ставить `regime = "TREND_UP"` / `"TREND_DOWN"` і емiтить `EVT:REGIME_DETECTED`

### 2. Example EVT:REGIME_DETECTED payload

```json
{
  "symbol": "BTCUSDT",
  "regime": "TREND_DOWN",
  "confidence": "0.73",
  "warmup": {"full_ready": true, "ticks_seen": 123},
  "changed": true,
  "last_update_ts_ms": 1700000000000
}
```

### 3. YAML cross-check

- `config/aurora/domains.yaml` uses:
  - `BUY: ["TREND_DOWN"]`
  - `SELL: ["TREND_UP"]`
  - `never_cancel_regimes: ["UNCERTAIN", "MEAN_REVERSION", "LOW_VOLATILITY"]`
- Verdict: `match` with canonical `RegimeLabel`

### 4. Routing behavior in `execution_position/fsm.py`

Condition tree as implemented:

1. If `pending_entry_ttl.enabled` and `cancel_on_regime_change` and `symbol`
2. If `advanced_stale_cancel is not None and advanced_stale_cancel.enabled`: call `_evaluate_advanced_stale_cancel(symbol, new_regime)`
3. Else: call legacy `_cancel_pending_entries_for_symbol(... reason="CANCEL_STALE_REGIME")`

Outcome on mismatch:

- With advanced enabled, legacy path is not called.
- If Gate 1 regime comparison misses, `_evaluate_advanced_stale_cancel()` simply approves no order IDs and no cancel occurs.
- Current config validation prevents phantom labels from reaching runtime via `ConfigLoader.load_config()`.

### 5. DecisionMaking / legacy namespace

- Runtime `apps/reference/domains/decision_making/decision_making.py` checks only:
  - `TREND_UP`
  - `TREND_DOWN`
  - `UNCERTAIN`
- No runtime `BULL_TREND/BEAR_TREND` usage found in `apps/reference`.
- Remaining `BULL_TREND/BEAR_TREND` hits are in tests only, so this is test drift, not active runtime logic.

## Reproduction

### Passing stale-cancel proof

- `pytest -q tests/domains/execution_position/test_advanced_stale_cancel.py`
- Result: `16 passed`
- New pulse test covers `_on_regime_detected` with canonical `TREND_DOWN` and verifies:
  - advanced path is taken
  - cancel reason is `CANCEL_STALE_REGIME_ADVANCED`
  - targeted `order_id` is filtered/approved

### Fail-fast regression proof

- `pytest -q tests/config/test_advanced_stale_cancel_config_validation.py`
- Result: `1 passed`
- The test mutates `domains.yaml` to inject `BEAR_TREND` and confirms `ConfigLoader.load_config()` raises `ValidationError("Unknown regime label ...")`

### Separate legacy finding (outside stale-cancel runtime)

- `pytest -q tests/domains/decision_making/test_regime_flip_close.py`
- Result: `3 failed, 4 passed`
- Failures occur because tests still drive `_handle_regime_flip()` with `BULL_TREND/BEAR_TREND`, while runtime logic expects `TREND_UP/TREND_DOWN`

## Fix

### Files changed

- `tests/domains/execution_position/test_advanced_stale_cancel.py`
  - removed legacy mock namespace from default advanced-stale-cancel test config
  - added `_on_regime_detected` pulse regression with canonical regime label
- `tests/config/test_advanced_stale_cancel_config_validation.py`
  - added full ConfigLoader fail-fast regression for phantom regime labels

### Production code

- No runtime code changes were required in stale-cancel path because the current branch is already fixed:
  - canonical config labels present
  - Pydantic validation rejects unknown labels
  - advanced routing is live

## Gates

- `pytest -q tests/domains/execution_position/test_advanced_stale_cancel.py` -> pass
- `pytest -q tests/config/test_advanced_stale_cancel_config_validation.py` -> pass
- `pytest -q tests/domains/decision_making/test_regime_flip_close.py` -> fails due legacy test namespace drift

## TODO / Next Stage

- Consider removing fallback Gate 1 path (`may_cancel_regimes[side] - never_cancel`) and require `allowed_regimes -> cancelable_regimes` derivation on every placed order, so stale-cancel becomes fully per-order and never depends on runtime-side label matching fallback.
