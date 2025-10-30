# TODO List for QUANT_ENHANCEMENT_P1

- [x] Update config/aurora/trading.yaml: Add risk_per_trade_pct and sl_bps to position_sizing
- [x] Update config/aurora/trading.yaml: Add execution_position.rules section
- [x] Update fsm_manage.py: Read sl_bps and tp_bps from config instead of hardcoded values
- [x] Update decision_making.py: Replace _calculate_simple_position_size_usd with _calculate_risk_based_position_size_usd
- [x] Update tests: Modify test_manage_flow_fsm.py for new config structure
- [x] Update tests: Add test_calculate_risk_based_position_size_usd to test_decision_making.py
- [x] Run pytest to validate all changes
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for DEBUG_EXEC_LOGIC_REFACTOR_P4

- [x] Refactor decision_making.py: Add _calculate_simple_position_size_usd method
- [x] Refactor decision_making.py: Update _calculate_position_size to use new method
- [x] Enhance XAI in decision_making.py: Update logging in _make_decision_for_symbol
- [x] Enhance XAI in decision_making.py: Change _propose_trade_intent to use why_chain
- [x] Enhance XAI in decision_making.py: Build why_chain in _make_decision_for_symbol
- [x] Enhance XAI in fsm_open.py: Change why="OPEN_OK" to "Open guards passed"
- [x] Enhance XAI in fsm_open.py: Update specific reject reasons
- [x] Run pytest to validate changes
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# Next Steps After CONFIG_TUNING_P1

- [ ] Restart system with python apps/reference/main.py
- [ ] Monitor logs for order flow unblocking
- [ ] Verify that ETH and BTC orders pass risk checks
- [ ] Test complete order lifecycle with new risk settings
- [ ] Validate that leverage changes don't affect position sizing
- [ ] Monitor for any new risk configuration conflicts

# TODO List for QUANT_ENHANCEMENT_P2

- [x] Update config/aurora/trading.yaml: Reduce min_liquidation_distance_pct from 5.0 to 1.0
- [x] Update fsm.py: Add routing of UPD:TICK to manage_flow
- [x] Update fsm_manage.py: Add UPD:TICK handling in handle() method
- [x] Update fsm_manage.py: Add SL/TP checking logic in _check_rules()
- [x] Update fsm_manage.py: Create _emit_close() method for DEC:CLOSE
- [x] Add test_client_side_stops_on_tick to test suite
- [x] Run pytest to validate all changes
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for QUANT_ENHANCEMENT_P3

- [x] Update position_tracking.py __init__: Add _total_commissions state
- [x] Update get_snapshot/load_snapshot: Include total_commissions persistence
- [x] Update on_trade_executed: Extract commission/commission_asset from payload
- [x] Update _update_position: Accumulate commissions, subtract from realized_pnl
- [x] Update portfolio emission: Include total_commissions in EVT:PORTFOLIO_STATE_UPDATED
- [x] Add test_position_tracking_commission_accounting to test suite
- [x] Run pytest to validate all changes
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for CONFIG_TUNING_P1

- [x] Update config/aurora/trading.yaml: Change max_risk_score from 0.8 to 0.95
- [x] Update config/aurora/trading.yaml: Change BTCUSDT leverage from 100 to 10
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P3

- [x] Update decision_making.py: Add equity > 0 validation in _check_and_trigger_decision_for_symbol
- [x] Update decision_making.py: Add pending_symbols set to track symbols waiting for portfolio
- [x] Update decision_making.py: Modify _check_and_trigger_decision_for_symbol to add symbols to pending when equity unavailable
- [x] Update decision_making.py: Modify on_portfolio to re-trigger decisions for pending symbols when valid equity arrives
- [x] Update tests: Modify test_rejects_trade_intent_if_equity_is_zero to check pending_symbols behavior
- [x] Update tests: Add test_processes_pending_symbols_when_portfolio_arrives_with_valid_equity
- [x] Run pytest to validate all changes (663 tests pass)
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Fix ExecPosFSM.hydrate to handle both single position and portfolio data formats
- [x] Run execution_position tests to validate hydrate fix (65 tests pass)
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P6

- [x] Fix PositionTracking: Revert to using totalWalletBalance from EVT:ACCOUNT_UPDATE_RECEIVED payload
- [x] Fix main.py logging filters: Change startswith filters to 'in record.name' for all domain handlers (already done in P5)
- [x] Update test to remove assets from ACCOUNT_UPDATE_RECEIVED payload
- [x] Run pytest to validate changes
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P3

- [x] Update decision_making.py: Add equity > 0 validation in _check_and_trigger_decision_for_symbol
- [x] Update decision_making.py: Add pending_symbols set to track symbols waiting for portfolio
- [x] Update decision_making.py: Modify _check_and_trigger_decision_for_symbol to add symbols to pending when equity unavailable
- [x] Update decision_making.py: Modify on_portfolio to re-trigger decisions for pending symbols when valid equity arrives
- [x] Update tests: Modify test_rejects_trade_intent_if_equity_is_zero to check pending_symbols behavior
- [x] Update tests: Add test_processes_pending_symbols_when_portfolio_arrives_with_valid_equity
- [x] Run pytest to validate all changes (663 tests pass)
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Fix ExecPosFSM.hydrate to handle both single position and portfolio data formats
- [x] Run execution_position tests to validate hydrate fix (65 tests pass)
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P4

- [x] Fix main.py DR hydration: Add validation for position_data fields before hydration
- [x] Add error handling in DR hydration loop to prevent crashes on invalid data
- [x] Run pytest to ensure no HYDRATION_ERROR during tests
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P3

- [x] Update decision_making.py: Add equity > 0 validation in _check_and_trigger_decision_for_symbol
- [x] Update decision_making.py: Add pending_symbols set to track symbols waiting for portfolio
- [x] Update decision_making.py: Modify _check_and_trigger_decision_for_symbol to add symbols to pending when equity unavailable
- [x] Update decision_making.py: Modify on_portfolio to re-trigger decisions for pending symbols when valid equity arrives
- [x] Update tests: Modify test_rejects_trade_intent_if_equity_is_zero to check pending_symbols behavior
- [x] Update tests: Add test_processes_pending_symbols_when_portfolio_arrives_with_valid_equity
- [x] Run pytest to validate all changes (663 tests pass)
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Fix ExecPosFSM.hydrate to handle both single position and portfolio data formats
- [x] Run execution_position tests to validate hydrate fix (65 tests pass)
- [x] Update TODO.md to mark task as completed

# TODO List for CRITICAL_FIX_P4

- [x] Fix main.py DR hydration: Add validation for position_data fields before hydration
- [x] Add error handling in DR hydration loop to prevent crashes on invalid data
- [x] Run pytest to ensure no HYDRATION_ERROR during tests
- [x] Add entry to docs/Хазяйство/JOURNAL_мій.md
- [x] Update TODO.md to mark task as completed
