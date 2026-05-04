# AGENT_REPORT_V1

## Executive Summary

Phase 0 inventory is now established before any strategy code changes. The main finding is a scope contradiction: current SSOT does not match the stated live mean_reversion assumption. Under current YAML plus runtime handler logic, mean_reversion has no active assigned surface, while md_amr is active only for XRPUSDT. Recorder coverage is sufficient for offline 300-second mean_reversion and 900-second md_amr studies on relevant symbols, but the recorder is a bar-and-feature dataset, not an execution or portfolio truth source. Existing mean_reversion tooling is close to Phase 1-ready; md_amr tooling is reusable for weight and integrated validation, but not yet proven to cover the full requested aggression search surface.

## FACTS

- This file is the first repo edit for this task. No code, config, execution, risk, or arbitration files were changed before this inventory was created.
- YAML plus Pydantic are the contract SSOT in this repo, with strict extra-forbid validation and no sanctioned silent business-logic fallbacks.
- The global strategy assignment SSOT is config/aurora/strategies.yaml.
- Current registry assignments in config/aurora/strategies.yaml are:
  - BTCUSDT -> aurora
  - ETHUSDT -> aurora
  - SOLUSDT -> aurora
  - XRPUSDT -> aurora, md_amr
  - BNBUSDT -> aurora
  - 1000PEPEUSDT -> llm_microstructure
  - DOGEUSDT mean_reversion hybrid assignment exists only as commented-out config, not as active SSOT.
- Current arbitration SSOT is priority mode with window_ms=1000 and priority order aurora=1, mean_reversion=2, md_amr=3, llm_microstructure=4.
- The md_amr profile SSOT is config/aurora/strategies/md_amr.yaml. It sets timeframe_sec=900 and currently enables asset blocks for ETHUSDT, SOLUSDT, and XRPUSDT; BTCUSDT, DOGEUSDT, and BNBUSDT are disabled in that strategy-local config.
- The mean_reversion profile SSOT is config/aurora/strategies/mean_reversion.yaml. It sets timeframe_sec=300 and currently enables only DOGEUSDT. Other asset blocks are disabled.
- Runtime handlers derive the effective active symbol set as assigned symbols intersect enabled asset blocks:
  - apps/reference/domains/strategies/runtimes/md_amr/handler.py yields active md_amr surface = XRPUSDT only.
  - apps/reference/domains/strategies/runtimes/mean_reversion/handler.py yields active mean_reversion surface = empty.
- Decision-making arbitration is registry-based and fail-closed in apps/reference/domains/decision_making/core/config_resolver.py and apps/reference/domains/decision_making/gates/arbitration_gate.py.
- The sanctioned strategy bridge for DM-facing imports is apps/reference/domains/strategies/runtimes/bridge.py. Boundary enforcement is covered by tests/domains/decision_making/test_fe_dm_boundary_guardrails.py.
- Recorder data lives under data/recorder as per-day CSV snapshots. The inventory artifact shows:
  - 82 day directories
  - 1,566 CSV files
  - 445,991 total rows
  - symbols: 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT
  - tf_sec values: 180, 300, 900
- Recorder field presence is feature-rich and strategy-usable for offline admission studies:
  - ready, regime, regime_conf, spread_bps, liquidity_kappa, pm_norm are present
  - portfolio_any=false and exposure_any=false in the inventory artifact
  - this is not an order, fill, exposure, or portfolio event ledger
- Existing calibration and validation surfaces found:
  - tools/calibration/calibrate_mean_reversion_params.py
  - tools/forensics/mr_signal_surface_audit.py
  - tools/calibration/calibrate_md_amr_weights.py
  - tools/analysis/md_amr_integrated_validation.py
  - tools/forensics/full_surface_calibration.py

## INFERENCES

- The user-stated expectation of live mean_reversion activity likely reflects historical or operator memory, not current checked-in SSOT.
- The main ambiguity in this track is not calibration math yet; it is target-surface ambiguity caused by the split between global registry assignment and strategy-local profile enablement.
- The safest Phase 1 path is to reuse existing strategy-local tools first and prove their adequacy before creating any new harness.
- If the requested track must stay strictly strategy-only and must not change assignments, then any live-only baseline for mean_reversion is currently blocked because the active runtime surface is empty.
- If dormant profile-enabled assets are allowed for offline study, then DOGEUSDT mean_reversion and ETHUSDT/SOLUSDT md_amr can still be analyzed offline without changing live registry assignments.
- tools/forensics/full_surface_calibration.py is not a trustworthy SSOT-aligned foundation for this task because it contains hardcoded registry/config constants rather than reading current YAML contracts.

## ASSUMPTIONS

- No external deployment override is intentionally superseding config/aurora/strategies.yaml unless separate evidence is provided.
- Phase 1, if approved, may begin as offline recorder-driven analysis rather than execution-truth replay, because the recorder itself does not contain exposure or order lifecycle truth.
- The user constraint remains in force: no global policy tuning, no execution_position changes, no risk-management changes, and no decision_making gateway or arbitration loosening.

## UNKNOWNS

- Whether any external runtime deployment layer overrides the checked-in strategies registry.
- Whether the desired output of this track is strictly offline calibration evidence, YAML candidate patches, or live rollout-ready settings.
- Whether the user wants calibration against current live-assigned surfaces only, or also against profile-enabled but currently unassigned strategy surfaces.
- Which primary metric defines aggression success for this track: trade count lift, acceptance rate lift, forward PnL, drawdown-constrained return, win rate, expectancy, or another metric.
- Whether current md_amr tooling already spans the requested threshold and aggression dimensions, especially threshold_z, dampening, deformation, progress/setup/hold/context quality overlays, and exit-action interactions.

## Live Assignments

### Global Registry Truth

| Symbol | Assigned strategies in SSOT | Effective note |
| --- | --- | --- |
| BTCUSDT | aurora | Not in current Phase 0 strategy target set |
| ETHUSDT | aurora | md_amr profile-enabled only, not md_amr-assigned |
| SOLUSDT | aurora | md_amr profile-enabled only, not md_amr-assigned |
| XRPUSDT | aurora, md_amr | Only current active md_amr surface |
| BNBUSDT | aurora | Not md_amr-assigned; md_amr asset block disabled |
| DOGEUSDT | none active for mean_reversion | mean_reversion hybrid line is commented out |
| 1000PEPEUSDT | llm_microstructure | Out of scope for this track |

### Effective Runtime Consequence

- Active md_amr surface now: XRPUSDT only.
- Active mean_reversion surface now: none.
- Any statement that DOGEUSDT is currently live under mean_reversion is not supported by current SSOT.

## Available Recorder Data By Symbol / tf_sec / date

The table below uses the generated artifact artifacts/strategy_calibration/context_inventory_recorder.json. It is intentionally centered on the symbols relevant to this track plus nearby broader-surface symbols.

| Symbol | Strategy relevance | date_start | date_end | day_count | 180 rows | 300 rows | 900 rows | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| DOGEUSDT | mean_reversion profile-enabled, not assigned | 2026-03-05 | 2026-04-30 | 57 | 20,986 | 20,774 | 6,112 | 300-second surface exists for offline MR study; not live-assigned |
| XRPUSDT | md_amr assigned and enabled | 2026-02-08 | 2026-04-30 | 82 | 30,712 | 26,637 | 10,608 | Current live md_amr target |
| ETHUSDT | md_amr profile-enabled only | 2026-02-08 | 2026-04-30 | 82 | 30,714 | 37,346 | 6,231 | Offline md_amr candidate only under current SSOT |
| SOLUSDT | md_amr profile-enabled only | 2026-02-08 | 2026-04-30 | 82 | 30,714 | 37,459 | 6,231 | Offline md_amr candidate only under current SSOT |
| BNBUSDT | broader recorder surface, md_amr disabled in profile | 2026-03-05 | 2026-04-30 | 57 | 20,986 | 20,774 | 6,112 | Not current md_amr target |
| BTCUSDT | broader recorder surface | 2026-02-08 | 2026-04-30 | 82 | 30,715 | 38,343 | 6,231 | Out of current track unless scope widens |
| 1000PEPEUSDT | out-of-scope assigned to llm_microstructure | 2026-03-07 | 2026-04-30 | 55 | 20,543 | 12,336 | 4,121 | Included only to show recorder breadth |

Additional recorder facts:

- 180-second data exists, but the requested strategy track is centered on 300-second mean_reversion and 900-second md_amr.
- Warmup sufficiency is plausible for both strategy cores from the observed spans, but that is dataset sufficiency only, not execution-truth sufficiency.
- Recorder rows contain regime and feature fields needed for offline admission and signal-surface analysis.
- Recorder rows do not contain direct portfolio exposure or order execution truth, so portfolio-aware or execution-aware conclusions require additional joins or a different evidence source.

## Existing Calibrators Found

| Tool | Strategy | Current usefulness | Current limitation |
| --- | --- | --- | --- |
| tools/calibration/calibrate_mean_reversion_params.py | mean_reversion | Strong Phase 1 reuse candidate; already does recorder-driven train/validation/forward calibration and candidate overlay output | Must still be checked against this track's exact aggression metrics and reporting requirements |
| tools/forensics/mr_signal_surface_audit.py | mean_reversion | Strong report-only diagnostic surface; computes effective YAML config and neutral reason buckets | Audit-only; not itself a forward candidate selector |
| tools/calibration/calibrate_md_amr_weights.py | md_amr | Reusable for recorder-driven md_amr parameter study via runtime bridge | Appears focused on weights and related parameters, not yet proven to cover the full aggression search surface |
| tools/analysis/md_amr_integrated_validation.py | md_amr | Useful report-only validation arm for integrated comparisons | Not obviously a full search or candidate generation harness |
| tools/forensics/full_surface_calibration.py | mixed / stale | Low confidence; not recommended as-is | Hardcoded root paths, registry assumptions, and constants conflict with current SSOT and no-hidden-constants rules |

## Contradictions / Evidence Gaps

- User-stated live mean_reversion assumption contradicts current checked-in SSOT, where DOGEUSDT mean_reversion assignment is commented out and effective active MR runtime surface is empty.
- md_amr profile enablement covers ETHUSDT, SOLUSDT, and XRPUSDT, but current registry assignment only activates XRPUSDT.
- Recorder coverage is broad, but recorder semantics stop at bar-plus-feature-plus-regime state. That is an evidence gap for any conclusion that depends on execution outcomes, portfolio exposure, or slippage-sensitive lifecycle truth.
- No existing single tool found in this Phase 0 pass is already proven to search the entire requested md_amr aggression surface while staying strictly SSOT-driven.

## Root Cause Candidates

- Primary root cause candidate for scope ambiguity: current live-surface truth depends on the intersection of two separate SSOT layers, global registry assignment and strategy-local asset enablement.
- Secondary root cause candidate for future calibration drift: historical or manual tooling can look plausible while bypassing current YAML contracts, especially when hardcoded registry data is embedded in scripts.

## Missing Proof Surfaces

- Proof that any deployment environment overrides config/aurora/strategies.yaml.
- Proof that current offline tools emit the exact per-symbol, per-regime, and forward-window evidence required by this calibration track.
- Proof that current md_amr tools span all desired aggression knobs without new SSOT-aligned harness work.
- Proof that recorder-only analysis is sufficient for any objective function that depends on fills, exposure, or realized execution economics.
- Proof that mean_reversion should be treated as a live-target calibration problem under current registry truth.

## Immediate Blockers

- Mean_reversion live target ambiguity: current active surface is empty, so live-only MR calibration is blocked until the intended target surface is explicitly clarified.
- Assignment versus enablement mismatch: ETHUSDT and SOLUSDT are md_amr profile-enabled but not md_amr-assigned, so "current live md_amr" and "potential offline md_amr calibration set" are different scopes.
- Recorder semantic limit: there is no portfolio or exposure truth in the inventory artifact, so execution-aware conclusions cannot be claimed from recorder alone.
- Tooling adequacy gap: md_amr has reusable components, but no already-proven full-surface aggression search harness was confirmed in this Phase 0 pass.

## Operational Risk

- Runtime risk: medium if Phase 1 quietly assumes mean_reversion is live when SSOT says otherwise.
- Observability-gap risk: medium because recorder evidence can support signal-surface analysis but not full lifecycle truth.
- Correctness risk: medium if stale manual tooling is reused instead of current YAML-driven tools.
- Capital risk: deferred for now because no runtime or config mutation has been proposed in this Phase 0 report.

## Files / Areas Touched

- Created: STRATEGY_CALIBRATION_CONTEXT_INVENTORY.md
- Read-only evidence set included:
  - Copilot_Master_Roadmap.md
  - config/aurora/strategies.yaml
  - config/aurora/strategies/md_amr.yaml
  - config/aurora/strategies/mean_reversion.yaml
  - apps/reference/config_models.py
  - apps/reference/config/strategies/md_amr.py
  - apps/reference/config/strategies/mean_reversion.py
  - apps/reference/domains/strategies/runtimes/bridge.py
  - apps/reference/domains/strategies/runtimes/md_amr/handler.py
  - apps/reference/domains/strategies/runtimes/mean_reversion/handler.py
  - apps/reference/domains/feature_engineering/md_amr_strategy.py
  - apps/reference/domains/feature_engineering/mean_reversion_strategy.py
  - apps/reference/domains/decision_making/core/config_resolver.py
  - apps/reference/domains/decision_making/gateway/strategy_gateway.py
  - apps/reference/domains/decision_making/gates/arbitration_gate.py
  - tools/calibration/calibrate_mean_reversion_params.py
  - tools/calibration/calibrate_md_amr_weights.py
  - tools/analysis/md_amr_integrated_validation.py
  - tools/forensics/mr_signal_surface_audit.py
  - tools/forensics/full_surface_calibration.py
  - tests/domains/decision_making/test_fe_dm_boundary_guardrails.py
  - artifacts/strategy_calibration/context_inventory_recorder.json

## Validation Performed

- Verified SSOT assignment and arbitration truth by direct inspection of config/aurora/strategies.yaml.
- Verified strategy-local enablement truth by direct inspection of md_amr and mean_reversion YAML plus their strict Pydantic config models.
- Verified effective runtime activation logic by direct inspection of both runtime handlers.
- Verified DM bridge and guardrail boundary by direct inspection of tests/domains/decision_making/test_fe_dm_boundary_guardrails.py.
- Verified recorder surface using the generated inventory artifact artifacts/strategy_calibration/context_inventory_recorder.json.
- No unit tests or runtime commands were run for this report because no behavior-changing code was introduced.

## Residual Risk

- This inventory is repo-truth only. It does not prove external deployment state.
- This inventory proves data presence, not signal quality or economic viability.
- This inventory proves tool existence, not that every tool already satisfies the requested track without augmentation.

## What Remains Unproven

- Whether the desired Phase 1 scope is live-assigned-only or includes dormant strategy surfaces.
- Whether a strategy-only offline calibration output can later be promoted without assignment clarification.
- Whether existing md_amr tools alone are enough for the requested aggression search dimensions.
- Whether any additional execution-truth dataset is available for post-recorder validation.

## Minimal Safe Verdict

Phase 0 is complete enough to proceed, but only with explicit scope discipline. The minimal safe next step is an offline-only adequacy check of the existing strategy-local tools, split by actual SSOT surface:

- md_amr live-surface baseline: XRPUSDT only.
- mean_reversion live-surface baseline: blocked under current SSOT because no symbol is actively assigned.
- optional offline dormant-surface studies: DOGEUSDT for mean_reversion, ETHUSDT and SOLUSDT for md_amr, but only if everyone agrees those are profile-enabled offline studies rather than current live targets.

No assignment, arbitration, execution, or risk mutations should be inferred from this report.