# JOIN_COVERAGE_MATRIX

| Left | Right | Key | Overlap Count | Left Coverage | Right Coverage | Grade |
| --- | --- | --- | --- | --- | --- | --- |
| data/authority_request_journal_v1.jsonl | data/authority_response_journal_v1.jsonl | decision_id | 28 | 100.0 | 100.0 | EXACT_PROMOTION_GRADE_POSSIBLE |
| data/authority_request_journal_v1.jsonl | logs/shadow_telemetry/decision_ledger_v1.jsonl | rid | 27 | 96.4286 | 87.0968 | EXACT_PROMOTION_GRADE_POSSIBLE |
| data/authority_response_journal_v1.jsonl | logs/shadow_telemetry/decision_ledger_v1.jsonl | decision_id | 27 | 96.4286 | 87.0968 | EXACT_PROMOTION_GRADE_POSSIBLE |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | logs/order_log_v1.jsonl | rid | 31 | 100.0 | 6.4583 | EXACT_PROMOTION_GRADE_POSSIBLE |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | logs/trade_lifecycle.jsonl | rid | 24 | 77.4194 | 27.5862 | EXACT_PROMOTION_GRADE_POSSIBLE |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | reports/executed_trades_master.csv | trade_id | 0 | 0.0 | 0.0 | NO_SHARED_POPULATED_KEY |
| logs/order_log_v1.jsonl | reports/executed_trades_master.csv | trade_id | 0 | 0.0 | 0.0 | NO_SHARED_POPULATED_KEY |
| reports/order_attempts_master.csv | reports/executed_trades_master.csv | trade_id | 0 | 0.0 | 0.0 | NO_SHARED_POPULATED_KEY |
| reports/rejected_attempts_master.csv | logs/shadow_telemetry/decision_ledger_v1.jsonl | symbol | 1 | 100.0 | 25.0 | DIAGNOSTICS_ONLY_CONTEXT_MATCH |
| logs/trade_lifecycle.jsonl | reports/executed_trades_master.csv | trade_id | 0 | 0.0 | 0.0 | NO_SHARED_POPULATED_KEY |
| data/order_ledger.db::orders | logs/order_log_v1.jsonl | order_id | 110 | 6.1763 | 100.0 | EXACT_PROMOTION_GRADE_POSSIBLE |
| data/order_ledger.db::orders | reports/executed_trades_master.csv | trade_id | 0 | 0.0 | 0.0 | NO_SHARED_POPULATED_KEY |