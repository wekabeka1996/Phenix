AGENT_IDENTITY:
  agent_number: 3
  agent_name: primary-instruction-hotreload-runtime-integrator
  machine: primary
  task_id: P39C_INSTRUCTION_HOTRELOAD_RUNTIME_LOOP
  branch: p39c-instruction-hotreload-runtime-loop-primary-20260709
  worktree: C:\Users\wekab\Music\Phenix-p39c-instruction-hotreload-runtime-loop
  started_at: 2026-07-09T21:05:00+03:00
  finished_at: 2026-07-09T21:20:20+03:00

# AGENT_REPORT_V1

task: P39C_INSTRUCTION_HOTRELOAD_RUNTIME_LOOP
branch: p39c-instruction-hotreload-runtime-loop-primary-20260709
baseline: origin/agent-hub-integrated-2026-07-09 @ 15b83bae3cce2bdcff20cd2fad95d296435051f3
verdict: P39C_HOTRELOAD_RUNTIME_LOOP_VALIDATED

## FACTS

- Created assigned worktree/branch from baseline commit `15b83bae3cce2bdcff20cd2fad95d296435051f3`.
- Baseline did not contain the P38C instruction manifest/runtime files.
- Cherry-picked local P38C contract commit `1dd04e49` as `550deb1a` on this branch before P39 work.
- Added `run_instruction_preflight_for_agent(...)`.
- The callable uses the existing disk-backed `SessionStore` event ledger.
- It appends `INSTRUCTIONS_REFRESHED` only when instruction files are changed or missing.
- It appends `INSTRUCTIONS_ACKED` every cycle with agent/session identity and active manifest version.
- Focused validation passed: `15 passed in 0.35s`.

## INFERENCES

- A Python callable is the lowest-risk runtime hook for Agent 5 because the task asks for an agent/session cycle callable and does not require dashboard control.
- A dashboard/API endpoint was not added because it would expand the surface without being necessary for the 4h MVP caller.

## ASSUMPTIONS

- Agent 5 can call this function from its runtime cycle with an existing `SessionStore`.
- Recommended MVP cadence is 300 seconds, with immediate caller invocation if file hash change is suspected.

## UNKNOWNS

- No live 4h agent runtime was started.
- No proof exists that Agent 5 is already invoking the callable every 5 minutes.
- No exchange testnet fills are proven by this package.

## Files Changed For P39

- `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_instruction_runtime.py`
- `tools/deepseek-terminal-agent/tests/test_agent_instruction_runtime.py`
- `reports/p39c_instruction_hotreload_runtime_loop/*`

## Commands Run

- `pwd`
- `git rev-parse --show-toplevel`
- `git status --short --branch`
- `git branch --show-current`
- `git fetch --all --prune`
- `git worktree add -b p39c-instruction-hotreload-runtime-loop-primary-20260709 C:\Users\wekab\Music\Phenix-p39c-instruction-hotreload-runtime-loop 15b83bae3cce2bdcff20cd2fad95d296435051f3`
- `git cherry-pick 1dd04e49`
- `python -m pytest tests/test_agent_instruction_manifest.py tests/test_agent_instruction_runtime.py`
- `git diff --check`

## Coordinator Summary

P39C now has a real caller-driven runtime loop hook. It persists refresh and ACK events into the session ledger, avoids duplicate refresh events on unchanged cycles, marks missing instruction files explicitly, and keeps the hot-reload cadence as a runtime recommendation rather than a daemon claim.
