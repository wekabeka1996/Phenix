# Validation

## FACTS

Commands/results:

- V2 + shadow/config/registry suites: `87 passed`.
- V2 + existing mapper/sizing/external-open/adapter suites: `109 passed, 4 skipped`.
- terminal-agent broad suite: `578 passed, 13 skipped, 3 existing dev-config warnings`.
- compileall for modified shadow/config modules: passed.
- `git diff --check`: passed.
- Static HTTP scan found no `fsm_ref` or direct FSM emit.
- Static V2 field inspection confirmed no caller quantity field.

The first attempted combined Aurora/terminal pytest process failed collection with `ImportPathMismatchError` because both trees use `tests.conftest`; suites were rerun in separate processes and passed. Skips are not counted as proof.

## INFERENCES

- Contract, pure sizing adapter, registry, HTTP queue, main bridge, and existing final command boundary are unit/integration validated.

## ASSUMPTIONS

- Existing skipped tests are unrelated to V2; no claim relies on them.

## UNKNOWNS

- Real process/socket, FSM handling, and exchange execution remain unproven and were forbidden.

