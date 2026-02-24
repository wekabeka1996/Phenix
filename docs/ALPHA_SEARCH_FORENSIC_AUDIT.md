# Forensic Audit: alpha_search (Shadow Domain)

- Audit window (UTC): 2026-02-20T21:50:01.602104+00:00 -> 2026-02-23T21:50:01.602104+00:00
- Data coverage alpha log: 2026-02-23T10:45:03+00:00 -> 2026-02-23T23:48:05+00:00
- Data coverage WAL: 2026-02-20T21:50:02.601000+00:00 -> 2026-02-23T21:50:05.474000+00:00
- Environment: PowerShell on Windows, repo root `c:\Users\user\Music\Phenix`.

## 1. File Discovery

Executed command requested by user:
```bash
grep -r --include="*.py" --include="*.yaml" --include="*.yml" "alpha_search\|AlphaSearch\|alpha-search" .
```
Result: `grep` is not installed in this PowerShell environment (`CommandNotFoundException`).
Fallback used:
```bash
rg -n --glob "*.py" --glob "*.yaml" --glob "*.yml" "alpha_search|AlphaSearch|alpha-search" .
rg -l --glob "*.py" --glob "*.yaml" --glob "*.yml" "alpha_search|AlphaSearch|alpha-search" .
```

Relevant file tree (all matches from discovery):

| Path | Short Description |
|---|---|
| `backtest_engine/feature_augmenter.py` | TA feature augmentation for backtest bars (MACD/RSI/Stoch/BB/ATR etc). |
| `backtest_engine/reporting.py` | Backtest report bundling; includes strategy/config snapshot for reproducibility. |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | Global event verb registry; declares ALPHA_SCORE_CALCULATED owner=alpha_search. |
| `apps/reference/main.py` | Composition root; wires AlphaSearchBacktestPlugin and AlphaScoreWalListener in backtest/live-testnet. |
| `apps/reference/domains/decision_making/decision_making.py` | Main DM engine; also emits dm_inline ALPHA_SCORE_CALCULATED for monitoring. |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | Core alpha_search shadow plugin: cache bridge, scoring, virtual trader, summary. |
| `apps/reference/domains/alpha_search/config_models.py` | Strict Pydantic schemas + YAML loaders for alpha_search and alpha_search_system. |
| `apps/reference/domains/alpha_search/ensemble.py` | TA ensemble model with dynamic weights and PnL feedback loop. |
| `apps/reference/domains/alpha_search/alpha_search_log_adapter.py` | Dedicated rotating structured log writer: logs/domain_alpha_search.log. |
| `apps/reference/domains/alpha_search/models/aurora_adapter.py` | Adapter to AuroraScoringKernel (shared scoring logic, fail-closed behavior). |
| `config/alpha_search.yaml` | Operational alpha_search config (providers, thresholds, triggers, virtual trader). |
| `config/alpha_search_system.yaml` | Model tuning config (weights, confidence params, clamps). |
| `scripts/analyze_alpha_search_log_pnl.py` | Parses VIRTUAL_CLOSE events and computes per-symbol win-rate/PnL. |
| `scripts/tmp_alpha_search_fee_adjusted_pnl.py` | Temporary fee-adjusted virtual PnL utility. |
| `tools/alpha_search_report.py` | Offline alpha performance analyzer from WAL/backtest artifacts. |
| `tools/backtest_diagnostics.py` | Diagnostics generation including alpha sections. |
| `tools/backtest_summarize.py` | Post-processing of backtest reports (regime mapping, summaries). |
| `apps/reference/domains/feature_engineering/feature_engineering.py` | Pass-through of augmented TA features used by alpha_search models. |
| `tests/domains/alpha_search/test_backtest_plugin.py` | A3 tests: feature cache bridge, fail-closed scoring, multi-provider behavior. |
| `tests/domains/alpha_search/test_integration.py` | Integration tests: plugin wiring, WAL capture, emitted payload contract. |
| `tests/domains/alpha_search/test_system_config.py` | Config schema/tests ensuring model params read from YAML. |
| `tests/domains/alpha_search/test_aurora_adapter.py` | Aurora adapter correctness/fail-closed tests. |
| `tests/domains/alpha_search/test_ensemble_features_plumbing.py` | Feature plumbing tests for ensemble models. |
| `tests/domains/alpha_search/test_models_determinism.py` | Determinism tests for alpha models. |
| `tests/domains/alpha_search/test_registry_fail_closed.py` | Registry/model fail-closed behavior tests. |
| `tests/test_ensemble.py` | Generic ensemble tests used by alpha stack. |
| `tests/test_backtest_engine.py` | Backtest engine behavior tests including integration points. |
| `tests/test_log_rotation.py` | Log rotation tests relevant to alpha_search domain log behavior. |
| `tests/investigation/test_sizing_regression.py` | Investigation/regression context touching alpha references. |

## 2. Повна конфігурація alpha_search

### 2.1 ?????? `config/alpha_search.yaml`
```yaml
# ==============================================================================
# Alpha Search Configuration — SSOT
# ==============================================================================
# ALPHA-A4: Multi-provider alpha search configuration.
# Loaded by AlphaSearchBacktestPlugin (separate loader, no core changes).
#
# Architecture:
# - Two-phase bridge: EVT:FEATURES_CALCULATED → cache → CMD:PROCESS_STRATEGY
# - Multi-provider: aurora + ta_ensemble can run simultaneously
# - Shadow mode: signals logged but not traded (for analysis)
# ==============================================================================

alpha_search:
  enabled: true
  shadow_mode: true  # If true, signals are logged but not traded

  # ============================================================================
  # Event Bridge Configuration (A3.1)
  # ============================================================================
  triggers:
    feature_event: "EVT:FEATURES_CALCULATED"  # Provides features → cache
    decision_event: "CMD:PROCESS_STRATEGY"    # Triggers scoring → read cache
    emit_event: "EVT:ALPHA_SCORE_CALCULATED"  # Output event

  # Cache for features between events
  cache:
    max_per_symbol: 10          # Keep last 10 bars per symbol
    require_same_bar_close_ts: false  # Fuzzy match to avoid cache misses

  # ============================================================================
  # Providers (A3.2) — aurora and/or ta_ensemble
  # ============================================================================
  providers:
    aurora:
      enabled: true
      symbols:
        - BTCUSDT
        - ETHUSDT
        - SOLUSDT
      threshold: 0.155          # було 0.12 → ближче до нашої 0.162
      fail_closed: true

      adapter:
        scoring_version: "v2"
        essential_features:
          - obi
          - delta_price
          - macro_resid

    ta_ensemble:
      enabled: true            # All 3 TA models active
      symbols: null            # All symbols
      threshold: 0.18           # було 0.15
      fail_closed: true

      ensemble:
        rebalance_frequency_days: 7
        performance_window_days: 30
        risk_adjustment: true
        models:
          mean_reversion_v1:
            enabled: true
          momentum_v1:
            enabled: true
          volatility_v1:
            enabled: true

  # ============================================================================
  # Virtual Trader (shadow PnL tracking)
  # ============================================================================
  virtual_trader:
    enabled: true
    per_provider: true         # Separate PnL per provider
    max_positions_per_symbol: 1
    notional_size: 1000
    exit:
      max_bars: 12
      max_hold_sec: 3600

  # ============================================================================
  # LEGACY: All deprecated fields moved under 'legacy' key for strict validation
  # These fields are ignored by new code but kept for migration/reference
  # ============================================================================
  legacy:
    augmenter:
      macd:
        fast: 12
        slow: 26
        signal: 9

      stochastic:
        k_period: 14
        d_period: 3

      rsi:
        period: 14

      momentum:
        windows_bars: [5, 60, 1440]

      volume_momentum:
        window: 5

    ensemble:
      rebalance_frequency_days: 7
      performance_window_days: 30
      min_weight: 0.1
      max_weight: 0.6
      risk_adjustment: true
      variance_cap: 0.5

    signals:
      long_threshold: 0.1
      short_threshold: -0.1
      pnl_normalization: 100.0

    models:
      momentum:
        short_weight: 0.3
        medium_weight: 0.4
        long_weight: 0.3
        volume_confirm_multiplier: 1.2
        volume_contradict_multiplier: 0.8
        base_confidence: 0.8
        rsi_overbought: 70
        rsi_oversold: 30
        rsi_confidence_penalty: 0.7
        macd_confirm_boost: 1.1
        macd_contradict_penalty: 0.9

      mean_reversion:
        bb_threshold: 2.0
        stoch_overbought: 80
        stoch_oversold: 20

      volatility:
        atr_period: 14
        volatility_threshold: 1.5
```

### 2.2 ?????? `config/alpha_search_system.yaml`
```yaml
# ==============================================================================
# Alpha Search System Configuration — Model Tuning Parameters
# ==============================================================================
# All hardcoded parameters from alpha_search models externalized here.
# Loaded by AlphaSearchBacktestPlugin alongside alpha_search.yaml.
#
# This file controls MODEL BEHAVIOR (weights, thresholds, multipliers).
# For operational config (providers, triggers, cache) see alpha_search.yaml.
# ==============================================================================

alpha_search_system:

  # ============================================================================
  # Momentum Model (momentum_v1)
  # Source: apps/reference/domains/alpha_search/models/momentum.py
  # ============================================================================
  momentum:
    weights:
      short: 0.3       # 5m momentum weight
      medium: 0.4      # 1h momentum weight
      long: 0.3        # 1d momentum weight

    volume:
      confirm_multiplier: 1.2      # Volume supports price direction
      contradict_multiplier: 0.8   # Volume contradicts price direction

    rsi:
      overbought: 70               # RSI overbought threshold
      oversold: 30                 # RSI oversold threshold
      confidence_penalty: 0.7      # Confidence reduction at extremes

    macd:
      confirm_boost: 1.1           # MACD confirms momentum direction
      contradict_penalty: 0.9      # MACD contradicts momentum direction

    confidence:
      base: 0.8                    # Base confidence level
      consistency_min: 0.7         # Min consistency multiplier (0% agreement)
      consistency_range: 0.6       # Range added at 100% agreement (min + range = max)

  # ============================================================================
  # Mean Reversion Model (mean_reversion_v1)
  # Source: apps/reference/domains/alpha_search/models/mean_reversion.py
  # ============================================================================
  mean_reversion:
    weights:
      bb: 0.4          # Bollinger Band position weight
      rsi: 0.3         # RSI divergence weight
      sma: 0.2         # SMA deviation weight
      stoch: 0.1       # Stochastic crossover weight

    rsi:
      oversold: 30                 # RSI oversold threshold (strong buy)
      overbought: 70               # RSI overbought threshold (strong sell)

    sma:
      deviation_normalizer: 0.05   # Typical 5% deviation for normalization

    stochastic:
      oversold_zone: 20            # %K oversold zone boundary
      overbought_zone: 80          # %K overbought zone boundary
      signal_strength: 0.3         # Stochastic crossover signal strength

    volume:
      confirm_multiplier: 1.2      # Volume supports reversion
      contradict_multiplier: 0.8   # Volume contradicts reversion
      high_threshold: 1.5          # Volume ratio for 'high volume'
      low_threshold: 0.7           # Volume ratio for 'low volume'

    bb_width:
      wide_threshold: 0.05         # BB width above this = high volatility
      narrow_threshold: 0.02       # BB width below this = low volatility
      max_multiplier: 1.5          # Max amplification from BB width
      narrow_penalty: 0.7          # Penalty for narrow bands

    confidence:
      base: 0.5                    # Base confidence level
      agreement_factor: 0.4        # Factor for signal agreement
      strength_base: 0.8           # Base for strength multiplier
      signal_threshold: 0.1        # Min absolute signal for 'non-zero'

  # ============================================================================
  # Volatility Model (volatility_v1)
  # Source: apps/reference/domains/alpha_search/models/volatility.py
  # ============================================================================
  volatility:
    weights:
      atr: 0.4         # ATR ratio weight
      bb: 0.25         # BB width change weight
      rv: 0.2          # Realized volatility trend weight
      range: 0.1       # Price range ratio weight
      vol_corr: 0.05   # Volume-volatility correlation weight

    bb:
      amplifier: 10                # Amplifies small BB width changes

    signal_clamp:
      atr: 2.0                     # ATR signal clamp [-2, 2]
      rv: 2.0                      # RV signal clamp [-2, 2]

    volume_vol:
      high_threshold: 1.2          # Volume-vol ratio for 'high'
      low_threshold: 0.8           # Volume-vol ratio for 'low'
      signal_strength: 0.2         # Vol-corr signal strength

    vol_level:
      low_level: 0.5               # Volatility level below this = very low
      low_penalty: 0.5             # Signal reduction for low volatility
      high_level: 2.0              # Volatility level above this = very high
      high_boost: 1.2              # Signal amplification for high volatility

    confidence:
      base: 0.6                    # Base confidence level
      agreement_factor: 0.3        # Factor for signal agreement
      strength_base: 0.7           # Base for strength multiplier
      no_signal: 0.4               # Confidence when no strong signals

  # ============================================================================
  # Ensemble Model
  # Source: apps/reference/domains/alpha_search/ensemble.py
  # ============================================================================
  ensemble:
    max_history: 100               # Max performance history entries per model
    confidence_threshold: 0.1      # Min confidence for valid score
    pnl_normalizer: 100.0          # PnL range for normalization (-100..+100 USD)
    min_performance_score: 0.1     # Floor for model performance score
    variance_cap: 0.5              # Max variance penalty in risk adjustment

  # ============================================================================
  # Backtest Plugin
  # Source: apps/reference/domains/alpha_search/backtest_plugin.py
  # ============================================================================
  plugin:
    default_tf_sec: 300            # Default timeframe when not in payload
    why_chain_limit: 5             # Max why entries in emitted events
```

### 2.3 ??????? ????????? (?????)

| ????? | ???????? | ???????? | ??????? |
|---|---|---|---|
| Mode | `alpha_search.enabled` | `true` | `config/alpha_search.yaml:14` |
| Mode | `alpha_search.shadow_mode` | `true` | `config/alpha_search.yaml:15` |
| Bridge | `triggers.feature_event` | `EVT:FEATURES_CALCULATED` | `config/alpha_search.yaml:21` |
| Bridge | `triggers.decision_event` | `CMD:PROCESS_STRATEGY` | `config/alpha_search.yaml:22` |
| Bridge | `triggers.emit_event` | `EVT:ALPHA_SCORE_CALCULATED` | `config/alpha_search.yaml:23` |
| Cache | `max_per_symbol` | `10` | `config/alpha_search.yaml:27` |
| Cache | `require_same_bar_close_ts` | `false` | `config/alpha_search.yaml:28` |
| Provider aurora | `threshold` | `0.155` | `config/alpha_search.yaml:40` |
| Provider aurora | `symbols` | `BTCUSDT, ETHUSDT, SOLUSDT` | `config/alpha_search.yaml:36-39` |
| Provider ta_ensemble | `threshold` | `0.18` | `config/alpha_search.yaml:53` |
| Provider ta_ensemble | models | `mean_reversion_v1, momentum_v1, volatility_v1` | `config/alpha_search.yaml:61-66` |
| Virtual trader | `enabled` | `true` | `config/alpha_search.yaml:72` |
| Virtual trader | `notional_size` | `1000` | `config/alpha_search.yaml:75` |
| Virtual trader exit | `max_bars / max_hold_sec` | `12 / 3600` | `config/alpha_search.yaml:77-78` |
| Trading mode global | `trading_mode` | `hybrid_live_data_testnet_exec` | `config/aurora/system.yaml:5` |
| Trading mode granular | `trading.domain_configuration.decision_making.trading_mode` | `live` | `config/aurora/trading.yaml:182-183` |
| Main Aurora decision | `signal_threshold / neutral_threshold` | `0.162 / 0.05` | `config/aurora/strategies/aurora.yaml:35-36` |
| Main Aurora gates | `anti_flat_sigma / anti_fomo_sigma` | `0.48 / 10.5` | `config/aurora/strategies/aurora.yaml:148-149` |
| Main Aurora churn | `holding_period.min_duration_sec / reentry_cooldown_sec` | `30 / 840` | `config/aurora/strategies/aurora.yaml:138,156` |
| MeanReversion global | `entry_threshold` | `0.115` | `config/aurora/strategies/mean_reversion.yaml:52` |
| Registry anomaly | `assignments.ETHUSDT` | `[]` (empty) | `config/aurora/strategies.yaml:26` |

### 2.4 ?????????? ?????? ???????? Aurora (??????)

```yaml
    1: config_version: 1.0.1
    2: # NEW: Defines the operational mode for the trading bot.
    3: # Options: "live", "testnet", "hybrid_live_data_testnet_exec"
    4: # HYBRID MODE: Live market data → Testnet execution (safe testing with real data)
    5: trading_mode: "hybrid_live_data_testnet_exec"
    6: 
    7: # REQUIRED: typed system config (SystemConfig)
    8: system:
```
```yaml
   12: trading:
   13:   # HYBRID MODE: testnet execution with live data (domain_configuration controls granular modes)
   14:   mode: hybrid_live_data_testnet_exec
   15:   backtest:
   16:     start_date: "2023-05-14"
   17:     end_date: "2023-08-30"
   18:     initial_balance: 1000.0
   19:   tca_prefs:
```
```yaml
  177:   domain_configuration:
  178:     market_data:
  179:       trading_mode: live      # Read LIVE Binance market data (WebSocket + REST)
  180:     feature_engineering:
  181:       trading_mode: live      # Process features from live data
  182:     decision_making:
  183:       trading_mode: live      # Generate signals from live features
  184:     # PURGE-DIRTY-DOZEN: Removed risk_management, execution_position, audit_trail trading_modes
  185:     # (dead legacy, global trading_mode is SSOT) - 2026-01-25
```
```yaml
   30:   decision:
   31:     testnet:
   32:       signal_threshold: 0.162
   33:     production:
   34:       signal_threshold: 0.162
   35:     signal_threshold: 0.162
   36:     neutral_threshold: 0.05
   37:     symbols_to_track:
   38:       - BTCUSDT
   39:       - ETHUSDT
   40:       - SOLUSDT
```
```yaml
  136:     holding_period:
  137:       enabled: true
  138:       min_duration_sec: 30          # Minimum seconds to hold position
  139:       emergency_exit_threshold: 0.7  # |score| threshold for emergency override
  140:       apply_to_flips: true          # Also apply holding period to FLIP signals
  141: 
  142:     # === VOL-ADJ-GATES-01: Sigma-normalized Motion Gates ===
  143:     # Anti-Flat: Block entry when normalized motion too small (fee churn in dead market)
  144:     # Anti-FOMO: Block entry when normalized motion too extreme (snapback risk)
  145:     # Formula: pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)
  146:     gates:
  147:       enabled: true
  148:       anti_flat_sigma: 0.48  # Підвищено 0.35→0.48 (2026-02-18)
  149:       anti_fomo_sigma: 10.5  # Підвищено 7.0→10.5: менше ANTI_FOMO блоків
  150:       # P0-2: FIXED 900 → 300 (pm_norm_900s doesn't exist in schema, only 10/60/300)
  151:       motion_window_sec: 300 # Use 5-minute window (pm_norm_300s)
  152: 
  153:     # === Re-entry Cooldown (Anti-Ping-Pong Gate) ===
  154:     # Prevents immediate re-entry after position closes.
  155:     # After exiting a position, wait this many seconds before allowing new entry.
  156:     reentry_cooldown_sec: 840  # Підвищено 300→840: Anti-Churn (2026-02-18)
  157: 
```
```yaml
   27:   # ORDER-POLICY-01: Entry order execution policy (SSOT for strategy)
   28:   # MR uses MARKET orders for fast mean-reversion entries
   29:   execution:
   30:     entry_order_type: "MARKET"   # MUST be one of: LIMIT, MARKET
   31:     entry_tif: null              # null for MARKET orders (ignored)
   32: 
   33:   # DM-SAFETY-BYPASSES-P1: Explicit safety gates control (fail-closed if missing)
   34:   # Mean reversion trades AGAINST trend → safety gates DISABLED.
   35:   safety_gates:
   36:     enabled: false
   37: 
```
```yaml
   51:     # Entry thresholds
   52:     entry_threshold: 0.115     # Підвищено 0.05→0.115 (2026-02-18)
   53:     rsi_oversold: 30
   54:     rsi_overbought: 70
   55:     
   56:     # Minimum bars before generating signals
   57:     min_bars: 25
```
```yaml
   24: assignments:
   25:   # ETH: Aurora-only (champion bar-driven asset, Phase 3+)
   26:   ETHUSDT: []
   27: 
   28:   # SOL: Aurora-only (scalping mode, Phase 3)
   29:   SOLUSDT:
   30:     - aurora
   31: 
   32:   # DOGE: MR-only (champion MR asset, +$387 in research)
   33:   DOGEUSDT:
   34:     - mean_reversion
   35: 
   36:   # XRP: MR-only (MR silver medal, +$121)
   37:   XRPUSDT:
   38:     - mean_reversion
   39: 
   40:   # BTC: Mean Reversion (CHANGED from aurora)
   41:   # Backtest showed 59% MEAN_REVERSION regime - Aurora unsuitable for ranging markets.
   42:   # Mean Reversion strategy designed for sideways/flat market conditions.
   43:   BTCUSDT:
   44:     - aurora
   45: 
```

## 3. Архітектура домену

### 3.1 ??????? ????

- ???????? ?????: `apps/reference/domains/alpha_search/`.
- ??????: `apps/reference/domains/alpha_search/models/` (`aurora_adapter.py`, `momentum.py`, `mean_reversion.py`, `volatility.py`).
- ?????????? ? ????????????? root: `apps/reference/main.py`.
- ?????????? ? FE/DM: `apps/reference/domains/feature_engineering/feature_engineering.py`, `apps/reference/domains/decision_making/decision_making.py`.

### 3.2 ??????? ?????/??????

- `AlphaSearchBacktestPlugin` (`apps/reference/domains/alpha_search/backtest_plugin.py:67`): two-phase bridge, multi-provider scoring, virtual trader.
- `AlphaScoreWalListener` (`apps/reference/domains/alpha_search/wal_listener.py:14`): ?????????? `EVT:ALPHA_SCORE_CALCULATED` ? WAL.
- `AuroraAlphaAdapter` (`apps/reference/domains/alpha_search/models/aurora_adapter.py:24`): ?????? `AuroraScoringKernel.compute(...)` ??? side effects.
- `EnsembleModel` (`apps/reference/domains/alpha_search/ensemble.py:53`): ?????????? TA-??????? ? adaptive weights.
- `AlphaModelRegistry` ? DM (`apps/reference/domains/decision_making/decision_making.py:212-219`): ??????? `dm_inline` ???? alpha-???????????.

### 3.3 ?????????? ? ???????? Aurora

1. ?????? ??????????? ???. Plugin ???????????? ?? ?? ? ????? FE/decision boundary:
```python
  242:     def _register_listeners(self) -> None:
  243:         """Register event listeners for two-phase bridge."""
  244:         if hasattr(self.event_bus, "listen"):
  245:             # Phase 1: Cache features
  246:             self.event_bus.listen(
  247:                 self.config.triggers.feature_event,
  248:                 self._on_features_cache
  249:             )
  250:             # Phase 2: Score on decision event
  251:             self.event_bus.listen(
  252:                 self.config.triggers.decision_event,
  253:                 self._on_decision_score
  254:             )
  255:             # Trade tracking for virtual PnL
  256:             self.event_bus.listen("EVT:TRADE_EXECUTED", self._on_trade)
  257: 
```
2. ???? ???? ??? ????? Two-phase cache bridge:
- `EVT:FEATURES_CALCULATED` -> cache (`_on_features_cache`).
- `CMD:PROCESS_STRATEGY` -> scoring (`_on_decision_score`).
3. ?? ??????? ?????? intents? ??. alpha_search emit-??? `EVT:ALPHA_SCORE_CALCULATED`, ??? ?? emit-??? `EVT:TRADE_INTENT_PROPOSED`.
```python
  489:     def _emit_score_event(
  490:         self,
  491:         provider_id: str,
  492:         symbol: str,
  493:         score: AlphaScore,
  494:         threshold: float,
  495:         tf_sec: int,
  496:         bar_close_ts: int,
  497:         signal_id: str,
  498:     ) -> None:
  499:         """Emit EVT:ALPHA_SCORE_CALCULATED with provider_id."""
  500:         payload = {
  501:             "provider_id": provider_id,
  502:             "model_name": score.model_name,
  503:             "symbol": symbol,
  504:             "tf_sec": tf_sec,
  505:             "bar_close_ts": bar_close_ts,
  506:             "score": float(score.score),
  507:             "confidence": float(score.confidence),
  508:             "threshold": threshold,
  509:             "shadow": self.shadow_mode,
  510:             "signal_id": signal_id,
  511:             # Limit why chain
  512:             "why": score.why[:self.system_config.plugin.why_chain_limit],
  513:             "features_used": score.features_used,
  514:         }
  515: 
  516:         self.event_bus.emit(
  517:             event_name=self.config.triggers.emit_event,
  518:             payload=payload,
  519:             why=f"alpha_search_{provider_id}"
  520:         )
```
4. ?? ???????? ??????? ? Aurora ? real-time?
- Direct compare hook `_shadow_compare_kernel` ????? ? DM (`apps/reference/domains/decision_making/decision_making.py:1557`), ??? **?? ????????????** (????? ????????? ? ?????).
- ???????? operational path ??? alpha_search: ?????????? ????? `ALPHA_SCORE_CALCULATED` + WAL/log; ?? ?????? execution.
```python
 1557:     def _shadow_compare_kernel(
 1558:         self,
 1559:         symbol: str,
 1560:         *,
 1561:         legacy_score: decimal.Decimal,
 1562:         legacy_side: str,
 1563:         legacy_thr_buy: decimal.Decimal,
 1564:         legacy_thr_sell: decimal.Decimal,
 1565:         features: Dict[str, Any],
 1566:         warmup_readiness: Dict[str, bool],
 1567:         price: decimal.Decimal,
 1568:         signal_weights: Dict[str, float],
 1569:         feature_neutrals: Dict[str, float],
 1570:         essential_features: List[str],
 1571:         base_threshold: decimal.Decimal,
 1572:         regime_name: Optional[str],
 1573:         regime_thresholds: Dict[str, float],
 1574:         buy_count: int,
 1575:         sell_count: int,
 1576:     ) -> None:
 1577:         """
 1578:         Shadow mode: compare legacy scoring with kernel (no side effects).
 1579: 
 1580:         Logs divergences for validation before switching to kernel.
 1581:         """
 1582:         # Check if shadow mode is enabled
 1583:         aurora_cfg = getattr(self.config.strategies, "aurora", None)
 1584:         if not aurora_cfg or not getattr(aurora_cfg, "shadow_mode_enabled", False):
 1585:             return
 1586: 
 1587:         try:
 1588:             # Build side bias state
 1589:             side_bias_state = SideBiasState(
 1590:                 buy_count=buy_count,
 1591:                 sell_count=sell_count,
 1592:                 window_sec=aurora_cfg.decision.side_bias_window_sec or 420,
 1593:                 target_ratio=aurora_cfg.decision.side_bias_target_ratio or 0.72,
 1594:                 penalty_factor=aurora_cfg.decision.side_bias_penalty_factor or 0.25,
 1595:                 min_intents=aurora_cfg.decision.side_bias_min_intents or 18,
 1596:             )
 1597: 
 1598:             # Get direction strength config
 1599:             ds_cfg = getattr(aurora_cfg.decision,
 1600:                              "direction_strength_scoring", None)
 1601:             direction_strength_cfg = {
 1602:                 "directional_features": list(ds_cfg.directional_features) if ds_cfg else [],
 1603:                 "strength_features": list(ds_cfg.strength_features) if ds_cfg else [],
 1604:                 "strength_alpha": ds_cfg.strength_alpha if ds_cfg else 0.5,
 1605:                 "strength_cap": ds_cfg.strength_cap if ds_cfg else 1.5,
 1606:             }
 1607: 
 1608:             signals_cfg = getattr(aurora_cfg.decision, "signals", None)
 1609:             delta_price_cap_pct = decimal.Decimal(
 1610:                 str(signals_cfg.delta_price_cap_pct)
 1611:             ) if signals_cfg and signals_cfg.delta_price_cap_pct else decimal.Decimal("0.005")
 1612: 
 1613:             # Call kernel
 1614:             kernel_result = AuroraScoringKernel.compute(
 1615:                 symbol=symbol,
 1616:                 features=features,
 1617:                 warmup_readiness=warmup_readiness,
 1618:                 price=price,
 1619:                 signal_weights=signal_weights,
 1620:                 feature_neutrals=feature_neutrals,
 1621:                 essential_features=essential_features,
 1622:                 base_threshold=base_threshold,
 1623:                 regime_name=regime_name,
 1624:                 regime_thresholds=regime_thresholds,
 1625:                 side_bias_state=side_bias_state,
 1626:                 direction_strength_cfg=direction_strength_cfg,
 1627:                 delta_price_cap_pct=delta_price_cap_pct,
 1628:             )
 1629: 
 1630:             # Compare results
 1631:             score_diff = abs(float(legacy_score) - float(kernel_result.score))
 1632:             thr_buy_diff = abs(float(legacy_thr_buy) -
 1633:                                float(kernel_result.thr_buy))
 1634:             thr_sell_diff = abs(float(legacy_thr_sell) -
 1635:                                 float(kernel_result.thr_sell))
 1636:             side_match = legacy_side.lower() == kernel_result.side.lower()
 1637: 
 1638:             # Log divergence if significant
 1639:             threshold = 0.001  # 0.1% tolerance
 1640:             if score_diff > threshold or thr_buy_diff > threshold or thr_sell_diff > threshold or not side_match:
 1641:                 self.logger.warning(
 1642:                     f"[{symbol}] SHADOW_DIVERGENCE: "
 1643:                     f"legacy_score={float(legacy_score):.4f} vs kernel={float(kernel_result.score):.4f} (diff={score_diff:.6f}) | "
 1644:                     f"legacy_side={legacy_side} vs kernel={kernel_result.side} (match={side_match}) | "
 1645:                     f"thr_buy_diff={thr_buy_diff:.6f} thr_sell_diff={thr_sell_diff:.6f}"
 1646:                 )
 1647:             else:
 1648:                 self.logger.debug(
 1649:                     f"[{symbol}] SHADOW_MATCH: score={float(legacy_score):.4f}, side={legacy_side}")
 1650: 
 1651:         except Exception as e:
 1652:             self.logger.error(f"[{symbol}] SHADOW_ERROR: {e}")
```
5. Wiring ? main:
```python
  621:     # 3d. Initialize AlphaSearch Backtest Plugin (Shadow Advisor)
  622:     # ALPHA-SEARCH: Wire plugin to enable virtual trading and ensemble learning
  623:     alpha_plugin = None
  624:     try:
  625:         from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
  626:         alpha_plugin = AlphaSearchBacktestPlugin(
  627:             event_bus=fsm,
  628:             config_path=str(project_root / "config" / "alpha_search.yaml"),
  629:         )
  630:         engine.alpha_search_plugin = alpha_plugin
  631:         LOG.info("AlphaSearch Backtest Plugin registered (shadow mode)")
  632:     except ImportError as e:
  633:         LOG.warning(f"AlphaSearch not available: {e}")
  634:     except Exception as e:
  635:         LOG.error(f"AlphaSearch init failed: {e}")
  636: 
  637:     # 3e. Alpha Score WAL Listener (captures all EVT:ALPHA_SCORE_CALCULATED to WAL)
  638:     try:
  639:         from apps.reference.domains.alpha_search.wal_listener import AlphaScoreWalListener
  640:         _alpha_wal = AlphaScoreWalListener(event_bus=fsm)
  641:     except Exception as e:
  642:         LOG.debug(f"Alpha WAL listener not initialized: {e}")
```
```python
 1397:     # ALPHA-SEARCH: Wire shadow observer for testnet/hybrid/live modes
 1398:     # Mirrors backtest wiring (lines 621-642) but without engine attachment.
 1399:     # In shadow_mode the plugin scores alongside real strategies without affecting execution.
 1400:     try:
 1401:         from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
 1402:         alpha_plugin = AlphaSearchBacktestPlugin(
 1403:             event_bus=fsm,
 1404:             config_path=str(project_root / "config" / "alpha_search.yaml"),
 1405:         )
 1406:         LOG.info("AlphaSearch shadow observer registered for live/testnet mode")
 1407:     except ImportError as e:
 1408:         LOG.debug(f"AlphaSearch not available: {e}")
 1409:     except Exception as e:
 1410:         LOG.warning(f"AlphaSearch init failed: {e}")
 1411: 
 1412:     # Alpha Score WAL Listener (testnet/hybrid/live)
 1413:     try:
 1414:         from apps.reference.domains.alpha_search.wal_listener import AlphaScoreWalListener
 1415:         _alpha_wal = AlphaScoreWalListener(event_bus=fsm)
 1416:     except Exception as e:
```

## 4. Логіка прийняття рішень

### 4.1 ??????? ??????? ???????? (alpha_search)

1. `momentum_v1`:
- `momentum_score = mom_5m*w_short + mom_1h*w_medium + mom_1d*w_long`.
- Volume confirm/contradict multiplier, RSI penalty, MACD confirm/penalty.
- Confidence ????????? ?? consistency ????? ???????????.
```python
   76:         # Calculate weighted momentum score
   77:         short_weight = Decimal(str(weights_cfg.get("short", 0.3)))
   78:         medium_weight = Decimal(str(weights_cfg.get("medium", 0.4)))
   79:         long_weight = Decimal(str(weights_cfg.get("long", 0.3)))
   80: 
   81:         momentum_score = (
   82:             mom_5m * short_weight +
   83:             mom_1h * medium_weight +
   84:             mom_1d * long_weight
   85:         )
   86: 
   87:         # Volume confirmation (amplifies signal if volume supports direction)
   88:         vol_confirm = Decimal(str(volume_cfg.get("confirm_multiplier", 1.2)))
   89:         vol_contradict = Decimal(
   90:             str(volume_cfg.get("contradict_multiplier", 0.8)))
   91: 
   92:         volume_multiplier = Decimal('1.0')
   93:         if momentum_score > 0 and vol_mom_5m > 0:
   94:             volume_multiplier = vol_confirm
   95:         elif momentum_score < 0 and vol_mom_5m < 0:
   96:             volume_multiplier = vol_confirm
   97:         elif momentum_score != 0 and vol_mom_5m * momentum_score < 0:
   98:             volume_multiplier = vol_contradict
   99: 
  100:         momentum_score *= volume_multiplier
  101: 
  102:         # RSI-based confidence adjustment
  103:         rsi_overbought = Decimal(str(rsi_cfg.get("overbought", 70)))
  104:         rsi_oversold = Decimal(str(rsi_cfg.get("oversold", 30)))
  105:         rsi_penalty = Decimal(str(rsi_cfg.get("confidence_penalty", 0.7)))
  106: 
  107:         rsi_confidence = Decimal('1.0')
  108:         if rsi > rsi_overbought:
  109:             rsi_confidence = rsi_penalty
  110:         elif rsi < rsi_oversold:
  111:             rsi_confidence = rsi_penalty
  112: 
  113:         # MACD confirmation
  114:         macd_boost = Decimal(str(macd_cfg.get("confirm_boost", 1.1)))
  115:         macd_penalty = Decimal(str(macd_cfg.get("contradict_penalty", 0.9)))
  116: 
  117:         macd_confidence = Decimal('1.0')
  118:         if (momentum_score > 0 and macd_signal > 0) or (momentum_score < 0 and macd_signal < 0):
  119:             macd_confidence = macd_boost
  120:         elif macd_signal * momentum_score < 0:
  121:             macd_confidence = macd_penalty
  122: 
  123:         # Overall confidence based on signal consistency and filters
  124:         base_confidence = Decimal(str(conf_cfg.get("base", 0.8)))
  125:         consistency_factor = self._calculate_consistency(
  126:             mom_5m, mom_1h, mom_1d)
  127: 
  128:         confidence = min(Decimal('1.0'), base_confidence *
  129:                          rsi_confidence * macd_confidence * consistency_factor)
  130: 
  131:         # Clamp score to [-1, 1]
  132:         final_score = max(Decimal('-1.0'), min(Decimal('1.0'), momentum_score))
  133: 
```
2. `mean_reversion_v1`:
- ???????: `bb_signal`, `rsi_signal`, `sma_signal`, `stoch_signal`.
- `combined_score` ?? ?????? ???? + volume multiplier + BB width volatility multiplier.
```python
   83:         # BB position signal: 0 = lower band (strong buy), 1 = upper band (strong sell)
   84:         # Convert to [-1, 1] where -1 = strong buy, +1 = strong sell
   85:         bb_signal = (bb_pos - Decimal('0.5')) * \
   86:             Decimal('2')  # [0,1] -> [-1,1] centered on 0
   87: 
   88:         # RSI signal: oversold (buy), overbought (sell)
   89:         rsi_oversold = Decimal(str(rsi_cfg.get("oversold", 30)))
   90:         rsi_overbought = Decimal(str(rsi_cfg.get("overbought", 70)))
   91: 
   92:         rsi_signal = Decimal('0')
   93:         if rsi < rsi_oversold:
   94:             rsi_signal = -Decimal('1.0')  # Strong buy
   95:         elif rsi > rsi_overbought:
   96:             rsi_signal = Decimal('1.0')  # Strong sell
   97: 
   98:         # SMA deviation signal
   99:         sma_normalizer = Decimal(
  100:             str(sma_cfg.get("deviation_normalizer", 0.05)))
  101:         sma_signal = sma_dev / sma_normalizer
  102:         sma_signal = max(Decimal('-1.0'), min(Decimal('1.0'), sma_signal))
  103: 
  104:         # Stochastic signal: %K crossing %D
  105:         stoch_oversold_zone = Decimal(str(stoch_cfg.get("oversold_zone", 20)))
  106:         stoch_overbought_zone = Decimal(
  107:             str(stoch_cfg.get("overbought_zone", 80)))
  108:         stoch_strength = Decimal(str(stoch_cfg.get("signal_strength", 0.3)))
  109: 
  110:         stoch_signal = Decimal('0')
  111:         if stoch_k > stoch_d and stoch_k < stoch_oversold_zone:
  112:             stoch_signal = -stoch_strength
  113:         elif stoch_k < stoch_d and stoch_k > stoch_overbought_zone:
  114:             stoch_signal = stoch_strength
  115: 
  116:         # Combine signals with weights
  117:         weights = {
  118:             'bb': Decimal(str(weights_cfg.get("bb", 0.4))),
  119:             'rsi': Decimal(str(weights_cfg.get("rsi", 0.3))),
  120:             'sma': Decimal(str(weights_cfg.get("sma", 0.2))),
  121:             'stoch': Decimal(str(weights_cfg.get("stoch", 0.1)))
  122:         }
  123: 
  124:         combined_score = (
  125:             bb_signal * weights['bb'] +
  126:             rsi_signal * weights['rsi'] +
  127:             sma_signal * weights['sma'] +
  128:             stoch_signal * weights['stoch']
  129:         )
  130: 
  131:         # Volume confirmation
  132:         vol_confirm = Decimal(str(vol_cfg.get("confirm_multiplier", 1.2)))
  133:         vol_contradict = Decimal(
  134:             str(vol_cfg.get("contradict_multiplier", 0.8)))
  135:         vol_high_thr = Decimal(str(vol_cfg.get("high_threshold", 1.5)))
  136:         vol_low_thr = Decimal(str(vol_cfg.get("low_threshold", 0.7)))
  137: 
  138:         volume_multiplier = Decimal('1.0')
  139:         if abs(combined_score) > 0.2 and vol_ratio > vol_high_thr:
  140:             volume_multiplier = vol_confirm
  141:         elif abs(combined_score) > 0.2 and vol_ratio < vol_low_thr:
  142:             volume_multiplier = vol_contradict
  143: 
  144:         combined_score *= volume_multiplier
  145: 
  146:         # BB width filter
  147:         bbw_wide = Decimal(str(bbw_cfg.get("wide_threshold", 0.05)))
  148:         bbw_narrow = Decimal(str(bbw_cfg.get("narrow_threshold", 0.02)))
  149:         bbw_max_mult = Decimal(str(bbw_cfg.get("max_multiplier", 1.5)))
  150:         bbw_narrow_pen = Decimal(str(bbw_cfg.get("narrow_penalty", 0.7)))
  151: 
  152:         volatility_multiplier = Decimal('1.0')
  153:         if bb_width > bbw_wide:
  154:             volatility_multiplier = min(
  155:                 bbw_max_mult, bb_width / bbw_wide)
  156:         elif bb_width < bbw_narrow:
  157:             volatility_multiplier = bbw_narrow_pen
  158: 
  159:         combined_score *= volatility_multiplier
  160: 
  161:         # Clamp to [-1, 1]
  162:         final_score = max(Decimal('-1.0'), min(Decimal('1.0'), combined_score))
  163: 
```
3. `volatility_v1`:
- ???????: ATR ratio, BB width change, RV trend, range ratio, volume-volatility correlation.
- Weight mix + volatility level filter (low penalty/high boost).
```python
   89:         # ATR ratio signal: >1 = higher volatility, <1 = lower volatility
   90:         atr_signal = atr_ratio - Decimal('1.0')  # Center on 0
   91:         atr_signal = max(-atr_clamp, min(atr_clamp, atr_signal))
   92: 
   93:         # BB width change signal: positive = expanding, negative = contracting
   94:         bb_signal = bb_width_change * bb_amplifier
   95:         bb_signal = max(Decimal('-1.0'), min(Decimal('1.0'), bb_signal))
   96: 
   97:         # Realized volatility trend: 1h vs 1d
   98:         rv_trend = rv_1h - rv_1d  # Positive = increasing vol, negative = decreasing
   99:         rv_signal = rv_trend / max(rv_1d, Decimal('0.001'))  # Normalize
  100:         rv_signal = max(-rv_clamp, min(rv_clamp, rv_signal))
  101: 
  102:         # Range ratio signal
  103:         range_signal = range_ratio - Decimal('1.0')  # Center on 0
  104:         range_signal = max(Decimal('-1.0'), min(Decimal('1.0'), range_signal))
  105: 
  106:         # Volume-volatility correlation
  107:         vvol_high = Decimal(str(vvol_cfg.get("high_threshold", 1.2)))
  108:         vvol_low = Decimal(str(vvol_cfg.get("low_threshold", 0.8)))
  109:         vvol_strength = Decimal(str(vvol_cfg.get("signal_strength", 0.2)))
  110: 
  111:         vol_corr_signal = Decimal('0')
  112:         if vol_vol_ratio > vvol_high:
  113:             vol_corr_signal = vvol_strength
  114:         elif vol_vol_ratio < vvol_low:
  115:             vol_corr_signal = -vvol_strength
  116: 
  117:         # Combine signals with weights
  118:         weights = {
  119:             'atr': Decimal(str(weights_cfg.get("atr", 0.4))),
  120:             'bb': Decimal(str(weights_cfg.get("bb", 0.25))),
  121:             'rv': Decimal(str(weights_cfg.get("rv", 0.2))),
  122:             'range': Decimal(str(weights_cfg.get("range", 0.1))),
  123:             'vol_corr': Decimal(str(weights_cfg.get("vol_corr", 0.05)))
  124:         }
  125: 
  126:         combined_score = (
  127:             atr_signal * weights['atr'] +
  128:             bb_signal * weights['bb'] +
  129:             rv_signal * weights['rv'] +
  130:             range_signal * weights['range'] +
  131:             vol_corr_signal * weights['vol_corr']
  132:         )
  133: 
  134:         # Absolute volatility level filter
  135:         vol_low = Decimal(str(vlevel_cfg.get("low_level", 0.5)))
  136:         vol_low_pen = Decimal(str(vlevel_cfg.get("low_penalty", 0.5)))
  137:         vol_high = Decimal(str(vlevel_cfg.get("high_level", 2.0)))
  138:         vol_high_boost = Decimal(str(vlevel_cfg.get("high_boost", 1.2)))
  139: 
  140:         volatility_level = (atr_ratio + bb_width *
  141:                             Decimal('20') + rv_1h) / Decimal('3')
  142:         if volatility_level < vol_low:
  143:             combined_score *= vol_low_pen
  144:         elif volatility_level > vol_high:
  145:             combined_score *= vol_high_boost
  146: 
  147:         # Clamp to [-1, 1]
  148:         final_score = max(Decimal('-1.0'), min(Decimal('1.0'), combined_score))
  149: 
```
4. `aurora_v2_adapter`: ???????? kernel ? ???????? Aurora, fail-closed ??? missing essentials.
```python
  169:         # Check essential features
  170:         missing_essential = [
  171:             feat for feat in self._essential_features 
  172:             if feat not in features or features[feat] is None
  173:         ]
  174:         if missing_essential:
  175:             return self._fail_closed_score(
  176:                 symbol,
  177:                 reason="missing_essential_features",
  178:                 why=[f"Missing essential features: {missing_essential}"]
  179:             )
  180:         
  181:         # Get regime (default to "DEFAULT" if not provided)
  182:         regime = context.get("regime", "DEFAULT")
  183:         
  184:         # Run Aurora kernel
  185:         try:
  186:             result: ScoringResult = AuroraScoringKernel.compute(
  187:                 symbol=symbol,
  188:                 features=features,
  189:                 warmup_readiness=warmup_readiness,
  190:                 price=decimal.Decimal(str(price)),
  191:                 signal_weights=self._signal_weights,
  192:                 feature_neutrals=self._feature_neutrals,
  193:                 essential_features=self._essential_features,
  194:                 base_threshold=self._base_threshold,
  195:                 regime_name=regime,
  196:                 regime_thresholds=self._regime_thresholds,
  197:                 side_bias_state=None,  # No side bias for alpha_search
  198:                 direction_strength_cfg=self._direction_strength_cfg,
  199:                 delta_price_cap_pct=self._delta_price_cap_pct,
  200:                 scoring_version=self._scoring_version,
  201:                 neutral_threshold=None,
  202:                 current_side="",
  203:             )
```

### 4.2 Regime usage

- `AuroraAlphaAdapter` ???????????? `context.get("regime", "DEFAULT")`, ??? plugin ????? ??????? ?????? `{"mode":"backtest","shadow":...}` ??? regime (`apps/reference/domains/alpha_search/backtest_plugin.py:385`).
- ????? ? ????????? path alpha_search adapter ???????? ?????? ? regime=`DEFAULT` ???? regime ???? ?? injected.

### 4.3 Entry/exit, filters, gates

- Entry ? shadow plugin: ???? `abs(score) > threshold`, ????? `VIRTUAL_OPEN` (1 ???????/??????/provider).
- Exit ? shadow plugin: `max_bars` ??? `max_hold_sec` (`virtual_trader.exit`).
```python
  469:         # Virtual trader logic
  470:         if self.config.virtual_trader.enabled and current_price > 0:
  471:             self._manage_virtual_positions(
  472:                 provider_id=provider_id,
  473:                 symbol=symbol,
  474:                 current_price=current_price,
  475:                 current_ts=current_ts,
  476:             )
  477: 
  478:             # Entry logic
  479:             if abs(score.score) > Decimal(str(threshold)):
  480:                 self._maybe_open_virtual_position(
  481:                     provider_id=provider_id,
  482:                     symbol=symbol,
  483:                     score=score,
  484:                     current_price=current_price,
  485:                     current_ts=current_ts,
  486:                     signal_id=signal_id,
  487:                 )
```
```python
  601:             # Exit conditions
  602:             should_exit = (
  603:                 pos.bars_held >= exit_cfg.max_bars or
  604:                 duration_sec >= exit_cfg.max_hold_sec
  605:             )
  606: 
  607:             if should_exit:
  608:                 self._close_virtual_position(
  609:                     provider_id=provider_id,
  610:                     pos=pos,
  611:                     exit_price=current_price,
  612:                     exit_ts=current_ts,
  613:                 )
  614:                 positions.pop(i)
  615: 
```
- Main Aurora ??? ????????? gate-? ?? anti-churn, ???? ? alpha_search virtual plugin ?????:
- `holding_period.min_duration_sec=30`, `reentry_cooldown_sec=840`, `gates.anti_flat_sigma=0.48`, `gates.anti_fomo_sigma=10.5`, `motion_window_sec=300` (`config/aurora/strategies/aurora.yaml:136-156`).

### 4.4 ?? ?? ???? ????, ?? Aurora?

- ???????? ???????: `obi`, `delta_price`, `macro_resid` ??? `aurora_adapter` (same essential features).
- ?????? ??? TA ensemble: RSI/MACD/Stoch/BB/ATR/momentum features, ??? FE pass-through ????? ?????????? ??? alpha_search.
```python
  910:             # ALPHA-SEARCH SUPPORT: AUGMENTED FEATURE PASS-THROUGH
  911:             # ================================================================
  912:             # In backtest mode, BacktestEngine injects TA features (RSI, MACD etc)
  913:             # into the tick payload. FeatureEngineering natively ignores unknown keys.
  914:             # We explicitly pass them through here to ensure AlphaSearch receives them.
  915:             aug_keys = [
  916:                 "macd_line", "macd_signal", "macd_histogram",
  917:                 "stoch_k", "stoch_d",
  918:                 "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
  919:                 "volume_momentum_5m", "rsi_14",
  920:                 # Bollinger / volatility / SMA features
  921:                 "bb_position", "bb_width", "bb_width_change",
  922:                 "atr_14", "atr_ratio",
  923:                 "realized_volatility_1h", "realized_volatility_1d",
  924:                 "volume_volatility_ratio", "price_range_ratio",
  925:                 "price_sma_20_deviation", "volume_sma_ratio",
  926:             ]
  927:             for k in aug_keys:
  928:                 if k in current_tick and current_tick[k] is not None:
  929:                     # Keep as string to match FE string-heavy contract, or native float?
  930:                     # Alpha models cast strictly, so string is safest for parity with FE.
  931:                     features[k] = str(current_tick[k])
  932: 
```

## 5. Shadow Mode деталі

1. ?? ?????? shadow ????? ? `alpha_search`:
- `shadow_mode=true` ? ???????. Plugin ???????? alpha score ? ???? `SCORE_EMITTED` + `EVT:ALPHA_SCORE_CALCULATED`.
- ?????? ?? ??????? `TRADE_INTENT_PROPOSED` ?????.
- ???????? ???????? virtual trader (`VIRTUAL_OPEN`, `VIRTUAL_CLOSE`) ??? offline PnL.
2. ?? ??????? ?????? ?? ??????? ??????? testnet?
- ??? `alpha_search` ?????? ??????? (virtual).
- ???????? testnet execution ?????? ??????? Aurora (global mode `hybrid_live_data_testnet_exec`).
3. ?? ???????????? ?? ???????????? shadow-???????:
- `logs/domain_alpha_search.log` (structured events).
- `ops/wal/*.jsonl` ????? `AlphaScoreWalListener` (verb `ALPHA_SCORE_CALCULATED`).
- ?????????? ? main ? ????? ?????? ???????? ????? ??????????? `ALPHA_SCORE_CALCULATED` (aurora tf=300, directional) ????? `ORDER_INTENT` ??? `DecisionMaking` (rid `aurora_*`).
```python
   22:     def _register(self) -> None:
   23:         if hasattr(self.event_bus, "listen"):
   24:             self.event_bus.listen(
   25:                 "EVT:ALPHA_SCORE_CALCULATED", self._on_alpha_score
   26:             )
   27:             LOG.info("AlphaScoreWalListener registered")
   28: 
   29:     def _on_alpha_score(self, event: Any, **kwargs) -> None:
   30:         payload = event.pld if hasattr(event, "pld") else event
   31:         if not isinstance(payload, dict):
   32:             return
   33: 
   34:         try:
   35:             from vfoundation.dr import wal
   36: 
   37:             wal_record = {
   38:                 "op": "EVT",
   39:                 "verb": "ALPHA_SCORE_CALCULATED",
   40:                 "symbol": payload.get("symbol", ""),
   41:                 "provider_id": payload.get("provider_id", "unknown"),
   42:                 "model_name": payload.get("model_name", "unknown"),
   43:                 "score": payload.get("score", 0),
   44:                 "confidence": payload.get("confidence", 0),
   45:                 "ts_ms": payload.get("ts_ms", 0),
   46:                 "tf_sec": payload.get("tf_sec", 0),
   47:                 "bar_close_ts": payload.get("bar_close_ts", 0),
   48:                 "shadow": payload.get("shadow", True),
   49:                 "signal_id": payload.get("signal_id", ""),
   50:                 "why": "alpha_wal_listener",
   51:             }
   52:             wal.append(wal_record)
   53:             self._count += 1
```

## 6. Поточний стан (логи за останні 72 години)

### 6.1 ????? ?? ?????? `ALPHA_SEARCH`, `SHADOW_`, `shadow_decision`, `shadow_intent`

- Raw grep/rg hit-count ? `logs` + `ops/wal`: ??? 4 ??????? = `0` ??????.
- ???????: ???????? runtime ???? ?????????? ???? ???? `"shadow": true` ? event names (`SCORE_EMITTED`, `VIRTUAL_*`), ? ?? literal ?????? ? ??????.

### 6.2 ???????? ?????? 72h

| ??????? | ???????? | ??????? |
|---|---|---|
| Shadow signals (all providers) | `20422` | WAL `ALPHA_SCORE_CALCULATED` |
| Shadow signals aurora/ta_ensemble | `7658` / `12764` | WAL |
| Shadow intents ??? alpha_search | `0` | ???????????? ?? ??????? intents |
| Directional shadow (aurora tf=300) | `2317` | WAL + threshold=0.155 |
| Main Aurora intents (72h) | `425` | `logs/order_log_v1.jsonl` |
| Divergent vs main (no_intent+opposite) | `1829` / `2317` (`78.94%`) | matching by symbol/time |
| Side match with main | `488` | same method |
| Side opposite vs main | `89` | same method |
| No corresponding main intent | `1740` | same method |
| Shadow virtual closes (available alpha log window) | `117` | `logs/domain_alpha_search.log` |
| Shadow virtual win-rate (ex flats) | `52.14%` | same |
| Shadow virtual PnL | `-54.9451` USDT | same |
| Shadow local fill-rate (VIRTUAL_OPEN / directional scores in available alpha log window) | `8.87%` | same |
| Main intent->ORDER_PLACED rate (72h) | `17.65%` | `order_log_v1.jsonl` |

### 6.3 ??? ??????? ?? ??????

- Shadow top symbols (WAL): `[['ETHUSDT', 5106], ['BTCUSDT', 5106], ['SOLUSDT', 5104], ['DOGEUSDT', 2553], ['XRPUSDT', 2553]]`
- Aurora intent regimes (from WAL `data_ref` parsing): `[['MEAN_REVERSION', 324], ['HIGH_VOLATILITY', 42], ['UNCERTAIN', 35], ['LOW_VOLATILITY', 25]]`

### 6.4 ??? ?????? ????????????

| Reason | Count |
|---|---|
| `ARBITRATION_REJECT:symbol_not_in_registry` | `104` |
| `BLOCK_SAME_SIDE_PYRAMIDING` | `50` |
| `FLIP_OPEN_DEFERRED` | `23` |
| `SAFETY_DENY_NRR-029` | `19` |
| `SAFETY_DENY_NRR-028` | `1` |
| `SAFETY_DENY_NRR-030` | `1` |

### 6.5 ??????? ?????????????

- `config/aurora/strategies.yaml:26` -> `ETHUSDT: []` (??????? ???????????): ?? ???????? ??????? ?????? ?????? `ARBITRATION_REJECT:symbol_not_in_registry` ??? ETH.
- `decision_making._shadow_compare_kernel` ????? ???????? dead path (?? ????????????), ???? runtime ?? ???? `SHADOW_DIVERGENCE/SHADOW_MATCH` even when shadow compare expected.
- `domain_alpha_search.log` ?? ???????? ????? 72h (? ???? ??? ~10:45 UTC 2026-02-23), ???? virtual PnL/win-rate ???????? ?? ?????????? ????????, ? ????????? counts ?? 72h ????? ? WAL.

## 7. Порівняльна таблиця

| ????????? | Alpha_Search (Shadow) | ??????? Aurora | ??????? ??????????? |
|---|---|---|---|
| Signal Threshold | `aurora: 0.155`, `ta_ensemble: 0.18` | `signal_threshold: 0.162` | Shadow aurora ????? ??????? ?????; TA ensemble ??? ??????? ?????. |
| Regime Logic | Adapter ????????? regime, ??? plugin ?? ??????? regime -> ???????? `DEFAULT` | Regime-aware thresholds/sizing ? decision engine | ? shadow adapter regime path ???????????????? ? ????????? bridge context. |
| Holding Period | Virtual exit: `max_bars=12` ??? `max_hold_sec=3600` | `holding_period.min_duration_sec=30`, emergency threshold, plus runtime position logic | Shadow ??? ????????? synthetic lifecycle. |
| Reentry Cooldown | ???? ???????? cooldown gate, ???? `max_positions_per_symbol=1` | `reentry_cooldown_sec=840` (global) + per-asset overrides | Main Aurora ????????? ????-churn; shadow ???????? ?????????. |
| Anti-FOMO Sigma | ???? ?????? ?????????? ? plugin | `anti_fomo_sigma=10.5`, `anti_flat_sigma=0.48` | Main ??? sigma-gates, shadow ??. |
| Features | Shared core (`obi`, `delta_price`, `macro_resid`) + TA-only features | Core Aurora features + strategy-specific signals | Shadow TA ensemble ???????????? ????????? FE pass-through ????. |
| Decision Output | `EVT:ALPHA_SCORE_CALCULATED` + virtual events | `EVT:TRADE_INTENT_PROPOSED` -> execution | Shadow ?? ??????? ??????? ?? ??????. |
| Execution | Virtual only (`VIRTUAL_OPEN/CLOSE`) | ???????? testnet execution ? hybrid mode | Shadow ?? ??????? ?????? ?? ?????. |
| WAL Trace | `ALPHA_SCORE_CALCULATED` by `alpha_search` listener | `TRADE_INTENT_PROPOSED`, order lifecycle | ?????????? ??????? ?????????? ????? WAL join, ?? inline gate. |
| Divergence (72h) | `1829/2317` directional aurora-tf300 shadow signals divergent vs main | n/a | ??????? ???????: no main intent + arbitration rejects/block gates. |

## Ключові фрагменти (forensic extracts)

### Emit fail-closed score
```python
  542:     def _emit_fail_closed_score(
  543:         self,
  544:         provider_id: str,
  545:         symbol: str,
  546:         tf_sec: int,
  547:         bar_close_ts: int
  548:     ) -> None:
  549:         """Emit fail-closed score (score=0) when features unavailable."""
  550:         payload = {
  551:             "provider_id": provider_id,
  552:             "model_name": f"{provider_id}_fail_closed",
  553:             "symbol": symbol,
  554:             "tf_sec": tf_sec,
  555:             "bar_close_ts": bar_close_ts,
  556:             "score": 0.0,
  557:             "confidence": 0.0,
  558:             "threshold": self.provider_configs[provider_id].threshold,
  559:             "shadow": True,
  560:             "signal_id": "",
  561:             "why": ["fail_closed:missing_features_for_bar"],
  562:             "features_used": [],
  563:         }
  564: 
  565:         self.event_bus.emit(
  566:             event_name=self.config.triggers.emit_event,
  567:             payload=payload,
  568:             why=f"alpha_search_{provider_id}_fail_closed"
  569:         )
  570: 
  571:         self.dlog.write(
  572:             event="FAIL_CLOSED",
  573:             provider_id=provider_id,
  574:             symbol=symbol,
  575:             payload={"reason": "missing_features_for_bar", "tf_sec": tf_sec, "bar_close_ts": bar_close_ts},
  576:         )
```
### Virtual trader open/close
```python
  616:     def _maybe_open_virtual_position(
  617:         self,
  618:         provider_id: str,
  619:         symbol: str,
  620:         score: AlphaScore,
  621:         current_price: float,
  622:         current_ts: int,
  623:         signal_id: str,
  624:     ) -> None:
  625:         """Open virtual position if allowed."""
  626:         positions = self.open_positions[provider_id]
  627:         max_per_symbol = self.config.virtual_trader.max_positions_per_symbol
  628: 
  629:         # Check existing positions for this symbol
  630:         existing = sum(1 for p in positions if p.symbol == symbol)
  631:         if existing >= max_per_symbol:
  632:             return
  633: 
  634:         side = "BUY" if score.score > 0 else "SELL"
  635: 
  636:         positions.append(VirtualPosition(
  637:             provider_id=provider_id,
  638:             symbol=symbol,
  639:             side=side,
  640:             entry_price=current_price,
  641:             entry_ts=current_ts,
  642:             signal_id=signal_id,
  643:         ))
  644: 
  645:         self.dlog.write(
  646:             event="VIRTUAL_OPEN",
  647:             provider_id=provider_id,
  648:             symbol=symbol,
  649:             payload={"side": side, "entry_price": current_price},
  650:             signal_id=signal_id,
  651:         )
  652: 
  653:         LOG.debug(
  654:             f"[{symbol}] {provider_id} OPEN VIRTUAL {side} @ {current_price}")
  655: 
  656:     def _close_virtual_position(
  657:         self,
  658:         provider_id: str,
  659:         pos: VirtualPosition,
  660:         exit_price: float,
  661:         exit_ts: int,
  662:     ) -> None:
  663:         """Close virtual position and record PnL."""
  664:         # Calculate PnL
  665:         if pos.side == "BUY":
  666:             pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
  667:         else:
  668:             pnl_pct = (pos.entry_price - exit_price) / pos.entry_price
  669: 
  670:         notional_pnl = pnl_pct * self.config.virtual_trader.notional_size
  671: 
  672:         # Update stats
  673:         stats = self.provider_stats[provider_id]
  674:         stats.total_pnl += notional_pnl
  675:         stats.trades_closed += 1
  676:         if notional_pnl > 0:
  677:             stats.wins += 1
  678: 
  679:         # Record closed position
  680:         closed_record = {
  681:             "provider_id": provider_id,
  682:             "symbol": pos.symbol,
  683:             "side": pos.side,
  684:             "entry_price": pos.entry_price,
  685:             "exit_price": exit_price,
  686:             "entry_ts": pos.entry_ts,
  687:             "exit_ts": exit_ts,
  688:             "bars_held": pos.bars_held,
  689:             "pnl": notional_pnl,
  690:             "signal_id": pos.signal_id,
  691:         }
  692:         self.closed_positions[provider_id].append(closed_record)
  693: 
  694:         self.dlog.write(
  695:             event="VIRTUAL_CLOSE",
  696:             provider_id=provider_id,
  697:             symbol=pos.symbol,
  698:             payload={
  699:                 "side": pos.side,
  700:                 "entry_price": pos.entry_price,
  701:                 "exit_price": exit_price,
  702:                 "bars_held": pos.bars_held,
  703:                 "pnl": round(notional_pnl, 4),
  704:             },
  705:             signal_id=pos.signal_id,
  706:         )
```
### DM alpha registry + dm_inline emit path
```python
   77: # Import alpha models
   78: try:
   79:     from apps.reference.domains.alpha_search import (
   80:         AlphaModelRegistry,
   81:         MomentumAlphaModel,
   82:         MeanReversionAlphaModel,
   83:         VolatilityAlphaModel
   84:     )
   85:     ALPHA_MODELS_AVAILABLE = True
```
```python
  212:         # Initialize alpha model registry
  213:         self.alpha_registry = None
  214:         if ALPHA_MODELS_AVAILABLE:
  215:             self.alpha_registry = AlphaModelRegistry()
  216:             # Register baseline models
  217:             self.alpha_registry.register(MomentumAlphaModel())
  218:             self.alpha_registry.register(MeanReversionAlphaModel())
  219:             self.alpha_registry.register(VolatilityAlphaModel())
  220:             self.logger.info(
  221:                 f"Alpha models initialized: {self.alpha_registry.list_models()}")
  222:         else:
  223:             self.logger.warning(
  224:                 "Alpha models not available - alpha_search module not found")
```
```python
 2164:             # Calculate alpha scores if alpha models are available
 2165:             if self.alpha_registry and feats:
 2166:                 try:
 2167:                     alpha_scores = self.alpha_registry.calculate_all_alpha(
 2168:                         symbol, {"current_price": feats.get("price")}, feats
 2169:                     )
 2170:                     if alpha_scores:
 2171:                         # Extract event context for unified payload
 2172:                         _pld = event.pld if isinstance(event.pld, dict) else {}
 2173:                         _tf_sec = _pld.get("tf_sec", 300)
 2174:                         _bar_close_ts = _pld.get("bar_close_ts", 0)
 2175:                         _ts_ms = self._clock.now_ms()
 2176: 
 2177:                         # Emit one event per score (unified schema)
 2178:                         for score in alpha_scores:
 2179:                             alpha_payload = {
 2180:                                 "symbol": symbol,
 2181:                                 "ts_ms": _ts_ms,
 2182:                                 "tf_sec": _tf_sec,
 2183:                                 "bar_close_ts": _bar_close_ts,
 2184:                                 "provider_id": "dm_inline",
 2185:                                 "model_name": score.model_name,
 2186:                                 "score": float(score.score),
 2187:                                 "confidence": float(score.confidence),
 2188:                                 "threshold": 0.1,
 2189:                                 "shadow": False,
 2190:                                 "signal_id": f"dm_{symbol}_{score.model_name}_{_ts_ms}",
 2191:                                 "features_used": score.features_used,
 2192:                                 "why": score.why[:10],
 2193:                             }
 2194:                             self.fsm.emit(
 2195:                                 "EVT:ALPHA_SCORE_CALCULATED",
 2196:                                 payload=alpha_payload,
 2197:                                 why=f"alpha_score:{score.model_name}",
 2198:                                 data_ref=[f"model_{score.model_name}"],
 2199:                             )
```
### Verb registry entry
```yaml
   69: - op: EVT
   70:   verb: ALPHA_SCORE_CALCULATED
   71:   owner: alpha_search
   72:   status: active
   73:   schema: null
   74:   since: '2026-01-08'
```

## Висновки, ризики та next steps

- `docs/alpha_search_forensic_metrics_72h.json` (machine-readable metrics used in this report).
- `docs/ALPHA_SEARCH_FORENSIC_AUDIT.md` (??? ?????? ????).
