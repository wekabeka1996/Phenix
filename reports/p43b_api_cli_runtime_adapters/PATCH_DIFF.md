# Patch Diff

Baseline: `5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d`.

Implementation commit: `998c813f`.

- Added `sessions/trading_agent_runtime.py` with common interface, response/context models, API adapter, restricted CLI adapter, and explicit factory.
- Extended `AgentRuntimeConfig` with explicit CLI command/path fields.
- Added explicit null/empty CLI configuration to `config/p42_dual_agent_mvp.yaml`, producing a fail-closed configured-CLI state.
- Added adapter-focused tests without modifying collective-memory internals or execution code.

