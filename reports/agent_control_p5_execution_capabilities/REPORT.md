# AURORA_AGENT_CONTROL_P5_EXECUTION_CAPABILITY_DESCRIPTORS_AND_READINESS_CLOSURE

## Problem framing

P4 activated safe direct-main observation but filter, normalization, and reduce-only capabilities lacked an immutable agent-facing descriptor surface. P5 exposes evidence without execution authority.

## FACTS

- `ExecutionCapabilityDescriptorV0` separates `runtime_owner`, `configured_only`, `exchange_confirmed`, and `unavailable` evidence.
- BTCUSDT/ETHUSDT have canonical tick, step, minimum quantity, and minimum notional values, but no fresh exchange-filter confirmation in no-order mode.
- Runtime-owned qty/price/minimum normalization is ready for both requested symbols and unknown symbols fail closed.
- Reduce-only request, close, and protect descriptors are runtime-owned and ready; exchange acceptance is explicitly false/unclaimed.
- P5 ran under `agent_bridge_observation_only` with `adapter=None` and no consequential listeners.
- Ten Cockpit GET polls succeeded and SQLite rows increased from 30 to 40.

## INFERENCES

- Config-only constraints improve visibility but cannot prove exchange parity.
- Pure normalization and explicit owner methods can be ready without an exchange command because their capability is local and deterministic.

## ASSUMPTIONS

- Loaded typed instrument models are the canonical configured SSOT.
- Bounded runtime logs represent this observation window only.

## UNKNOWNS

- Current exchange-confirmed filters, max notional, and max position are unavailable.
- Exchange acceptance of reduce-only requests is intentionally untested.

## Root cause versus symptom

The root defect was absent descriptor ownership, not broken execution. P4's missing/degraded invariant labels were symptoms of that visibility gap.

## Implementation summary

Added compact descriptor, constraint-summary, and readiness-summary contracts; a strict allowlisted builder; requested-symbol projection; P5 publication versioning; packet integration without duplicated full readiness snapshots; and focused evidence-classification tests.

## Descriptor design summary

Each descriptor includes name, optional symbol, status, evidence level, owner, timestamp, compact constraints, raw reference, detail, and missing reason. The builder reads no credential fields and calls no adapter/executor method.

## Exchange filter descriptor results

BTCUSDT and ETHUSDT are `degraded/configured_only`. Both expose tick size, step size, min quantity, and min notional. Fresh exchange confirmation, max notional, and max position remain unavailable.

## Precision/minimum descriptor results

Both requested symbols are `ready/runtime_owner`: quantity floor-to-step, price tick quantization, min-quantity/min-notional checks, symbol resolution, and unknown-symbol fail-closed behavior are present.

## Reduce-only descriptor results

Typed request representation, close-path enforcement ownership, and protect/bracket ownership are each `ready/runtime_owner`. No order was submitted and exchange acceptance is not claimed.

## Readiness before/after

P4: filters missing, precision/minimum missing, reduce-only degraded. P5: filters degraded/configured-only, precision/minimum ready, reduce-only ready. Idempotency, lifecycle, bracket, trace, isolation, and secret-safe inspection did not regress.

## Runtime observation results

All ten BTCUSDT/ETHUSDT packets returned HTTP 200 through Cockpit, used direct-main market/features and execution publication, contained seven projected descriptors and two symbol summaries, stayed `fresh=8`, and persisted ten new rows. No consequential route or exchange action was observed.

## Latency and token budget

Round trip was 20-57 ms, mean 28.5 ms. Packets were 14,450-14,453 bytes and 3,613-3,614 estimated tokens of 4,400, with no truncation. Descriptor projection prevents unrelated configured symbols from entering the packet.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Python compilation, descriptor classification, missing/unknown, no-secret/no-call, startup, publication, GET route, packet budget, Cockpit lint/build/tests, live polling, schema checks, and safety scans passed.

## What is proven

- Truthful config-only exchange-filter visibility.
- Runtime-owned precision/minimum and reduce-only capability visibility.
- Direct P5 readiness publication and compact packet integration.
- No-order, GET-only, disabled-action continuity.

## What remains unproven

- Fresh exchange-confirmed filters.
- Max notional/max position.
- Exchange acceptance or order execution.
- Agent authority.

## Risks

- Config values may drift from exchange metadata until a safe public filter owner is attached.
- Descriptor readiness states capability availability, not business-gate admission or exchange success.

## P6 recommendation

Add an optional public, credential-free exchange-info cache with freshness and parity diagnostics. Keep it read-only and separate from adapter/order authority.

## Final verdict

P5_CAPABILITY_DESCRIPTORS_VALIDATED_WITH_CONFIG_ONLY_FILTERS
