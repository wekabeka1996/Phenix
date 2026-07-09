# Validation

## FACTS

Command:

`python -m pytest tests/test_agent_instruction_manifest.py tests/test_agent_instruction_runtime.py`

Result:

`15 passed in 0.35s`

Command:

`git diff --check`

Result:

No whitespace errors reported.

Test coverage:

- first cycle writes refresh event and ACK
- changed Markdown file produces refresh event
- unchanged cycle does not duplicate refresh event
- missing required instruction file marks missing state
- path traversal identity is rejected
- event/ACK includes agent/session identity
- manifest contract tests from P38C still pass

## INFERENCES

- The callable is unit-test validated against the same session event store used by Cockpit sessions.

## ASSUMPTIONS

- Focused tests are the right validation scope because no 4h runtime was requested for this agent.

## UNKNOWNS

- No 4h runtime proof.
- No exchange execution proof.
- No dashboard/API route proof because none was added.
