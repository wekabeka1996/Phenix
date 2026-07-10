# Patch Diff

Changed implementation:

- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/collective_memory.py`
- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/collective_memory_models.py`

Added validation/benchmark:

- `tools/deepseek-terminal-agent/tests/test_collective_memory_fault_injection.py`
- `tools/deepseek-terminal-agent/tests/test_semantic_recall_benchmark.py`
- `tools/deepseek-terminal-agent/scripts/benchmark_semantic_recall.py`
- `reports/p41y_memory_fault_injection/**`

Repairs are limited to demonstrated partial-tail, lock contention, reconciliation persistence, failure injection, and source-bound semantic recall gaps. No dashboard, Aurora runtime, exchange adapter, trading YAML, secret, log, ledger, or existing `.agent_memory` file was edited.
