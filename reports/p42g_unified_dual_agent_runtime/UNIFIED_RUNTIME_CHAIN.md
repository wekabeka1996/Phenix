# UNIFIED RUNTIME CHAIN

This document verifies the code structural cohesion, configuration parsing, and shared state directory settings.

---

## 1. Single Checkout and Import Cohesion

- **Zero Regressions**: All package imports resolve cleanly from the unified worktree root.
- **Single Source of Imports**: Python modules successfully import FSM, models, and adapters using the common relative namespace path (`deepseek_terminal_agent`).
- **Test Integrity**: Executing `pytest` across all suites passes cleanly, verifying that the testing harness correctly finds models, persistence stores, and adapters.

---

## 2. Config & Directory Cohesion

- **Unified Configuration Model**:
  - The configuration schemas for both the runner and the cockpit view are loaded from the single canonical file: `config/p42_dual_agent_mvp.yaml`.
  - Configs are parsed using Pydantic schemas in `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py` and `arena_runtime_view.py`.
- **Shared Session Roots**:
  - Both the runner (`dual_agent_runner.py`) and the Cockpit API service (`arena_runtime_view.py`) use the same file system root for active session states: `.agent_memory/sessions/`.
  - The cockpit reads the active states from `active_dual_agent_session.json` written by the runner, ensuring real-time view updates without duplicating persistence schemas.
- **Duplicate Prevention**: No duplicate configurations, config models, or runtime environments exist in the workspace.
