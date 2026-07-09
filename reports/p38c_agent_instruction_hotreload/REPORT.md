AGENT_IDENTITY:
  agent_number: 3
  agent_name: primary-agent-instruction-hotreload-builder
  machine: primary
  task_id: P38C_AGENT_INSTRUCTION_HOTRELOAD
  branch: p38c-instruction-hotreload-primary-20260709
  worktree: C:\Users\wekab\Music\Phenix-p38c-instruction-hotreload
  started_at: 2026-07-09T18:30:00+03:00
  finished_at: 2026-07-09T18:48:18+03:00

# AGENT_REPORT_V1

task: P38C_AGENT_INSTRUCTION_HOTRELOAD
branch: p38c-instruction-hotreload-primary-20260709
worktree: C:\Users\wekab\Music\Phenix-p38c-instruction-hotreload
verdict: P38C_INSTRUCTION_HOTRELOAD_VALIDATED

## Summary

Implemented a session/agent instruction manifest and preflight layer for Markdown instruction hot reload. The layer hashes required instruction files, tracks manifest versions, reports missing files explicitly, detects changed hashes, emits a bounded refresh event payload, and produces ACK records.

This package does not wire a live trading or agent daemon loop. Runtime proof that agents call this every few minutes is absent; the implemented contract is ready for next-cycle callers to invoke without stopping runtime.

## Files Changed

- docs/agent_arena_instructions/AGENT_ARENA_RULES.md
- docs/agent_arena_instructions/AGENT_SKILLS.md
- docs/agent_arena_instructions/AGENT_TRADING_STYLE.md
- docs/agent_arena_instructions/FEATURE_TRUST_GUIDE.md
- docs/agent_arena_instructions/SESSION_OBJECTIVE.md
- docs/agent_arena_instructions/SUBAGENT_RULES.md
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_instruction_manifest.py
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_instruction_runtime.py
- tools/deepseek-terminal-agent/tests/test_agent_instruction_manifest.py
- tools/deepseek-terminal-agent/tests/test_agent_instruction_runtime.py
- reports/p38c_agent_instruction_hotreload/*

## Commands Run

- `pwd; git rev-parse --show-toplevel; git status --short --branch; git branch --show-current`
- `git worktree add -b p38c-instruction-hotreload-primary-20260709 C:\Users\wekab\Music\Phenix-p38c-instruction-hotreload bc25105175bd6e41d677f8d74f72979cd7155b1e`
- `python -m pytest tests/test_agent_instruction_manifest.py tests/test_agent_instruction_runtime.py`
- `git diff --check`
- `git status --short --branch --untracked-files=all`

## Validation

Focused pytest passed:

`10 passed in 0.22s`

Covered:
- detects file change
- detects missing required file
- produces ACK
- preserves priority ordering
- rejects path traversal
- does not mutate trading config

## Rails

- No Aurora trading runtime started.
- No exchange calls added.
- No YAML/business config edited.
- No hidden fallback for missing instruction files; missing files are reported in manifest and preflight payload.
- No broad rewrites outside assigned files.

## Coordinator Summary

P38C adds the first dynamic Markdown instruction layer as a reusable manifest/preflight/ACK contract. Next integration should call `agent_instruction_preflight()` on each agent cycle or scheduler tick, persist the emitted refresh event, and require `acknowledge_instruction_manifest()` before treating an agent as refreshed.
