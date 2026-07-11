# Patch Diff

## FACTS

- Added `sessions/collective_memory.py`: explicit single-writer append/read/summary/carryover API.
- Extended `sessions/collective_memory_models.py` with strict canonical record and summary contracts.
- Added `tests/test_single_memory_kernel.py` with six focused tests.
- Added the required P46 report package.
- No YAML, dashboard, FSM, adapter, exchange, or trading-runtime files changed.

`git diff --stat` and `git diff --name-only` were captured before commit; ignored reports are listed explicitly in `REPORT.md`.

## INFERENCES

- The change is additive and does not silently redirect existing runtime writes.

## ASSUMPTIONS

- Runtime migration will be a separately reviewed patch.

## UNKNOWNS

- Final commit SHA is recorded after commit in the coordinator-visible Git branch.

