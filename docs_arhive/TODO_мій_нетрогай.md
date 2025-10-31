# TODO â ” FSMP-P0 Task Tracking

## Active Tasks

_No active tasks â ” FSMP-P0-T03 completed!_

## Completed Tasks (Latest First)

### FSMP-P0-T03 â ” Concurrent WAL & Idempotency Integration âœ…

- [x] **Router integration** with single-flight idempotency API (idem.begin/complete)
- [x] **Stress tests** for concurrent WAL appends (100 threads, chain integrity verified)
- [x] **Single-flight stress test** (50 threads, same key, verified 1 execution)
- [x] **ADR-004** documentation for file-locking design (449 lines, comprehensive)
- [x] **Protocol fix**: Added "CMD" op type to protocol.py
- [x] **Test coverage**: Raised from 82% â†’ **89%** (128 tests, 476/537 lines covered)
- [x] **Performance validation**: p95(router) â‰¤50ms maintained (SLO compliance)

**Coverage breakdown**:
- 100% coverage modules: protocol.py, routing.py, idempotency.py, replay.py, why.py, rbac_abac.py, retry_cb.py
- High coverage: wal.py (75%), debug_api.py (76%)
- Remaining gaps: Unix fcntl code (platform-specific), FastAPI endpoints (async testing)

### FSMP-P0-T02 â ” Observability & DR Foundation âœ…

- [x] **FSMP-P0-T02:** Implement GET /metrics endpoint with router_p95_ms, timeout_rate, queue_depth
- [x] **FSMP-P0-T02:** Extend /debug/{rid} with why_chain, integrity_ok, merkle_root
- [x] **FSMP-P0-T02:** Extend /replay/{rid} with integrity_ok and replayed count
- [x] **FSMP-P0-T02:** Implement idempotent_key + TTL cache (10min default)
- [x] **FSMP-P0-T02:** Fix routing.py validation and CircuitBreaker.allow() logic
- [x] **FSMP-P0-T02:** WAL verify_chain() and calculate_merkle_root()
- [x] **FSMP-P0-T02:** Test suite: 29 tests, 89% coverage, mypy clean
- [x] **FSMP-P0-T02:** VS Code .venv auto-activation configuration
- [x] **FSMP-P0-T03:** Cross-platform file-locking infrastructure (_file_lock context manager)
- [x] **FSMP-P0-T03:** WAL append() with exclusive locks and fsync
- [x] **FSMP-P0-T03:** WAL append_cas() for optimistic concurrency control
- [x] **FSMP-P0-T03:** Single-flight idempotency begin/complete API with inflight registry
- [x] **FSMP-P0-T03:** Metrics for lock contention and idempotency events

---

**Convention:** One atomic task per line. After PR merge â†’ tick and remove the line in follow-up commit.
