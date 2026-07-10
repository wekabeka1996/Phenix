# SUBAGENT RUNTIME BOUNDARY

This document analyzes the role of the regex-triggered `ScoutAgent` and defines the runtime boundary for trading operations.

---

## 1. Task Router Subagents Analysis

The P42F coordination status mentions regex-triggered `ScoutAgent` and repository-search routing in `task_router.py`:

- **ScoutAgent**: Triggered when a prompt contains keywords like "EvidencePack" or "Scout". It collects repository files and logs in a read-only manner.
- **TestScoutAgent**: Triggered on test-related prompts ("testreport", "testscout") to run tests and output test reports.
- **LogScanner**: Triggered on log inspection keywords ("logs", "jsonl").

### Boundary Audit Result:
- **Classification**: **Generic coding-agent/workbench orchestration functionality**.
- **Role**: These subagents are tools of the coding assistant workbench (used during development and coordination to automate testing, log scanning, and code exploration).
- **No Trading Role**: They are **completely decoupled** from the actual trading loop, order placement logic, or market-analysis strategy.

---

## 2. Strict Boundary Rules

To preserve structural safety and prevent accidental code execution or workspace mutations:

1. **Market Analysis Hard Rule**: The live trading loop must never invoke repository-search, terminal shell execution, or coding-agent subagents for market-analysis or trading decisions.
2. **Read-Only Constraints**: Subagents spawned by the `TaskRouter` (like `ScoutAgent`) use the `read_only` tool policy and are prohibited from making modifications to source code or active configuration files.
3. **No Direct Execution**: Neither subagents nor the task router have any access to the FSM execution bus or exchange adapter clients. They cannot place, modify, or query orders.
