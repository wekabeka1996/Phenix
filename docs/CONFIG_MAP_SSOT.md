# Aurora Configuration — Single Source of Truth (SSOT)

This document is automatically generated from code-truth analytics.
It establishes the definitive map of configuration parameters, their sources, and their readers.

## Summary Statistics
- **Total Parameters (Inventory)**: 1603
- **Effective Parameters (Unique Paths)**: 783
- **Code-Referenced Parameters**: 504
- **Contract Violations (Overlaps)**: 57

## Freeze SSOT Rules (CFG-STRATEGY-SSOT-FREEZE-* + SIZING-MARGIN-FIRST-SSOT-02)

This repo is now **strategy-config SSOT** and **fail-closed**:

- `config/aurora/strategies.yaml` is the sole strategy assignment registry (mandatory).
- `config/aurora/strategies/<strategy>.yaml` is the SSOT for strategy policy:
  - `aurora` policy SSOT: `strategies/aurora.yaml` (`aurora.decision` + `aurora.assets`)
  - `mean_reversion` policy SSOT: `strategies/mean_reversion.yaml`
- `config/aurora/instruments.yaml` is the SSOT for per-symbol execution + sizing:
  - Exchange constraints: `instruments.<SYMBOL>.constraints.*` (tick/step/min_qty/min_notional)
  - Execution: `instruments.<SYMBOL>.execution.*` (isolated margin, target leverage, leverage policy)
  - Sizing: `instruments.<SYMBOL>.sizing.margin_pct` (margin-first sizing input)
- `config/aurora/trading.yaml` must contain **no strategy policy** (notably no `trading.decision`).
- `config/aurora/domains.yaml` must contain **no strategy policy** (domain mechanics only).
- `config/aurora/archive/*` is not loaded (historical reference only).

### Canonical Runtime Paths (No Shim)

- Aurora policy: `strategies.aurora.decision.*`
- Aurora per-symbol overrides: `strategies.aurora.assets.<SYMBOL>.*`
- Mean Reversion policy: `strategies.mean_reversion.*`
- Execution + sizing SSOT: `instruments.<SYMBOL>.execution.*` and `instruments.<SYMBOL>.sizing.margin_pct`
- Legacy runtime paths `trading.decision.*` and `aurora_instruments.*` are forbidden as strategy-policy sources.
- Legacy sizing sources are forbidden: `percent_equity`, `fixed_notional_usd`, `fixed_qty`, `risk_contract_v1`.

### Load / Merge Order

Effective config is constructed in this order:

1. `system.yaml` (stage=`system`)
2. `instruments.yaml` (stage=`instruments`)
3. `trading.yaml` (stage=`trading`)
4. `regime.yaml` (stage=`regime`)
5. `domains.yaml` (stage=`domains`)
6. `strategies.yaml` registry → loads `strategies/<id>.yaml` (stage=`strategy`)

### Migration Notes (What Moved Where)

- `trading.yaml::trading.decision.*` → `strategies/aurora.yaml::aurora.decision.*` (canonical runtime: `strategies.aurora.decision.*`)
- `aurora_instruments.yaml::{SYMBOL}.*` → `strategies/aurora.yaml::aurora.assets.{SYMBOL}.*` (canonical runtime: `strategies.aurora.assets.<SYMBOL>.*`)
- `trading.symbols_to_track` is derived from `strategies.yaml::assignments` keys unless explicitly set (and must match SSOT in strict mode).
- Legacy notional-first sizing was removed; margin-first sizing inputs now live in `instruments.<SYMBOL>.sizing.margin_pct` + `instruments.<SYMBOL>.execution.target_leverage`.

## Critical Overlaps (Action Required)
The following keys appear in multiple YAML files and MUST be moved to a single SSOT location.

| Key | Files | Severity |
| :--- | :--- | :--- |

## Effective Provenance Map
Tracing each parameter to its definitive source file.

| Parameter Path | Source File | Usage Count | Stage |
| :--- | :--- | :--- | :--- |
| `account_observer.poll_interval` | system.yaml | 1 | system |
| `aurora.description` | strategies/aurora.yaml | 0 | strategy |
| `aurora.enabled` | strategies/aurora.yaml | 0 | strategy |
| `aurora.type` | strategies/aurora.yaml | 0 | strategy |
| `aurora_instruments.BTCUSDT.allowed_regimes` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.cooldown_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.ema_clamp` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.enabled` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.execution` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.exit.max_hold_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.exit.sl_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.max_risk_score` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.position_mode` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_sizing.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_sizing.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_sizing.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_thresholds.DEFAULT` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_thresholds.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_thresholds.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.regime_thresholds.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.side_bias.penalty_factor` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.side_bias.target_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.side_bias.window_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.signal_threshold` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.take_profit.partial_exit_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.take_profit.tp_high_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.take_profit.tp_low_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.timeframe_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.trailing_stop.activation_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.trailing_stop.enabled` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.trailing_stop.min_update_interval_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.trailing_stop.trail_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.delta_price` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.depth_imbalance` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.ema` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.liquidity` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.macro` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.obi` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.tfi` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.volatility` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.BTCUSDT.weights.volume` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.allowed_regimes` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.cooldown_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.ema_clamp` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.enabled` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.execution` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.exit.max_hold_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.exit.sl_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.max_risk_score` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.position_mode` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_sizing.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_sizing.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_sizing.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_thresholds.DEFAULT` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_thresholds.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_thresholds.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.regime_thresholds.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.side_bias.penalty_factor` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.side_bias.target_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.side_bias.window_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.signal_threshold` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.take_profit.partial_exit_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.take_profit.tp_high_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.take_profit.tp_low_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.timeframe_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.trailing_stop.activation_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.trailing_stop.enabled` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.trailing_stop.min_update_interval_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.trailing_stop.trail_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.delta_price` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.depth_imbalance` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.ema` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.liquidity` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.macro` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.obi` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.tfi` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.volatility` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.DOGEUSDT.weights.volume` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.allowed_regimes` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.cooldown_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.ema_clamp` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.enabled` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.execution` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.exit.max_hold_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.exit.sl_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.max_risk_score` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.position_mode` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_sizing.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_sizing.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_sizing.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_thresholds.DEFAULT` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_thresholds.HIGH_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_thresholds.LOW_VOLATILITY` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.regime_thresholds.MEAN_REVERSION` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.side_bias.penalty_factor` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.side_bias.target_ratio` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.side_bias.window_sec` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.signal_threshold` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.take_profit.partial_exit_pct` | aurora_instruments.yaml | 0 | instruments |
| `aurora_instruments.ETHUSDT.take_profit.tp_high_ratio` | aurora_instruments.yaml | 0 | instruments |

## Code Usage Details
Mapping parameters to their implementation readers.

### `AURORA_ALERTS_SLACK_WEBHOOK_URL`
- `[apps/reference/telemetry/alerts.py:80]` .get("AURORA_ALERTS_SLACK_WEBHOOK_URL")

### `DEFAULT`
- `[apps/reference/domains/decision_making/decision_making.py:2512]` .get("DEFAULT")

### `LOT_SIZE`
- `[apps/reference/adapters/binance_adapter.py:716]` .get("LOT_SIZE")

### `MINQ`
- `[apps/reference/adapters/binance_adapter.py:716]` .get("MINQ")

### `__default__`
- `[apps/reference/main.py:252]` .get("__default__")
- `[apps/reference/domains/position_tracking/position_tracking.py:976]` .get("__default__")

### `a`
- `[apps/reference/domains/market_data/market_data_connector.py:242]` .get("a")
- `[apps/reference/domains/market_data/worker.py:368]` .get("a")

### `absorption`
- `[apps/reference/domains/risk_management/risk_management.py:263]` .get("absorption")

### `account_observer.poll_interval`
- `[apps/reference/domains/account_balance/account_connector.py:51]` config.account_observer.poll_interval

### `ack_ttl_ms`
- `[apps/reference/domains/execution_position/watchdog.py:56]` config["ack_ttl_ms"]

### `activation_profit_atr_k`
- `[apps/reference/domains/execution_position/fsm_manage.py:298]` .get("activation_profit_atr_k")

### `alert_cooldown_minutes`
- `[apps/reference/monitoring/performance_monitor.py:255]` config.alert_cooldown_minutes

### `allow_close_to_close_atr`
- `[apps/reference/domains/regime_detector/regime_detector.py:88]` cfg.allow_close_to_close_atr

### `allowed_regimes`
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:325]` config.allowed_regimes
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:325]` config.allowed_regimes
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:257]` config.allowed_regimes
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:257]` config.allowed_regimes
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:271]` config.allowed_regimes
- ... and 1 more locations

### `anchor`
- `[apps/reference/domains/market_data/proxy.py:223]` .get("anchor")
- `[apps/reference/domains/feature_engineering/feature_engineering.py:180]` .get("anchor")

### `api_key`
- `[apps/reference/domains/account_balance/account_connector.py:68]` config.api_key
- `[apps/reference/domains/account_observer/account_observer.py:70]` config.api_key
- `[apps/reference/domains/execution_position/fsm.py:984]` config.api_key

### `api_secret`
- `[apps/reference/domains/account_balance/account_connector.py:69]` config.api_secret
- `[apps/reference/domains/account_observer/account_observer.py:71]` config.api_secret
- `[apps/reference/domains/execution_position/fsm.py:985]` config.api_secret

### `arming.max_attempts`
- `[apps/reference/domains/decision_making/decision_making.py:231]` cfg.arming.max_attempts

### `arming.require_regime_warmup`
- `[apps/reference/domains/decision_making/decision_making.py:229]` cfg.arming.require_regime_warmup

### `arming.retry_backoff_ms`
- `[apps/reference/domains/decision_making/decision_making.py:230]` cfg.arming.retry_backoff_ms

### `ask`
- `[apps/reference/main.py:1305]` .get('ask')
- `[apps/reference/domains/market_data/proxy.py:194]` .get("ask")

### `ask_size`
- `[apps/reference/domains/market_data/proxy.py:197]` .get("ask_size")

### `asset`
- `[apps/reference/domains/account_balance/account_connector.py:130]` .get("asset")
- `[apps/reference/domains/account_balance/account_connector.py:302]` .get("asset")
- `[apps/reference/domains/position_tracking/position_tracking.py:567]` .get("asset")

### `assets`
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:186]` config.assets
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:194]` config.assets
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:200]` config.assets
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:201]` config.assets
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:202]` config.assets
- ... and 2 more locations

### `assets.get`
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:260]` config.assets.get
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:587]` config.assets.get

### `assets.items`
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:187]` config.assets.items

### `assignments`
- `[apps/reference/config_loader.py:346]` .get("assignments")
- `[apps/reference/config_loader.py:909]` .get("assignments")

### `atr_period`
- `[apps/reference/domains/regime_detector/regime_detector.py:86]` cfg.atr_period

### `atr_sma_length`
- `[apps/reference/domains/regime_detector/regime_detector.py:87]` cfg.atr_sma_length

### `atr_window`
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:356]` config.atr_window
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:360]` config.atr_window
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:246]` config.atr_window
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:246]` cfg.atr_window

### `aurora_instruments`
- `[apps/reference/config_loader.py:382]` .get("aurora_instruments")
- `[apps/reference/config_loader.py:406]` config["aurora_instruments"]
- `[apps/reference/config_loader.py:409]` .get("aurora_instruments")
- `[apps/reference/config_loader.py:411]` config["aurora_instruments"]
- `[apps/reference/config_loader.py:413]` config["aurora_instruments"]
- ... and 8 more locations

### `aurora_optimal`
- `[apps/research/aurora_optuna/validate_feb_2024.py:26]` config['aurora_optimal']
- `[apps/research/aurora_optuna/validate_feb_2024.py:33]` config['aurora_optimal']
- `[apps/research/aurora_optuna/validate_feb_2024.py:40]` config['aurora_optimal']
- `[apps/research/aurora_optuna/validate_feb_2024.py:47]` config['aurora_optimal']

### `auto`
- `[apps/reference/domains/execution_position/fsm_manage.py:127]` cfg.auto

### `axes`
- `[apps/reference/domains/decision_making/decision_making.py:1704]` .get("axes")

### `backoff_factor`
- `[apps/reference/main.py:144]` config.backoff_factor

### `backoff_ms`
- `[apps/reference/domains/execution_position/exposure_guard.py:221]` config['backoff_ms']

### `balance`
- `[apps/reference/domains/position_tracking/position_tracking.py:575]` .get("balance")
- `[apps/reference/domains/position_tracking/position_tracking.py:1158]` .get("balance")

### `bar_gating.bar_ms`
- `[apps/reference/domains/decision_making/decision_making.py:246]` cfg.bar_gating.bar_ms

### `bar_gating.enable`
- `[apps/reference/domains/decision_making/decision_making.py:245]` cfg.bar_gating.enable

### `bar_seconds`
- `[apps/research/aurora_optuna/validate_feb_2024.py:147]` config['bar_seconds']

### `base_probability`
- `[apps/reference/domains/decision_making/decision_making.py:2810]` cfg.base_probability
- `[apps/reference/domains/decision_making/decision_making.py:2811]` cfg.base_probability

### `batch_cancel_limit`
- `[apps/reference/domains/execution_position/fsm.py:2064]` cfg["batch_cancel_limit"]

### `bb_num_std`
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:352]` config.bb_num_std
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:245]` config.bb_num_std
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:245]` cfg.bb_num_std
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:267]` config.bb_num_std

### `bb_window`
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:348]` config.bb_window
- `[apps/reference/domains/feature_engineering/mean_reversion_strategy.py:351]` config.bb_window
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:244]` config.bb_window
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:244]` cfg.bb_window
- `[apps/reference/domains/decision_making/mean_reversion_handler.py:266]` config.bb_window
- ... and 1 more locations

### `behavior_fsm.enable`
- `[apps/reference/domains/decision_making/decision_making.py:250]` cfg.behavior_fsm.enable

### `behavior_fsm.high_vol_multiplier`
- `[apps/reference/domains/decision_making/decision_making.py:252]` cfg.behavior_fsm.high_vol_multiplier

### `behavior_fsm.low_vol_multiplier`
- `[apps/reference/domains/decision_making/decision_making.py:253]` cfg.behavior_fsm.low_vol_multiplier

### `bid`
- `[apps/reference/main.py:1305]` .get('bid')
- `[apps/reference/domains/market_data/proxy.py:193]` .get("bid")

### `bid_size`
- `[apps/reference/domains/market_data/proxy.py:196]` .get("bid_size")

### `binance_api`
- `[apps/reference/config_loader.py:489]` config["binance_api"]
- `[apps/reference/domains/account_balance/account_connector.py:55]` config.binance_api
- `[apps/reference/domains/account_observer/account_observer.py:68]` config.binance_api
- `[apps/reference/domains/execution_position/fsm.py:970]` config.binance_api

### `binance_api.live`
- `[apps/reference/domains/market_data/market_data_connector.py:107]` config.binance_api.live
