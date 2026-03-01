# EP-INT-FLIP-VERTICAL-QTY-FIXTURE REPORT

## Summary
Fixed integration fixture behavior for vertical flip close path after truthful reduce-only close success semantics.

## Files changed
- `tests/integration/test_flip_vertical_dm_bridge_execpos.py`

## Root cause
- Test monkeypatch for `DecisionMaking._propose_trade_intent` emitted an event but returned `None`.
- After H2 hardening, `_emit_reduce_only_close` now returns success only when intent proposal result is non-`None`, so integration flow reported `NRR-FLIP-CLOSE-QTY-INVALID`.

## Fix
- Monkeypatched helper now returns an intent-like payload dict after emitting `EVT:TRADE_INTENT_PROPOSED`.

## Validation commands
- `pytest -q tests/integration/test_flip_vertical_dm_bridge_execpos.py -k vertical_flip_close -vv` → **1 passed**
- `pytest -q tests/integration -k "flip_vertical_dm_bridge_execpos" --maxfail=1` → **1 passed**
