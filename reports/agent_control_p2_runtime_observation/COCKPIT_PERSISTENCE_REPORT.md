# Cockpit persistence report

Store: `.agent_workspace/runtime_store/runtime.sqlite`.

Table: `agent_feed_packet_metadata`.

- Rows before successful observation: 0.
- Rows after ten successful polls: 10.
- Rows inserted: 10.
- Latest packet id: `afp_b1b96bd3b0e34ceab44e063cb2e881f0`.
- Latest id matched the tenth sampled packet.

The table stores packet id, produced timestamp, symbols, freshness summary, estimated tokens, payload bytes, truncation, persistence time, and validated compact payload.

The TypeScript parser rejects malformed schema and over-budget packets before persistence; focused tests pass. The live failure check returned HTTP 502 while Aurora was unavailable, and row count stayed at 10. Failed polls are therefore not persisted as packets.
