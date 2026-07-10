# VALIDATION — Test Suite Execution Records

This document lists the validation suite results confirming that all policy constraints, safety boundaries, and response structures behave correctly under test.

---

## 1. Test Execution Summary

All tests were executed on the runtime environment under `pytest`:

```powershell
C:\Users\wekab\Music\Phenix\.venv\Scripts\pytest tools/deepseek-terminal-agent/tests/test_agent_order_lifecycle_harness.py -vv
```

### Results:
- **Total Tests Run**: 8
- **Passed**: 8
- **Failed**: 0
- **Warnings**: 3 (Insecure dev default token warnings, expected in sandbox tests)

---

## 2. Verified Capabilities

| Test Case | Description | Verification Type | Result |
| :--- | :--- | :--- | :--- |
| `test_harness_blocked_guard_rejections` | Verifies that missing capability descriptor or non-testnet environment triggers block immediately. | FSM Handoff Guard | **PASSED** (returns `BLOCKED_ENVIRONMENT`) |
| `test_harness_blocked_missing_config` | Asserts that empty/missing adapter ID causes configuration block. | Configuration Guard | **PASSED** (returns `BLOCKED_CONFIG`) |
| `test_harness_blocked_no_order` | Confirms that setting `p40a_gate_allow_order_submit` to `False` prevents orders from reaching adapter. | Policy Guard | **PASSED** (returns `BLOCKED_POLICY`) |
| `test_harness_testnet_proof_ack` | Proves that valid external commands reach the real `BinanceAdapter` and invoke its REST placement method. | Adapter Routing | **PASSED** (returns `EXTERNAL_ACK`) |
| `test_harness_url_double_guard_rejects`| Confirms production URLs in base URL parameter are strictly blocked. | Double Guard | **PASSED** (returns `BLOCKED_ENVIRONMENT`) |
| `test_harness_agent_1_blocked` | Asserts that Agent 1 (`api_agent_01`) is prohibited from submitting external orders. | Agent Policy | **PASSED** (returns `BLOCKED_POLICY`) |
| `test_harness_wrong_symbol_owner` | Verifies that trading symbols owned by another agent (e.g. Agent 2 trading Agent 1's SOLUSDT) is blocked. | Coordination Lease | **PASSED** (returns `BLOCKED_POLICY`) |
| `test_harness_duplicate_command_id` | Verifies that duplicate commands are checked against trace files and blocked. | Idempotency Guard | **PASSED** (returns `BLOCKED_DUPLICATE`) |

---

## 3. Strict Precedence Checks

1. **Pre-flight precedence**:
   Duplicate Command ID and Hand-off environment checks are executed first to guarantee no duplicate or mainnet payload can reach any internal logic.
2. **Symbol Ownership precedence**:
   Checked prior to order placement to enforce the lease assignments defined in `collective_memory_config.yaml`.
3. **Agent 1 execution restriction precedence**:
   Enforced before adapter initialization to comply with execution authority restrictions.
4. **Exchange connection precedence**:
   Initializes only when environment validation, symbol ownership, and credentials pass.
