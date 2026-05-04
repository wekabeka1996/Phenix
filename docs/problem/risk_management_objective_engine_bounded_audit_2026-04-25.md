# Risk Management / Objective Engine Bounded Audit

## Scope

This package is a bounded verification-first audit of exactly two domains:

- apps/reference/domains/risk_management
- apps/reference/domains/objective_engine

Constraints preserved:

- no risk score formula change
- no Objective Engine scoring or gating semantics change
- no TradingRiskConfig or Pydantic model migration in this package
- no broad validator refactor
- no delete/move of code unless references and tests justify it

One narrow patch was allowed only when a defect was directly proven.

## Verdict

ACCEPTED_WITH_NARROW_REPAIR

The external audit bundle was directionally useful but materially overcalled several findings. On the audited runtime surface, the only confirmed defect that justified code change was a risk_management config-contract gap in DailyRiskState init-time parsing of risk.daily.max_drawdown_pct.

Most remaining items are either:

- maintainability debt on non-runtime or low-risk helper surfaces
- false positives where fail-closed guards already exist
- one telemetry-state item that still needs runtime proof before any code change

## Key Runtime Map

### risk_management

- apps/reference/domains/risk_management/risk_management.py
  - class RiskManagement
  - public methods: on_features_calculated, on_portfolio_state_updated, validate_risk_thresholds, test_risk_thresholds
  - internal control points: _calculate_risk_parameters, _get_risk_score_weights, _get_max_risk_score
- apps/reference/domains/risk_management/daily_gate.py
  - class DailyRiskState
  - helper surfaces: _d, _fmt_pct, _fmt_usd, _now_utc
- apps/reference/domains/risk_management/domain_dict.json
  - event imports: EVT:FEATURES_CALCULATED, EVT:PORTFOLIO_STATE_UPDATED
  - event exports: EVT:RISK_ASSESSMENT_COMPLETED, EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE
- apps/reference/domains/risk_management/schemas/risk_assessment_v1.json

### objective_engine

- apps/reference/domains/objective_engine/runtime.py
  - class ObjectiveEngineRuntime
  - event imports: EVT:TRADE_INTENT_PROPOSED, EVT:TRADE_EXECUTED, EVT:REGIME_DETECTED, EVT:MARKET_TICK_RECEIVED
  - event export: EVT:OBJECTIVE_REALIZED_V1
- apps/reference/domains/objective_engine/adapters.py
  - build_signal_input
  - build_market_input
  - build_structure_input
  - build_structure_input_from_prices
  - compute_projected_order_notional
  - build_exposure_input
  - build_behavior_input
  - build_execution_input
  - build_objective_input
- apps/reference/domains/objective_engine/types.py
  - ObjectiveSignalInput
  - ObjectiveMarketInput
  - ObjectiveStructureInput
  - ObjectiveExposureInput
  - ObjectiveBehaviorInput
  - ObjectiveExecutionInput
  - ObjectiveInput
  - ObjectiveTrace
  - ObjectiveScore
- apps/reference/domains/objective_engine/pretrade_kernel.py
  - evaluate_pretrade_objective
- apps/reference/domains/objective_engine/engine.py
  - evaluate_objective
- apps/reference/domains/objective_engine/snapshot_registry.py
  - class ObjectiveSnapshotRegistry
- apps/reference/domains/objective_engine/realized_types.py
  - ObjectiveSnapshot
  - ActiveObjectivePosition
  - ObjectiveRealizedEvent

## Runtime Consumers

- apps/reference/bootstrap/domain_builder.py constructs RiskManagement and ObjectiveEngineRuntime.
- apps/reference/domains/decision_making/core/facade.py listens to EVT:RISK_ASSESSMENT_COMPLETED.
- apps/reference/domains/shadow_telemetry/snapshot_store.py also consumes EVT:RISK_ASSESSMENT_COMPLETED.
- apps/reference/domains/decision_making/gates/objective_gate_evaluator.py is the main consumer path for objective_engine adapters and evaluate_objective.
- apps/reference/domains/strategies/runtimes/aurora/decision.py, apps/reference/domains/strategies/runtimes/mean_reversion/handler.py, and apps/reference/domains/strategies/runtimes/md_amr/handler.py call the shared objective gate evaluator.

## FACTS

- RiskManagement is a strict AuroraConfig-only surface at construction time and rejects dict config.
- DailyRiskState is also a strict AuroraConfig-only root surface, but it intentionally reads cfg.trading.risk as a Dict[str, Any]. This matches TradingConfig.risk, which is still a legacy dict contract in apps/reference/config_models.py.
- ObjectiveEngineRuntime only activates when config.domains.objective_engine.enabled is truthy.
- compute_projected_order_notional already fails closed when position_queries is None, when sizing rejects, and when sizing_dbg lacks order_notional.
- ObjectiveSnapshotRegistry is covered by direct tests for entry bind/full close and reduce_only close-reason propagation.
- The runTests tool was not useful for this slice during audit because it returned generic process-termination summaries without actionable tracebacks. Direct pytest runs were used for executable evidence instead.
- A direct Python probe before the patch proved that DailyRiskState accepted risk.daily.max_drawdown_pct='bad' and printed NO_EXCEPTION.

## INFERENCES

- The strongest real contract problem in the audited surface was not the existence of _d itself, but reusing that forgiving helper for init-time config parsing.
- That defect was fail-closed in runtime outcome, not fail-open: bad config could silently collapse max_drawdown_pct to 0 and block all opens, while obscuring the real configuration error.
- Several external-audit claims confused helper duplication or compatibility seams with live runtime defects.
- objective_engine currently has better fail-closed behavior than the external audit suggested, especially around missing sizing truth.

## ASSUMPTIONS

- Current repo config and tests reflect the intended live contract for these two domains.
- Objective Engine input builders are consumed through the shared objective gate evaluator rather than via ad hoc direct callers elsewhere.

## UNKNOWNS

- snapshot_registry close-and-reopen semantics on overshoot reversal fills were not proven end-to-end in this package
- no live replay or exchange-event corpus was used here to prove multi-fill reversal behavior beyond existing unit coverage
- the runTests harness instability for this slice was not root-caused here

## Claim-By-Claim Verdicts

| # | External claim | Verdict | Severity | Evidence |
| --- | --- | --- | --- | --- |
| 1 | RiskManagement._get_use_absorption_penalty is a meaningful runtime defect | CONFIRMED_MAINTAINABILITY_DEBT | Low | Helper exists, but runtime logic uses cached self._use_absorption_penalty; repo-wide textual search found helper referenced only in its definition and tests. |
| 2 | validate_risk_thresholds / test_risk_thresholds are a runtime problem | CONFIRMED_MAINTAINABILITY_DEBT | Low | Both methods are public diagnostic helpers with test coverage only; no runtime caller was found outside tests. |
| 3 | objective_engine build_structure_input duplication is a defect | CONFIRMED_MAINTAINABILITY_DEBT | Low | Two builders exist for two structure modes and are both used by objective_gate_evaluator; duplication is real but semantics are aligned. |
| 4 | repeated finite-float validators in objective_engine/types.py are a defect | CONFIRMED_MAINTAINABILITY_DEBT | Low | Duplication exists across Pydantic input models; no behavior bug was proven and error messages remain model-specific. |
| 5 | DailyRiskState mixed object/dict access is broken by itself | FALSE_POSITIVE | Low | Root object access is strict, while cfg.trading.risk intentionally remains dict-shaped by TradingConfig contract. The mixed access is compatibility, not by itself a bug. |
| 6 | absorption penalty logic in _calculate_risk_parameters is currently broken | FALSE_POSITIVE | Low | Static review plus direct branch tests showed source-routed and clamped score behavior; no formula defect was proven and no formula change was justified. |
| 7 | daily_gate._d silent fallback is a defect | CONFIRMED_DEFECT | Medium | Narrowed scope: init-time parsing of risk.daily.max_drawdown_pct reused forgiving _d, allowing invalid config to instantiate DailyRiskState without ConfigContractError. Direct probe reproduced NO_EXCEPTION before patch. |
| 8 | objective_engine lacks a fail-closed position_queries guard | FALSE_POSITIVE | Low | compute_projected_order_notional already raises OBJECTIVE_SIZING_UNAVAILABLE for missing position_queries, sizing rejection, and missing order_notional. objective_gate_evaluator tests passed on this path. |
| 9 | sizing_dbg["order_notional"] is an unsafe bug | CONFIRMED_MAINTAINABILITY_DEBT | Low | Cross-module implicit contract exists, but adapter access is wrapped in a fail-closed ValueError. This is coupling debt, not a proven runtime defect. |
| 10 | snapshot_registry flip logic is defective | NEEDS_RUNTIME_PROOF | Medium | Existing tests prove bind/full-close and reduce_only reason flow, but overshoot reversal and same-fill close-plus-reopen semantics were not proven strongly enough for a safe patch. |

## Minimal Repair

### Confirmed root cause

DailyRiskState.__init__ used the forgiving helper _d to parse the config field risk.daily.max_drawdown_pct. That helper returns Decimal("0") for invalid input. As a result, malformed config such as max_drawdown_pct='bad' could instantiate successfully instead of raising ConfigContractError.

### Why this patch is safe

- It does not change _d behavior for runtime portfolio/equity payloads.
- It does not change risk score math.
- It does not change daily gate semantics for valid config.
- It only makes one config field fail closed at the boundary where config must already be authoritative.

### Files changed

- apps/reference/domains/risk_management/daily_gate.py
- tests/domains/risk_management/test_risk_management_coverage.py
- docs/problem/risk_management_objective_engine_bounded_audit_2026-04-25.md

### Exact code change summary

- Added _parse_decimal_config() as a strict config-only decimal parser in daily_gate.py.
- Switched DailyRiskState.__init__ to parse risk.daily.max_drawdown_pct through _parse_decimal_config instead of _d.
- Added a regression test asserting that invalid max_drawdown_pct now raises ConfigContractError.

## Validation

### Pre-patch discriminating probe

```text
NO_EXCEPTION
```

Meaning: invalid max_drawdown_pct='bad' instantiated DailyRiskState before the patch.

### Post-patch focused validation

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_daily_state_invalid_max_drawdown_pct_raises tests/domains/risk_management/test_daily_gate_drawdown_8pct.py::test_daily_gate_uses_equity_cross_usdt_and_blocks_at_8pct_drawdown -q

2 passed in 0.78s
```

### risk_management audit bundle

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_risk_management_methods_and_validation_branches tests/domains/risk_management/test_risk_management_coverage.py::test_test_risk_thresholds_default_and_error_paths tests/domains/risk_management/test_risk_management_coverage.py::test_daily_state_invalid_max_drawdown_pct_raises tests/domains/risk_management/test_daily_gate_drawdown_8pct.py::test_daily_gate_uses_equity_cross_usdt_and_blocks_at_8pct_drawdown -q

4 passed in 0.88s
```

### absorption branch evidence

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_risk_score_high_and_price_invalid_paths tests/domains/risk_management/test_risk_management_coverage.py::test_risk_debug_override_emit_exception_and_clamp_paths -q

2 passed in 0.76s
```

### objective_engine audit bundle

```text
pytest tests/apps/reference/domains/objective_engine/test_objective_engine.py tests/apps/reference/domains/objective_engine/test_runtime.py tests/apps/reference/domains/objective_engine/test_realized_objective.py tests/domains/decision_making/test_objective_gate_evaluator.py -q

37 passed in 1.49s
```

### Editor diagnostics

- get_errors on daily_gate.py: no errors
- get_errors on test_risk_management_coverage.py: no errors

## Residual Risks

- snapshot_registry still deserves a dedicated reversal/overshoot runtime proof package before anyone changes it.
- sizing_dbg["order_notional"] remains an implicit cross-module contract; it is fail-closed today but brittle for future refactors.
- validate_risk_thresholds and test_risk_thresholds remain public non-runtime helper surface in risk_management.py; they are low-risk debt but not urgent.

## What Was Intentionally Not Changed

- RiskManagement score formula and absorption weighting
- Objective Engine scoring, normalization, and gate semantics
- Pydantic model structure in objective_engine/types.py
- DailyRiskState runtime payload coercion via _d for live portfolio updates
- snapshot_registry flip behavior without stronger runtime proof

## Outcome

The bounded audit found one medium-severity config-contract defect in risk_management and repaired it with a two-file narrow patch. The rest of the external audit claims do not justify further runtime edits under the current package constraints.
