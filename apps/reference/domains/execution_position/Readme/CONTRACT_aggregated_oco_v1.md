# CONTRACT: Aggregated OCO v1 (execution_position)

> **Scope note**: This document describes the Aggregated OCO layer (BracketSetMeta, Guardian behaviour, TTL rules). For the higher-level aggregated-only order contract (entry/exit rules, position sources, watchdog invariants) see [`CONTRACT_aggregated_orders_v1.md`](./CONTRACT_aggregated_orders_v1.md). If requirements conflict, the orders contract defines the expected outcomes while this file specifies how the Aggregated OCO layer fulfils them.

## 1. Terms and Entities

- **position** — aggregated position per `(symbol, side)` that tracks `qty` and `avg_entry_price`.
- **entry_order** — any order used to open or scale the position.
- **bracket_set** — logical pair `TP + SL` that protects the whole position.
- **bracket_set_id** — identifier of the active bracket set for `(symbol, side)`.
- **guardian_client_order_id** — structured clientOrderId used by OrderGuardian to recognise managed orders.
- **parent_entry_id** — exchange `orderId` of the initial entry (legacy concept, not the anchor for Aggregated OCO).
- **aggregated_side** — canonical (`LONG`/`SHORT`) representation derived from fills (`BUY`/`SELL`) before ManageFlowFSM or OrderGuardian touch aggregated state.

## 2. Invariants

1. At most one active `bracket_set` exists for any `(symbol, side)` pair.
2. If `position_amt > 0` then either a valid SL exists in the active `bracket_set` **or** `allow_unprotected_position = true` is explicitly enabled.
3. Every order inside a `bracket_set`:
   - must use `reduceOnly=True` or `closePosition=True`;
   - must present a valid `guardian_client_order_id`.
4. Cleanup flows must never leave `position_amt > 0` without SL unless `allow_unprotected_position=true`.
5. `bracket_set` linkage is keyed by `(symbol, side)` / `position_id`, never by `parent_entry_id`.
6. Aggregated OCO components operate only on canonical sides (`LONG`/`SHORT`); raw `BUY/SELL` inputs must be normalized before registering, rehydrating, or clearing metadata.

## 3. Scenarios

### 3.1. First entry

- `position_amt: 0 → >0`.
- ManageFlow:
  - computes aggregated TP/SL via `compute_aggregated_brackets`.
  - installs the first `bracket_set`.
- Guardian:
  - registers `bracket_set_id` for `(symbol, side)`.

### 3.2. Scale-in

- `position_amt` increases and `avg_entry_price` updates.
- ManageFlow:
  - invokes `compute_aggregated_brackets` for the updated position;
  - creates a new `bracket_set` (new `bracket_set_id`);
  - initiates cancellation of the previous `bracket_set`.
- Guardian:
  - guarantees there is always an SL (old or new) and no gaps without SL.

### 3.3. Partial-close

- `position_amt` decreases (avg price may change depending on implementation).
- Governed by `aggregated_oco.recalc_on_partial_close`:
  - `true` — recompute TP/SL for the reduced position;
  - `false` — retain the previous `bracket_set`, yet never allow the position to stay without SL.

### 3.4. Full close

- `position_amt: >0 → 0`.
- ManageFlow:
  - triggers complete position exit.
- Guardian:
  - removes all `reduceOnly` / `closePosition` orders for `(symbol, side)`;
  - clears the stored `bracket_set_id` as soon as adapters report `position_amt = 0` to avoid stale DR metadata.
  - emits `AGG_OCO_BRACKET_GUARD(decision="cleanup_zero_position")` so observability shows when zero-position cleanup purges outstanding brackets.

### 3.5. Flip (LONG → SHORT / SHORT → LONG)

- Treated as:
  - full close of the old side;
  - new `first entry` on the opposite side.
- The old `bracket_set` is purged entirely, while a fresh one is created for the new `side`.

### 3.6. Restart / Recovery

- After restart the FSM / Guardian state is empty while adapters rehydrate positions and open orders.
- Guardian:
  - reconstructs the active `bracket_set` using open orders with `guardian_client_order_id` and the current `(symbol, side)` position;
  - must not delete SL/TP if the position remains open.

## 4. Component Roles

### 4.1. ManageFlowFSM (`execution_position/fsm_manage.py`)

- Operates on aggregated positions instead of individual entries.
- Tracks `(symbol, side)` exposure (`qty`, `avg_entry_price`, `last_entry_reason`).
- Calls `compute_aggregated_brackets` for:
  - first entry events,
  - scale-in events,
  - (configurable) partial-close events,
  - fail-closed partial closes when SL is cancelled externally.
- Emits DEC events to place new `bracket_set` orders, cancel superseded brackets, and register `BracketSetMeta` via `OrderGuardian.register_bracket_set`, always passing the canonical `LONG`/`SHORT` side.
- Enforces `why` strings ≤ 80 chars for every aggregated action (e.g. `agg_scale_in_recalc`, `agg_partial_close_guard`).
- Emits XAI log `AGG_OCO_BRACKET_SET_CHANGED` with payload `{symbol, side, bracket_set_id, reason}` for every recalculation / reinstall / flip / DR rehydrate.

### 4.2. OrderGuardian (`order_guardian.py`)

- Maintains a map `[(symbol, side)] ? bracket_set_id + {sl, tp, created_ts, version}` (stored as `BracketSetMeta`) keyed strictly by `(symbol.upper(), side ? {LONG, SHORT})`.
- Provides `rehydrate_bracket_set_for_position` to rebuild metadata from live open orders during DR / restart phases before any cleanup executes.
- Guarantees a single valid `bracket_set` per `(symbol, side)` and prevents naked positions by running `ensure_single_bracket_set_for_position`.
- Uses `ttl_protect_new_bracket_ms` to shield newly placed brackets from premature cleanup and logs `AGG_OCO_BRACKET_GUARD` (`decision`, `why`, `has_sl_after`).
- Applies fail-closed logic (`allow_unprotected_position=false`) so cleanup never removes the last SL when `position_amt > 0`, and drops the metadata immediately once adapters report `position_amt = 0`.

## 5. Observability & DR

- **XAI events:**
  - `AGG_OCO_BRACKET_SET_CHANGED` — emitted by ManageFlowFSM on create / recalc / flip / rehydrate (`action` field signals reason: `first_entry`, `scale_in`, `partial_close`, `flip`, `rehydrate`).
  - `AGG_OCO_BRACKET_GUARD` — emitted by OrderGuardian on TTL guards, cleanup, fail-closed skips, extra bracket cancellation.
- **DR / restart:**
  - ExecPos startup fetches live positions + orders, then calls `OrderGuardian.rehydrate_bracket_set_for_position` per `(symbol, side)` before linking orders or running cleanup.
  - Smoke scenario: restart with open position + SL/TP must keep SL intact and maintain `BracketSetMeta` (see `tests/domains/execution_position/test_aggregated_oco_dr_restart.py`).

## 6. Aggregated OCO Configuration

This contract is backed by the following config v2 block:

```yaml
execution:
  manage:
    brackets:
      aggregated_oco:
        enabled: true
        recalc_on_scale_in: true
        recalc_on_partial_close: false
        ttl_protect_new_bracket_ms: 3000
        allow_unprotected_position: false
```

- `enabled` — toggles Aggregated OCO v1 behaviour.
- `recalc_on_scale_in` — recompute TP/SL whenever the position scales in.
- `recalc_on_partial_close` — recompute TP/SL after partial closes.
- `ttl_protect_new_bracket_ms` — TTL that keeps the new `bracket_set` safe from cleanup races.
- `allow_unprotected_position` — experimental mode that allows SL-less positions (defaults to `false`).

When `aggregated_oco.enabled=true`, the legacy `keep_single_bracket_set` flag is considered deprecated.

## 7. Test Scenarios (TDD)

1. First entry installs the aggregated OCO set.
2. Multi scale-in keeps exactly one valid `bracket_set` while SL covers the full position.
3. Partial-close:
   - `recalc_on_partial_close=true` recomputes brackets;
   - `recalc_on_partial_close=false` retains prior brackets yet forbids SL gaps.
4. Full close wipes orders and `bracket_set` metadata.
5. Flip (LONG ↔ SHORT) resets the previous `bracket_set` and spawns a new one for the opposite side.
6. Restart / recovery rebuilds `bracket_set` without losing SL/TP protection.
7. Edge cases:
   - race between placement and cleanup;
   - inconsistent adapter state (orders exist while position is absent);
   - `allow_unprotected_position=true` semantics.
