# EP-H2-SAFE-EXIT-DEGRADE REPORT

## Summary
Implemented fail-safe reduce-only exit degradation to prevent close intent rejection on missing `tf_sec/TTL` for LIMIT exits. Added separate exit execution policy fields and degradation observability event.

## Files changed
- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `apps/reference/domains/decision_making/schemas/trade_intent_degraded_v1.json`
- `tests/domains/decision_making/test_flip_orchestration_v1.py`
- `tests/domains/decision_making/test_regime_flip_close.py`
- `tests/ops/test_verb_registry_contracts.py`
- `JOURNAL.md`
- `TODO.md`

## Contract/result
- Added additive execution fields: `exit_order_type`, `exit_tif`, `exit_limit_ttl_ms`.
- `reduce_only=True` now resolves policy from `execution.exit_*`, defaulting to `MARKET`.
- LIMIT reduce-only exit without explicit TTL degrades to MARKET (no `NRR-046` reject).
- Added `EVT:TRADE_INTENT_DEGRADED` with payload lineage fields including `strategy_id`.
- `_emit_reduce_only_close` now returns `True` only if intent proposal succeeded.

## Validation commands
- `pytest -q tests/domains/decision_making/test_flip_orchestration_v1.py` → **13 passed**
- `pytest -q tests/domains/decision_making/test_regime_flip_close.py` → **7 passed**
- `pytest -q tests/ops/test_verb_registry_contracts.py -k "trade_intent"` → **2 passed**
