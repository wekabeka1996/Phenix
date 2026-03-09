# Blueprint: Critical Trade Lifecycle Failures

## Purpose

This blueprint formalizes the failures discovered in the 2026-03-08 lifecycle investigation.
Its goal is not to restate symptoms, but to define:

- what exactly is broken,
- why this is a logic defect and not an acceptable edge case,
- what system behavior becomes unsafe because of it,
- what implementation plan should be executed.

This document is based on the evidence captured in:

- reports/trade_lifecycle_failure_vectors_20260308_rca.md
- tests/domains/decision_making/test_trade_lifecycle_failure_vectors_20260308.py
- tests/domains/execution_position/test_inferred_fill_telemetry_blindness_20260308.py

## Executive Summary

The current engine has four systemic failure classes in the trade lifecycle:

1. Exit operations can be blocked by the same gates that are meant only for new entries.
2. Busy-state tracking can survive after the real position is already flat.
3. Hot reload can revoke ownership of an already active lifecycle.
4. Fill discovery can stay local to execution logic and never become canonical global telemetry.

These are not isolated bugs.
They are violations of core lifecycle invariants.
Because of that, they impact not only one strategy path, but the engine's control model as a whole.

## System Invariants That Must Hold

The engine must satisfy the following invariants.

### I1. Risk reduction must always have a path

If the system holds exposure, then risk-reducing actions must not be blocked by entry-only admission rules.

### I2. Internal busy state must converge to broker truth

If broker truth says the symbol is flat, internal symbol-busy state must converge to flat within bounded time.

### I3. Active lifecycle ownership must be stable

Once a position is opened, the strategy and lifecycle owner must remain responsible for it until terminal state, even if config changes.

### I4. Fills must become canonical events

Any real fill, regardless of discovery path, must produce a deterministic execution event visible to all downstream consumers.

### I5. Local recovery must not create global blindness

A local safety mechanism is allowed to recover internal state, but it is not allowed to hide that recovery from telemetry, accounting, and orchestration layers.

## Problem Blueprint

## Problem 1: Exit Hostage Under Regime Drift

### Problem statement

The strategy can open a position in an allowed regime and later become unable to close it after regime drift, because the same regime allowlist gate is still applied to the exit path.

### Why this is a logic problem

The logic conflates two different classes of intent:

- admission of new risk,
- reduction of existing risk.

These classes are not equivalent and must not be governed by the same policy.
Applying entry admissibility rules to exit operations is a policy modeling error.

### Why this is a behavior problem

Observed system behavior becomes internally contradictory:

- the engine knows it has exposure,
- the engine also knows regime has become unfavorable,
- but instead of reducing exposure it suppresses the close path.

That means the system behaves against its own safety objective.

### Why this is critical

This turns the risk manager from a safety layer into a deadlock generator.
Instead of limiting loss, it can force the engine to keep a position it already wants to close.

### Broken invariant

Broken invariant: I1. Risk reduction must always have a path.

### Required target behavior

- Entry can be blocked by regime policy.
- Reduce-only close cannot be blocked by regime allowlist.
- Flip must be decomposed into close-first and only the new entry leg may be rejected.

## Problem 2: Phantom Symbol Busy After Lifecycle Completion

### Problem statement

The system can keep rejecting new intents with symbol busy even after the broker-facing account state is already flat.

### Why this is a logic problem

The busy condition is derived from local transient memory and is not reconciled against an authoritative source.
That means the engine treats a temporary coordination artifact as if it were durable truth.

This is a state-modeling defect.
Transient orchestration markers must never outrank broker reality.

### Why this is a behavior problem

Behaviorally, the engine says two incompatible things at the same time:

- portfolio state says no active position,
- admission gate says symbol is still occupied.

That is a convergence failure between state observers.

### Why this is critical

It creates false lockouts, suppresses strategy throughput, and can leave the engine in a pseudo-degraded mode indefinitely.
In practice, this looks like a frozen symbol while the account is in fact idle.

### Broken invariant

Broken invariant: I2. Internal busy state must converge to broker truth.

### Required target behavior

- Busy state must be lease-based, not immortal in-memory state.
- Flat broker truth must invalidate stale busy markers.
- Reconciliation must happen automatically and within bounded latency.

## Problem 3: Orphaned Lifecycle After Hot Reload

### Problem statement

When config is hot-reloaded and a symbol is disabled, strategy handlers can stop managing a still-open position because management eligibility is tied to current enabled_symbols rather than the lifecycle that created the position.

### Why this is a logic problem

The engine is using configuration admission state as if it were lifecycle ownership state.
Those are different concepts.

- Admission answers whether a new lifecycle may start.
- Ownership answers who is responsible for an existing lifecycle.

Replacing the second with the first is a domain-boundary error.

### Why this is a behavior problem

The system can open a position under one config version and then silently stop reacting to that same position under another config version.
From the outside, the engine appears alive, but responsibility for the position disappears.

This is a classic orphaned-state behavior defect.

### Why this is critical

Open positions can lose strategy-side close logic, timeout logic, and protective orchestration.
That is not just a config issue; it is a direct loss of lifecycle control.

### Broken invariant

Broken invariant: I3. Active lifecycle ownership must be stable.

### Required target behavior

- Config reload may stop new entries.
- Config reload must not revoke management of active lifecycle_id values.
- Active lifecycles must drain gracefully to terminal state.

## Problem 4: Telemetry Blindness on Inferred Fills

### Problem statement

The engine can discover a real fill via internal recovery paths such as REST polling, update local execution state, and still fail to emit a canonical global execution event for downstream consumers.

### Why this is a logic problem

The system has multiple fill discovery channels but no single canonical event contract at the adapter boundary.
As a result, execution truth is normalized differently depending on discovery path.

This is a contract design defect.
If multiple sources can observe the same business fact, they must normalize into one event model.

### Why this is a behavior problem

Local execution logic recovers, but the rest of the system remains partially blind:

- position tracking may lag,
- telemetry may miss the fill,
- post-mortem reconstruction may diverge,
- higher layers may reason from stale or incomplete state.

The system therefore exhibits split-brain behavior between local recovery and global observability.

### Why this is critical

In trading systems, unobserved fills are one of the highest-severity behavioral failures.
The engine can no longer prove what it believes happened, when it happened, and who consumed that fact.

### Broken invariants

Broken invariant: I4. Fills must become canonical events.
Broken invariant: I5. Local recovery must not create global blindness.

### Required target behavior

- Any fill source must produce the same canonical execution event.
- Downstream consumers must not care whether the fill came from websocket, REST reconciliation, or cancel pre-check.
- Deduplication must be explicit and deterministic.

## Why These Are System Problems, Not Isolated Defects

These failures belong to the architecture layer because they all share the same pattern:

- intent class is not modeled explicitly,
- transient state is treated as durable truth,
- ownership is inferred from config instead of lifecycle identity,
- recovery paths bypass canonical event publication.

In other words, the engine currently mixes:

- policy and safety,
- admission and ownership,
- local recovery and global truth publication.

That is why the observed issues manifest as stuck positions, false blocks, orphaned positions, and telemetry gaps.
They are all different symptoms of the same architectural weakness: lifecycle state is not expressed as a first-class contract.

## Blueprint Plan

## Phase 1: Stabilize execution truth

### Goal

Create one canonical fill contract and make every fill path publish through it.

### Work items

1. Define a normalized execution event at the exchange-adapter boundary.
2. Route websocket fills, REST-detected fills, and discovered fills through the same normalizer.
3. Add explicit deduplication by venue, order_id, and trade_id or deterministic fallback key.
4. Ensure canonical execution telemetry reaches execution_position, position_tracking, and observability consumers.

### Why first

Without canonical fill truth, every other remediation still runs on unstable event semantics.

## Phase 2: Separate entry policy from exit safety

### Goal

Make it impossible for entry admission gates to block reduce-only risk reduction.

### Work items

1. Introduce explicit intent classification: ENTRY, EXIT, FLIP_CLOSE, HOLD.
2. Apply regime allowlist, warmup, and concentration only to ENTRY.
3. Apply a dedicated exit-safety policy to EXIT and FLIP_CLOSE.
4. Add regression tests proving regime drift cannot trap an open position.

### Expected outcome

The engine will be able to reject new risk while still safely unwinding old risk.

## Phase 3: Replace immortal busy state with reconciled leases

### Goal

Make symbol busy bounded, self-healing, and broker-reconciled.

### Work items

1. Convert busy markers into lifecycle-bound leases with ttl_ms.
2. Reconcile leases on account updates and terminal execution events.
3. Drop any lease that conflicts with flat broker truth.
4. Add telemetry for stale lease expiration and forced cleanup.

### Expected outcome

Phantom lockouts disappear and busy state converges to the real account state.

## Phase 4: Bind management to lifecycle identity

### Goal

Preserve ownership of active positions across config reloads.

### Work items

1. Assign lifecycle_id and config_version_snapshot when opening a position.
2. Keep active lifecycle management bound to the snapshot until terminal state.
3. Allow hot reload to affect only future entries.
4. Add graceful-drain semantics for disabled symbols.

### Expected outcome

Config reload becomes safe for active positions and no longer produces orphaned management state.

## Phase 5: Promote lifecycle invariants to CI contracts

### Goal

Make these failures impossible to reintroduce silently.

### Work items

1. Keep the current xfail scenarios as tracked vulnerabilities until remediation lands.
2. Convert them into strict passing regressions after each fix.
3. Add invariant-focused audit tests:
   - reduce-only close cannot be blocked,
   - flat state clears busy lease,
   - hot reload does not orphan active lifecycle,
   - inferred fills become canonical global events.

## Priority Order

Priority should be:

1. Canonical fill telemetry.
2. Exit-safe gating split.
3. Busy-state reconciliation.
4. Lifecycle-bound hot-reload ownership.
5. CI contract hardening.

The reason for this order is simple:

- first, the engine must know what actually happened,
- second, it must always be able to reduce risk,
- third, it must stop blocking itself on stale coordination state,
- fourth, it must preserve responsibility across config churn.

## Definition of Done

The blueprint is considered implemented only when all conditions below are true:

1. An open position can always reach a reduce-only close path, even after regime drift.
2. A flat broker account cannot remain symbol-busy beyond bounded reconciliation latency.
3. Disabling a symbol at runtime does not stop management of an already active lifecycle.
4. REST-discovered fills are visible as canonical global execution events.
5. The four current xfail simulations are converted to normal passing regression tests.

## Final Position

The main issue is not that the engine has four separate bugs.
The main issue is that lifecycle control is currently distributed across multiple local mechanisms without one explicit contract for:

- ownership,
- execution truth,
- risk-reducing intent,
- convergence to broker reality.

This blueprint therefore recommends treating lifecycle control as a first-class architectural subsystem, not as scattered handler logic.
