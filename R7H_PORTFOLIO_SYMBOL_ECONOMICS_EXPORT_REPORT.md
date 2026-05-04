# R7H Portfolio Symbol Economics Export Report

## Problem Framing
R7G localized the blocker to the upstream portfolio-state boundary: PositionTracking exported only minimal position snapshots, so Sidecar could not receive symbol-scoped economics without guessing. This package adds those economics at the boundary and keeps Sidecar policy logic unchanged.

## FACTS
- `PositionTracking.on_market_tick()` caches symbol mark prices in `_mark_prices` from `EVT:MARKET_TICK_RECEIVED` payloads.
- `PositionTracking._get_positions_snapshot()` previously exported only `symbol`, `net_position`, `avg_entry_price`, and `venues`.
- The authoritative portfolio-state schema is `apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json`, which is the path registered in `apps/reference/dictionaries/verb_registry_v1.yaml`.
- Sidecar already reads `markPrice`, `unrealizedProfit` / `unrealizedPnl`, and `unrealized_pnl_pct` / `unrealizedPnlPct` aliases.
- The new contract fields are additive and nullable: `markPrice`, `unrealizedPnl`, and `unrealizedPnlPct`.
- Focused pytest validation passed for the new schema, emitter, and Sidecar regression tests.

## INFERENCES
- The authoritative source for `markPrice` is the fresh symbol mark cache in PositionTracking, populated by market ticks.
- Per-position unrealized PnL can be computed safely from `markPrice`, `avg_entry_price`, and `net_position` using the futures sign convention already used in the aggregate helper.
- Sidecar does not need a new fallback path because it already understands the canonical aliases once the upstream snapshot exports them.
- Keeping the fields nullable preserves fail-closed semantics when a fresh mark is not available.

## ASSUMPTIONS
- A fresh cached mark price is a better export boundary than inventing any fallback price.
- The existing 5-second freshness threshold for mark cache usability is acceptable for the emitted symbol economics.
- The additive typed compatibility model is sufficient once the authoritative JSON schema and emitter are updated.

## UNKNOWNS
- Live runtime coverage for all symbols is not proven yet; this package only proves the boundary and the unit/integration slices.
- The actual live mark tick cadence during the next runtime slice is not yet proven.
- Any downstream consumer outside the validated Sidecar path may still have its own assumptions about the position payload shape.

## Exact Source of `markPrice`
- Source: `PositionTracking._mark_prices[symbol]["mark_price"]`.
- Population path: `PositionTracking.on_market_tick()` reads `mid` or `price` from `EVT:MARKET_TICK_RECEIVED` and calls `update_mark_price()`.
- Usability rule: the mark must be fresh enough to pass the existing stale-mark threshold before it is exported.

## Exact PnL Formula
- Per-position unrealized PnL: `(mark_price - entry_price) * quantity`.
- Long positions profit when mark price rises above entry; short positions profit when mark price falls below entry because the signed quantity carries the direction.
- Per-position PnL percentage: `unrealized_pnl / (abs(quantity) * entry_price) * 100` when notional is positive.
- Both values are quantized to two decimal places before export.

## Schema Changes
- Added nullable per-position fields in the portfolio-state schema:
  - `markPrice`
  - `unrealizedPnl`
  - `unrealizedPnlPct`
- Preserved `additionalProperties: false` on each position object.
- Left existing required fields unchanged.
- Updated the duplicate root schema file to avoid drift.

## Emitter Changes
- `PositionTracking._get_positions_snapshot()` now exports the new symbol economics when the cached mark is fresh.
- If a fresh mark is unavailable, the new fields are emitted as `null`.
- The aggregate portfolio `unrealized_pnl` behavior was left unchanged.
- No Sidecar thresholds, routing, or trigger math were modified.

## Sidecar Compatibility Findings
- `PositionPolicySidecar` already consumes `markPrice` directly.
- `PositionPolicySidecar` already accepts `unrealizedProfit` or `unrealizedPnl`.
- `PositionPolicySidecar` already accepts `unrealized_pnl_pct` or `unrealizedPnlPct`.
- No Sidecar fallback from aggregate portfolio PnL was added or needed.
- Existing null-reason handling remains the fail-closed path when economics are absent.

## Validation Evidence
- `get_errors` on the touched Python code files returned no errors.
- Pytest slice: 55 tests passed across the new contract test, the typed payload tests, the new PositionTracking emitter tests, the Sidecar regression tests, and the existing portfolio-field regression file.
- The validated slice showed long, short, and unavailable-mark cases behaving as intended.

## Residual Risks
- Runtime proof is still required on a live slice with the verified build.
- If the market tick feed is absent or stale in live operation, the exported symbol economics will remain null and Sidecar will continue to fail closed.
- The new fields are exportable now, but the next runtime slice must prove they are populated in real traffic.
