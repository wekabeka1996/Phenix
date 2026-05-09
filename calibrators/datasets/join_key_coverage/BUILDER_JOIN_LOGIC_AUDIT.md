# BUILDER_JOIN_LOGIC_AUDIT

## Objective builder current logic
- Reads decision rows from authority_request_journal_v1.jsonl, authority_response_journal_v1.jsonl, and decision_ledger_v1.jsonl.
- Reads realized rows only from reports/executed_trades_master.csv.
- Keys executed-trade rows by attempt_id before any realized row is emitted.
- Copies decision_id from executed_trades_master when present, but does not require a matched decision row overlap to emit a realized row.
- Ignores order_log_v1.jsonl, trade_lifecycle.jsonl, order_attempts_master.csv, and order_ledger.db when building objective realized rows.

## Answers
1. Which fields does the builder currently use to join decisions to realized trades?
   - It does not perform a strict decision↔realized exact join. The realized path is driven by executed_trades_master rows keyed by attempt_id, with optional decision_id lookup back into the decision ledger.
2. Are those fields actually present in the source rows?
   - executed_trades_master current header fields: attempt_id, synthetic_id, symbol, side, regime, intent_price, intent_ts, outcome, confidence, reject_reason, order_instance_id, exit_ts, exit_price, realized_pnl, commission, exact_roundtrip.
   - decision_ledger key fields present: decision_id, rid, lifecycle_id, trade_id, symbol.
3. Are they populated?
   - executed_trades_master rows=0; attempt_id non-null count=0; decision_id non-null count=0.
4. Do the values overlap?
   - Best current exact pair result for decision_ledger ↔ executed_trades_master is key=trade_id overlap=0 grade=NO_SHARED_POPULATED_KEY.
5. Does builder ignore a better available key?
   - It ignores order_log lifecycle/order identifiers and trade_lifecycle runtime identities; order_log key fields present: rid, order_id, client_order_id, lifecycle_id, trade_id, symbol, strategy_id, side, regime; trade_lifecycle key fields present: request_id, rid, trace_id, order_id, client_order_id, exchange_order_id, entry_order_id, symbol, strategy_id, side, regime, ts_ms, event_ts_ms.
6. Does builder use a key that exists only in synthetic tests?
   - Synthetic tests assume a populated executed_trades_master surface with attempt_id, decision_id, rid, lifecycle_id, strategy_id, and *_ts_ms fields. The live master report currently has zero rows and its header does not contain several of those columns.
7. Does builder filter out valid rows accidentally?
   - Current evidence does not prove accidental filtering inside the realized loop; the dominant fact is that executed_trades_master contributes zero rows before row-level validation even begins.
8. Does it require exact fields that reports do not contain?
   - Yes. The builder expects decision_id, rid, lifecycle_id, strategy_id, intent_ts_ms, entry_ts_ms, exit_ts_ms, gross_pnl, fees, mfe, mae, bars_held, and terminal_status. The current executed_trades_master header uses intent_ts, exit_ts, realized_pnl, order_instance_id, and does not expose several expected fields.
9. Does it lose identity during normalization?
   - No direct proof of identity loss from normalize_symbol/normalize_side. The main loss is upstream: realized identity is absent or not surfaced in the chosen report.
10. Does it conflate decision row and realized trade row identity?
   - Yes. The realized row identity is driven by whatever executed_trades_master exposes, while decision identity stays on decision_id/rid. There is no enforced canonical bridge proving that emitted realized rows belong to emitted decision rows.

## Audit conclusion
- Current executed_trades_master rows=0 is the immediate reason objective_stack emits zero realized rows.
- order_attempts_master rows=4 shows at least one alternate attempt surface exists, but objective_stack does not consume it.
- The objective builder therefore exhibits a builder-logic gap relative to available runtime surfaces, but the first blocking fact is an empty chosen realized-outcome report.