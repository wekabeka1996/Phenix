# Architecture Atlas (SSOT)

This document is the **visual single source of truth** for the system’s runtime flow and domain boundaries.

Scope anchor (code):
- Decision making + intent emission: `apps/reference/domains/decision_making/decision_making.py`
- Alpha scoring kernel: `apps/reference/domains/decision_making/signal_score_v2.py`
- Daily risk gate (drawdown): `apps/reference/domains/risk_management/daily_gate.py`
- Execution FSM: `apps/reference/domains/execution_position/fsm.py`
- Execution arithmetic helpers: `apps/reference/domains/execution_position/qty_normalizer.py`, `apps/reference/domains/decision_making/sizing_margin_first.py`

## Diagram 1: Data-to-Decision Spine (Sequence)

```mermaid
sequenceDiagram
    autonumber
    participant MD as Market Data
    participant FE as Feature Engineering
    participant RG as Risk Gate (DailyGate)
    participant DM as Decision Making
    participant BUS as Event Bus
    participant XFSM as Execution FSM

    MD->>FE: compute_features(bars/ticks)
    FE-->>MD: features + readiness

    Note over RG: Blocking / Sync boundary
    MD->>RG: can_open(equity_open, equity_now)
    RG-->>MD: allowed? + drawdown_pct

    MD->>DM: calculate_score(features, weights, neutrals, readiness)
    DM-->>MD: trade intent decision (or reject/defer)

    Note over DM,BUS: Async hand-off boundary
    DM->>BUS: publish EVT:TRADE_INTENT_PROPOSED
    BUS-->>XFSM: deliver EVT:TRADE_INTENT_PROPOSED

    XFSM->>XFSM: transitions (open/manage/close)
```

## Diagram 2: Domain Map (C4 Context Style)

```mermaid
flowchart LR
    %% C4-ish context map (high signal, low detail)
    subgraph Telemetry["Telemetry (Observer)"]
        TEL["Metrics / Logs / Forensics"]
    end

    subgraph Truth["Truth (SSOT State)"]
        WAL["WAL / Audit Trail"]
        POS["Position Tracking / Indices"]
        RSTATE["Risk Gate State (persisted)"]
    end

    subgraph Brain["Brain (Alpha & Decisions)"]
        FE["Feature Engineering\n(indicators, transforms)"]
        STRAT["Strategies / Alpha Models"]
        SCORE["Scoring Kernel\n(SignalScoreV2)"]
        DM["Decision Making\n(gates → trade intent)"]
    end

    subgraph Execution["Execution (FSM & Guardians)"]
        XFSM["Execution FSM"]
        GUARD["Order/Exposure Guardians"]
        LEV["Leverage Service"]
        QTY["Qty Normalizer"]
    end

    %% Consumption arrows (who consumes whom)
    FE --> STRAT
    STRAT --> SCORE
    SCORE --> DM

    Truth --> DM
    DM -->|EVT:TRADE_INTENT_PROPOSED| XFSM
    XFSM --> GUARD
    XFSM --> LEV
    XFSM --> QTY

    %% Observability
    Brain -.-> TEL
    Execution -.-> TEL
    Truth -.-> TEL

    %% Persistence / truth links
    DM --> WAL
    XFSM --> POS
    RG["Risk Gate (DailyGate)"] --> RSTATE
    RG --> DM
```

## Boundaries (SSOT)

- **Confirmed sync boundary (blocking):** `Risk Gate (DailyGate.can_open)` blocks new opens without valid equity and blocks when drawdown exceeds limit (`apps/reference/domains/risk_management/daily_gate.py`).
- **Confirmed async boundary:** `EVT:TRADE_INTENT_PROPOSED` emitted by Decision Making and consumed by Execution FSM (`apps/reference/domains/execution_position/fsm.py`).

