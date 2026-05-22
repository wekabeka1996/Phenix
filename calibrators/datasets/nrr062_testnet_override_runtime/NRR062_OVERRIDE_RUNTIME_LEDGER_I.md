# NRR062_OVERRIDE_RUNTIME_LEDGER_I

## Executive Summary
Current frozen bundle retains 5 distinct override-admitted rid(s) in the cumulative post-deploy tail beginning at line 1734.

## Runtime Window
- start: 2026-05-15T10:55:08.184000+00:00
- end: 2026-05-16T10:10:03.371000+00:00
- duration_seconds: 83695
- active_symbols: BNBUSDT, BTCUSDT, XRPUSDT, ETHUSDT, DOGEUSDT
- restarts_after_boundary: 3
- manual_cleanup_status: NOT_OBSERVED_IN_FROZEN_EVIDENCE
- trading_modes: hybrid_live_data_testnet_exec

| RID | Symbol | Side | Decision ID | Submitted | Filled | Closed | Close Reason | Net | Fees | Exact RT | Sidecar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aurora_BTCUSDT_1778845805903 | BTCUSDT | short | 49f6a2b8-4774-4ce0-9132-a8887f8c6c10 | True | True | True | closed_win | 22.6742616 | 1.9257384 | True | False |
| aurora_BTCUSDT_1778874602993 | BTCUSDT | short | 8363e15a-09f9-4330-a260-1232f8a06a9c | True | True | True | closed_win | 16.35869414 | 1.93960586 | True | False |
| aurora_ETHUSDT_1778874602066 | ETHUSDT | short | 626a999c-97ed-4c19-a4dd-71918cb59f90 | True | False | False | None | None | None | False | False |
| aurora_ETHUSDT_1778875209803 | ETHUSDT | short | 0331abf6-efb2-475c-86a3-37e9230ab4ad | True | True | True | closed_win | 22.795140229999998 | 2.45903977 | True | False |
| aurora_XRPUSDT_1778875503239 | XRPUSDT | short | a9405806-90e6-44ec-9d81-d4e27eba94bd | True | True | True | closed_win | 8.511641540000001 | 1.7230384600000002 | True | False |
