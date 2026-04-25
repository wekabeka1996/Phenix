# 📄 Semantic Configuration Passport: `config/aurora/trading.yaml` (Gemini Extraction)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/trading_passport_gemini.md
> - Scope: First ~200 lines of `config/aurora/trading.yaml`
> - Purpose: Baseline passport extraction for system configuration logic.

Цей паспорт описує торгову логіку, ризики, налаштування біржового виконання та інтеграцію ШІ на рівні `trading.yaml`.

---

## 1. Binance API Connections (`binance_api`)

### `binance_api.live.api_key` / `api_secret`
- **Type:** `string` (environment variable injection)
- **Role:** Credentials for Binance Futures REST/WS in production (`live` mode). Required for authentication and HMAC signatures.

### `binance_api.live.rest_url`
- **Type:** `string` (environment variable injection)
- **Role:** Base URL for production exchange REST API calls.

### `binance_api.testnet.api_key` / `api_secret`
- **Type:** `string` (environment variable injection)
- **Role:** Credentials for Binance Futures Testnet environment. Required for `testnet` and `hybrid` execution modes.

### `binance_api.testnet.rest_url`
- **Type:** `string` (`https://testnet.binancefuture.com`)
- **Role:** Base URL for testnet execution.

---

## 2. Trading Mode (`trading.mode`)

### `trading.mode`
- **Type:** `string` (enum)
- **Value:** `hybrid_live_data_testnet_exec`
- **Role:** The master runtime mode selector. It controls the blast radius by separating data feeds (live) from actual trade execution (testnet), providing a safe environment for strategy evaluation without real capital risk.

---

## 3. TCA Preferences (`trading.tca_prefs`)

### `trading.tca_prefs.max_slippage_pct` / `max_slippage_bps`
- **Type:** `float` (0.5) / `int` (25)
- **Role:** Maximum acceptable slippage tolerance. The system uses `bps` (basis points) internally for strict integer arithmetic during price boundary checking.

### `trading.tca_prefs.max_latency_ms`
- **Type:** `int` (3000)
- **Role:** Acceptable intent-to-fill execution latency constraint in milliseconds.

### `trading.tca_prefs.maker_preference`
- **Type:** `string` (neutral)
- **Role:** Determines the preferred liquidity provision strategy (maker vs. taker) during entry orchestration.

### `trading.tca_prefs.preferred_venue`
- **Type:** `string` (binance)
- **Role:** Target exchange for execution routing.

### `trading.tca_prefs.execution_priority`
- **Type:** `string` (speed)
- **Role:** Instructs the FSM whether to prioritize fill rate (speed) or optimal price (price) during entry generation.

---

## 4. Risk Budgets (`trading.risk_budgets`)

### `trading.risk_budgets.trade_cvar95_max_bps`
- **Type:** `int` (100)
- **Role:** Maximum acceptable Conditional Value at Risk (CVaR) per individual trade at the 95% confidence level.

### `trading.risk_budgets.session_cvar95_max_bps`
- **Type:** `int` (200)
- **Role:** Maximum CVaR budget allocated for the entire trading session.

### `trading.risk_budgets.max_portfolio_risk_pct` / `max_single_position_risk_pct`
- **Type:** `float` (5.0 / 1.0)
- **Role:** Global portfolio guardrails defining the absolute maximum percentage of equity that can be exposed globally or allocated to a single asset.

### `trading.risk_budgets.max_daily_loss_pct`
- **Type:** `float` (2.0)
- **Role:** The hard Daily Stop limit (drawdown threshold).

---

## 5. Active Risk Management (`trading.risk`)

### `trading.risk.score_weights.*`
- **Type:** `float`
- **Role:** The directional conviction weighting coefficients used by legacy or active scoring kernels (`delta_price: 0.05`, `obi: 0.35`, `tfi: 0.35`, `absorption_inverse: 0.25`).

### `trading.risk.trading_allowed_thresholds.max_risk_score`
- **Type:** `float` (0.9)
- **Role:** The absolute maximum system stress/risk score that allows new positional entries.

### `trading.risk.daily`
- **Type:** `object`
- **Role:** Configures the daily drawdown safety gate (`enabled: false`, `max_drawdown_pct: 8.0`, `reset_time_utc: 00:00`). If triggered, the system fail-closes new entries until the reset time.

### `trading.risk.soft_limits`
- **Type:** `object`
- **Role:** Controls position sizing adjustments (`mode: clip`). Enforces exposure constraints like `side_exposure_usdt: 2000` and `directional_ratio_max: 20.0` to prevent excessive directional tilt.

### `trading.risk.regime_adaptation`
- **Type:** `object`
- **Role:** Dynamically shifts risk thresholds based on the active market regime (Trend Up/Down vs Flat).

---

## 6. Market Data (`trading.market_data`)

### `trading.market_data.poll_interval_sec`
- **Type:** `float` (5.0)
- **Role:** Background polling rate for REST fallback or specific data sync cycles.

### `trading.market_data.websocket_streams`
- **Type:** `list[string]`
- **Role:** Explicit subscription topics for Binance WS (`bookTicker`, `trade`).

### `trading.market_data.use_multiprocessing`
- **Type:** `bool` (true)
- **Role:** Determines if market data ingestion runs in an isolated OS process via IPC queues to prevent event loop blocking.

### `trading.market_data.macro_sync`
- **Type:** `object`
- **Role:** Defines anchor symbols (`BTCUSDT`, `ETHUSDT`) used for global market state alignment and macro feature generation over a specified `window: 60` seconds.

### `trading.market_data.bar_aggregator`
- **Type:** `object`
- **Role:** Aggregates tick data into standard OHLCV timeframes (`180`, `300`, `900`, `14400`, `86400` seconds).

---

## 7. Execution (`trading.execution`)

### `trading.execution.manage.brackets`
- **Type:** `object`
- **Role:** Configures automatic Take Profit / Stop Loss behavior (`tp.fixed_bps: 80`, `sl.fixed_bps: 40`), including OCO (One Cancels the Other) emulation and price safety offsets.

### `trading.execution.manage.orphan_monitor`
- **Type:** `object`
- **Role:** Background garbage collection for stray orders (`enabled: true`, `periodic_interval_sec: 300`).

### `trading.execution.exposure`
- **Type:** `object`
- **Role:** Defines hard execution exposure limits (`max_equity_utilization_pct: 150.0`) and leverage defaults for specific assets (BTCUSDT: 20x).

### `trading.execution.order_guardian`
- **Type:** `object`
- **Role:** Manages the persistent SQLite database (`data/order_ledger.db`) for strict event idempotency and crash recovery (`unified: true`).

---

## 8. Domain Configuration Mappings (`trading.domain_configuration`)

- **Role:** Explicitly defines which environment (`live` vs `testnet`) each domain connects to. Currently enforces that `market_data`, `feature_engineering`, and `decision_making` consume `live` data streams.

---

## 9. LLM Orchestration (`trading.llm_orchestration`)

### `trading.llm_orchestration.mode`
- **Type:** `string` (`hybrid_advisory`)
- **Role:** Defines the level of AI autonomy. `hybrid_advisory` implies the LLM suggests or filters intents but does not directly execute them.

### `trading.llm_orchestration.allowlist_symbols`
- **Type:** `list[string]`
- **Role:** Restricts LLM interference to specific isolated assets (e.g., `1000PEPEUSDT`) to protect core trading pairs from AI hallucination risks.

### `trading.llm_orchestration.intent_policy`
- **Type:** `object`
- **Role:** The absolute hard-boundaries for AI-generated commands:
  - `max_notional_usd: 100.0` (Strict capital bound per AI intent).
  - `require_tp_sl: true` (AI cannot submit unprotected entries).
  - `allow_limit_only: true` (AI cannot submit aggressive MARKET orders).
  - `max_price_deviation_bps: 20.0` (Protects against fat-finger AI price hallucinations).
