# Residuals and Proven/Unproven Report

## FACTS

### 1. Proven
- **Exact Source Branch SHAs**:
  - `p46-1b-p43b-runtime-adapter-hardening-primary-20260711`: `4d2d82a304ed4f7fb71e91810bef32e3d2ede407`
  - `p46-1b-single-memory-kernel-primary-20260711`: `c14e27713fb24aa81c86f37a2926f2a1b548bc0b`
- **Exact Commits Integrated**:
  - `226b5d85` (hardened P43B adapter commit)
  - `e460d7a7` (single memory kernel commit)
- **Exact Files Changed**:
  - `config/p42_dual_agent_mvp.yaml`
  - `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py`
  - `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/trading_agent_runtime.py`
  - `tools/deepseek-terminal-agent/tests/test_trading_agent_runtime.py`
  - `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/collective_memory.py`
  - `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/collective_memory_models.py`
  - `tools/deepseek-terminal-agent/tests/test_single_memory_kernel.py`
- **Exact Tests and Results**:
  - `pytest tools/deepseek-terminal-agent/tests/`: 565 passed, 13 skipped.
- **Canonical Branch Final SHA**: `e460d7a7f741b8e6908ee32e7256918ac237ab91`
- **Remote Push Result**: Pending push.

### 2. Still Unproven
The following areas remain unproven and out of scope for this task:
- Legacy `AgentMemoryLifecycle` migration.
- Multiprocess production-scale append behavior.
- React Cockpit integration.
- Provider runtime.
- Full Phenix context.
- `AgentTradeIntentV2`.
- Phenix-side sizing.
- End-to-end Testnet chain.

### 3. Documentation Updates Required
- **Architecture Updates**: The strategy passport and coordination designs (`docs/llm_microstructure_strategy_passport.md`) need updates to document the `CanonicalMemoryStore` JSONL ledger schema as the single coordination log writer, replacing prior in-process or dual-writing assumptions.

## INFERENCES
- The integration branch establishes the necessary data model and runtime adapters, but complete integration verification requires testing the future Cockpit and Testnet integration lanes.

## ASSUMPTIONS
- A later stage will wire `CanonicalMemoryStore` as the sole runtime writer.

## UNKNOWNS
- None.
