---
name: order-lifecycle
description: Use for order lifecycle analysis, idempotency, correlation IDs, and fill/cancel flows. Anchors to tools/check_orders.py, tools/debug_orders.py, tools/run_order_tests.py, logs/*.jsonl, and backtest_engine/.
---

# Order Lifecycle Skill

## Purpose
Provide deterministic order lifecycle analysis with explicit invariants.

## Scope
- Order state transitions (submit, ack, fill, cancel)
- Idempotency and correlation IDs
- Diagnostics in tools/ and logs/

## When to use
- Any change to order flow or execution logic
- Any investigation of fills, cancels, retries

## When NOT to use
- Non-execution features with no order impact

## Required inputs
- Order type(s) and venue(s)
- Target subsystem or module
- Failure scenario or question

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Identify order flow components in backtest_engine/ or relevant execution modules.
2) Inspect tools/check_orders.py, tools/debug_orders.py, and tools/run_order_tests.py for lifecycle assertions.
3) Correlate order IDs and correlation IDs in logs/*.jsonl and logs/backtests/*.
4) Enumerate allowed transitions and forbidden transitions.
5) Define idempotency keys and retry boundaries.
6) If any referenced artifact is missing, output MUST start with:
   BLOCKED: missing <exact paths>

## Output
Use output_template.md.

## Safety constraints
- Do not propose non-idempotent transitions.
- Do not bypass risk gates or kill switches.
- Do not assume live trading or production write access.

## Failure handling
If required inputs or artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
