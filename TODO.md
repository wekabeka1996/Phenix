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

# Next Steps After QUANT_ENHANCEMENT_P2

- [ ] Deploy configuration and code changes to testnet environment
- [ ] Monitor SL/TP execution with client-side stops
- [ ] Validate that stops trigger correctly on price movements
- [ ] Monitor position sizing with unblocked Van Tharp logic
- [ ] Test liquidation guard behavior with new 1.0% threshold
- [ ] Consider adding SL/TP execution analytics to metrics

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

# Next Steps After QUANT_ENHANCEMENT_P2
