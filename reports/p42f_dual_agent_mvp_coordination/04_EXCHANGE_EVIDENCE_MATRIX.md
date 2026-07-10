# 04 — Exchange Evidence Matrix

This document summarizes the exchange integration layer, response classifications, and evidence verification parameters.

---

## 1. Response Classification Matrix

Incoming exchange responses are mapped to explicit Pydantic response classes, which inherit from `OrderLifecycleTrace` to preserve type compatibility:

| Response Class | Status | Rationale / Trigger |
| :--- | :--- | :--- |
| **EXTERNAL_ACK** | `ACK` | Order was successfully accepted by the exchange and sits open in the order book. |
| **EXTERNAL_REJECT** | `REJECT` | Order was rejected by the exchange or adapter boundary. |
| **EXTERNAL_FILL** | `FILL` | Order filled immediately, returning `filled_qty` and `price`. |
| **BLOCKED_CONFIG** | `BLOCKED_CONFIG` | Blocked due to missing credentials, misconfigured adapter ID, or default placeholders. |
| **BLOCKED_POLICY** | `BLOCKED_POLICY` | Blocked due to wrong symbol owner, Agent 1 restriction, or dry-run constraints. |
| **BLOCKED_DUPLICATE** | `BLOCKED_DUPLICATE` | Blocked because the command ID was already processed in the trace logs. |
| **BLOCKED_ENVIRONMENT**| `BLOCKED_ENVIRONMENT`| Blocked due to production URLs in base URL or non-testnet environment setting. |

---

## 2. Evidence Verification Rules

- **No Overclaiming**: The cockpit UI and execution bridge enforce strict rules for verifying external evidence. An order cannot claim `REAL_EXTERNAL` status unless it passes validation against a real testnet exchange response and contains no `stub-*` or shadow markers.
- **Rejecting Stub/Shadow**: The harness rejects `stub-*` client order IDs or shadow-only adapter descriptors during execution verification, classifying them as `STUB` or `SHADOW` respectively.

---

## 3. Order Operations & Cleanup

- **Exchange Methods**: `BinanceAdapter` exposes the necessary methods (`create_order`, `cancel_order`, `get_open_orders`, `get_open_positions`) to support standard order lookup, cancel, and close workflows.
- **FSM-Only Authority**: No raw exchange client (such as direct CCXT imports or direct REST HTTP calls) is imported or called by the trading agents. The FSM remains the exclusive order execution authority, and all actions route through FSM events.
- **Cleanup and Reconciliation**: On loop ticks or session teardowns, FSM monitors check for open orders and positions, executing market-reduce closes or cancels to ensure no unresolved exposure is left after session termination.
