# R7G Sidecar Economic Input Audit

## Problem Framing
This audit localizes why the peak-giveback Sidecar does not receive usable economic inputs. The question is not whether the Sidecar can classify a lifecycle; the question is where the symbol-scoped economics stop being available.

Evidence base used here:
- [apps/reference/domains/execution_position/position_policy_sidecar.py](apps/reference/domains/execution_position/position_policy_sidecar.py)
- [apps/reference/domains/execution_position/event_handlers.py](apps/reference/domains/execution_position/event_handlers.py)
- [apps/reference/domains/position_tracking/position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py)
- [apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json](apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json)
- [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl)
- [logs/domain_execution_position.log](logs/domain_execution_position.log)

## Source-Path Trace
1. PositionTracking can ingest market ticks through EVT:MARKET_TICK_RECEIVED and cache symbol-level mark prices in its internal _mark_prices map.
2. PositionTracking emits EVT:PORTFOLIO_STATE_UPDATED from trade, account, and balance handlers, but the emitted positions array is minimal: symbol, net_position, avg_entry_price, and venues.
3. The portfolio_state_v1 contract allows only that minimal position shape. It does not require markPrice, unrealizedPnl, or unrealizedPnlPct on each position.
4. Sidecar receives EVT:PORTFOLIO_STATE_UPDATED and normalizes each position into a per-symbol snapshot.
5. Sidecar only copies net_position into positionAmt and avg_entry_price into entryPrice. It does not synthesize markPrice or unrealizedPnl from the aggregate portfolio fields.
6. Sidecar then reads markPrice, unrealizedProfit / unrealizedPnl, and unrealized_pnl_pct from the normalized per-symbol snapshot. If those fields are absent, the economics remain null.

## Runtime Evidence
- The inspected runtime slice contains no EVT:MARKET_TICK_RECEIVED traces in the execution-position logs or the Sidecar lifecycle log.
- The Sidecar lifecycle log shows active per-symbol portfolio snapshots later in the tail, but mark_price and unrealized_pnl_usdt still remain null even when portfolio_snapshot_status is present.
- Earlier lifecycle rows show symbol_absent snapshots, which is expected when no open position is present.
- The runtime does expose aggregate portfolio unrealized_pnl at the portfolio boundary, but that is not the alias Sidecar consumes for peak-giveback economics.

## Inference
The economic inputs are not being lost inside Sidecar. They stop at the portfolio boundary because the emitted portfolio-state contract does not carry symbol-scoped mark-price or per-position PnL fields, and the observed runtime slice does not show a market-tick feed that would populate a symbol cache for export.

## Smallest Safe Corrective Action
The smallest safe fix is an upstream contract and emitter change, not a Sidecar policy change:
- extend the position snapshot schema and emitter to carry symbol-scoped markPrice, unrealizedPnl, and, if available, unrealizedPnlPct;
- populate those fields from the existing mark-price source used by PositionTracking;
- keep Sidecar fail-closed and unchanged so it can consume the fields it already expects.

That preserves ownership boundaries and avoids teaching Sidecar to guess from aggregate portfolio values.
