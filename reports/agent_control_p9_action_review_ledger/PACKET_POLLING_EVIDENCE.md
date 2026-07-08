# Packet polling evidence

- Route: Cockpit `GET /api/agent-feed/v0/packet` → Aurora `GET /agent-feed/v0/packet`.
- Measured polls: 10; HTTP 200: 10; failures: 0; unique packet ids: 10.
- SQLite `agent_feed_packet_metadata`: 75 → 85, delta +10.
- Packet bytes: 16,260-16,263.
- Estimated tokens: 4,065-4,066/4,400; no truncation.
- Latency: 13-39 ms, mean 25.9 ms.
- Every packet projected completed review revision 2, realized `no_clear_scenario`, unresolved count zero, and non-submitted execution status.
- Full evidence: `samples/runtime_agent_feed_packets_p9.jsonl`.
