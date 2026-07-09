# Operational and System Risks

This document registers any risks remaining in the hardened FSM guard and handoff mechanisms.

---

## 1. Identified Risks

### 1. Cooperative Configuration Errors
* **Risk**: The FSM guard relies on the environment setting `no_order_observation_mode` flag and descriptor configuration being passed correctly. If an orchestration layer initializes the adapter without loading these variables, safety parameters may default to unsafe values if not validation-asserted.
* **Mitigation**: Fail-closed checks on missing capability descriptors and invalid formats.

### 2. Payload Schema Polymorphism
* **Risk**: The quantity validation searches for `qty`, `quantity`, or `notional` case-insensitively in payload. If a future strategy command specifies sizing using a custom key (e.g. `amount` or `notional_value`), it might get rejected as missing quantity.
* **Mitigation**: Restrict execution command payloads to strictly conform to schema attributes.

### 3. Disk Write Latency / Storage Overflow
* **Risk**: Writing rejections to disk synchronously (`audit_rejections.jsonl`) can introduce latency under high-frequency signal rates, or exhaust filesystem space on excessive fails.
* **Mitigation**: Rejections are rare and only trigger on invalid/safety violations, not normal observation cycles.
