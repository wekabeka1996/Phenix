# Timer and Wakeup Contract

This document details the scheduling, timing, and event-driven wakeups for the supervisor.

---

## 1. Cadence Intervals

The supervisor supports independently configured cadence loops (timers) for:
- **Market Refresh**: `market_refresh_cadence_sec`
- **Heartbeat**: `heartbeat_cadence_sec`
- **Agent Analysis**: `analysis_cadence_sec`
- **Peer/Collective Refresh**: `collective_publication_cadence_sec`
- **Portfolio Refresh**: `portfolio_sync_cadence_sec`
- **Instruction Refresh**: `analysis_cadence_sec` (aligned with checks)
- **Reflection**: `reflection_cadence_sec`

---

## 2. Event-Driven Wakeups

The supervisor intercepts events from the FSM event bus. An immediate wakeup is triggered for the running agents upon receiving any of the following FSM events:
- **Instruction Change**: Intercepting `INSTRUCTIONS_REFRESHED`
- **Peer Publication**: Intercepting `PEER_MESSAGE_PUBLISHED` / `COLLECTIVE_STATE_UPDATED`
- **Order/Position Change**: Intercepting `ORDER_RESULT` / `POSITION_UPDATE`
- **Exchange Error**: Intercepting `EXCHANGE_ERROR`
- **Risk Warning**: Intercepting `RISK_WARNING`
- **Kill Switch**: Intercepting `PANIC`

Waking up is implemented using `asyncio.Event` flags for each agent. The agent loop waits for either the event flag to be set or the cadence timeout to expire.
