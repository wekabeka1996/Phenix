# SIDECAR_OUTPUT_CONTRACT_FUTURE_DESIGN_PRECONDITIONS_NOTE

## Proven Preconditions

- A future sidecar can remain derived-context only and still reuse existing close ownership.
- Current runtime already has a valid close execution path: reduce-only close through `CMD:CLOSE` -> `DEC:CLOSE` -> `CloseExecutor`.
- `ManageFlowFSM`, `CloseExecutor`, and `OrderGuardian` are the incumbent owners that must remain SSOT for lifecycle truth, execution, and reconciliation.
- A separate file inside `execution_position` could, in principle, compute additive policy and hand off to existing owners without taking over lifecycle truth.
- Aurora already has incumbent post-entry exit logic in `ExitManager`; any future sidecar must acknowledge this as active overlap, not empty space.

## Unresolved Blockers

- No executable close-by-id contract exists today.
- No proven `position_id` exists today.
- Public eventing does not uniformly expose "close already initiated" before execution continues.
- Current observability is insufficient to answer "who closed first and why" across all close sources.
- `ExitManager` stop-tighten branch to live bracket mutation remains `UNPROVEN`.

## Dangerous Assumptions

- Assuming `CMD:CLOSE` already means order-targeted or lifecycle-targeted close.
- Assuming `lifecycle_id` is an authoritative executable position key.
- Assuming `idempotent_key` in close payload selects a live lifecycle.
- Assuming current duplicate-close hardening is lifecycle-specific; it is symbol/effective-state based.
- Assuming a fully external event-only sidecar can stay race-free with current public contracts.
- Assuming `ExitManager` territory is empty just because it does not emit a dedicated public close command by itself.

## Minimum Extra Evidence Still Needed Before RFC

- Decide whether the future sidecar only needs symbol-scoped close or truly needs exact lifecycle targeting.
- If exact targeting is required, define and prove a new executable identity surface before RFC proceeds.
- Prove what the first outward-facing sidecar action mode should be:
  - recommendation-only,
  - EP-internal request,
  - or direct symbol-scoped close request.
- Add or at least specify a universal close-initiation attribution surface so race forensics are possible.
- Specify how sidecar output will be suppressed when:
  - `_closing_position` is already true,
  - bracket fill already resolved the lifecycle,
  - max-hold or regime-flip already emitted a close,
  - or duplicate-close hardening already blocked equivalent action.

## Guardrail Conclusion

Before a true RFC, the design discussion must stay honest about one constraint:

Current runtime can reuse close execution safely only as symbol-scoped reduce-only close. If the real requirement is "close this exact lifecycle/order/position by ID," that is not a wiring problem. That is a missing contract problem.
