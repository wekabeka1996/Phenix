# Packet polling evidence

- Request: Cockpit GET-only packet endpoint, BTCUSDT/ETHUSDT, 300s, max 4,400 tokens.
- Ports: Aurora read host 18080; Cockpit 18081; 7102/8443 unused.
- Polls: 10; HTTP 200: 10; failures: 0; unique packet IDs: 10.
- SQLite persistence: 30 -> 40, delta +10.
- Freshness per packet: fresh 8, stale 0, missing 0, unknown 0.
- Ownership: direct main publication for market/features/execution body.
- Descriptors per packet: 7; constraint summaries: 2.
- Descriptor status per packet: ready 5, degraded 2, missing 0.
- Budget: 14,450-14,453 bytes; 3,613-3,614 tokens; truncation false.
- Latency: 20-57 ms, mean 28.5 ms.

Full envelopes are stored in `samples/runtime_agent_feed_packets_p5.jsonl`.
