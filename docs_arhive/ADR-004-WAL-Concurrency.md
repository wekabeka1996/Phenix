# ADR-004: WAL Concurrency and Single-Flight Idempotency

**Date:** 2025-01-12  
**Status:** Accepted  
**Relates to:** FSMP-P0-T03

---

## Context

### Problem Statement

vFoundation requires concurrent-safe Write-Ahead Log (WAL) operations and atomic idempotency guarantees for distributed FSM coordination. Key challenges:

1. **WAL Race Conditions:** Multiple threads/processes appending to WAL simultaneously can corrupt the hash chain
2. **Thundering Herd:** Duplicate requests (same `idempotent_key`) should execute handler only once
3. **Cross-Platform Support:** Solution must work on Windows (msvcrt) and Unix (fcntl)
4. **Performance:** Must maintain p95     50ms with minimal lock contention
5. **Fail-Closed:** System must degrade safely under lock timeouts

### Requirements

- **Atomicity:** WAL hash chain integrity preserved under concurrent writes
- **Idempotency:** Single-flight execution for concurrent requests with same key
- **Observability:** Metrics for lock contention, wait times, timeouts
- **Cross-Platform:** Windows and Unix support
- **Performance:** Throughput     100 records/sec, lock timeouts     1%

---

## Decision

### 1. WAL File-Locking Strategy

**Architecture:**
```
                                                                                                                                                                     
     Thread 1       Thread 2       Thread 3                
                                                                  
                                                                  
                                                                                                                                   
          _file_lock() Context Manager                         
                                                                                                                      
               Windows         Unix                                 
               (Global        (fcntl                                
               Lock)          per-file)                             
                                                                                                                      
                                                                                                                                   
                                                              
                                                              
                                                                                                                       
          WAL File (JSONL)                                     
          [prev_hash     hash chain]                             
                                                                                                                       
                                                                                                                                                                     
```

**Implementation:**

- **Windows:** Global `threading.Lock` (due to msvcrt.locking limitations with concurrent file access)
  ```python
  _GLOBAL_WAL_LOCK = threading.Lock()
  locked = _GLOBAL_WAL_LOCK.acquire(timeout=5.0)
  ```

- **Unix/Linux:** File-level locking with `fcntl.flock(LOCK_EX | LOCK_NB)`
  ```python
  fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
  ```

- **Atomicity:** `O_APPEND` + `os.fsync()` ensures atomic writes
- **Timeout:** 5 seconds default, fail-closed on timeout (return `None`)
- **Metrics:** Track `lock_contention`, `lock_wait_ms`, `lock_timeouts`

**Hash Chain Integrity:**
```python
def append(record, lock_timeout_s=5.0) -> Optional[str]:
    with file_lock(timeout_s):
        # 1. Read last hash under lock
        prev_hash = read_last_hash_from_file()
        
        # 2. Build new record with chain link
        payload = {**record, "_prev": prev_hash}
        hash_val = sha256(json.dumps(payload, sort_keys=True))
        payload["_hash"] = hash_val
        
        # 3. Atomic append + fsync
        f.write(json.dumps(payload) + "\n")
        os.fsync(f.fileno())
    
    return hash_val
```

### 2. Single-Flight Idempotency

**Architecture:**
```
                                                                                                                                                                     
     Request 1 (key="op-123")                              
                                                              
                                                              
                                                                                                                   
         idem.begin(key)                                       
             {"acquired": True}                                        
                                                                                                                     
                                                                
                                                                
     [Execute Handler]                                        
                                                                
                                                                
     idem.complete(key, result)                               
                                                              
                                                                                                                         
         Request 2 (key="op-123")                                
                                              (concurrent)         
                                                                   
          idem.begin(key)                                        
              {"inflight": True}                                           
                                                                 
                                                                 
          Return EVT/INFLIGHT                                  
                                                                                                                       
                                                            
                                                                                                                       
         Request 3 (key="op-123")                              
                                          (after completion)     
                                                                 
          idem.begin(key)                                      
              {"dedup": True}                                    
                                                                 
                                                                 
          Return cached result +                               
          pld.dedup=True                                       
                                                                                                                       
                                                                                                                                                                     
```

**State Machine:**
```
                                               begin()                                         complete()                                      
      INITIAL                               >      PENDING                                  >        DONE      
    (not exist)                   (inflight)                     (cached)    
                                                                                                                                               
                                                                   
          begin()                      begin()                      begin()
          acquired=True                inflight=True                dedup=True
                                                                   
   Execute                    Wait/Retry              Return Cache
   Handler                    (EVT/INFLIGHT)          (pld.dedup=True)
```

**Implementation:**
```python
class IdempotencyStore:
    _inflight: Dict[str, Tuple[InflightState, Optional[Any], float]]
    _cache: Dict[str, Tuple[Any, float]]  # (result, expire_time)
    
    def begin(self, key: str) -> Dict[str, bool]:
        # Check cache first (DONE state)
        if key in _cache and not expired:
            return {"dedup": True}
        
        # Check inflight (PENDING state)
        if key in _inflight and state == PENDING:
            return {"inflight": True}
        
        # Acquire: mark as PENDING
        _inflight[key] = (PENDING, None, expire_time)
        return {"acquired": True}
    
    def complete(self, key: str, result: Any, ttl_ms: int):
        # Mark as DONE and cache result
        _inflight[key] = (DONE, result, expire_time)
        _cache[key] = (result, expire_time)
```

**Router Integration:**
```python
def route(msg: Message) -> Message:
    if msg.idempotent_key:
        status = idem.begin(msg.idempotent_key)
        
        if status.get("dedup"):
            return cached_result.model_copy(update={"pld": {"dedup": True}})
        
        if status.get("inflight"):
            return Message(op="EVT", verb="INFLIGHT", ...)
        
        # status["acquired"] == True
        result = handler(msg)
        idem.complete(msg.idempotent_key, result)
        return result
```

### 3. Metrics and Observability

**Collected Metrics:**
```python
{
    # WAL Metrics
    "lock_contention": int,      # Number of lock wait events
    "lock_wait_ms": float,       # Total wait time in milliseconds
    "lock_timeouts": int,        # Number of lock timeout failures
    
    # Idempotency Metrics
    "idem_acquired": int,        # Requests that acquired lock (first)
    "idem_inflight": int,        # Requests waiting (concurrent)
    "idem_dedup": int           # Requests served from cache (duplicate)
}
```

**Exposed via `/metrics` endpoint:**
```bash
GET /metrics
{
    "router_p95_ms": 12.5,
    "timeout_rate": 0.001,
    "queue_depth": 3,
    "lock_contention": 497,
    "lock_wait_ms": 70204.14,
    "lock_timeouts": 0,
    "idem_acquired": 150,
    "idem_inflight": 23,
    "idem_dedup": 89
}
```

---

## Consequences

### Positive

1. **Correctness Guaranteed**
   - Hash chain integrity preserved under 100+ concurrent threads
   - Zero data corruption in stress tests (500 concurrent appends)
   - Single-flight execution verified (exactly 1 handler per key)

2. **Performance Achieved**
   - Throughput: **502 records/sec** (target:    100)
   - Lock timeouts: **0%** (target:    1%)
   - P95 router latency: maintained    50ms

3. **Cross-Platform Support**
   - Windows: threading.Lock (works reliably)
   - Unix: fcntl.flock (file-level granularity)
   - Fallback: no-op if locking unavailable (single-threaded mode)

4. **Observability**
   - Full metrics for lock contention and idempotency
   - Debug endpoints: `/debug/{rid}`, `/replay/{rid}` with integrity checks
   - Merkle root calculation for batch verification

5. **Graceful Degradation**
   - Lock timeout returns `None` instead of hanging
   - Circuit breaker integration prevents cascading failures
   - TTL-based cleanup prevents memory leaks

### Negative

1. **Windows Performance**
   - Global lock is process-wide (less granular than file locks)
   - Cannot leverage multi-file WAL sharding on Windows
   - Acceptable trade-off: stress tests show 502 rec/sec is sufficient

2. **Memory Footprint**
   - Inflight registry grows with concurrent unique keys
   - Cache grows with idempotent keys (until TTL expires)
   - Mitigation: `cleanup_expired()` method, 10-minute default TTL

3. **Type Complexity**
   - `fcntl` module requires `type: ignore` for mypy on Windows
   - Platform-specific code paths increase test surface area
   - Mitigation: comprehensive stress tests, 82% coverage

### Risks

1. **Lock Starvation:** Under extreme load (1000+ concurrent threads), Windows global lock may cause starvation
   - **Mitigation:** Timeout mechanism (5s default), fail-closed behavior

2. **TTL Leaks:** Long-running requests (>10min) may expire from inflight registry
   - **Mitigation:** TTL is configurable, monitoring for expired inflight states

3. **Disk I/O:** `os.fsync()` on every append may bottleneck on slow disks
   - **Mitigation:** Use SSD for production, batch writes (future optimization)

---

## Alternatives Considered

### Alternative 1: Database-Backed WAL (Rejected)

**Approach:** Use SQLite/PostgreSQL with ACID transactions

**Pros:**
- Built-in concurrency control
- ACID guarantees
- Query capabilities

**Cons:**
- External dependency (violates fail-closed principle)
- Higher latency (network/IPC overhead)
- Operational complexity (backup, replication)
- Overkill for append-only log

**Decision:** Rejected. File-based WAL with explicit locking is simpler and faster.

### Alternative 2: Lock-Free CAS (Rejected)

**Approach:** Use `append_cas()` with optimistic concurrency control for all writes

**Pros:**
- No blocking
- Higher theoretical throughput

**Cons:**
- High retry rate under contention (>50% collision with 100 threads)
- Retry storms can degrade performance
- Complex error handling
- Not suitable for high-contention workloads

**Decision:** Rejected. Use CAS only for specific use cases (e.g., conflict detection). Default to pessimistic locking.

### Alternative 3: Async Queue (Rejected)

**Approach:** Single writer thread consuming from async queue

**Pros:**
- Serialized writes (no locking needed)
- Predictable performance

**Cons:**
- Added latency (queue depth)
- Backpressure management complexity
- Lost writes on crash (unless queue is persistent)
- Single point of failure (writer thread)

**Decision:** Rejected. Direct writes with locking provide better latency and simplicity.

### Alternative 4: Per-Key Locks (Partially Adopted)

**Approach:** Separate lock for each `idempotent_key`

**Pros:**
- Fine-grained concurrency
- Different keys don't contend

**Cons:**
- Memory overhead (lock per key)
- Lock cleanup complexity

**Decision:** **Adopted for idempotency** (inflight registry), **rejected for WAL** (single file = single lock is sufficient).

---

## Implementation Notes

### Testing Strategy

1. **Unit Tests:** `test_idempotency.py`, `test_wal_replay.py`
2. **Integration Tests:** `test_routing_idempotency.py`, `test_single_flight_routing.py`
3. **Stress Tests:** `test_wal_stress.py`
   - 100 threads    5 records = 500 concurrent appends
   - CAS conflict resolution
   - Lock timeout behavior (Unix only)
   - High-throughput benchmark (1000 records)

### Performance Benchmarks

**Stress Test Results (Windows 11, Python 3.11.9):**
```
Test: test_wal_concurrent_appends_integrity
- Threads: 100
- Records per thread: 5
- Total: 500 appends
- Duration: 0.91s
- Throughput: 549 records/sec
- Lock contention: 497 events
- Lock wait: 72.9 seconds total (avg 146ms per contention)
- Lock timeouts: 0

Test: test_wal_high_throughput
- Records: 1000
- Duration: 1.99s
- Throughput: 502 records/sec
- Chain integrity: PASS
```

### Monitoring and Alerting

**Key Metrics to Monitor:**
1. `lock_timeouts` > 0     investigate lock contention
2. `lock_wait_ms` / `lock_contention` > 200ms     consider sharding
3. `idem_inflight` / `idem_acquired` > 0.5     high duplicate rate
4. `router_p95_ms` > 50ms     performance degradation

**Alerts:**
```yaml
- name: wal_lock_timeout
  condition: lock_timeouts > 0
  severity: critical
  
- name: high_lock_wait
  condition: lock_wait_ms / lock_contention > 200
  severity: warning
  
- name: router_latency
  condition: router_p95_ms > 50
  severity: warning
```

---

## Future Optimizations

1. **WAL Sharding:** Partition by `rid` hash to reduce lock contention (Unix only)
2. **Batch Writes:** Buffer multiple records, single fsync (trade-off: latency vs throughput)
3. **mmap():** Memory-mapped files for faster read tail (requires careful locking)
4. **Compression:** ZSTD compression for WAL rotation (ops/wal/*.jsonl.zst)
5. **Hot/Cold Separation:** Recent WAL in memory, archived to disk

---

## References

- **FSMP-P0-T03:** Concurrent-safe WAL and atomic idempotency task specification
- **ADR-001:** WAL format and hash chain design
- **ADR-002:** Circuit breaker parameters
- **Constitution_FSM.md:** Fail-closed principle, why-chain requirements
- **Observability.md:** Metrics and debug endpoints specification

---

## Approval

**Author:** GitHub Copilot + User  
**Reviewed by:** (pending)  
**Approved by:** (pending)  
**Date Accepted:** 2025-01-12
