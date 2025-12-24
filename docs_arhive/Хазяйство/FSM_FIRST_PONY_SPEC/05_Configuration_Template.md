# 05 Configuration Template — Параметри для Тюнінгу

**Мета**: Повна YAML структура для налаштування режимної детекції, Kelly калькулятора, ризик-обмежень.

**Дата**: 3 листопада 2025 | **Статус**: ✅ DRAFT

---

## 📋 FULL CONFIGURATION REFERENCE

```yaml
# ═══════════════════════════════════════════════════════════════════════════
# AURORA TRADING CONFIGURATION v1.0
# For: First Pony Spec (Range-Scalp with Regime FSM on M15)
# Mode: testnet (live market data, testnet execution)
# ═══════════════════════════════════════════════════════════════════════════

trading:
  mode: "testnet"  # Valid: "testnet", "production"

  # ═══════════════════════════════════════════════════════════════════════
  # DECISION MAKING SETTINGS
  # ═══════════════════════════════════════════════════════════════════════

  decision:
    # Signal composition weights (must sum to 1.0)
    signal_weights:
      obi: 0.6           # Order Book Imbalance: [0.3, 0.7]
      tfi: 0.35          # Trade Flow Imbalance: [0.2, 0.6]
      delta_price: 0.05  # Price change component: [0.05, 0.2]

    # Entry threshold (minimum signal score required)
    signal_threshold: 0.15  # ϑ: [0.12, 0.35]

    # Cooldown after decision
    cooldown_sec: 10    # [5, 20] seconds between decisions per symbol

    # Position sizing
    position_sizing:
      min_position_size_usd: 10      # Minimum notional USD
      liquidity_based_cap_usd: 10000 # Maximum notional USD
      max_single_position_pct: 0.01  # Max 1% of equity per position

    # ═════════════════════════════════════════════════════════════════════
    # REGIME-ADAPTIVE SIZING MODIFIERS
    # Applied after Kelly fraction calculation
    # ═════════════════════════════════════════════════════════════════════
    sizing_modifiers:
      HIGH_VOLATILITY: "0.60"    # -40% in high vol (reduce risk)
      LOW_VOLATILITY: "1.20"     # +20% in calm market (increase exposure)
      MEAN_REVERSION: "0.50"     # -50% in ranging (reduced edge)
      UNCERTAIN: "0.50"          # -50% when confidence low
      TREND_UP: "1.00"           # No modifier (baseline)
      TREND_DOWN: "1.00"         # No modifier (baseline)

    # QoS (Quality of Service) settings
    qos:
      mode: "defer"              # "defer" intents instead of blocking
      enforce: false             # Disable enforcement for testnet
      exposure_block_cooldown_sec: 30
      symbol_cooldown_sec: 0.5   # [0.1, 2.0] seconds
      max_intents_per_minute_per_symbol: 60  # Rate limit

  # ═════════════════════════════════════════════════════════════════════
  # KELLY CRITERION SETTINGS
  # ═════════════════════════════════════════════════════════════════════

  kelly:
    base_probability: 0.50  # Base win rate (neutral)
    payoff_ratio_r: 1.5     # TP/SL ratio (configurable per regime)
    kelly_cap: 0.25         # Maximum Kelly fraction [0.1, 0.3]
    kelly_alpha: 0.80       # Conservative scaling [0.5, 1.0]
    # Usage: kelly_fraction = min(kelly_cap, kelly_alpha * full_kelly)

  # ═════════════════════════════════════════════════════════════════════
  # INSTRUMENT SPECIFICATIONS (BINANCE FUTURES)
  # ═════════════════════════════════════════════════════════════════════

  instruments:
    BTCUSDT:
      step_size: "0.00001"  # Minimum order increment
      min_notional: "10"    # Minimum order value (USD)
      leverage_default: 2   # Default leverage
    ETHUSDT:
      step_size: "0.001"
      min_notional: "10"
      leverage_default: 2

  # ═════════════════════════════════════════════════════════════════════
  # MARKET REGIME DETECTION (RegimeDetector Domain)
  # ═════════════════════════════════════════════════════════════════════

  models:
    # Volatility-based regime detection (ATR)
    volatility:
      enabled: true
      atr_period: 14              # ATR lookback window
      threshold_multiplier: 2.0   # HIGH_VOLATILITY: ATR > 2.0 × SMA(ATR)
      low_vol_multiplier: 0.5     # LOW_VOLATILITY: ATR < 0.5 × SMA(ATR)
      sma_period: 100             # SMA(ATR) window for normalization

    # SMA Trend-following detection
    sma_trend:
      enabled: true
      short_period: 20    # Short SMA (fast)
      long_period: 50     # Long SMA (slow)
      # TREND_UP: short > long ∧ price > short
      # TREND_DOWN: short < long ∧ price < short

    # Mean reversion detection
    mean_reversion:
      enabled: true
      threshold: 0.005    # [0.002, 0.010] — tolerance for tight clustering
      # Detected when: sma_spread < threshold ∧ price_deviations < threshold

    # Tension Index (future enhancement)
    tension_index:
      enabled: false  # Planned for Phase 2
      beta_weights:
        delta_oi: 0.25    # ΔOI component
        funding: 0.25     # Funding rate component
        ls_ratio: 0.25    # Long/Short ratio component
        squeeze: 0.15     # Squeeze indicator
        phase: 0.10       # Intra-bar phase weight

  # ═════════════════════════════════════════════════════════════════════
  # RISK MANAGEMENT SETTINGS
  # ═════════════════════════════════════════════════════════════════════

  risk:
    # Risk score components (TRADE mode weights)
    score_weights:
      delta_price: 0.05
      obi: 0.35
      tfi: 0.35
      absorption_inverse: 0.25

    # Daily risk gates
    daily:
      max_realized_loss_usd: 250.0     # Stop trading after -$250
      max_drawdown_pct: 8.0            # Stop trading at 8% DD from daily open
      max_trades_per_day: 96           # Max trades in 24h (one per M15 bar)
      reset_time_utc: "00:00"          # Reset daily limits at UTC midnight

    # Intra-trade risk thresholds
    trading_allowed_thresholds:
      max_risk_score: 0.90             # Testnet: higher tolerance

  # ═════════════════════════════════════════════════════════════════════
  # TAKE-PROFIT & STOP-LOSS STRATEGY
  # ═════════════════════════════════════════════════════════════════════

  execution:
    # Default order type for opening positions
    open_order_type: "MARKET"  # "MARKET", "LIMIT"

    # Stop-loss setting
    sl:
      bps: 60                  # SL_bps ∈ [40, 120] basis points
      mode: "static"           # "static" (fixed), "atr-based" (adaptive)

    # Take-profit strategy
    tp:
      low_ratio: 0.60          # k₁: TP_low = 0.60 × SL_bps (60% of SL)
      high_ratio: 1.00         # k₂: TP_high = 1.00 × SL_bps (full SL ratio)
      partial_close_fraction: 0.50  # φ: Close 50% at TP_low

    # Trailing stop for remaining position
    trail:
      enabled: true
      start_threshold_bps: 10  # Start trail after +10 bps profit
      trail_stop_bps: 5        # Move SL up by 5 bps on each new high
      # Formula: TrailStop(t) = max(BE, max_price(t) - λ_trail)

    # Auto-trading management
    manage:
      auto: true               # Enable automatic TP/SL management

    # Portfolio exposure gate (critical for leverage)
    exposure:
      max_equity_utilization_pct: 0.40  # Max 40% of equity in notional
      max_portfolio_fraction: 0.20       # Max 20% of free equity
      count_pending_orders: true         # Include pending orders in limit
      exclude_reduce_only: true          # Exclude reduce-only orders
      pending_reservation_ttl_sec: 45    # Clean stale reservations
      leverage_defaults:
        BTCUSDT: 2
        ETHUSDT: 2
        __default__: 1

  # ═════════════════════════════════════════════════════════════════════
  # DOMAIN-LEVEL CONFIGURATION
  # ═════════════════════════════════════════════════════════════════════

  domain_configuration:
    # Data sources: READ from live market
    market_data:
      trading_mode: "live"  # Read LIVE Binance data

    feature_engineering:
      trading_mode: "live"  # Process live features

    decision_making:
      trading_mode: "live"  # Make decisions on live signals

    risk_management:
      trading_mode: "live"  # Risk scoring on live data

    # Execution: WRITE to testnet (safety!)
    execution_position:
      trading_mode: "testnet"  # Place orders on TESTNET

    audit_trail:
      trading_mode: "live"  # Log from live data

# ═══════════════════════════════════════════════════════════════════════
# BINANCE API CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    api_secret: "${BINANCE_FUTURES_API_SECRET_LIVE}"
    rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
    ws_url: "wss://fstream.binance.com"

  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
```

---

## 🎯 ПАРАМЕТРИ ДЛЯ ТЮНІНГУ (§18)

### Рекомендовані Діапазони

| Параметр | Мінімум | Максимум | Дефолт | Вплив |
|----------|---------|---------|--------|--------|
| **w₁ (OBI)** | 0.3 | 0.7 | 0.6 | Вищий вплив на бук-дисбалланс |
| **w₂ (TFI)** | 0.2 | 0.6 | 0.35 | Вищий вплив на потік |
| **w₃ (ΔP)** | 0.05 | 0.2 | 0.05 | Мінімальний вплив |
| **ϑ (threshold)** | 0.12 | 0.35 | 0.15 | ↑ = менше входів, ↓ = більше входів |
| **SL (bps)** | 40 | 120 | 60 | ↑ = менший Kelly, ↓ = більший Kelly |
| **TP_low ratio** | 0.5 | 0.8 | 0.60 | ↑ = раніше закриття, ↓ = більший профіт |
| **TP_high ratio** | 0.8 | 1.5 | 1.00 | Максимальна мета прибутку |
| **κ_regime[HIGH_VOL]** | 0.5 | 0.8 | 0.60 | ↓ = більш консервативно у волі |
| **κ_regime[LOW_VOL]** | 1.0 | 1.5 | 1.20 | ↑ = агресивніше у спокої |
| **kelly_alpha** | 0.5 | 1.0 | 0.80 | ↓ = більш консервативно |
| **ATR_threshold** | 1.5 | 2.5 | 2.0 | Поріг HIGH_VOLATILITY |
| **max_dd_daily** | 5% | 15% | 8% | ↓ = більш захисна торгівля |

---

## 🔧 КОМБІНАЦІЇ ДЛЯ РІЗНИХ СЦЕНАРІЇВ

### Сценарій 1: CONSERVATIVE (Низький ризик)
```yaml
decision:
  signal_weights:
    obi: 0.7
    tfi: 0.2
    delta_price: 0.1
  signal_threshold: 0.25  # Вищий поріг = менше входів
  sizing_modifiers:
    HIGH_VOLATILITY: "0.40"  # -60%
    LOW_VOLATILITY: "0.80"   # -20%
    MEAN_REVERSION: "0.30"   # -70%

execution:
  sl:
    bps: 40  # Жорсткіше
  tp:
    low_ratio: 0.80   # Скоріше закриття
```

**Очікуваний результат**: Менше (20-30) входів на день, вищий win rate, менший profit/trade

---

### Сценарій 2: BALANCED (Середній ризик)
```yaml
# Use defaults from above configuration
```

**Очікуваний результат**: 50-80 входів на день, moderate win rate, balanced profit

---

### Сценарій 3: AGGRESSIVE (Високий ризик)
```yaml
decision:
  signal_weights:
    obi: 0.5
    tfi: 0.4
    delta_price: 0.1
  signal_threshold: 0.10  # Нижчий поріг = більше входів
  sizing_modifiers:
    HIGH_VOLATILITY: "0.80"  # -20%
    LOW_VOLATILITY: "1.50"   # +50%
    MEAN_REVERSION: "0.70"   # -30%

execution:
  sl:
    bps: 100  # Ширший SL
  tp:
    low_ratio: 0.50   # Довше утримання
```

**Очікуваний результат**: 100+ входів на день, нижчий win rate, вищий profit/trade (якщо успішна)

---

## 📊 VALIDATION CHECKLIST

Перед запуском:

```
Configuration Validation
─────────────────────────
☐ signal_weights sum to 1.0
  └ w₁ + w₂ + w₃ = 1.0

☐ All regime_modifiers ∈ [0.3, 1.5]
  └ Консервативні скорочення (0.3-0.7)
  └ Агресивні збільшення (1.1-1.5)

☐ kelly_alpha ∈ (0.5, 1.0]
  └ > 0.5: консервативно
  └ ≈ 1.0: full Kelly

☐ SL_bps ∈ [40, 120]
  └ Мінімум для на точність, максимум для volatility

☐ max_dd_daily ≤ 10%
  └ Safety constraint

☐ max_equity_utilization ≤ 50%
  └ Leverage safety
```

---

## 📝 ВИСНОВОК

Ця конфігурація містить:
- ✅ Всі параметри § 18 (діапазони)
- ✅ Рекомендовані дефолти
- ✅ Три готові сценарії (Conservative, Balanced, Aggressive)
- ✅ Validation checklist

**Наступний крок**: Перейти до `06_Validation_Criteria.md` для валідації результатів.

