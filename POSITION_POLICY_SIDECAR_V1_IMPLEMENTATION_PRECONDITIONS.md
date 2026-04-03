# POSITION_POLICY_SIDECAR_V1_IMPLEMENTATION_PRECONDITIONS

## Prerequisites Before Any Code Is Written

- Accept the Phase-1 boundary: recommendation-only, no action emission.
- Accept the owner boundary:
  - `ManageFlowFSM` stays SSOT
  - `CloseExecutor` stays executor
  - `OrderGuardian` stays reconcile owner
- Accept the contract boundary: no exact close-by-id claims.
- Decide the module path inside `execution_position`.
- Decide the minimum telemetry/event names for sidecar evaluation, suppression, and recommendation traces.

## Unresolved Blockers

- There is still no executable lifecycle or `position_id` contract.
- Current runtime still lacks a universal close-initiation attribution surface.
- `ExitManager` stop-tighten to live bracket mutation remains unresolved.
- Future partial-reduce ownership is unresolved.

## Missing Trace Fields Mandatory First

Before any action-bearing rollout beyond Phase 1, the system needs:

- `trace_id` carried from sidecar recommendation/request through downstream handling
- `policy_source` or equivalent attribution field
- explicit suppression reason
- explicit incumbent owner marker
- explicit outcome linkage from request to reconcile

## Can Phase 1 Start With Recommendation-Only?

Yes.

That is the recommended starting posture because it:

- preserves the separate-file sidecar concept
- avoids pretending the close contract is stronger than it is
- keeps blast radius minimal
- makes failures diagnosable and reversible

## Future Contract Work Required Beyond Symbol-Scoped Reduce-Only Behavior

- exact lifecycle/position identity contract if precise targeting is ever required
- EP-internal action request contract for guarded Phase-2 close requests
- stronger close-initiation attribution so overlap/race analysis becomes unambiguous
- bracket mutation contract if TP replacement, extension, or stop mutation is ever added
- explicit policy precedence contract if sidecar and `ExitManager` both become action-capable later

## Phase-1 Start Recommendation

Start with:

- one separate sidecar module in `execution_position`
- required event subscriptions only
- derived local cache only
- structured evaluation/suppression/recommendation traces
- no direct close or reduce action

Anything more ambitious should wait for the missing contract work above.
