# Trade Lifecycle Failure Vectors RCA (2026-03-08)

## Scope

This note documents four failure vectors observed in the Aurora / md_amr lifecycle on 2026-03-08.
The analysis is contract-first and follows the current SSOT split:

- CLOSE / OPEN belong to execution_position.
- TRADE_INTENT_PROPOSED belongs to decision_making.
- ACCOUNT_UPDATE_RECEIVED belongs to account_balance.
- ORDER_EXECUTED still has owner=unknown in the registry, which is itself a governance smell for fill telemetry.

Added simulations:

- tests/domains/decision_making/test_trade_lifecycle_failure_vectors_20260308.py
- tests/domains/execution_position/test_inferred_fill_telemetry_blindness_20260308.py

All simulations are marked xfail on purpose. They encode the safe behavior we want, while reproducing the current vulnerability profile.

## Vector 1: Regime Drift and Exit Hostage

### Root cause

AuroraHandler evaluates strict regime allowlist before exit/flip handling.
This means a position can be opened in an allowed regime, drift into a now-disallowed regime, and then have the opposite-side signal blocked before it can become a close/flip intent.

Evidence path:

- decision_making/aurora_handler.py: strict allowlist gate runs before is_exit_signal / is_flip_signal handling.
- decision_making/decision_making.py: reduce_only closes are already treated specially in other paths, so this is inconsistent policy layering.

Failure mode:

1. Position is open.
2. Market regime changes to a regime excluded by allowed_regimes.
3. Strategy generates a close-or-flip signal.
4. Handler emits REGIME_NOT_ALLOWLISTED instead of forwarding the exit leg.
5. Position remains hostage to the gate.

### Architectural fix

Split policy into two explicit classes:

- EntryPolicy: applies allowlist, warmup, symbol-busy, concentration, QoS.
- ExitSafetyPolicy: applies only close-safe checks and must never reject reduce-only risk reduction because of regime allowlist.

Minimum invariant:

- New exposure can be blocked.
- Risk-reducing exposure must always have a pass-through path.

### Pseudocode

```python
def classify_intent(position_side: str, signal_side: str | None) -> str:
    if not position_side and signal_side:
        return "ENTRY"
    if position_side and not signal_side:
        return "EXIT"
    if position_side and signal_side and signal_side.lower() != position_side.lower():
        return "FLIP_CLOSE"
    return "HOLD"


def gate_strategy_signal(signal, state, regime, policies):
    intent_class = classify_intent(state.position_side, signal.side)

    if intent_class in {"EXIT", "FLIP_CLOSE"}:
        return policies.exit_safety.allow_reduce_only(signal, state)

    return policies.entry.allow_new_exposure(signal, state, regime)
```

## Vector 2: Stale Cache / Phantom Symbol Busy

### Root cause

The symbol-busy decision path is not derived from a single authoritative state machine. In current code it can remain blocked by stale in-memory state such as pending flip metadata even after portfolio state is flat.

Evidence path:

- decision_making/decision_making.py: _get_symbol_entry_block_reason() blocks on active_position or pending_flip_close.
- No broker-authoritative reconciliation exists for stale pending_flip entries.

Failure mode:

1. A close or flip sequence starts.
2. Cleanup / terminal event is missed.
3. ACCOUNT_UPDATE says flat, but pending flip marker survives.
4. New intents still get NRR-SYMBOL-BUSY.

### Architectural fix

Move symbol-busy to a lease-based store with explicit expiry and reconciliation:

- source_of_truth = broker/account snapshot + terminal order state.
- local busy entries carry ttl_ms and lifecycle_id.
- any flat broker state invalidates stale busy leases for the symbol.

### Pseudocode

```python
def reconcile_symbol_busy(symbol, broker_qty, busy_lease, now_ms):
    if broker_qty == 0:
        return None

    if busy_lease is None:
        return None

    if busy_lease.expires_at_ms <= now_ms:
        return None

    return busy_lease


def get_symbol_busy(symbol):
    broker_qty = broker_snapshot.position_qty(symbol)
    lease = busy_store.get(symbol)
    reconciled = reconcile_symbol_busy(symbol, broker_qty, lease, clock.now_ms())
    if reconciled is None:
        busy_store.delete(symbol)
    return reconciled
```

## Vector 3: Hot-Reload Ownership Desync

### Root cause

Strategy handlers use current enabled_symbols / assignments both for new entries and for already-open lifecycles. Once hot-reload removes a symbol, the handler silently stops processing bars, trade sync, and close logic for that symbol.

Evidence path:

- decision_making/md_amr_handler.py: symbol not in _enabled_symbols returns early across process, regime, trade executed, and rejection callbacks.
- decision_making/mean_reversion_handler.py follows the same assignment-intersection pattern.

Failure mode:

1. Strategy opens a position under config version N.
2. Hot reload applies config version N+1 where asset.enabled=false.
3. Handler drops the symbol from enabled_symbols.
4. Lifecycle is still live on exchange, but strategy-side management goes dark.

### Architectural fix

Introduce lifecycle-bound config snapshots:

- Opening a position creates lifecycle_id and captures lifecycle_config_version.
- Existing lifecycles stay manageable until terminal state.
- Hot reload affects only admission of new lifecycles, not ownership of active ones.

This is a graceful drain model, not an abrupt detach.

### Pseudocode

```python
def on_config_reload(new_cfg):
    admission_policy.swap(new_cfg)
    for lifecycle in lifecycle_store.active():
        lifecycle.management_policy = lifecycle.management_policy or snapshot_at_open(lifecycle)


def can_strategy_manage(symbol, lifecycle_id, current_cfg):
    lifecycle = lifecycle_store.get(lifecycle_id)
    if lifecycle and not lifecycle.is_terminal:
        return True
    return current_cfg.symbol_enabled(symbol)
```

## Vector 4: Telemetry Blindness / Inferred Fills

### Root cause

REST-discovered fills are translated into local ExecPosFSM handling, but intentionally not broadcast as deterministic global execution events because payload shape is order-centric and incompatible with downstream consumers.

Evidence path:

- execution_position/watchdog.py detects FILLED and emits TRADE_EXECUTED through internal hook payload.
- execution_position/fsm.py explicitly avoids global bus broadcast for watchdog-discovered TRADE_EXECUTED.
- position_tracking relies on TRADE_EXECUTED or ACCOUNT_UPDATE_RECEIVED for state updates.

Failure mode:

1. WebSocket ACCOUNT_UPDATE is delayed or lost.
2. Watchdog REST poll detects fill.
3. ExecPosFSM updates local lifecycle.
4. Global telemetry / position tracking does not receive a canonical fill event.
5. Observability and state reconstruction diverge.

### Architectural fix

Add a canonical fill event in the exchange adapter boundary:

- Exchange adapter emits a normalized execution event with stable schema.
- All sources (WebSocket execution report, REST reconciliation, cancel-precheck discovery) normalize into the same event.
- Deduplication is keyed by venue + order_id + trade_id (or fill sequence fallback).

Registry implication:

- ORDER_EXECUTED / FILL should no longer remain owner=unknown.
- A single execution domain contract should own normalized fill semantics.

### Pseudocode

```python
def normalize_fill(raw, source):
    return CanonicalFillEvent(
        venue=raw.venue,
        order_id=raw.order_id,
        trade_id=raw.trade_id or f"{raw.order_id}:{raw.executed_qty}:{raw.avg_price}",
        symbol=raw.symbol,
        side=normalize_side(raw.side),
        qty=Decimal(raw.executed_qty),
        price=Decimal(raw.avg_price),
        ts_ms=raw.ts_ms,
        source=source,
    )


def publish_fill(raw, source):
    event = normalize_fill(raw, source)
    dedup_key = (event.venue, event.order_id, event.trade_id)
    if fill_dedup.seen(dedup_key):
        return
    fill_dedup.mark(dedup_key)
    bus.emit("EVT:ORDER_FILLED", payload=event.model_dump())
    bus.emit("EVT:TRADE_EXECUTED", payload=event.to_position_tracking_payload())
```

## Recommended implementation sequence

1. Introduce canonical execution event + dedup store.
2. Separate entry gates from risk-reducing exit gates.
3. Add lifecycle-bound config snapshots and graceful drain on hot reload.
4. Replace in-memory symbol busy flags with lease + reconciliation.

## Expected regression portfolio

- Regime drift cannot block reduce-only close.
- Flat broker state clears stale symbol-busy within one reconciliation cycle.
- Disabling a symbol stops new entries but continues managing active lifecycle_id values.
- REST-discovered fills produce canonical global execution telemetry even when ACCOUNT_UPDATE is absent.
