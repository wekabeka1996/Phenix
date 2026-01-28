# ==============================================================================
# Aurora Strategy Profile — SSOT
# ==============================================================================
# CFG-STRATEGY-SSOT-FREEZE-02:
# - Strategy policy SSOT: this file (no policy in trading.yaml/domains.yaml)
# - Global Aurora policy: aurora.decision (migrated from trading.yaml)
# - Per-symbol Aurora params: aurora.assets (migrated from aurora_instruments.yaml)
# ==============================================================================

aurora:
  enabled: true
  # Migration control: keep Aurora on legacy DecisionMaking tick-path until AuroraHandler is validated.
  legacy_tick_path_enabled: false
  type: bar_driven
  description: "Bar-driven multi-signal alpha strategy (5m basis) with regime awareness"
  timeframe_sec: 300
  
  # ORDER-POLICY-01: Entry order execution policy (SSOT for strategy)
  # LIMIT entries require explicit tif. No silent fallbacks.
  execution:
    entry_order_type: "LIMIT"   # MUST be one of: LIMIT, MARKET
    entry_tif: "GTX"            # MUST be set for LIMIT. One of: GTC, GTX, IOC, FOK

  # Global Aurora policy (DecisionConfig)
  decision:
    testnet:
      signal_threshold: 0.12
    production:
      signal_threshold: 0.12
    signal_threshold: 0.12
    neutral_threshold: 0.05
    symbols_to_track:
      - BTCUSDT
      - ETHUSDT
      - SOLUSDT
      - DOGEUSDT
      - XRPUSDT
    behavior_fsm:
      enable: false
      high_vol_multiplier: 2.0
      low_vol_multiplier: 0.5
    regime_threshold_multipliers:
      HIGH_VOLATILITY: 1.0
      LOW_VOLATILITY: 0.9
      MEAN_REVERSION: 0.75
      TREND_UP: 1.0
      TREND_DOWN: 1.0
      UNCERTAIN: 1.15
      DEFAULT: 1.0
    side_bias_min_score: null
    side_bias_window_sec: 420
    side_bias_target_ratio: 0.72
    side_bias_penalty_factor: 0.25
    side_bias_min_intents: 18
    cooldown_sec: 6
    retry_ttl_ms: 5000
    retry_max_count: 3
    retry_backoff_factor: 1.5
    regime_thresholds:
      HIGH_VOLATILITY: 0.10
      LOW_VOLATILITY: 0.09
      MEAN_REVERSION: 0.075
      TREND_UP: 0.1
      TREND_DOWN: 0.1
      UNCERTAIN: 0.115
      DEFAULT: 0.1
    kelly:
      base_probability: 0.5
      kelly_cap: 0.25
      kelly_alpha: 0.8
      payoff_ratio_r: 1.5
      p_min: 0.45
      p_max: 0.65
      uplift_factor: 0.20
    qos:
      mode: defer
      enforce: false
      exposure_block_cooldown_sec: 30
      symbol_cooldown_sec: 1
      max_intents_per_minute_per_symbol: 60
    signals:
      normalize_signals_mode: signed_v2
      enable_new_metrics: true
      delta_price_cap_pct: 0.02
    bar_gating: null
    roi_exit: null
    mean_reversion: null
    
    # Phase 4: Signal Score V2 Global Configuration
    scoring_version: v2

    # Direction/Strength split scoring (project-wide hardening)
    direction_strength_scoring:
      directional_features:
        - obi
        - tfi
        - delta_price
        - ema_bias
        - depth_imbalance
        # R1: macro_resid replaces macro_sync in directional scoring
        - macro_resid
        # Legacy: kept for telemetry; not weighted in v2 by default
        - macro_sync
      strength_features:
        - volume_spike
        - volatility_state
      strength_alpha: 0.5
      strength_cap: 1.0
    
    liquidity_gate:
      enabled: true
      kappa_min: 0.1
      kappa_max: 1.0
      failsafe_qty_check: true

    essential_features:
      - obi
      - delta_price
      - macro_resid  # Phase 4 Fix: Require macro_resid for fail-closed behavior

    # [Phase 3 Fix] Anchor Shock Veto: Block long signals during BTC crash
    anchor_shock_veto:
      enabled: true
      anchor_symbol: "BTCUSDT"
      threshold: -2.0  # Block BUY if macro_resid < -2.0 (strong crash)

    # === Minimum Holding Period (Anti-Churn Gate) ===
    # Prevents HFT-style churn by enforcing minimum time in position before
    # allowing signal-based exits. Does NOT affect safety exits (SL/TP/Risk).
    # RFC: docs/RFC_min_duration_logic.md
    holding_period:
      enabled: true
      min_duration_sec: 30          # Minimum seconds to hold position
      emergency_exit_threshold: 0.7  # |score| threshold for emergency override
      apply_to_flips: true          # Also apply holding period to FLIP signals

    # === VOL-ADJ-GATES-01: Sigma-normalized Motion Gates ===
    # Anti-Flat: Block entry when normalized motion too small (fee churn in dead market)
    # Anti-FOMO: Block entry when normalized motion too extreme (snapback risk)
    # Formula: pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)
    gates:
      enabled: true
      anti_flat_sigma: 0.5   # Block ENTRY if |pm_norm| < 0.5 (dead market)
      anti_fomo_sigma: 4.0   # Block ENTRY if |pm_norm| > 4.0 (extreme impulse)
      # P0-2: FIXED 900 → 300 (pm_norm_900s doesn't exist in schema, only 10/60/300)
      motion_window_sec: 300 # Use 5-minute window (pm_norm_300s)

    # === Re-entry Cooldown (Anti-Ping-Pong Gate) ===
    # Prevents immediate re-entry after position closes.
    # After exiting a position, wait this many seconds before allowing new entry.
    reentry_cooldown_sec: 60  # Global default: 60 seconds

    feature_neutrals:
      obi: 0.0
      tfi: 0.0
      delta_price: 0.0
      ema_bias: 0.5
      volume_spike: 0.0
      volatility_state: 0.0
      depth_imbalance: 0.5
      macro_sync: 0.5
      macro_resid: 0.0
    
    signal_weights:
      obi: 0.15
      tfi: 0.15
      delta_price: 0.1
      ema_bias: 0.15
      volume_spike: 0.1
      volatility_state: 0.1
      # depth_imbalance: phi in [0,1], higher = ASK dominance (sell pressure) -> negative weight
      depth_imbalance: -0.15
      # R1: macro_resid replaces macro_sync in directional scoring
      macro_resid: 0.1
      # macro_sync: 0.0  # DEPRECATED for scoring (kept as telemetry)

  # Per-symbol overrides (AuroraInstrumentConfig)
  assets:
    # ETHUSDT - Phase 3+ Optuna optimized parameters
    # Source: aurora_optimal_full_v1.yaml, aurora_phase3_production.yaml
    ETHUSDT:
      enabled: true
      position_mode: "STRICT"
      
      # P1: Active Leverage Management
      leverage:
        target: 20
        mode: "ISOLATED"
      
      # Holding period: ETH trend-following, longer holding
      holding_period:
        min_duration_sec: 45
        emergency_exit_threshold: 0.65
      
      # Re-entry cooldown: conservative for trend-following
      reentry_cooldown_sec: 120
      
      # Adjusted weights: Liquidity moved to Gate
      weights:
        ema_bias: 0.20
        volume_spike: 0.20
        # R1: macro_resid replaces macro_sync
        macro_resid: 0.25
        # macro_sync: 0.0  # DEPRECATED (telemetry only)
        # liquidity_kappa: 0.341 (Moved to Gate)
        obi: 0.25
        tfi: 0.093
        volatility_state: 0.036
        depth_imbalance: -0.256
        delta_price: 0.10

      liquidity_gate:
        enabled: true
        kappa_min: 0.2
        kappa_max: 1.0
        failsafe_qty_check: true

      side_bias:
        penalty_factor: 0.9
        window_sec: 600
        target_ratio: 0.6

      regime_thresholds:
        HIGH_VOLATILITY: 1.3
        LOW_VOLATILITY: 0.85
        MEAN_REVERSION: 1.05
        DEFAULT: 1.0

      regime_sizing:
        HIGH_VOLATILITY: 0.3
        LOW_VOLATILITY: 1.9
        MEAN_REVERSION: 0.8

      exit:
        sl_pct: 0.019
        max_hold_sec: 3000

      take_profit:
        tp_low_ratio: 0.4
        tp_high_ratio: 1.4
        partial_exit_pct: 0.7

      trailing_stop:
        enabled: false
        activation_pct: 0.003
        trail_pct: 0.006
        min_update_interval_sec: 5

      allowed_regimes: ["TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "LOW_VOLATILITY", "MEAN_REVERSION"]
      signal_threshold:
        enabled: true
        value: 0.09
      cooldown_sec: null
      
      # Smart Limit Entry: Volatility-based pricing (Maker/GTX compliance)
      volatility_entry_logic:
        enabled: true
        regime_multipliers:
          HIGH_VOLATILITY: 0.5    # ETH less volatile than SOL
          LOW_VOLATILITY: 0.1
          MEAN_REVERSION: 0.25
          TREND_UP: 0.2
          TREND_DOWN: 0.2
          UNCERTAIN: 0.2
          DEFAULT: 0.2
      
      timeframe_sec: null

    # SOLUSDT - Phase 3 Optuna optimized parameters
    SOLUSDT:
      # Holding period: uses global defaults (30s)
      # holding_period: null  # Explicit: inherit from decision.holding_period
      
      # P1: Active Leverage Management
      leverage:
        target: 20
        mode: "ISOLATED"
      
      # Re-entry cooldown: conservative for ALT
      reentry_cooldown_sec: 120
      
      # Adjusted weights: Liquidity moved to Gate
      weights:
        ema_bias: 0.20
        volume_spike: 0.20
        # R1: macro_resid replaces macro_sync
        macro_resid: 0.25
        # macro_sync: 0.0  # DEPRECATED (telemetry only)
        # liquidity_kappa: 0.25 (Moved to Gate)
        obi: 0.25
        tfi: 0.09
        volatility_state: 0.05
        depth_imbalance: -0.20
        delta_price: 0.10
      enabled: true
      position_mode: "STRICT"

      liquidity_gate:
        enabled: true
        kappa_min: 0.15
        kappa_max: 1.0
        failsafe_qty_check: true

      side_bias:
        penalty_factor: 0.0
        window_sec: 300
        target_ratio: 0.5
      
      regime_sizing:
        HIGH_VOLATILITY: 5.0
        LOW_VOLATILITY: 6.0
        MEAN_REVERSION: 5.0

      exit:
        sl_pct: 0.01512
        max_hold_sec: 3000

      take_profit:
        tp_low_ratio: 0.36
        tp_high_ratio: 0.60
        partial_exit_pct: 0.31

      allowed_regimes: ["TREND_DOWN", "LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION"]

      trailing_stop:
        enabled: true
        activation_pct: 0.046
        trail_pct: 0.018
        min_update_interval_sec: 5

      regime_thresholds: null
      signal_threshold:
        enabled: true
        value: 0.09
      cooldown_sec: null
      
      # Smart Limit Entry: Volatility-based pricing (Maker/GTX compliance)
      volatility_entry_logic:
        enabled: true
        regime_multipliers:
          HIGH_VOLATILITY: 0.6    # Deep offset (wider range)
          LOW_VOLATILITY: 0.1     # Tight offset
          MEAN_REVERSION: 0.3
          TREND_UP: 0.2
          TREND_DOWN: 0.2
          UNCERTAIN: 0.25
          DEFAULT: 0.2            # REQUIRED fallback
      
      timeframe_sec: null

    # =========================================================================
    # P2-2: DOGE/XRP REMOVED - MR-only symbols per strategies.yaml registry
    # =========================================================================
    # DOGEUSDT and XRPUSDT are assigned to mean_reversion ONLY in strategies.yaml.
    # Keeping them in aurora.assets was a source of confusion.
    # Registry SSOT (strategies_registry.assignments) now controls activation.
    # See: dm_strategy_ssot_implement_01.md, P1-1 fix.
    # =========================================================================

    # BTCUSDT - baseline params
    BTCUSDT:
      # P1: Active Leverage Management (only used if BTC is assigned to Aurora)
      leverage:
        target: 20
        mode: "ISOLATED"
      
      # Adjusted weights: Liquidity moved to Gate
      weights:
        ema_bias: 0.20
        volume_spike: 0.15
        # R1: macro_resid replaces macro_sync
        macro_resid: 0.15
        # macro_sync: 0.0  # DEPRECATED (telemetry only)
        # liquidity_kappa: 0.15
        obi: 0.20
        tfi: 0.10
        volatility_state: 0.10
        depth_imbalance: -0.05
        delta_price: 0.05
      enabled: true
      position_mode: "STRICT"
      
      # Holding period: BTC faster reaction due to high liquidity
      holding_period:
        min_duration_sec: 20
        emergency_exit_threshold: 0.7
      
      # Re-entry cooldown: faster for BTC due to high liquidity
      reentry_cooldown_sec: 45
      
      liquidity_gate:
        enabled: true
        kappa_min: 0.1
        kappa_max: 1.0
        failsafe_qty_check: true

      side_bias:
        penalty_factor: 0.5
        window_sec: 600
        target_ratio: 0.6

      regime_thresholds:
        HIGH_VOLATILITY: 1.2
        LOW_VOLATILITY: 0.9
        MEAN_REVERSION: 1.05
        DEFAULT: 1.0

      regime_sizing:
        HIGH_VOLATILITY: 3.0
        LOW_VOLATILITY: 4.0
        MEAN_REVERSION: 3.5

      exit:
        sl_pct: 0.02
        max_hold_sec: 3000
        # AURORA_REGIME_TP_SL_PLAN: Regime-based TP/SL adaptation
        # enabled: false by default — set to true to activate
        regime_tpsl:
          enabled: true  # Set to true to enable regime-based TP/SL
          mode: "pct_mult"  # "pct_mult" | "atr"
          # SL multipliers per regime (relative to base sl_pct)
          # Values from AURORA_REGIME_TP_SL_PLAN.md §4.2
          sl_mult:
            DEFAULT: 1.0
            FLAT_LOW: 0.70        # Less volatility → tighter SL
            LOW_VOLATILITY: 0.75
            FLAT_NORMAL: 0.85
            MEAN_REVERSION: 0.95
            TREND_UP: 1.10        # Trending → wider SL
            TREND_DOWN: 1.10
            HIGH_VOLATILITY: 1.35 # High noise → widest SL
            UNCERTAIN: 1.00
          # TP multipliers per regime (relative to base tp_low_ratio)
          tp_mult:
            DEFAULT: 1.0
            FLAT_LOW: 0.75        # Less movement → lower TP
            LOW_VOLATILITY: 0.80
            FLAT_NORMAL: 0.90
            MEAN_REVERSION: 0.85
            TREND_UP: 1.25        # Trending → higher TP
            TREND_DOWN: 1.25
            HIGH_VOLATILITY: 1.05
            UNCERTAIN: 1.00
          # Guardrails
          min_sl_pct: 0.003   # 0.3% min SL
          max_sl_pct: 0.06    # 6% max SL
          min_tp_rr: 0.3
          max_tp_rr: 3.0
          min_dist_bps: 15    # Min 15 bps from entry

      take_profit:
        tp_low_ratio: 0.5
        tp_high_ratio: 1.0
        partial_exit_pct: 0.5

      trailing_stop:
        enabled: false
        activation_pct: 0.02
        trail_pct: 0.01
        min_update_interval_sec: 5

      allowed_regimes: ["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "FLAT_LOW", "FLAT_NORMAL"]
      signal_threshold:
        enabled: false
        value: null
      cooldown_sec: null
      
      # Smart Limit Entry: Volatility-based pricing (Maker/GTX compliance)
      volatility_entry_logic:
        enabled: true
        regime_multipliers:
          HIGH_VOLATILITY: 0.4    # BTC most stable, conservative offsets
          LOW_VOLATILITY: 0.05
          MEAN_REVERSION: 0.2
          TREND_UP: 0.15
          TREND_DOWN: 0.15
          UNCERTAIN: 0.15
          DEFAULT: 0.15
      
      timeframe_sec: null





binance_api:
  live:
    api_key: ${BINANCE_FUTURES_API_KEY_LIVE}
    api_secret: ${BINANCE_FUTURES_API_SECRET_LIVE}
    rest_url: ${BINANCE_FUTURES_BASE_URL_LIVE}
    # PURGE-DEAD-CONFIG-03: ws_url removed (hardcoded in connectors)
  testnet:
    api_key: ${BINANCE_TESTNET_API_KEY}
    api_secret: ${BINANCE_TESTNET_API_SECRET}
    rest_url: https://testnet.binancefuture.com
    # PURGE-DEAD-CONFIG-03: ws_url removed (hardcoded in connectors)
trading:
  # HYBRID MODE: testnet execution with live data (domain_configuration controls granular modes)
  mode: backtest
  backtest:
    start_date: "2023-05-14"
    end_date: "2023-05-31"
    initial_balance: 1000.0
  tca_prefs:
    max_slippage_pct: 0.5
    max_slippage_bps: 10
    max_latency_ms: 500
    maker_preference: neutral
    preferred_venue: binance
    execution_priority: speed
  risk_budgets:
    trade_cvar95_max_bps: 100
    session_cvar95_max_bps: 200
    max_portfolio_risk_pct: 5.0
    max_single_position_risk_pct: 1.0
    max_daily_loss_pct: 2.0
  risk:
    max_daily_drawdown_limit: 0.05
    score_weights:
      delta_price: 0.05
      obi: 0.35
      tfi: 0.35
      absorption_inverse: 0.25
    testnet:
      max_risk_score: 0.9
    production:
      max_risk_score: 0.8
    trading_allowed_thresholds:
      max_risk_score: 0.9
    daily:
      enabled: false
      max_realized_loss_usd: 250.0
      max_drawdown_pct: 8.0
      reset_time_utc: 00:00
    profile: balanced
    soft_limits:
      # LIVE SAFETY: Soft clipping for position sizing risk management.
      mode: clip
      clip_min_notional_usdt: 10
      directional_ratio_max: 20.0
      side_exposure_usdt: 2000
      margin_exposure_usdt: 5000
    regime_adaptation:
      trend_up_delta: 0.3
      trend_down_delta: 0.3
      flat_delta: -0.3
      bounds:
      - 2.0
      - 4.0
    feature_flags:
      dynamic_ratio: true
      clipping_enabled: true
  market_data:
    poll_interval_sec: 5.0
    websocket_streams:
    - bookTicker
    - trade
    use_multiprocessing: true
    # PURGE-DIRTY-DOZEN: Removed api_call_limits (dead stub, REST replaced by WebSocket) - 2026-01-25
    macro_sync:
      enabled: true
      anchors:
      - BTCUSDT
      - ETHUSDT
      window: 60
      emit_abs: false
      align_mode: tail_min_len
      min_buffer_size: 3
      time_diff_threshold_ms: 60000
      anchor_update_from_ticks: false
    bar_aggregator:
      enabled: true
      timeframes_sec:
      - 180
      - 300
      - 900  # REGIME-BAR-FORENSICS-01: Enable 15m bars
  ops:
    panic_killswitch: false
  execution:
    manage:
      auto: true
      brackets:
        oco_emulation: true
        # TASK-ZOMBIE-FIX: Removed stop_loss_bps (dead duplicate, SSOT is sl.fixed_bps)
        offset_bps: 5
        sl:
          fixed_bps: 40
        tp:
          fixed_bps: 80
      orphan_monitor:
        enabled: true
      # Emergency mode config (optional - set enabled: false to disable)
      emergency:
        enabled: false
        wait_mode_bars: 2
        emergency_sl_bps: 100
      # TASK-ZOMBIE-FIX: Removed failsafe (dead, max_hold_sec moved to instruments.<SYM>.exit)
    fsm_periodic_cleanup_enabled: false
    cooldown_after_close_ms: 60000
    anti_race_close_ms: 800
    fallback: null
    limit_orders: null
    exposure:
      max_equity_utilization_pct: 150.0
      max_portfolio_fraction: 150.0
      # TASK-ZOMBIE-FIX: Removed max_side_utilization_pct (dead, never read in exposure_guard)
      max_directional_ratio: 50.0
      # TASK-ZOMBIE-FIX: Removed per_symbol_cap_pct (dead, never read in exposure_guard)
      count_pending_orders: true
      exclude_reduce_only: true
      pending_ttl_sec: 90
      # TASK-ZOMBIE-FIX: Removed pending_reservation_ttl_sec (dead, never read in exposure_guard)
      post_fill_hold_ttl_sec: 5
      # TASK-ZOMBIE-FIX: Removed positions_stale_ttl_sec (duplicate, SSOT is domains.execution_position.exposure_guard.stale_ttl_sec)
      leverage_defaults:
        BTCUSDT: 20
        ETHUSDT: 20
        SOLUSDT: 20
        XRPUSDT: 20
        DOGEUSDT: 20
        __default__: 20
    # PURGE-DIRTY-DOZEN: Removed open_order_type (dead stub, order_type now in intent) - 2026-01-25
    order_params:
      LIMIT:
        timeInForce: GTC
      STOP_MARKET:
        workingType: MARK_PRICE
      TAKE_PROFIT_MARKET:
        workingType: MARK_PRICE
      TRAILING_STOP_MARKET:
        callbackRate: '0.5'
    watchdog:
      ack_ttl_ms: 8000
      fill_ttl_ms: 60000
      check_interval_ms: 1000
      rps_limit: 10
    orders:
      default_ttl_seconds: 15
    preflight_backoff_ms:
    - 120
    - 250
    - 400
    - 800
    - 1200
    - 1800
    # PURGE-DIRTY-DOZEN: Removed min_post_interval_per_symbol_ms (dead stub, rate limit in adapter) - 2026-01-25
    allow_trade_with_guardian_tidy_only: false
    order_guardian:
      unified: true
      ledger_db_path: data/order_ledger.db
  # ═══════════════════════════════════════════════════════════════════════
  # HYBRID MODE CONFIGURATION (Live Data → Testnet Execution)
  # ═══════════════════════════════════════════════════════════════════════
  # Data domains: LIVE (read real market data)
  # Execution domains: TESTNET (write orders to testnet)
  # This allows safe testing with real market conditions without risking capital
  domain_configuration:
    market_data:
      trading_mode: live      # Read LIVE Binance market data (WebSocket + REST)
    feature_engineering:
      trading_mode: live      # Process features from live data
    decision_making:
      trading_mode: live      # Generate signals from live features
    # PURGE-DIRTY-DOZEN: Removed risk_management, execution_position, audit_trail trading_modes
    # (dead legacy, global trading_mode is SSOT) - 2026-01-25
  # ═══════════════════════════════════════════════════════════════════════
  # RISK MANAGEMENT DATA SOURCES (Hybrid Mode)
  # ═══════════════════════════════════════════════════════════════════════
  # portfolio_state: testnet → use testnet account balances/positions
  # market_data: live → use live prices for risk calculations
  risk_management:
    data_sources:
      portfolio_state: testnet  # Read positions/balance from TESTNET account
      market_data: live         # Use LIVE prices for mark-to-market valuations





# ==============================================================================
# STRATEGIES REGISTRY SSOT
# ==============================================================================
# Phase 0: Strategy assignments + arbitration (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
#
# CANONICAL SOURCE OF TRUTH для визначення:
# 1. Які стратегії активні для кожного символу
# 2. Як арбітрити конфлікти між стратегіями
#
# ConfigLoader завантажує це в AuroraConfig.strategies_registry
# Strict mode: missing file → ValueError
# ==============================================================================

version: "1.0.0"

# ==============================================================================
# STRATEGY ASSIGNMENTS (per-symbol)
# ==============================================================================
# Кожен символ має список активних стратегій (strategy_id)
# Valid strategy_id values:
# - "aurora": Bar-driven multi-signal strategy (5m basis)
# - "mean_reversion": Bar-based Bollinger Bands strategy (1m bars)
# ==============================================================================
assignments:
  # ETH: Aurora-only (champion bar-driven asset, Phase 3+)
  ETHUSDT:
    - aurora

  # SOL: Aurora-only (scalping mode, Phase 3)
  SOLUSDT:
    - aurora

  # DOGE: MR-only (champion MR asset, +$387 in research)
  DOGEUSDT:
    - mean_reversion

  # XRP: MR-only (MR silver medal, +$121)
  XRPUSDT:
    - mean_reversion

  # BTC: Mean Reversion (CHANGED from aurora)
  # Backtest showed 59% MEAN_REVERSION regime - Aurora unsuitable for ranging markets.
  # Mean Reversion strategy designed for sideways/flat market conditions.
  BTCUSDT:
    - aurora


# ==============================================================================
# ARBITRATION (conflict resolution)
# ==============================================================================
# Коли symbol має >1 активну стратегію і обидві генерують intent у один
# "decision window", система має детерміновано обрати одну.
#
# Modes:
# - "priority": Використовувати фіксований пріоритет (strategy_id → rank)
# - "regime": Обирати на основі поточного режиму (NOT IMPLEMENTED yet)
# - "round_robin": Чергувати (NOT IMPLEMENTED yet)
# ==============================================================================
arbitration:
  mode: priority

  # Decision window (ms): priority arbitration applies only within the same window.
  # This prevents permanent suppression of the lower-priority strategy on hybrid symbols (e.g. BTC).
  window_ms: 1000

  # Priority ranks (lower = higher priority)
  # Якщо Aurora і MR одночасно хочуть трейдити BTC:
  # - Aurora має пріоритет 1 (вищий)
  # - MR має пріоритет 2 (нижчий)
  # Результат: Aurora intent проходить, MR intent відкидається
  priority:
    aurora: 1
    mean_reversion: 2

  # Logging policy: що логувати, коли intent відкинуто через арбітраж
  # - rejected_strategy: ID стратегії, яка програла
  # - reason: короткий why-код (≤80 символів)
  logging:
    rejected_why_prefix: "ARBITRATION_REJECT"  # Prefix для why-кодів
    log_level: "INFO"  # Рівень логування (INFO/WARNING)


# SSOT: Canonical instrument precision configuration
# Priority: This file overrides trading.instruments (deprecated mirror)
#
# CFG-INSTRUMENTS-AURORA-SSOT-01
# TASK50: Added min_qty and min_notional for fail-closed qty normalization

instruments:
  SOLUSDT:
    symbol: "SOLUSDT"
    # Binance testnet LOT_SIZE: stepSize=1 (qty must be integer)
    step_size: "1"
    tick_size: "0.01"
    # Binance testnet LOT_SIZE: minQty=1
    min_qty: "1"
    min_notional: "5"     # Binance testnet: notional=5
    execution:
      margin_mode: "isolated"
      target_leverage: 20
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
    sizing:
      margin_pct: 0.11
    
  ETHUSDT:
    symbol: "ETHUSDT"
    step_size: "0.001"
    tick_size: "0.01"
    min_qty: "0.001"
    min_notional: "20"
    execution:
      margin_mode: "isolated"
      target_leverage: 41
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
    sizing:
      margin_pct: 0.11
    
  BTCUSDT:
    symbol: "BTCUSDT"
    step_size: "0.001"
    tick_size: "0.1"
    min_qty: "0.001"
    min_notional: "100"
    execution:
      margin_mode: "isolated"
      # With small equity, BTC needs higher leverage to clear step_size + min_notional constraints.
      target_leverage: 50
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
    sizing:
      margin_pct: 0.10
    
  DOGEUSDT:
    symbol: "DOGEUSDT"
    step_size: "1"
    tick_size: "0.00001"
    min_qty: "1"
    min_notional: "5"
    execution:
      margin_mode: "isolated"
      target_leverage: 20
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
    sizing:
      margin_pct: 0.11
    
  XRPUSDT:
    symbol: "XRPUSDT"
    step_size: "0.1"
    tick_size: "0.0001"
    min_qty: "0.1"
    min_notional: "5"
    execution:
      margin_mode: "isolated"
      target_leverage: 20
      leverage_policy: "set_and_verify"
      max_notional_utilization: 0.8
    sizing:
      margin_pct: 0.11




# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST CONFIGURATION OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════
#
# This file is ONLY loaded when trading_mode == "backtest".
# Values here OVERRIDE the base SSOT configs (domains.yaml, trading.yaml).
# Keep this file minimal - override only what's necessary for simulation.
#
# Pattern: Configuration Overlay (deep-merge on top of base config)
# ═══════════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# DOMAINS OVERRIDES (base: config/aurora/domains.yaml)
# ---------------------------------------------------------------------------
domains:

  # Feature Engineering: warmup enforcement for simulation
  feature_engineering:
    warmup:
      # BACKTEST: warn_only allows intents even if features not fully warmed up
      # LIVE: MUST be fail_fast to prevent trading with incomplete data
      enforcement_mode: warn_only

  decision_making:
    # Risk Skew Guard: disable strict skew check for historical data
    risk_skew:
      # BACKTEST: Set very high to disable skew check (historical data has no "staleness")
      # LIVE: Set to 5 seconds for production safety
      max_skew_sec: 999999

    # Directional Sanity: allow counter-trend entries for mean-reversion testing
    directional_sanity:
      # BACKTEST: disabled to allow counter-trend orders
      # LIVE: enabled=true for trend-following safety protection
      enabled: false

    # Price Motion Sanity: requires tick-level data not available in bar-based backtest
    price_motion_sanity:
      # BACKTEST: disabled (5m bars don't provide 10s/60s granularity for pm_norm_*)
      # LIVE: enabled=true to restore Anti-FOMO protection with tick-level data
      enabled: false

    # Flip-orchestration smoothing to reduce churn/fees in backtest.
    # Enables close-then-reopen workflow instead of instant netting flips.
    flip:
      enabled: true
      hysteresis_mult: 1.5

    # QoS: reduce intent spam in backtest (fees burner protection).
    # Only these fields override base; the rest is inherited from domains.yaml.
    qos:
      symbol_cooldown_sec: 300
      max_intents_per_minute_per_symbol: 6

# ---------------------------------------------------------------------------
# TRADING OVERRIDES (base: config/aurora/trading.yaml)
# ---------------------------------------------------------------------------
trading:
  # Backtest runs ONLY on BTCUSDT (dataset is BTC-only)
  symbols_to_track:
    - BTCUSDT

  # TCA preferences relaxed for simulation
  tca_prefs:
    # BACKTEST: relaxed slippage for historical simulation
    # LIVE: use stricter values (e.g., 10 bps)
    max_slippage_bps: 50

  risk:
    soft_limits:
      # BACKTEST: disabled until MockBroker correctly uses config leverage
      # LIVE: mode=clip with appropriate limits
      mode: "off"

# ---------------------------------------------------------------------------
# STRATEGIES (SSOT: config/aurora/strategies/*.yaml)
# NOTE: Backtest runs on SSOT config (no extra override file).
# ---------------------------------------------------------------------------
strategies:
  aurora:
    decision:
      # REGIME KILL-SWITCH: No strategy-driven trading actions in these regimes.
      # This is stronger than thresholds because it also blocks HOLD/EXIT signals.
      blocked_regimes:
        - MEAN_REVERSION
        - UNCERTAIN

      # Backtest runs ONLY on BTCUSDT (dataset is BTC-only)
      symbols_to_track:
        - BTCUSDT

    assets:
      BTCUSDT:
        # Per-symbol override exists in strategies/aurora.yaml, so we must hard-lock here too.
        # Otherwise MEAN_REVERSION / UNCERTAIN can fall back to DEFAULT and still trade.
        regime_thresholds:
          MEAN_REVERSION: 99.0
          UNCERTAIN: 99.0
          HIGH_VOLATILITY: 0.1
          LOW_VOLATILITY: 0.09
          TREND_UP: 0.1
          TREND_DOWN: 0.1
          DEFAULT: 0.1
        exit:
          # Base 0.5% SL in backtest; regime multipliers apply on top.
          sl_pct: 0.005
          regime_tpsl:
            enabled: true
            mode: "pct_mult"
            sl_mult:
              HIGH_VOLATILITY: 1.5
              LOW_VOLATILITY: 1.0
              DEFAULT: 1.0
            tp_mult:
              HIGH_VOLATILITY: 4.0
              LOW_VOLATILITY: 1.5
              DEFAULT: 1.5

        take_profit:
          tp_low_ratio: 1.0
          tp_high_ratio: 2.0
  # Disable Mean Reversion strategy in this BTC-only backtest overlay
  mean_reversion:
    enabled: false









