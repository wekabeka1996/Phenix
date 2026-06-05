# POSITION_CLOSED_MISSING_ROW_CASEBOOK

Package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR

## Cohort Summary

| bucket | rows | dominant pattern | 03T action |
| --- | --- | --- | --- |
| ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | 8 | trade_lifecycle terminal evidence includes ORPHANED_TTL after fill, while order_log has only intent/placed or limit-adjusted rows | repaired by adding reconcile-path canonical parity when close truth exists |
| ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | 2 | ORDER_TIMEOUT + ORDER_CANCELLED in order_log and CANCELLED in trade_lifecycle | left unchanged; not a proved realized close producer |
| DECISION_LEDGER_REALIZED_ONLY | 1 | realized fields in decision ledger with no close evidence in order_log or trade_lifecycle | left unchanged; authority issue remains separate |
| INCONCLUSIVE | 2 | fill/order evidence exists but no decisive terminal close evidence remains | left unchanged; still unproven |

## Row Casebook

| rid | bucket | order_log pattern | trade_lifecycle pattern | inferred runtime path | 03T target |
| --- | --- | --- | --- | --- | --- |
| aurora_BTCUSDT_1778364903981 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | LIMIT_PRICE_ADJUSTED, ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_BNBUSDT_1778377202278 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_BNBUSDT_1778378405537 | ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | ORDER_INTENT, ORDER_PLACED, ORDER_TIMEOUT, ORDER_CANCELLED | TRADE_LIFECYCLE_ORDERED, CANCELLED | terminal non-fill or cancelled close attempt | no |
| aurora_BNBUSDT_1778379004957 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | LIMIT_PRICE_ADJUSTED, ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_XRPUSDT_1778382005365 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_XRPUSDT_1778402706854 | ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT | ORDER_INTENT, ORDER_PLACED, ORDER_TIMEOUT, ORDER_CANCELLED | TRADE_LIFECYCLE_ORDERED, CANCELLED | terminal non-fill or cancelled close attempt | no |
| aurora_BNBUSDT_1778405705080 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_XRPUSDT_1778414705236 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_BNBUSDT_1778416502994 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_BTCUSDT_1778424602438 | ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED, ORPHANED_TTL | missed portfolio edge then TTL flush | yes |
| aurora_ETHUSDT_1778428202947 | INCONCLUSIVE | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED | unproven | no |
| aurora_BTCUSDT_1778429706498 | DECISION_LEDGER_REALIZED_ONLY | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED | decision-ledger-only realized authority | no |
| aurora_XRPUSDT_1778430903673 | INCONCLUSIVE | ORDER_INTENT, ORDER_PLACED | EXECUTION_FILL_INGRESS, TRADE_LIFECYCLE_FILLED | unproven | no |

## Minimal Safe Interpretation

The dominant 8-row cohort is consistent with a missed canonical close emission followed by trade_lifecycle TTL finalization. That is the only cohort directly targeted by the 03T runtime patch.
