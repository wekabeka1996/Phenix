# PriceService Contract (v0, additive-only)

Status: Draft
Created: 2025-11-12
Maintainer: Architecture WG

## Purpose
Provide a single source of truth (SSOT) for prices consumed by domains (decision_making, execution_position, exposure_guard, position_tracking), eliminating fragmentation and implicit payload fallbacks.

## Data Model
- PriceQuote
  - symbol: string (e.g., "BTCUSDT")
  - mark: float | null
  - last: float | null
  - mid: float | null
  - ts: int (epoch ms)
  - source: "MARK" | "LAST" | "MID"

## API
- get_mark(symbol: str, ttl_ms: int = 250) -> PriceQuote
- get_last(symbol: str, ttl_ms: int = 250) -> PriceQuote
- get_mid(symbol: str, ttl_ms: int = 250) -> PriceQuote
- get_current(symbol: str, working_type: str = "MARK", ttl_ms: int = 250) -> PriceQuote

Notes:
- All methods are non-breaking additions.
- TTL provides read-through cache semantics backed by adapter calls.
- Working type policy defines fallback chain:
  - Default: MARK -> LAST -> MID
  - Configurable per symbol in future versions.

## Metrics
- price.cache_hit_total{symbol,kind}
- price.adapter_calls_total{symbol,endpoint}
- price.latency_ms_bucket{symbol,kind}
- price.fallback_taken_total{from,to}
- price.errors_total{class}

## Error Taxonomy (subset)
- AdapterTransientError (network timeout, -1021 time sync)
- AdapterRateLimitError
- AdapterFatalError (bad symbol)
- DataIntegrityError (nonnumeric payload)

## Consumers Matrix (initial)
- decision_making: `get_current(..., working_type=MARK)` for sizing and thresholds
- execution_position Entry/Manage: reference price for brackets and quick-profit
- manage_flow.quick_profit: real-time PnL calculation via mark price (short TTL, e.g., 100ms)
- exposure_guard: valuation for margin/notional (replace entry-price approximation)
- position_tracking: unrealized PnL via mark
- feature_engineering: continues to consume tick stream independently (not SSOT)

## Non-Goals (v0)
- No persistence. No historical bar aggregation. No cross-venue best-price.

## Future Extensions
- Per-symbol working_type policies; circuit breakers; cross-venue arbitrage guard.
- Subscription API for push updates.

## Acceptance Criteria
- Zero breaking changes (purely additive files & imports).
- Domains must compile without referencing adapter prices directly when integrated.
- Metrics emitted for cache, fallback, and adapter usage.

## References
- `vfoundation/core/adapters/base.py` — async `get_mark_price`/`get_last_price`
- `apps/reference/domains/execution_position/fsm_manage.py` — current payload fallback patterns
- `docs/AUDIT_VERIFICATION_LOG.md` — SSOT remediation rationale

---

## Concurrency Model
- PriceService is asyncio-native (public methods designed to be async in v1; v0 may expose sync wrappers while keeping thread-safety constraints).
- Internal cache operations are protected by an asyncio.Lock (single instance per event loop recommended).
- Safe for concurrent access from multiple domains within one event loop; if multi-threaded access is required, calls must be marshalled onto the owning loop.

## Cache Policy
- TTL-based expiration (default 250ms) with read-through fetch from the exchange adapter.
- LRU eviction when cache exceeds 100 symbols (configurable).
- Force refresh supported via `ttl_ms=0`.
- Stale-while-revalidate policy: on adapter transient errors, serve last non-expired value and trigger background refresh where applicable.

## Fallback Configuration (v0 → v1)
- Default chain: `MARK → LAST → MID`.
- v0: global default chain only.
- v1 (future): per-symbol chains via config:

```yaml
price_service:
  fallback_chains:
  BTCUSDT: [MARK, LAST]
  ETHUSDT: [MID, LAST]
  default: [MARK, LAST, MID]
```

## Error Handling Patterns (Examples)
```python
try:
  quote = await price_service.get_mark("BTCUSDT")
except AdapterTransientError:
  # Retry with exponential backoff, or rely on stale-while-revalidate
  ...
except AdapterRateLimitError:
  # Use cached value if available, delay next adapter call
  ...
except AdapterFatalError:
  # Invalid symbol / permanent failure: surface to caller
  raise
```

Additional error classes (planned v0.5):
- CacheError — cache corruption or invariant breach.
- FallbackExhaustedError — all sources (MARK/LAST/MID) returned None.

## Migration Strategy
Phase 1 (Additive):
- Add PriceService in `vfoundation/services/`; no breaking changes; domains unchanged.

Phase 2 (Integration via feature flag):
- decision_making uses `get_current()`; execution_position uses PriceService for brackets; exposure_guard switches to PriceService for margin; position_tracking uses mark for unrealized PnL.

Phase 3 (Deprecation and Cutover):
- Remove direct `adapter.get_mark_price()` usages; emit deprecation warnings for two weeks; finalize cutover after validation.

## Performance Targets
| Metric | Target | Rationale |
|--------|--------|-----------|
| Cache hit latency | < 1 ms | In-memory lookup |
| Cache miss latency | < 50 ms | Adapter call + network |
| p99 latency | < 100 ms | Hot path SLO alignment |
| Cache hit rate | > 90% | With 250 ms TTL |
| Memory usage | < 10 MB | ~100 symbols |

## Testing Requirements
- Unit: cache logic, TTL expiration, fallback chain behavior, force refresh.
- Integration: adapter mocking for transient/fatal errors; stale-while-revalidate paths.
- E2E: decision → execution with PriceService gated by feature flag.
- Performance: cache hit rate, p99 latency under load.

## Observability
- Metrics (Prometheus): cache hits/misses, adapter calls, latency buckets, fallbacks, errors, cache size/evictions, stale served counters.
- Structured logging: INFO (cache hit/miss), WARN (fallback taken), ERROR (adapter fatal).
- Tracing: span/trace IDs propagated for price fetch.
- Optional debug endpoint: `GET /debug/price/{symbol}` returning last quote + source.

## Implementation Notes
### Cache Structure
```python
_cache: Dict[str, Tuple[PriceQuote, float]]  # symbol -> (quote, expire_ts)
_lock: asyncio.Lock
_adapter: ExchangeAdapter  # exposes get_mark_price/get_last_price
```

### Fallback Logic
```python
async def get_current(symbol: str, working_type: str = "MARK", ttl_ms: int = 250) -> PriceQuote:
  quote = await _get_cached_or_fetch(symbol, ttl_ms)
  # Preference order based on working_type
  order = {
    "MARK": ("mark", "last", "mid"),
    "LAST": ("last", "mark", "mid"),
    "MID": ("mid", "mark", "last"),
  }[working_type]
  for attr in order:
    val = getattr(quote, attr)
    if val is not None:
      return PriceQuote(**{**quote.__dict__, "source": attr.upper()})
  raise FallbackExhaustedError(f"No price available for {symbol}")
```

### Thread Safety
- All cache mutations occur under `_lock`.
- Adapter calls should be issued outside the lock where possible to avoid blocking other readers.

## Quick Profit Integration (Wave 0.5)
Quick Profit ($2 target) requires low-latency mark price to compute real-time PnL:

```python
quote = await price_service.get_mark(symbol, ttl_ms=100)
current_price = Decimal(str(quote.mark))
# Compute PnL vs entry price and position size, then trigger close on threshold
```

Benefits:
- Consistent source (no mark vs last confusion).
- Cache reduces latency on hot path; TTL can be tuned per use case.
