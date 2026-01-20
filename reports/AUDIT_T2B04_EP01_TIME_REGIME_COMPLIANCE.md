# AUDIT REPORT: Time Sovereignty (T2B-04) & Regime Typing (EP-01)
**Date:** 2026-01-20  
**Auditor:** Senior Code Compliance Auditor (Copilot)  
**Scope:** `apps/reference/domains/*`  
**Status:** ⛔ **CRITICAL VIOLATIONS FOUND**

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Time Violations (T2B-04)** | 🔴 **25+ files** |
| **`time.time()` usages in business logic** | 100+ occurrences |
| **`time.sleep()` usages** | 11 occurrences |
| **`asyncio.sleep()` usages** | 20+ occurrences |
| **`datetime.now()` usages** | 11 occurrences |
| **Regime Typing (EP-01)** | ✅ Mostly compliant |
| **`get_clock()` adoption in domains** | 🔴 **0 files** |

**Verdict:** Система **НЕ ВІДПОВІДАЄ** контракту T2B-04. Абстракція `get_clock()` існує в `apps/reference/core/time`, але **ЖОДЕН домен її не використовує**.

---

## PHASE 1: TIME CONTAMINATION VIOLATIONS (T2B-04)

### 1.1 Critical Violations Table (FSM & Core Trading Logic)

| File | Line(s) | Violation | Severity |
|------|---------|-----------|----------|
| [fsm.py](apps/reference/domains/execution_position/fsm.py#L15) | 15, 515, 780, 871, 1158, 1190, 1391, 1569, 1627, 1655, 1781, 1812, 1825, 1839 | `import time` + `time.time()` x14 | 🔴 **CRITICAL** |
| [fsm_open.py](apps/reference/domains/execution_position/fsm_open.py#L13) | 13, 210, 237, 249, 389, 446 | `import time` + `time.time()` x6 | 🔴 **CRITICAL** |
| [fsm_close.py](apps/reference/domains/execution_position/fsm_close.py#L13) | 13, 61, 103, 148 | `import time` + `time.time()` x4 | 🔴 **CRITICAL** |
| [fsm_manage.py](apps/reference/domains/execution_position/fsm_manage.py#L14) | 14, 405, 408, 506, 530, 1039, 1041, 1075, 1213, 1300, 1310, 1340, 1360 | `import time` + `time.time()` x13 | 🔴 **CRITICAL** |
| [decision_making.py](apps/reference/domains/decision_making/decision_making.py#L15) | 15, 1927, 2021, 2038, 2091, 2314, 2598, 2896, 3438, 3499, 3543, 3592, 3636, 3640, 3650, 3739, 3757, 3801, 3918, 3924, 3985 | `import time` + `time.time()` x21 | 🔴 **CRITICAL** |
| [mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L22) | 22, 419, 465, 498, 818 | `import time` + `time.time()` x5 | 🔴 **CRITICAL** |
| [exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L12) | 12, 193, 264, 454, 550, 718, 840, 866 | `import time` + `time.time()` x8 | 🔴 **CRITICAL** |
| [watchdog.py](apps/reference/domains/execution_position/watchdog.py#L10) | 10, 107, 187, 215, 257, 297 | `import time` + `time.time()` x6 | 🔴 **CRITICAL** |

### 1.2 High Violations (Supporting Execution Logic)

| File | Line(s) | Violation | Severity |
|------|---------|-----------|----------|
| [drift_monitor.py](apps/reference/domains/execution_position/drift_monitor.py#L20) | 20, 151, 158, 211, 231 | `import time` + `time.time()` x5 | 🟠 HIGH |
| [order_index.py](apps/reference/domains/execution_position/order_index.py#L12) | 12, 165, 206, 266 | `from time import time` + `time()` x4 | 🟠 HIGH |
| [order_ledger.py](apps/reference/domains/execution_position/infra/order_ledger.py#L16) | 16, 63, 65, 271, 283, 320 | `import time` + `time.time()` x6 | 🟠 HIGH |
| [metrics_collector.py](apps/reference/domains/execution_position/metrics_collector.py#L9) | 9, 93, 112, 131, 150, 303 | `import time` + `time.time()` x6 | 🟠 HIGH |
| [idempotent_cancel.py](apps/reference/domains/execution_position/idempotent_cancel.py#L8) | 8, 102 | `import time` + `time.time()` x1 | 🟠 HIGH |
| [leverage_service.py](apps/reference/domains/execution_position/leverage_service.py#L8) | 8 | `import time` (unused?) | 🟡 WARN |
| [aurora_log_adapter.py](apps/reference/domains/execution_position/aurora_log_adapter.py#L10) | 10, 88, 149, 194, 243 | `import time` + `time.time()` x4 | 🟠 HIGH |
| [utils.py](apps/reference/domains/execution_position/utils.py) | 177, 334 | `time.time()` x2 | 🟠 HIGH |

### 1.3 Decision Making Domain Violations

| File | Line(s) | Violation | Severity |
|------|---------|-----------|----------|
| [deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py#L10) | 10, 46 | `import time` + `time.time()` | 🔴 **CRITICAL** |
| [trade_intent_reject_wal.py](apps/reference/domains/decision_making/trade_intent_reject_wal.py#L3) | 3, 36 | `import time` + `time.time()` | 🟠 HIGH |
| [aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L19) | 19 | `import time` | 🟡 WARN |
| [mean_reversion_logger.py](apps/reference/domains/decision_making/mean_reversion_logger.py#L5) | 5 | `import time` | 🟡 WARN |

### 1.4 Other Domains Violations

| File | Line(s) | Violation | Severity |
|------|---------|-----------|----------|
| [daily_gate.py](apps/reference/domains/risk_management/daily_gate.py#L12) | 12, 52 | `datetime.now()` | 🟠 HIGH |
| [risk_management.py](apps/reference/domains/risk_management/risk_management.py#L11) | 11 | `from datetime import datetime` | 🟡 WARN |
| [position_tracking.py](apps/reference/domains/position_tracking/position_tracking.py#L11) | 11, 1104 | `import time` + `datetime.now()` | 🟠 HIGH |
| [snapshot_scheduler.py](apps/reference/domains/snapshot_scheduler/snapshot_scheduler.py#L12) | 12, 165, 203 | `datetime.now()` x2 | 🟠 HIGH |
| [bar_aggregator.py](apps/reference/domains/market_data/bar_aggregator.py#L28) | 28, 127 | `import time` + `time.time()` | 🟠 HIGH |
| [worker.py](apps/reference/domains/market_data/worker.py#L25) | 25, 385, 397 | `import time` + `time.time()` x2 | 🟠 HIGH |
| [proxy.py](apps/reference/domains/market_data/proxy.py#L18) | 18, 328 | `import time` + `time.sleep()` | 🟠 HIGH |
| [recorder.py](apps/reference/domains/data_recorder/recorder.py#L12) | 12, 90, 142, 149 | `import time` + `time.sleep()` + `time.time()` | 🟠 HIGH |
| [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L25) | 25 | `import time` | 🟡 WARN |
| [bar_resampler.py](apps/reference/domains/feature_engineering/bar_resampler.py#L24) | 24 | `import time` | 🟡 WARN |
| [mean_reversion_strategy.py](apps/reference/domains/feature_engineering/mean_reversion_strategy.py#L25) | 25 | `import time` | 🟡 WARN |
| [ensemble.py](apps/reference/domains/alpha_search/ensemble.py#L12) | 12, 123, 268, 318 | `datetime.now()` x3 | 🟠 HIGH |
| [alpha_model.py](apps/reference/domains/alpha_search/alpha_model.py#L17) | 17 | `from datetime import datetime` | 🟡 WARN |
| [reconciler.py](apps/reference/domains/inflight_reconcile/reconciler.py#L17) | 17 | `import time` | 🟡 WARN |

### 1.5 `time.sleep()` Violations (Blocking Calls)

| File | Line | Usage | Severity |
|------|------|-------|----------|
| [account_connector.py](apps/reference/domains/account_balance/account_connector.py#L112) | 112 | `time.sleep(self.update_interval)` | 🟠 HIGH |
| [proxy.py](apps/reference/domains/market_data/proxy.py#L328) | 328 | `time.sleep(self._idle_sleep_sec)` | 🟠 HIGH |
| [recorder.py](apps/reference/domains/data_recorder/recorder.py#L142) | 142 | `time.sleep(self._flush_interval)` | 🟠 HIGH |
| [worker.py](apps/reference/domains/neocortex/logic/brain/worker.py#L133) | 133 | `time.sleep(1)` | 🟠 HIGH |
| [bridge.py](apps/reference/domains/neocortex/logic/brain/bridge.py#L126) | 126 | `time.sleep(1)` | 🟠 HIGH |

### 1.6 `asyncio.sleep()` Violations

| File | Lines | Severity |
|------|-------|----------|
| [multi_tailer.py](apps/reference/domains/neocortex/logic/ingest/multi_tailer.py) | 249, 318 | 🟡 WARN (infra) |
| [tailer.py](apps/reference/domains/neocortex/logic/ingest/tailer.py) | 183, 212, 267, 305, 325 | 🟡 WARN (infra) |
| [wal_replayer.py](apps/reference/domains/neocortex/logic/ingest/wal_replayer.py) | 136, 151 | 🟡 WARN (infra) |
| [main.py](apps/reference/domains/neocortex/main.py) | 172 | 🟠 HIGH |

---

## PHASE 2: REGIME TYPE SAFETY (EP-01)

### 2.1 Execution Domain Analysis

| File | Status | Notes |
|------|--------|-------|
| [exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py) | ✅ **COMPLIANT** | Uses `ExecutionRegimeBucket` correctly (L30, L951-957) |
| [fsm.py](apps/reference/domains/execution_position/fsm.py) | ✅ **COMPLIANT** | Imports `ExecutionRegimeBucket` (L55), documents mapping from `RegimeLabel` |

### 2.2 Risk Management Analysis

| File | Status | Notes |
|------|--------|-------|
| [risk_management.py](apps/reference/domains/risk_management/risk_management.py) | ⚠️ **REVIEW NEEDED** | No `ExecutionRegimeBucket` import found |
| [daily_gate.py](apps/reference/domains/risk_management/daily_gate.py) | ⚠️ **REVIEW NEEDED** | No regime-related imports |

### 2.3 String Literal Checks

| Pattern | Matches | Status |
|---------|---------|--------|
| `== "TREND_UP"` / `"TREND_DOWN"` / `"VOLATILE"` | 0 in execution_position | ✅ |
| `== "UNKNOWN"` | 1 (L3559 fsm.py, for `fill_side`) | ✅ (not regime-related) |
| Raw `RegimeLabel` usage in decisions | 0 | ✅ |

**EP-01 Verdict:** ✅ Execution домен коректно використовує `ExecutionRegimeBucket`. Risk Management потребує перевірки на повноту.

---

## PHASE 3: REFACTORING ESTIMATE

### Summary Statistics

| Category | Files Affected | Priority |
|----------|----------------|----------|
| FSM Core (fsm*.py) | 4 | 🔴 P0 |
| Decision Making | 6 | 🔴 P0 |
| Execution Support | 10 | 🟠 P1 |
| Market Data | 4 | 🟠 P1 |
| Other Domains | 8 | 🟡 P2 |
| Infrastructure/Adapters | 6 | 🟢 P3 |
| **TOTAL** | **~38 files** | |

### Required Clock API Adoption

```python
# BEFORE (non-compliant):
import time
now_ms = int(time.time() * 1000)

# AFTER (T2B-04 compliant):
from apps.reference.core.time import get_clock
now_ms = get_clock().now_ms()
```

### Effort Estimate

| Phase | Scope | Effort |
|-------|-------|--------|
| P0: FSM + DecisionMaking | 10 files, ~150 replacements | 4-6 hours |
| P1: Execution Support | 10 files, ~80 replacements | 3-4 hours |
| P2: Other Domains | 8 files, ~30 replacements | 2-3 hours |
| P3: Infra (optional) | 6 files | 1-2 hours |
| **Testing & Validation** | Full regression | 4+ hours |
| **TOTAL** | | **14-19 hours** |

---

## RECOMMENDATIONS

### Immediate Actions (P0)

1. **Create migration script** to auto-replace `time.time()` → `get_clock().now_sec()` and `int(time.time() * 1000)` → `get_clock().now_ms()`
2. **Add linter rule** to CI that fails on `import time` in `apps/reference/domains/` (excluding tests)
3. **Update FSM files first** — це критичний шлях торгівлі

### Architectural Improvements

1. **Inject Clock dependency** in constructors замість global `get_clock()`
2. **Add `@clock_required` decorator** для методів, що потребують час
3. **Document T2B-04 contract** в кожному domain README

### CI Gate (Proposed)

```yaml
# .github/workflows/time-audit.yml
- name: Check time contamination
  run: |
    grep -rn "import time\|from time import\|datetime.now\|asyncio.sleep" \
      apps/reference/domains/ \
      --include="*.py" \
      --exclude-dir=tests \
      --exclude="*adapter*" \
      --exclude="*connector*" \
    && exit 1 || exit 0
```

---

## APPENDIX: Files by Domain

### execution_position/ (15 violations)
- `fsm.py`, `fsm_open.py`, `fsm_close.py`, `fsm_manage.py`
- `exposure_guard.py`, `watchdog.py`, `drift_monitor.py`
- `order_index.py`, `order_ledger.py`, `metrics_collector.py`
- `idempotent_cancel.py`, `leverage_service.py`, `aurora_log_adapter.py`, `utils.py`

### decision_making/ (6 violations)
- `decision_making.py`, `mean_reversion_handler.py`
- `deferred_scheduler.py`, `trade_intent_reject_wal.py`
- `aurora_handler.py`, `mean_reversion_logger.py`

### market_data/ (4 violations)
- `bar_aggregator.py`, `worker.py`, `proxy.py`, `market_data_connector.py`

### feature_engineering/ (3 violations)
- `feature_engineering.py`, `bar_resampler.py`, `mean_reversion_strategy.py`

### neocortex/ (8 violations)
- `transport/adapter.py`, `logic/dreamer.py`, `logic/telemetry.py`
- `logic/brain/worker.py`, `logic/brain/bridge.py`
- `logic/ingest/multi_tailer.py`, `logic/ingest/tailer.py`, `main.py`

### Other domains (5 violations)
- `risk_management/daily_gate.py`, `risk_management/risk_management.py`
- `position_tracking/position_tracking.py`
- `snapshot_scheduler/snapshot_scheduler.py`
- `alpha_search/ensemble.py`, `alpha_search/alpha_model.py`
- `data_recorder/recorder.py`, `inflight_reconcile/reconciler.py`
- `account_balance/account_connector.py`

---

**Report Generated:** 2026-01-20T12:00:00Z  
**Next Review:** After P0 remediation complete
