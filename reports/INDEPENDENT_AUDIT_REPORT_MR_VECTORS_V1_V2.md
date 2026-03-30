# INDEPENDENT AUDIT REPORT: MR Vectors V1 and V2

## 1. Executive Verdict

### Short answer to the three mandatory questions

1. Did the code really change as claimed?
   - Yes. Actual repository files contain real V1 and V2 code on disk, not only narrative reports.
   - However, proof quality is mixed: some surfaces are committed branch history, while several remediation reports and one V2 behavioral test file were present only as working-tree artifacts at audit time.

2. If yes, was the intended logic implemented correctly?
   - Partially.
   - Vector 2 threshold modulation is mostly implemented correctly.
   - Vector 1 fail-closed behavior is implemented, but the intended flow x price-reaction runtime contract is not fully wired to the actual MR command payload.

3. Is the implementation architecturally safe and mathematically coherent?
   - Mixed.
   - Vector 2 is mathematically coherent and structurally reasonable.
   - Vector 1 is safety-biased and fail-closed, but not fully contract-faithful because the handler expects nested `features.price_motion` while the actual FE -> CMD path emits `price_motion` outside `features`.

### Executive verdict

The implementation is real, not fabricated. Vector 2 is mostly sound. Vector 1 is only partially correct at runtime because one of its key inputs is not wired the way the handler expects.

Final verdict: **ACCEPT WITH CRITICAL GAPS**.

Operational interpretation:
- Acceptable as dormant code already kept disabled.
- Not trustworthy for enablement until the runtime input contract and evidence gaps are closed.

## 2. FACTS

1. `MRMicrostructureVetoConfig` exists in `apps/reference/config_models.py` as a strict Pydantic model with `extra='forbid'`.
2. `MRDirectionalBiasConfig` exists in `apps/reference/config_models.py` as a strict Pydantic model with `extra='forbid'`.
3. `missing_policy` is now `Literal["block"]`; the fail-open `"skip"` path is not allowed by the active config model.
4. `MeanReversionHandler` contains `_check_microstructure_veto()` and `_apply_directional_bias()` and wires them in `_on_process_strategy()`.
5. The V1 overlay executes after `strategy.on_bar()` returns an actionable signal and before downstream signal emission.
6. `MeanReversion1mStrategy._evaluate_signal()` uses split long/short thresholds when transient overrides are present.
7. FE computes base `obi` and `tfi` into the `features` dictionary.
8. FE computes `price_motion`, but emits it as a top-level event block in `EVT:FEATURES_CALCULATED`, not as `features["price_motion"]` in `CMD:PROCESS_STRATEGY`.
9. `MeanReversionHandler._check_microstructure_veto()` reads `features.get("price_motion", {})` from cached CMD features.
10. `MeanReversionHandler.register()` does not register `EVT:FEATURES_CALCULATED`, even though its docstring says such listeners are kept for data caching.
11. `MeanReversionHandler` has a stale `_on_features_calculated()` method, but it is not registered, and it writes to `self.features[...]`, which is not initialized anywhere else in the class.
12. FE can populate `funding_rate`, but only when feature-engineering futures support is enabled.
13. Current `config/aurora/domains.yaml` contains a `feature_engineering` block but no `futures` sub-block, so the default `futures_enabled` accessor resolves to false.
14. Therefore, under the current repository config defaults, V2 dynamic funding modulation is likely to degrade to static split thresholds even if the V2 overlay itself is enabled.
15. Current `config/aurora/strategies.yaml` does not assign `mean_reversion` to any symbol.
16. Current `config/aurora/strategies/mean_reversion.yaml` keeps both `microstructure_veto.enabled` and `directional_bias.enabled` set to false.
17. Targeted pytest execution of the four MR test files collected 66 tests and all 66 passed.
18. Focused coverage from those same tests was only 20% for `mean_reversion_handler.py` and 49% for `mean_reversion_strategy.py`.
19. Multiple reports are stale relative to current code and tests.
20. `NormalizedRejectReasons` includes `MICROSTRUCTURE_VETO = "NRR-060"`.

## 3. INFERENCES

1. V1 currently behaves more safely than permissively, but also more bluntly than intended.
2. Because `price_motion` is not wired into MR's cached CMD features, the runtime V1 logic cannot fully use the intended adverse-continuation vs rebound branching except through wick geometry.
3. In the common runtime case where nested `features.price_motion` is absent, adverse flow with no wick absorption falls into the ambiguous fail-closed block path.
4. V2's mathematical signs are correct in code, even though some prose surfaces remain inverted.
5. The V2 implementation is structurally isolated enough for dormant use because each symbol gets its own strategy instance.
6. The test suite is materially better for config contracts than for active runtime integration.
7. The report pack set should not be treated as a single trustworthy narrative because several packs contradict current source truth.

## 4. ASSUMPTIONS

1. The earlier local branch-status snapshot gathered before the user disallowed further git usage still reflects the audit-time repository state.
2. No hidden runtime adapter outside the searched repository paths rewrites MR `CMD:PROCESS_STRATEGY` payloads to inject nested `features.price_motion` before they reach `MeanReversionHandler`.
3. Current `config/aurora` YAMLs are the intended runtime defaults for this workspace.

## 5. UNKNOWNS

1. Whether some external, non-repository runtime bridge injects nested `features.price_motion` for MR in production.
2. Whether operators plan to add a `feature_engineering.futures` config block before any V2 rollout.
3. Whether the stale `_on_features_calculated()` method was meant to be reconnected later or is simply dead code.
4. Whether the strategy will ever be reassigned in `strategies.yaml` without first fixing the V1 runtime payload mismatch.

## 6. Repository Truth / Diff Proof

### File-system proof

The following target surfaces exist on disk and contain the claimed V1/V2 additions:

- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/docs/mean_reversion_state_machine_passport.md`
- `tests/config/test_mr_microstructure_veto_config.py`
- `tests/domains/decision_making/test_mr_microstructure_veto.py`
- `tests/config/test_mr_directional_bias_config.py`
- `tests/domains/decision_making/test_mr_directional_bias.py`

### Earlier branch-status snapshot already collected before git was disallowed

Earlier local evidence showed:

- Modified working-tree surfaces included the core code files, YAML, passport, and V1 test files.
- Untracked working-tree surfaces included `REPORT_IMPLEMENTED_MR_VECTORS_V1_V2.md`, `REPORT_PACK_5/6/7`, `REPORT_PACK_R1/R2/R3/R4`, and `tests/domains/decision_making/test_mr_directional_bias.py`.
- A prior branch-vs-main snapshot already showed committed branch proof for:
  - modified: `config_models.py`, `mean_reversion_handler.py`, `mean_reversion_strategy.py`, `mean_reversion.yaml`, passport
  - added: `REPORT_PACK_1`, `REPORT_PACK_2`, `REPORT_PACK_3`, `REPORT_PACK_4`, `test_mr_directional_bias_config.py`, `test_mr_microstructure_veto_config.py`, `test_mr_microstructure_veto.py`

### What this means

1. The implementation is not merely claimed. It exists in source files.
2. Proof strength is uneven across surfaces:
   - core implementation files: strong file-state proof, plus earlier branch snapshot proof
   - later remediation reports and `test_mr_directional_bias.py`: file-state proof existed, but those surfaces were only working-tree evidence at audit time

### Trusted report claims

These claims are supported by current source truth:

1. V1 and V2 config models exist.
2. V1 and V2 YAML blocks exist.
3. The MR handler contains V1 and V2 overlay methods.
4. `NRR-060` exists.
5. The V2 implementation uses the simplified symmetric contract.
6. `missing_policy="skip"` is removed from the active runtime contract.

### Untrusted or downgraded report claims

1. `REPORT_PACK_1` still describes `missing_policy` as `Literal["block","skip"]` and assumes price reaction is available in CMD payload. That is stale.
2. `REPORT_PACK_3` still cites the removed `test_missing_tfi_allows_when_policy_skip` and still reports 15 tests. That is stale.
3. `REPORT_PACK_4` inverts V2 trigger semantics for positive and negative funding. That is wrong.
4. `REPORT_PACK_5` says FE likely does not populate `funding_rate`. The code can populate it, but current config defaults disable futures features, so the report is incomplete and misleading.
5. `REPORT_PACK_6` still reports 13 tests and repeats inverted easier/stricter semantics. That is stale.
6. `REPORT_PACK_R3` says try/finally cleanup is proven by tests; the current test only simulates cleanup and does not exercise the actual finally block.
7. `REPORT_PACK_R4` says parity is complete; current code/report/doc parity is not complete because `config_models.py` still carries inverted V2 prose and older packs remain stale.

## 7. Vector 1 Audit

### Contract existence and strictness

V1 contract existence is proven.

- `MRMicrostructureVetoConfig` exists.
- It is strict (`extra='forbid'`).
- It is wired globally and per-asset.
- YAML contains the block and keeps it disabled by default.

### Actual handler placement

The overlay is placed correctly in the handler sequence:

1. `strategy.on_bar()` runs first.
2. If `signal.is_signal` is true, the handler computes side and calls `_check_microstructure_veto()`.
3. If veto blocks, the handler writes `write_trade_intent_rejected()` and emits strategy-blocked telemetry.
4. Only after veto passes does the handler proceed toward downstream gating and emission.

This matches the architectural intent of a handler overlay rather than a strategy-core rewrite.

### Exact V1 logic actually implemented

1. Required primary flow metric is `tfi`, not `tsi`.
2. TFI is smoothed handler-side with EMA.
3. For LONG, adverse flow means `smoothed_tfi < -tfi_adverse_threshold`.
4. For SHORT, adverse flow means `smoothed_tfi > tfi_adverse_threshold`.
5. OBI is confirm-only in code: when confirm is enabled and OBI is not adverse, the method returns allow immediately.
6. Missing TFI blocks.
7. Invalid TFI blocks.
8. Missing or invalid OBI blocks only when OBI confirmation is enabled.
9. Zero-range bars block.
10. Warmup blocks until `readiness_min_bars` is reached.

### Core V1 problem: runtime payload mismatch

The intended contract says V1 uses flow x price reaction. The active implementation expects `features["price_motion"]` inside cached `CMD:PROCESS_STRATEGY` features. But FE currently:

- emits `price_motion` at top level in `EVT:FEATURES_CALCULATED`
- does not put `price_motion` inside `cmd_payload["features"]`
- does not register MR to listen for `EVT:FEATURES_CALCULATED`

Therefore the actual runtime V1 path is weaker than claimed:

1. `tfi` and `obi` can arrive.
2. nested `features.price_motion` is not proven to arrive for MR.
3. `recent_ret` therefore tends to remain `None`.
4. Without rebound/continuation return data, the algorithm falls back to wick geometry plus ambiguous fail-closed blocking.

### Answer to the mandatory V1 questions

- Does `MRMicrostructureVetoConfig` exist? Yes.
- Is it strict? Yes.
- Is Vector 1 implemented as an overlay after actionable signal and before emission? Yes.
- Does it use TFI/TFI-EMA and optional OBI confirm-only semantics? Yes.
- Does it distinguish toxic flow from absorption in code? Partially yes, but full runtime distinction depends on unavailable nested `features.price_motion`.
- Is OBI confirm-only in actual code? Yes.
- Is missing required microstructure input strict fail-closed? Yes for TFI, and for OBI when confirm is enabled.
- Was permissive skip removed fully? Yes in the active contract.

### V1 conclusion

Vector 1 exists and is fail-closed, but the actual runtime implementation is not fully faithful to the intended bivariate contract because one of the key price-reaction inputs is not wired to the handler's expected payload shape.

## 8. Vector 2 Audit

### Contract existence and strictness

V2 contract existence is proven.

- `MRDirectionalBiasConfig` exists.
- It is strict (`extra='forbid'`).
- Split thresholds `base_long_threshold` and `base_short_threshold` are implemented.
- Global and per-asset wiring exist.
- YAML block exists and is disabled by default.

### Actual implementation

V2 is implemented as handler-side preprocessing plus strategy-side threshold consumption:

1. Handler reads `funding_rate` from cached CMD features.
2. Handler computes normalized funding with clamp and deadband.
3. Handler computes effective long/short thresholds.
4. Handler writes transient overrides into `strategy.config.entry_threshold_long/short`.
5. Strategy consumes those thresholds in `_evaluate_signal()`.
6. Handler clears the overrides in a `finally` block after `on_bar()`.

### Graceful degradation

When `funding_rate` is missing or invalid, the code sets static split thresholds from `base_long_threshold` and `base_short_threshold`. It does not fail-closed.

That part of the contract is implemented correctly.

### Current runtime boundary

The code path for `funding_rate` exists in FE, but current config defaults do not expose a `feature_engineering.futures` block, and the feature-engineering config accessor returns false if futures config is absent. That means:

- the implementation supports `funding_rate`
- the current repo default profile likely does not emit it
- V2 would therefore behave as static split thresholds under the current config unless feature-engineering futures support is explicitly enabled

### Mandatory V2 answers

- Does `MRDirectionalBiasConfig` exist? Yes.
- Is it strict? Yes.
- Are split thresholds actually implemented? Yes.
- Is missing funding gracefully degraded to static thresholds? Yes.
- Is the implemented contract the simplified ratified contract? Yes.
- Is there drift between code, YAML, docs, and tests? Yes. Code/YAML/passport are close; older reports and `config_models.py` prose are not.

### V2 conclusion

Vector 2 logic is mostly correct. The major risks are not formula sign errors anymore, but config/docs/test overclaiming and the fact that current repo defaults likely suppress dynamic funding input.

## 9. Mathematical Semantics Audit

### Vector 1

The implemented math is coherent as a heuristic overlay:

- adverse flow is directional and side-aware
- absorption can be proven by wick geometry or favorable return
- adverse continuation can be proven by return direction
- ambiguous cases block conservatively

But mathematical coherence is not the same as contract completeness. Because nested `features.price_motion` is not wired into MR CMD features, the intended continuation-vs-rebound discrimination is not fully available at runtime.

### Vector 2

The exact implementation is:

```
norm_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
if abs(norm_funding) < funding_deadband:
    norm_funding = 0

eff_long = clamp(base_long_threshold - norm_funding * funding_shift_magnitude,
                 threshold_clamp_min, threshold_clamp_max)
eff_short = clamp(base_short_threshold + norm_funding * funding_shift_magnitude,
                  threshold_clamp_min, threshold_clamp_max)
```

Trigger topology in strategy code is:

```
LONG  fires when pct_b < long_threshold
SHORT fires when pct_b > (1 - short_threshold)
```

Therefore:

- positive funding lowers `eff_long` -> LONG becomes harder
- positive funding raises `eff_short` -> SHORT boundary drops -> SHORT becomes easier
- negative funding does the reverse

That is mathematically coherent for crowd-fade logic.

### Semantic drift

The code formula is correct, but multiple prose surfaces still lag:

1. `config_models.py` still says positive funding makes SHORT stricter and LONG easier.
2. `REPORT_PACK_4` says the same inverted thing.
3. `REPORT_PACK_6` still describes `+1` funding as `eff_long=0.08 (easier), eff_short=0.12 (stricter)`.
4. The passport and current V2 tests describe the geometry correctly.

## 10. Immutability / Cross-Symbol Isolation Audit

### What is proven in code

1. `MeanReversionHandler` stores strategies in `self._strategies: Dict[str, MeanReversion1mStrategy]`.
2. `_init_strategies()` constructs a fresh `MRStrategyConfig()` per enabled symbol.
3. `_on_process_strategy()` resolves the strategy by symbol, applies directional bias to that symbol's strategy instance, calls `on_bar()`, and then clears the overrides in `finally`.

That is real structural evidence for per-symbol isolation.

### What is not fully proven by tests

1. The cross-symbol tests call `_apply_directional_bias()` on separate handcrafted strategy objects rather than driving the real handler `_strategies` map through `_on_process_strategy()`.
2. The cleanup test manually clears overrides after simulating `on_bar()`; it does not prove the actual finally block executes on exception.

### Isolation verdict

Architecturally, cross-symbol contamination risk appears low because the symbol-to-strategy boundary is real in source code. Test proof is weaker than the reports claim, but the code structure itself is favorable.

## 11. Test Quality Audit

### What the tests do prove well

1. Pydantic config strictness and validators for both vectors.
2. Helper-level branch behavior inside `_check_microstructure_veto()`.
3. Helper-level threshold math inside `_apply_directional_bias()`.

### What the tests do not prove well

1. Actual MR runtime payload compatibility for V1.
2. End-to-end ordering inside `_on_process_strategy()`.
3. Real try/finally cleanup execution in the V2 call site.
4. True signal-boundary behavior through full strategy signal generation for the split-threshold tests named `test_split_thresholds_affect_long_signal` and `test_split_thresholds_affect_short_signal`.
5. Runtime integration between FE event shape and MR handler expectations.

### Coverage evidence

Targeted coverage from the 66 passing tests was:

- `mean_reversion_handler.py`: 20%
- `mean_reversion_strategy.py`: 49%

That is materially too low to treat the current passing suite as full proof of runtime correctness.

## 12. Code/Docs/YAML Parity Audit

### Good parity

1. Code, YAML, and passport agree that both overlays exist and are disabled by default.
2. Code, YAML, and tests agree that `missing_policy` is effectively block-only now.
3. Code and current passport agree on the corrected V2 trigger geometry.

### Bad parity

1. `config_models.py` still contains inverted V2 semantic prose.
2. `REPORT_PACK_1` still shows the old `missing_policy` contract and overstates CMD payload availability for price-motion data.
3. `REPORT_PACK_3` still references a removed skip test and stale test count.
4. `REPORT_PACK_4` still inverts V2 easier/harder semantics.
5. `REPORT_PACK_6` still uses stale test count and stale V2 easier/harder prose.
6. `REPORT_PACK_R4` claims parity is complete; that is not true.
7. `MeanReversionHandler.register()` docstring says `EVT:FEATURES_CALCULATED` is kept for data caching, but the event is not actually registered.

### Parity verdict

Parity is incomplete. The passport is the closest narrative surface to current code. The broader report pack set is not internally consistent enough to be trusted without source inspection.

## 13. Final Risk Assessment

### Current dormant risk

Current live-style risk is low because:

1. `mean_reversion` is not assigned in `config/aurora/strategies.yaml`.
2. Both V1 and V2 are disabled in `mean_reversion.yaml`.

### Enablement risk

Enablement risk is high because:

1. V1 price-reaction input is not wired to the MR handler the way the code expects.
2. The test suite misses the exact runtime contract mismatch that matters most for V1.
3. V2 docs and reports still contain contradictory semantics and overstated evidence.
4. Current repo defaults likely disable dynamic funding features, so V2 would often behave as static split thresholds even if enabled.

### Required follow-up before trust

1. Wire price-motion data into the actual MR runtime contract.
   - Either place `price_motion` inside MR `cmd_payload["features"]`, or register and correctly cache `EVT:FEATURES_CALCULATED` for MR.
2. Add end-to-end MR tests around real `CMD:PROCESS_STRATEGY` payload shape.
   - Include cases with and without nested price-motion data.
   - Assert ordering: `on_bar()` -> V1 veto -> downstream signal path.
3. Add real V2 call-site cleanup tests.
   - Force an exception during `on_bar()` and assert the actual finally block clears overrides.
4. Rewrite stale report packs and the V2 prose in `config_models.py`.
5. Explicitly document whether V2 is expected to remain static split under current default feature-engineering config.

## 14. Final Verdict: ACCEPT WITH CRITICAL GAPS

Reason:

- The implementation is real.
- Vector 2 math is mostly correct.
- Vector 1 safety hardening is real.
- But the repository does not support a clean claim that both vectors are fully correct, fully integrated, and rollout-ready.

If the question is "can this remain dormant on disk?" the answer is yes.

If the question is "should this be trusted for enablement without further work?" the answer is no.
