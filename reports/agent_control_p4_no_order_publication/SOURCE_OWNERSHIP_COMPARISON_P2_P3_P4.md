# Source ownership comparison: P2 / P3 / P4

| Dimension | P2 | P3 | P4 |
|---|---|---|---|
| BTC/ETH market | stale bounded decision fallback; prices missing | fresh publication relay | fresh direct main publication |
| BTC/ETH features | missing | fresh publication relay | fresh direct main publication |
| Execution diagnostics | runtime missing | relay envelope, runtime missing | direct execution-owner publication, partial readiness |
| Freshness per packet | 3 fresh / 3 stale / 2 missing | 8 / 0 / 0 | 8 / 0 / 0 |
| Packet bytes | 11,629-11,632 | 9,734-9,737 | 11,293-11,295 |
| Estimated tokens | 2,908 | 2,434-2,435 | 2,824 |
| Round trip | 2,094-2,443 ms | 14-48 ms | 9-40 ms |
| Operational risk | stale/missing truth | relay lifecycle/ownership | controlled no-order main; broader GET-only observation runtime remains |

Position and business-warning cards still use bounded observational sources. Global ownership remains mixed because portfolio truth is not part of the market publication.
