# ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT

Generated at UTC: 2026-05-10T19:33:43.251528+00:00
Audit source kind: artifact_authority_snapshot
Source snapshot manifest: artifacts/calibration_datasets/_post_03k_realized_outcome_03q/source_snapshot/source_snapshot_manifest.json

## Summary

| metric | value |
| --- | --- |
| rows_with_exact_order_position_closed | 0 |
| rows_with_lifecycle_bridge_position_closed | 0 |
| rows_with_trade_bridge_position_closed | 0 |
| rows_with_trade_lifecycle_terminal_close | 10 |
| rows_with_order_log_alternative_terminal_event | 2 |
| rows_with_decision_ledger_realized_fields | 1 |
| rows_classified_runtime_logging_gap | 0 |

## Close Surface Comparison

| rid | bucket | exact_pos_closed | lifecycle_bridge_pos_closed | trade_exact_close | exact_order_events | lifecycle_bridge_order_events |
| --- | --- | --- | --- | --- | --- | --- |
| aurora_BTCUSDT_1778364903981 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'LIMIT_PRICE_ADJUSTED': 1, 'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_BNBUSDT_1778377202278 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_BNBUSDT_1778378405537 | ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | 0 | 0 | 1 | {'ORDER_CANCELLED': 1, 'ORDER_INTENT': 2, 'ORDER_PLACED': 1, 'ORDER_TIMEOUT': 1} | {} |
| aurora_BNBUSDT_1778379004957 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'LIMIT_PRICE_ADJUSTED': 1, 'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_XRPUSDT_1778382005365 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_XRPUSDT_1778402706854 | ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | 0 | 0 | 1 | {'ORDER_CANCELLED': 1, 'ORDER_INTENT': 2, 'ORDER_PLACED': 1, 'ORDER_TIMEOUT': 1} | {} |
| aurora_BNBUSDT_1778405705080 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_XRPUSDT_1778414705236 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_BNBUSDT_1778416502994 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_BTCUSDT_1778424602438 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 0 | 0 | 1 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_ETHUSDT_1778428202947 | INCONCLUSIVE | 0 | 0 | 0 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_BTCUSDT_1778429706498 | DECISION_LEDGER_REALIZED_ONLY | 0 | 0 | 0 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
| aurora_XRPUSDT_1778430903673 | INCONCLUSIVE | 0 | 0 | 0 | {'ORDER_INTENT': 2, 'ORDER_PLACED': 1} | {} |
