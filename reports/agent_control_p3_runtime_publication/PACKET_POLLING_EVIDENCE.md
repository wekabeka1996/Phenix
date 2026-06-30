# Packet polling evidence

- Path: Cockpit GET proxy → Aurora `GET /agent-feed/v0/packet`.
- Symbols: BTCUSDT, ETHUSDT.
- Polls: 10; successes: 10; failures: 0.
- Unique packet ids: 10.
- SQLite rows: 10 before, 20 after; exactly 10 inserted.
- Packet budget: 9,734–9,737 bytes and 2,434–2,435 estimated tokens.
- Truncation: none.
- Freshness on every poll: `fresh=8, stale=0, missing=0, unknown=0`.
- Oldest source age: 814,463–819,260 ms, within the configured 15-minute market freshness corridor during observation.
- Round trip: 14–48 ms; mean 25.7 ms; median 26 ms.

All observation envelopes record `request_method=GET` and HTTP 200. Aurora access logs contained packet GETs only for this path. No order or consequential call was made.
