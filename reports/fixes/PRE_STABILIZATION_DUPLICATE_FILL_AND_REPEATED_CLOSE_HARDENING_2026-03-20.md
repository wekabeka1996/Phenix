# REPORT — PRE STABILIZATION DUPLICATE FILL AND REPEATED CLOSE HARDENING

## 1. Executive Summary
Implemented a narrow pre-stabilization hardening package for two live-path risks:
- shared duplicate-fill suppression for `EVT:TRADE_EXECUTED` across WS and watchdog/REST producer paths,
- source-boundary repeated `CMD:CLOSE` suppression before downstream `DEC:CLOSE` propagation.

The package is safe to merge for this scope. It changes runtime behavior only in two explicit cases:
- a second `EVT:TRADE_EXECUTED` with the same exact active-path fill identity is suppressed before listeners run,
- a repeated `CMD:CLOSE` for the same symbol and same effective portfolio state within the existing anti-race close window is suppressed before `CloseFlowFSM` emits another `DEC:CLOSE`.

It does not migrate FSMs, redesign contracts, rewrite restore, or change sizing/risk/order placement semantics for the first legitimate attempt.

## 2. Scope
Changed active paths:
- `binance_ws_client` / watchdog co-emission path into `FSMCore.emit("EVT:TRADE_EXECUTED", ...)`
- `ExecPosFSM.handle(CMD:CLOSE)` source boundary
- portfolio-update path used to observe state change for close-guard resets
- shadow-journal capture list so suppression remains observable

Intentionally untouched:
- `ManageFlowFSM` / `CloseFlowFSM` architecture
- adapter placement semantics
- restore/hydrate design
- broad event contract redesign
- distributed or restart-persistent idempotency

## 3. Active Path Confirmed
### FACTS
- WebSocket live fills are emitted from `apps/reference/adapters/binance_ws_client.py` as `EVT:TRADE_EXECUTED` on `FILLED`.
- Watchdog REST fallback emits the same verb from `apps/reference/domains/execution_position/watchdog.py`.
- `FSMCore.emit()` is the shared choke point both producers pass through before any listener callback runs.
- `PositionTracking` and other consumers subscribe directly to `EVT:TRADE_EXECUTED`.
- Repeated close propagation enters execution at `ExecPosFSM.handle(CMD:CLOSE)` and then flows into `CloseFlowFSM.handle()` which emits `DEC:CLOSE`.

### INFERENCES
- The narrowest shared duplicate-fill guard is the bus seam in `FSMCore.emit()`.
- The earliest safe repeated-close guard is `ExecPosFSM.handle(CMD:CLOSE)` before `CloseFlowFSM` emits another downstream close decision.

### ASSUMPTIONS
- Current live `EVT:TRADE_EXECUTED` usage represents a terminal order-fill truth event, not distinct per-trade partial fills.

### UNKNOWNS
- Whether future producers will emit `EVT:TRADE_EXECUTED` without `orderId`.
- Whether autonomous non-`CMD:CLOSE` close paths need the same guard in a later package.

Instrumented active chain:

`Binance WS FILLED -> FSMCore.emit(EVT:TRADE_EXECUTED) -> shared fill dedupe -> listeners`

`Watchdog REST FILLED -> FSMCore.emit(EVT:TRADE_EXECUTED) -> shared fill dedupe -> listeners`

`DecisionMaking / reduce_only route -> ExecPosFSM.handle(CMD:CLOSE) -> close source guard -> CloseFlowFSM.handle -> DEC:CLOSE`

## 4. Fill Dedupe Design
### FACTS
- New owner: `FSMCore._execution_truth_hardening`
- Key basis in covered path: `trade_executed:{SYMBOL}:order_id={orderId}`
- Suppression point: inside `FSMCore.emit()` after shadow-journal event capture and before listener callbacks
- Lifetime: existing `domains.execution_position.event_dedup.ttl_ms`
- Bounded memory: existing `domains.execution_position.event_dedup.max_size`
- Restart behavior: in-memory only; state is lost on process restart

### INFERENCES
- For the current active path, `symbol + orderId` is exact enough because both WS and watchdog emit the same terminal fill truth for the same exchange order.
- Suppressing at the shared bus seam protects all listeners, including `PositionTracking`, instead of only protecting one downstream consumer.

### ASSUMPTIONS
- Same `orderId` should not represent multiple distinct `EVT:TRADE_EXECUTED` truths on the active path.

### UNKNOWNS
- If future producers emit per-trade partial execution truth on the same verb, this key will be too coarse and must be revisited.

If `orderId` is missing, the code fails open and does not suppress. That is intentional.

### Table A — Fill Dedupe Matrix
| Producer path | Consumer path | Identity basis | Exact or heuristic? | Suppression point | Residual risk |
|---|---|---|---|---|---|
| Binance WS `FILLED` | All `EVT:TRADE_EXECUTED` listeners | `symbol + orderId` | Exact for current active path | `FSMCore.emit()` | No suppression if `orderId` missing |
| Watchdog REST `FILLED` | All `EVT:TRADE_EXECUTED` listeners | `symbol + orderId` | Exact for current active path | `FSMCore.emit()` | In-memory only; restart loses guard |

## 5. Repeated Close Guard Design
### FACTS
- Guard location: `ExecPosFSM.handle(CMD:CLOSE)` before `CloseFlowFSM.handle()`
- Guard owner: `FSMCore._execution_truth_hardening`, queried from `ExecPosFSM`
- Guard key: `cmd_close:{SYMBOL}:position={portfolio_position_signature}:qty={requested_qty|FULL}`
- Position signature source: current `_latest_portfolio_state`
- Position signature forms:
  - `LONG:<abs(positionAmt)>`
  - `SHORT:<abs(positionAmt)>`
  - `FLAT:0`
  - `UNKNOWN`
- Lifetime: existing `trading.execution.anti_race_close_ms`
- Restart behavior: in-memory only; state is lost on process restart

### INFERENCES
- Using the current portfolio position signature is safer than using only `rid`, because it allows a legitimate new close after real state change even if the request lineage is reused.
- Reusing the existing anti-race close window keeps this package narrow and aligned with existing close-in-flight semantics.

### ASSUMPTIONS
- The highest-confidence repeated-close risk is near-duplicate propagation in the same local state window, not long-delayed retries.

### UNKNOWNS
- Whether some environments need a longer close guard than `anti_race_close_ms`.

Legitimate retry rules:
- Allowed immediately if position signature changes.
- Allowed after guard TTL expiry if state did not change.
- If position signature is `UNKNOWN`, the guard falls back to `rid`; if both are unavailable, it fails open.

### Table B — Repeated Close Matrix
| Scenario | Old behavior | New behavior | Guard basis | Residual risk |
|---|---|---|---|---|
| Same `CMD:CLOSE`, same symbol, same open position state, same window | Repeated `DEC:CLOSE` propagation | Second request suppressed | `symbol + position_signature + qty` | Retry allowed after TTL even if still open |
| Same `CMD:CLOSE`, position size changed | Repeated `DEC:CLOSE` propagation | New close allowed | Changed position signature | Depends on portfolio update freshness |
| Same `CMD:CLOSE`, state unknown, same `rid` | Repeated `DEC:CLOSE` propagation | Second request suppressed | `symbol + rid + qty` | Fail-open if both signature and `rid` missing |

## 6. Files Changed
| File | Function/Class | Purpose | Behavior risk |
|---|---|---|---|
| `apps/reference/domains/execution_position/truth_hardening.py` | `ExecutionTruthHardening` and helpers | Shared in-memory fill/close hardening state and identity helpers | Low |
| `vfoundation/core/fsm_core.py` | `FSMCore.emit()` | Shared duplicate-fill suppression before listener callbacks | Medium |
| `apps/reference/domains/execution_position/fsm.py` | `ExecPosFSM.handle()` | Source-boundary repeated `CMD:CLOSE` suppression | Medium |
| `apps/reference/domains/execution_position/event_handlers.py` | `on_portfolio_state_updated()` | Observe portfolio state transitions for close-guard state discipline | Low |
| `apps/reference/domains/position_tracking/position_tracking.py` | `PositionTracking.__init__()` | Ensures shared hardening attaches even when PositionTracking is the first consumer | Low |
| `apps/reference/telemetry/shadow_journal.py` | `DEFAULT_CRITICAL_EVENTS` | Capture new suppression records | Low |
| `apps/reference/config_models.py` | `ShadowCriticalEventJournalConfig` defaults | Keep typed observability defaults aligned | Low |
| `config/aurora/observability.yaml` | `shadow_journal.critical_events` | Capture suppression records in live config | Low |
| `tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py` | new tests | Proves hardening behavior and observability | None |

## 7. Behavioral Changes
- `FSMCore.emit("EVT:TRADE_EXECUTED", ...)` now suppresses the second callback dispatch when the same covered fill identity (`symbol + orderId`) is seen again within the existing event-dedup lifetime.
- `ExecPosFSM.handle(CMD:CLOSE)` now returns `None` instead of another downstream `DEC:CLOSE` when the same effective close request is repeated within the existing anti-race close window.
- Both suppression decisions now generate explicit shadow-journal records.

## 8. Observability Integration
Existing observability preserved:
- The original `EVT:TRADE_EXECUTED` emit is still journaled.
- The duplicate attempt is also still journaled, and the second event keeps the existing duplicate heuristic marker when origin changes (`websocket` vs `watchdog`).

New explicit suppression records:
- `HARDENING:TRADE_EXECUTED_SUPPRESSED`
- `HARDENING:CMD_CLOSE_SUPPRESSED`

Example smoke evidence summary:
- Duplicate fill produced:
  - first `EVT:TRADE_EXECUTED` from `websocket`
  - second `EVT:TRADE_EXECUTED` from `watchdog` with `suspected_duplicate=true`
  - `HARDENING:TRADE_EXECUTED_SUPPRESSED` with note `fill_key=trade_executed:BTCUSDT:order_id=777`
- Repeated close produced:
  - `HARDENING:CMD_CLOSE_SUPPRESSED` with note `guard_key=cmd_close:BTCUSDT:position=LONG:0.01:qty=FULL`

### Table C — Observability Matrix
| Event/Scenario | Shadow record emitted? | Suppression visible? | Exact or heuristic? | Notes |
|---|---|---|---|---|
| First live fill | Yes | N/A | Exact identity available but not used for suppression yet | Standard `EVT:TRADE_EXECUTED` record |
| Duplicate WS/REST fill attempt | Yes | Yes | Exact suppression, heuristic duplicate marker also present on second event record | Both attempt and suppression remain visible |
| Repeated `CMD:CLOSE` in same state | Yes | Yes | Exact relative to current portfolio state signature | Suppression record is explicit |
| Legitimate new close after state change | Yes | No suppression | Exact state change basis | New close allowed through |

## 9. Tests Added / Updated
- `test_shared_trade_executed_dedupe_suppresses_cross_origin_duplicate_before_callbacks`
  - Proves shared bus-level suppression for duplicate WS/watchdog fills and visible journal evidence.
- `test_shared_trade_executed_dedupe_allows_distinct_orders`
  - Proves legitimate distinct fills are not suppressed.
- `test_position_tracking_only_applies_duplicate_fill_once`
  - Proves the authoritative position truth consumer is protected from duplicate fill application.
- `test_execpos_cmd_close_guard_suppresses_repeated_close_and_allows_after_state_change`
  - Proves repeated close suppression and legitimate close retry after real position change.

## 10. Validation Evidence
Commands run:

```powershell
python -m py_compile apps/reference/domains/execution_position/truth_hardening.py `
  apps/reference/domains/execution_position/fsm.py `
  apps/reference/domains/execution_position/event_handlers.py `
  apps/reference/domains/position_tracking/position_tracking.py `
  apps/reference/telemetry/shadow_journal.py `
  apps/reference/config_models.py `
  vfoundation/core/fsm_core.py `
  tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py
```

Result:
- success

```powershell
python -m pytest tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py -q
```

Result:
- `4 passed in 2.55s`

```powershell
python -m pytest `
  tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py `
  tests/telemetry/test_shadow_critical_event_journal.py `
  tests/domains/execution_position/test_close_flow_cmd_close_always_emits_dec_close.py `
  tests/domains/test_watchdog_polling_fix.py -q
```

Result:
- `12 passed in 3.47s`

```powershell
python -m pytest tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k trade_executed_marks_order_index_terminal -q
```

Result:
- `1 passed, 29 deselected in 1.42s`

```powershell
python -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader().load_config(); print(cfg.observability.shadow_journal.path); print(cfg.trading.execution.anti_race_close_ms); print(cfg.domains.execution_position.event_dedup.ttl_ms)"
```

Result:
- `logs/shadow_critical_event_journal_v1.jsonl`
- `800`
- `86400000`

### Table D — Validation Matrix
| Scenario | Expected behavior | Proven by code? | Proven by test? | Notes |
|---|---|---|---|---|
| WS + watchdog duplicate fill | Second listener dispatch suppressed | Yes | Yes | Shared bus seam |
| Distinct fills | Both dispatches allowed | Yes | Yes | Different `orderId` |
| Duplicate fill against PositionTracking | Position updated once | Yes | Yes | WAL append patched in test to avoid side effects |
| Repeated close same state | Second `CMD:CLOSE` suppressed | Yes | Yes | Source-boundary guard |
| New close after real state change | Allowed | Yes | Yes | Position signature changed |
| Close retry after TTL expiry | Allowed | Yes | No | Covered by code path, not directly timed in test |
| Restart persistence | Guard state lost on restart | Yes | No | In-memory only by design |

## 11. Safety Assessment
### FACTS
- No FSM migration was introduced.
- No order placement contract was changed.
- No adapter API was changed.
- No new canonical truth store was introduced.
- The new hardening state is explicit, local, in-memory, and observable through the shadow journal.

### INFERENCES
- This is a narrow enough package for pre-stabilization because it hardens only two proven live-path risks and reuses existing config lifetimes.

### ASSUMPTIONS
- Existing `anti_race_close_ms` is an acceptable pre-stabilization close-source guard lifetime.

### UNKNOWNS
- Whether production needs a longer repeated-close window after more journal evidence is gathered.

Remaining blast radius:
- Duplicate fill suppression is only as strong as current `orderId` coverage.
- Repeated close suppression is only guaranteed inside the anti-race close window.
- Restart clears both in-memory guards.

## 12. Limitations
- No restart-persistent idempotency. Process restart loses dedupe/guard memory.
- No suppression for `EVT:TRADE_EXECUTED` when `orderId` is absent.
- No broad dedupe for other fill-like verbs.
- No new guard for autonomous/internal close paths that bypass `CMD:CLOSE`.
- No replay engine or restore rewrite.

## 13. Long-Term Goal Alignment
### FACTS
- The package uses explicit identity keys, explicit suppression reasons, and explicit shadow records.

### INFERENCES
- This moves the system toward a canonical replayable truth plane because later work can compare:
  - emitted duplicate attempts,
  - exact suppression decisions,
  - state-aware close guard outcomes,
  without guessing from side effects alone.

### ASSUMPTIONS
- Later packages will promote these identities into stronger contract-level truth surfaces rather than leaving them as local runtime discipline only.

### UNKNOWNS
- The eventual canonical fill identity may need exchange trade IDs or richer execution lineage.

## 14. Next Recommended Package
Execution truth continuation package:
- harden non-`CMD:CLOSE` close paths, especially any direct/internal `DEC:CLOSE` emitters,
- verify and, if necessary, upgrade `EVT:TRADE_EXECUTED` contract identity to include a stable execution identifier beyond `orderId`,
- define restart-aware replay/restore behavior for idempotency state.

## REPORT Appendix
### files changed
- `apps/reference/domains/execution_position/truth_hardening.py`
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/event_handlers.py`
- `apps/reference/domains/position_tracking/position_tracking.py`
- `vfoundation/core/fsm_core.py`
- `apps/reference/telemetry/shadow_journal.py`
- `apps/reference/config_models.py`
- `config/aurora/observability.yaml`
- `tests/domains/execution_position/test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py`

### key code snippets
```python
# shared fill dedupe seam
key = f"trade_executed:{symbol}:order_id={order_id}"
if self._fill_deduper.seen(key):
    suppress = True
```

```python
# repeated close guard
key = f"cmd_close:{symbol}:position={position_signature}:qty={requested_qty}"
if current and current.key == key and age_ms <= self.close_guard_ttl_ms:
    suppress = True
```

### suppression/dedupe config basis
```yaml
trading:
  execution:
    anti_race_close_ms: 800

domains:
  execution_position:
    event_dedup:
      max_size: 100000
      ttl_ms: 86400000
```

### example shadow records showing suppression decisions
```json
{
  "event_name": "HARDENING:TRADE_EXECUTED_SUPPRESSED",
  "event_origin_type": "watchdog",
  "symbol": "BTCUSDT",
  "order_id": "777",
  "notes": [
    "duplicate_trade_executed_same_order_identity",
    "fill_key=trade_executed:BTCUSDT:order_id=777",
    "exact_identity"
  ]
}
```

```json
{
  "event_name": "HARDENING:CMD_CLOSE_SUPPRESSED",
  "event_origin_type": "execution",
  "symbol": "BTCUSDT",
  "notes": [
    "duplicate_cmd_close_same_effective_state",
    "guard_key=cmd_close:BTCUSDT:position=LONG:0.01:qty=FULL",
    "requested_qty=FULL"
  ]
}
```

### Table E — Non-Goals Matrix
| Non-goal | Why excluded |
|---|---|
| FSM migration | Unsafe at current evidence level; outside narrow pre-stabilization scope |
| Restore/hydrate redesign | Needs a separate truth/replay package |
| Contract redesign for all execution verbs | Too broad for this pass |
| Global canonical WAL | Shadow journal remains the observability plane only |
| Adapter rewrite | Not required to reduce the two targeted risks |
