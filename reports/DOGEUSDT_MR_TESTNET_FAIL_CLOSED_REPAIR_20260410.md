# DOGEUSDT Mean Reversion TESTNET Fail-Closed Forensic + Repair

## 1. Scope

### FACT

- Scope is limited to DOGEUSDT on the mean_reversion path on TESTNET.
- This report uses current disk state plus retained runtime logs from the 2026-04-09 to 2026-04-10 window.
- This package does not broaden into BTC, ETH, SOL, or non-MR Aurora tuning.

### FACT

- Code changes were applied only to the execution-position lifecycle path.
- Config change was applied only to DOGEUSDT leverage SSOT in instruments.yaml.
- mean_reversion safety_gates were not changed in this package.

## 2. Proven Runtime Facts

### FACT

- config/aurora/strategies.yaml assigns DOGEUSDT to mean_reversion.
- config/aurora/strategies/mean_reversion.yaml has DOGEUSDT enabled with leverage target 10.
- Before this repair, config/aurora/instruments.yaml had DOGEUSDT.execution.target_leverage = 20.
- apps/reference/domains/execution_position/leverage_config.py makes instruments.yaml the runtime leverage SSOT and logs strategy leverage as legacy/ignored.
- logs/order_log_v1.jsonl shows DOGE ORDER_INTENT metadata.leverage = 20.0 at runtime.

### FACT

- logs/domain_execution_position.log.2 line 6326 shows DOGE SL placed with algoId 1000000045118395 and clientAlgoId 5eoGHdmBTZO7MqhKhccrdP.
- logs/domain_execution_position.log.2 line 6327 shows DOGE TP placed with algoId 1000000045118396 and clientAlgoId DqtvbNd02QK1uSj8duidFj.
- logs/domain_execution_position.log.2 line 6328 records EXECUTION_BRACKET_PRIMARY_PLACED for DOGE with those bracket ids.
- logs/domain_execution_position.log.2 lines 6335-6337 show the DOGE entry fill followed immediately by ManageFlow re-entering _place_brackets and clearing the already-synced bracket ids as phantom local ids.
- logs/domain_execution_position.log.2 lines 7429-7437 show later DOGE SL fills arriving with child clientOrderId 5eoGHdmBTZO7MqhKhccrdP, while local expected bracket ids were all None, producing EXIT_MATCH_FAILED.
- logs/domain_execution_position.log.1 and logs/domain_execution_position.log show repeated EXECUTION_GUARD_BLOCKED with local_manage_state = BRACKETS_PENDING and portfolio_state = FLAT for DOGE after the first trade was already closed.

### FACT

- config/aurora/strategies/mean_reversion.yaml sets safety_gates.enabled = false.
- apps/reference/domains/decision_making/safety_gates.py therefore emits threshold_verdict = BYPASS and threshold_reason = safety_gates_disabled.
- logs/order_log_v1.jsonl and logs/domain_decision_making.log* show DOGE intents with threshold_verdict = BYPASS.

## 3. Root Cause Ranking

### FACT

1. Dominant runtime blocker: lifecycle ghost lock after the first DOGE trade.
2. Second proven issue: leverage SSOT drift caused DOGE runtime to trade at 20x while MR calibration expected 10x.
3. Third proven issue: safety gate verdict is BYPASS by design, so the path is not fail-closed.

### INFERENCE

- ATR stop geometry and MARKET execution may still affect quality of the next DOGE trade, but they are not the dominant reason DOGE became operationally non-evaluable in the inspected run.
- The inspected DOGE runtime became non-evaluable primarily because the first closed lifecycle was never cleared locally, so subsequent valid intents were rejected before execution.

## 4. Minimal Patch Set Applied

### FACT

- apps/reference/domains/execution_position/fsm_manage.py now preserves already-synced exchange/algo bracket identity on the entry-fill path instead of clearing it as phantom local state.
- The preservation path is restricted to cases where bracket identity already looks exchange-synced, including stored algo client ids.
- config/aurora/instruments.yaml now sets DOGEUSDT.execution.target_leverage = 10 to align runtime SSOT with the active mean_reversion DOGE calibration.

### INFERENCE

- This is the minimum code+config package that fixes the proven DOGE ghost mechanism and the proven DOGE leverage drift without changing broader MR strategy geometry.

## 5. Validation

### FACT

- Targeted pytest validation passed:
  - tests/domains/execution_position/test_entry_fill_preserves_primary_bracket_identity.py
  - tests/domains/execution_position/test_bracket_algo_client_id_correlation.py
  - tests/domains/execution_position/test_brackets_pending_silent_drop_fix.py
- Combined result: 22 passed, 0 failed.
- Config load validation after the YAML edit returned DOGEUSDT.execution.target_leverage = 10.

### FACT

- The new regression test reproduces the exact proven failure shape:
  - primary bracket ids synced before entry fill,
  - entry fill processed,
  - later SL fill matched by algo client id,
  - lifecycle cleared to FLAT.

## 6. Residual Risk

### FACT

- mean_reversion safety_gates remain disabled in current strategy config.
- No per-asset DOGE-only safety_gates override was identified in the current config contract.

### INFERENCE

- Re-enabling safety_gates inside mean_reversion.yaml would change the whole mean_reversion strategy block, not just the DOGE runtime seam repaired here.
- Because only DOGE is currently enabled on mean_reversion, that broader config change may still be acceptable operationally, but it is a strategy-policy decision rather than a narrowly proven DOGE bug fix.

## 7. Go / No-Go

### FINAL

- GO for the next DOGEUSDT TESTNET diagnostic run if the objective is to make DOGE operationally evaluable again on MR after the proven ghost-lock and leverage drift fixes.
- NO-GO for claiming a fully fail-closed DOGE/MR path while mean_reversion safety_gates remain intentionally disabled and continue to emit BYPASS.

### FINAL

- Recommended operating posture for the next run:
  - keep scope DOGE-only,
  - restart cleanly so the fixed lifecycle path is exercised from a fresh state,
  - treat the run as constrained diagnostic validation rather than final policy closure,
  - decide separately whether MR safety_gates should be enabled at strategy scope.
