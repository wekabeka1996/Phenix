# Patch Diff

## Added

- `docs/agent_arena_instructions/AGENT_ARENA_RULES.md`
- `docs/agent_arena_instructions/AGENT_SKILLS.md`
- `docs/agent_arena_instructions/AGENT_TRADING_STYLE.md`
- `docs/agent_arena_instructions/FEATURE_TRUST_GUIDE.md`
- `docs/agent_arena_instructions/SESSION_OBJECTIVE.md`
- `docs/agent_arena_instructions/SUBAGENT_RULES.md`
- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_instruction_manifest.py`
- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_instruction_runtime.py`
- `tools/deepseek-terminal-agent/tests/test_agent_instruction_manifest.py`
- `tools/deepseek-terminal-agent/tests/test_agent_instruction_runtime.py`
- `reports/p38c_agent_instruction_hotreload/REPORT.md`
- `reports/p38c_agent_instruction_hotreload/INSTRUCTION_CONTRACT.md`
- `reports/p38c_agent_instruction_hotreload/PATCH_DIFF.md`
- `reports/p38c_agent_instruction_hotreload/VALIDATION.md`
- `reports/p38c_agent_instruction_hotreload/RISKS.md`

## Functional Diff

- Added a required Markdown instruction manifest contract.
- Added SHA-256 hashing and short version derivation per instruction file.
- Added manifest version derivation across required file state.
- Added explicit missing-file reporting instead of fallback behavior.
- Added changed-file detection from previous to current manifest.
- Added preflight refresh event payload generation.
- Added manifest ACK model.
- Added tests for change detection, missing files, ACK, priority order, traversal rejection, and config immutability.

Full patch is available from git on branch `p38c-instruction-hotreload-primary-20260709`.
