# Regime Provenance Hardening Report

Date: 2026-04-16
Status: COMPLETE
Package: explicit same-bar truth, cache provenance, and ordering-safe observability

## 1. Executive Verdict

The narrow additive hardening package is complete.

The decision boundary now carries explicit machine-readable regime provenance, so the runtime can distinguish:

- same-bar detector truth
- cached previous-bar regime
- missing detector heartbeat fail-closed

without inferring provenance from timestamp deltas.

Focused validation is green:

- 16 focused tests passed
- same-bar provenance is explicit on the real detector -> FE -> Aurora path
- cached-previous-bar provenance remains explicitly proven in the timing harness

## 2. Scope Implemented

The package was intentionally limited to the structural regime path that feeds direct Aurora and Mean Reversion decision handling.

Implemented surfaces:

- shared runtime provenance helper contract
- detector payload enrichment
- FE cache and CMD regime snapshot enrichment
- Aurora cache/state preservation and signal/features surfacing
- Mean Reversion cache/state preservation and signal payload surfacing
- deterministic seam tests and real integration proof

Intentionally not broadened:

- generic decision_making event_handlers provenance object
- safety_gates extraction path
- telemetry JSONL schemas or audit record formats

## 3. Contract Surface

New additive regime fields carried inside existing regime snapshots:

- regime_source
- regime_event_ts_ms
- regime_same_bar
- regime_provenance_reason

Supported regime_source values:

- same_bar_detector
- cached_previous_bar
- missing_detector_heartbeat

Observed provenance reasons used by the package:

- same_bar_detector_truth
- cached_previous_bar_regime
- explicit_uncertain_same_bar
- explicit_uncertain_cached_regime
- missing_detector_heartbeat_fail_closed

Important contract correction:

- regime_event_ts_ms is resolved in bar-end time domain first from regime_event_ts_ms, then ts_ms, then ts, and only then bar_close_ts_ms

Why this matters:

- the FE or detector path can canonicalize close_boundary_ts_ms as bar_end_ts_ms + 1
- CMD bar_close_ts remains bar_end_ts_ms
- same-bar classification must therefore compare using bar-end timestamps, or same-bar truth is misclassified as cached_previous_bar

## 4. Producer And Consumer Map

Producers:

- apps/reference/contracts/runtime_regime_layers.py
- apps/reference/domains/regime_detector/regime_detector.py
- apps/reference/domains/feature_engineering/feature_engineering.py

Consumers:

- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/mean_reversion_handler.py

Proof surfaces:

- tests/sim/test_regime_timing_edge_cases.py
- tests/integration/test_regime_provenance_hardening.py

## 5. Files Changed

- apps/reference/contracts/runtime_regime_layers.py
- apps/reference/domains/regime_detector/regime_detector.py
- apps/reference/domains/feature_engineering/feature_engineering.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/mean_reversion_handler.py
- tests/sim/test_regime_timing_edge_cases.py
- tests/integration/test_regime_provenance_hardening.py

## 6. Minimum Safe Package Reasoning

The package keeps provenance inside the existing regime object because the CMD schema is strict at the top level while regime snapshots already allow additive properties.

This is the smallest safe contract surface that:

- preserves backward compatibility for current CMD consumers
- makes provenance explicit at the decision boundary
- avoids schema widening outside the regime snapshot
- proves behavior on the real detector -> FE -> Aurora wiring

The package also keeps the direct Aurora and Mean Reversion paths aligned without widening into unrelated execution or generic decision_making surfaces.

## 7. Validation Evidence

Focused validation command outcome:

- tests/sim/test_regime_timing_edge_cases.py
- tests/integration/test_regime_provenance_hardening.py
- tests/integration/test_pillars_quadratic_pipeline.py
- result: 16 passed, 0 failed

What is proven by those tests:

- explicit same-bar detector truth is surfaced through the real detector -> FE -> Aurora stack
- previous-bar cache provenance is machine-readable in the ordering harness
- explicit uncertain regime provenance is machine-readable
- missing-heartbeat fail-closed provenance is explicit
- MR signal payloads carry the same provenance fields

Additional nearby regression sweep:

- tests/domains/decision_making/test_aurora_handler.py
- tests/domains/decision_making/test_cmd_process_strategy.py
- tests/domains/decision_making/test_mr_bar_gating.py
- result: 35 passed, 3 skipped, 2 failed

The two failures are in test_cmd_process_strategy.py and fail during Aurora config mocking with an invalid OperationalMode MagicMock value. The stack does not enter the new provenance logic and the failures are treated as pre-existing or unrelated to this package.

## 8. Backward Compatibility Assessment

Risk level: LOW

Why low:

- all fields are additive
- no existing regime fields were removed or renamed
- no existing public handler entrypoints changed
- no execution-position or order-lifecycle contracts were widened
- CMD top-level schema remains unchanged

Behavioral change worth noting:

- when synchronous current-bar detector delivery exists, the fully wired stack now correctly classifies current detector truth as same_bar_detector instead of cached_previous_bar even if close-boundary canonicalization uses +1ms

This is a correctness fix, not a semantics expansion.

## 9. Residual Notes

The full detector -> FE -> Aurora stack does not naturally demonstrate cached_previous_bar at the current bar when detector delivery is synchronous, because the current-bar detector event arrives before CMD emission and correctly overrides stale cache.

That is why cached_previous_bar remains proven in the deterministic timing harness rather than the fully wired synchronous integration path.

## 10. Follow-Up Recommendation

Recommended next package:

- add an optional strict guard that allows entry logic to require same_bar_detector when a strategy is configured to reject cached structural regime at open-decision time

That follow-up should remain separate from this package because it changes policy behavior, whereas the current package only hardens provenance truth and observability.
