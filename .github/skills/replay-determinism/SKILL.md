---
name: replay-determinism
description: Use for backtest/replay determinism, reproducibility, and ordering guarantees. Anchors to backtest_engine/, tools/strategy_replay.py, tools/feature_integrity_replay_check.py, and config/aurora/backtest_override.yaml.
---

# Replay Determinism Skill

## Purpose
Guarantee deterministic replay and reproducible backtests.

## Scope
- Backtest engine and replay harness
- RNG/seed control and ordering
- Data contracts and checkpoints

## When to use
- Any backtest or replay change
- Any nondeterminism investigation

## When NOT to use
- Pure live-execution tasks without replay

## Required inputs
- Replay/backtest target
- Data sources and time range
- RNG usage (if any)

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Identify replay harness in backtest_engine/ and tools/strategy_replay.py.
2) Verify data sources and contracts in data/, schemas/, and config/aurora/backtest_override.yaml.
3) Check replay integrity via tools/feature_integrity_replay_check.py.
4) Validate RNG usage and seed control.
5) Verify deterministic ordering and checkpoint usage (data/checkpoints/ if applicable).
6) If any referenced artifact is missing, output MUST start with:
   BLOCKED: missing <exact paths>

## Output
Use output_template.md.

## Safety constraints
- Do not mix live data with replay runs.
- Do not change data sources without contract updates.
- Do not assume production write access.

## Failure handling
If required inputs or artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
