# ADR-005: ENV-based Configuration System

**Status:** Accepted  
**Date:** 2025-01-26  
**RID:** FSMP-P1-T04  
**Deciders:** QuantumTraderX Core Team  

---

## Context

QuantumTraderX vFoundation library hardcoded critical operational knobs (RBAC tokens, WAL settings, circuit breaker params, idempotency TTLs) across multiple modules. This created several problems:

1. **Security:** Admin tokens hardcoded as "admin-secret-token" in source
2. **Testability:** No way to override settings for tests without modifying source
3. **Deployment:** Different environments (dev/staging/prod) needed different values
4. **Operations:** Tuning timeouts/thresholds required code changes + redeployment

We needed minimal configuration without introducing heavy frameworks (no Pydantic, no YAML, no live-reload complexity).

---

## Decision

Implement **minimal ENV-based config** with these constraints:

### 1. **Single Config Module** (`vfoundation/config.py`)
- Load all ENV vars at import time (singleton pattern)
- No framework dependencies (pure stdlib)
- No YAML/JSON files     ENV vars only
- Validation with bounds checking, no crashes on invalid input

### 2. **Extracted Parameters (9 total)**

**Security:**
- `RBAC_ADMIN_TOKENS`     comma-separated list of admin bearer tokens
- `SIGNING_KEY`     64-char hex Ed25519 private key

**DR/WAL:**
- `WAL_DIR`     write-ahead log directory path
- `WAL_LOCK_TIMEOUT_SEC`     cross-platform file lock timeout

**Circuit Breaker:**
- `CB_THRESHOLD`     failure count before opening circuit
- `CB_COOLDOWN_SEC`     cooldown period after circuit opens

**Idempotency:**
- `IDEM_TTL_MS`     cache entry time-to-live
- `IDEM_MAX_ENTRIES`     max cache size before eviction

**Drift Monitoring:**
- `DRIFT_TIME_WINDOW_SEC`     time window for shadow-mode drift calculation

### 3. **Dev-Obvious Defaults**
All defaults trigger `UserWarning` to ensure visibility:
- `RBAC_ADMIN_TOKENS`: `["dev-admin-token"]` (INSECURE, visible in logs)
- `SIGNING_KEY`: `"0" * 64` (INSECURE, visible in logs)
- Operational knobs: Documented reasonable defaults (5s WAL timeout, 5 failures CB threshold, etc.)

### 4. **Validation Strategy**
- **Min/max bounds:** Invalid values clamped to minimum (e.g., `CB_THRESHOLD < 1`     1)
- **Parse failures:** Fall back to default with warning (e.g., `CB_THRESHOLD="abc"`     5)
- **No crashes:** Always return valid config, never raise exceptions

### 5. **Test Support**
- `reload_config()` function for ENV override testing
- Updates singleton attributes **in-place** (preserves existing references)
- Not thread-safe (test-only usage)

### 6. **Integration Pattern**
Modules use config via:
```python
from vfoundation.config import config

def some_function(param: Optional[int] = None):
    actual_value = param if param is not None else config.some_setting
```

Backward compatible     existing code with hardcoded values works unchanged.

---

## Consequences

###     **Positive**

1. **Security:** Secrets externalized to ENV (KMS/Vault integration point)
2. **Testability:** `reload_config()` enables ENV override tests, 20 new tests, +3% coverage
3. **Deployment:** Environment-specific config without code changes
4. **Operations:** Tuning knobs via ENV without redeployment (with container restart)
5. **Fail-obvious:** Dev defaults visible in logs via warnings
6. **Minimal:** Zero framework dependencies, 80 SLOC total
7. **Backward compatible:** Existing code unmodified, optional params with defaults

###     **Negative / Limitations**

1. **No live-reload:** Changes require process restart (acceptable for stateless services)
2. **No type safety:** ENV vars are strings, validation at load time only
3. **No nested config:** Flat namespace, no hierarchical structure
4. **Test isolation:** `reload_config()` is global, tests must use `monkeypatch.setenv()` + cleanup
5. **Documentation burden:** ENV vars must be documented externally (deployment guides)

###        **Risks**

1. **ENV var typos:** Misspelled vars silently use defaults (mitigated by warnings)
2. **Validation gaps:** Complex validation (e.g., key format) minimal (only length check for signing key)
3. **Test interference:** Parallel tests with `reload_config()` can race (mitigated by pytest-xdist isolation)

---

## Alternatives Considered

### A. **Pydantic Settings**
-     Heavy dependency (200+ modules)
-     Overkill for 9 settings
-     Type safety + validation
- **Decision:** Rejected due to complexity

### B. **YAML Config Files**
-     Requires file distribution (containers, deployment complexity)
-     Secrets in files (not ENV) harder to manage
-     Hierarchical structure
- **Decision:** Rejected     ENV is cloud-native standard

### C. **Hardcoded Constants (Status Quo)**
-     Security risk (secrets in source)
-     No environment flexibility
-     Zero complexity
- **Decision:** Rejected     unacceptable for production

---

## Implementation Notes

### Modified Modules (5)
1. `vfoundation/security/rbac_abac.py`     lazy import for test support
2. `vfoundation/dr/wal.py`     WAL_DIR and lock timeout
3. `vfoundation/core/retry_cb.py`     CB threshold/cooldown defaults
4. `vfoundation/core/idempotency.py`     TTL and max_entries defaults
5. `vfoundation/apps/reference/domains/execution_position/drift_monitor.py`     time_window_sec default

### Test Updates (2)
1. `tests/test_rbac.py`     added `reload_config()` calls
2. `tests/test_security_xai_tighten.py`     added `reload_config()` calls

### New Test Suite
- `tests/test_config_env_overrides.py`     20 tests covering:
  - Defaults (3 tests)
  - ENV overrides (7 tests)
  - Validation bounds (8 tests)
  - Reload behavior (2 tests)

### Coverage Impact
- **Before:** 89% total, config.py N/A (didn't exist)
- **After:** 91% total, config.py = 92%
- **Tests:** 280     300 passed (+20)

---

## Related Documents

- `docs/ROADMAP_DELTA_EMPTY_BRANCH.md`     Task FSMP-P1-T04 specification
- `docs/docs_vfoundation/Security.md`     RBAC token usage
- `docs/docs_vfoundation/Operations.md`     Deployment ENV vars
- `tests/test_config_env_overrides.py`     Config test suite

---

## Changelog

**2025-01-26 (FSMP-P1-T04):**
- Created `vfoundation/vfoundation/config.py` (80 SLOC, 92% coverage)
- Integrated config in 5 modules (rbac_abac, wal, retry_cb, idempotency, drift_monitor)
- Added 20 config tests, 300 total tests passing, 91% coverage
- All tests green, warnings working correctly

---

## Future Work

1. **Schema validation:** JSON Schema for ENV var validation (FSMP-P2)
2. **Secrets manager:** KMS/Vault integration for `SIGNING_KEY` (FSMP-P2-Security)
3. **Config hot-reload:** Optional live-reload for non-critical settings (FSMP-P3)
4. **Audit logging:** Log config changes at startup (FSMP-P2-Observability)
