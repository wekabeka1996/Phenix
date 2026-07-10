# Turn Context Contract

Each turn requires:

- `session_id`, `turn_id`, `agent_id`, `agent_number`;
- `owned_symbols` and explicit `owned_symbol`;
- current market context;
- portfolio state and own positions/orders;
- peer publications;
- instruction versions and active `instruction_version`;
- current checkpoint summary;
- bounded private reflection summaries;
- available tools;
- deadline and `current_collective_state_version`.

`compact_payload()` preserves identity, ownership, versions, deadline, and the current checkpoint while bounding market/portfolio/order/publication/reflection payloads. Recent private reflections are limited to six short summaries; peer publications to eight clipped records. If the encoded payload remains too large, reflections are removed and the checkpoint/publication windows are reduced. No raw memory dump or hidden context fallback is used.

