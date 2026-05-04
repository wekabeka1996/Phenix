# MD_AMR Package C.4 Report

## 1. Current Overlay Surface

- FACT: C.1 already provides anchored progress fields in in-position trace: progress_pct, progress_state, entry_price, entry_target_price.
- FACT: C.2 already provides entry-only setup_quality and its bounded sub-scores.
- FACT: C.3 already provides hold-quality overlays: expected_progress_pct, progress_deficit, time_decay, structural_hold_quality, hold_quality_penalty, hold_quality.
- FACT: current runtime evidence remains active for md_amr on XRPUSDT and BNBUSDT per reports/RUNTIME_21H_FORENSIC_CONTEXT_REPORT.md.
- FACT: md_amr handler already owns regime cache and regime confidence cache, while strategy core already owns local ATR, channel, directional, progress, and hold-quality math.
- INFERENCE: the narrowest safe owner for C.4 is strategy-local trace math with handler pass-through of already-owned regime context.
- UNKNOWN: config/docs/MD_AMR_PACKAGE_C1_REPORT.md is still not present in the repo.
- UNKNOWN: config/docs/MD_AMR_PACKAGE_C2_REPORT.md is still not present in the repo.

## 2. C.4 Design

- FACT: C.4 is implemented as an in-position, additive, advisory-only overlay.
- FACT: C.4 does not alter resolve_exit_action(), close ownership, order state, or handler lifecycle truth.
- FACT: context_validity is computed only when md_amr is already in position and strategy trace already has local bar/channel/ATR/directional context.
- FACT: C.4 uses four explainable components:
  - regime_validity_component: derived from handler-owned regime allowlist compatibility plus regime confidence.
  - volatility_validity_component: derived from strategy-local ATR z-score.
  - structure_validity_component: derived from thesis-side directional coherence plus channel sanity.
  - progress_alignment_component: derived from existing C.3 hold_quality and progress_deficit.
- FACT: if critical regime or anchored-progress inputs are missing, C.4 fails closed to context_validity_state = UNKNOWN and emits explicit missing field names.
- FACT: INVALID is emitted immediately when current regime context is explicitly incompatible with the md_amr allowlist.
- INFERENCE: this keeps C.4 lightweight and locally explainable while avoiding duplication of the regime detector or promotion into a second strategy brain.

## 3. Fields Added

- trace.context_regime
- trace.context_regime_confidence
- trace.context_regime_allowed
- trace.regime_validity_component
- trace.volatility_validity_component
- trace.context_directional_coherence
- trace.context_channel_sanity
- trace.structure_validity_component
- trace.progress_alignment_component
- trace.context_validity
- trace.context_validity_state
- trace.context_penalty_reason
- trace.context_validity_missing_fields

## 4. Config Surface

- YAML SSOT: config/aurora/strategies/md_amr.yaml now contains a required context_validity block.
- Pydantic SSOT: apps/reference/config_models.py now defines MDAMRContextValidityConfig with extra='forbid'.
- Contract guards enforced:
  - regime_confidence_valid > regime_confidence_floor
  - volatility_z_invalid > volatility_z_weakening
  - channel_width_pct_valid > channel_width_pct_floor
  - component weights sum exactly to 1.0
  - valid_score_min > invalid_score_max
- FACT: no runtime silent fallback was added for C.4. Handler and tests pass the block explicitly.

## 5. Files Changed

- apps/reference/config_models.py
- apps/reference/domains/feature_engineering/md_amr_strategy.py
- apps/reference/domains/decision_making/md_amr_handler.py
- config/aurora/strategies/md_amr.yaml
- tests/config/test_md_amr_package_c4_config_contract.py
- tests/domains/feature_engineering/test_md_amr_package_c4_context_validity.py
- tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py
- reports/MD_AMR_PACKAGE_C4_VALIDATION_CASES.md
- plus direct md_amr strategy/handler test stubs updated to include the explicit C.4 contract block

## 6. Validation Evidence

- Contract validation target:
  - tests/config/test_md_amr_package_c4_config_contract.py
- Behavior validation target:
  - tests/domains/feature_engineering/test_md_amr_package_c4_context_validity.py
- Handler compatibility target:
  - tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py
- Regression target set:
  - Package A/B/C.1/C.2/C.3 suites plus md_amr handler readiness/observability/tf_sec suites
- Evidence artifact:
  - reports/MD_AMR_PACKAGE_C4_VALIDATION_CASES.md
- Focused command result:
  - pytest tests/config/test_md_amr_package_c4_config_contract.py tests/domains/feature_engineering/test_md_amr_package_c4_context_validity.py tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py -q
  - RESULT: 13 passed in 0.77s
- Regression command result:
  - pytest tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py tests/domains/feature_engineering/test_md_amr_package_b_hold_calibration.py tests/domains/feature_engineering/test_md_amr_package_c1_progress.py tests/domains/feature_engineering/test_md_amr_package_c2_setup_quality.py tests/domains/feature_engineering/test_md_amr_package_c3_hold_quality.py tests/domains/feature_engineering/test_md_amr_package_c4_context_validity.py tests/domains/decision_making/test_md_amr_runtime_readiness.py tests/domains/decision_making/test_md_amr_silence_observability.py tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py tests/domains/decision_making/test_md_amr_package_c4_handler_contract.py tests/config/test_md_amr_package_c3_config_contract.py tests/config/test_md_amr_package_c4_config_contract.py tests/domains/decision_making/test_md_amr_tf_sec_guard.py -q
  - RESULT: 95 passed in 3.10s
- Deterministic helper separation captured in reports/MD_AMR_PACKAGE_C4_VALIDATION_CASES.md:
  - healthy context_validity = 0.9550
  - degraded context_validity = 0.4460
  - invalid state forced by regime incompatibility while remaining advisory-only
  - unknown state exposes explicit missing fields

## 7. What Is Proven

- FACT: a bounded context_validity overlay now exists in md_amr strategy math.
- FACT: VALID, WEAKENING, INVALID, and UNKNOWN are deterministic and explicit.
- FACT: missing critical context produces UNKNOWN instead of silent inferred validity.
- FACT: handler ownership remains intact; handler only passes regime context it already owns.
- FACT: C.4 is trace-visible and replay-testable at helper and on_bar level.
- FACT: Package C.4 does not modify exit ownership or promote itself into hard close behavior.

## 8. What Remains Unproven

- UNKNOWN: no full historical economic replay or matched-cohort study has been executed in this package patch.
- UNKNOWN: no live/testnet post-patch runtime capture has been collected yet.
- UNKNOWN: whether future Package C integration should consume context_validity as an attenuator, veto, or remain observability-only beyond this boundary.

## 9. Operational Risks

- If C.4 is promoted into exit or sizing control without broader replay evidence, valid late mean reversions could be penalized too aggressively.
- Regime incompatibility is now explicit in trace, but it is still advisory only; operators must not infer that C.4 already enforces closes.
- UNKNOWN state will surface whenever regime heartbeat/confidence or anchor-driven hold overlays are absent; downstream consumers must treat UNKNOWN as lack of proof, not as implicit validity.

## 10. Final Verdict

Package C.4 is complete at the package boundary.

The repo now has a strict, md_amr-scoped, additive-only context-validity overlay that stays inside strategy-local math, consumes only already-owned local or handler-owned evidence, remains replay-testable and explainable, and does not alter execution truth or hard exit semantics.
