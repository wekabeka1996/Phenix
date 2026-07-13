# Agent 1 P46-2A Status

## FACTS

- Exact Cockpit baseline: `wekabeka1996/deepseek-agent-os workspace-changes@15e63ce5`.
- Primary-only closure: 10 new plus 4 modified files; 418 other differences are line endings only.
- Preservation branch: `p46-preserve/primary-cockpit-preintegration-20260713`.
- Preservation tip: `b9726ac`, pushed and synchronized with origin.
- Phenix report branch: `p46-2a-primary-cockpit-truth-primary-20260713` from `2caae9d3`.
- Tests: TypeScript pass, 9 focused tests pass, build pass.
- Critical blocker for later integration: Cockpit V1 accepts model `qty`; it is not V2 no-sizing authority.
- Canonical ownership: Phenix memory/context version/session/lease/sizing/FSM/venue; Cockpit UI/provider/orchestration/presentation.

## INFERENCES

Proceed to bounded review/integration packages; do not merge the snapshot wholesale.

## ASSUMPTIONS

Preservation refs remain available remotely after push.

## UNKNOWNS

Live Cockpit interoperability remains unproven.

## Verdict

`P46_2A_PRIMARY_COCKPIT_TRUTH_AND_PRESERVATION_VALIDATED`
