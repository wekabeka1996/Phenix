# NRR062_OVERRIDE_RUNTIME_LEDGER

## Executive Summary
The frozen runtime window contains 1 order_log row(s) with nrr062_segment_override_applied=true across 1 unique rid(s). Canonical realized data confirms 1 realized row(s) for the admitted override cohort with net PnL 22.6742616 quote.

## Proven Facts
- Bundle root: logs/frozen/nrr062_fresh_capture_20260515_180927
- order_log window: 2026-05-11T15:09:59.999000+00:00 to 2026-05-15T13:59:59.999000+00:00
- trade_lifecycle malformed lines skipped: 7
- Override-applied order_log rows: 1
- Override-applied shadow journal rows: 1
- Objective dataset rows for override rid(s): 1
- Objective rows preserving override token: 0
- Decision ledger rows preserving override token: 0
- Realized rows for override rid(s): 1
- Realized exact roundtrip rows for override rid(s): 1

## Ledger Table
| rid | symbol | side | outcome | net_pnl_quote | sidecar_rows | decision_ledger_terminal_status |
| --- | --- | --- | --- | ---: | ---: | --- |
| aurora_BTCUSDT_1778845805903 | BTCUSDT | short | closed_win | 22.6742616 | 948 | INVALID_FOR_DATASET |

## Residual Risk
- Override truth does not survive into canonical objective decision rows; raw order_log and shadow journal remain required.
- Decision ledger still marks the admitted rid diagnostics-only / invalid-for-dataset while canonical realized data proves a profitable close.
- Sidecar observation exists post-fill, but this bundle does not show any sidecar authority mutation or widening of override admission scope.
