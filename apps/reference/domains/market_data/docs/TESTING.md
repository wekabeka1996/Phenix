# Market Data Testing

## Overview
The `market_data` domain implements a comprehensive testing strategy covering Unit, Integration, and **Forensic** stress tests.

**Pass Rate:** 100% (Standard Suite)
**Status:** Incomplete Forensic Coverage (Tests for leaks missing in CI/CD).

---

## 1. Standard Test Structure (`test_market_data.py`)

Run these tests for general regression checking.

```bash
pytest tests/domains/test_market_data*.py -v
```

### Coverage Areas
-   **Initialization:** Validates config loading and defaults.
-   **Message Processing:** Ensures JSON from Binance converts to correct `EVT:MARKET_TICK`.
-   **Sequence Control:** Checks that strictly ordered updates (seq+1) are accepted.
-   **Error Handling:** Validates that 500/400 errors don't crash the main loop.

---

## 2. Forensic Test Suite (Stress & Chaos)

These tests are designed to expose architectural flaws identified in the Jan 2026 Audit.

### Case A: Memory Leak Simulation
**Objective:** Prove `seen_trade_ids` causes OOM.
**Run:**
```python
# Pseudo-code for reproducing leak
def test_memory_leak():
    agg = WebSocketAggregator()
    # Pumping 1M unique trades
    for i in range(1_000_000):
        agg.on_trade(..., id=i)
    
    import sys
    print(sys.getsizeof(agg.seen_trade_ids))
    # Expectation: Size > 100MB
```
**Fix Verification:** Run same test with `maxlen=10000` fix. Size should plateau at ~2MB.

### Case B: Blackhole Connection
**Objective:** Ensure `worker.py` detects silent socket death.
**Setup:** Use `toxiproxy` to cut bandwidth to 0 byte/s while keeping TCP connected.
**Expectation:** Worker should raise `TimeoutError` in 30s.
**Current Reality:** Worker hangs indefinitely (Test Fails).

### Case C: Out-of-Order (OOO) Data
**Objective:** Measure impact of network jitter.
**Scenario:** Send ticks `100`, `102`, `101`.
**Current Reality:** `101` is dropped.
**Desired Reality:** `101` is reordered and processed.

---

## 3. Performance Testing

### Latency Benchmarks
-   **Event Emission:** < 0.05ms (Async Emit).
-   **Data Processing:** < 1ms per batch.
-   **Throughput:** Capable of processing 1000 ticks/sec on single core.

### Testing Commands
```bash
# Run with coverage report
pytest --cov=apps.reference.domains.market_data

# Run performance timing
pytest --durations=10
```

---

## 4. Mock Infrastructure

We utilize `MockFSM` and `MockBinanceAdapter` to simulate the environment.

```python
class MockFSM:
    def __init__(self):
        self.events = []
    
    async def emit_event(self, type, payload):
        self.events.append((type, payload))
```

**Note:** For Forensic tests, we must mock at the *Socket* level (aiohttp), not just the Adapter level, to simulate real network failures.
