# R7H Economic Export Field Map

| Field | Source | Nullable / Required | Calculation formula | Owner | Consumer | Null semantics |
| --- | --- | --- | --- | --- | --- | --- |
| `markPrice` | `PositionTracking._mark_prices[symbol]["mark_price"]` populated by `on_market_tick()` | Nullable | Direct source value, no synthesis | `position_tracking` | `execution_position` Sidecar peak-giveback snapshot | `null` means no fresh symbol mark is available for export |
| `unrealizedPnl` | Computed in `PositionTracking` from `markPrice`, `avg_entry_price`, and signed `net_position` | Nullable | `(markPrice - avg_entry_price) * net_position`, quantized to 2 decimals | `position_tracking` | `execution_position` Sidecar `unrealized_pnl_usdt` / `current_edge_usd` | `null` means economics are unavailable, usually because `markPrice` is missing or stale |
| `unrealizedPnlPct` | Computed in `PositionTracking` from per-position PnL and notional | Nullable | `unrealizedPnl / (abs(net_position) * avg_entry_price) * 100`, quantized to 2 decimals | `position_tracking` | `execution_position` Sidecar `unrealized_pnl_pct` | `null` means the percentage cannot be evaluated safely |
| `net_position` | Internal open-position state in PositionTracking | Required | Direct source value | `position_tracking` | Sidecar normalizer maps to `positionAmt` | Not emitted as null for open positions |
| `avg_entry_price` | Internal open-position state in PositionTracking | Required | Direct source value | `position_tracking` | Sidecar normalizer maps to `entryPrice` | Not emitted as null for open positions |
| `venues` | Internal open-position state in PositionTracking | Required | Direct source value | `position_tracking` | Sidecar and downstream audit consumers | Empty list is allowed by the contract shape, but the field itself is required |
| `positions_last_ts_ms` | `get_clock().now_ms()` at portfolio snapshot emission time | Required top-level | Direct timestamp | `position_tracking` | Sidecar freshness gate and portfolio correlation trace | Not applicable; missing or stale timestamps fail closed |

## Notes
- The exported symbol economics are additive to the existing position snapshot shape.
- Aggregate top-level `unrealized_pnl` remains portfolio-wide and is not a substitute for symbol economics.
- The Sidecar does not infer symbol economics from aggregate portfolio values; it consumes the new position fields directly when available.
