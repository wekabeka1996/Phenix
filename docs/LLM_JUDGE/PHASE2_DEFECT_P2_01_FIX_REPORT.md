# DEFECT-P2-01 Fix Report

**Date**: 2026-04-15
**Package**: DEFECT-P2-01 — Judge Expert Provider Shadow Path
**Authority**: `docs/LLM_JUDGE/LLM_JUDGE_PHASE1_PHASE2_CODE_AUDIT.md`

---

## 1. Executive Verdict

**DONE**

All stated requirements met. Judge expert providers now emit `EVT:JUDGE_EXPERT_PRODUCED_V1` via the bridge, write JSONL shadow logs, and do NOT emit `EVT:ALPHA_SCORE_CALCULATED`. Non-judge providers are unchanged. 268 alpha_search tests pass, 234 judge tests pass, 0 failures.

---

## 2. Scope Implemented

Bounded corrective package limited to:
- `apps/reference/domains/alpha_search/backtest_plugin.py` — routing fix
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py` — new integration test file

No changes to:
- main.py, config_loader.py, root config_models.py
- decision_making, execution_position, quadratic_scoring_kernel
- Expert modules (Layer 1 scoring unchanged)
- Judge contracts, config models, verb registry
- No new verbs, no new config surfaces, no new files beyond test

---

## 3. Root Cause

**Cause**: Phase 2 (Package 2C) integrated judge experts into the provider factory (`_create_judge_expert`) but did not differentiate judge experts from other providers in the scoring execution path.

**Mechanism**: `_process_score()` called `_emit_score_event()` unconditionally for all providers. `_emit_score_event()` emits `EVT:ALPHA_SCORE_CALCULATED`. Similarly, `_emit_fail_closed_score()` emitted `EVT:ALPHA_SCORE_CALCULATED` for all providers on cache miss or feature miss.

**Effect**: Judge expert outputs flowed through the generic alpha_score event stream. The bridge (`alpha_score_to_expert_output`), the `EVT:JUDGE_EXPERT_PRODUCED_V1` verb, and JSONL shadow logging were never invoked from the real provider execution path.

---

## 4. FACTS

1. `_process_score()` (backtest_plugin.py:862) is the single site where provider scores are dispatched to events.
2. `_emit_score_event()` (backtest_plugin.py:920) emits `self.config.triggers.emit_event` which is `EVT:ALPHA_SCORE_CALCULATED`.
3. `_emit_fail_closed_score()` (backtest_plugin.py:1027) emits the same event for fail-closed scenarios.
4. `ProviderConfig.judge_expert` (config_models.py:173) is `Optional[JudgeExpertProviderConfig]`, non-None only for judge providers.
5. The bridge `alpha_score_to_expert_output()` and `write_jsonl_shadow_log()` existed in `expert_output_bridge.py` since Phase 2 but were never called from the provider path.
6. The `EVT:JUDGE_EXPERT_PRODUCED_V1` verb was registered in Phase 2 but never emitted by the plugin.

---

## 5. INFERENCES

1. The discriminator `cfg.judge_expert is not None` is the narrowest correct mechanism — it uses an existing config attribute with no new fields needed.
2. Judge expert fail-closed events should be suppressed entirely (not routed through bridge) because a fail-closed score=0 carries no expert semantic value worth logging.
3. The fix preserves Layer 1/Layer 2 separation: expert modules remain pure scoring, bridge/emission/logging remain in the plugin orchestration path.

---

## 6. ASSUMPTIONS

1. Judge experts in fail-closed state (cache miss, feature miss) should produce no event at all, rather than a zero-score `EVT:JUDGE_EXPERT_PRODUCED_V1`. This matches the shadow-only semantics.
2. Virtual trader logic for judge expert providers can continue to run (it's harmless in shadow mode and tracks virtual PnL independently).
3. No other file outside `alpha_search` calls `_process_score` or `_emit_score_event` — these are internal methods.

---

## 7. UNKNOWNS

1. Whether operator dashboards currently consume `EVT:ALPHA_SCORE_CALCULATED` and filter by provider_id for judge experts. If so, those filters would now see no judge events (correct behavior — they should watch `EVT:JUDGE_EXPERT_PRODUCED_V1` instead).
2. Whether the judge expert virtual trader PnL tracking has downstream consumers that expect the old event format. Unlikely given shadow mode.

---

## 8. Files Added

| File | Purpose |
|------|---------|
| `tests/domains/alpha_search/judge/test_expert_provider_integration.py` | 12 integration tests proving the fix end-to-end |

---

## 9. Files Modified

| File | Change |
|------|--------|
| `apps/reference/domains/alpha_search/backtest_plugin.py` | 3 changes (see Section 10) |

---

## 10. Exact Fix Description

### Change 1: Import bridge utilities (line 26)
Added import of `alpha_score_to_expert_output` and `write_jsonl_shadow_log` from `judge.experts.expert_output_bridge`.

### Change 2: Route judge experts in `_process_score()` (line 877)
Replaced unconditional `_emit_score_event()` call with a branch:
```python
cfg = self.provider_configs[provider_id]
if cfg.judge_expert is not None:
    self._process_judge_expert_score(...)
else:
    self._emit_score_event(...)
```

### Change 3: New method `_process_judge_expert_score()` (after line 957)
Layer 2 integration method that:
1. Resolves `expert_version` from judge expert config
2. Calls `alpha_score_to_expert_output()` to translate AlphaScore → ExpertOutput
3. Emits `EVT:JUDGE_EXPERT_PRODUCED_V1` with ExpertOutput payload
4. Writes JSONL shadow log via `write_jsonl_shadow_log()` when `judge.shadow_log.enabled` is true
5. Does NOT emit `EVT:ALPHA_SCORE_CALCULATED`

### Change 4: Suppress fail-closed for judge experts in `_emit_fail_closed_score()` (line 1027)
Added early return when `cfg.judge_expert is not None` — judge experts in fail-closed state produce no event (silent suppression with debug log).

---

## 11. Validation Evidence

### Test Commands
```
python -m pytest tests/domains/alpha_search/judge/test_expert_provider_integration.py -v
python -m pytest tests/domains/alpha_search/judge/ -v
python -m pytest tests/domains/alpha_search/ -v
```

### Pass/Fail Results
- New integration tests: **12 passed, 0 failed**
- All judge tests: **234 passed, 0 failed**
- All alpha_search tests: **268 passed, 0 failed**

### Proof: JUDGE_EXPERT_PRODUCED_V1 Is Emitted
`TestJudgeExpertEmitsCorrectEvent::test_signal_weights_emits_judge_event` — asserts exactly 1 event with name `EVT:JUDGE_EXPERT_PRODUCED_V1` and correct `expert_id`, `symbol`, `schema_version`.
`TestJudgeExpertEmitsCorrectEvent::test_feature_neutrals_emits_judge_event` — same for feature_neutrals expert.

### Proof: ALPHA_SCORE_CALCULATED Is Suppressed for Judge Experts
`TestJudgeExpertSuppressesAlphaScore::test_signal_weights_no_alpha_score_event` — asserts 0 events with name `EVT:ALPHA_SCORE_CALCULATED`.
`TestJudgeExpertSuppressesAlphaScore::test_feature_neutrals_no_alpha_score_event` — same.

### Proof: JSONL Logging Works
`TestJSONLShadowLog::test_jsonl_log_written_when_enabled` — verifies JSONL file created with valid ExpertOutput record.
`TestJSONLShadowLog::test_jsonl_log_not_written_when_disabled` — verifies no JSONL when `shadow_log.enabled=False`.
`TestJSONLShadowLog::test_jsonl_log_multiple_symbols` — verifies per-symbol JSONL files.

### Proof: Non-Judge Providers Unchanged
`TestNonJudgeProviderUnchanged::test_non_judge_provider_emits_alpha_score_calculated` — non-judge provider still emits `EVT:ALPHA_SCORE_CALCULATED`, no `EVT:JUDGE_EXPERT_PRODUCED_V1`.

### Proof: Mixed Providers Coexist
`TestMixedProviders::test_mixed_judge_and_nonjudge` — judge emits judge event, non-judge emits alpha event, no cross-contamination.

### Proof: Bridge Produces Valid ExpertOutput
`TestBridgeProducesValidExpertOutput::test_judge_event_payload_is_valid_expert_output` — payload deserializes to valid `ExpertOutput` Pydantic model.

---

## 12. Regression Evidence

- `tests/domains/alpha_search/test_backtest_plugin.py` — all existing plugin tests pass (scoring, caching, virtual trader, multi-provider, fail-closed, summary)
- `tests/domains/alpha_search/test_objective_feedback.py` — objective feedback path unchanged
- `tests/domains/alpha_search/test_aurora_adapter.py` — Aurora adapter unaffected
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py` — 9 tests confirming Aurora/ensemble providers have no judge_expert config

Total: **268 alpha_search tests, 0 regressions.**

---

## 13. Explicit Proof That Live Aurora Path Was Not Changed

1. `test_aurora_adapter_still_works` — Aurora provider config unchanged, `judge_expert is None`.
2. `test_ta_ensemble_still_works` — TA ensemble provider config unchanged, `judge_expert is None`.
3. `test_existing_providers_no_judge_expert` — all real config providers have `judge_expert is None`.
4. The routing branch in `_process_score()` only activates when `cfg.judge_expert is not None` — for Aurora/ensemble providers this is always False, so the existing `_emit_score_event()` path executes unchanged.
5. No changes to `quadratic_scoring_kernel.py`, `aurora_decision.py`, `aurora_handler.py`, or any decision_making/execution_position file.

---

## 14. Whether Phase 2 Note Can Now Be Cleared

**Yes.** The audit finding (DEFECT-P2-01) that judge expert outputs flow through the wrong event path is now closed. The complete Phase 2 shadow path is functional:
- Expert scoring (Layer 1): unchanged, pure
- Bridge translation (Layer 2): now called from real provider path
- Event emission: `EVT:JUDGE_EXPERT_PRODUCED_V1` emitted, `EVT:ALPHA_SCORE_CALCULATED` suppressed
- JSONL logging: written from real provider path when enabled

Phase 2 can be considered code-complete with this correction applied.
