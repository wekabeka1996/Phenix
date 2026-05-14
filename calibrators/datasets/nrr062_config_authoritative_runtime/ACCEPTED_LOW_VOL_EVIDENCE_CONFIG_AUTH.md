# ACCEPTED_LOW_VOL_EVIDENCE_CONFIG_AUTH

| Metric | Value | Notes |
| --- | --- | --- |
| Status | NO_ACCEPTED_LOW_VOL_EVIDENCE_CONFIG_AUTH | frozen-surfaces-only accepted LOW_VOL audit |
| order_log accepted intents | 0 | any non-rejected decision intents in frozen order_log |
| order_log accepted LOW_VOL rows | 0 | explicit LOW_VOL markers on accepted order_log rows |
| decision ledger accepted LOW_VOL rows | 0 | EXECUTED_AND_CLOSED or ACCEPTED plus LOW_VOL marker |
| trade_lifecycle LOW_VOL diagnostic rows | 3 | diagnostic only, not accepted proof |
| regime LOW_VOL rows | 2551 | ambient LOW_VOL regime rows in frozen regime audit |

## Notes
- Accepted LOW_VOL evidence was tested only against frozen order_log, frozen decision_ledger, and frozen trade_lifecycle surfaces from the Package E bundle.
- No objective or realized-trade auxiliary datasets were used for this Package E accepted-evidence audit.
- trade_lifecycle LOW_VOL markers are diagnostic only unless paired with accepted rid-level proof on canonical accepted surfaces.

## Diagnostic LOW_VOL Trade Rows
| Class | RID | Lifecycle | Symbol | Record Kind | Event Type | TS UTC |
| --- | --- | --- | --- | --- | --- | --- |
| TRADE_LIFECYCLE_LOW_VOL_DIAGNOSTIC | aurora_BTCUSDT_1778669703907 |  | BTCUSDT | trade_lifecycle_snapshot | TRADE_LIFECYCLE_ORDERED |  |
| TRADE_LIFECYCLE_LOW_VOL_DIAGNOSTIC | aurora_BTCUSDT_1778669703907 |  | BTCUSDT | trade_lifecycle_snapshot | TRADE_LIFECYCLE_FILLED |  |
| TRADE_LIFECYCLE_LOW_VOL_DIAGNOSTIC | aurora_BTCUSDT_1778669703907 |  | BTCUSDT |  |  | 2026-05-13T11:57:41.569000+00:00 |
