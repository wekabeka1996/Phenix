# P0: Runtime Influence and Timing Forensic Report

## 1. Executive Verdict
**FACT:** Raw `obi` and `tfi` features do **not** feed directly into any core strategy scoring logic for Aurora or MD-AMR. Instead, they act strictly as upstream L2 Risk vetos, L3 Strategy vetos (Mean Reversion), or downstream execution modulators (EntryPlan offsets).
**FACT:** Aurora scoring is driven almost exclusively by upstream models (via `pillar_sum` / `linear_score`) modulated by `volatility`. The documentation claims that `obi` is a "global essential" scoring feature are materially false in runtime.
**FACT:** `llm_microstructure` is a bridge-driven strategy (Sentinel Handler) that relies on the IPC bus (`CMD:LLM_INTENT_SUBMIT_V1`); it performs zero internal feature computation and ignores `obi`/`tfi`.
**FACT:** The system timing configuration is littered with dead knobs (`trading.execution.exposure.*`, `hardening.ttl_config.*`) and code-default-only parameters (like `bar_ttl_ms` silently defaulting to 10s).

## 2. Facts
1. `tfi` is a direct live consumer in `risk_management.py` (L2 Risk score toxicity term) and `mean_reversion_handler.py` (L3 Microstructure Veto).
2. `obi` is a direct live consumer in `entry_plan.py` (limit offset modulation) and an optional confirmation in `mean_reversion_handler.py`.
3. Aurora and MD-AMR extract `obi` strictly to pass to `entry_plan.py`.
4. `system.market_data.tick_ttl_ms` is entirely inert in bar mode because `regime_detector.py` returns early on `tf_sec == 0` before the TTL check.
5. The `llm_gate` used by `md_amr_handler.py` relies on the `sentiment_state` feature.

## 3. OBI/TFI Consumer Map
Refer to `artifacts/P0_OBI_TFI_CONSUMER_MAP.csv` for complete mappings.
- **L2 Risk:** Direct consumption of both OBI and TFI to compute `risk_score` (blocks execution entirely if max exceeded).
- **L3 Strategy (MR):** Direct consumption of TFI to compute an EMA. If EMA > threshold, blocks entry with `MICROSTRUCTURE_VETO:TFI_ADVERSE`.
- **L3 Strategy (Aurora/MD-AMR):** Indirect pass-through to entry planning.
- **Entry Planning:** Direct consumption of OBI to compute offset multipliers (`entry_k_atr * atr * obi_multiplier`).

## 4. Decision-Critical Feature Map by Strategy/Layer
Refer to `artifacts/P0_DECISION_CRITICAL_FEATURE_MAP.csv`.
- **Aurora Core:** `pillar_sum`, `volatility`.
- **Mean Reversion Core:** Implied math triggers (`z_score`, `rsi`), overridden by `tfi_ema` veto.
- **MD-AMR Core:** Basic price series + `sentiment_state` veto.
- **LLM Microstructure Core:** None (IPC bridge).

## 5. Timer / TTL / Cooldown / Hysteresis Census
Refer to `artifacts/P0_TIMER_TTL_CENSUS.csv`.
**Key wiring findings:**
- `watchdog` correctly uses `ack_ttl_ms`, `fill_ttl_ms`, and `check_interval_ms`.
- `aurora` correctly implements `reentry_cooldown_sec` and `cooldown_after_close_ms`.
- `exposure_guard` reads from `domains.execution_position.exposure_guard.*`, rendering `trading.execution.exposure.*` fields dead.
- `md_amr_handler` relies heavily on `defer_ttl_sec` and `reconcile_interval_sec`.

## 6. Drift / Contradiction Ledger
Refer to `artifacts/P0_DRIFT_AND_CONTRADICTION_LEDGER.md`.
Major contradictions:
- `aurora_math_passport.md` misrepresents OBI as a direct scoring variable.
- `trading_passport.md` describes exposure TTLs in `trading.yaml` which are silently ignored by the `ExposureGuard` (it reads `domains.yaml`).
- `system_passport.md` claims `hardening.ttl_config` values apply to API requests, but the python execution environment does not wire these values anywhere.

## 7. Negative Findings
Refer to `artifacts/P0_NEGATIVE_FINDINGS.md`.
- Aurora does not score using OBI/TFI.
- LLM Microstructure performs no internal feature evaluation.
- `tick_ttl_ms` does nothing in standard bar mode.

## 8. Operational Risks
- **False Tuning (High Risk):** Operators attempting to tune `trading.execution.exposure.*` or `hardening.ttl_config.*` will observe zero runtime changes.
- **Hidden Failures (Medium Risk):** The silent fallback of `bar_ttl_ms` to `10000` ms inside `regime_detector.py` means stale bars might cause intermittent regime collapses (`UNCERTAIN`) without clear configuration traceability.
- **Misattributed Score Volatility (High Risk):** Tuning `obi` weights in an attempt to modify Aurora's underlying win-rate/conviction will fail, as `obi` only shifts the limit order entry price.

## 9. Recommended Next Investigations
1. **Exposure Guard Wiring Audit:** We must formally remove `trading.execution.exposure.*` from YAML or re-wire `ExposureGuard` to prioritize it, enforcing a single source of truth.
2. **Aurora Feature Math Injection:** Determine if `obi`/`tfi` *should* have been included in the quadratic scoring kernel (as the documentation implies) and was accidentally left out during a previous refactor.
3. **Tick/Bar TTL Consolidation:** Clean up the `regime_detector.py` early returns so that `tick_ttl_ms` functions as intended or is formally removed.

## 10. Validation Evidence
- **Code path tracing:** 
  - `risk_management.py:368-369` (Computes `risk_score` adding `abs(obi)` and `abs(tfi)` terms).
  - `aurora_decision.py:990` and `entry_plan.py:213` (Show OBI simply passed to `EntryPlan` and clamped).
  - `mean_reversion_handler.py:666` (TFI extracted and explicitly drives `MICROSTRUCTURE_VETO`).
  - `llm_microstructure.py:28` (Returns `_LlmMicrostructureSentinelHandler` which only logs a string and registers no FSM listeners).
  - `regime_detector.py:377` (`getattr(sys_md, "bar_ttl_ms", 10000)` fallback).

## 11. What Remains Unproven
- It remains unproven whether the *external* models that generate `pillar_sum` (consumed by Aurora) or the external IPC intent generators (consumed by `llm_microstructure`) are using OBI/TFI under the hood. Our scope is limited strictly to the python runtime's live decision boundaries.
- We have not validated whether the specific clamps/thresholds (e.g. `obi_mod_clamp_max` = 1.2) are mathematically optimal for the current market regime, as this was not a tuning task.

### WHAT IS PROVEN
1. The exact locations where OBI and TFI influence the `risk_management` gate, `mean_reversion` veto, and `entry_plan` offset.
2. The complete absence of OBI/TFI in Aurora's `quadratic_scoring_kernel.py`.
3. The sentinel nature of `llm_microstructure`.
4. The exact config keys powering TTLs and cooldowns, including dead knobs in `trading.yaml`.

### WHAT REMAINS UNPROVEN
1. External upstream usage of OBI/TFI in models compiling `pillar_sum`.
2. The correctness or profitability of the currently active config values.