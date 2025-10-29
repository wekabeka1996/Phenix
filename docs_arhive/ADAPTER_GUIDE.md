# Execution Adapter Guide (FSMP-P2-T01)

**Status**: ✅ Implemented  
**Version**: v1.0 (dry_run + paper modes)

---

## Overview

The **Execution Adapter** is a thin layer over exchange SDK that provides:
- **Execution modes**: `dry_run` (default), `paper`, `live`
- **Idempotency**: Exactly-once semantics via deterministic `client_order_id`
- **Reliability**: Retry with exponential backoff, circuit breaker
- **Observability**: Metrics (p95 latency, counters), structured logging with WHY≤80

---

## Execution Modes

| Mode | Description | SDK Calls | Use Case |
|------|-------------|-----------|----------|
| **dry_run** | Simulation only | None (local mock) | Testing, CI, development |
| **paper** | Sandbox/testnet | Real SDK (paper endpoint) | Pre-production validation |
| **live** | Production trading | Real SDK (live endpoint) | Production (NOT in P2-T01) |

**Default**: `dry_run` (safe by design)

---

## API Reference

### `ExecutionAdapter` (Abstract Base)

All adapters inherit from `ExecutionAdapter` and implement:

```python
from vfoundation.core.adapters.execution_adapter import (
    ExecutionAdapter,
    MockExecutionAdapter,
    OrderDTO,
    ExecutionMode
)

# Create adapter (MockExecutionAdapter for dry_run/paper)
adapter = MockExecutionAdapter(mode=ExecutionMode.DRY_RUN)
```

### Methods

#### `submit(order: OrderDTO) -> Dict[str, Any]`

Submit order to exchange.

**Parameters**:
- `order`: OrderDTO with symbol, side, qty, price, etc.

**Returns**:
- Event dict: `EVT:ORDER_PLACED` or `EVT:REJECTED`

**Raises**:
- `CBOpenError`: Circuit breaker is open
- `IdempotentDuplicateError`: Duplicate submission
- `AdapterTimeoutError`: Operation timed out
- `SDKError`: SDK returned error

**Example**:
```python
from decimal import Decimal

order = OrderDTO(
    symbol="BTCUSDT",
    side="buy",
    order_type="limit",
    qty=Decimal("0.01"),
    price=Decimal("50000"),
    idempotent_key="optional_user_key"  # For additional idempotency
)

event = adapter.submit(order)
# Returns:
# {
#   "event_type": "ORDER_PLACED",
#   "client_order_id": "abc123...",  # Generated deterministically
#   "exchange_order_id": "MOCK_1",   # None in dry_run
#   "symbol": "BTCUSDT",
#   "side": "buy",
#   "qty": 0.01,
#   "qty_remain": 0.01,
#   "status": "NEW"  # or "SIMULATED" in dry_run
# }
```

---

#### `cancel(order_id=None, client_order_id=None) -> Dict[str, Any]`

Cancel order by ID.

**Parameters**:
- `order_id`: Exchange order ID (optional)
- `client_order_id`: Client order ID (optional)
- **Must provide at least one**

**Returns**:
- Event dict: `EVT:CANCELLED` or `EVT:REJECTED`

**Raises**:
- Same as `submit()`

**Example**:
```python
event = adapter.cancel(client_order_id="abc123...")
# Returns:
# {
#   "event_type": "CANCELLED",
#   "client_order_id": "abc123...",
#   "exchange_order_id": "MOCK_1",
#   "reason": "USER_CANCEL",
#   "status": "CANCELLED"
# }
```

---

#### `async stream() -> AsyncIterator[Dict[str, Any]]`

Stream execution events from exchange WebSocket.

**Yields**:
- Event dicts: `EVT:PARTIAL_FILL`, `EVT:FILL`, `EVT:EXPIRED`, `EVT:REJECTED`

**Example**:
```python
async for event in adapter.stream():
    if event["event_type"] == "PARTIAL_FILL":
        print(f"Partial fill: {event['filled_qty']}/{event['qty']}")
    elif event["event_type"] == "FILL":
        print(f"Order filled: {event['avg_fill_price']}")
```

**Note**: MockExecutionAdapter returns no events (use real SDK adapter for streaming).

---

## Idempotency

### How It Works

1. **Deterministic Key**: `client_order_id` is generated from order parameters:
   ```
   hash64(symbol, side, qty, price_mode, reduce_only?, ts_bucket_1s, idempotent_key)
   ```

2. **Ledger Storage**: First submission stores `{key, first_seen_ts, last_status, last_event}`

3. **Duplicate Detection**: Subsequent submissions with same key → `IdempotentDuplicateError`

### Example

```python
order = OrderDTO(symbol="ETHUSDT", side="buy", qty=Decimal("1.0"), price=Decimal("3000"))

# First submit - succeeds
event1 = adapter.submit(order)

# Second submit (same params within 1s) - raises IdempotentDuplicateError
try:
    event2 = adapter.submit(order)
except IdempotentDuplicateError as e:
    print(e.why)  # "Idempotent duplicate: no-op (key=abc123...)"
```

### Configuration

- **TTL**: `IDEM_TTL_MS` (default 600,000 = 10 min)
- **Max Entries**: `IDEM_MAX_ENTRIES` (default 10,000, LRU eviction)

---

## Retry & Circuit Breaker

### Retry

**Exponential backoff** with jitter on transient failures (rate limits, timeouts).

**Configuration**:
- `ADAPTER_RETRY_MAX_ATTEMPTS`: Max retry attempts (default 3)
- `ADAPTER_RETRY_BASE_MS`: Base delay (default 100ms)
- `ADAPTER_RETRY_MAX_MS`: Max delay after backoff (default 2000ms)

**Behavior**:
- Delay = min(base_ms * 2^(attempt-1), max_ms) + jitter(0-10%)
- Only retries on `RateLimitError` or `SDKError` (not on validation errors)

---

### Circuit Breaker

Protects system from cascading failures.

**States**:
1. **CLOSED**: Normal operation
2. **OPEN**: Suppressing operations (raises `CBOpenError`)
3. **HALF_OPEN**: Testing recovery with limited probes

**Configuration**:
- `ADAPTER_CB_OPEN_THRESHOLD`: Error rate to open (default 0.5 = 50%)
- `ADAPTER_CB_COOLDOWN_MS`: Cooldown in OPEN state (default 5000ms)
- `ADAPTER_CB_HALF_OPEN_PROBES`: Probes before closing (default 3)

**Behavior**:
- Error rate > threshold → OPEN
- After cooldown → HALF_OPEN
- N successful probes → CLOSED
- Any failure in HALF_OPEN → back to OPEN

**Example**:
```python
try:
    event = adapter.submit(order)
except CBOpenError as e:
    print(e.why)  # "CB open: submit suppressed"
    # Wait and retry later
```

---

## Metrics

### Counters

- `sdk_submit_total`: Total submit calls
- `sdk_cancel_total`: Total cancel calls
- `sdk_stream_events_total`: Total stream events processed
- `sdk_retries_total`: Total retry attempts
- `sdk_cb_open_total`: Times CB opened

### Latency (p95)

- `sdk_submit_latency_ms`: p95 latency for submit (SLO: ≤25ms for mock)
- `sdk_cancel_latency_ms`: p95 latency for cancel

**Access**:
```python
print(f"Submit p95: {adapter.metrics.get_p95_submit_latency()}ms")
print(f"Retries: {adapter.metrics.sdk_retries_total}")
```

---

## Environment Variables

### Required (non-dry_run modes)

| Variable | Description | Example |
|----------|-------------|---------|
| `EXECUTION_MODE` | Mode: dry_run, paper, live | `dry_run` |
| `EXCHANGE_API_KEY` | Exchange API key | `your_api_key` |
| `EXCHANGE_API_SECRET` | Exchange API secret | `your_secret` |
| `EXCHANGE_BASE_URL` | REST API URL | `https://api.exchange.com` |
| `EXCHANGE_WS_URL` | WebSocket URL | `wss://stream.exchange.com` |

### Optional (Adapter Tuning)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADAPTER_SUBMIT_TIMEOUT_MS` | 200 | Submit timeout |
| `ADAPTER_CANCEL_TIMEOUT_MS` | 200 | Cancel timeout |
| `ADAPTER_STREAM_TIMEOUT_MS` | 5000 | Stream timeout |
| `ADAPTER_RETRY_MAX_ATTEMPTS` | 3 | Max retry attempts |
| `ADAPTER_RETRY_BASE_MS` | 100 | Retry base delay |
| `ADAPTER_RETRY_MAX_MS` | 2000 | Retry max delay |
| `ADAPTER_CB_OPEN_THRESHOLD` | 0.5 | CB error rate threshold |
| `ADAPTER_CB_COOLDOWN_MS` | 5000 | CB cooldown period |
| `ADAPTER_CB_HALF_OPEN_PROBES` | 3 | CB recovery probes |

**Note**: dry_run mode works without any ENV variables (safe default).

---

## Error Handling

All adapter errors include `ERR.code` + `WHY≤80`.

### Error Classes

| Exception | Code | When |
|-----------|------|------|
| `AdapterTimeoutError` | `ERR.adapter.timeout` | Operation exceeded timeout |
| `CBOpenError` | `ERR.adapter.cb_open` | Circuit breaker open |
| `IdempotentDuplicateError` | `ERR.adapter.idempotent_duplicate` | Duplicate operation |
| `SDKError` | `ERR.adapter.sdk_error` | SDK returned error |
| `RateLimitError` | `ERR.adapter.rate_limit` | Rate limit exceeded |
| `InvalidModeError` | `ERR.adapter.invalid_mode` | Operation not allowed in mode |
| `ConfigurationError` | `ERR.adapter.config` | Missing/invalid ENV |

### WHY Examples

```python
"CB open: submit suppressed"
"Timeout submit 250ms > 200ms limit"
"Idempotent duplicate: no-op (key=abc123...)"
"SDK error submit: INSUFFICIENT_BALANCE"
"Rate limit exceeded, retry after 1000ms"
```

---

## Usage Patterns

### Basic Submit/Cancel (Mock Adapter)

```python
from decimal import Decimal
from vfoundation.core.adapters.execution_adapter import (
    MockExecutionAdapter,
    OrderDTO,
    ExecutionMode
)

# Initialize adapter
adapter = MockExecutionAdapter(mode=ExecutionMode.DRY_RUN)

# Submit order
order = OrderDTO(
    symbol="BTCUSDT",
    side="buy",
    order_type="limit",
    qty=Decimal("0.01"),
    price=Decimal("50000")
)
event = adapter.submit(order)
print(f"Order placed: {event['client_order_id']}")

# Cancel order
cancel_event = adapter.cancel(client_order_id=event['client_order_id'])
print(f"Order cancelled: {cancel_event['status']}")
```

---

### Paper/Testnet Binding (Real SDK)

```python
import os
from decimal import Decimal
from vfoundation.core.adapters.sdk_adapter_binance import SdkAdapterBinance
from vfoundation.core.adapters.execution_adapter import OrderDTO, ExecutionMode

# Set testnet ENV variables
os.environ["EXECUTION_MODE"] = "paper"
os.environ["EXCHANGE_API_KEY"] = "your_testnet_api_key"
os.environ["EXCHANGE_API_SECRET"] = "your_testnet_api_secret"
os.environ["EXCHANGE_BASE_URL"] = "https://testnet.binance.vision/api"

# Install dependency: pip install python-binance

# Initialize paper adapter (connects to Binance testnet)
adapter = SdkAdapterBinance(mode=ExecutionMode.PAPER)

# Submit order to real testnet
order = OrderDTO(
    symbol="BTCUSDT",
    side="buy",
    order_type="limit",
    qty=Decimal("0.01"),
    price=Decimal("50000"),
    time_in_force="GTC"
)

event = adapter.submit(order)
print(f"Testnet order: {event['exchange_order_id']}")
```

**Paper Mode Requirements:**
- `EXCHANGE_API_KEY` + `EXCHANGE_API_SECRET`: Binance testnet credentials
- `EXCHANGE_BASE_URL`: Must contain "testnet" or "test"
- `python-binance` installed: `pip install python-binance`
- **Live mode BLOCKED** in P2-T01 (will be added in P2-T02 with guards)

---

### Error Handling

```python
from vfoundation.core.adapters.execution_exceptions import (
    CBOpenError,
    IdempotentDuplicateError,
    AdapterTimeoutError
)

try:
    event = adapter.submit(order)
except CBOpenError as e:
    logger.warning(f"Circuit breaker open: {e.why}")
    # Implement backoff strategy
except IdempotentDuplicateError as e:
    logger.info(f"Duplicate detected: {e.why}")
    # Use cached result from ledger
except AdapterTimeoutError as e:
    logger.error(f"Timeout: {e.why}")
    # Implement timeout recovery
```

---

### Streaming Events

```python
import asyncio

async def process_events():
    adapter = MockExecutionAdapter(mode=ExecutionMode.PAPER)
    
    async for event in adapter.stream():
        event_type = event["event_type"]
        
        if event_type == "PARTIAL_FILL":
            print(f"Partial: {event['filled_qty']}/{event['qty']}")
        elif event_type == "FILL":
            print(f"Filled at {event['avg_fill_price']}")
        elif event_type == "CANCELLED":
            print(f"Cancelled: {event['reason']}")

asyncio.run(process_events())
```

---

## Testing

### Run Tests

```bash
# Run all adapter tests
pytest tests/adapters/ -v

# Run with coverage
pytest tests/adapters/ --cov=vfoundation.core.adapters --cov-report=term

# Run specific test
pytest tests/adapters/test_execution_adapter_dry_run.py::test_adapter_submit_dry_run_ok -v
```

### Type Checking

```bash
# mypy strict mode
mypy --strict vfoundation/core/adapters
```

---

## Logging

All adapter operations log structured events:

**Format**: `ts|rid|op|verb|src→dst|key|lat_ms|err?` + `why (≤80)`

**Examples**:
```
2025-10-14T10:30:45.123Z|RID-123|adapter|submit|client→exchange|BTCUSDT|15ms|OK why="Order placed"
2025-10-14T10:30:46.456Z|RID-124|adapter|submit|client→exchange|ETHUSDT|250ms|ERR why="Timeout submit 250ms > 200ms"
2025-10-14T10:30:47.789Z|RID-125|adapter|cancel|client→exchange|abc123...|8ms|OK why="Order cancelled"
```

---

## Roadmap

### P2-T01 (Current)
- ✅ dry_run mode
- ✅ paper mode (mock SDK)
- ✅ Idempotency ledger
- ✅ Retry + CB
- ✅ Metrics (p95, counters)

### P2-T02 (Future)
- [ ] Real SDK integration (CCXT, python-binance, etc.)
- [ ] WebSocket streaming (live events)
- [ ] live mode with production guards

### P2-T03 (Future)
- [ ] Multi-exchange support
- [ ] Advanced order types (FOK, IOC, etc.)
- [ ] Position lifecycle integration

---

## Troubleshooting

### Issue: `RuntimeError: EXECUTION_MODE=paper requires ENV vars`

**Cause**: Missing `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, or `EXCHANGE_BASE_URL`

**Fix**: Set ENV variables or use `dry_run` mode:
```bash
export EXECUTION_MODE=dry_run
```

---

### Issue: `CBOpenError: CB open: submit suppressed`

**Cause**: Circuit breaker opened due to high error rate

**Fix**:
1. Check upstream service health
2. Wait for CB cooldown (default 5s)
3. Reduce load to allow recovery

---

### Issue: `IdempotentDuplicateError`

**Cause**: Duplicate submission within TTL window

**Fix**: This is expected behavior. Retrieve cached result from ledger:
```python
entry = adapter.ledger.get(client_order_id)
if entry:
    print(entry.last_event)  # Use cached event
```

---

## Distributed Idempotency (FSMP-P2-T02)

**Status**: ✅ Implemented  
**Version**: v1.0 (Redis backend)

### Overview

Distributed idempotency layer ensures **exactly-once semantics** across multiple workers:
- **Reserve**: Atomic key acquisition (Lua script)
- **Confirm**: Finalize operation result
- **Release**: Cancel/timeout cleanup
- **TTL**: Auto-expiry of stale records

**Source of truth**: Redis (distributed store)

---

### API Operations

#### Reserve (Atomic)

```python
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore

store = RedisIdempotencyStore(
    redis_url="redis://localhost:6379/0",
    worker_id="worker-1",
    ttl_ms=60_000
)

result = store.reserve(
    key="client-order-123",
    payload_digest="sha256...",
    ttl_ms=60_000,
    owner="worker-1"
)

# Result statuses:
# - NEW: Successfully reserved (first time)
# - DUPLICATE_SAME: Same payload (idempotent no-op)
# - DUPLICATE_CONFLICT: Different payload (reject)
# - EXTERN_OWNER: Held by another worker (busy)
```

#### Confirm

```python
store.confirm(
    key="client-order-123",
    final_status="ORDER_PLACED",
    meta={"exchange_order_id": "EX-456"}
)
```

#### Release

```python
store.release(key="client-order-123", owner="worker-1")
```

---

### ENV Configuration

```bash
# Redis connection
REDIS_URL="redis://localhost:6379/0"

# Idempotency settings
IDEMP_TTL_MS=60000              # Lease duration (60s)
IDEMP_TIMEOUT_MS=100            # I/O timeout
IDEMP_RETRY_MAX_ATTEMPTS=3      # Retry attempts
IDEMP_RETRY_BASE_MS=50          # Base retry delay
IDEMP_RETRY_MAX_MS=1000         # Max retry delay
IDEMP_CB_THRESHOLD=0.6          # CB error rate threshold
IDEMP_CB_COOLDOWN_MS=3000       # CB cooldown period
IDEMP_CB_HALF_OPEN_PROBES=2     # CB half-open probes
WORKER_ID="worker-1"            # Unique worker ID
```

---

### Error Codes (WHY≤80)

| Error | Code | WHY Example | Description |
|-------|------|-------------|-------------|
| Conflict | `ERR.idemp.conflict` | `idemp conflict: key=order-001` | Different payload for same key |
| Busy | `ERR.idemp.busy` | `idemp busy: owner=w2` | Key held by another worker |
| Timeout | `ERR.idemp.timeout` | `idemp timeout: reserve 150ms > 100ms` | Operation timed out |
| CB Open | `ERR.idemp.cb_open` | `cb open: idemp reserve` | Circuit breaker is open |
| Missing | `ERR.idemp.missing` | `idemp missing: confirm key=...` | Record not found |
| Store | `ERR.idemp.store` | `idemp store: reserve failed` | Backend error |

---

### Integration with Adapter

Adapter calls `store.reserve()` **before** SDK submit/cancel:

```python
# In ExecutionAdapter.submit():
digest = hashlib.sha256(payload.encode()).hexdigest()

try:
    result = self.store.reserve(
        key=client_order_id,
        payload_digest=digest,
        ttl_ms=self.config.idemp_ttl_ms,
        owner=self.config.worker_id
    )
    
    if result.status == ReserveStatus.NEW:
        # Call SDK (first time)
        sdk_response = self.sdk.submit(order)
        
        # Confirm after success
        self.store.confirm(
            key=client_order_id,
            final_status="ORDER_PLACED",
            meta=sdk_response
        )
        
        return build_event(sdk_response)
    
    elif result.status == ReserveStatus.DUPLICATE_SAME:
        # Idempotent no-op: return cached result
        status = self.store.get_status(client_order_id)
        return build_event_from_cache(status.meta)
    
    elif result.status == ReserveStatus.DUPLICATE_CONFLICT:
        # Should not reach here (reserve raises ConflictError)
        pass

except ConflictError as e:
    # Reject: different payload for same key
    return {"event_type": "REJECTED", "error": e.why}

except BusyError as e:
    # Backoff and retry (1-2 attempts)
    time.sleep(0.1)
    # ... then fail with ERR.idemp.busy
    return {"event_type": "REJECTED", "error": e.why}
```

---

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `idemp_reserve_total{status}` | Counter | Reserve operations by status |
| `idemp_confirm_total{status}` | Counter | Confirm operations by status |
| `idemp_release_total{status}` | Counter | Release operations by status |
| `idemp_conflict_total` | Counter | Conflict errors |
| `idemp_busy_total` | Counter | Busy errors |
| `idemp_retries_total` | Counter | Retry attempts |
| `idemp_cb_open_total` | Counter | CB open events |
| `idemp_reserve_latency_ms` | Histogram | Reserve latency (p95 ≤ 10ms SLO) |
| `idemp_confirm_latency_ms` | Histogram | Confirm latency (p95 ≤ 10ms SLO) |

---

### Testing

```bash
# Run idempotency tests
pytest tests/idempotency/ -v

# Coverage check (target ≥90%)
pytest tests/idempotency/ --cov=vfoundation.core.idempotency --cov-report=term-missing
```

---

## References

- **Architecture**: `docs/CENTRAL_FSM_SPEC.md`
- **ACL Adapter**: `docs/ACL-Adapter.md`
- **Config**: `vfoundation/config.py`
- **Tests**: `tests/adapters/`, `tests/idempotency/`

---

**Last Updated**: 2025-10-14  
**Author**: vFoundation Team  
**RID**: FSMP-P2-T02

