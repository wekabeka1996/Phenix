# 02 Architecture Mapping — Як Специфіка Реалізована в Проекті

**Мета**: Прямий маппінг математичної специфіки на домени, FSM потоки та потік подій.

**Дата**: 3 листопада 2025 | **Статус**: ✅ DRAFT

---

## 🏗️ АРХІТЕКТУРНА ТОПОЛОГІЯ

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AURORA+vFoundation FSM Network                     │
└──────────────────────────────────────────────────────────────────────┘

┌─ MARKET DATA LAYER ──────────────────────────────────────────────────┐
│ binance_adapter (REST/WS)                                             │
│     ↓ OHLCV + Orderbook + Funding                                     │
│ market_data domain                                                    │
│     ↓ EVT:MARKET_TICK_RECEIVED (every ~500ms)                         │
└──────────────────────────────────────────────────────────────────────┘

┌─ FEATURE ENGINEERING LAYER ──────────────────────────────────────────┐
│ feature_engineering domain                                           │
│     ← EVT:MARKET_TICK_RECEIVED                                        │
│     ↓ Calc OBI, TFI, ΔP, absorption (за кожен тік)                    │
│     ↓ Агрегація за 15-хв бар                                          │
│     ↓ EVT:FEATURES_CALCULATED                                         │
└──────────────────────────────────────────────────────────────────────┘

┌─ REGIME DETECTION LAYER ─────────────────────────────────────────────┐
│ regime_detector domain                                               │
│     ← EVT:FEATURES_CALCULATED                                        │
│     ↓ Calc T_s(t): Tension Index (ATR ratio + SMA crossover)          │
│     ↓ Determine regime: TREND_UP/DOWN, HIGH_VOL/LOW_VOL, etc.         │
│     ↓ EVT:REGIME_DETECTED (regime, confidence, source_model)         │
└──────────────────────────────────────────────────────────────────────┘

┌─ DECISION MAKING LAYER ──────────────────────────────────────────────┐
│ decision_making domain                                               │
│     ← EVT:FEATURES_CALCULATED (S_s(t))                                │
│     ← EVT:REGIME_DETECTED (ℳ(t))                                      │
│     ← EVT:RISK_ASSESSMENT_COMPLETED (risk score)                      │
│     ← EVT:PORTFOLIO_STATE_UPDATED (E(t), positions)                   │
│                                                                       │
│  1. REGIME FILTER: Block counter-trend (TREND_UP blocks SELL)        │
│  2. SIGNAL CHECK: S_s(t) ≥ ϑ?                                         │
│  3. KELLY CALC: kelly_fraction = f(p, r)                              │
│  4. SIZING: position_size × κ_regime                                   │
│  5. WHY-CHAIN: Log all decision parameters                            │
│                                                                       │
│     ↓ DEC:TRADE_INTENT_PROPOSED (if pass all checks)                 │
└──────────────────────────────────────────────────────────────────────┘

┌─ EXECUTION LAYER (3 Flows) ──────────────────────────────────────────┐
│ execution_position domain (FSM wrapper)                              │
│     ← DEC:TRADE_INTENT_PROPOSED                                       │
│                                                                       │
│  ┌─ OPEN FLOW ──────────────────────────────────────────────────┐   │
│  │ - Validate intent (anti-fraud, notional cap)                 │   │
│  │ - Calculate SL/TP prices                                     │   │
│  │ - Send order to Binance (MARKET or LIMIT)                    │   │
│  │ - DEC:PLACE_ORDER                                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─ MANAGE FLOW ─────────────────────────────────────────────────┐  │
│  │ - Receive EVT:PARTIAL_FILL / EVT:FILL                        │  │
│  │ - Track bracket orders (SL + TP)                             │  │
│  │ - Check rules: Trail, Breakeven, Time Stop                   │  │
│  │ - DEC:ADJUST (for trailing stop updates)                     │  │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─ CLOSE FLOW ──────────────────────────────────────────────────┐  │
│  │ - TP hit? → Close full position                              │  │
│  │ - SL hit? → Close full position                              │  │
│  │ - Partial exit? → Close fraction φ, trail rest               │  │
│  │ - Manual close? → Close remaining                            │  │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│     ↓ EVT:ORDER_ACK, EVT:ORDER_FILL (async)                           │
└──────────────────────────────────────────────────────────────────────┘

┌─ PORTFOLIO TRACKING & AUDIT ─────────────────────────────────────────┐
│ position_tracking domain                                             │
│ account_balance domain                                               │
│ audit_trail (DecisionLog, OrderLogger)                               │
│     ← All events above                                                │
│     ↓ WAL (Write-Ahead Log) for DR                                    │
│     ↓ Correlation store for why-chain                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 📊 ТАБЛИЦЯ ДОМЕНІВ & ВІДПОВІДАЛЬНОСТЕЙ

| Домен | Файл | Вхід | Вихід | Відповідальність |
|-------|------|------|-------|------------------|
| **Market Data** | `market_data/` | Binance REST/WS | EVT:MARKET_TICK | Потік даних M15 |
| **Feature Eng** | `feature_engineering/` | EVT:MARKET_TICK | EVT:FEATURES_CALC | OBI, TFI, ΔP компьютинг |
| **Regime Detector** | `regime_detector/` | EVT:FEATURES_CALC | EVT:REGIME_DETECTED | T_s(t), ℳ(t) визначення |
| **Decision Making** | `decision_making/` | EVT:FEATURES/REGIME/RISK/PORT | DEC:TRADE_INTENT | Вхід/сайзинг/Kelly |
| **Risk Management** | `risk_management/` | EVT:PORTFOLIO | EVT:RISK_ASSESS | CVaR, MaxDD, скоринг |
| **Execution Pos** | `execution_position/fsm.py` | DEC:TRADE_INTENT | EVT:ORDER_ACK/FILL | Open/Manage/Close flows |
| **Position Tracking** | `position_tracking/` | EVT:FILL | EVT:PORTFOLIO | Портфель синхронізація |

---

## 🔄 EVENT FLOW: ВІД ТИКУ ДО РЕШЕННЯ

### Сценарій: TREND_UP Режим + Сильний OBI Сигнал

```
t=0: Binance WS tick arrives
     price = 3950, bid_size = 10, ask_size = 5, buy_vol = 100, sell_vol = 40

     ↓ market_data emits EVT:MARKET_TICK_RECEIVED

t=5ms: feature_engineering receives event
       obi = (10-5)/(10+5) = 0.33
       tfi = (100-40)/(100+40) = 0.43
       delta_price = (3950 - 3940) = 10

       ↓ feature_engineering emits EVT:FEATURES_CALCULATED
       payload: {symbol, ts, features: {obi, tfi, delta_price, price, sma_short, sma_long, atr_14, ...}}

t=10ms: regime_detector receives event
        sma_short = 3960, sma_long = 3900
        atr_14 = 8, atr_14_sma_100 = 4

        # Detection logic:
        atr_ratio = 8 / 4 = 2.0  ≥ threshold_multiplier (2.0)
        regime = "HIGH_VOLATILITY" (Priority 1)

        BUT: Check trend as fallback
        sma_short (3960) > sma_long (3900) ✓ AND price (3950) > sma_short (3960) ✗
        regime = "TREND_UP_WITH_HIGH_VOL" (composite)

        ↓ regime_detector emits EVT:REGIME_DETECTED
        payload: {symbol, ts, regime: "TREND_UP", confidence: 0.82, source_model: "sma_trend_v1"}

t=15ms: decision_making receives EVT:FEATURES_CALCULATED
        ├─ Update symbol_states[BTCUSDT]["features"] = event.pld
        ├─ Alpha score calculation (if available)
        └─ Trigger _check_and_trigger_decision_for_symbol("BTCUSDT")

t=20ms: decision_making receives EVT:REGIME_DETECTED
        ├─ Update latest_regime = event.pld
        └─ Trigger _check_and_trigger_decision_for_symbol("BTCUSDT")  # again!

t=25ms: decision_making._try_make_decision() executes
        ├─ [Regime Filter] TREND_UP + side="buy" → ALLOW (not counter-trend)
        ├─ [Signal Score] S = 0.6×0.33 + 0.35×0.43 + 0.05×norm(10) = 0.34 ≥ 0.15 ✓
        ├─ [Size Calc]
        │  ├─ base_size = 100 (from Kelly)
        │  ├─ HIGH_VOLATILITY multiplier = 0.60
        │  ├─ adjusted_size = 100 × 0.60 = 60
        │  └─ qty_raw = 60 / 3950 = 0.0152 contracts
        ├─ [Why-Chain Logging]
        │  └─ ψ(t) = [0.33, 0.43, 0.05, ..., "TREND_UP", "HIGH_VOLATILITY"]
        └─ ✓ EMIT DEC:TRADE_INTENT_PROPOSED
           payload: {
               symbol: "BTCUSDT",
               side: "buy",
               qty: "0.0152",
               entry_price: 3950,
               sl_price: 3890,  # -60 bps
               tp_low: 3986,    # +36 bps (60% of 60)
               tp_high: 4010,   # +60 bps
               kelly_fraction: 0.08,
               signal_score: 0.34,
               regime: "TREND_UP",
               confidence: 0.82,
               why_chain: {...}  # Full reason
           }

t=30ms: execution_position/fsm.py receives DEC:TRADE_INTENT_PROPOSED
        ├─ OpenFlowFSM validates intent
        ├─ Check exposure guard (20% max)
        ├─ Generate client_order_id = hash(scope+verb+ts)
        └─ Emit DEC:PLACE_ORDER
           payload: {
               symbol: "BTCUSDT",
               side: "BUY",
               type: "MARKET",
               quantity: 0.0152,
               client_order_id: "intent_20251103_abc123..."
           }

t=35ms: BinanceExecutionAdapter.place_order()
        ├─ Send to Binance REST API
        ├─ Receive order_id = "123456789"
        └─ Emit EVT:ORDER_ACK

t=200ms: Binance WebSocket FILL
         ├─ qty_filled = 0.0152, fill_price = 3951
         ├─ event_handler in ExecPosFSM
         └─ Emit EVT:ORDER_FILL

t=205ms: ManageFlowFSM receives EVT:ORDER_FILL
         ├─ Update position_qty = 0.0152, entry_price = 3951
         ├─ Place bracket orders:
         │  ├─ SL: SELL 0.0152 @ 3891 (STOP_MARKET)
         │  └─ TP₁: SELL 0.00912 @ 3987 (60% at low TP, then trail)
         └─ Update state → TRACKING

... (position management continues via TrailingStop rules)
```

---

## 📍 РЕЖИМНА ДЕТЕКЦІЯ — ДЕТАЛЬНА ЛОГІКА

### Алгоритм в `regime_detector.py`

```python
def handle_event(event: Message) -> None:
    """
    Detect regime from features with priority-based logic.

    PRIORITY ORDER:
    1. HIGH_VOLATILITY / LOW_VOLATILITY (ATR-based)
    2. MEAN_REVERSION (SMA clustering)
    3. TREND_UP / TREND_DOWN (SMA crossover)
    → Default: UNCERTAIN
    """

    # Extract features
    features = event.pld.get("features", {})
    price = Decimal(features["price"])
    sma_short = Decimal(features["sma_short"])
    sma_long = Decimal(features["sma_long"])
    atr_14 = Decimal(features.get("atr_14", 0))
    atr_14_sma_100 = Decimal(features.get("atr_14_sma_100", 0))

    regime = "UNCERTAIN"
    confidence = Decimal("0.5")
    source_model = "default"

    # ═══════════════════════════════════════════════════════════════════
    # PRIORITY 1: Volatility Regimes
    # ═══════════════════════════════════════════════════════════════════

    volatility_config = config.get("models", {}).get("volatility", {})

    if volatility_config.get("enabled") and atr_14_sma_100 > 0:
        threshold_multiplier = Decimal(str(volatility_config.get("threshold_multiplier", 2.0)))
        low_vol_multiplier = Decimal(str(volatility_config.get("low_vol_multiplier", 0.5)))

        atr_ratio = atr_14 / atr_14_sma_100

        if atr_ratio > threshold_multiplier:
            regime = "HIGH_VOLATILITY"
            source_model = "volatility_v1"
            excess = atr_ratio - threshold_multiplier
            confidence = min(Decimal("0.95"), Decimal("0.5") + excess * Decimal("2.0"))

        elif atr_ratio < low_vol_multiplier:
            regime = "LOW_VOLATILITY"
            source_model = "volatility_v1"
            deficit = low_vol_multiplier - atr_ratio
            confidence = min(Decimal("0.95"), Decimal("0.5") + deficit * Decimal("2.0"))

    # ═══════════════════════════════════════════════════════════════════
    # PRIORITY 2: Mean Reversion
    # ═══════════════════════════════════════════════════════════════════

    if regime == "UNCERTAIN":
        mr_config = config.get("models", {}).get("mean_reversion", {})
        threshold = Decimal(str(mr_config.get("threshold", 0.005)))

        sma_spread = abs(sma_short - sma_long) / sma_long if sma_long > 0 else Decimal("999")
        price_dev_short = abs(price - sma_short) / sma_short if sma_short > 0 else Decimal("999")
        price_dev_long = abs(price - sma_long) / sma_long if sma_long > 0 else Decimal("999")

        if sma_spread < threshold and price_dev_short < threshold and price_dev_long < threshold:
            regime = "MEAN_REVERSION"
            source_model = "mean_reversion_v1"
            confidence = Decimal("0.75")

    # ═══════════════════════════════════════════════════════════════════
    # PRIORITY 3: Trend Detection (SMA Crossover)
    # ═══════════════════════════════════════════════════════════════════

    if regime == "UNCERTAIN":
        # Uptrend
        if sma_short > sma_long and price > sma_short:
            regime = "TREND_UP"
            confidence = self._calculate_confidence(sma_short, sma_long)
            source_model = "sma_trend_v1"

        # Downtrend
        elif sma_short < sma_long and price < sma_short:
            regime = "TREND_DOWN"
            confidence = self._calculate_confidence(sma_short, sma_long)
            source_model = "sma_trend_v1"

    # Emit event
    self.fsm.emit(
        Message(
            op="EVT",
            verb="REGIME_DETECTED",
            pld={
                "symbol": symbol,
                "ts": ts,
                "regime": regime,
                "confidence": str(confidence),
                "source_model": source_model,
            }
        )
    )
```

---

## 📍 РІШЕННЯ В DECISION MAKING — ДЕТАЛЬНА ЛОГІКА

### Алгоритм в `decision_making.py` (_try_make_decision)

```python
def _try_make_decision(self) -> None:
    """
    Aggregate all signals for symbol and emit trade intent if criteria met.

    Flow:
    1. Regime filter (block counter-trend)
    2. Signal score (OBI+TFI+ΔP)
    3. Probability calculation (base + signal)
    4. Kelly fraction
    5. Position sizing with regime multiplier
    6. Why-chain logging
    """

    # ... for each symbol with complete state ...

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: REGIME FILTER
    # ═══════════════════════════════════════════════════════════════════

    if self.latest_regime and self.latest_regime.get("symbol") == symbol:
        current_regime = self.latest_regime.get("regime")

        # Determine side from signal score
        signal_score = ... # calc below
        side = "buy" if signal_score > 0 else "sell"

        # Block counter-trend trades
        if current_regime == "TREND_UP" and side == "sell":
            logger.info(f"[{symbol}] TREND_UP blocks SELL (counter-trend)")
            self.clear_internal_state()
            return

        if current_regime == "TREND_DOWN" and side == "buy":
            logger.info(f"[{symbol}] TREND_DOWN blocks BUY (counter-trend)")
            self.clear_internal_state()
            return

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: SIGNAL SCORE CALCULATION
    # ═══════════════════════════════════════════════════════════════════

    features = self.symbol_states[symbol]["features"].get("features", {})
    obi = Decimal(str(features.get("obi", 0)))
    tfi = Decimal(str(features.get("tfi", 0)))
    delta_price = Decimal(str(features.get("delta_price", 0)))

    # Normalize to [0, 1]
    phi_obi = (obi + 1) / 2  # [-1, 1] → [0, 1]
    phi_tfi = (tfi + 1) / 2
    phi_delta = norm_delta(delta_price)  # custom normalization

    # Weighted score
    decision_config = self.config.get("trading", {}).get("decision", {})
    w1 = Decimal(str(decision_config.get("signal_weights", {}).get("obi", 0.6)))
    w2 = Decimal(str(decision_config.get("signal_weights", {}).get("tfi", 0.35)))
    w3 = Decimal(str(decision_config.get("signal_weights", {}).get("delta_price", 0.05)))

    signal_score = w1 * phi_obi + w2 * phi_tfi + w3 * phi_delta
    signal_threshold = Decimal(str(decision_config.get("signal_threshold", 0.15)))

    if signal_score < signal_threshold:
        logger.info(f"[{symbol}] Signal {signal_score} < threshold {signal_threshold}")
        return

    side = "buy" if signal_score > 0.5 else "sell"

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: DYNAMIC PROBABILITY & KELLY
    # ═══════════════════════════════════════════════════════════════════

    risk_config = decision_config.get("risk", {})
    base_prob = Decimal("0.5")
    p = base_prob + (signal_score - Decimal("0.5"))  # p ∈ [0, 1]

    payoff_ratio_r = Decimal("1.5")  # TP/SL ratio (configurable)
    full_kelly = p - (Decimal("1") - p) / payoff_ratio_r if payoff_ratio_r > 0 else 0

    kelly_cap = Decimal("0.25")
    kelly_alpha = Decimal("0.8")  # conservative
    kelly_fraction = min(kelly_cap, kelly_alpha * full_kelly)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: POSITION SIZING WITH REGIME MULTIPLIER
    # ═══════════════════════════════════════════════════════════════════

    equity = Decimal(str(self._cached_equity_free_usdt or "10000"))
    q = Decimal("0.015")  # Risk fraction
    sl_bps = Decimal("60")

    notional = (q * equity / (sl_bps / Decimal("10000"))) * Decimal("0.8")  # κ_liq
    position_size = notional * kelly_fraction

    # Apply regime-based sizing multiplier
    sizing_modifiers = decision_config.get("sizing_modifiers", {})
    regime_multiplier = Decimal("1.0")

    if current_regime in sizing_modifiers:
        regime_multiplier = Decimal(str(sizing_modifiers[current_regime]))
        position_size *= regime_multiplier
        logger.info(f"[{symbol}] {current_regime} sizing multiplier: {regime_multiplier}x")

    # Convert to quantity
    price = Decimal(str(features.get("price", "0")))
    qty_raw = position_size / price if price > 0 else 0

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: WHY-CHAIN LOGGING
    # ═══════════════════════════════════════════════════════════════════

    why_details = {
        "obi": str(obi),
        "tfi": str(tfi),
        "delta_price": str(delta_price),
        "signal_score": str(signal_score),
        "probability": str(p),
        "kelly_fraction": str(kelly_fraction),
        "regime": current_regime,
        "regime_multiplier": str(regime_multiplier),
        "position_size_usd": str(position_size),
        "qty": str(qty_raw),
    }

    self.dlog.write("TRADE_INTENT_PROPOSAL", event_rid, why_details)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: EMIT INTENT
    # ═══════════════════════════════════════════════════════════════════

    self.fsm.emit(
        Message(
            op="DEC",
            verb="TRADE_INTENT_PROPOSED",
            pld={
                "symbol": symbol,
                "side": side,
                "qty": str(qty_raw),
                "entry_price": str(price),
                "sl_price": str(price - (sl_bps / Decimal("10000")) * price),
                "tp_low": str(price + (sl_bps / Decimal("10000")) * price * Decimal("0.6")),
                "tp_high": str(price + (sl_bps / Decimal("10000")) * price),
                "kelly_fraction": str(kelly_fraction),
                "signal_score": str(signal_score),
                "regime": current_regime,
                "why_chain": why_details,
            }
        )
    )
```

---

## 📝 ВИСНОВОК

**Архітектура правильно відображає специфіку:**

✅ **Потік подій**: Market Data → Features → Regime → Decision → Execution
✅ **Режимна детекція**: SMA crossover + ATR ratio (High/Low VOL)
✅ **Фільтрація**: Counter-trend блокування працює (TREND_UP blocks SELL)
✅ **Сайзинг**: Kelly фракція × режимний множник
✅ **TP/SL**: Трейл-止loss в ManageFlow

⚠️ **Потреби розширення**:
- Повна Tension Index (ΔOI + Funding) на ETH funding events
- Break/Fake детекція
- Walk-forward validation інфраструктура

**Наступний крок**: Перейти до `03_Implementation_Status.md` для деталей кожного компонента.

