# R7G Economic Field Trace

## Trace Summary

| Field | Intended source | Exported by PositionTracking | Present in inspected runtime | Consumed by Sidecar | Outcome |
| --- | --- | --- | --- | --- | --- |
| markPrice | EVT:MARKET_TICK_RECEIVED cache or positionRisk-style upstream data | No | No market-tick traces found | Yes, as markPrice | Null |
| unrealizedPnl / unrealized_pnl_usdt | PositionTracking calculation | Yes, only aggregate unrealized_pnl at portfolio level | Yes, as top-level unrealized_pnl | Sidecar expects per-position unrealizedProfit / unrealizedPnl | Null at Sidecar boundary |
| unrealizedPnlPct / unrealized_pnl_pct | Derived from per-position mark price and entry price, or direct field | No | No evidence of export | Yes | Null |
| positionAmt / net_position | PositionTracking positions snapshot | Yes | Yes | Yes, normalized into positionAmt | Present |
| avg_entry_price / entryPrice | PositionTracking positions snapshot | Yes | Yes | Yes, normalized into entryPrice | Present |
| positions_last_ts_ms | PositionTracking freshness marker | Yes | Yes | Yes, for freshness only | Present |
| portfolio_snapshot_status | Sidecar-local usability gate | N/A | Yes, present or symbol_absent | Yes | Gates evaluation, not economics |

## Field-by-Field Notes
- markPrice is the missing symbol-level price input. Without it, Sidecar cannot compute giveback economics from price movement.
- aggregate unrealized_pnl exists upstream, but Sidecar does not consume the aggregate field for peak-giveback math.
- positionAmt and avg_entry_price do reach Sidecar, but they are not sufficient by themselves because the current Sidecar snapshot logic still requires a symbol-level markPrice or unrealizedPnl alias.
- positions_last_ts_ms and portfolio_snapshot_status confirm freshness and presence, but they do not supply economics.

## Boundary Location
- PositionTracking can compute or cache economics internally.
- The exported portfolio-state contract does not surface the symbol-scoped economic fields Sidecar expects.
- The Sidecar normalizer does not backfill those fields from the aggregate portfolio payload.

## Conclusion
The symbol-level economic trace stops at the portfolio-state boundary. Sidecar sees the portfolio update, but the fields it needs for peak-giveback economics are not exported in the shape it consumes.
