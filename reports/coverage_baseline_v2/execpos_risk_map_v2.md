# ExecPos Coverage Risk Map V2 (Quantitative)

Generated on: 2025-12-20
Tools: `pytest-cov`, `pytest 9.0.1`
Baseline: **51% Repository Total**

## Domain: execution_position (apps/reference/domains/execution_position)

| Component | Lines | Miss | Branch | BrMiss | Coverage | Risk Level |
|-----------|-------|------|--------|--------|----------|------------|
| `fsm_manage.py` | 664 | 610 | 260 | 0 | **6%** | 🔥 CRITICAL |
| `exposure_guard.py` | 519 | 415 | 146 | 4 | **17%** | 🔥 CRITICAL |
| `fsm.py` | 1270 | 950 | 444 | 42 | **23%** | 🔴 HIGH |
| `aurora_log_adapter.py`| 77 | 34 | 40 | 12 | **47%** | 🟡 MEDIUM |
| `watchdog.py` | 216 | 83 | 58 | 16 | **57%** | 🟡 MEDIUM |
| `order_guardian.py` | 58 | 22 | 8 | 4 | **61%** | 🟡 MEDIUM |
| `fsm_open.py` | 161 | 47 | 64 | 23 | **64%** | 🟢 LOW |
| `contracts.py` | 172 | 36 | 46 | 2 | **74%** | 🟢 LOW |
| `fsm_close.py` | 66 | 13 | 12 | 4 | **76%** | 🟢 LOW |
| `utils.py` | 136 | 27 | 76 | 13 | **76%** | 🟢 LOW |
| `idempotent_cancel.py` | 92 | 14 | 20 | 6 | **80%** | 🟢 LOW |
| `soft_clip.py` | 70 | 6 | 12 | 2 | **88%** | 🟢 LOW |
| `order_index.py` | 67 | 2 | 18 | 3 | **94%** | 🟢 LOW |

## Top 3 Danger Zones

1.  **fsm_manage.py (6%)**: Complete lack of coverage for bracket placement logic, trailing stops, and take-profit rules. Logic is highly complex (1443 lines) but untested in live-like scenarios.
2.  **exposure_guard.py (17%)**: Core safety mechanism for portfolio limits and directional ratio. Most logic for limit checks is currently bypassed or untested.
3.  **fsm.py (23%)**: Orchestration logic. While simple routing works, error recovery and interleaving (race conditions) are mostly uncovered.

## Strategic Recommendations

- **Immediate**: The 6% coverage in `fsm_manage.py` is unacceptable for a production-live system. Focus Step 4 tests on this file.
- **Medium**: Refactor `exposure_guard.py` for testability (Dependency Injection) to increase its coverage from 17% to >70%.
- **Observation**: `fsm_open.py` and `fsm_close.py` have decent coverage (64%+), likely from previous integration tests.
