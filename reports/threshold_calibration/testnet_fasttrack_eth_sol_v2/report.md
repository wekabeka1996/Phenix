# Aurora Threshold Calibration Report

## Verdict
- NO_GO

## Scope
- Objective: calibrate only live per-symbol Aurora threshold surface for assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds.
- Non-goals: no neutral_threshold tuning, no weight tuning, no cooldown/reentry/holding-period changes, no writeback into base YAML.
- Symbols: ETHUSDT, SOLUSDT
- Date window: 2026-02-08 through 2026-03-20 inclusive
- Recorder timeframe: 300s
- Validation holdout: trailing 5 unique eligible recorder dates

## Runtime Truth Anchors
- FACT: active Aurora scoring path is QuadraticScoringKernel with DangerZone -> Context -> Memory shield cascade.
- FACT: this V2 replay reuses live RegimeDetector, QuadraticScoringKernel, live side-bias parameters, and live shield config.
- FACT: per-symbol signal_threshold.value and per-symbol regime_thresholds are the only tuned surfaces emitted by this tool.
- FACT: feature logs are audited for schema evidence, but recorder is the only auditable timestamp backbone because sampled feature-log keys expose no explicit timestamp field.

## Dataset Audit
- Config timeframe_sec: 300

### ETHUSDT
- Recorder bars loaded: 10088
- Validation split starts on: 2026-03-16
- Feature log: exists=True, size_mb=324.41, sampled_lines=20, has_timestamp_fields=False
- Sampled feature-log keys: ['absorption', 'delta_price', 'depth_imbalance', 'ema_bias', 'large_trade_imbalance', 'liquidity_kappa', 'macro_resid', 'macro_sync', 'obi', 'price', 'spread_bps', 'tfi', 'volatility_state', 'volume_spike', 'volume_zscore']
- WARNING: Sampled feature-log keys for ETHUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.

### SOLUSDT
- Recorder bars loaded: 10085
- Validation split starts on: 2026-03-16
- Feature log: exists=True, size_mb=320.71, sampled_lines=20, has_timestamp_fields=False
- Sampled feature-log keys: ['absorption', 'delta_price', 'depth_imbalance', 'ema_bias', 'large_trade_imbalance', 'liquidity_kappa', 'macro_resid', 'macro_sync', 'obi', 'price', 'spread_bps', 'tfi', 'volatility_state', 'volume_spike', 'volume_zscore']
- WARNING: Sampled feature-log keys for SOLUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.

## Candidate Search Guardrails
- min_activation_rate=0.0200
- max_activation_rate=0.3500
- max_daily_activation_rate=0.4500
- min_forward_edge_bps=0.00
- min_active_bars=8
- quantile_grid=[0.55, 0.6, 0.65, 0.7, 0.75]

## Symbol Evaluations

### ETHUSDT
| split | eligible_bars | active_bars | activation_rate | buy_count | sell_count | max_daily_activation | mean_fwd_1_bps | mean_fwd_3_bps | hit_rate_1 | hit_rate_3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current/train | 537 | 0 | 0.00% | 0 | 0 | 0.00% | - | - | - | - |
| current/validation | 795 | 0 | 0.00% | 0 | 0 | 0.00% | - | - | - | - |
- No candidate cleared train-time guardrails.
- Symbol warnings:
  - Sampled feature-log keys for ETHUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.
  - No V2 candidate for ETHUSDT cleared train-time guardrails across quantile grid [0.55, 0.6, 0.65, 0.7, 0.75].

### SOLUSDT
| split | eligible_bars | active_bars | activation_rate | buy_count | sell_count | max_daily_activation | mean_fwd_1_bps | mean_fwd_3_bps | hit_rate_1 | hit_rate_3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current/train | 540 | 0 | 0.00% | 0 | 0 | 0.00% | - | - | - | - |
| current/validation | 792 | 0 | 0.00% | 0 | 0 | 0.00% | - | - | - | - |
- No candidate cleared train-time guardrails.
- Symbol warnings:
  - Sampled feature-log keys for SOLUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.
  - No V2 candidate for SOLUSDT cleared train-time guardrails across quantile grid [0.55, 0.6, 0.65, 0.7, 0.75].

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
