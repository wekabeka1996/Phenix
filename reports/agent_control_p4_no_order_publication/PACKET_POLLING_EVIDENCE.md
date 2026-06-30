# Packet polling evidence

- Endpoint path: Cockpit `GET /api/agent-feed/v0/packet` -> Aurora `GET /agent-feed/v0/packet`.
- Approved ports: read host 18080, Cockpit 18081.
- Forbidden bridge ports 7102/8443: unused.
- Requested symbols: BTCUSDT, ETHUSDT; timeframe 300s; max budget 4,400 tokens.
- Polls: 10; HTTP 200: 10; failures: 0; unique packet IDs: 10.
- Persistence: SQLite rows 20 -> 30, delta +10.
- Freshness each poll: fresh 8, stale 0, missing 0, unknown 0.
- Ownership each poll: BTC/ETH market and features plus execution body `direct_main_publication`.
- Packet budget: 11,293-11,295 bytes; 2,824 estimated tokens; no truncation.
- Oldest card-source age: 249,695-254,405 ms.

The complete observation envelopes are in `samples/runtime_agent_feed_packets_direct_main.jsonl`.
