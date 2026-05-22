# NEXT TESTNET CONFIG BLUEPRINT 2026-05-16

Status: PROPOSED

Scope: Aurora next testnet preset based on `order_log_scenario_backtest` replay and actual-hold forensics.

This document is blueprint-only. It does not apply any config changes by itself.

## Objective

Cut the currently evidence-backed losing configuration surfaces before the next testnet run, keep the cohorts that still show entry alpha, move live behavior closer to the profitable `TP/SL-only` contour, and explicitly record what the original blueprint did not cover.

## Evidence Base

Primary evidence files:

- `reports/order_log_scenario_backtest/post_download_tp24h_20260515/run_manifest.json`
- `reports/order_log_scenario_backtest/post_download_tp24h_20260515/tp_sl_only/report.md`
- `reports/order_log_scenario_backtest/post_download_tp24h_20260515/sidecar_only/report.md`
- `reports/order_log_scenario_backtest/post_download_20260515_live/actual_hold_roi_path_summary.json`
- `reports/order_log_scenario_backtest/post_download_20260515_live/actual_hold_roi_path_analysis.csv`
- `reports/order_log_scenario_backtest/pyramiding_enabled_20260516/run_manifest.json`
- `reports/order_log_scenario_backtest/pyramiding_enabled_20260516_non_strict/pyramiding_enabled_tp_sl_only/report.md`
- `reports/order_log_scenario_backtest/pyramiding_enabled_20260516_non_strict/pyramiding_candidate_summary.json`
- `reports/order_log_scenario_backtest/pyramiding_enabled_20260516_non_strict/pyramiding_candidate_audit.csv`

Primary config targets:

- `config/aurora/domains.yaml`
- `config/aurora/strategies/aurora.yaml`

## Executive Verdict

The strongest next-step preset is:

1. Remove sidecar from live close authority, but keep its telemetry.
2. Remove signal-based non-TP/SL exits from Aurora for the next run.
3. Disable `XRPUSDT` in Aurora.
4. Remove `MEAN_REVERSION` from Aurora `allowed_regimes` for the symbols that still allow it.
5. Keep `NRR026...030` disabled for now.
6. Keep Aurora `position_mode = STRICT` for the baseline next testnet preset.
7. Do not enable global pyramiding from config on the basis of the current evidence.

This is not a guarantee of profit. It is the narrowest config profile that matches the current evidence.

## What V1 Missed

The original blueprint did not include a counterfactual pass for same-side signals that were rejected by anti-pyramiding logic.

That matters because Aurora currently runs with `position_mode: STRICT` on all covered symbols, and the live system emits real `ANTI_PYRAMIDING_BLOCK` rejects. A baseline that looks only at actually opened positions can miss a separate alpha slice that existed in the decision stream but never reached execution.

This document is updated to include that missing slice and to explain why the new evidence still does not justify a global switch to `DYNAMIC`.

## Why This Preset

### 1. Sidecar is the clearest losing surface

- `tp_sl_only`: `62` trades, `39` wins, `23` losses, `total_net_roi = +108.05375`
- `sidecar_only`: `62` trades, `17` wins, `34` losses, `11` unresolved, `total_net_roi = -135.74516014`
- Actual closed cohort: `54` closed, `27` wins, `27` losses, `actual_total_net_roi = -13.25732902`
- `CLOSE_FILL_ONLY`: `27` trades, `net_roi_sum = -147.25210413`
- `13 / 27` `CLOSE_FILL_ONLY` trades were positive at some point during the hold but later closed worse

Interpretation:

- Entry alpha exists.
- Current close handling destroys too much of that edge.
- Sidecar should not hold live close authority in the next run.
- `shadow` is preferred over `disable` because the sidecar code emits action-bearing close requests only in `ENABLE`, so `shadow` keeps telemetry while removing live close-command authority.

### 2. `XRPUSDT` is weak on both theoretical and actual surfaces

- `XRPUSDT` in `tp_sl_only`: `10` trades, `total_net_roi = -11.8`
- `XRPUSDT` in actual closed cohort: `total_net_roi = -12.67154894`

Interpretation:

- This is not only a close-management issue.
- `XRPUSDT` currently looks weak even under the favorable `TP/SL-only` contour.

### 3. `MEAN_REVERSION` is weak on both theoretical and actual surfaces

- `MEAN_REVERSION` in `tp_sl_only`: `28` trades, `total_net_roi = -36.9`
- `MEAN_REVERSION` in actual closed cohort: `total_net_roi = -34.05991177`

Interpretation:

- This regime should be cut from the next Aurora testnet preset.

### 4. `TREND_UP` and `TREND_DOWN` should not be cut

- `TREND_UP` in `tp_sl_only`: `total_net_roi = +66.7`
- `TREND_DOWN` in `tp_sl_only`: `total_net_roi = +60.41`
- `TREND_UP` in actual closed cohort: `total_net_roi = -15.68009242`
- `TREND_DOWN` in actual closed cohort: `total_net_roi = +19.41860625`

Interpretation:

- These regimes are not the primary problem.
- The bigger problem is how positions are being managed and closed after entry.

### 5. `BNBUSDT` should not be cut automatically

- `BNBUSDT` in `tp_sl_only`: `total_net_roi = +14.6`
- `BNBUSDT` in actual closed cohort: `total_net_roi = -44.55712447`

Interpretation:

- `BNBUSDT` looks bad in actual runtime, but good under `TP/SL-only`.
- This points more to bad close behavior than to hopeless entry quality.
- Keep `BNBUSDT` only if sidecar and signal exits are removed from live authority.

### 6. Pyramiding was a real blind spot, but it does not justify global `DYNAMIC`

Pyramiding scenario method:

- Source of synthetic candidates: `ANTI_PYRAMIDING_BLOCK` rejects from `logs/shadow_critical_event_journal_v1.jsonl`
- Entry construction rule: same-side reject must have an active same-side reference position at reject time
- Synthetic add-entry price: next `1m` candle open after reject timestamp
- TP/SL geometry: current Aurora TP/SL config
- Leverage: current `target_leverage` from config
- Quantity: non-authoritative in retained truth; scenario keeps `qty=0` and evaluates ROI as price-path geometry rather than account-size PnL

Pyramiding scenario evidence:

- Rejects seen: `318`
- Synthetic entries materialized: `298`
- Candidates skipped: `20`
- Strict run verdict: fail-closed for fresh rejects without a full future `+24h` replay horizon
- Analytical non-strict run verdict: usable for hypothesis analysis only, not production promotion

Top-line analytical result from `pyramiding_enabled_tp_sl_only`:

- `363` trades
- `308` resolved
- `190` wins
- `118` losses
- `55` unresolved
- `avg_net_roi = +1.65`
- `total_net_roi = +508.2`

Why this is not enough to enable pyramiding globally:

- The positive result is heavily concentrated in one narrow synthetic cohort: `LOW_VOLATILITY + SELL`
- Synthetic `LOW_VOLATILITY + SELL`: `115` trades, `63` resolved wins, `1` resolved loss, `52` unresolved, `total_net_roi = +1039.9625`
- If that one cohort is removed, synthetic pyramiding becomes strongly negative:
  - `183` resolved synthetic trades
  - `89` wins
  - `94` losses
  - `avg_net_roi = -3.4963`
  - `total_net_roi = -639.81625`

Negative synthetic pyramiding cohorts:

- `MEAN_REVERSION`: `total_net_roi = -447.3`
- `TREND_UP`: `total_net_roi = -160.55`
- `LOW_VOLATILITY + BUY`: `total_net_roi = -89.40625`

Interpretation:

- Pyramiding is not globally bad, but it is also not globally good.
- The current evidence supports at most a narrow hypothesis around `LOW_VOLATILITY + SELL`.
- Current `position_mode` is only `STRICT` or `DYNAMIC` at the per-symbol level. It is not regime-specific or side-specific.
- Because of that config contract, a clean YAML-only change cannot express the apparently good slice without also turning on clearly bad slices for the same symbol.

Blueprint consequence:

- Do not switch Aurora symbols to `DYNAMIC` in the baseline next testnet preset.
- Keep `position_mode: STRICT` for all Aurora symbols for the baseline run.
- If pyramiding is tested later, it should be a dedicated experiment with new gating semantics, not a broad config flip.

## Recommended Config Changes

### Preset A: Recommended next testnet baseline

| File | Key | Current | Proposed | Why |
|---|---|---|---|---|
| `config/aurora/domains.yaml` | `execution_position.position_policy_sidecar.mode` | `enable` | `shadow` | Keep telemetry, remove live sidecar close authority |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.decision.exit.signal_exit_enabled` | `true` | `false` | Move closer to profitable TP/SL-only contour |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.*.position_mode` | `STRICT` | keep `STRICT` | Global `DYNAMIC` would enable both promising and clearly bad pyramiding cohorts because the contract is per-symbol, not per-regime or per-side |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.XRPUSDT.enabled` | `true` | `false` | XRP is negative in both actual and TP/SL-only |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.BTCUSDT.allowed_regimes` | includes `MEAN_REVERSION` | remove `MEAN_REVERSION` | Regime is negative on both surfaces |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.BNBUSDT.allowed_regimes` | includes `MEAN_REVERSION` | remove `MEAN_REVERSION` | Regime is negative on both surfaces |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.DOGEUSDT.allowed_regimes` | includes `MEAN_REVERSION` | remove `MEAN_REVERSION` | Regime is negative on both surfaces |
| `config/aurora/strategies/aurora.yaml` | `strategies.aurora.assets.XRPUSDT.allowed_regimes` | includes `MEAN_REVERSION` | remove `MEAN_REVERSION` | Future-proof even if XRP is re-enabled later |
| `config/aurora/domains.yaml` | `decision_making.directional_sanity.nrr026_enabled` | `false` | keep `false` | Replay evidence is not decision-grade |
| `config/aurora/domains.yaml` | `decision_making.directional_sanity.nrr027_enabled` | `false` | keep `false` | Replay evidence is not decision-grade |
| `config/aurora/domains.yaml` | `decision_making.price_motion_sanity.enabled` | `false` | keep `false` | Replay evidence is not decision-grade |

### Optional stricter variant

If the next run must be maximally conservative, also disable `DOGEUSDT` in Aurora for one cycle.

Reason:

- `DOGEUSDT` is positive in current replay, but the sample is too small to treat as decision-grade.

## Concrete YAML Target Shape

### 1. `config/aurora/domains.yaml`

```yaml
execution_position:
  position_policy_sidecar:
    mode: shadow

decision_making:
  directional_sanity:
    nrr026_enabled: false
    nrr027_enabled: false
  price_motion_sanity:
    enabled: false
```

### 2. `config/aurora/strategies/aurora.yaml`

```yaml
strategies:
  aurora:
    decision:
      exit:
        signal_exit_enabled: false
    assets:
      BTCUSDT:
        position_mode: STRICT
        allowed_regimes:
        - TREND_UP
        - TREND_DOWN
        - LOW_VOLATILITY
        - HIGH_VOLATILITY
      BNBUSDT:
        position_mode: STRICT
        allowed_regimes:
        - TREND_UP
        - TREND_DOWN
        - HIGH_VOLATILITY
      DOGEUSDT:
        position_mode: STRICT
        allowed_regimes:
        - TREND_DOWN
        - HIGH_VOLATILITY
      XRPUSDT:
        enabled: false
        position_mode: STRICT
        allowed_regimes:
        - TREND_UP
        - TREND_DOWN
        - HIGH_VOLATILITY
        - LOW_VOLATILITY
```

## Explicitly Not Recommended Yet

Do not change these yet based only on the current dataset:

- `signal_threshold.value`
- `exit.sl_pct`
- `regime_tpsl.tp_mult`
- `regime_tpsl.sl_mult`
- `position_mode` from `STRICT` to `DYNAMIC`
- `target_leverage`
- `regime_sizing`
- `reentry_cooldown_sec`

Reason:

- The current evidence clearly isolates the main losing surfaces as sidecar close behavior, signal-based non-TP/SL exits, `XRPUSDT`, `MEAN_REVERSION`, and broad untargeted pyramiding.
- It does not yet justify deeper geometry retuning.

## NRR Position

Do not enable `NRR026...030` in the next testnet preset.

Reason:

- Offline replay did not preserve enough authoritative gate surfaces to make a trustworthy financial call.
- Current blocked reasons are mostly missing retained context, not proven profitability or unprofitability.

## Expected Outcome Band

If the next run uses the recommended preset, the theoretical expectation is a band, not a single number:

- Conservative operational band: around `+0.5%` to `+1.0%` average `net ROI` per trade
- More optimistic upper band if live behavior stays close to TP/SL replay: around `+3.8%` to `+4.0%` average `net ROI` per trade

This is not account-level return. It is per-position `net ROI` in the current reporting methodology.

For pyramiding specifically, the current evidence does not justify adding a second expected-return band to the baseline preset, because the apparent positive synthetic result is too concentrated in one narrow cohort and cannot be expressed safely with the current `STRICT/DYNAMIC` config contract.

## Validation Protocol For The Next Testnet Run

The next run should be accepted only if all of the following are true:

1. `position_policy_sidecar.mode = shadow` produced telemetry but no live sidecar close-command authority.
2. `signal_exit_enabled = false` removed premature non-TP/SL Aurora exits.
3. `XRPUSDT` produced no Aurora entries.
4. `MEAN_REVERSION` produced no Aurora entries.
5. Actual closed cohort no longer shows `CLOSE_FILL_ONLY` as the main PnL drag.
6. `TREND_UP` remains live and no longer flips from positive `TP/SL-only` expectation into actual net loss because of close handling.
7. Aurora symbols remained `position_mode: STRICT` for the baseline run.

## FACTS

- `TP/SL-only` is profitable on the reconstructed cohort.
- `sidecar-only` is strongly unprofitable on the same cohort.
- `XRPUSDT` is negative in both actual and `TP/SL-only`.
- `MEAN_REVERSION` is negative in both actual and `TP/SL-only`.
- `TREND_UP`, `TREND_DOWN`, `BTCUSDT`, `ETHUSDT`, and `BNBUSDT` still show usable entry-side signal under `TP/SL-only`.
- Same-side anti-pyramiding rejects do contain a real counterfactual signal surface, but it is highly asymmetric by regime and side.

## INFERENCES

- The main damage is in position management and close authority, not in all entry logic.
- The next testnet preset should simplify live exit authority before it attempts deeper threshold tuning.
- The narrowest high-confidence move is to push Aurora toward a TP/SL-dominant contour.
- Pyramiding should remain out of the baseline preset because the current positive result is dominated by `LOW_VOLATILITY + SELL`, while several other pyramiding cohorts are clearly negative.

## ASSUMPTIONS

- The next testnet run will be used as a validation pass, not as final production promotion.
- `shadow` mode is acceptable because it preserves telemetry without granting live sidecar close authority.
- No hidden external strategy overrides will reintroduce the removed Aurora surfaces.
- The synthetic pyramiding scenario is acceptable as a hypothesis generator even though it does not have authoritative size truth.

## UNKNOWNS

- Exact account-level return remains unknown until position overlap, balance utilization, and compounding are modeled explicitly.
- The exact incremental value of `DOGEUSDT` remains weakly proven because the sample is small.
- `NRR026...030` remain financially undecidable in the current replay substrate.
- A safe config-only way to express `LOW_VOLATILITY + SELL` pyramiding does not exist in the current per-symbol `position_mode` contract.
