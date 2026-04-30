# R7G Gap List

- The inspected runtime slice does not show EVT:MARKET_TICK_RECEIVED traces, so the symbol-level mark-price cache is not observable in this evidence window.
- The portfolio-state schema only allows minimal position objects, so it blocks markPrice, unrealizedPnl, and unrealizedPnlPct at the contract boundary.
- Sidecar normalizes only net_position and avg_entry_price from each position and does not derive usable economics from aggregate unrealized_pnl.
- As a result, active lifecycle rows can show portfolio_snapshot_status: present while mark_price and unrealized_pnl_usdt remain null.
- No threshold-met case can be proven from the inspected runtime because the economic inputs required for peak-giveback math never become symbol-scoped and usable.
- The smallest safe next step is to widen the upstream position contract to export symbol-scoped markPrice and PnL aliases, then re-run the same runtime proof without changing Sidecar thresholds.
