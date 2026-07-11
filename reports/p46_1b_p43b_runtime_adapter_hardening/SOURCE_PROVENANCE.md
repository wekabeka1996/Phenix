AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-p43b-runtime-adapter-hardener
  machine: primary
  task_id: P46_1B_P43B_RUNTIME_ADAPTER_HARDENING
  branch: p46-1b-p43b-runtime-adapter-hardening-primary-20260711
  worktree: C:\Users\wekab\Music\Phenix-p46-1b-p43b

# Source Provenance Report

## FACTS
All integrated adapter files originate from:
- **Source candidate branch**: `p43b-api-cli-agent-runtime-adapters-primary-20260710`
- **Source candidate commit**: `d18cc36e9777a51ef6271c3531c2cfdd3af1546e`
- **Selected Phenix Base**: `5bc64f9b`

The file-to-origin mapping is:
- `config/p42_dual_agent_mvp.yaml`: Ported from `d18cc36e` (Lineage: base `5bc64f9b` -> modified in `998c813f` -> preserved in `d18cc36e`)
- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/p42_config.py`: Ported from `d18cc36e` (Lineage: base `5bc64f9b` -> modified in `998c813f` -> preserved in `d18cc36e`)
- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/trading_agent_runtime.py`: Ported from `d18cc36e` (Lineage: added in `998c813f` -> preserved in `d18cc36e`)
- `tools/deepseek-terminal-agent/tests/test_trading_agent_runtime.py`: Ported from `d18cc36e` (Lineage: added in `998c813f` -> preserved in `d18cc36e`)

## INFERENCES
- The lineage matches the user's manual baseline integration directive.

## ASSUMPTIONS
- The git hashes are immutable and fully represent the respective source snapshots.

## UNKNOWNS
- None.
