# Public exchange-info cache design

- Exact allowlist: Binance USD-M live/testnet `fapi/v1/exchangeInfo`; P6 enables testnet.
- HTTP surface: GET only, no redirects, authentication headers, signing, adapter, or command methods.
- Bounds: 10-second timeout, 2 MiB response, 64 KiB persisted model, 12 symbols.
- Scheduling: daemon refresh, 900-second TTL, 60-second failure retry, clean shutdown.
- Persistence: same-directory temporary file, file fsync, atomic replace, parent fsync where supported.
- Failure: retain last successful values as stale with bounded error metadata; no values means missing.
- Content: timestamps, environment/endpoint, required and optional filter values, filter names, missing/unsupported filters, status/error.
