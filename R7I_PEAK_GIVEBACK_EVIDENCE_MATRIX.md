# R7I Peak-Giveback Evidence Matrix

Scope note: this matrix covers the two XRP lifecycles observed in the snapshot. The broad Sidecar suppression stream is summarized in the main report.

| rid | symbol | side | first / last timestamp | evaluated rows | portfolio economics present? | sidecar economics present? | null reasons | max mark_price | max unrealized_pnl_usdt | max current_edge_usd | max peak_edge_usd | max giveback_pct | first armed timestamp | threshold met? | recommendation emitted? | close request emitted? | downstream close observed? | case classification | anomaly flag | notes |
|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `aurora_XRPUSDT_1777509605601` | `XRPUSDT` | `LONG` | `2026-04-30T00:40:05.735Z` -> `2026-04-30T01:00:07.426Z` | `0` | `No` | `No` | `N/A` | `n/a` | `n/a` | `n/a` | `n/a` | `n/a` | `n/a` | `No` | `No` | `No` | `No` | `CASE E` | `No` | Order timed out, then cancelled before fill. No Sidecar lifecycle formed. |
| `aurora_XRPUSDT_1777513802272` | `XRPUSDT` | `LONG` | `2026-04-30T01:50:02.460Z` -> `2026-04-30T08:37:10.403Z` | `4,483` | `No` | `No` | `mark_price:missing_mark_price; unrealized_pnl_usdt:missing_unrealized_pnl_usdt; unrealized_pnl_pct:missing_unrealized_pnl_pct; current_edge_usd:missing_unrealized_pnl_usdt; giveback_pct:missing_current_edge_usd; threshold_crossed:threshold_not_evaluable; early rows also miss entry_price/position_qty/side` | `null` | `null` | `null` | `0.0` | `n/a` | `n/a` | `No` | `No` | `No` | `Yes` | `CASE F` | `No` | Filled lifecycle. Sidecar saw position context, but economics stayed null. Close routing stayed on incumbent EP / CloseExecutor. |

