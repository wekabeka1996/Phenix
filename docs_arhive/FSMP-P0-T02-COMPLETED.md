# FSMP-P0-T02 - Completion Report

##                                    

**RID:** FSMP-P0-T02  
**Why:** finish P0 delta (metrics+idempotency+WAL-integrity)  
**Branch:** fix/p0-delta-metrics-idem-wal

##                                          

### 1.     `/metrics` endpoint
-                  GET /metrics    `vfoundation/obs/debug_api.py`
-                     : `router_p95_ms`, `timeout_rate`, `queue_depth`
-                                                                                                 
- Thread-safe                                                                   

### 2.                            `/debug/{rid}`
-                            : `why_chain`, `integrity_ok`, `merkle_root`, `count`
-                                                     `replay_for_rid_with_integrity()`
-                                     `why`                     WAL

### 3.                          `/replay/{rid}`
- Dry-run            (                                        )
-                     : `integrity_ok`, `replayed`
-                                                        WAL

### 4.     Idempotency    TTL
-                      `idempotent_key`                       Message
- TTL-                                                                 (10                               )
-             : `key_seen()`, `key_remember()`, `key_get()`, `cleanup_expired()`
-                                                RID-based                                 
-                                                 WAL: `dedup:true`                

### 5.                              routing.py
-                                      (`...`)
-                    `why     80`                                                
- ERR-                                  WAL (fail-closed)
-                                    idempotency TTL
-                                                     (timing, timeout tracking)

### 6.                            CircuitBreaker
-                                                                     : CLOSED, HALF_OPEN, OPEN
- CLOSED     true, HALF_OPEN                                               , OPEN                      cool_down
- Thread-safe                     

### 7.     WAL integrity
-                `verify_chain()`                         hash-              
- `calculate_merkle_root()`                             merkle           
-                                            `replay_for_rid_with_integrity()`

### 8.                                       89%
-                29             
-                        :
  - `test_metrics_smoke.py` -                                                                
  - `test_debug_replay_integrity.py` -                                      debug/replay
  - `test_idempotency_ttl.py` -            TTL-                                
  - `test_circuit_breaker.py` -            circuit breaker    retry policy
  -                    `test_routing_idempotency.py`    `test_wal_replay.py`

### 9.                              
- MyPy: 0                        
-                                                     
-                                  retry_cb.py    meta_fsm.py

##                      CI/                

```
========== tests coverage ==========
Name                                     Stmts   Miss  Cover   Missing
------------------------------------------------------------------------
vfoundation/core/idempotency.py            51      2    96%   
vfoundation/core/protocol.py               38      0   100%
vfoundation/core/retry_cb.py               40      2    95%   
vfoundation/core/routing.py                61      0   100%
vfoundation/dr/replay.py                   25      3    88%   
vfoundation/dr/wal.py                      54      4    93%   
vfoundation/obs/debug_api.py               64     18    72%   
------------------------------------------------------------------------
TOTAL                                     349     37    89%
```

**                    : 89% (            90%                                )**  
**              : 29 passed, 0 failed**  
**    MyPy: Success, no issues found**

##                    (additive-only)

### /metrics
```json
{ "router_p95_ms": <number>, "timeout_rate": <number>, "queue_depth": <integer> }
```

### /debug/{rid} 
```json
{ "rid": "<rid>", "count": <int>, "events": [...], "why_chain": ["..."], "integrity_ok": true, "merkle_root": "<hex>" }
```

### /replay/{rid}
```json
{ "rid":"<rid>", "replayed": <int>, "integrity_ok": true }
```

### Message.idempotent_key
```python
class Message(BaseModel):
    # ... existing fields ...
    idempotent_key: Optional[str] = None  # NEW: TTL-based idempotency
```

##                    VS Code

                                                                                                                                                  :
- `.vscode/settings.json` -                                       Python
-                                                                                    
- `PYTHONPATH`                                            
- `terminal.autoApprove`        .venv             

##             

```
fix(p0): metrics/idempotency TTL/wal integrity + router/cb finalize [FSMP-P0-T02]

- Add /metrics endpoint with router_p95_ms, timeout_rate, queue_depth
- Extend /debug/{rid} with why_chain, integrity_ok, merkle_root  
- Extend /replay/{rid} with integrity_ok, dry-run mode
- Implement idempotent_key + TTL cache (10min default)
- Fix routing.py: remove ..., add why validation, ERR without WAL
- Complete CircuitBreaker.allow() for all states  
- Add WAL verify_chain() and merkle_root calculation
- Test coverage: 89% (29 tests passed)
- MyPy: 0 type errors, VS Code .venv auto-config
```

**             FSMP-P0-T02                                  !     **