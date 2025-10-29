# Aurora Core Architecture

This document provides a high-level overview of the Aurora Core system architecture after the architectural stabilization phase.

## System Overview

The system is a federated Finite State Machine (FSM) architecture designed for algorithmic trading. It is composed of several independent but interconnected domains, each responsible for a specific part of the trading lifecycle. The domains communicate asynchronously through a central FSM Core message bus.

## Data Flow

The data flow follows a logical progression from market data ingestion to trade execution:

1.  **`MarketDataConnector`**: Connects to an external data source (e.g., Binance WebSocket) and emits raw market data ticks as `EVT:MARKET_TICK_RECEIVED` events.

2.  **`FeatureEngineering`**: Subscribes to market ticks and calculates various trading indicators and features (e.g., OBI, TFI). It emits the calculated features as `EVT:FEATURES_CALCULATED` events.

3.  **`RiskManagement`**: Subscribes to both feature events and portfolio updates. It performs two levels of risk assessment:
    *   **Portfolio-level**: Checks for breaches of portfolio-wide limits, such as maximum daily drawdown. If a limit is breached, it acts as a circuit breaker, halting all new trades.
    *   **Instrument-level**: Assesses the risk of the current market conditions for a specific instrument based on the calculated features.
    It emits its assessment as `EVT:RISK_ASSESSMENT_COMPLETED`, which includes an `is_trading_allowed` flag.

4.  **`PositionTracking`**: Subscribes to trade execution events (`EVT:TRADE_EXECUTED`) and account updates from the exchange. It maintains the current state of the portfolio, including open positions, equity, and P&L. It emits the consolidated portfolio state as `EVT:PORTFOLIO_STATE_UPDATED` events. This domain is also responsible for creating state snapshots for disaster recovery.

5.  **`DecisionMaking`**: This is the core logic unit. It subscribes to events from `FeatureEngineering`, `RiskManagement`, and `PositionTracking`. When it has a complete picture for an instrument (features, risk assessment, and portfolio state), it decides whether to propose a trade. If a trade is warranted, it emits an `EVT:TRADE_INTENT_PROPOSED` event.

6.  **`main.py` Bridge**: A listener in the main application acts as a bridge, converting the analytical `EVT:TRADE_INTENT_PROPOSED` event into an executable `CMD:OPEN` command.

7.  **`ExecPosFSM` (Execution Position)**: This domain is responsible for the entire lifecycle of an order. It is a wrapper that manages three sub-FSMs on a per-symbol basis:
    *   **`OpenFlowFSM`**: Receives `CMD:OPEN`, validates it against guards (e.g., cooldown, min notional), and emits a `DEC:OPEN` decision to the execution adapter. It includes idempotency checks to prevent duplicate orders.
    *   **`ManageFlowFSM`**: Activates when a position is opened (on a `FILL` event). It is responsible for managing the position's risk, such as placing bracket orders (Stop Loss / Take Profit) and handling trailing stops.
    *   **`CloseFlowFSM`**: Also activates when a position is opened. It monitors for conditions that would warrant closing the position, such as a `max_hold_sec` time limit being reached.

8.  **Execution Adapter**: The `DEC:*` messages are handled by an adapter (e.g., `BinanceExecutionAdapter` or `SimulatedExecutionAdapter`), which communicates with the exchange API to place, cancel, or modify orders. The adapter then emits events back into the system based on the results (e.g., `EVT:TRADE_EXECUTED`).

## Disaster Recovery

The system has a disaster recovery mechanism based on snapshots and a Write-Ahead Log (WAL):
-   `PositionTracking` periodically creates snapshots of the portfolio state.
-   All critical events (like trades and account updates) are written to the WAL before being processed.
-   On startup, the system restores the latest snapshot and replays any subsequent events from the WAL to reconstruct the exact state.
-   The `ManageFlowFSM` and `CloseFlowFSM` instances are then "hydrated" with the state of the restored positions, ensuring that open positions continue to be managed correctly after a restart.
