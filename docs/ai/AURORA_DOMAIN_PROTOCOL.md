# Aurora / Phenix Domain Protocol

## Core project laws
- YAML + Pydantic are the SSOT.
- No silent fallbacks in business logic.
- No hidden business constants outside config.
- Contract-first evolution.
- Additive-only changes unless an explicit removal/refactor package is authorized.
- Runtime truth outweighs documentation.
- A task is not DONE until a REPORT is produced and recorded.

## Configuration laws
- All business behavior must come from explicit config or validated contracts.
- Pydantic models should be strict where applicable; avoid silent acceptance of extra fields.
- Any new event, command, mode, or registry entry must be declared explicitly in the proper YAML registry.
- Overrides must be explicit and traceable.

## Runtime / architecture laws
- Preserve fail-closed behavior.
- Check invariants across event flow, routing, and execution lifecycle.
- Temporal order matters: do not reason about event-driven behavior as if it were timeless.
- Cold-start, warmup, sticky state, and restart semantics must be considered when relevant.
- Code presence, unit coverage, and runtime proof are not equivalent.

## Trading / operational laws
- Prioritize capital safety over convenience.
- Any behavior affecting routing, rejection, sizing, order execution, or risk gating must state the invariant it protects.
- Silent drops are unacceptable: each proposed trade intent must either route, reject explicitly, or be explainably deferred.
- Runtime observability is mandatory for high-risk paths.

## Documentation / audit laws
- Docs must be updated when code/config behavior changes.
- Passport updates must reflect actual code/config/runtime evidence in scope.
- Historical claims must not be asserted unless verified from evidence, not assumed from older reports.
