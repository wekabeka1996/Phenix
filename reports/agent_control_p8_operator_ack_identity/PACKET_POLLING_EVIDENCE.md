# Packet polling evidence

- Route: Cockpit `GET /api/agent-feed/v0/packet` → Aurora `GET /agent-feed/v0/packet`.
- Polls: 10; HTTP 200: 10; failures: 0; unique packet ids: 10.
- Cockpit SQLite `agent_feed_packet_metadata`: 61 → 71, delta +10.
- Packet bytes: 15,418-15,421.
- Estimated tokens: 3,855-3,856/4,400; no truncation.
- Latency: 2,050-2,134 ms; mean 2,080.3 ms.
- Every packet: BTCUSDT `unacknowledged/missing`, no operator id; ETHUSDT `not_required/not_required`.
- History rows: 154 before P8 runtime → 182 after observation.
- Full observations: `samples/runtime_agent_feed_packets_p8.jsonl`.
