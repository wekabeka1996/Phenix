## 1. Current C.1/C.2 Runtime Surface

- C.1 anchor ownership remains handler-local in `apps/reference/domains/decision_making/md_amr_handler.py`. The handler stores `_entry_anchor`, passes `entry_price` / `entry_target_price` into `position_ctx`, sets anchors on `ENTRY`, and clears them on full-flat transitions.
- C.1 strategy trace remains in `apps/reference/domains/feature_engineering/md_amr_strategy.py`. In-position trace already exposes `progress_pct`, `progress_state`, `entry_price`, and `entry_target_price`; missing anchors remain explicit as `progress_state="UNKNOWN"` and `progress_pct=None`.
- C.2 remains strategy-local and entry-only. `setup_quality`, `sq_penetration`, `sq_channel_quality`, `sq_coherence`, and `sq_volatility` are added only on `ENTRY` trace and are not part of `resolve_exit_action()`.
- Current runtime evidence still proves `md_amr` is active on its assigned path: `reports/RUNTIME_21H_FORENSIC_CONTEXT_REPORT.md` shows `XRPUSDT` reaching handler-owned path, `TRADE_INTENT_PROPOSED`, and execution, and shows `BNBUSDT` execution as proven.
- `UNKNOWN`: `config/docs/MD_AMR_PACKAGE_C1_REPORT.md` is not present in the repo.
- `UNKNOWN`: `config/docs/MD_AMR_PACKAGE_C2_REPORT.md` is not present in the repo.
- `STALE`: `config/docs/MD_AMR_BASELINE_STATUS_SNAPSHOT.md` contains an older activation snapshot that does not match current `config/aurora/strategies.yaml` plus the 21h runtime report. It was used only for baseline defaults, not for current activation truth.

## 2. C.3 Design

- Cause: a hold can remain structurally alive (`hold_health > hold_edge_min`) while anchored thesis progress lags and time-to-timeout keeps shrinking.
- Chosen mechanism: add a compact in-position overlay in strategy math only; do not move state into the strategy, do not alter handler ownership, and do not let C.3 own execution truth.
- Expected progress rule:
  - `elapsed_hold_frac = clamp(bars_held / max_hold_bars, 0, 1)`
  - `expected_progress_pct = 0` during a grace window
  - after grace, expected progress ramps linearly to `1.0` by timeout
- Progress lag rule:
  - `progress_deficit = max(0, expected_progress_pct - clamp(progress_pct, 0, 1))`
- Time erosion rule:
  - `remaining_hold_frac = 1 - elapsed_hold_frac`
  - `time_decay = clamp((1 - remaining_hold_frac) * (1 - clamp(progress_pct, 0, 1)), 0, 1)`
- Hold quality rule:
  - `structural_hold_quality = clamp((hold_health + 1) / 2, 0, 1)`
  - `hold_quality = clamp(structural_hold_quality - time_decay_weight*time_decay - progress_deficit_weight*progress_deficit, 0, 1)`
- Effect: healthy progressing holds remain materially above stale lagging holds in trace, while exit behavior stays unchanged.
- Design choice: C.3 is trace/overlay only in this package. It does not yet gate exits. That keeps Package A/B semantics intact and avoids repeating Package B-style promotion without evidence.

## 3. Fields Added

- `elapsed_hold_frac`: strategy-local trace field in `MDAMRStrategyV11`; derived from `bars_held` and `max_hold_bars`.
- `remaining_hold_frac`: strategy-local trace field in `MDAMRStrategyV11`; derived from `elapsed_hold_frac`.
- `expected_progress_pct`: strategy-local trace field in `MDAMRStrategyV11`; derived from elapsed hold fraction plus the explicit grace/ramp rule.
- `progress_deficit`: strategy-local trace field in `MDAMRStrategyV11._compute_hold_quality_overlay()`; not stored in handler state.
- `time_decay`: strategy-local trace field in `MDAMRStrategyV11._compute_hold_quality_overlay()`; not stored in handler state.
- `structural_hold_quality`: strategy-local trace field in `MDAMRStrategyV11`; normalized view of existing `hold_health`.
- `hold_quality_penalty`: strategy-local trace field in `MDAMRStrategyV11`; sum of weighted C.3 penalties.
- `hold_quality`: strategy-local trace field in `MDAMRStrategyV11._compute_hold_quality_overlay()`; emitted on in-position trace only and not consumed by execution lifecycle ownership.

## 4. Config Surface

- YAML SSOT: `config/aurora/strategies/md_amr.yaml` now contains a required `hold_quality` block:
  - `expected_progress_grace_frac: 0.25`
  - `time_decay_weight: 0.35`
  - `progress_deficit_weight: 0.45`
- Pydantic SSOT: `apps/reference/config_models.py` now defines `MDAMRHoldQualityConfig` with `extra='forbid'`.
- Contract guard: `MDAMRHoldQualityConfig` rejects unknown fields and rejects penalty weights whose sum is greater than `1.0`.
- `MDAMRStrategyConfig.hold_quality` is now required, so C.3 fails closed if the block is absent from `md_amr.yaml`.
- Handler wiring: `apps/reference/domains/decision_making/md_amr_handler.py` now forwards:
  - existing baseline fields `hold_edge_min` and `target_approach_pct`
  - new C.3 fields from `self._cfg.hold_quality.*`

## 5. Files Changed

- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/md_amr_strategy.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- `config/aurora/strategies/md_amr.yaml`
- `tests/domains/feature_engineering/test_md_amr_package_c3_hold_quality.py`
- `tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py`
- `tests/config/test_md_amr_package_c3_config_contract.py`
- `tests/domains/decision_making/test_md_amr_silence_observability.py`
- `tests/domains/decision_making/test_md_amr_tf_sec_guard.py`
- `reports/MD_AMR_PACKAGE_C3_VALIDATION_CASES.md`
- `config/docs/MD_AMR_PACKAGE_C3_REPORT.md`

## 6. Validation Evidence

- Contract validation:
  - `tests/config/test_md_amr_package_c3_config_contract.py` proves current config loads, unknown fields are rejected, and invalid penalty budgets fail closed.
- Behavior + regression validation:
  - Command run:

```text
python -m pytest tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py tests/domains/feature_engineering/test_md_amr_package_b_hold_calibration.py tests/domains/feature_engineering/test_md_amr_package_c1_progress.py tests/domains/feature_engineering/test_md_amr_package_c2_setup_quality.py tests/domains/feature_engineering/test_md_amr_package_c3_hold_quality.py tests/domains/decision_making/test_md_amr_runtime_readiness.py tests/domains/decision_making/test_md_amr_silence_observability.py tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py tests/config/test_md_amr_package_c3_config_contract.py tests/domains/decision_making/test_md_amr_tf_sec_guard.py -q
```

  - Result: `84 passed in 1.15s`
- Evidence artifact:
  - `reports/MD_AMR_PACKAGE_C3_VALIDATION_CASES.md`
  - Key separation from the artifact:
    - `healthy_mid_hold hold_quality = 0.7909`
    - `stale_late_hold hold_quality = 0.2066`
    - `lagging_late_hold progress_deficit = 0.5667`
    - `stale_late_hold time_decay = 0.8312`
- Runtime/handler compatibility:
  - `tests/domains/decision_making/test_md_amr_package_c3_handler_contract.py` proves the handler passes the C.3 config block into the strategy core and preserves the anchor surface in `position_ctx`.
  - `tests/domains/decision_making/test_md_amr_silence_observability.py` still passes, so the handler-owned signal emission path remains intact at unit/integration level.

## 7. What Is Proven

- `time_decay`, `progress_deficit`, and `hold_quality` are implemented in `md_amr` strategy math.
- The C.3 formulas are deterministic and replay-testable at helper level.
- The new C.3 fields are visible in in-position trace.
- Anchor-missing behavior stays explicit (`UNKNOWN` / `None`) instead of silently inventing progress.
- Baseline exit semantics remain unchanged. Package A/B/C.1/C.2 regression suites are still green.
- The config contract is typed, strict, and explicit in YAML.
- Handler ownership remains intact: anchors stay handler-owned, strategy math stays strategy-local, and execution truth is still outside C.3.

## 8. What Remains Unproven

- No full bar-replay or normalized economic validation has been run after the C.3 patch.
- No live/testnet runtime session has been rerun after this patch, so post-patch XRP/BNB runtime proof is still absent.
- `config/docs/MD_AMR_PACKAGE_C1_REPORT.md` and `config/docs/MD_AMR_PACKAGE_C2_REPORT.md` remain missing from the repo.
- C.3 has not yet been promoted into exit gating or capital-allocation behavior; only the explainable overlay is proven here.

## 9. Operational Risks

- If `hold_quality` is promoted into exit decisions without replay/economic validation, slow but valid reversions could be cut too aggressively.
- The chosen expected-progress rule is intentionally narrow (`grace + linear ramp`). It is explainable, but it is not yet symbol/regime-calibrated.
- Some older md_amr documents in the repo are stale on activation history. Future package work should continue trusting current code, current YAML, and current runtime artifacts over stale historical summaries.
- C.3 now fails closed on missing YAML block. Any out-of-date temp config used by future tests or scratch replays must include the new `hold_quality` block explicitly.

## 10. Final Verdict

Package C.3 is complete at the package boundary.

`md_amr` now has a deterministic, explainable hold overlay for `time_decay`, `progress_deficit`, and `hold_quality`, wired through YAML + Pydantic SSOT, visible in trace, and validated by focused strategy, handler, config, and regression tests. Scope stayed inside `md_amr`, exit ownership did not drift, and no broad rewrite was introduced.

What is not complete is promotion. C.3 is implemented and validated as an additive cognitive overlay, but it is not yet economically proven for live default behavior.
