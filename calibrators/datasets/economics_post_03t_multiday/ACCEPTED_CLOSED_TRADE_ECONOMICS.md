# ACCEPTED_CLOSED_TRADE_ECONOMICS

- canonical_closed_rows: 12
- exact_roundtrip_rows: 11
- diagnostics_only: True
- promotion_grade: False

| Metric | Value | Notes |
| --- | ---: | --- |
| Total Gross PnL | 171.06727 | canonical realized rows |
| Total Net PnL | 139.18404117 | canonical realized rows |
| Total Fees | 31.88322883 | fees + commission surfaces |
| Profitable Closes | 9 | net pnl > 0 |
| Losing Closes | 3 | net pnl < 0 |
| Fee Share Of Losses % | 28.6212 | fees on losing closes / abs(net losses) |
| Sidecar Realized Closes | 0 | joined by realized rid to POSITION_CLOSED.lifecycle_id |
| Sidecar Net PnL | 0 | observational only |
| Sidecar Fees | 0 | observational only |
| Sidecar Observed POSITION_CLOSED Rows | 15 | order_log POSITION_CLOSED with ppsreq rid |
| Sidecar Observed Net PnL | -92.86671668 | order_log POSITION_CLOSED fallback |
| Sidecar Observed Fees | 39.27871668 | order_log POSITION_CLOSED fallback |
| Bracket TP Closes | 9 | close_reason contains TP |
| Bracket SL Closes | 1 | close_reason contains SL/STOP |
