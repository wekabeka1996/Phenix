# MR Defaults, Fallbacks, and Hardcoded-Policy Matrix

> **Scope:** Mean Reversion strategy — all config surfaces, runtime behaviors, and code-level policies.
> **Date:** 2026-03-31
> **Source truth:** Code at HEAD of Phenix_v2 branch.

## Legend

| Category | Meaning |
|---|---|
| **YAML default** | Value declared in `mean_reversion.yaml`; operator-configurable |
| **Pydantic default** | Default in Pydantic `Field(default=...)` or `@dataclass` field; operator can override via YAML |
| **Required / no default** | Pydantic `Field()` with no default — YAML must supply it or validation fails |
| **Runtime fallback** | Code branch that substitutes a safe value when optional data is absent at runtime |
| **Graceful degradation** | System continues operating with reduced capability (not an error) |
| **Fail-closed** | Missing/invalid data → operation blocked unconditionally (safety contract) |
| **Hardcoded policy** | Logic baked into code, not exposed as a YAML knob |
| **Dormant default** | Config exists on disk but inactive because `enabled: false` or strategy unassigned |

---

## Core Strategy Parameters

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `enabled` | YAML `mean_reversion.enabled` | field | `true` | **YAML default** | Handler `_parse_config()` | Global kill-switch; `false` → handler inactive | mean_reversion.yaml:17 |
| `timeframe_sec` | YAML `mean_reversion.timeframe_sec` | field | `300` (5m) | **Required / no default** | Handler gating | CMD with wrong `tf_sec` silently skipped | config_models.py:812 |
| `bb_window` | YAML `strategy.bb_window` | field | `20` | **Required / no default** | Strategy BB computation | Window for SMA/StdDev in Bollinger Bands | config_models.py:393 |
| `bb_num_std` | YAML `strategy.bb_num_std` | field | `2.0` | **Required / no default** | Strategy BB computation | Multiplier for band width | config_models.py:394 |
| `atr_window` | YAML `strategy.atr_window` | field | `14` | **Required / no default** | Strategy ATR/stop computation | ATR smoothing window | config_models.py:395 |
| `rsi_window` | YAML `strategy.rsi_window` | field | `14` | **Required / no default** | Strategy RSI computation | RSI smoothing window | config_models.py:396 |
| `entry_threshold` | YAML `strategy.entry_threshold` | field | `0.115` | **Required / no default** | Strategy `_evaluate_signal` | %B threshold for symmetric entry | config_models.py:401 |
| `rsi_oversold` | YAML `strategy.rsi_oversold` | field | `30` | **Required / no default** | Strategy confidence bonus | RSI level for oversold confirmation | config_models.py:402 |
| `rsi_overbought` | YAML `strategy.rsi_overbought` | field | `70` | **Required / no default** | Strategy confidence bonus | RSI level for overbought confirmation | config_models.py:403 |
| `min_bars` | YAML `strategy.min_bars` | field | `25` | **Required / no default** | Strategy warmup | Bars needed before any signal | config_models.py:405 |
| `min_bb_width` | YAML `strategy.min_bb_width` | field | `0.001` | **Required / no default** | Strategy width filter | Blocks signals in dead markets | config_models.py:406 |
| `max_bb_width` | YAML `strategy.max_bb_width` | field | `0.15` | **Required / no default** | Strategy width filter | Blocks signals in extreme volatility | config_models.py:407 |
| `sl_atr_mult` | YAML `strategy.sl_atr_mult` | field | `1.5` | **Required / no default** | Strategy stop computation | Base ATR multiplier for SL | config_models.py:409 |
| `tp_to_mid` | YAML `strategy.tp_to_mid` | field | `true` | **Required / no default** | Strategy TP target | `true` → mid BB; `false` → opposite band | config_models.py:410 |
| `cooldown_sec` | YAML `strategy.cooldown_sec` | field | `60` | **Required / no default** | Strategy anti-churn | Seconds between actionable signals | config_models.py:411 |
| `confidence_base` | YAML `strategy.confidence_base` | field | `0.5` | **Pydantic default** | Strategy scoring | Base confidence scalar | config_models.py:414 |
| `confidence_bb_slope` | YAML `strategy.confidence_bb_slope` | field | `2.0` | **Pydantic default** | Strategy scoring | BB distance sensitivity | config_models.py:418 |
| `confidence_rsi_bonus` | YAML `strategy.confidence_rsi_bonus` | field | `0.2` | **Pydantic default** | Strategy scoring | RSI confirmation bonus | config_models.py:422 |
| `allowed_regimes` | YAML `mean_reversion.allowed_regimes` | field | `["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]` | **Required / no default** | Strategy regime gate | Strict allowlist; empty = allow nothing | config_models.py:828 |
| `regime_thresholds.high_vol_pct` | YAML | field | `0.003` | **Required / no default** | Regime mapping | ATR% above this = FLAT_HIGH | config_models.py:435 |
| `regime_thresholds.low_vol_pct` | YAML | field | `0.001` | **Required / no default** | Regime mapping | ATR% below this = FLAT_LOW | config_models.py:436 |
| `score_multiplier` | Pydantic only | field | `1.0` | **Pydantic default** | Handler scoring | Not in YAML; default always used | config_models.py:399 |

## Regime Sizing

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `regime_sizing.FLAT_LOW.sizing_mult` | YAML | field | `0.8` | **Required / no default** | Handler signal emission | Position size multiplier | mean_reversion.yaml:304 |
| `regime_sizing.FLAT_LOW.stop_mult` | YAML | field | `1.0` | **Required / no default** | Strategy SL computation | Stop multiplier | mean_reversion.yaml:305 |
| `regime_sizing.FLAT_LOW.target_mult` | YAML | field | `0.8` | **Required / no default** | Strategy TP computation | Target multiplier | mean_reversion.yaml:306 |
| `regime_sizing.FLAT_NORMAL.*` | YAML | field | `1.0 / 1.0 / 1.0` | **Required / no default** | Strategy SL/TP | Standard multipliers | mean_reversion.yaml:308-311 |
| `regime_sizing.FLAT_HIGH.*` | YAML | field | `0.7 / 1.5 / 1.2` | **Required / no default** | Strategy SL/TP | Wider stops, larger targets | mean_reversion.yaml:313-316 |

## Execution and Safety

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `execution.entry_order_type` | YAML | field | `"MARKET"` | **Required / no default** | Signal emission | Order type in signal payload | mean_reversion.yaml:30 |
| `execution.entry_tif` | YAML | field | `null` | field | Signal emission | Time-in-force (ignored for MARKET) | mean_reversion.yaml:31 |
| `safety_gates.enabled` | YAML | field | `false` | **Required / no default** | Handler safety gates | MR is counter-trend → gates off | mean_reversion.yaml:37 |
| `safety_gates.system_stress_policy` | YAML | field | `"off"` | **Pydantic default** | Handler Gate 0.5 | Off = bypass stress gate | config_models.py:782 |

## Per-Asset Override Precedence

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `assets.<SYM>.enabled` | YAML per-asset | field | varies | **Required / no default** | Handler `_parse_config()` | Per-asset kill-switch | config_models.py:727 |
| `assets.<SYM>.strategy.*` | YAML per-asset | field | all `Optional[None]` | **Runtime fallback** | Handler config merge | `None` → use global strategy value | config_models.py:669-715 |
| `assets.<SYM>.allowed_regimes` | YAML per-asset | field | per-asset list | **Required / no default** | Strategy regime gate | Per-asset override of global | config_models.py:743 |
| `assets.<SYM>.liquidity_gate` | YAML per-asset | field | `None` | **Runtime fallback** | Handler liquidity gate | `None` → use global `mean_reversion.liquidity_gate` | config_models.py:740 |
| `assets.<SYM>.strategy.microstructure_veto` | YAML per-asset | field | `None` | **Runtime fallback** | Handler veto config resolution | `None` → use global V1 config | config_models.py:687 |
| `assets.<SYM>.strategy.directional_bias` | YAML per-asset | field | `None` | **Runtime fallback** | Handler bias config resolution | `None` → use global V2 config | config_models.py:691 |

## Vector 1: Microstructure Veto

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `microstructure_veto.enabled` | YAML | field | `false` | **YAML default; dormant** | Handler config resolution | Master switch; `false` → entire V1 inactive | mean_reversion.yaml:268 |
| `microstructure_veto.tfi_ema_span` | YAML | field | `5` | **Pydantic default + YAML** | Handler `_check_microstructure_veto()` | EMA smoothing window | config_models.py:517, YAML:269 |
| `microstructure_veto.tfi_adverse_threshold` | YAML | field | `0.3` | **Pydantic default + YAML** | Handler veto logic | \|TFI\| above this = adverse | config_models.py:521, YAML:270 |
| `microstructure_veto.obi_confirm_enabled` | YAML | field | `false` | **Pydantic default + YAML** | Handler veto logic | OBI as confirming factor (NOT sole driver) | config_models.py:527, YAML:271 |
| `microstructure_veto.obi_adverse_threshold` | YAML | field | `0.3` | **Pydantic default + YAML** | Handler veto logic | \|OBI\| above this = adverse book | config_models.py:531, YAML:272 |
| `microstructure_veto.price_reaction_lookback_sec` | YAML | field | `60` | **Pydantic default + YAML** | Handler return-key selection | Maps to `ret_10s` / `ret_60s` / `ret_300s` | config_models.py:537, YAML:273 |
| `microstructure_veto.price_continuation_threshold` | YAML | field | `0.001` | **Pydantic default + YAML** | Handler veto logic | Adverse price move threshold | config_models.py:541, YAML:274 |
| `microstructure_veto.absorption_wick_ratio_min` | YAML | field | `0.4` | **Pydantic default + YAML** | Handler veto logic | Wick ratio for absorption detection | config_models.py:547, YAML:275 |
| `microstructure_veto.absorption_rebound_threshold` | YAML | field | `0.0005` | **Pydantic default + YAML** | Handler veto logic | Favorable price move for rebound | config_models.py:551, YAML:276 |
| `microstructure_veto.readiness_min_bars` | YAML | field | `5` | **Pydantic default + YAML** | Handler warmup gate | Bars before veto engages | config_models.py:557, YAML:277 |
| `microstructure_veto.missing_policy` | YAML | field | `"block"` | **Pydantic default (Literal["block"])** | Handler veto logic | Only "block" accepted (R1 hardening) | config_models.py:562, YAML:278 |
| Missing TFI in features | Handler code | behavior | — | **Fail-closed** | `_check_microstructure_veto()` | Always blocks; no config override | handler.py:672-673 |
| Invalid TFI (not float) | Handler code | behavior | — | **Fail-closed** | `_check_microstructure_veto()` | Always blocks; no config override | handler.py:676-678 |
| OBI confirm-only | Handler code | policy | — | **Hardcoded policy** | `_check_microstructure_veto()` | OBI can only confirm adverse TFI, never veto alone | handler.py:706-722 |
| Zero-range bar | Handler code | behavior | — | **Fail-closed** | `_check_microstructure_veto()` | `bar_range <= 0` → always blocked | handler.py:735-737 |
| Ambiguous case (no absorption, no continuation) | Handler code | behavior | — | **Fail-closed (hardcoded)** | `_check_microstructure_veto()` | Conservative block when evidence unclear | handler.py:791-792 |
| `price_motion` absent from CMD | Handler code | behavior | — | **Fail-closed (effective)** | `_check_microstructure_veto()` | No continuation/rebound data → ambiguous block | handler.py:751 |
| `price_motion` top-level in CMD | FE + Schema | contract | — | **Hardcoded policy** | FE emission + handler cache | Always top-level field, NOT in `features` | feature_engineering.py + cmd_schema |
| Return key selection (`ret_10s`/`ret_60s`/`ret_300s`) | Handler code | formula | lookback ≤15→10s; ≥250→300s; else 60s | **Hardcoded policy** | `_check_microstructure_veto()` | Not configurable; derived from `price_reaction_lookback_sec` | handler.py:754-758 |
| EMA formula: `α * tfi + (1-α) * prev` | Handler code | formula | `α = 2/(span+1)` | **Hardcoded policy** | `_check_microstructure_veto()` | Standard EMA; not configurable | handler.py:682-686 |
| Absorption override: wick OR rebound | Handler code | policy | — | **Hardcoded policy** | `_check_microstructure_veto()` | Either evidence type sufficient; operator cannot change | handler.py:783-784 |

## Vector 2: Directional Bias

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `directional_bias.enabled` | YAML | field | `false` | **YAML default; dormant** | Handler config resolution | Master switch; `false` → entire V2 inactive | mean_reversion.yaml:288 |
| `directional_bias.base_long_threshold` | YAML | field | `0.115` | **Required / no default** | Handler `_apply_directional_bias()` | Static %B for LONG | config_models.py:609 |
| `directional_bias.base_short_threshold` | YAML | field | `0.115` | **Required / no default** | Handler `_apply_directional_bias()` | Static %B for SHORT | config_models.py:613 |
| `directional_bias.funding_shift_magnitude` | YAML | field | `0.02` | **Pydantic default + YAML** | Handler bias formula | Max shift per unit funding | config_models.py:619, YAML:291 |
| `directional_bias.funding_normalization_scale` | YAML | field | `0.0003` | **Pydantic default + YAML** | Handler bias formula | Normalizer for raw funding rate | config_models.py:623, YAML:292 |
| `directional_bias.funding_deadband` | YAML | field | `0.1` | **Pydantic default + YAML** | Handler bias formula | Noise gate | config_models.py:627, YAML:293 |
| `directional_bias.threshold_clamp_min` | YAML | field | `0.01` | **Pydantic default + YAML** | Handler bias formula | Floor for thresholds | config_models.py:633, YAML:294 |
| `directional_bias.threshold_clamp_max` | YAML | field | `0.3` | **Pydantic default + YAML** | Handler bias formula | Ceiling for thresholds | config_models.py:637, YAML:295 |
| Missing funding_rate | Handler code | behavior | — | **Graceful degradation** | `_apply_directional_bias()` | Falls back to static split thresholds | handler.py:820-826 |
| Invalid funding_rate (not float) | Handler code | behavior | — | **Graceful degradation** | `_apply_directional_bias()` | Falls back to static split thresholds | handler.py:830-836 |
| Bias not configured for symbol | Handler code | behavior | — | **Runtime fallback** | `_apply_directional_bias()` | Clears overrides → legacy symmetric `entry_threshold` | handler.py:810-814 |
| Formula: `eff_long = base - norm * shift` | Handler code | formula | — | **Hardcoded policy** | `_apply_directional_bias()` | Fade-the-crowd direction; not configurable | handler.py:850-851 |
| Clamp: `max(min, min(max, val))` | Handler code | formula | — | **Hardcoded policy** | `_apply_directional_bias()` | Boundary enforcement; not configurable | handler.py:854-855 |
| Transient clearing in `finally` | Handler code | policy | — | **Hardcoded policy** | `_on_process_strategy()` | R3: thresholds cleared post-on_bar | handler.py:916-917 |
| Per-symbol isolation | Handler code | policy | — | **Hardcoded policy** | `_strategies: Dict[str, ...]` | Each symbol has separate strategy instance | handler.py:256 |
| Legacy fallback: `entry_threshold_long/short = None` | Strategy code | behavior | — | **Runtime fallback** | `_evaluate_signal()` | `None` → use symmetric `entry_threshold` | mean_reversion_strategy.py:501-502 |

## Activation and Assignment

| Surface / Field | Location | Type | Current Value | Category | Consumer | Operational Effect | Proof Source |
|---|---|---|---|---|---|---|---|
| `strategies.yaml:assignments.DOGEUSDT` | YAML registry | field | `["mean_reversion"]` | **YAML default** | StrategyRuntime | DOGEUSDT is assigned to MR | strategies.yaml:41 |
| `mean_reversion.enabled` | YAML | field | `true` | **YAML default** | Handler | MR globally enabled | mean_reversion.yaml:17 |
| `mean_reversion.assets.DOGEUSDT.enabled` | YAML | field | `true` | **YAML default** | Handler | DOGEUSDT trading enabled in MR | mean_reversion.yaml:171 |
| Activation = assigned ∩ enabled | Handler code | policy | — | **Hardcoded policy** | `_parse_config()` | Both registry assignment AND asset enabled required | handler.py `_parse_config` |
| `microstructure_veto.enabled` | YAML | field | `false` | **Dormant default** | Handler V1 resolution | V1 exists on disk but inactive | mean_reversion.yaml:268 |
| `directional_bias.enabled` | YAML | field | `false` | **Dormant default** | Handler V2 resolution | V2 exists on disk but inactive | mean_reversion.yaml:288 |
| Other assets (BTCUSDT, XRPUSDT, etc.) | YAML | field | `enabled: false` | **Dormant default** | Handler | Configured on disk but not trading | mean_reversion.yaml:193,213,234 |

## `MRStrategyConfig` Dataclass Defaults (Unit Test Only)

These defaults exist in the `@dataclass` but are **never used in production** — handler always injects explicit values from YAML.

| Field | Dataclass Default | Production Source | Category |
|---|---|---|---|
| `bb_window` | `20` | YAML `strategy.bb_window` | **Test-only default** |
| `bb_num_std` | `2.0` | YAML `strategy.bb_num_std` | **Test-only default** |
| `atr_window` | `14` | YAML `strategy.atr_window` | **Test-only default** |
| `rsi_window` | `14` | YAML `strategy.rsi_window` | **Test-only default** |
| `min_bars` | `25` | YAML `strategy.min_bars` | **Test-only default** |
| `min_bb_width` | `Decimal("0.001")` | YAML `strategy.min_bb_width` | **Test-only default** |
| `max_bb_width` | `Decimal("0.05")` | YAML `strategy.max_bb_width` | **Test-only default** |
| `entry_threshold` | `Decimal("0.05")` | YAML `strategy.entry_threshold` | **Test-only default** |
| `entry_threshold_long` | `None` | Handler `_apply_directional_bias()` | **Runtime fallback** (None → symmetric) |
| `entry_threshold_short` | `None` | Handler `_apply_directional_bias()` | **Runtime fallback** (None → symmetric) |
| `sl_buffer_pct` | `Decimal("0")` | YAML if declared | **Pydantic/dataclass default** |
| `tp_buffer_pct` | `Decimal("0")` | YAML if declared | **Pydantic/dataclass default** |
| `allowed_regimes` | `[]` (empty) | YAML `allowed_regimes` | **Test-only default** (empty = fail-closed) |
