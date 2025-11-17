- TICK
- EVT:FEATURES_CALCULATED
- EVT:DECISION_SIGNAL
- INTENT_OPEN
- EVT:RISK_ASSESSMENT_COMPLETED
- CMD:OPEN
- ACK
- FILL
- FSM:OPENING → FSM:OPENED (перехід станів OPENING→OPENED)
- BRACKETS_SET (TP/SL встановлені)
- FSM:MANAGING (перехід станів OPENED→MANAGING)
- EVT:TP_FILLED або EVT:SL_FILLED
- CMD:CLOSE
- FSM:CLOSING (перехід станів MANAGING→CLOSING)
- EVT:CLOSED
- FSM:CLOSED (перехід станів CLOSING→CLOSED)
- SUMMARY


## Aggregated OCO v1 flow (entry → scale-in → partial-close → full-close → restart)

1. **First entry**
	- `EVT:ENTRY_FILLED` triggers `_recalc_aggregated_brackets(reason="first_entry")`.
	- ManageFlowFSM places TP/SL pair, logs `AGG_OCO_BRACKET_SET_CHANGED(action="first_entry")`.
	- OrderGuardian registers `BracketSetMeta(symbol, side)`.
2. **Scale-in**
	- `EVT:SCALE_IN_FILLED` updates position qty.
	- FSM recomputes TP/SL (`DEC:AGG_OCO_RECALC(scale_in)`), new `bracket_set_id` replaces old one.
	- Guardian ensures only one pair remains, cancelling stale brackets via `ensure_single_bracket_set_for_position`.
3. **Partial-close**
	- `EVT:PARTIAL_CLOSE_FILLED` fires.
	- If `aggregated_oco.recalc_on_partial_close=true`, FSM recalculates; otherwise it keeps prior set but still checks for SL gaps.
	- When SL is cancelled manually, FSM issues `DEC:AGG_OCO_RECALC(partial_close_unprotected)` to restore coverage.
4. **Full close / flip**
	- `EVT:POSITION_CLOSED` (or side flip) invokes `_cleanup_aggregated_brackets()`.
	- Guardian clears metadata and cancels remaining reduce-only orders.
5. **Restart / DR**
	- On startup, ExecPos fetches live positions + open orders.
	- `_rehydrate_aggregated_brackets_on_startup` groups data per `(symbol, side)` and calls `OrderGuardian.rehydrate_bracket_set_for_position`.
	- Guardian may log `AGG_OCO_BRACKET_SET_CHANGED(action="rehydrate")` and only then runs cleanup to avoid deleting valid SL.

**Invariant reminder:** For any phase where `position_amt > 0` and `allow_unprotected_position=false`, aggregated OCO keeps at least one active SL after each FSM/Guardian action.
