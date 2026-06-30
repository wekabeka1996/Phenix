# Packet polling evidence

- Route: Cockpit `GET /api/agent-feed/v0/packet` → Aurora `GET /agent-feed/v0/packet`.
- Symbols: BTCUSDT, ETHUSDT.
- Requested budget: 4,400 estimated tokens.
- Polls: 10.
- Successes: 10.
- Failures during success window: 0.
- HTTP statuses: ten 200 responses.
- Unique packet IDs: 10.
- Round trip: 2,094–2,443 ms; mean 2,141.8 ms; median 2,108 ms.
- Response bodies: 11,627–11,632 bytes.
- Producer budget metadata: 11,629–11,632 bytes, 2,908 estimated tokens.
- Truncation: none.
- Oldest source age: 345,055,552–345,079,157 ms.
- Freshness per packet: `fresh=3`, `stale=3`, `missing=2`, `unknown=0`.

Aurora access logs contain ten GET packet lines and one GET readiness line. They contain no bridge POST/PATCH/DELETE line. The observation JSONL contains only `request_method="GET"`.

Failure visibility was also exercised: while Aurora was stopped, the same Cockpit GET returned HTTP 502 and a visible read-only error. It was not converted to an empty packet and was not persisted.
