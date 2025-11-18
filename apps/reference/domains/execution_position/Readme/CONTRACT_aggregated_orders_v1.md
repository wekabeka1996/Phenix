# CONTRACT: Aggregated-Only Orders & TP/SL v1

> RID: OCO-11.1 — canonical specification for execution_position aggregated-only mode.

## 1. Scope & Runtime Mode

- **Scope** — execution_position domain (ExecPosFSM + ManageFlowFSM + OrderGuardian + PositionTracking integration) when `execution.manage.brackets.aggregated_oco.enabled=true` **and** `execution.manage.brackets.aggregated_oco.aggregated_only_mode=true`, i.e. entry orders are emitted without inline TP/SL instructions.
- **Out of scope** — legacy per-order TP/SL payloads (inline `tp_price`, `sl_price`, `stopLoss`, `takeProfit`, client OCO groups). Those paths are **deprecated** and MUST remain disabled while this contract is active.
- **Target behaviour** — entry orders carry only the intent to open/close size; protection is delegated to Aggregated OCO, which owns SL/TP lifecycle for the entire `(symbol, aggregated_side)` position.

## 2. Position Source of Truth

| Layer | Responsibilities | Guarantees |
| --- | --- | --- |
| **PositionTracking** | Listens to `EVT:TRADE_EXECUTED`, `EVT:ACCOUNT_UPDATE_RECEIVED`; maintains ledger `{symbol, qty, avg_price, side}`; emits `EVT:PORTFOLIO_STATE_UPDATED`. | Considered *the* runtime truth for ExecPosFSM. |
| **ExecPosFSM** | Consumes `EVT:PORTFOLIO_STATE_UPDATED`, hydrates `_ws_position_cache` with `PositionSnapshot(symbol, side, qty, avg_price, updated_ts)`. | `_preflight_position_check` MUST rely on this cache before REST fallbacks. |
| **REST /fapi/v2/positionRisk** | Used for DR bootstrap, sanity checks, manual resync. | MUST NOT block hot-path TP/SL placement; invoked only during startup or watchdog recoveries. |

**Decision rule** — TP/SL logic (recalc, placement, cleanup) MUST operate on `EVT:PORTFOLIO_STATE_UPDATED` state plus the local snapshot cache. REST snapshots MAY be used to seed or verify that state but cannot gate live execution.

## 3. Entry & Exit Order Contract

### 3.1 Entry orders (open / scale-in)

- Types: `MARKET` or `LIMIT` (optionally post-only, iceberg, etc.).
- MUST include only quantity/price/routing data.
- MUST NOT include inline TP/SL parameters (`tp_price`, `stopLoss`, `reduceOnly=True`, `closePosition=True`, `ocoOrder`, `attachedOrders`, etc.).
- MUST set `reduceOnly=False` (default) because entry expands exposure.

### 3.2 Exit orders (manual/system close)

- Types: `MARKET` or `LIMIT` flagged with `reduceOnly=True` or `closePosition=True`.
- Used for discretionary exits, emergency flattening, or fail-safe transport issues.
- MUST NOT carry inline TP/SL instructions.

**Invariant** — In aggregated-only mode *no* entry/exit order may attempt to protect itself. All safety orders MUST be installed by Aggregated OCO.

## 4. Aggregated TP/SL Contract (Aggregated OCO Layer)

- Operates per `(symbol, aggregated_side)` where `aggregated_side ∈ {LONG, SHORT}`.
- Inputs: current `position_amt`, `avg_entry_price`, risk config (SL/TP ratios, RR templates), market metadata (tick size, min notional, precision), and ManageFlow state.
- Output: desired aggregated bracket spec `{sl_price, tp_price, qty or closePosition flag, working_type}`.
- **OrderGuardian** materializes this spec by placing / cancelling `reduceOnly | closePosition` orders and storing `BracketSetMeta` (`bracket_set_id`, `symbol`, `side`, `sl_order_id`, `tp_order_id`, `created_ts`, `version`).
- **Zero position** (`position_amt == 0`): MUST have zero reduceOnly/closePosition orders and no `BracketSetMeta`.
- **Positive position** (`position_amt > 0`): MUST have at least one SL order (opposite direction reduceOnly/closePosition). Exactly one `BracketSetMeta` per `(symbol, side)` MUST exist.
- Detailed Guardian semantics remain in `CONTRACT_aggregated_oco_v1.md`; this document supersedes it for higher-level order/position rules.

## 5. Behaviour Scenarios & Guarantees

### Legend

- **Input events** — canonical triggers.
- **Expected state** — required order/position outcome.
- **Invariants / XAI** — must hold + example `why` tags.

| Scenario | Input events | Expected state | Invariants / XAI |
| --- | --- | --- | --- |
| **Open (0 → X)** | Entry fill → `EVT:TRADE_EXECUTED` → `EVT:PORTFOLIO_STATE_UPDATED` (qty = X). | ManageFlow recomputes bracket spec, `OrderGuardian.register_bracket_set` installs one SL+TP pair covering X. | `position_amt > 0 ⇒ has SL` ; log `why="agg_first_entry"` / `why="ensure_sl_for_open_position"`. |
| **Scale-in (X → Y)** | New fill increases qty (cache + PT). | Existing bracket cancelled, new bracket for Y placed, `BracketSetMeta.version++`. | SL coverage continuous (old or new) — no gap; `why="agg_recalc_scale_in"`. |
| **Partial close (Y → Z, 0 < Z < Y)** | Fill from TP/manual exit updates qty to Z. | If config `recalc_on_partial_close=true` ⇒ recompute; else retain current bracket but confirm SL still valid for Z. | No waiting for next entry; if SL missing, immediate placement with `why="partial_close_guard"`. |
| **Full close (→ 0)** | Fill or manual flatten sets qty = 0. | Guardian cancels every reduceOnly/closePosition order, clears `BracketSetMeta`. | Emit `AGG_OCO_BRACKET_GUARD(decision="cleanup_zero_position", why="position_amt_zero")`. |
| **Flip (LONG ↔ SHORT)** | Sequence: full close of old side + open of new side. | Old bracket removed, new aggregated bracket installed for opposite side. | `BracketSetMeta` for old side removed before new registration. |
| **DR / restart** | Startup snapshot + live open orders feed. | PositionTracking seeds state, Guardian rehydrates `BracketSetMeta` from open reduceOnly/closePosition orders before cleanup runs. | `position_amt > 0` & SL present ⇒ rehydrated meta retains ownership; `why="rehydrate_bracket_set"`. |
| **Manual resync / watchdog** | Operator triggers resync or watchdog detects drift. | Watchdog inspects `(positions, open_orders, bracket_metas)` and raises violation if invariants fail; optional auto-heal via `reconcile_symbol`. | Violations log `[AGG_WATCHDOG] why∈{no_sl_for_open_position, orphan_sl_for_zero_position, multiple_meta_sets}`. |

## 6. Watchdog Invariants (Must-Haves)

- `position_amt > 0`:
  - MUST have ≥1 SL reduceOnly/closePosition order pointing opposite to the position side.
  - MUST have exactly one `BracketSetMeta` per `(symbol, side)`.
- `position_amt == 0`:
  - MUST NOT have any reduceOnly/closePosition orders.
  - MUST NOT have `BracketSetMeta`.
- These rules persist across DR, restart, manual reconcilers, and after any failure recovery.

## 7. Legacy Behaviour & Migration Notes

- Inline TP/SL (per-order protection) is tagged **legacy**. Implementations MUST either hard-disable those code paths or guard them behind explicit feature flags so aggregated-only deployments cannot regress.
- Any occurrence of entry payloads containing `tp/sl` data SHOULD raise observability warnings and MUST NOT pass validation once aggregated-only mode is enforced.
- Migration path:
  1. Enable `aggregated_oco.enabled=true`, set `aggregated_only_mode=true`, keep `keep_single_bracket_set=true`, disable inline TP/SL config knobs.
  2. Verify watchdog invariants (section 6) via automated smoke flows.
  3. Remove legacy config from production manifests, leaving this contract as the “constitution” for order behaviour.

---

### Relation to CONTRACT_aggregated_oco_v1

- `CONTRACT_aggregated_orders_v1.md` (this document) governs the *full* order + TP/SL lifecycle for aggregated-only execution.
- `CONTRACT_aggregated_oco_v1.md` remains the authoritative spec for the Aggregated OCO layer itself (BracketSetMeta state machine, TTL protections, Guardian responsibilities). Both contracts MUST be read together; if conflicts arise, this higher-level contract defines the required outcomes while `aggregated_oco_v1` defines how Guardian achieves them.
