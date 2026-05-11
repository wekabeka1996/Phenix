# AGENT_REPORT_V1

## Executive Summary
A6 repaired the Aurora price_motion boundary contract by promoting top-level CMD transport into the typed seam, resolving canonical Aurora provenance in one place, and making cache fallback same-bar-only and explicitly observable.

## Proven Facts
- apps/reference/domains/decision_making/contracts/boundary_models.py now declares optional top-level price_motion on ProcessStrategyBoundary.
- apps/reference/domains/decision_making/contracts/core_models.py now exposes optional read-only ProcessStrategyCmd.price_motion, and apps/reference/domains/decision_making/contracts/boundary_mappers.py maps it without changing cmd.raw.
- apps/reference/domains/strategies/runtimes/aurora/handler.py now caches price_motion together with cached_price_motion_close_boundary_ts_ms and cached_price_motion_bar_close_ts.
- apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py now resolves price_motion in this order: cmd.price_motion, features.price_motion, cmd.raw["price_motion"], cached FEATURES snapshot, missing.
- apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py now treats prior-bar cache as source=cache with ready=false; only same-bar cache is eligible for local feature injection.
- apps/reference/domains/strategies/runtimes/aurora/decision.py now injects resolved price_motion only into the local mutable features copy used inside Aurora, and removes stale/missing blocks from that local copy.
- apps/reference/domains/strategies/runtimes/aurora/decision.py now emits additive top-level fields price_motion_source, price_motion_age_ms, and price_motion_ready on EVT:QUADRATIC_DECISION_TRACE.
- apps/reference/domains/strategies/runtimes/aurora/decision.py now emits scoring.price_motion on EVT:STRATEGY_SIGNAL_PRODUCED and details.price_motion on EVT:STRATEGY_DECISION_BLOCKED, including consumed_by_vol_gate.
- apps/reference/domains/decision_making/intent/schemas/quadratic_decision_trace_v1.json was updated additively to require the new trace provenance fields.
- tests/domains/decision_making/test_aurora_price_motion_provenance.py proves the normal same-bar FE -> typed CMD path resolves as source=cmd_typed, age_ms=0, ready=true, and consumed_by_vol_gate=true on the signal path.
- tests/domains/decision_making/test_aurora_price_motion_provenance.py proves the legacy raw fallback path still resolves as source=cmd_raw_fallback, age_ms=0, ready=true when ProcessStrategyCmd.price_motion is absent but cmd.raw["price_motion"] exists.
- tests/domains/decision_making/test_aurora_price_motion_provenance.py proves nested features-only price_motion remains source=features, and that cmd.price_motion overrides conflicting nested features price_motion.
- tests/domains/decision_making/test_aurora_price_motion_provenance.py proves stale prior-bar cache remains visible as source=cache with age_ms=300000, ready=false, consumed_by_vol_gate=false, and no hidden fallback.
- tests/domains/decision_making/test_aurora_price_motion_provenance.py proves the missing-everywhere case resolves as source=missing, age_ms=null, ready=false.

## Inferred Findings
- Root cause was the decision_making typed seam plus Aurora consumer access pattern, not Feature Engineering emission. FE was already emitting top-level CMD price_motion, but Aurora did not consume it through a first-class typed field.
- Normal same-bar FE -> CMD behavior changed inside Aurora. Evidence: the new same-bar raw-path test shows vol-gate consumption through direct CMD transport; the pre-change repo note in memories/repo/aurora_price_motion_boundary_observability_seam_2026-05-09.md documented that Aurora previously relied on features/cache and had no observed raw rehydration path.
- Legacy/raw fallback behavior is now explicit and bounded. Evidence: the direct ProcessStrategyCmd fallback test shows source=cmd_raw_fallback even when the typed field is absent; FE public payload shape did not change.
- Stale-cache behavior changed fail-closed. Evidence: the stale-cache test shows prior-bar cache is no longer consumed by vol gates, while still remaining observable as source=cache.
- Observability improved materially because trace, signal, and blocked payloads now expose one consistent provenance surface instead of requiring inference from cache behavior.

## Contradictions / Evidence Gaps
- No live runtime log capture was collected in this task, so same-bar FE -> CMD behavior is proven by focused tests and code-path inspection, not by live production artifacts.
- The task did not rerun the entire repo test suite; validation was intentionally bounded to the touched seam and adjacent contracts.
- The task did not add or audit downstream consumers outside Aurora for new scoring.price_motion/details.price_motion nested observability fields because the signal schema remains additive.

## Root Cause Candidates
- Confirmed primary cause: ProcessStrategyBoundary / ProcessStrategyCmd did not promote top-level CMD price_motion into a typed first-class field.
- Confirmed contributing cause: Aurora scoring helper treated the FEATURES cache as the effective primary path and did not expose consistent provenance for stale or missing data.
- Confirmed masking layer: trace and blocked surfaces did not previously expose source/age/ready, which made cache-vs-raw behavior hard to audit.

## Operational Risk
- Runtime
- Observability Gap

## Files / Areas Touched
- apps/reference/domains/decision_making/contracts/boundary_models.py
- apps/reference/domains/decision_making/contracts/core_models.py
- apps/reference/domains/decision_making/contracts/boundary_mappers.py
- apps/reference/domains/strategies/runtimes/aurora/handler.py
- apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py
- apps/reference/domains/strategies/runtimes/aurora/decision.py
- apps/reference/domains/decision_making/intent/schemas/quadratic_decision_trace_v1.json
- tests/domains/decision_making/test_boundary_models.py
- tests/domains/decision_making/test_boundary_mappers.py
- tests/domains/decision_making/test_aurora_price_motion_provenance.py
- tests/domains/decision_making/test_aurora_quadratic_logging.py
- tests/domains/decision_making/test_aurora_vol_adj_gates.py
- tests/domains/decision_making/test_aurora_vol_adj_gates_fixed.py
- tests/config/test_btcusdt_aurora_runtime_fields.py

## Validation Performed
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_boundary_models.py tests/domains/decision_making/test_boundary_mappers.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_aurora_price_motion_provenance.py tests/domains/decision_making/test_aurora_quadratic_logging.py tests/domains/decision_making/test_aurora_vol_adj_gates.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_aurora_vol_adj_gates_fixed.py tests/contracts/test_strategy_signal_produced_schema_additive.py tests/config/test_btcusdt_aurora_runtime_fields.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_aurora_price_motion_provenance.py tests/domains/decision_making/test_aurora_quadratic_logging.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_aurora_price_motion_provenance.py tests/domains/decision_making/test_aurora_quadratic_logging.py tests/domains/decision_making/test_aurora_vol_adj_gates.py tests/domains/decision_making/test_aurora_vol_adj_gates_fixed.py -q
- VS Code diagnostics check on all touched runtime/contracts/test files: no errors found.

## A6 Addendum - Provenance Ambiguity Cleanup
- Final price_motion_source labels are exactly: cmd_typed, cmd_raw_fallback, features, cache, missing.
- Final Aurora resolver order is exactly: cmd.price_motion -> features.price_motion -> cmd.raw["price_motion"] -> same-bar cache -> missing.
- QUADRATIC_DECISION_TRACE emitter coverage was rechecked after the schema change: the only runtime emitter in apps/reference/domains/strategies/runtimes/aurora/decision.py explicitly sets price_motion_source, price_motion_age_ms, and price_motion_ready, and _build_quadratic_decision_trace also carries those fields for reused trace payloads.
- Cleanup tests run after the label split: the focused 11-test provenance/logging slice passed, and the broader 34-test provenance/logging/vol-gate slice passed.
- No thresholds, scoring weights, FE public payload shape, or vol-gate math changed in this cleanup. The change is limited to provenance labeling, resolver precedence, schema enum values, tests, and report wording.

## Residual Risk
- Live FE -> CMD traffic was not replayed through a captured runtime artifact in this task, so there is still a bounded risk that an untested producer variant supplies close-boundary metadata differently than the focused tests.
- Other Aurora blocked branches not exercised by the focused tests now carry additive details.price_motion fields, but downstream operator tooling for those fields was not audited here.

## What Remains Unproven
- Whether any external dashboards, exporters, or forensics tooling depend on the exact absence of scoring.price_motion or details.price_motion.
- Whether live ordering/restart timing produces any additional same-bar edge case beyond the tested same close_boundary_ts_ms and prior-bar cache cases.
- Whether all non-Aurora strategy runtimes want the same provenance contract; this change was intentionally Aurora-local only.

## Minimal Safe Verdict
- The requested A6 boundary/provenance repair is implemented in scope.
- Normal same-bar FE -> CMD transport is now consumed through the typed Aurora seam and reported as source=cmd_typed; this is a real Aurora behavior change supported by focused tests, not by live runtime proof.
- Legacy raw fallback remains available and explicit.
- Stale cache is now visible but fail-closed and not consumed, which is also a real Aurora behavior change supported by focused tests.
- The FE public payload shape was not changed.
