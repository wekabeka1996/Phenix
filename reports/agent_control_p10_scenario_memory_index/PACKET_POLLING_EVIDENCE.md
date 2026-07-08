# Packet polling evidence

- Cockpit endpoint: `GET /api/agent-feed/v0/packet`.
- Read host: 18080; Cockpit: 18081.
- Polls: 10; successes: 10; failures: 0; unique packet ids: 10.
- SQLite rows: 86 → 96, delta +10.
- Packets: 16,669–16,672 bytes; 4,168 estimated tokens; no truncation.
- Freshness: stale=8 on every packet because Aurora main was intentionally not started.
- Full samples: `samples/runtime_agent_feed_packets_p10.jsonl`.
