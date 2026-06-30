# Packet polling evidence

- Route: Cockpit `GET /api/agent-feed/v0/packet` to Aurora `GET /agent-feed/v0/packet`.
- Hosts: Aurora 18080; Cockpit 18081.
- Symbols: BTCUSDT, ETHUSDT; budget 4,400.
- Polls: 10; HTTP 200: 10; failures: 0; unique packet IDs: 10.
- Persistence: `agent_feed_packet_metadata` rows 40 → 50.
- Packet sizes: 14,866-14,869 bytes; estimated tokens: 3,717-3,718; truncation: false.
- Every packet contains only requested-symbol constraint/parity summaries and seven projected capability descriptors.
- Full evidence: `samples/runtime_agent_feed_packets_p6.jsonl`.
