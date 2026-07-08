# Packet polling evidence

- Route: Cockpit `GET /api/agent-feed/v0/packet` to Aurora `GET /agent-feed/v0/packet`.
- Polls: 10; HTTP 200: 10; failures: 0; unique packet IDs: 10.
- SQLite `agent_feed_packet_metadata`: 50 → 60, delta +10.
- Packet bytes: 14,977-14,982.
- Estimated tokens: 3,745-3,746/4,400; `truncated=false`.
- Round trip: 2,064-2,146 ms; mean 2,077.4 ms.
- Every packet: ETHUSDT `match/not_required`; BTCUSDT `conservative_mismatch/unacknowledged`.
- Full observations: `samples/runtime_agent_feed_packets_p7.jsonl`.
- Packet ids and row counts: `samples/p7_observation_summary.json`.
