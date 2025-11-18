# Aggregated OCO Production Profile

## Runtime Mode

Aggregated protection for the `execution_position` domain is always deployed in aggregated-only mode. The active configuration (see `config/domains/execution.yaml`) MUST satisfy the following knobs:

- `execution.manage.mode = aggregated_only` (no inline TP/SL payloads)
- `manage.brackets.aggregated_oco.enabled = true`
- `manage.brackets.aggregated_oco.aggregated_only_mode = true`
- `manage.brackets.aggregated_oco.recalc_on_partial_close = true`
- `manage.brackets.aggregated_oco.allow_unprotected_position = false`
- `manage.brackets.aggregated_oco.watchdog.enabled = true`

These guards ensure that all TP/SL logic flows through `ManageFlowFSM` \+ OrderGuardian, while the watchdog continuously enforces ownership per `(symbol, PositionSide)`.

## Operational Invariants

1. **Canonical sides only** — Aggregated OCO operates strictly on `PositionSide.LONG`, `PositionSide.SHORT`, or `PositionSide.FLAT`. Raw `"buy"/"sell"` inputs are normalized by `canonicalize_position_side` before any bracket math or Guardian updates.
2. **Exactly one bracket set per position** — Each `(symbol, PositionSide)` pair owns exactly one `BracketSetMeta`. Registering a new bracket implicitly replaces the prior version.
3. **Zero quantity ⇒ zero protection** — When live WS/portfolio snapshots show `net_qty = 0`, ManageFlowFSM clears Guardian metadata and no SL/TP orders remain for that `(symbol, side)`.
4. **Snapshot truth source** — `get_agg_oco_state_snapshot()` always prefers WS snapshots for quantity/price data, merges ManageFlow FSM state for SL/TP levels, and appends Guardian metadata plus watchdog status.
5. **Observability contract** — `/debug/agg_oco_state` and `auroractl agg-oco-state` rely on the snapshot rows above; breaking the schema blocks operators from validating RID/WHY chains.

## Symbol Profiles (SOLUSDT & BNBUSDT)

| Symbol   | Min Qty | Step Size | Max Position Size | Effective Max Leverage |
|----------|---------|-----------|-------------------|------------------------|
| SOLUSDT  | 0.01    | 0.01      | 5.0 SOL           | 125x (override)        |
| BNBUSDT  | 0.01    | 0.01      | 5.0 BNB           | 125x (override)        |

- Base instrument data sourced from `config/instruments.yaml` (precision, min_notional, tick/step sizes, conservative leverage).
- Production overrides in `config/overrides.yaml` lift the max leverage to 125× for SOLUSDT/BNBUSDT, matching `exposure.leverage_defaults`.
- Exposure guard enforces `per_symbol_cap_pct = 8%` and global directional ratio ≤ 3.0, so even at 125× leverage positions remain bounded by config-layer risk controls.

## Verification & Tests

- `tests/domains/execution_position/test_agg_oco_state_dump.py` ensures `ExecPosFSM.get_agg_oco_state_snapshot()` returns canonical `PositionSide`, merged bracket metadata, and watchdog data for active positions.
- `tests/domains/execution_position/test_agg_oco_symbol_profiles.py` locks the SOLUSDT/BNBUSDT production profile (aggregated-only mode, watchdog flags, min qty/step size, effective leverage) against config regressions.
- Regression triad for `[OCO-11.13]` (canonical sides + state dump + profile) must remain green before promoting config or runtime changes.
