# PLAN: Telemetry, Monitoring & Orchestrator Remediation

**Date:** 2026-02-24
**Author:** SRE / vFoundation Architect
**Ref:** `docs/architectural_audits/AUDIT_APPS_TELEMETRY_ORCH.md`

---

## Executive Summary

Five confirmed defects across three subsystems. All are actionable and testable in isolation.
No architectural grand-rewrites required — each fix is surgical.

---

## STEP 1: RCA (Root Cause Analysis) — confirmed findings

### Finding 1 — Non-Deterministic Ed25519 Signing (`orchestrator_fsm.py:357`)

```python
# BROKEN: str() of a dict is implementation-defined
sign_data = str(cmd_payload)          # line 357
signature = signing_ed25519.sign(sign_data.encode())
```

**Why it is broken:** `cmd_payload` contains `"why_chain"` (a list) and `"data_ref"` (a list).
`str(dict)` in Python 3.11+ is formally insertion-ordered but the string representation
includes spaces after commas and colons, and `Decimal`/`None` formatting can vary across
Python versions. More critically: if `why_chain` is populated in different orders by
concurrent callers (race), the signature differs for identical semantic payloads.
The receiver cannot verify the signature.

**Fix:** Canonical JSON serialization.

```python
import json
sign_data = json.dumps(cmd_payload, sort_keys=True, separators=(',', ':'), default=str)
signature = signing_ed25519.sign(sign_data.encode())
```

---

### Finding 2 — Memory Leak: Orphaned RIDs in `trade_lifecycle_logger.py:108`

```python
self._trades: Dict[str, TradeRecord] = {}   # line 108 — UNBOUNDED
```

**Leak path:**
1. `on_intent(rid=X)` is called → `TradeRecord` inserted into `self._trades`.
2. Exchange rejects the order, FSM emits `EVT:ORDER_REJECTED`.
3. `OrchestratorFSM._on_error` increments `state.error_count` but does **not** call
   `trade_lifecycle.on_cancel(rid=X)`.
4. The `TradeRecord` for `X` stays in `self._trades` indefinitely.

In a live system with hundreds of ticks/day, orphaned records accumulate until OOM.
`flush_all()` exists but is only called at graceful shutdown — not during normal operation.

**Proof:** `open_trades` property (line 244) grows monotonically if no `on_close/on_cancel`
is called for a RID. There is no periodic timer or size cap on `self._trades`.

**Fix:** TTL sweeper + max-size guard using `cachetools.LRUCache`.

---

### Finding 3 — Memory Leak: Unbounded `recent_alerts` in `alerts.py:87`

```python
self.recent_alerts: Dict[str, float] = {}   # line 87 — UNBOUNDED
```

**Leak path:**
1. Every time `raise_alert()` is called and passes deduplication, a new key is inserted:
   `self.recent_alerts[alert_key] = alert.timestamp` (line 242).
2. Old keys are **never removed**. `_should_deduplicate` only reads, never prunes.
3. In a long-lived system with varying alert titles (e.g., different symbols), the
   `recent_alerts` dict grows without bound.

`active_alerts` is correctly cleaned on `resolve_alert()` (line 271), but `recent_alerts`
is never pruned.

---

### Finding 4 — SSOT Violation: `os.environ` in `alerts.py:80-94`

```python
self.slack_webhook_url   = os.environ.get("AURORA_ALERTS_SLACK_WEBHOOK_URL")      # line 80
self.deduplication_window_sec = int(os.environ.get("AURORA_ALERTS_DEDUP_WINDOW_SEC","300"))  # line 81
self.max_alerts_per_hour = int(os.environ.get("AURORA_ALERTS_MAX_PER_HOUR", "10")) # line 82
self.risk_gate_threshold = int(os.environ.get("AURORA_ALERTS_RISK_GATE_PCT", "80"))# line 92
self.wal_size_threshold_mb = int(os.environ.get("AURORA_ALERTS_WAL_SIZE_MB","500"))# line 93
self.cb_active_threshold_sec = int(os.environ.get("AURORA_ALERTS_CB_ACTIVE_SEC","60")) # line 94
```

**Why this is wrong:**
- `AlertManager.__init__` validates that `config` is `AuroraConfig` (line 72-75),
  then **ignores** config entirely and reads env vars.
- An invalid env var (e.g. `AURORA_ALERTS_RISK_GATE_PCT=INVALID`) does not fail at startup
  (Pydantic would catch it), but raises `ValueError: invalid literal for int()` at the
  moment of the first alert — potentially silencing a real critical event in production.
- All SSOT validation (type, range, defaults) lives in Pydantic models, not shell env.

---

### Finding 5 — Thread-Blocking Hot Path: `performance_monitor.py:82,107,132,167`

```python
self._lock = threading.RLock()            # line 82

def start_decision(self, rid):            # called EVERY tick
    with self._lock:                      # LINE 107 — RLock per tick
        self._timings.append(timing)

def end_decision(self, timing_id, ...):   # called EVERY tick
    with self._lock:                      # LINE 132
        for timing in reversed(self._timings): ...   # O(N) scan under lock

def get_current_metrics(self):            # called every 60s by background loop
    with self._lock:                      # LINE 167
        completed = [t for t in self._timings ...]   # FULL deque scan up to 10k elements
        durations = [t.duration_ms ...]
        percentiles = quantiles(durations, n=100)    # O(N log N) under lock
```

**Impact:** In the asyncio event loop, any call to `start_decision` or `end_decision`
blocks the event loop for the duration of the lock acquisition. When `_background_monitoring`
calls `check_slo_compliance()` → `get_current_metrics()` every 60 seconds, it holds
`threading.RLock` for O(N log N) time across 10k items = measurable stall.

Prometheus `Histogram.observe()` is lock-free and thread-safe by design. This NIH
implementation duplicates functionality that already exists in `metrics.py`.

---

## STEP 2: Strategic Remediation Plan

### Task A — Fix Ed25519 Signing Determinism (Risk: LOW, Impact: HIGH)

**File:** `apps/reference/orchestrator/orchestrator_fsm.py:337-368`

**Change:** Replace `str(cmd_payload)` with `json.dumps(..., sort_keys=True, separators=(',',':'), default=str)`.

**Why `default=str`:** `why_chain` may contain objects; `str()` fallback makes serialization
safe without losing the payload content. This is the canonical approach for audit-trail signing.

**No other code changes required.** The signature is consumed by the receiver; any receiver
already using `nacl.signing.VerifyKey.verify()` on the raw bytes will verify correctly once
both sides use the same canonical representation.

---

### Task B — Fix Memory Leak in `trade_lifecycle_logger.py`

**Approach:** Protect `self._trades` with a TTL-based size cap.

Two options:

**Option B1 (Preferred — zero deps):** Add a background `asyncio`-compatible TTL sweeper.
Set a `_max_orphan_age_sec` (e.g., 3600s = 1 hour). A `_periodic_sweep()` method iterates
`list(self._trades.items())` (safe copy) and flushes any record older than TTL with
`status=TTL_EXPIRED`.

```python
def sweep_orphans(self, max_age_sec: int = 3600) -> int:
    """Flush records not closed/cancelled within max_age_sec. Returns count flushed."""
    cutoff_ms = int(time.time() * 1000) - (max_age_sec * 1000)
    to_flush = [
        rid for rid, rec in list(self._trades.items())
        if rec.intent_ts_ms > 0 and rec.intent_ts_ms < cutoff_ms
        and rec.status not in ("CLOSED", "CANCELLED")
    ]
    for rid in to_flush:
        rec = self._trades.get(rid)
        if rec:
            rec.status = "TTL_EXPIRED"
            rec.close_reason = f"TTL_EXPIRED after {max_age_sec}s"
        self._flush(rid)
    return len(to_flush)
```

**Option B2 (cachetools LRU):** Replace `self._trades` with `cachetools.LRUCache(maxsize=1000)`.
On eviction, a callback flushes the record. This is simpler but requires the `cachetools` dep.

**Recommendation: Option B1** (no new dependency, deterministic behavior, testable).

**Test:** Create 5 RIDs with `on_intent()`, never call `on_close/on_cancel`, call
`sweep_orphans(max_age_sec=0)` (cutoff = now), assert `open_trades == 0`.

---

### Task C — Fix Memory Leak + SSOT in `alerts.py`

**C1 — recent_alerts TTL prune:**
Replace `recent_alerts: Dict[str, float]` with a prune-on-access pattern:

```python
def _prune_recent_alerts(self) -> None:
    """Remove dedup entries older than 2x window (they can never fire again)."""
    cutoff = time.time() - (self.deduplication_window_sec * 2)
    stale = [k for k, ts in self.recent_alerts.items() if ts < cutoff]
    for k in stale:
        del self.recent_alerts[k]
```

Call `_prune_recent_alerts()` at the start of `raise_alert()`.

This is O(N) but only runs on alert creation (rare event, not hot path).

**C2 — SSOT Fix (os.environ elimination):**

Add `AlertsConfig` to `config_models.py`:

```python
class AlertsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    slack_webhook_url: Optional[str] = Field(default=None)
    deduplication_window_sec: int = Field(default=300, ge=0)
    max_alerts_per_hour: int = Field(default=10, ge=1)
    risk_gate_threshold_pct: int = Field(default=80, ge=0, le=100)
    wal_size_threshold_mb: int = Field(default=500, ge=1)
    cb_active_threshold_sec: int = Field(default=60, ge=0)
```

Add `alerts: Optional[AlertsConfig]` to `ObservabilityConfig`.

Update `AlertManager.__init__` to read from `config.observability.alerts` if set,
falling back to the current defaults (backward compatible).

**Why not break the env vars immediately:** The env vars currently serve as the only
configuration path. We add the Pydantic path and emit a `DeprecationWarning` if
env vars are detected, giving operators time to migrate. A follow-on PR removes
the `os.environ` fallback path entirely.

---

### Task D — Deprecate `performance_monitor.py`, Add Prometheus Histogram

**D1 — Add decision latency Histogram to `metrics.py`:**

```python
h_decision_latency_ms = Histogram(
    "decision_latency_ms",
    "Decision path latency (intent to command emission) in milliseconds",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
)

c_decision_why_coverage_total = Counter(
    "decision_why_coverage_total",
    "Decisions with non-empty WHY chain",
)

def observe_decision_latency(latency_ms: float) -> None:
    h_decision_latency_ms.observe(latency_ms)

def inc_decision_why_covered() -> None:
    c_decision_why_coverage_total.inc()
```

**D2 — Update callers in `orchestrator_fsm.py`:**

Replace `self.performance_monitor.start_decision(rid)` / `end_decision(...)` with:

```python
_start_ts = time.time()
# ... processing ...
latency_ms = (time.time() - _start_ts) * 1000
metrics.observe_decision_latency(latency_ms)
if len(state.why_chain) > 0:
    metrics.inc_decision_why_covered()
```

**D3 — Mark `performance_monitor.py` as deprecated:**
Add `# DEPRECATED: Use telemetry/metrics.py Prometheus Histograms instead.` header.
Do NOT delete yet — integration tests may import it. Deletion in subsequent PR.

**SLO Compliance:** p95 is now computed at query time by Prometheus/Grafana using
`histogram_quantile(0.95, rate(decision_latency_ms_bucket[5m]))`.
This is zero-overhead at runtime.

---

### Task E — Decommission OrchestratorFSM (Strategic)

The `OrchestratorFSM` is a God Object that violates the choreography principle.
Its three responsibilities should be distributed:

| Responsibility | New Owner |
|---|---|
| WHY chain aggregation | `xai_store.py` (Phase 11 pattern, already exists in `vfoundation/obs/xai_store.py`) |
| Trade lifecycle tracking | `trade_lifecycle_logger.py` (passive observer, already correct) |
| Circuit breaker | Inline in each Domain FSM (already partially implemented) |
| Idempotency check | `vfoundation/core/idempotency/` (already exists) |
| Ed25519 signing | Keep in place; use canonical JSON |

**Migration strategy:**
1. Verify `XAIStore` accepts WHY chain append calls (Phase 11 contract).
2. Wire `WHY chain` events from `DecisionMaking` domain to `XAIStore.append_why(rid, reason)`.
3. Remove `OrchestratorFSM` listeners from the bus.
4. Delete `apps/reference/orchestrator/` directory.

**This task is separate from Tasks A-D and has no blocking dependency on them.**
Tasks A-D fix acute defects; Task E is the strategic architecture cleanup.

---

## STEP 3: Implementation Order

```
Task A (Ed25519 fix)       ← 15min, zero risk
Task D (Prometheus Histogram) ← 30min, additive only
Task C (alerts.py fixes)   ← 60min, SSOT + memory leak
Task B (lifecycle logger)  ← 45min, memory leak + tests
Task E (Orchestrator decomm) ← Separate sprint, requires E2E testing
```

---

## Definition of Done

- [ ] `orchestrator_fsm.py` uses canonical JSON for Ed25519 signing
- [ ] `trade_lifecycle_logger.py` has `sweep_orphans()` method with test proving eviction
- [ ] `alerts.py` prunes `recent_alerts` on each `raise_alert()` call
- [ ] `alerts.py` reads from `config.observability.alerts` if available (SSOT path)
- [ ] `AlertsConfig` exists in `config_models.py` under `ObservabilityConfig`
- [ ] `metrics.py` exposes `h_decision_latency_ms` Histogram + helper functions
- [ ] `performance_monitor.py` carries DEPRECATED header
- [ ] All new code covered by pytest (memory leak eviction tests, canonical JSON signing tests)
- [ ] No new `os.environ` calls in telemetry subsystem
- [ ] `pytest` suite is green

---

## Files To Modify

| File | Change |
|---|---|
| `apps/reference/orchestrator/orchestrator_fsm.py` | Canonical JSON signing (Task A) + Prometheus metrics (Task D) |
| `apps/reference/telemetry/trade_lifecycle_logger.py` | `sweep_orphans()` TTL method (Task B) |
| `apps/reference/telemetry/alerts.py` | `_prune_recent_alerts()` + SSOT config path (Task C) |
| `apps/reference/telemetry/metrics.py` | Add `h_decision_latency_ms` Histogram (Task D) |
| `apps/reference/config_models.py` | Add `AlertsConfig` + wire to `ObservabilityConfig` (Task C) |
| `apps/reference/monitoring/performance_monitor.py` | Add DEPRECATED header (Task D) |

## Files To Create

| File | Purpose |
|---|---|
| `tests/units/test_telemetry_memory_leaks.py` | Memory leak tests (Task B + C) |
| `tests/units/test_orchestrator_signing.py` | Canonical JSON signing determinism (Task A) |
