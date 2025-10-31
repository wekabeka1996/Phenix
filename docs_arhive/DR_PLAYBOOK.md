# PATH: docs/DR_PLAYBOOK.md
# Disaster Recovery (DR) Playbook

**Version:** 1.0  
**Based on:** PLAN_AURORA_TO_VFOUNDATION.md (Phase L4)  
**Created:** 2025-10-18  
**RTO Target:** ‚â§ 5 minutes  
**RPO Target:** ‚â§ 1 minute

## 1. Mechanism Overview

The system uses a combination of periodic state snapshots and a continuous Write-Ahead Log (WAL) to ensure data durability and rapid recovery.

### 1.1 State Snapshots

- **Frequency:** Every 5 minutes
- **Target Domain:** `position_tracking` FSM (critical for financial state)
- **Format:** Versioned JSON with SHA-256 state hash
- **Storage:** Secure, write-once storage (e.g., S3 bucket with versioning)
- **Retention:** Last 24 hours (288 snapshots), then daily archives for 30 days

### 1.2 Write-Ahead Log (WAL)

- **Scope:** All incoming messages to `position_tracking` domain
- **Critical Events:** `EVT:TRADE_EXECUTED`, `EVT:POSITION_ADJUSTED`, `DEC:CLOSE`
- **Format:** JSONL (JSON Lines) - one message per line
- **Rotation:** Daily at 00:00 UTC
- **Naming:** `wal_<YYYY-MM-DD>.jsonl` (e.g., `wal_2025-10-18.jsonl`)
- **Storage:** Local disk + async replication to remote storage

## 2. Recovery Process (RTO ‚â§ 5 min)

### 2.1 Automated Recovery Steps

1. **Detect Failure State**
   - Service startup detects missing or corrupted local state file
   - Health check detects state inconsistency
   - Manual DR trigger via admin endpoint

2. **Fetch Latest Snapshot** (‚è±Ô∏è ~30 seconds)
   - Connect to remote storage (S3/Azure Blob/GCS)
   - Download most recent successful snapshot for `position_tracking`
   - Verify snapshot integrity via state_hash
   - Fallback to previous snapshot if corrupted

3. **Load Base State** (‚è±Ô∏è ~10 seconds)
   - Initialize `position_tracking` FSM with snapshot state
   - Validate loaded state (schema compliance, balance checks)
   - Log snapshot metadata (timestamp, hash, positions count)

4. **Fetch WAL Segments** (‚è±Ô∏è ~60 seconds)
   - Calculate time gap: `snapshot_timestamp` ‚Üí `current_time`
   - Download all WAL files covering the gap
   - Verify WAL integrity (checksums, sequence continuity)

5. **Replay Events** (‚è±Ô∏è ~120 seconds for 1000 events)
   - Parse WAL entries (JSONL format)
   - Filter critical events: `EVT:TRADE_EXECUTED`, `EVT:POSITION_ADJUSTED`
   - Replay events in chronological order into FSM
   - Skip duplicate events (idempotency check via RID)
   - Log replay progress every 100 events

6. **Resume Normal Operations** (‚è±Ô∏è ~30 seconds)
   - Run post-recovery validation:
     * Portfolio balance check
     * Position consistency with exchange
     * Risk limits recalculation
   - Emit `EVT:DR_RECOVERY_COMPLETED` event
   - Resume message processing

### 2.2 Recovery Time Breakdown

| Phase | Target Time | Actions |
|-------|-------------|---------|
| Detection | 0-10s | Startup checks, health monitoring |
| Snapshot Download | 30s | Network transfer (assuming <10MB snapshot) |
| State Load | 10s | JSON parsing, FSM initialization |
| WAL Download | 60s | Network transfer (assuming <100MB WAL) |
| Event Replay | 120s | Processing ~1000 events at 8 events/sec |
| Validation | 30s | Balance checks, exchange reconciliation |
| **Total RTO** | **‚â§ 5 min** | **End-to-end recovery time** |

### 2.3 Manual Recovery Procedures

**Scenario A: Snapshot Corruption**
```bash
# Fallback to previous snapshot
python -m vfoundation.dr.recovery --domain position_tracking --snapshot-offset 1

# Or specific snapshot by timestamp
python -m vfoundation.dr.recovery --domain position_tracking --snapshot-ts "2025-10-18T12:00:00Z"
```

**Scenario B: WAL Gap (missing segments)**
```bash
# Force reconciliation with exchange API
python -m vfoundation.dr.reconcile --domain position_tracking --source binance --force
```

**Scenario C: State Inconsistency After Recovery**
```bash
# Run state validation and auto-fix
python -m vfoundation.dr.validate --domain position_tracking --fix --audit-log
```

## 3. Contracts

### 3.1 Snapshot Schema (`snapshot_v1.schema.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.scalp/dr/snapshot_v1.schema.json",
  "title": "DR Snapshot Schema v1",
  "description": "State snapshot for disaster recovery (position_tracking domain)",
  "type": "object",
  "required": ["domain", "version", "timestamp_utc", "state_hash", "state", "metadata"],
  "properties": {
    "domain": {
      "type": "string",
      "const": "position_tracking",
      "description": "Target FSM domain identifier"
    },
    "version": {
      "type": "string",
      "const": "1.0.0",
      "description": "Snapshot schema version"
    },
    "timestamp_utc": {
      "type": "string",
      "format": "date-time",
      "description": "Snapshot creation timestamp (ISO 8601)"
    },
    "state_hash": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$",
      "description": "SHA-256 hash of serialized state for integrity verification"
    },
    "state": {
      "type": "object",
      "required": ["positions", "portfolio"],
      "properties": {
        "positions": {
          "type": "object",
          "description": "Active positions by symbol",
          "patternProperties": {
            "^[A-Z]+$": {
              "type": "object",
              "required": ["qty", "avg_price", "side"],
              "properties": {
                "qty": {
                  "type": "string",
                  "description": "Position quantity (Decimal as string)"
                },
                "avg_price": {
                  "type": "string",
                  "description": "Average entry price (Decimal as string)"
                },
                "side": {
                  "type": "string",
                  "enum": ["long", "short"]
                },
                "unrealized_pnl": {
                  "type": "string",
                  "description": "Current unrealized P&L (optional)"
                }
              }
            }
          }
        },
        "portfolio": {
          "type": "object",
          "required": ["equity", "balance"],
          "properties": {
            "equity": {
              "type": "string",
              "description": "Total portfolio equity (Decimal as string)"
            },
            "balance": {
              "type": "string",
              "description": "Available balance (Decimal as string)"
            },
            "margin_used": {
              "type": "string",
              "description": "Used margin (optional)"
            }
          }
        }
      }
    },
    "metadata": {
      "type": "object",
      "description": "Snapshot metadata for auditing",
      "properties": {
        "worker_id": {
          "type": "string",
          "description": "Worker instance that created snapshot"
        },
        "positions_count": {
          "type": "integer",
          "description": "Number of active positions"
        },
        "sequence_number": {
          "type": "integer",
          "description": "Monotonic snapshot sequence number"
        }
      }
    }
  }
}
```

### 3.2 WAL Entry Schema (`wal_entry_v1.schema.json`)

WAL entries use the standard **vFoundation Message protocol**:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.scalp/dr/wal_entry_v1.schema.json",
  "title": "WAL Entry Schema v1",
  "description": "Write-Ahead Log entry (vFoundation Message wrapper)",
  "type": "object",
  "required": ["op", "name", "ts", "rid", "pld"],
  "properties": {
    "op": {
      "type": "string",
      "enum": ["EVT", "DEC", "CMD"],
      "description": "Message operation type"
    },
    "name": {
      "type": "string",
      "description": "Event/Decision/Command name (e.g., TRADE_EXECUTED)"
    },
    "ts": {
      "type": "number",
      "description": "Unix timestamp (milliseconds)"
    },
    "rid": {
      "type": "string",
      "description": "Request ID for idempotency and tracing"
    },
    "src": {
      "type": "string",
      "description": "Source domain (optional)"
    },
    "dst": {
      "type": "string",
      "description": "Destination domain (optional)"
    },
    "pld": {
      "type": "object",
      "description": "Event-specific payload (schema varies by event type)"
    },
    "why": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Chain of reasoning (WHY-chain)"
    }
  }
}
```

### 3.3 Critical Events for WAL Replay

| Event Name | Priority | Description |
|------------|----------|-------------|
| `EVT:TRADE_EXECUTED` | **P0** | Trade filled on exchange - updates position |
| `EVT:POSITION_ADJUSTED` | **P0** | Manual position adjustment (liquidation, transfer) |
| `DEC:CLOSE` | **P1** | Close position decision |
| `EVT:ACCOUNT_UPDATE_RECEIVED` | **P1** | Exchange account snapshot |
| `EVT:BALANCE_UPDATE_RECEIVED` | **P2** | Balance change notification |

## 4. Storage Configuration

### 4.1 Snapshot Storage

**Local Cache:**
```
logs/dr/snapshots/
  ‚îú‚î ‚î  position_tracking_20251018_120000_seq_001.json
  ‚îú‚î ‚î  position_tracking_20251018_120500_seq_002.json
  ‚îî‚î ‚î  ...
```

**Remote Storage (S3 example):**
```
s3://aurora-dr-prod/snapshots/position_tracking/
  ‚îú‚î ‚î  2025/10/18/120000_seq_001.json
  ‚îú‚î ‚î  2025/10/18/120500_seq_002.json
  ‚îî‚î ‚î  ...
```

### 4.2 WAL Storage

**Local:**
```
logs/dr/wal/
  ‚îú‚î ‚î  wal_2025-10-18.jsonl      (current day, append-only)
  ‚îú‚î ‚î  wal_2025-10-17.jsonl.gz   (rotated, compressed)
  ‚îî‚î ‚î  ...
```

**Remote Storage:**
```
s3://aurora-dr-prod/wal/
  ‚îú‚î ‚î  2025/10/18/wal_2025-10-18.jsonl
  ‚îú‚î ‚î  2025/10/17/wal_2025-10-17.jsonl.gz
  ‚îî‚î ‚î  ...
```

## 5. Monitoring & Alerts

### 5.1 DR Health Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| `dr.snapshot.success_rate` | 100% | <95% over 1 hour |
| `dr.snapshot.duration_ms` | <5000 | >10000 |
| `dr.wal.write_latency_ms` | <10 | >50 (p99) |
| `dr.replay.event_rate` | >5/sec | <1/sec during replay |
| `dr.state_hash.mismatch_count` | 0 | >0 in 24 hours |

### 5.2 Alert Scenarios

**Critical (P0):**
- Snapshot upload failure (3 consecutive attempts)
- WAL write failure (disk full, permissions)
- State hash mismatch after recovery

**Warning (P1):**
- Snapshot duration exceeds 10 seconds
- WAL segment missing during recovery
- Recovery RTO exceeds 5 minutes

## 6. Testing & Validation

### 6.1 DR Drill Schedule

- **Weekly:** Automated snapshot restore test (non-production)
- **Monthly:** Full DR simulation (snapshot + WAL replay)
- **Quarterly:** Chaos engineering (random component failure during trading)

### 6.2 Test Scenarios

1. **Cold Start Recovery:** Restore from 24-hour-old snapshot
2. **Partial WAL Loss:** Simulate missing WAL segment (force reconciliation)
3. **Corrupted Snapshot:** Automatic fallback to previous snapshot
4. **High-Frequency Replay:** Replay 10,000 events in <5 minutes

## 7. Future Enhancements (Phase L5+)

- [ ] Multi-domain snapshots (risk_management, decision_making)
- [ ] Incremental snapshots (delta compression)
- [ ] Real-time replication (active-passive cluster)
- [ ] Cross-region disaster recovery
- [ ] Automated DR testing via CI/CD

---

**Document Ownership:** vFoundation Architecture Team  
**Last Review:** 2025-10-18  
**Next Review:** 2025-11-18
