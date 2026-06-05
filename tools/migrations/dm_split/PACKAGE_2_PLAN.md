# Package 2 Plan - Variant A Internal Modularization

## Move
- Move every `.py` module listed in `dm_move_map.csv` to the Variant A paths from Audit section 7.A.1.
- Include Addendum #3 section 2 placements:
  - `position_queries.py` to `primitives/position_queries.py`
  - `operational_mode.py` to `primitives/operational_mode.py`
- Move `schemas/` JSON files to `intent/schemas/`.
- Move `domain_dict.json` to `contracts/domain_dict.json`.

## Import Rewrite
- Rewrite Python imports using the libcst rewriter in `04_rewrite_imports.py`.
- Cover absolute imports and relative imports inside `apps/reference/domains/decision_making/`.
- Update external repo consumers in place when they import moved Variant A modules.

## Delete
- Remove the old Package 2 blocked report only by overwriting it with the final Package 2 report.
- Do not delete runtime modules outside the file moves.

## Add
- Add the migration toolkit under `tools/migrations/dm_split/`.
- Add toolkit tests under `tools/migrations/dm_split/tests/`.
- Add `tests/domains/decision_making/test_layered_boundaries.py`.
- Add backward-compat shims for authorized public surface and in-scope external consumers.

## Documentation
- Update only the file-map section of `apps/reference/domains/decision_making/README.md`.
- Write `PACKAGE_2_REPORT.md` and `PACKAGE_2_REPORT.json` under `tools/migrations/dm_split/artifacts/`.
