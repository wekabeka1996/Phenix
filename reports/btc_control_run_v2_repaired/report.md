# Aurora Threshold Calibration Report

## Verdict
- NO_GO

## Scope
- Calibration class: production.
- Objective: calibrate only live per-symbol Aurora threshold surface for assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds.
- Threshold source mode: live-effective
- Evidence tier for this run: production-aligned because the replay reuses live RegimeDetector, QuadraticScoringKernel, shield cascade, and validation holdout.
- Non-goals: no neutral_threshold tuning, no weight tuning, no cooldown/reentry/holding-period changes, no writeback into base YAML.
- Symbols: BTCUSDT
- Date window: 2026-03-01 through 2026-03-31 inclusive
- Recorder timeframe: 300s
- Validation holdout: trailing 5 unique eligible recorder dates

## Runtime Truth Anchors
- FACT: active Aurora scoring path is QuadraticScoringKernel with DangerZone -> Context -> Memory shield cascade.
- FACT: this V2 replay reuses live RegimeDetector, QuadraticScoringKernel, live side-bias parameters, and live shield config.
- FACT: in live-effective mode the baseline threshold source follows live Aurora runtime semantics: use assets.<SYMBOL>.signal_threshold.value only when the per-symbol override is enabled, otherwise fall back to decision.signal_threshold.
- FACT: per-symbol signal_threshold.value and per-symbol regime_thresholds are the only tuned surfaces emitted by this tool.
- FACT: signal_weights, direction_strength_scoring, and feature_neutrals are legacy Aurora surfaces and are not tuned here.
- FACT: feature logs are audited for schema evidence, but recorder is the only auditable timestamp backbone because sampled feature-log keys expose no explicit timestamp field.

## Dataset Audit
- Config timeframe_sec: 300

### BTCUSDT
- Recorder bars loaded: 8199
- Validation split starts on: 2026-03-28
- Feature log: exists=True, size_mb=431.15, sampled_lines=20, has_timestamp_fields=False
- Sampled feature-log keys: ['absorption', 'delta_price', 'depth_imbalance', 'ema_bias', 'large_trade_imbalance', 'liquidity_kappa', 'macro_resid', 'macro_sync', 'obi', 'price', 'spread_bps', 'tfi', 'volatility_state', 'volume_spike', 'volume_zscore']
- WARNING: Sampled feature-log keys for BTCUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.

## Candidate Search Method
- Method: replay the current surface first, then fit candidate thresholds from train-split absolute score quantiles.
- Method: replay each candidate surface through live RegimeDetector, live shield cascade, and QuadraticScoringKernel using identical recorder bars.
- Fail-closed rule: when the current live baseline resolves through a global decision threshold or global regime-threshold map, candidate emission is disabled because this tool still emits per-asset overlay surfaces only.
- Candidate ranking objective: maximize validation-proxy desirability by train metrics tuple (mean_forward_bps_3, hit_rate_3, active_bars) after guardrail filtering.

## Guardrails
- min_activation_rate=0.0200
- max_activation_rate=0.3500
- max_daily_activation_rate=0.4500
- min_forward_edge_bps=0.00
- min_active_bars=8
- quantile_grid=[0.55, 0.6, 0.65, 0.7, 0.75]

## Baseline vs Candidate

### BTCUSDT
| split | eligible_bars | active_bars | activation_rate | buy_count | sell_count | max_daily_activation | mean_fwd_1_bps | mean_fwd_3_bps | hit_rate_1 | hit_rate_3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current/train | 2972 | 518 | 17.43% | 0 | 518 | 26.52% | -0.37 | 1.54 | 49.42% | 52.32% |
| current/validation | 993 | 148 | 14.90% | 0 | 148 | 34.29% | 0.23 | -1.93 | 52.03% | 44.22% |
- Current signal_threshold.value: 0.162000
- Current signal_threshold source: global_decision (decision.signal_threshold)
- Current regime_thresholds: {'HIGH_VOLATILITY': 0.18, 'LOW_VOLATILITY': 0.12, 'TREND_UP': 0.1, 'TREND_DOWN': 0.1, 'MEAN_REVERSION': 0.07, 'UNCERTAIN': 99.0, 'DEFAULT': 99.0}
- Current regime_threshold source: asset_override (assets.BTCUSDT.regime_thresholds)
- Candidate target supported: False
- Candidate blockers:
  - Current live signal threshold resolves via decision.signal_threshold; candidate emission remains limited to assets.<SYMBOL>.signal_threshold.value and is therefore disabled in this mode.
- No candidate cleared train-time guardrails.
- Symbol warnings:
  - Sampled feature-log keys for BTCUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.
  - Current live signal threshold resolves via decision.signal_threshold; candidate emission remains limited to assets.<SYMBOL>.signal_threshold.value and is therefore disabled in this mode.

## Candidate Overlay
```yaml
assets: {}
```

## Facts
- FACT: feature logs are present and schema-rich, but sampled lines do not expose explicit timestamp keys.
- FACT: recorder 300s bars expose price, high, low, pillar_sum, pillar_operator, pillar_strategist, spread_bps, volatility_state, pm_norm, readiness, and timestamp.
- FACT: recorder regime/regime_conf columns were not trusted for fitting; regimes are reconstructed offline through live RegimeDetector.

## Inferences
- INFERENCE: if a V2 candidate clears both train and validation guardrails, the restart recommendation is bounded to threshold-surface changes only.
- INFERENCE: if no candidate clears validation guardrails, the safest answer is NO_GO rather than widening scope into weight or shield changes.

## Assumptions
- ASSUMPTION: forward 1-bar and 3-bar close-to-close directional proxies are acceptable restart-side sanity checks, not realized PnL estimates.
- ASSUMPTION: side-bias and memory-shield sequential replay over recorder bars is directionally representative enough for threshold validation, even though execution gating/objective gating are not replayed here.

## Unknowns
- UNKNOWN: whether downstream execution gates, order routing, and market-impact effects preserve the same forward-edge ranking seen in offline bar replay.
- UNKNOWN: whether BTCUSDT control would suggest the same quantile family under the same date window if audited separately.

## Risks
- Risk: offline replay still excludes full execution-routing, fill-quality, and objective-stack behavior, so GO_FOR_TESTNET_RESTART is bounded to threshold-surface restart testing, not direct production promotion.
- Risk: sparse regime coverage can produce DEFAULT-only overlays that are operationally safer than overfit regime factors but may miss true per-regime opportunities.

## Next Action
- Next action: keep the emitted overlay in candidate-only status and investigate the failing guardrails before any restart or promotion decision.
