# REPORT — LLM External Intent Path: Listener Wiring Fix

**Date:** 2026-03-20
**Scope:** `LISTENER_NOT_REGISTERED` break for `CMD:EXTERNAL_OPEN_REQUEST_V1`
**Evidence base:** `docs/FORENSIC_REPORT_LLM_INTENT_PATH.md`

---

## Executive Verdict

**FIXED.** The `LISTENER_NOT_REGISTERED` break identified in the forensic report is resolved.

`CMD:EXTERNAL_OPEN_REQUEST_V1` now has a registered consumer in `ExecPosFSM.__init__()`. The event reaches `IntentRouter.on_external_open_request()`, which either:
- **rejects** via `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` (gate failure), or
- **proceeds** to build `CMD:OPEN` and call `self._fsm.handle(cmd_open)` (success path).

Both outcomes are proven by tests.

---

## Evidence Base

### Forensic Report Reference
- `docs/FORENSIC_REPORT_LLM_INTENT_PATH.md`
- **First proven break:** `CMD:EXTERNAL_OPEN_REQUEST_V1` emitted at `21:56:02.520` — zero consumers. ExecPosFSM never registered a listener. `IntentRouter.on_external_open_request()` exists but was unwired.
- **Break classification:** `LISTENER_NOT_REGISTERED`
- **RID:** `c4d939a0-bbbd-4ead-83f3-f3ddd6e6bea7`

---

## Change Summary

### File 1: `apps/reference/domains/execution_position/fsm.py`

**Change A — Bus listener registration (constructor, after line ~453):**
```python
# LLM external intent path: wire CMD:EXTERNAL_OPEN_REQUEST_V1
self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1",
                self._on_external_open_request)
```

**Change B — Thin delegation method (after `_on_trade_intent_rejected`):**
```python
def _on_external_open_request(self, msg: Message) -> None:
    """Phase 14A: Delegated to IntentRouter (LLM external intent path)."""
    self._intent_router.on_external_open_request(msg)
```

### Why ExecPosFSM, not main.py

| Factor | ExecPosFSM | main.py |
|--------|-----------|---------|
| Ownership | ExecPosFSM owns all EP bus listeners (8 existing `self.bus.listen()` calls in `__init__`) | main.py only wires cross-domain listeners (InFlightReconciler, RetryScheduler) |
| Pattern | Matches existing `EVT:TRADE_INTENT_PROPOSED → _on_trade_intent_proposed → intent_router.on_trade_intent_proposed` delegation pattern exactly | Would break the established single-owner pattern |
| Encapsulation | Handler stays internal to execution_position domain | Would expose intent_router internals to main.py |

This is not a hack — it follows the exact same delegation pattern used for all other IntentRouter handlers.

### File 2: `tests/domains/execution_position/test_external_open_request_wiring.py`

New test file with 4 tests (see Tests section).

---

## Runtime Proof

### Test Evidence: Path Advances Past Previous Break

**Previous break:** `CMD:EXTERNAL_OPEN_REQUEST_V1` → DEAD EMIT (zero consumers)

**After fix — reject path (GATE 1):**
```
CMD:EXTERNAL_OPEN_REQUEST_V1 emitted
  → _on_external_open_request() invoked (PROVEN: listener registered)
  → IntentRouter.on_external_open_request() invoked
  → GATE 1 fails (no intent_id)
  → EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1 emitted with reason_code=NRR-EXT-MISSING-INTENT-ID
```

**After fix — success path:**
```
CMD:EXTERNAL_OPEN_REQUEST_V1 emitted (valid payload)
  → _on_external_open_request() invoked
  → IntentRouter.on_external_open_request() invoked
  → GATE 1-6 pass
  → CMD:OPEN Message built (strategy=llm_microstructure, source=external_llm)
  → self._fsm.handle(cmd_open) called
```

Both paths proven by test output (4/4 wiring tests pass, 10/10 combined intent tests pass).

---

## Tests

| Test | What it proves | Result |
|------|---------------|--------|
| `test_external_open_request_listener_registered` | `CMD:EXTERNAL_OPEN_REQUEST_V1` has exactly 1 registered consumer on ExecPosFSM's bus | PASS |
| `test_external_open_request_reaches_intent_router_gate_reject` | Dispatched event reaches handler; missing intent_id triggers `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1` with `NRR-EXT-MISSING-INTENT-ID` | PASS |
| `test_external_open_request_reaches_cmd_open` | Valid payload → handler builds `CMD:OPEN` with correct symbol/side/strategy/metadata and calls `fsm.handle()` | PASS |
| `test_external_open_request_does_not_use_dm_reject_verb` | Reject uses `EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1`, NOT `EVT:TRADE_INTENT_REJECTED` (provenance preserved) | PASS |

```
tests/domains/execution_position/test_external_open_request_wiring.py  4 passed
tests/domains/execution_position/test_external_open_request.py        18 passed, 2 pre-existing failures
```

**Pre-existing failures (not caused by this fix):**
- `test_cooldown_guard_applies` — test mock `capture_emit()` doesn't accept `rid=` kwarg
- `test_exposure_guard_applies` — same test mock issue

---

## Next Boundary

### FACT
- `CMD:EXTERNAL_OPEN_REQUEST_V1` listener is now wired.
- Handler `on_external_open_request()` is invoked.
- On success, `CMD:OPEN` is built and passed to `self._fsm.handle()`.

### INFERENCE
- After `handle(CMD:OPEN)`, the standard ExecPosFSM open-flow runs (exposure guard, order placement, etc.). This is the same path used by DM-originated intents.

### UNPROVEN
1. **`self._fsm.bus.emit()` after `handle()` return** (`intent_router.py:451-457`): The handler calls `self._fsm.bus.emit(f"{result.op}:{result.verb}", ..., rid=result.rid)`. Whether the bus's `emit()` method accepts a `rid=` keyword argument at runtime is unproven. The 2 pre-existing test failures show that mock `emit()` does NOT accept it — this may also be a runtime issue. **Candidate next break: `bus.emit()` signature mismatch on `rid=` kwarg at intent_router.py:453.**
2. **`llm_microstructure.pending_entry_ttl_ms` config presence**: Whether this key exists in production `aurora.yaml` is unproven (affects GATE 6 fallback when `valid_for_ms` is None in the request).
3. **Schema validation for `CMD:EXTERNAL_OPEN_REQUEST_V1` payload**: Schema exists in registry but whether the mapper's payload passes validation at runtime is unproven.

---

## Final Verdict

**Mergeable: YES** — for the scope of this fix package.

The `LISTENER_NOT_REGISTERED` break is resolved. The path now proceeds from `CMD:EXTERNAL_OPEN_REQUEST_V1` through to handler invocation and `CMD:OPEN` construction. The next boundary (post-handle emit signature) is documented but out of scope for this package.

---

## Evidence Appendix

### Grep: Listener now exists in fsm.py
```
grep "EXTERNAL_OPEN_REQUEST" apps/reference/domains/execution_position/fsm.py
# → self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1", self._on_external_open_request)
# → def _on_external_open_request(self, msg: Message) -> None:
```

### Diff summary
```
apps/reference/domains/execution_position/fsm.py:
  +3 lines: bus.listen registration
  +3 lines: _on_external_open_request delegation method

tests/domains/execution_position/test_external_open_request_wiring.py:
  New file: 4 tests proving wiring + downstream path
```

### Test run output
```
$ python -m pytest tests/domains/execution_position/test_external_open_request_wiring.py -v
4 passed in 1.19s

$ python -m pytest tests/domains/execution_position/test_external_open_request_wiring.py \
    tests/execution_position/test_intent_rid_propagation.py \
    tests/domains/execution_position/test_intent_boundary_audit.py -v
10 passed in 2.39s
```
