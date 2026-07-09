# Patch Diff

## FACTS

P39 changed:

- `agent_instruction_runtime.py`
  - Added event constants.
  - Added `InstructionRuntimeCycleResult`.
  - Added `run_instruction_preflight_for_agent(...)`.
  - Added previous-manifest lookup from prior `INSTRUCTIONS_ACKED` events.
  - Persists `INSTRUCTIONS_REFRESHED` and `INSTRUCTIONS_ACKED` events through `SessionStore`.
- `test_agent_instruction_runtime.py`
  - Added real `SessionStore` tests for first cycle, changed file, unchanged cycle, missing file, traversal rejection, and identity metadata.

Dependency included on branch:

- P38C instruction contract commit was cherry-picked because the required baseline lacked it.

## INFERENCES

- The patch is additive and avoids dashboard/API changes.

## ASSUMPTIONS

- Event names are acceptable as the "or equivalent" requested by P39.

## UNKNOWNS

- No external runtime used these events during validation.
