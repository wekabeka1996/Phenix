# Judge Current-Window Trading Readiness Review

Executive verdict: CONFIG_ONLY_TESTNET_PROMOTION_POSSIBLE, FULL_LIVE_PROMOTION_NOT_PROVEN.

## Scope

- Evidence window in this workspace: 14 judge shadow slices across 7 symbols and 2 dates.
- All currently available XRP slices were processed: 2026-05-23 and 2026-05-24.
- Primary evidence anchors:
  - reports/judge/sidecar_shadow_counterfactual_batch_all_available/report.md
  - reports/judge/cross_asset_current_window_feature_report/report.md
  - reports/judge/shadow_entry_plan_XRPUSDT_2026-05-24_barcount_research/financial_report.md

## Facts

- The current batch processed 14 of 14 available shadow entry plan files with 0 failures.
- The current aggregate balanced managed-exit recommendation is sidecar_pct_0.40_gb_80.
- The best current-config managed scenario in the same batch is sidecar_pct_0.07_gb_50.
- Judge confidence and live Aurora score are different fields and different authority surfaces.
- Live Aurora decision math currently resolves from linear_score or features['pillar_sum'] and then emits raw_score and decision_score.
- In the score-lineage registry, pillar_sum, raw_score, decision_score, and objective_score are live-authoritative fields.
- In the same registry, strategy_confidence and judge_confidence are shadow-only normalized confidence candidates.
- The active quadratic kernel accepts signal_weights and feature_neutrals for compatibility but explicitly does not read them.
- Current live SSOT symbol status is not "everything is already on":
  - enabled: ETHUSDT, SOLUSDT, BTCUSDT, DOGEUSDT
  - disabled: BNBUSDT, 1000PEPEUSDT, XRPUSDT
- Current symbol regime exposure is heterogeneous, not global:
  - ETHUSDT: TREND_UP, TREND_DOWN, LOW_VOLATILITY
  - SOLUSDT: TREND_UP, TREND_DOWN, LOW_VOLATILITY, HIGH_VOLATILITY
  - BTCUSDT: TREND_UP, TREND_DOWN, LOW_VOLATILITY, HIGH_VOLATILITY
  - DOGEUSDT: TREND_DOWN, HIGH_VOLATILITY
  - BNBUSDT: TREND_UP, TREND_DOWN, HIGH_VOLATILITY
  - 1000PEPEUSDT: TREND_DOWN, LOW_VOLATILITY, FLAT_NORMAL, MEAN_REVERSION, TREND_UP
  - XRPUSDT: TREND_UP, TREND_DOWN, HIGH_VOLATILITY, MEAN_REVERSION, LOW_VOLATILITY
- Under current config, the 0.9-1.0 confidence bucket is negative on the current window aggregate and is therefore under suspicion as an overconfident or speculative slice rather than a reliably high-quality slice.
- Under best-available managed selection, the best single buckets by total net pnl are:
  - 0.5-0.6: total_net_pnl_pct = 316.533419
  - 0.6-0.7: total_net_pnl_pct = 305.579988
  - 0.7-0.8: total_net_pnl_pct = 244.171638
  - 0.8-0.9: total_net_pnl_pct = 154.523421
- Under best-available managed selection, the highest per-row expectancy among these high-confidence buckets is 0.8-0.9, not 0.5-0.6.
- Current-window top support feature findings in target buckets 0.6-0.9 are provisional but already directional:
  - macro_resid: robust_valuable
  - obi: mixed, regime-sensitive
  - delta_price: mixed, weaker and less stable

## Why The Original Analysis Used 0.1 Buckets

- The counterfactual tooling already materializes and compares discrete confidence buckets.
- The judge sidecar counterfactual target focus is explicitly defined as 0.6-0.7, 0.7-0.8, and 0.8-0.9.
- This bucketed view was used first because it localizes where profitability changes, where loss families cluster, and where apparently strong confidence becomes pathological.
- It does not imply that merged windows like 0.5-0.7 or 0.4-0.8 are invalid. Those merged windows were simply a second step, not the first step.

## Merged Confidence Range Results On The Current Window

These merged ranges were computed after the discrete bucket pass from the already materialized per-file scenario rows.

### best_available_managed

| range | rows | win_rate_pct | total_net_pnl_pct | expectancy_net_pnl_pct |
| --- | --- | --- | --- | --- |
| 0.4-0.8 | 3527 | 51.0632 | 972.417829 | 0.275707 |
| 0.5-0.8 | 2884 | 51.9417 | 866.285045 | 0.300376 |
| 0.6-0.9 | 2116 | 52.8828 | 704.275047 | 0.332833 |
| 0.5-0.7 | 2146 | 51.7707 | 622.113407 | 0.289894 |

### current_config

| range | rows | win_rate_pct | total_net_pnl_pct | expectancy_net_pnl_pct |
| --- | --- | --- | --- | --- |
| 0.4-0.8 | 3527 | 38.1627 | 196.873241 | 0.055819 |
| 0.5-0.8 | 2884 | 38.8003 | 183.174790 | 0.063514 |
| 0.6-0.9 | 2116 | 39.4612 | 166.309922 | 0.078596 |
| 0.5-0.7 | 2146 | 38.8164 | 95.579105 | 0.044538 |

### no_timeout

| range | rows | win_rate_pct | total_net_pnl_pct | expectancy_net_pnl_pct |
| --- | --- | --- | --- | --- |
| 0.4-0.8 | 3527 | 51.4602 | 966.246440 | 0.273957 |
| 0.5-0.8 | 2884 | 52.2538 | 864.582783 | 0.299786 |
| 0.6-0.9 | 2116 | 55.5293 | 732.587767 | 0.346214 |
| 0.5-0.7 | 2146 | 51.3514 | 621.410755 | 0.289567 |

## Interpretation Of The Range Results

- If the objective is maximum aggregate net pnl on the current window, 0.4-0.8 is the strongest merged range.
- If the objective is higher quality per candidate, 0.6-0.9 has the better expectancy.
- If the objective is pathology localization, the split 0.5-0.6 / 0.6-0.7 / 0.7-0.8 / 0.8-0.9 view is still better because merged windows hide where the deterioration or the edge is actually concentrated.
- Therefore the earlier bucket view was a diagnostic choice, not a claim that 0.5-0.7 or 0.4-0.8 were inferior by definition.

## Judge Confidence Versus Live Aurora Score

The profitable Judge confidence buckets are real evidence, but they answer a different question from live Aurora runtime scoring.

Judge confidence analysis tells us:

- where the cognitive or judge layer saw edge in shadow research
- which confidence windows behaved better or worse in those shadow slices

Live Aurora trading decisions currently depend on:

- pillar_sum as the signed linear input
- decision_score and raw_score from the quadratic kernel path
- objective overrides, regime allowlists, NRR, readiness, liquidity, and execution gates

Therefore a profitable Judge band cannot be copied directly into a live Aurora threshold without a mapping layer.

Practical consequence:

- if we stay in the current Aurora architecture, we must calibrate the fields that actually drive live execution
- if we want Judge confidence itself to decide promotion or trade activation, that is not YAML-only tuning anymore; it is a bridge or authority redesign

## What Can Be Tuned Without Code Changes

Important runtime boundary before any tuning:

- weights are only one control plane
- regime allowlists are a separate hard gate
- NRR and readiness/liveness protections are a separate hard gate family
- objective and execution gates are also separate

Therefore changing weights alone does not tell the system to trade more regimes, and turning on more regimes does not prove the weights are good.

Another critical boundary:

- a YAML-only weight retune is currently not proven to change live Aurora math unless it changes an upstream producer of pillar_sum or the scoring contamination is patched first
- the current runtime still passes signal_weights and feature_neutrals into the kernel call, but the active kernel marks them compatibility-only and ignores them

### 1. Entry weighting and admission thresholds

Real config surfaces already exist in config/aurora/strategies/aurora.yaml and config/aurora/domains.yaml.

Available YAML levers:

- aurora.decision.signal_weights
- aurora.decision.signal_threshold
- low_vol_cost_floor_gate.thresholds.min_direction_confidence_by_regime
- low_vol_cost_floor_gate.thresholds.min_normalized_confidence_by_regime
- low_vol_cost_floor_gate.thresholds.min_*_overrides_by_strategy_symbol

Current evidence-supported direction:

- Increase macro_resid modestly rather than aggressively. It is the strongest current candidate for a truly valuable feature.
- Do not increase obi just because its aggregate pnl is large. It is useful but not stable enough across slices to be treated as universally trustworthy.
- Reduce or at least cap delta_price before treating it as a primary driver. It is weaker and less stable on the current window.
- Tighten symbol and regime specific confidence floors for weak slices rather than using a single global threshold.

Recommended config-only sweep band, not yet a production claim:

- macro_resid weight: 0.10 -> 0.15 to 0.20 sweep
- delta_price weight: 0.15 -> 0.05 to 0.10 sweep
- obi weight: keep at or slightly below current, do not increase beyond current dominance
- signal_threshold: tighten only after weight changes, otherwise the system may simply suppress flow without fixing score quality

Interpretation boundary:

- this is a scoring recalibration under the current Aurora gate stack
- it is not a Judge authority rollout
- it does not override current regime allowlists
- it does not bypass NRR fail-closed behavior

### 2. Sidecar exit behavior

Real live action surface already exists in config/aurora/domains.yaml under position_policy_sidecar.

Important boundary:

- peak_giveback_close is a real live action path.
- shadow_percent_notional_arm is not a live action path; it is shadow diagnostics and calibration telemetry.

This means:

- The profitable shadow calibration around 0.30 to 0.40 percent arm and 80 percent giveback cannot be transferred literally into live behavior without code changes.
- The only direct config-only live giveback action currently available is the USD-based peak_giveback_close.

Config-only testnet approximation that is defensible:

- Enable peak_giveback_close
- Move giveback_trigger_pct from 50 to 80
- Set edge_arm_usd conservatively from observed testnet median notional rather than guessing from shadow plans
- Keep action scope bounded to soft close only

What this achieves:

- It approximates the looser giveback policy that outperformed the static timeout.
- It does not reproduce the shadow percent-arm exactly.

### 3. Shadow telemetry expansion for further calibration

Without code changes, the shadow candidate grid can still be widened in config for more faithful comparison in future runs.

Useful diagnostic extension:

- shadow_percent_notional_arm.candidate_pcts: add 0.10, 0.15, 0.20, 0.30, 0.40
- peak_giveback_close.giveback_trigger_pct: align shadow diagnostic comparison with the currently strongest aggregate giveback zone

This improves shadow observability, not live trading by itself.

## What Cannot Be Done Cleanly Without Code Changes

### Thresholded promotion from shadow to live Judge authority

The current contracts expose neocortex_enforcement_mode as a global shadow or enforce switch.
There is no existing config contract for:

- enforce only above confidence X
- stay shadow below confidence X
- symbol-specific live authority promotion by confidence window only

Therefore, a config-only rule such as "Judge exits shadow when confidence > 0.7" is not currently a first-class supported mode.

The closest approximation without code is:

- keep Judge in shadow authority mode
- tighten upstream admission and confidence thresholds so only stronger candidates survive to execution

### "Just turn everything on" is not the same experiment

Turning on disabled symbols, widening allowed_regimes, and changing weights in one package creates an attribution failure:

- if pnl improves, it is unclear whether the gain came from score recalibration, extra regime exposure, or simply higher trade count
- if pnl worsens, it is unclear whether the weights are bad or the newly enabled regimes are toxic
- NRR and readiness failures can still dominate regardless of the new score geometry

Therefore a broad enable-all experiment is operationally aggressive but analytically weak.

It is valid only if the objective is emergency exploratory testnet exposure rather than clean causal calibration.

### NRR and regime gates remain binding even with better weights

Examples already present in the current Aurora runtime:

- strict regime allowlist gate rejects entries with REGIME_NOT_ALLOWLISTED
- regime detector liveness rejects with NRR-REGIME-NO-HEARTBEAT
- stale heartbeat rejects with NRR-REGIME-DETECTOR-DEAD
- liquidity, objective, execution, and readiness gates can still reject independently of score quality

This means a better score can still result in no trade if the non-scoring contract is not satisfied.

### Global Judge promotion risk

The standalone Neocortex runtime on this branch explicitly refuses to boot unless decision_making.neocortex_enforcement_mode is shadow.
That means a clean no-code switch to globally enforced standalone Judge authority is not supported by the current standalone runtime boundary.

## How Far The Research Actually Went

Exhaustive within the currently available window:

- all 14 available symbol-date shadow slices were processed
- all currently available XRP slices were processed
- sidecar managed-exit calibration grid was run on the full current window
- per-file balanced picks were materialized
- current-window merged confidence ranges were computed
- cross-asset feature attribution from scenario rows was computed

Not exhaustive beyond the current window:

- only 2 dates per symbol are present in the current workspace slice
- there is no broader multi-week or multi-month judge shadow archive in this analysis set
- there is no rematerialized 1m execution path proof for official TP/SL and hold-horizon promotion claims
- there is no live or hybrid runtime A/B proving that the config-only plan improves real testnet outcomes

Therefore the current work is strong for a bounded testnet promotion plan, but not enough for an unconditional live promotion claim.

## Recommended No-Code Promotion Ladder

### Phase A: Config-only scoring cleanup in testnet

- Keep decision_making.neocortex_enforcement_mode = shadow.
- Reweight aurora decision.signal_weights toward macro_resid and away from delta_price overuse.
- Do not strengthen obi dominance yet.
- Tighten symbol or regime specific confidence floors only where the current window is weak.
- Keep current regime allowlists and current NRR protections unchanged for the first pass.

Why:

- this isolates whether weights and thresholds improve behavior under the same structural gate stack
- it avoids confusing score calibration with regime exposure expansion

### Phase B: Config-only bounded exit improvement in testnet

- Enable position_policy_sidecar.peak_giveback_close.
- Move giveback_trigger_pct toward 80 for the testnet trial.
- Set edge_arm_usd conservatively from observed median position notional, not from a guessed constant.
- Keep bounded soft-close only. Do not enable partial reduce or bracket mutation in the same trial.

### Phase C: Re-evaluate before any live promotion

- Compare the new testnet run against the current losing baseline.
- Require improvement in both aggregate pnl and stability by symbol.
- If the system still improves only in shadow-style replay but not in runtime testnet, do not promote Judge authority yet.

### Phase D: Only after that, expand regime exposure or symbol enablement

- widen allowed_regimes per symbol only after a symbol x regime report exists
- re-enable disabled symbols one by one, not all at once
- do not combine symbol re-enable, regime widening, and major weight retune into the same change set

## Two Different Projects

### Project 1: Aurora scoring recalibration

Goal:

- improve trade selection quality while keeping the existing Aurora decision stack, regime gates, NRR, objective checks, and execution gates

This project is config-first and can start now.

### Project 2: Judge-owned decision authority

Goal:

- move from Aurora-first admission to a real Judge-owned or hybrid Judge/Aurora authority bridge

This project is not a weight tweak. It requires a code path that explicitly defines:

- when Judge is authoritative
- how Judge and Aurora disagree
- which gates remain hard fail-closed
- how regime and NRR evidence is shared into the Judge authority surface

This project should not be smuggled into a YAML-only tuning pass.

## Operational Recommendation Right Now

- Defensible now: a config-only testnet or hybrid-live-data testnet-exec trial focused on entry weighting, confidence floor tightening, and bounded USD giveback exits.
- Not defensible now: full live promotion of Judge authority or a claim that the current evidence proves production profitability.
