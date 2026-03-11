# Unified Runtime Execution Backlog

Date: 2026-03-11
Source plan: `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md`
Status: execution backlog for phased implementation
Mode: additive-first, rollback-safe, Aurora-v2-live until foundation is verified

## Ordering

1. URS-A1 Readiness Schema and State Model
2. URS-A2 Canonical Bar Identity and Replay Identity Specification
3. URS-B1 Gap Policy
4. URS-B2 Analytics Restore
5. URS-B3 Startup Hydration Planner Design
6. URS-C1 Strategy Compatibility and Isolation Matrix
7. URS-D1 Regime Layering
8. URS-E1 Quadratic Shadow Rollout and Rollback Specification

## URS-A1 Readiness Schema and State Model

Status: implemented on 2026-03-11 as additive foundation

- Problem: runtime truth is split across FE warmup, regime warmup, strategy-local gates, and execution safety without one canonical readiness object or separate permissions for protect-only vs new risk.
- Scope: canonical readiness schema, owners, state enum, signal-level additive surfaces, explicit runtime permissions.
- Owner domains: market_data, feature_engineering, regime_detector, decision_making, execution_position, policy arbiter.
- In-scope files: readiness contract module, strategy signal payload builders, gateway contract checks, additive schemas, package spec.
- Out-of-scope boundaries: startup planner, analytics restore, bar identity hardening, gap repair, rollout activation.
- Invariants: keep `readiness.warmup_ok` backward-compatible; do not make Quadratic HTF a global gate; do not merge `can_manage_existing_risk` with `can_open_new_risk`; do not flip live runtime to Quadratic.
- Deliverables: package spec, canonical enum/model, owner map, additive `runtime_readiness`/`runtime_permissions` payloads, gateway respect for explicit open-risk denial.
- Tests: contract serialization tests, signal payload additive tests, gateway protect-only test, MR/md_amr compatibility assertions.
- Rollback/safety: additive-only fields, no config flip, legacy gates remain active.
- Done when: code has one reusable readiness model and signal-level permissions surface without changing current live default behavior.

## URS-A2 Canonical Bar Identity and Replay Identity Specification

Status: implemented on 2026-03-11 as additive canonical identity layer

- Problem: `bar_end_ts_ms`, `bar_close_ts`, `close_ts`, event timestamps, and extracted downstream timestamps are still mixed implicitly.
- Scope: canonical bar identity object, replay identity token, naming rules, downstream adapters, schema references.
- Owner domains: market_data for canonical bar identity; replay/DR for replay identity.
- In-scope files: bar schemas, aggregator payloads, WAL/replay identity builders, consumers with timestamp extraction.
- Out-of-scope boundaries: gap repair policy, startup hydration sequencing, restore orchestration.
- Invariants: one canonical close identity per live/replay/warmup path; no silent timestamp aliasing.
- Deliverables: spec, shared identity type/helpers, schema updates, consumer migration shims.
- Tests: producer/consumer identity tests, replay identity round-trip, no alias-mixing regressions.
- Rollback/safety: additive aliases allowed only behind explicit bridge fields during migration.
- Done when: live/replay/warmup point to one canonical bar identity and replay token contract.

## URS-B1 Gap Policy

Status: implemented on 2026-03-11 as additive gap consequence layer

- Problem: gaps are detected but mostly informational; they do not deterministically change readiness or trading permissions.
- Scope: formal gap consequence model: repair, invalidate, degrade-to-non-trading.
- Owner domains: market_data for continuity facts; policy arbiter for final trading consequences.
- In-scope files: bar aggregator gap outputs, readiness invalidation logic, policy mapping, telemetry.
- Out-of-scope boundaries: restore implementation, startup planner orchestration, Quadratic rollout.
- Invariants: gaps must have policy consequences; invalidation must not silently reopen risk.
- Deliverables: spec, gap-state model, policy mapper, telemetry counters.
- Tests: gap consequence unit tests, trading-disable tests, non-trading degrade tests.
- Rollback/safety: fail-closed on ambiguous gap classification.
- Done when: gaps move readiness into an explicit degraded/invalidated state instead of a log-only note.

## URS-B2 Analytics Restore

Status: implemented on 2026-03-11 as additive analytics-restore truth layer with protect-only restart semantics

- Problem: restart is partially execution-safe but analytics state is not restored or declared cold honestly.
- Scope: restore or honest cold-state path for bars, FE caches, regime detector, pillars, decision caches, strategy-local startup state.
- Owner domains: feature_engineering, regime_detector, decision_making, execution_position.
- In-scope files: DR loader, startup restore hooks, state serializers/deserializers, honest-cold declarations.
- Out-of-scope boundaries: startup planning, canonical bar identity spec creation, rollout activation.
- Invariants: do not treat execution restore as proof of analytics restore; protect-only must remain possible.
- Deliverables: spec, restore adapters or explicit cold-paths, state restoration telemetry.
- Tests: restart restore tests, honest-cold tests, md_amr local hydration preservation tests.
- Rollback/safety: if restore evidence is incomplete, declare cold/partial instead of guessing.
- Done when: restart can either restore analytics state or publish honest cold/partial readiness with evidence.

## URS-B3 Startup Hydration Planner Design

Status: implemented on 2026-03-11 as additive planning/report layer

- Problem: startup hydration responsibilities are blurred; planner logic risks becoming a god-object and owner of readiness truth.
- Scope: split Planner, Hydrator/Importer, Replayer, Readiness evaluator, Policy arbiter.
- Owner domains: bootstrap/runtime coordination only; owner truth remains in domain owners.
- In-scope files: startup composition root, bootstrap coordinators, hydration services, policy wiring.
- Out-of-scope boundaries: strategy-scoring math, broad domain refactors, active config rollout.
- Invariants: planner does not fetch data directly, replay directly, or own final trading permission.
- Deliverables: spec, role boundaries, orchestration interfaces, minimal coordinator wiring.
- Tests: planner role isolation tests, startup sequence tests, owner-truth preservation tests.
- Rollback/safety: coordinator remains additive and can be disabled cleanly.
- Done when: startup hydration is coordinated by explicit roles without centralizing runtime truth.

## URS-C1 Strategy Compatibility and Isolation Matrix

Status: implemented on 2026-03-11 as additive compatibility SSOT and planner input

- Problem: shared readiness/bootstrap surfaces can regress mean_reversion and md_amr even though they do not use Quadratic directly.
- Scope: code-facing strategy compatibility matrix and per-strategy readiness dependency map.
- Owner domains: decision_making with explicit consumer contracts from feature_engineering and regime_detector.
- In-scope files: strategy registry/compatibility artifacts, strategy-aware gates, tests for Aurora v2, Aurora Quadratic, mean_reversion, md_amr.
- Out-of-scope boundaries: regime redesign, rollout activation, analytics restore internals.
- Invariants: MR must not depend on Quadratic HTF by default; md_amr must not be double-gated by shared bootstrap.
- Deliverables: matrix artifact, strategy-aware gate wiring, compatibility tests.
- Tests: MR non-blocking tests, md_amr bootstrap tests, mixed-symbol assignment tests.
- Rollback/safety: default to current isolated behavior when explicit strategy contract is absent.
- Done when: shared contracts are strategy-aware in code, not just in prose.

## URS-D1 Regime Layering

Status: implemented on 2026-03-11 as additive layered-regime contract split

- Problem: structural regime is per-symbol in practice, but global leakage and microstructure creep remain in downstream consumers.
- Scope: formalize structural regime layer, isolate global leakage, define downstream execution micro regime as separate layer.
- Owner domains: regime_detector for structural regime; execution/FE for micro regime.
- In-scope files: regime detector outputs, execution consumers, decision shared caches, strategy consumers.
- Out-of-scope boundaries: scoring rollout, startup planner, gap repair.
- Invariants: do not inject microstructure into core structural classifier; do not keep last-writer-wins shared regime as SSOT.
- Deliverables: spec, contract split, cache isolation changes, telemetry.
- Tests: per-symbol regime consumer tests, global leakage regression tests.
- Rollback/safety: preserve current classifier math while changing only contract boundaries.
- Done when: structural regime and execution micro regime are separate and downstream consumers stop relying on global leakage.

## URS-E1 Quadratic Shadow Rollout and Rollback Specification

Status: implemented on 2026-03-11 as additive rollout/rollback contract with shadow evaluation and explicit v2 fallback mode

- Problem: Quadratic code exists, but readiness/bootstrap/rollback semantics are not explicit or one-step safe.
- Scope: shadow rollout mode, rollback-armed behavior, explicit switchback to v2, observability for rollout state.
- Owner domains: policy arbiter, decision_making Aurora runtime, execution safeguards.
- In-scope files: rollout policy config, shadow compare wiring, rollback command path, operator telemetry.
- Out-of-scope boundaries: foundational readiness/bar/gap/restore work that must land first.
- Invariants: no active config flip before foundations; rollback must preserve protect-existing-risk behavior.
- Deliverables: spec, rollout state machine, explicit rollback path, tests.
- Tests: shadow rollout tests, one-step rollback tests, protect-only persistence tests.
- Rollback/safety: rollback is explicit, tested, and does not require manual state surgery.
- Done when: Quadratic can shadow or activate behind explicit readiness and return to v2 in one tested step.
