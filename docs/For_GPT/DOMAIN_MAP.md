# DOMAIN_MAP.md
Short descriptions of key domains that run inside `apps/reference/domains`.

- **decision** – Runs `decision_making` FSMs that validate incoming trade intents, apply rejection rules, and pass refined intents to execution while recording rejects and timing metrics.
- **risk_management** – Keeps the portfolio inside guardrails by publishing daily limits, calculating risk indicators, and validating against `schemas/risk_assessment_v1.json`.
- **execution_management** – Orchestrates execution flows, prepares commands for `execution_position`, enforces fill regimes, and validates broker ACK/FILL responses before those events reach the FSM.
- **execution_position** – Execution FSM stack (open/manage/close) with Binance/simulated adapters, exposure guard, and Aggregated OCO v1 behaviour (TP/SL per `(symbol, side)`, XAI logging, DR rehydrate).
- **feature_engineering** – Prepares the features feeding downstream models, stages experimental builds, and stores published definitions (e.g., `features_calculated_v1.json`) for repeatable data generation.
- **market_data** – Captures live market streams via WebSocket connectors, aggregates quotes and depth, and makes them available through `market_data_connector.py` for every consumer.
- **regime_detector** – Assesses volatility regimes, publishes status (normal/volatile/crisis), and feeds thresholds/sizing adjustments back to decision, risk, and execution layers.
- **audit** – Provided by `apps/reference/telemetry` plus `vfoundation/obs`, this stack logs events, alerts, order guardian decisions, and audit trails for post-mortem analysis.
- **portfolio** – Account balances and positions surface through `account_balance`, `position_tracking`, and reporting helpers that reconcile states and expose portfolio health.
- **system** – Infrastructure plumbing (bootstrap, config loaders, preflight) that validates `config/aurora` and `config/_schemas` before the rest of the FSM stack starts.
- **backtesting** – Hosted in `alpha_discovery` where `backtest_engine.py` and sample scripts let teams exercise strategy logic against historical data.
- **logging/observability** – Telemetry, metrics, alerts, and structured logging live in `telemetry` and `vfoundation/obs`, with outputs flowing into `logs/` for dashboards and investigations.
