# AgentFeedPacket v0 bridge contract

The canonical transport is HTTP GET. Shared files are not an integration contract.

## Aurora endpoints

- `GET /agent-feed/v0/health`
- `GET /agent-feed/v0/sources`
- `GET /agent-feed/v0/packet?symbols=BTCUSDT,ETHUSDT&max_tokens=4400&tf_sec=300`

The endpoint accepts 1–12 explicit symbols. `max_tokens` is constrained to 1,500–4,400. The exporter returns HTTP 503 rather than sending an over-budget packet.

## Packet

`schema_version` is exactly `agent-feed/v0` and `read_only` is exactly `true`. The six UI groups are represented by `global_market`, `symbol_markets`, `feature_signals`, `position_life`, `business_warnings`, and `execution_body`.

Every card includes `source_ts_ms`, `produced_ts_ms`, `freshness`, opaque `source_refs`, `missing_fields`, and diagnostics. Freshness is one of `fresh`, `stale`, `missing`, or `unknown`. A missing value is omitted or null and named in `missing_fields`; it is never replaced with a neutral market value.

`budget` reports estimated tokens (`ceil(compact_utf8_bytes / 4)`), compact payload bytes, the requested cap, truncation, and omitted sections. `oldest_source_age_ms` and `freshness_summary` describe the packet as a whole. Raw records are not embedded; `raw_refs` contains capped opaque references.

Business warnings are advisory and use `would_block`, `warning`, `context_note`, or `unknown`. Mechanical invariants are separate and use `ready`, `degraded`, `missing`, or `unknown`.

## Consumer behavior

Cockpit validates the packet before rendering or persistence. Its Aurora client issues GET requests only and rejects URLs on ports 7102 and 8443. Successful compact packets are persisted in `agent_feed_packet_metadata`. The P1 surface polls every 15 seconds and exposes no enabled action.

There is no AgentIntent, dispatch, order, council, ranking, or execution contract in v0.
