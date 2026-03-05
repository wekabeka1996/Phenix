# Forensics: regime starvation, OBI/TFI, flip exits, risk gate (2026-03-03)

## Executive summary
- DOGE assigned to mean_reversion only: TRUE (config/aurora/strategies.yaml).
- DOGE regime gating (analyzed period): signals=269, neutral_regime_not_flat=1902, neutral_regime_not_allowed=0, total_bars=4756.
  - Regime-gated neutral share: 40.0% of bars.
- DOGE last-24h (available bars): signals=10, neutral_regime_not_flat=128, neutral_regime_not_allowed=0, total_bars=223.
- OBI/TFI sign: CONFIRMED (positive = buy pressure; formulas in feature_engineering.py).
- DOGE MR sample size: 5 signals in logs/domain_mean_reversion.log.
- SOL reduce-only closes found (order_log rid *-close): 2.
- SOL flip claim ("100% favorable") and risk gate binding are evaluated in sections 3.2 and 4.4 with computed percentages.

## Inputs used
- Configs: `config/aurora/strategies.yaml`, `config/aurora/strategies/mean_reversion.yaml`, `config/aurora/strategies/aurora.yaml`, `config/aurora/regime.yaml`, `config/aurora/domains.yaml`, `config/aurora/trading.yaml`
- Logs/datasets: `logs/order_log_v1.jsonl`, `logs/domain_execution_position.log`, `logs/domain_feature_engineering.log`, `logs/domain_mean_reversion.log`, `logs/mean_reversion/bars_180s.tsv`, `logs/mean_reversion/bars_300s.tsv`, `logs/domain_regime_detector.log`, `logs/aurora_core.log.*`, `logs/domain_decision_making.log.*`
- Verb registry: `apps/reference/dictionaries/verb_registry_v1.yaml`

## 1) DOGE starvation (regime gating)
### 1.1 Assignment: DOGE -> mean_reversion only
- Strategy registry SSOT: config/aurora/strategies.yaml:38 (DOGE) and config/aurora/strategies.yaml:39 (assigned mean_reversion)
- Runtime strategy tag (execution_position): logs/domain_execution_position.log:6272 and logs/domain_execution_position.log:7056

### 1.2 Mean Reversion allowed_regimes
- DOGE block: config/aurora/strategies/mean_reversion.yaml:92
- allowed_regimes: config/aurora/strategies/mean_reversion.yaml:111

### 1.3 Exact regime names
- LOW_VOLATILITY (not LOW_VOL): apps/reference/domains/feature_engineering/regime_mapping.py:117
- HIGH_VOLATILITY: apps/reference/domains/feature_engineering/regime_mapping.py:113

### 1.4 Reason codes: requested vs actual
- Task requested: REGIME_NOT_ALLOWLISTED
- MR neutral mapping in code: apps/reference/domains/decision_making/mean_reversion_handler.py:948 and apps/reference/domains/decision_making/mean_reversion_handler.py:950 (`regime_not_flat:*` -> `REGIME_MAPPING_NONE`, `regime_not_allowed:*` -> `REGIME_NOT_ALLOWED`)

### 1.5 Observed DOGE regimes + regime-gate rejections (from MR bars TSV)
- Latest bar (UTC): `2026-03-03 09:50:59`
- Last-24h window start (UTC): `2026-03-02 09:50:59`

**Last 24h (available in bars TSVs)**
- Bars: 223
- Signals: {'NEUTRAL': 213, 'LONG': 7, 'SHORT': 3}
- Regime-gate neutral counts: {'REGIME_MAPPING_NONE': 128}
- Top `regime_not_flat:*` raw regime at rejection time: `UNCERTAIN` (count=106)
- Regime values (top): UNCERTAIN=114, MEAN_REVERSION=47, LOW_VOLATILITY=30, HIGH_VOLATILITY=22, FLAT_NORMAL=8, FLAT_LOW=1, FLAT_HIGH=1

**Analyzed period (all available DOGE bars in `bars_300s.tsv` + `bars_180s.tsv`)**
- Bars: 4756
- Signals: {'NEUTRAL': 4487, 'LONG': 159, 'SHORT': 110}
- Regime-gate neutral counts: {'REGIME_MAPPING_NONE': 1902}
- Top `regime_not_flat:*` raw regime at rejection time: `UNCERTAIN` (count=1576)
- Regime values (top): UNCERTAIN=1610, MEAN_REVERSION=1325, LOW_VOLATILITY=1221, HIGH_VOLATILITY=327, FLAT_LOW=134, FLAT_NORMAL=108, FLAT_HIGH=27, TREND_UP=4
- Raw regimes seen in `regime_not_flat:*`: `HIGH_VOLATILITY, TREND_UP, UNCERTAIN`

## 2) OBI/TFI sign conventions + DOGE MR losses
### 2.1 OBI/TFI computation + sign
- OBI: apps/reference/domains/feature_engineering/feature_engineering.py:880 => positive = bid-dominant (buy pressure)
- TFI: apps/reference/domains/feature_engineering/feature_engineering.py:888 => positive = buy-volume dominant (buy pressure)

### 2.2 DOGE MR signals: entry features + outcome proxy
- Outcome proxy: forward return in position direction at +3/+6 MR bars (180s bars) from `logs/mean_reversion/bars_180s.tsv` (bar close = signal timestamp).
- Entry OBI/TFI snapshot: last `Calculated features for DOGEUSDT` within 60s before signal from `logs/domain_feature_engineering.log`.

- Signals found: 5

| ts_utc | side | pct_b | obi | tfi | delta_price | ret+3 | ret+6 | mfe(6) | mae(6) | |tfi|>0.3 | tfi_align_breakout |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| 2026-03-03 07:17:59 | SELL | 1.045 | 0.317 | -0.396 | -0.000010 | -0.17% | -0.06% | 0.05% | -0.28% | True | True |
| 2026-03-03 07:29:59 | SELL | 0.971 | -0.845 | 0.096 | 0.000000 | 0.02% | 0.89% | 0.89% | -0.09% | False |  |
| 2026-03-03 07:47:59 | BUY | -0.056 | 0.932 | -0.569 | 0.000020 | 0.18% | 0.29% | 0.29% | -0.04% | True | False |
| 2026-03-03 08:14:59 | BUY | 0.045 | 0.997 | -0.729 | -0.000030 | 0.06% | -0.27% | 0.28% | -0.38% | True | True |
| 2026-03-03 08:38:59 | BUY | -0.042 | 0.538 | -0.207 | 0.000000 | -0.63% | -0.86% | 0.03% | -0.97% | False |  |

- Losing (ret+6 < 0): 3 / 5

### 2.3 Veto test: `abs(TFI) > 0.3`
- Trades with TFI snapshot: 5 / 5
- Would veto: 3; would allow: 2
- Win rate proxy (ret+6>0): all=40.0%, allowed=50.0%, vetoed=33.3%
### 2.4 Top losing DOGE MR trades (by ret+6 proxy)
| rank | ts_utc | side | pct_b | obi | tfi | delta_price | abs(tfi)>0.3 | tfi_align_breakout | ret+6 |
|---:|---:|:---:|---:|---:|---:|---:|:---:|:---:|---:|
| 1 | 2026-03-03 08:38:59 | BUY | -0.042 | 0.538 | -0.207 | 0.000000 | False |  | -0.86% |
| 2 | 2026-03-03 08:14:59 | BUY | 0.045 | 0.997 | -0.729 | -0.000030 | True | True | -0.27% |
| 3 | 2026-03-03 07:17:59 | SELL | 1.045 | 0.317 | -0.396 | -0.000010 | True | True | -0.06% |

## 3) SOL flip premature exits
### 3.1 Close identification
- Aurora timeframe (bars): config/aurora/strategies/aurora.yaml:15 (timeframe_sec: 300)
- DEC/CLOSE verb exists: apps/reference/dictionaries/verb_registry_v1.yaml:40
- Reduce-only closes observed (execution_position): logs/domain_execution_position.log count=2 (first lines: 5689, 7375)

### 3.2 SOL reduce-only closes: post-close return + MFE/MAE (5m bars)
- Close intents in `logs/order_log_v1.jsonl`: 2

| close_ts_utc | rid (order_log line) | close_side | position_closed | ret+3bars | ret+6bars | mfe(6) | mae(6) |
|---:|:---|:---:|:---:|---:|---:|---:|---:|
| 2026-03-03 06:55:00 | aurora_SOLUSDT_1772520900200-close (`logs/order_log_v1.jsonl:11`) | BUY | SHORT | 0.01% | -0.33% | 0.12% | -0.62% |
| 2026-03-03 08:00:00 | aurora_SOLUSDT_1772524800308-close (`logs/order_log_v1.jsonl:50`) | SELL | LONG | -0.49% | -0.75% | 0.20% | -0.84% |

- Claim check: `100% favorable after close` at +6 bars => 0/2 favorable (0.0%).
  - Verdict: FALSE
### 3.3 Hold-until-TP/SL proxy after close (uses last TP/SL before close)
- Source TP/SL: most recent `TP/SL_RESOLVED` for SOL before the close in `logs/domain_execution_position.log`.
- Proxy: after close, scan next 30 minutes of `logs/domain_feature_engineering.log` SOL prices and report first hit (TP/SL/BOTH).

- No TP/SL_RESOLVED records matched to SOL closes (cannot compute proxy).

## 4) Risk gate (risk_score)
### 4.1 Configured threshold + cap
- Threshold SSOT: config/aurora/domains.yaml:331 (domains.risk_management.trading_allowed_thresholds.max_risk_score: 0.96)
- Cap/clamp: apps/reference/domains/risk_management/risk_management.py:327 (risk_score clamped to [0, 1])

### 4.2 Observed risk_score distribution (RISK_RX)
- RISK_RX samples parsed: 40928

| stat | value |
|---:|---:|
| min | 0.0000 |
| median | 0.2266 |
| p90 | 0.3650 |
| p99 | 0.4534 |
| max | 0.5785 |

### 4.3 risk_score around trade intents (accepted vs rejected)
- DecisionMaking ORDER_INTENTs: 30
- Intents with matched risk_score (<=120s old): 14
- Accepted (ORDER_PLACED): 7
- Rejected (ORDER_REJECTED): 14
- Accepted risk_score min/med/p90/p99/max: 0.058/0.159/0.279/0.281/0.282
- Rejected risk_score min/med/p90/p99/max: 0.117/0.214/0.292/0.314/0.317

### 4.4 Percentile-based threshold recommendation
- To reject ~5% of intents (by historical accepted distribution): set `max_risk_score` ? p95=0.280
- To reject ~1% of intents: set `max_risk_score` ? p99=0.281
- Current `0.96` is non-binding on this dataset (p99=0.281).

## Appendix: Config/code excerpts (line-numbered)

### `config/aurora/strategies.yaml`
```text
   28   # SOL: Aurora + Mean Reversion
   29   SOLUSDT:
   30     - aurora
   31 
   32   # BTC: Aurora (re-enabled 2026-03-03, testnet/hybrid)
   33   # Calibrated weights applied: tools/calibrate_aurora_signal_weights.py 2026-03-03
   34   BTCUSDT:
   35     - aurora
   36 
   37   # DOGE: MR-only (champion MR asset, +$387 in research)
   38   DOGEUSDT:
   39     - mean_reversion
   40 
   41   # XRP: MR-only (MR silver medal, +$121)
   42   XRPUSDT: []
```

### `config/aurora/strategies/mean_reversion.yaml`
```text
   88   # Source: trading.yaml optimization (December 2025)
   89 
   90   assets:
   91     # --- DOGE (CHAMPION ðŸ¥‡) ---
   92     DOGEUSDT:
   93       enabled: true
   94       position_mode: "STRICT"
   95 
   96       # P1: Active Leverage Management
   97       leverage:
   98         target: 10
   99         mode: "ISOLATED"
  100 
  101       strategy:
  102         bb_window: 20
  103         bb_num_std: 2.1
  104         min_bb_width: 0.005  # (min_vol_atr from report)
  105         entry_threshold: 0.05
  106         # Exit parameters
  107         sl_atr_mult: 1.5     # Base, overridden below
  108         tp_to_mid: false     # False for outer band target
  109         cooldown_sec: 660
  110       # Regime Gating - DOGE champion (+$387) - includes FLAT_HIGH for "Ð¶Ð¸Ñ€Ð½Ñ–" ÑƒÐ³Ð¾Ð´Ð¸
  111       allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
  112 
  113     # --- BTC (BRONZE ðŸ¥‰) ---
  114     BTCUSDT:
  115       enabled: true
  116       position_mode: "STRICT"
  117 
```

### `config/aurora/domains.yaml`
```text
  318     # TASK-ZOMBIE-FIX: Removed bounds (dead, feature_sanity.feature_bounds is SSOT)
  319 
  320 risk_management:
  321   # Commit 6: Disable placeholder absorption penalty by default
  322   use_absorption_penalty: true
  323   absorption_dp_cap_pct: 0.02  # SSOT cap for toxicity normalization (used only when use_absorption_penalty=true)
  324   risk_score_weights:
  325     delta_price_pct: 0.1
  326     obi: 0.3
  327     tfi: 0.3
  328     absorption_inverse: 0.3
  329 
  330   trading_allowed_thresholds:
  331     max_risk_score: 0.96  # Increased by 20% to allow more trading
  332 
  333   validation:
  334     total_weight_min: 0.5
  335     total_weight_max: 2.0
  336 
  337 position_tracking:
```

### `config/aurora/strategies/aurora.yaml`
```text
   10 aurora:
   11   enabled: true
   12   # SCORCHED-EARTH-2026-01-27: legacy_tick_path_enabled DELETED from schema
   13   type: bar_driven
   14   description: "Bar-driven multi-signal alpha strategy (5m basis) with regime awareness"
   15   timeframe_sec: 300
   16 
   17   # ORDER-POLICY-01: Entry order execution policy (SSOT for strategy)
   18   # LIMIT entries require explicit tif. No silent fallbacks.
   19   execution:
   20     entry_order_type: "LIMIT"   # MUST be one of: LIMIT, MARKET
   21     entry_tif: "GTX"            # MUST be set for LIMIT. One of: GTC, GTX, IOC, FOK
   22 
   23   # DM-SAFETY-BYPASSES-P1: Explicit safety gates control (fail-closed if missing)
   24   # Aurora is trend-following â†’ directional sanity and price motion gates APPLY.
```

### `apps/reference/domains/feature_engineering/feature_engineering.py`
```text
  874             # ================================================================
  875             # BASE FEATURES (always computed)
  876             # ================================================================
  877 
  878             # OBI (Order Book Imbalance) [-1, 1]
  879             depth = bid_size + ask_size
  880             obi = (bid_size - ask_size) / \
  881                 depth if depth > 0 else decimal.Decimal(0)
  882 
  883             # EP-01.1: Cache OBI for bar close snapshot
  884             self._last_obi[symbol] = obi
  885 
  886             # TFI (Trade Flow Imbalance) [-1, 1]
  887             total_flow = buy_volume + sell_volume
  888             tfi = (buy_volume - sell_volume) / \
  889                 total_flow if total_flow > 0 else decimal.Decimal(0)
  890 
  891             # Delta Price (with spike filter)
  892             delta_price = (
  893                 price - prev_price
  894                 if time_diff < self.cfg.delta_price_spike_filter_ms
  895                 else decimal.Decimal(0)
  896             )
  897 
  898             # Liquidity Kappa [kappa_min, kappa_max]
```

### `apps/reference/domains/feature_engineering/regime_mapping.py`
```text
  103     thresholds = thresholds or DEFAULT_THRESHOLDS
  104     
  105     # Normalize regime string
  106     regime_upper = regime.upper().strip() if regime else ""
  107     
  108     # Skip trending markets - not suitable for mean reversion
  109     if regime_upper in ("TREND_UP", "TREND_DOWN"):
  110         return None
  111     
  112     # Skip high volatility - too risky for MR
  113     if regime_upper == "HIGH_VOLATILITY":
  114         return None
  115     
  116     # LOW_VOLATILITY â†’ FLAT_LOW (tight bands, small moves)
  117     if regime_upper == "LOW_VOLATILITY":
  118         return FlatRegime.FLAT_LOW
  119     
  120     # MEAN_REVERSION â†’ classify by ATR%
  121     if regime_upper == "MEAN_REVERSION":
  122         if atr_pct is not None:
  123             return thresholds.classify(atr_pct)
  124         return None
  125     
  126     # P0 FIX: UNCERTAIN â†’ None (fail-closed)
  127     # MR must NOT trade when regime is uncertain/uninitialized.
  128     # This prevents trading before regime_detector has established the regime.
  129     # If explicit UNCERTAIN trading is needed, use a separate opt-in config flag.
  130     if regime_upper == "UNCERTAIN":
  131         return None
  132     
  133     # Unknown regime â†’ skip
  134     return None
  135 
  136 
  137 def is_flat_regime(regime: str) -> bool:
```
