# Execution Position Architecture

> Package-local architecture summary. The authoritative physical layout is
> described in `../README.md`.

## Three-phase lifecycle

Execution flows through three specialized FSM implementations:

1. `flows/open/fsm_open.py`
   Validates open intents, enforces exposure/leverage gates, and prepares entry submission.
2. `flows/manage/fsm_manage.py`
   Activates after fills, manages brackets, tracks live position state, and routes max-hold behavior.
3. `flows/close/fsm_close.py`
   Orchestrates explicit close commands and protects close flow semantics from bracket conflicts.

## Root orchestration anchor

`fsm.py` remains the root orchestration anchor for `ExecPosFSM`. That is
intentional and frozen by Phase 9A guardrails; it is not unfinished migration debt.

## Supporting layers

- `guards/` holds exposure, leverage, qty, and soft-clip logic.
- `state/` holds order ledger, restore, and startup-truth modules.
- `guardian/` holds orphan cleanup and cancel bridges.
- `telemetry/` holds metrics and observability utilities.
- `sidecar/` holds position-policy sidecar and mediator logic.
- `orchestration/` holds event ingress helpers.
- `support/` holds non-shadowing support utilities.
