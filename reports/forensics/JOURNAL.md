# P0 Execution Split-Brain Research Journal

## Date: 2026-03-13

### Scope
- Investigate execution split-brain on DOGEUSDT in `mean_reversion` incident.
- Gather context, find code paths for sync/async divergence.
- Prove/disprove key hypotheses.
- Reconstruct timeline using logs and deterministic simulated reproduction.
- No fixes on this package; only research.

### Sources
- Code: `apps/reference/domains/execution_position/*`, `fsm.py`, `fsm_open.py`, `fsm_manage.py`, `bracket_manager.py`
- Logs: `logs/order_log_v1.jsonl`, `logs/trade_lifecycle.jsonl`, `logs/domain_execution_position.log*`, `logs/event_chain.log*`, `logs/aurora_core.log*`
- Config: `config/aurora/trading.yaml`, `config/aurora/domains.yaml`, `config/aurora/strategies/mean_reversion.yaml`

### 1.4 Constraints
*   **NO FIXES** allows.
*   **READ-ONLY** analysis (tests can be created but not hooked).
*   **FOCUS**: Provide definitive proof of the structural vulnerability.

## 2. Verdict & Findings
**Hypothesis H3 & H4 Confirmed**: A structural desynchronization exists between the global `DecisionMaking` Portfolio SSOT (which correctly identifies the position as `FLAT` upon an exchange SL hit) and the local execution `ManageFlowFSM` (which misses WebSocket drops and remains stuck in `TRACKING`).
Because `fsm_open.py`'s one-open-order guard only checks for pending entry orders and *fails* to check `ManageFlowFSM.state`, the FSM authorizes a new entry on the same symbol. Upon new entry fill, `ManageFlowFSM` skips bracket placement because it retains "phantom" bracket IDs from the previous position, leaving the new entry completely unprotected.
See `reports/forensics/p0_exec_split_brain_summary.md` for full breakdown.
- Additive artifacts only: tests, reports.

### Hypotheses to Validate
1. WS / ORDER UPDATE LOSS (exchange/adapter silent drop)
2. FSM MISSED TRANSITION (update received but state skipped)
3. OPEN-OVERWRITE BUG (new OPEN replaces locally active OPEN dict entry)
4. SPLIT-BRAIN BETWEEN POLLING AND FSM (tracker flat != fsm open)
5. TTL ORPHAN CLEANUP (ttl watcher vs cleanup cause)
6. BRACKET ACK vs FILL vs RECONCILIATION
7. TESTNET-SPECIFIC ANOMALY

### Current Status
- Initializing workspace and starting static forensics.

### Addendum: Reproduction Evidence Upgrade (2026-03-13)
- Verified that `tests/domains/execution_position/test_split_brain_repro.py` existed only as a stub and was not valid evidence.
- Replaced the stub with 5 deterministic research-only reproduction tests:
  - local open guard missing over stale `TRACKING`
  - new entry fill ignored over stale tracking state
  - `REST=FLAT` vs `FSM=TRACKING` divergence still admits reopen
  - orphan cleanup emits `EVT:SYMBOL_TIDY` but does not reconcile local close
  - valid TP fill can be ignored when manage flow still tracks pre-ACK client id
- Pytest evidence captured:
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -q`
  - `pytest tests/domains/execution_position/test_split_brain_repro.py -vv`
  - Result: `5 passed` as bug-demonstration tests against current runtime behavior
- Hypothesis updates from evidence:
  - `H1` downgraded to `LIKELY` because no raw event proof was recovered
  - `H2` upgraded to `PROVEN` as a live code/runtime path
  - `H3` upgraded to `PROVEN`
  - `H4` kept `PROVEN` only after reframing the mechanism: stale `TRACKING` state suppresses bracket placement before `_place_brackets()`, not `_has_brackets()`
  - Added `H6`: one symbol can continue with a new lifecycle over stale execution state (`PROVEN`)
- Implementation-ready basis now lives in `reports/forensics/p0_exec_repro_tests_addendum.md`.
