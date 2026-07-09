# CLI Agent Session Protocol

This protocol defines the minimal contract and lifecycle logic for bounded CLI agent session loops on the Phenix platform.

## 1. Core Principles
- **Strict Bounded Execution**: Agents must not execute infinite daemon loops. Loops are constrained by max iterations and max elapsed runtime.
- **Inspectable State**: Every wakeup iteration produces an inspectable log tick (`TimerTick`).
- **GET-Only/Read-Only Context**: Agents do not directly edit configs or place execution orders. All updates and proposals are read-only drafts.
- **Cadence & SOS Synchronization**: Staggered intervals balance memory refresh load, while SOS alerts allow immediate, out-of-band forced updates.

## 2. Actions & Envelopes
All communication envelopes (`CLIAgentActionEnvelope`) must reject executable field payloads:
- Prohibited fields: `order`, `sizing`, `leverage`, `quantity`, `notional`, `exchange_order_id`, `client_order_id`.
- Supported actions:
  - `memory_refresh`: Pulls the latest synchronized shared context state.
  - `sos_emit`: Signals sharp market-change events requesting global updates.
  - `proposal_submit`: Submits drafts for reviewed non-executable suggestions.
  - `heartbeat`: Registers check-in signals indicating operational stability.
