# Validation Report

This document records the unit test validation executed on the synchronized integration baseline.

## Test Summary

| Test File | Directory | Tests Run | Result | Notes |
| :--- | :--- | :---: | :---: | :--- |
| `test_session_context_contract.py` | `tests/domains/agent_bridge` | 6 | **PASSED** | Validates GET-only constraints and safety. |
| `test_dashboard_chat_app.py` | `tools/deepseek-terminal-agent/tests` | 9 | **PASSED** | Cockpit dashboard backend routes. |
| `test_agent_cadence.py` | `tools/deepseek-terminal-agent/tests` | 4 | **PASSED** | Stagger interval governance equations. |
| `test_agent_timer_runner.py` | `tools/deepseek-terminal-agent/tests` | 5 | **PASSED** | Scheduler, TTL, and heartbeat loops. |
| `test_agent_proposals.py` | `tools/deepseek-terminal-agent/tests` | 10 | **PASSED** | Proposal state transitions. |
| `test_agent_proposal_api.py` | `tools/deepseek-terminal-agent/tests` | 4 | **PASSED** | Proposal HTTP API routes. |
| **Total** | | **38** | **PASSED** | **100% Success Rate.** |

---

## Test Execution Outputs

### 1. Bridge Session Context Contract Tests
```
tests/domains/agent_bridge/test_session_context_contract.py::test_missing_store_fails_closed PASSED [ 16%]
tests/domains/agent_bridge/test_session_context_contract.py::test_no_order_sizing_leverage_payload PASSED [ 33%]
tests/domains/agent_bridge/test_session_context_contract.py::test_source_required PASSED [ 50%]
tests/domains/agent_bridge/test_session_context_contract.py::test_provenance_validation PASSED [ 66%]
tests/domains/agent_bridge/test_session_context_contract.py::test_schema_validates_examples PASSED [ 83%]
tests/domains/agent_bridge/test_session_context_contract.py::test_routes_session_context PASSED [100%]

============================= 6 passed in 10.14s ==============================
```

### 2. Cockpit Dashboard App Tests
```
tests\test_dashboard_chat_app.py .........                               [100%]

============================== 9 passed in 2.66s ==============================
```

### 3. Agent Cadence Governance Tests
```
tests\test_agent_cadence.py ....                                         [100%]

============================== 4 passed in 0.61s ==============================
```

### 4. Agent Timer Runner Scheduler Tests
```
tests\test_agent_timer_runner.py .....                                   [100%]

============================== 5 passed in 0.73s ==============================
```

### 5. Agent Proposal Ledger & API Tests
```
tests\test_agent_proposal_api.py ....                                    [ 28%]
tests\test_agent_proposals.py ..........                                 [100%]

============================= 14 passed in 1.48s ==============================
```
