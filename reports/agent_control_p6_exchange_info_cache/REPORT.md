# AURORA_AGENT_CONTROL_P6_PUBLIC_EXCHANGE_INFO_CACHE_AND_FILTER_PARITY_DIAGNOSTICS

## Problem framing

P5 exposed configured precision constraints but had no credential-free owner proving current exchange parity. P6 adds public metadata evidence only; it does not add execution or agent authority.

## FACTS

- The cache uses only `GET https://testnet.binancefuture.com/fapi/v1/exchangeInfo`, without credentials, signing, redirects, or adapter access.
- The bounded atomic cache contains seven configured symbols and is 3,542 bytes.
- BTCUSDT public filters are tick `0.10`, step `0.0001`, min qty `0.0001`, max qty `1000`, min notional `50`.
- ETHUSDT public filters are tick `0.01`, step `0.001`, min qty `0.001`, max qty `10000`, min notional `20`.
- ETHUSDT matches SSOT. BTCUSDT configured step/min qty/min notional are stricter compatible values, classified `minor_mismatch`.
- Both requested filter descriptors are `ready/exchange_confirmed`; P5 precision/minimum and reduce-only runtime-owner descriptors remain intact.
- Ten Cockpit GET polls succeeded and SQLite rows increased from 40 to 50.
- Final no-order runtime logs contain zero signed HTTP, order/create/place/cancel/modify/amend, or non-GET AgentFeed calls.

## INFERENCES

- BTC configuration is conservative relative to current testnet metadata and should not be automatically relaxed.
- Public filter confirmation improves mechanical visibility but does not prove exchange acceptance or permission to trade.

## ASSUMPTIONS

- Fetch freshness is measured from successful receipt time; Binance `serverTime` remains separately recorded as source time.
- The hybrid profile compares instrument SSOT with its execution venue, Binance USD-M testnet.

## UNKNOWNS

- Exchange acceptance of any order remains intentionally untested.
- Max notional is absent in the returned testnet filters; max position is not represented by this metadata endpoint.

## Root cause versus symptom

The root cause was absence of a safe public metadata owner. `configured_only` readiness was the symptom. P6 resolves ownership without changing execution configuration.

## Implementation summary

Added strict typed configuration, an allowlisted bounded background cache, atomic persistence, parity contracts/classification, P6 descriptor integration, requested-symbol packet projection, lifecycle shutdown, and no-order composition hardening that omits authenticated account and strategy hydration clients.

## Cache and fetch results

The cache is at `ops/agent_bridge/exchange_info/public_exchange_info_cache_v0.json`, uses a 900-second TTL and 60-second retry, and stores projected filter fields rather than the 877 KB raw exchange payload. Fetch status is `ok`.

## Parity and readiness

ETH is `match`; BTC is `minor_mismatch`. Both remain `ready/exchange_confirmed` because metadata is fresh and complete and BTC's configured grid/minima are stricter. Material, stale, missing-exchange, missing-config, and unavailable paths are test-covered and cannot become ready.

## Runtime observation

Aurora final PIDs are 22824/25520 under `agent_bridge_observation_only`; read host is 18080 and Cockpit is 18081. Cockpit remained `armed=false`, `status=stopped`. An internal Aurora listener exists on 7102, but Cockpit neither targeted nor connected to it; its client test rejects 7102/8443.

Early runtime attempts exposed legacy signed account and strategy-hydration reads. Those attempts were stopped immediately. The final composition omits both owners and its bounded log has no signed/authenticated HTTP. A malformed portfolio fallback was also corrected to the registered schema before final validation. Before every restart only `ops/wal/*.json` was targeted for removal.

## Latency and token budget

Ten polls completed in 2,049-2,135 ms, mean 2,073.6 ms. Packets were 14,866-14,869 bytes and 3,717-3,718 estimated tokens of 4,400, with no truncation.

## Files changed

See `FILES_CHANGED.md`.

## Tests and validation

Python focused cache, descriptor, publication, no-order, route, adapter and filter suites pass (60 passed, 4 skipped). Cockpit lint/build and focused AgentFeed tests pass. The broader Cockpit trading-agent suite has one pre-existing EZE OPEN_INTENT failure unrelated to P6; 38/39 passed.

## What is proven

- Credential-free public filter acquisition and bounded atomic persistence.
- Fresh exchange-confirmed BTC/ETH descriptors and compact requested-symbol parity.
- Safe stale/missing/material mismatch degradation.
- GET-only Cockpit polling and persistence with actions disabled.

## What remains unproven

- Order execution, reduce-only exchange acceptance, AgentIntent, and agent authority.
- Automatic configuration correction, deliberately out of scope.

## Risks

- Testnet metadata can drift after the 900-second TTL.
- Conservative BTC SSOT differs from exchange minima and should remain an explicit operator decision.

## P7 recommendation

Keep P7 read-only: add operator-facing acknowledgement/history for parity drift. Do not add automatic YAML correction or execution authority.

## Final verdict

P6_EXCHANGE_INFO_CACHE_VALIDATED_WITH_PARITY_WARNINGS
