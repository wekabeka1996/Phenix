# Preservation Branch

## FACTS

- Repository: `wekabeka1996/deepseek-agent-os`.
- Base: `workspace-changes@15e63ce57a5be75b6f08a594259ba517428cff1f`.
- Branch: `p46-preserve/primary-cockpit-preintegration-20260713`.
- Imported scope: exactly 10 new and 4 modified files listed in `SOURCE_MANIFEST_SUMMARY.md`.
- Non-imported substantive source files: zero.
- 418 line-ending-only differences were intentionally not imported.
- Runtime/generated/private exclusions were not imported.
- Source commit: `7862947` (`P46-2A preserve primary Cockpit agent feed sources`).
- Documentation commit/final pushed tip: `b9726ac` (`P46-2A document primary Cockpit preservation`).
- Push: succeeded; local and `origin/p46-preserve/primary-cockpit-preintegration-20260713` are synchronized.

Validation before preservation close: `git diff --check`, TypeScript no-emit, focused tests, build, excluded-path scan, and secret-pattern scan.

## INFERENCES

The branch is suitable as the sole reviewable source of primary-only Cockpit work.

## ASSUMPTIONS

No runtime claim follows from compilation and tests.

## UNKNOWNS

Live UI behavior remains unproven.
