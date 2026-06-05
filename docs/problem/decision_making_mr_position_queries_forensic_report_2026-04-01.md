# Deep Evidence-Based Audit Of Unresolved Decision Making Risks Around MR, PositionQueries, md_amr, And Mean Reversion Logger

Date: 2026-04-01

Scope:
- apps/reference/domains/decision_making/mean_reversion_handler.py
- apps/reference/domains/decision_making/position_queries.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/decision_making/mean_reversion_logger.py
- apps/reference/domains/feature_engineering/feature_engineering.py
- apps/reference/domains/feature_engineering/mean_reversion_strategy.py
- apps/reference/domains/market_data/bar_aggregator.py
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/decision_making/strategy_gateway.py
- apps/reference/domains/objective_engine/adapters.py
- apps/reference/domains/position_tracking/position_tracking.py
- apps/reference/config_models.py
- config/aurora/domains.yaml
- targeted tests under tests/integration, tests/domains/decision_making, tests/domains/market_data, tests/domains/execution_position, tests/decision_making

Environment:
- Repository state as inspected on 2026-04-01
- Branch: Phenix_v2
- Investigation mode: code audit, targeted pytest, narrow runtime probes
- No runtime code edits were made while producing this report

Method:
- SSOT-first review via Copilot_Master_Roadmap.md and repository memories
- Full reads of the primary runtime surfaces and their direct upstream/downstream callers
- Symbol usage mapping to determine blast radius
- Focused pytest execution on the relevant code paths
- Two narrow runtime probes to separate local idempotency facts from end-to-end live-order assumptions

## 1. Executive Summary

- The strongest confirmed unresolved issue in this scope is the missing local idempotency guard on the mean reversion CMD path.
- This issue is real, but its exact severity must be stated carefully. It is a proven local correctness defect in apps/reference/domains/decision_making/mean_reversion_handler.py and apps/reference/domains/feature_engineering/mean_reversion_strategy.py, because the same completed bar can be processed twice and mutate strategy state twice.
- I did not prove the stronger claim that the current dominant live path already produces duplicate live orders for the same bar under normal operation. The upstream live path has partial protection in bar aggregation, and the MR strategy cooldown can mask duplicate emission even while duplicate state mutation still occurs.
- The public 4-tuple contract in apps/reference/domains/decision_making/position_queries.py is a real contract fragility, but the production blast radius is bounded. It is not yet a proven high-severity live trading bug.
- The hardcoded 1e-9 thresholds inside PositionQueries are real SSOT drift relative to config/aurora/domains.yaml, but the strongest evidence currently supports maintainability and future-drift risk rather than an already-proven runtime break.
- The current md_amr runtime surface no longer shows the previously suspected unresolved defects in this scope. Duplicate-live guards exist in code, rr_post is present in code, and the focused md_amr pytest batch passed.
- The mean reversion logger currently looks like a fail-safe append-only observability component with missing dedicated coverage, not a confirmed runtime defect.
- The next practical patch should target apps/reference/domains/decision_making/mean_reversion_handler.py first, because it is the smallest localized fix that addresses a proven live code defect without broad refactoring.

## 2. Decision Matrix

| Surface | Question | Status | Classification | Recommended Priority |
| --- | --- | --- | --- | --- |
| mean_reversion_handler.py | Is duplicate CMD / duplicate bar handling a real unresolved risk | PROVEN locally, PARTIAL end-to-end | Local idempotency and state-correctness defect | P1 first patch |
| position_queries.py | Is the tuple public contract operationally dangerous | PARTIAL | Bounded contract fragility | P2 |
| position_queries.py thresholds | Are hardcoded 1e-9 checks a proven runtime bug | PARTIAL | SSOT drift and future-drift risk | P3 |
| md_amr_handler.py | Are duplicate-live or rr_post gaps still unresolved runtime bugs | NOT PROVEN as open defects | Mostly already fixed plus proof gap | No urgent code patch |
| mean_reversion_logger.py | Is there an unresolved runtime problem | NOT PROVEN | Coverage gap only on current evidence | No urgent code patch |

## 3. Evidence By Surface

### 3.1 Mean Reversion Duplicate CMD And Duplicate Bar Risk

#### Facts

- MeanReversionHandler explicitly documents CMD:PROCESS_STRATEGY as the primary decision trigger at apps/reference/domains/decision_making/mean_reversion_handler.py:190 and apps/reference/domains/decision_making/mean_reversion_handler.py:350.
- The handler subscribes to CMD:PROCESS_STRATEGY at apps/reference/domains/decision_making/mean_reversion_handler.py:357.
- The main runtime entry point is apps/reference/domains/decision_making/mean_reversion_handler.py:1741.
- The handler declares per-symbol state named _last_counted_bar_end_ts_ms at apps/reference/domains/decision_making/mean_reversion_handler.py:215.
- Repo-wide search found no runtime usage of _last_counted_bar_end_ts_ms beyond the declaration in the handler and a test harness assignment in tests/integration/test_mr_v1_e2e_price_motion.py:160.
- The handler performs tf_sec validation, bar_close_ts validation, and bar presence validation in apps/reference/domains/decision_making/mean_reversion_handler.py:1773 through apps/reference/domains/decision_making/mean_reversion_handler.py:1857.
- The handler then parses the bar and calls strategy.on_bar at apps/reference/domains/decision_making/mean_reversion_handler.py:1939 and apps/reference/domains/decision_making/mean_reversion_handler.py:1940.
- No same-bar or older-bar idempotency check is performed in the inspected handler path before strategy.on_bar.
- The MR strategy appends the incoming completed bar to state before any cooldown check at apps/reference/domains/feature_engineering/mean_reversion_strategy.py:342 through apps/reference/domains/feature_engineering/mean_reversion_strategy.py:369.
- The cooldown check only happens after the bar has already been appended and indicators potentially updated, at apps/reference/domains/feature_engineering/mean_reversion_strategy.py:376 through apps/reference/domains/feature_engineering/mean_reversion_strategy.py:455.
- FeatureEngineering emits CMD:PROCESS_STRATEGY after its gate checks in apps/reference/domains/feature_engineering/feature_engineering.py:1979 through apps/reference/domains/feature_engineering/feature_engineering.py:2216.
- The emitted payload includes bar_close_ts and explicitly comments that it is required for dedup/idempotency at apps/reference/domains/feature_engineering/feature_engineering.py:2174 and apps/reference/domains/feature_engineering/feature_engineering.py:2175.
- The bar-path helper _create_synthetic_tick_for_bar_close intentionally sets the synthetic previous tick timestamp to bar_ts - 1 at apps/reference/domains/feature_engineering/feature_engineering.py:1028 through apps/reference/domains/feature_engineering/feature_engineering.py:1054.
- I did not find a dedicated per-symbol bar_close_ts dedup check in FeatureEngineering on the bar-driven CMD path.
- The dominant live upstream producer BarAggregator drops ticks when ts_ms <= last_ts at apps/reference/domains/market_data/bar_aggregator.py:171.
- That upstream duplicate timestamp protection is covered by tests/domains/market_data/test_bar_aggregator_ssot.py:162.
- Warmup-import bars are emitted through inject_historical_bar without an additional handler-local dedup layer in apps/reference/domains/market_data/bar_aggregator.py:382 through apps/reference/domains/market_data/bar_aggregator.py:402.
- MR routing itself is covered by tests/domains/decision_making/test_mr_bar_gating.py:109 and tests/domains/decision_making/test_cmd_process_strategy.py:281.
- The current test docs for Aurora duplicate CMD behavior already acknowledge lack of explicit dedup as current behavior in tests/domains/decision_making/test_cmd_process_strategy.py:336 through tests/domains/decision_making/test_cmd_process_strategy.py:378.

#### Runtime probes

Probe A: local handler behavior

- I ran a narrow runtime probe that constructed MeanReversionHandler with a stub strategy and fed the exact same CMD payload twice.
- The probe showed strategy.on_bar was called twice with the same symbol and the same end timestamp.
- The probe output was:

```text
{'calls': [('BTCUSDT', 1700000000000, 1700000000000), ('BTCUSDT', 1700000000000, 1700000000000)], 'bars_received': 2, 'bars_completed': 0}
```

- This proves the handler itself is not locally idempotent for identical CMD input when no upstream dedup intervenes.

Probe B: local strategy behavior

- I ran a second narrow runtime probe directly against MeanReversion1mStrategy with the exact same completed bar and timestamp passed twice.
- The probe showed bars_after_first = 1 and bars_after_second = 2.
- The probe output was:

```text
{'bars_after_first': 1, 'bars_after_second': 2, 'why1': 'neutral:insufficient_bars', 'why2': 'neutral:insufficient_bars'}
```

- This proves duplicate processing mutates internal strategy history even in a neutral path.

#### Inferences

- The unresolved MR duplicate issue is not a false positive.
- The exact proven bug is local idempotency failure and duplicate state mutation, not yet a proven end-to-end duplicate live order bug.
- The live market-data path is partially protected because BarAggregator drops duplicate and out-of-order ticks, which lowers but does not eliminate the practical risk.
- The existence of _last_counted_bar_end_ts_ms strongly suggests this exact class of guard was intended or partially scaffolded but is not active in the current runtime path.
- Cooldown does not save state correctness because it executes after the duplicate bar has already been appended.

#### Verdict

- PROVEN as a local runtime correctness defect.
- PARTIAL as an end-to-end live duplicate-order claim.

#### Operational severity

- Severity: S2.
- Justification: duplicate local state mutation is proven in live code, but a wider S1 claim about current duplicate live orders was not established on the dominant live upstream path.

#### Minimal safe fix shape

- Add a per-symbol bar_close_ts idempotency guard in apps/reference/domains/decision_making/mean_reversion_handler.py before strategy.on_bar.
- Use the existing bar_close_ts payload and keep the fix additive and fail-closed.
- Do not broad-refactor FeatureEngineering or the strategy until this local seam is closed.

### 3.2 PositionQueries Public Tuple Contract And Threshold Drift

#### Facts

- apps/reference/domains/decision_making/position_queries.py defines get_position_state at line 98, check_symbol_is_flat at line 151, and calculate_position_size at line 212.
- get_position_state treats abs(qty_signed) < 1e-9 as FLAT at apps/reference/domains/decision_making/position_queries.py:112 through apps/reference/domains/decision_making/position_queries.py:118.
- check_symbol_is_flat treats abs(qty_signed) <= 1e-9 as flat via flat_threshold at apps/reference/domains/decision_making/position_queries.py:194 through apps/reference/domains/decision_making/position_queries.py:202.
- calculate_position_size returns tuple[Optional[Decimal], str, Optional[str], Dict[str, Any]] at apps/reference/domains/decision_making/position_queries.py:219.
- The DecisionMaking facade exposes thin wrappers over PositionQueries at apps/reference/domains/decision_making/decision_making.py:513 through apps/reference/domains/decision_making/decision_making.py:523.
- The production sizing unpack in objective logic is at apps/reference/domains/objective_engine/adapters.py:143.
- The production sizing unpack through the DM wrapper is at apps/reference/domains/decision_making/strategy_gateway.py:764.
- Usage mapping showed calculate_position_size has limited production blast radius: direct production use in objective_engine.adapters and indirect production use through decision_making + strategy_gateway, plus test references.
- Usage mapping showed _check_symbol_is_flat has no broader production fanout beyond its DM wrapper and a split-brain repro test.
- The SSOT precision block exists in config/aurora/domains.yaml:397 through config/aurora/domains.yaml:401.
- The configured values are quantity_min_threshold = 1e-9 and flat_position_threshold = 1e-12 in config/aurora/domains.yaml:398 through config/aurora/domains.yaml:400.
- The corresponding typed model is PrecisionConfig in apps/reference/config_models.py:3489 through apps/reference/config_models.py:3495.
- PositionTracking loads these precision fields in apps/reference/domains/position_tracking/position_tracking.py:146 through apps/reference/domains/position_tracking/position_tracking.py:149.
- Repo-wide search showed quantity_min_threshold is used in position_tracking runtime, but flat_position_threshold was only proven as loaded, not as a meaningful downstream runtime decision threshold in the inspected path.

#### Inferences

- The tuple result is a real public contract fragility because production consumers rely on positional unpacking.
- The blast radius is bounded enough that this is not currently a repository-wide hidden bomb.
- I did not find evidence of an already-triggered wrong-order unpack bug causing a bad trade decision.
- The hardcoded 1e-9 checks in PositionQueries duplicate precision knowledge that also exists in SSOT config.
- Because flat_position_threshold is configured as 1e-12 but not proven as the actual owner of flat-state runtime semantics in this surface, the current evidence supports SSOT drift and maintainability risk more strongly than an already-active runtime bug.

#### Verdict

- Tuple contract: PARTIAL, real fragility but not a proven high-severity live defect.
- Threshold drift: PARTIAL, real SSOT inconsistency but not a proven live defect.

#### Operational severity

- Tuple contract severity: S3.
- Threshold drift severity: S3.
- Justification: the production blast radius is limited, and no concrete trading failure caused by these contracts was reproduced.

#### Minimal safe fix shape

- Introduce an additive named result object for calculate_position_size while preserving the current tuple temporarily.
- Add focused tests that pin both tuple compatibility and named-field semantics.
- Consolidate flat-threshold semantics into one authoritative source, then add one explicit test documenting the chosen threshold contract.

### 3.3 md_amr_handler.py

#### Facts

- md_amr duplicate-live detection exists in apps/reference/domains/decision_making/md_amr_handler.py:460 through apps/reference/domains/decision_making/md_amr_handler.py:464.
- _on_features_calculated checks _is_duplicate_live_event at apps/reference/domains/decision_making/md_amr_handler.py:896.
- _on_process_strategy checks _is_duplicate_live_event again on bar_close_ts at apps/reference/domains/decision_making/md_amr_handler.py:1297 through apps/reference/domains/decision_making/md_amr_handler.py:1304.
- md_amr records rr_post in apps/reference/domains/decision_making/md_amr_handler.py:2205.
- The focused md_amr pytest batch passed 42 tests.
- Relevant validated files included:
  - tests/domains/decision_making/test_md_amr_tf_sec_guard.py
  - tests/domains/decision_making/test_md_amr_strategy_gateway.py
  - tests/domains/decision_making/test_md_amr_silence_observability.py
  - tests/domains/decision_making/test_md_amr_runtime_readiness.py
  - tests/domains/decision_making/test_md_amr_objective_atr_injection.py
  - tests/domains/decision_making/test_md_amr_hybrid_hydration.py
  - tests/domains/decision_making/test_md_amr_clean_start_upgrade.py
  - tests/contracts/test_md_amr_basis_decoupled.py
- tests/domains/decision_making/test_md_amr_runtime_readiness.py:15 proves cold-start gating and tests/domains/decision_making/test_md_amr_runtime_readiness.py:68 proves seeded bars bypass the cold-start gate.

#### Inferences

- The previously suspected duplicate-live problem is not open in the same way as the MR path. md_amr already has explicit local duplicate protection.
- The rr_post field is present in current runtime code.
- The remaining gap is not an obvious runtime defect but rather that I did not find an md_amr-specific regression assertion that directly pins rr_post in the exact payload shape of interest.

#### Verdict

- NOT PROVEN as an unresolved runtime defect.
- Status is best described as already hardened in code plus residual proof gap.

#### Operational severity

- Severity: S3.
- Justification: no failing runtime evidence remained in this scope after code inspection and focused test execution.

### 3.4 mean_reversion_logger.py

#### Facts

- MeanReversionBarLogger is defined in apps/reference/domains/decision_making/mean_reversion_logger.py:22.
- It creates TSV and JSONL sidecar paths in apps/reference/domains/decision_making/mean_reversion_logger.py:38 through apps/reference/domains/decision_making/mean_reversion_logger.py:39.
- It initializes the TSV header once in apps/reference/domains/decision_making/mean_reversion_logger.py:44 through apps/reference/domains/decision_making/mean_reversion_logger.py:49.
- It appends TSV rows in apps/reference/domains/decision_making/mean_reversion_logger.py:94 through apps/reference/domains/decision_making/mean_reversion_logger.py:100.
- It appends JSONL rows in apps/reference/domains/decision_making/mean_reversion_logger.py:102 through apps/reference/domains/decision_making/mean_reversion_logger.py:127.
- It swallows write failures and only logs an error in apps/reference/domains/decision_making/mean_reversion_logger.py:129 through apps/reference/domains/decision_making/mean_reversion_logger.py:132.
- The logger is wired from MeanReversionHandler, with import at apps/reference/domains/decision_making/mean_reversion_handler.py:88 and initialization at apps/reference/domains/decision_making/mean_reversion_handler.py:328 through apps/reference/domains/decision_making/mean_reversion_handler.py:330.
- I did not find a dedicated test file for MeanReversionBarLogger.

#### Inferences

- The logger is intentionally designed not to influence trading decisions.
- The strongest current gap is coverage, especially around serialization edges and file I/O error handling, not a proven defect in the decision path.

#### Verdict

- NOT PROVEN as a runtime defect.
- Current status is coverage gap only.

#### Operational severity

- Severity: S3.
- Justification: write failures are already fail-safe and non-fatal to the decision path.

## 4. Validation Evidence

### 4.1 Focused pytest evidence

The following targeted pytest execution was run:

- tests/integration/test_fe_emits_cmd_process_strategy.py
- tests/domains/market_data/test_bar_aggregator_ssot.py
- tests/domains/market_data/test_bar_aggregator_warmup_import.py
- tests/domains/decision_making/test_mr_bar_gating.py
- tests/domains/decision_making/test_cmd_process_strategy.py
- tests/domains/decision_making/test_strategy_gateway_objective_contracts.py
- tests/domains/execution_position/test_split_brain_repro.py
- tests/domains/decision_making/test_mean_reversion_clean_start_upgrade.py
- tests/decision_making/test_regime_tpsl.py

Observed result summary:

- 80 passed
- 2 skipped
- 2 failed
- 3 errors

Interpretation:

- The failures and errors in that batch were Aurora fixture/runtime-contract issues around OperationalMode in tests/domains/decision_making/test_cmd_process_strategy.py and tests/decision_making/test_regime_tpsl.py.
- They did not invalidate the MR routing, FE emission, bar aggregator, strategy gateway, or split-brain evidence gathered for this report.

The focused md_amr batch was also run:

- tests/domains/decision_making/test_md_amr_tf_sec_guard.py
- tests/domains/decision_making/test_md_amr_strategy_gateway.py
- tests/domains/decision_making/test_md_amr_silence_observability.py
- tests/domains/decision_making/test_md_amr_runtime_readiness.py
- tests/domains/decision_making/test_md_amr_objective_atr_injection.py
- tests/domains/decision_making/test_md_amr_hybrid_hydration.py
- tests/domains/decision_making/test_md_amr_clean_start_upgrade.py
- tests/contracts/test_md_amr_basis_decoupled.py

Observed result summary:

- 42 passed
- 0 failed

### 4.2 Narrow runtime probes

Probe A proved local MeanReversionHandler duplicate processing of identical CMD payloads.

Probe B proved duplicate-state mutation inside MeanReversion1mStrategy for identical bar input.

These probes were intentionally narrow and should not be over-interpreted as proof of a current duplicate-order incident in production.

## 5. Facts, Inferences, Assumptions, Unknowns

### Facts

- The MR handler has no active local same-bar idempotency guard before strategy.on_bar.
- The MR strategy mutates state before cooldown.
- The dominant live BarAggregator path drops duplicate and out-of-order ticks.
- FeatureEngineering emits CMD:PROCESS_STRATEGY with bar_close_ts but without a proven per-bar dedup gate in the bar-driven path.
- PositionQueries uses a positional tuple contract in production code.
- PositionQueries hardcodes 1e-9 while SSOT config also contains position precision thresholds.
- md_amr has explicit duplicate-live checks and rr_post in current runtime code.
- mean_reversion_logger is fail-safe and append-only.

### Inferences

- MR duplicate handling is a real unresolved local defect even if the current live upstream path reduces its frequency.
- PositionQueries is fragile, but not yet proven as a severe runtime break.
- md_amr and mean_reversion_logger do not currently justify entry into the critical patch queue on the evidence inspected here.

### Assumptions

- The dominant live path for MR still flows through market_data.bar_aggregator to feature_engineering and then to mean_reversion_handler.
- No hidden alternate producer of CMD:PROCESS_STRATEGY outside the inspected chain materially changes the findings.

### Unknowns

- I did not reproduce a live duplicate-order incident for MR under the normal market-data path.
- I did not find an md_amr-specific rr_post regression assertion for the exact payload seam of interest.
- I did not find a dedicated logger regression test for mean_reversion_logger.

## 6. Root Cause And Contributing Factors

Primary root cause:

- The MR consumer path accepts bar_close_ts as a dedup identity signal but does not actually enforce local idempotency before mutating strategy state.

Contributing factors:

- The strategy itself appends bars before cooldown, which amplifies the impact of any duplicate delivery that escapes upstream protection.
- FeatureEngineering documents bar_close_ts as dedup-relevant but does not close the seam itself.
- Historical and warmup import paths are not obviously constrained by the same live tick-order protection as the dominant live tick path.
- PositionQueries still exposes positional tuple semantics and duplicated threshold knowledge, which makes future contract evolution riskier.

## 7. Severity Classification

- Mean reversion duplicate local idempotency defect: S2
- PositionQueries tuple contract fragility: S3
- PositionQueries threshold SSOT drift: S3
- md_amr residual concern in this scope: S3
- mean_reversion_logger residual concern in this scope: S3

Severity rationale:

- The MR defect touches live decision-path correctness and is proven in code plus runtime probes, but the evidence does not yet support an S1 claim of currently reproduced duplicate live orders on the normal live path.
- The remaining items are either bounded contract fragility or proof gaps without a demonstrated live failure in this investigation.

## 8. Practical Fix Plan

### Patch 1

Target file:
- apps/reference/domains/decision_making/mean_reversion_handler.py

Goal:
- Add an additive per-symbol bar_close_ts idempotency guard before strategy.on_bar.

Why this goes first:
- It addresses the strongest proven defect.
- It is localized.
- It does not require broad refactoring across FeatureEngineering, strategy code, or event bus semantics.
- The handler already carries a likely intended state slot for counted bar timestamps.

Minimum validation:
- Add a focused regression test proving identical CMD payloads with the same bar_close_ts do not call strategy.on_bar twice.
- Re-run MR bar gating and CMD path tests.

### Patch 2

Target file:
- apps/reference/domains/decision_making/position_queries.py

Goal:
- Introduce an additive named result surface for sizing while keeping tuple compatibility temporarily.

Minimum validation:
- Add direct tests for both objective_engine.adapters and strategy_gateway consumers.

### Patch 3

Target files:
- apps/reference/domains/decision_making/position_queries.py
- apps/reference/domains/position_tracking/position_tracking.py
- config/aurora/domains.yaml

Goal:
- Resolve threshold ownership and encode it in one explicit contract.

Minimum validation:
- Add one focused test that demonstrates the intended flat-state threshold.

### Deferred, not immediate patches

- md_amr_handler.py should only receive new work here if a new failing regression test or runtime incident is produced.
- mean_reversion_logger.py should receive focused tests before any behavior change.

## 9. Final Audit Verdict

- The mean reversion duplicate-CMD / duplicate-bar gap is real enough to justify immediate localized correction in the handler.
- The PositionQueries issues are real but secondary.
- md_amr is not the next patch target in this scope.
- mean_reversion_logger is not the next patch target in this scope.

## 10. Next Practical Patch Recommendation

The next practical patch should be a minimal localized change in apps/reference/domains/decision_making/mean_reversion_handler.py that rejects or skips duplicate bar_close_ts per symbol before strategy.on_bar executes.

That patch should be accompanied by one narrow regression test proving handler-local idempotency on repeated identical CMD input.
