# Alpha Search Quality and Debt

## 1. Current Quality Position

The current tree has stronger boundaries than the older docs suggested:

- config models are strict and fail closed
- judge runtime mode is still bounded to off and shadow
- the simulator is kept offline even when shutdown export is enabled
- the current plugin suppresses judge experts from the generic alpha-score stream

Those are strengths, but they also define where future changes tend to go wrong.

## 2. Main Architectural Hotspots

### 2.1 Dual Runtime Shapes

alpha_search now has both a preserved standalone runtime and an embedded main.py plugin path.

That split is intentional, but it creates a recurring drift risk: docs, plans, and refactors can accidentally describe only one path and then make false ownership claims about the whole domain.

### 2.2 Split Config Surfaces

The domain owns multiple config surfaces that look related but are not interchangeable:

- config/alpha_search.yaml for the embedded plugin
- config/judge_simulator.yaml for the offline simulator
- historical scenario and runtime configs under the standalone runner path

Confusing these surfaces is a recurrent source of design drift.

### 2.3 Broad Domain Surface Area

alpha_search now spans:

- provider scoring
- judge shadow evidence production
- standalone replay tooling
- simulator and summary artifact generation

This increases the chance of accidental cross-boundary changes, especially attempts to give alpha_search decision or execution authority that it does not own.

## 3. Debt Ledger

| Debt item | Risk | Verified anchor | Recommended posture |
|-----------|------|-----------------|---------------------|
| Dual-path runtime documentation drift | people document only the standalone path or only the embedded plugin path | main.py and runtime/launcher.py both remain active anchors | preserve the dual-path narrative explicitly in docs and planning |
| Config-family confusion | operators or future changes can mix plugin config and simulator config responsibilities | config_models.py and judge/simulator/cli.py load different authorities | keep config families separate unless there is a deliberate migration plan |
| Legacy compatibility surfaces | old config and scenario shapes can be mistaken for the current production authority | AlphaSearchConfig still carries a legacy bucket and compatibility parsing | treat legacy paths as compatibility seams, not as the preferred architecture |
| Split test trees | important coverage is divided across tests/domains/... and tests/apps/reference/... which is easy to under-sample during focused work | both test families are populated in the current tree | choose targeted test slices deliberately instead of assuming one directory is enough |
| Shutdown export coupling | shutdown export reuses the offline CLI path and can be over-interpreted as a live runtime mode | backtest_plugin.shutdown() reuses simulator loader and runner | keep the hook bounded, optional, and fail-closed |
| UNCERTAIN regime gating split between two override paths | shadow scenarios silently produced 0 signals when only the per-asset regime override was applied | shadow/registry_adapter.py overrides both `aurora.assets.{sym}.regime_thresholds.UNCERTAIN` and `aurora.decision.regime_threshold_multipliers.UNCERTAIN`; scenario_matrix.yaml S03/S05/S06/S20 use the latter directly | when adjusting UNCERTAIN behavior, audit both paths together — they target different config surfaces |
| Scenario IDs naming drift | scenario_id can promise a directional behavior (e.g. former `S19_ENSEMBLE_MR_SHORT_BIAS`) that the override weights do not implement; misleads readers and reports | renamed to `S19_ENSEMBLE_MR_BALANCED_VARIANT`; ensemble.py has no directional flip mechanism for ta_ensemble | only encode behavior in scenario_id that is implemented in code or override; if a directional bias is wanted, add an explicit flip mechanism rather than a name |

## 4. Non-Debt Boundaries That Must Stay Fixed

The following are not cleanup opportunities unless the repo explicitly decides to redesign them:

- alpha_search being outside Aurora DomainsConfig
- judge shadow outputs remaining non-authoritative
- the simulator remaining offline-only
- Phase 6 semantics staying out of Phase 5 summary output

Trying to "simplify" any of those without a migration plan would be a scope change, not a debt fix.

## 5. Safe Improvement Directions

If this domain is extended later, the lowest-risk improvements are:

- keep docs anchored to the current tree before changing architecture
- preserve fail-closed behavior on new provider or simulator surfaces
- add verification at the seam being changed instead of broad refactors
- isolate experimental complexity in new helper layers rather than widening existing runtime authority
