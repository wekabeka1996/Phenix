## 2025-11-24: RID: EXEC-R2-LOGS-L1-ERROR-WARNING-AUDIT

### Summary

Completed comprehensive audit of runtime logs to identify and analyze ERROR and WARNING signatures. Created automated log parsing utility and detailed audit report with root cause analysis.

### Tasks Completed

#### ✅ Log Parser Utility
  - Parses both `.log` and `.jsonl` formats
  - Extracts ERROR and WARNING messages
  - Normalizes signatures (removes variable parts like IDs, symbols, prices)
  - Aggregates by unique signature with occurrence count
  - Outputs to JSON for analysis

#### ✅ Automated Report Generator
  - Reads aggregated JSON data
  - Categorizes errors by risk level
  - Generates markdown audit report
  - Provides actionable recommendations

#### ✅ Comprehensive Audit Report
  - Analysis of 10 log files (~13 MB total)
  - 18 unique ERROR signatures (189 occurrences)
  - 589 unique WARNING signatures (18,855 occurrences)
  - Root cause analysis for critical incidents
  - Code location mapping
  - Risk assessment and recommendations

### Key Findings

#### 🔴 Critical Issues Identified

1. **Race Condition in Bracket Creation**
   - **Location:** `apps/reference/domains/execution_position/shadow_execpos/runtime.py:1329`
   - **Method:** `_apply_bracket_plan()`
   - **Problem:** No async lock protection when multiple flows (watchdog healing, position updates, reconciliation) simultaneously create TP/SL orders
   - **Impact:** Duplicate TP orders (confirmed: 2 TP on BTC instead of 1)
   - **Severity:** HIGH

2. **State Divergence: Local Mirror vs Exchange**
   - **Location:** `shadow_execpos/runtime.py:981` (`_has_equivalent_bracket()`)
   - **Problem:** Duplicate check uses stale local mirror `_open_orders_by_symbol` instead of querying exchange
   - **Impact:** System creates duplicate orders when local state out of sync
   - **Scenarios:** Timeouts, missed WebSocket events, race conditions
   - **Severity:** HIGH

3. **SOL Position Without TP/SL**
   - **Problem:** Bracket creation fails silently without proper error handling
   - **Possible causes:**
     - Timeout from exchange during PLACE operation
     - Validation error (price/notional constraints)
     - Exception not logged/handled
   - **Impact:** Unprotected position (no stop loss)
   - **Severity:** HIGH

4. **-4116 DUPLICATE_CLIENT_ORDER_ID Errors**
   - **Location:** `adapters/binance_adapter.py` (error handling in place_* methods)
   - **Problem:** Client order ID collision when rapid retries occur
   - **Current mitigation:** Fallback to ledger lookup + re-fetch
   - **Risk:** Fallback fails if ledger doesn't have entry (race/missed event)
   - **Severity:** MEDIUM

### Code Locations Mapped

| Component | File | Method | Issue |
|-----------|------|--------|-------|
| Bracket creation | `shadow_execpos/runtime.py:1329` | `_apply_bracket_plan()` | ❌ No async lock |
| Duplicate check | `shadow_execpos/runtime.py:981` | `_has_equivalent_bracket()` | ⚠️ Uses stale local mirror |
| Client ID generation | `shadow_execpos/runtime.py:945` | `_make_bracket_client_order_id()` | ⚠️ Collision possible |
| Watchdog healing | `shadow_execpos/runtime.py` | `_periodic_watchdog_check()` | ⚠️ Concurrent with other flows |
| Exchange adapter | `adapters/binance_adapter.py` | `place_stop_market_close_position()` | ✅ Has -4116 handling |

### Statistics

```
📊 Analyzed Logs:
   - Files: 10 (aurora_core.log, execpos_v2_runtime.jsonl, domain_*.log, etc.)
   - Total size: ~13 MB
   - Time range: Recent runtime sessions

📈 Error Statistics:
   - Total ERROR occurrences: 189
   - Unique ERROR signatures: 18
   - Total WARNING occurrences: 18,855
   - Unique WARNING signatures: 589

🎯 Categorization:
   - Duplicate/Idempotency errors: [mapped in report]
   - Bracket/TP/SL errors: [mapped in report]
   - Timeout/Adapter errors: [mapped in report]
   - State/Divergence errors: [mapped in report]
```

### Artifacts Created

```
tools/
├── logs_errors_summary.py          (Log parser)
└── generate_log_audit_report.py    (Report generator)

docs/
├── EXEC_R2_LOG_ERRORS_RAW.json     (Aggregated signatures)
└── EXEC_R2_LOG_ERRORS_AUDIT.md     (Full audit report)
```

### Recommendations

#### Priority 1: Immediate Hotfixes (CRITICAL)

1. **Add async lock to bracket creation**
   ```python
   # In ExecPosRuntimeV2.__init__:
   self._bracket_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

   # In _apply_bracket_plan:
   async with self._bracket_locks[symbol]:
       # ... existing bracket creation logic
   ```

2. **Force orders snapshot after bracket operations**
   ```python
   # After successful bracket PLACE:
   await self._request_orders_snapshot(symbol, force=True)
   ```

3. **Add explicit error logging for bracket failures**
   - Log to dedicated ERROR channel
   - Include symbol, action type, failure reason
   - Trigger alert for unprotected positions

#### Priority 2: Short-term Improvements

4. Implement retry logic for bracket creation (exponential backoff)
5. Verify bracket existence on exchange (REST API) before PLACE
6. Add metrics + alerting for unprotected positions
7. Implement circuit breaker for watchdog on repeated failures

#### Priority 3: Long-term Architecture

8. Distributed lock (Redis) for multi-instance deployments
9. State machine for bracket lifecycle (PENDING → PLACING → ACTIVE)
10. Comprehensive audit trail for bracket operations
11. A/B testing framework for bracket logic changes

### Root Cause Analysis: Incident Scenarios

#### Scenario 1: SOL Without TP/SL
1. Entry order for SOL filled → `_on_position_updated()`
2. `_apply_bracket_plan()` called to create TP/SL
3. **Failure point:** Timeout or validation error
4. **Missing:** Error handling + retry + alerting
5. **Result:** Position opened without protection

#### Scenario 2: Duplicate TP on BTC
1. Initial state: BTC LONG with 1 TP, 1 SL
2. User manually cancels all TP/SL via exchange interface
3. Watchdog cycle runs, sees missing brackets
4. **Race condition:** Watchdog + reconciliation both call `_apply_bracket_plan()`
5. **Missing:** Lock protection between concurrent flows
6. **Result:** 2 TP orders created

### Next Steps

#### Immediate Actions (TODAY)

#### Investigation Tasks

#### Documentation

### Related Work



**Completed by:** AI Auditor (Antigravity)
**Date:** 2025-11-24
**Status:** ✅ AUDIT COMPLETE — HOTFIX NEEDED


## 2025-11-23: OCO-AUDIT-R1 Package Completed

### Summary

Completed full audit package **OCO-AUDIT-R1** for Aggregated OCO / TP-SL lifecycle analysis.

### Tasks Completed

#### ✅ OCO-AUDIT-R1-A: Architectural Map
- **File:** `docs/audit/OCO_AUDIT_R1A_ARCH_MAP.md`
- **Output:** Complete architectural documentation
  - 11 component modules mapped
  - 10+ FSM events identified
  - 2 implementation paths (Legacy vs V2)
  - 11 identified gaps (P0-P2 severity)
  - State diagram with 8 states
  - Event-to-handler mapping for both paths

**Key Findings:**
- Dual implementation (Legacy FSM + V2 Runtime) creates maintenance burden
- `recalc_on_partial_close=false` default in legacy is critical bug
- No `position_id` binding — brackets tied only to `(symbol, side)` key

#### ✅ OCO-AUDIT-R1-B: Size Synchronization
- **File:** `docs/audit/OCO_AUDIT_R1B_SIZE_SYNC.md`
- **Output:** Position size sync audit
  - 4 scenarios analyzed (partial close, scale-in, reverse, full close)
  - 3 formal invariants defined (R1-B-INV-1/2/3)
  - 4 legacy gaps identified
  - Complete code traces for each scenario

**Key Findings:**
- **R1-B-GAP-1 (P0):** Legacy `recalc_on_partial_close=false` leaves positions unprotected
- **R1-B-INV-1:** Bracket qty ≤ position qty — violated in legacy, enforced in V2
- V2 always enforces recalc via `BracketService.evaluate()`

#### ✅ OCO-AUDIT-R1-C: Race Conditions
- **File:** `docs/audit/OCO_AUDIT_R1C_RACES.md`
- **Output:** Race condition analysis
  - 4 race scenarios with sequence diagrams
  - 7 risks cataloged (R1-C-RISK-1 through R1-C-RISK-7)
  - Data staleness analysis (position & orders sources)
  - Mitigation strategies documented

**Key Findings:**
- **R1-C-RISK-1 (P0):** OrderGuardian cleanup before position visible
- **R1-C-RISK-3 (P0):** Concurrent fills → duplicate SL/TP
- V2 mitigates via throttling (3s), snapshot TTL, guard loop

#### ✅ OCO-AUDIT-R1-D: Test Plan
- **File:** `docs/audit/OCO_AUDIT_R1D_TESTPLAN.md`
- **Output:** Comprehensive test package proposal
  - 48 test scenarios across 4 groups
  - Fixture structure defined
  - Test-to-invariant mapping
  - Test-to-risk mapping
  - Mock implementations
  - Execution strategy (3-week plan)

**Key Deliverables:**
- Group 1: Position size changes (10 tests)
- Group 2: Close + re-entry races (5 tests)
- Group 3: Timeout/snapshot (6 tests)
- Group 4: Manual cancel (4 tests)
- Unit tests: Invariant validation (5 tests)
- Integration tests: E2E flows (10+ tests)

### Artifacts Created

```
docs/audit/
├── OCO_AUDIT_R1A_ARCH_MAP.md       (Architecture)
├── OCO_AUDIT_R1B_SIZE_SYNC.md      (Size sync audit)
├── OCO_AUDIT_R1C_RACES.md          (Race conditions)
└── OCO_AUDIT_R1D_TESTPLAN.md       (Test plan)
```

### Invariants Defined

| ID | Definition | Enforcement |
|----|------------|-------------|
| **R1-B-INV-1** | Bracket qty ≤ position qty | Legacy: Config-dependent ❌; V2: Automatic ✅ |
| **R1-B-INV-2** | Flat position → No brackets within N events | Both: ✅ Satisfied |
| **R1-B-INV-3** | No hanging brackets (untracked orders) | Legacy: At risk ⚠️; V2: Enforced ✅ |

### Risks Cataloged

| ID | Severity | Description | Mitigation |
|----|----------|-------------|------------|
| **R1-C-RISK-1** | P0 | OrderGuardian cleanup timing | V2: TTL protection |
| **R1-C-RISK-2** | P1 | Symbol-only cleanup key | V2: Side segregation |
| **R1-C-RISK-3** | P0 | Concurrent fills duplicate brackets | V2: Throttling (3s) |
| **R1-C-RISK-4** | P1 | Duplicate bracket orders | V2: Equivalence check |
| **R1-C-RISK-5** | P2 | Stale ORDERS_SNAPSHOT | V2: Force refresh |
| **R1-C-RISK-6** | P1 | Position flip cleanup | V2: Watchdog auto-cancel |
| **R1-C-RISK-7** | P1 | Watchdog + fill race | V2: Throttling + equivalence |

### Gaps Identified

| ID | Severity | Component | Description |
|----|----------|-----------|-------------|
| **R1-A-GAP-1** | P1 | Architecture | Dual implementation drift |
| **R1-A-GAP-5** | P0 | Legacy | `_clear_guardian_bracket_set()` NOT called on partial close |
| **R1-B-GAP-1** | P0 | Legacy Config | `recalc_on_partial_close=false` default |
| **R1-B-GAP-2** | P1 | Legacy | Guardian metadata cleared without recalc |

### Statistics

- **Total audit artifacts:** 4 documents
- **Total pages:** ~60 pages of analysis
- **Total test scenarios proposed:** 48
- **Total invariants defined:** 3
- **Total risks identified:** 7
- **Total gaps identified:** 11
- **Time invested:** ~3 hours

### Recommendations

#### Immediate Actions (P0):
1. ✅ Set `recalc_on_partial_close=true` in all production configs (Legacy)
2. ✅ Maintain V2 invariants (already enforced)
3. 📊 Add monitoring for `partial_close_no_recalc_count` metric

#### Short-term Actions (P1):
1. 🧪 Implement test suite from R1-D (48 tests)
2. 🔍 Add `position_id` to bracket_set key
3. 📈 Track watchdog violations in production metrics

#### Long-term Actions (P2):
1. 🏗️ Complete legacy → V2 migration
2. 🧹 Remove legacy code paths
3. 📚 Document V2 contracts in wiki

### Next Phase

**PACK: OCO-STABILIZE-R2** (Future) will implement:
- All 48 tests from R1-D
- Fixes for identified P0/P1 gaps
- Enhanced monitoring and alerting
- Production validation

### References

- Parent task: `PACK: OCO-AUDIT-R1`
- Previous work: `INVESTIGATION_AGGREGATED_OCO.md` (Nov 19, 2025)
- Related: `EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md`

---

**Completed by:** AI Auditor (Antigravity)
**Date:** 2025-11-23
**Status:** ✅ READY FOR HANDOFF

---

## 2025-11-26: RID: BINANCE-ENDPOINTS-MAP

### Summary
Inventory of all Binance REST/WS endpoints; created `docs/BINANCE_ENDPOINTS_MAP.{md,json}`.

### Tasks Completed
- **Documentation**: Created `docs/BINANCE_ENDPOINTS_MAP.md` mapping all REST/WS endpoints to domains and events.
- **JSON Map**: Created `docs/binance_endpoints_map.json` for machine-readable access.

### Next Steps
- [ ] 🔲 Review and validate endpoint mappings
- [ ] 🔲 Integrate with existing API documentation
- [ ] 🔲 Publish documentation update

## 2025-11-26: RID: BINANCE-MAP-V2-AUDIT

### Summary
Completed V2 Audit and Hardening of Binance Endpoints Map. Established Single Source of Truth, identified Algo Service Tech Debt, and finalized machine-readable map.

### Tasks Completed
- **Audit**: Full codebase scan for `fapi` and `wss` usages.
- **Documentation**: Updated `docs/BINANCE_ENDPOINTS_MAP.md` with "Tech Debt" section and accurate "Hybrid" market data description.
- **JSON Map**: Finalized `docs/binance_endpoints_map.json` with complete schema including `tech_debt` section.
- **Tech Debt**: Explicitly identified missing Algo Service endpoints (`/fapi/v1/algoOrder`) required for advanced conditional orders.

### Key Findings
1. **Hybrid Market Data**: Confirmed `MarketDataConnector` uses REST polling (`bookTicker`, `trades`, `klines`) to simulate WS data.
2. **Algo Service Gap**: Missing support for server-side conditional orders (STOP, TRAILING_STOP). Currently relying on local emulation or basic STOP_MARKET.
3. **Idempotency**: Confirmed `clientOrderId` usage in `binance_execution_adapter.py` for idempotent operations.

### Artifacts Created/Updated
- `docs/BINANCE_ENDPOINTS_MAP.md` (Updated)
- `docs/binance_endpoints_map.json` (Updated/Overwritten)

### Next Steps
- [ ] 🔲 Implement Algo Service endpoints (Tech Debt)
- [ ] 🔲 Migrate Market Data to full WebSocket (if latency requirements demand)

---

## 2025-11-26: RID: BINANCE-ENDPOINTS-MAP-GUARD-TEST

### Summary
Added guard test to keep `docs/binance_endpoints_map.json` in sync with actual Binance endpoints used in code.

### Tasks Completed
- Created `tests/test_binance_endpoints_map.py`
- Implemented JSON structure validation
- Implemented static code analysis (regex-based) to verify code usage vs JSON map
- Implemented Tech Debt sanity check for Algo Service
- Verified test failure with fake endpoint injection

### Files
- `tests/test_binance_endpoints_map.py`
- `docs/binance_endpoints_map.json`

---

## 2025-11-26: RID: AURORA-EXEC-ALGO-SERVICE-BLUEPRINT

### Summary
Added Binance Algo Service migration blueprint, feature flag for conditional orders, and skeleton implementation of POST /fapi/v1/algoOrder in BinanceExecutionAdapter (flag OFF by default), plus tests and endpoints map update.

### Tasks Completed
- Created `docs/ALGO_SERVICE_MIGRATION.md` blueprint.
- Added `use_algo_service_for_conditionals` flag to `ExecutionConfig` (default False).
- Implemented `_place_conditional_via_algo_service` in `BinanceExecutionAdapter`.
- Added routing logic in `_place_binance_order_async` based on flag.
- Created `tests/test_binance_execution_adapter_algo_service.py` covering flag logic and fail-closed behavior.
- Updated `docs/binance_endpoints_map.json` and `docs/BINANCE_ENDPOINTS_MAP.md` with new endpoint.
- Verified with `tests/test_binance_endpoints_map.py`.

### Files
- `docs/ALGO_SERVICE_MIGRATION.md`
- `docs/BINANCE_ENDPOINTS_MAP.md`
- `docs/binance_endpoints_map.json`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`
- `apps/reference/config_models.py`
- `tests/test_binance_execution_adapter_algo_service.py`

## 2025-11-26: RID: BINANCE-USER-STREAM-KEEPALIVE-FIX

### Summary
Implemented periodic keepalive for Binance User Data listenKey (PUT /fapi/v1/listenKey); added tests and controlled reconnect on -1125.

### Tasks Completed
- Added `_last_listen_key_keepalive_at` tracking to `BinanceExecutionAdapter`.
- Updated `_refresh_listen_key` to return success status and handle -1125 error.
- Integrated keepalive check into `_websocket_loop` (every 45 mins).
- Added `tests/test_binance_user_stream_keepalive.py`.

### Files
- `apps/reference/domains/execution_position/binance_execution_adapter.py`
- `tests/test_binance_user_stream_keepalive.py`

---

## 2025-11-26: RID: BINANCE-MARKET-WS-MIGRATION-BLUEPRINT

### Summary
Blueprint and skeleton for Binance Market Data WebSocket migration.

### Tasks Completed
- **Docs**: Created `docs/MARKET_WS_MIGRATION.md` (Blueprint).
- **Config**: Added `use_ws_market_data` flag to `MarketDataConfig` and `config/domains/market_data.yaml`.
- **Code**:
    - Implemented `MarketWSClient` skeleton in `apps/reference/domains/market_data/market_ws_client.py`.
    - Integrated `MarketWSClient` into `MarketDataConnector` (conditional on flag).
    - Updated `ConfigLoader` to hydrate `market_data` from v2 config.
- **Tests**: Added `tests/test_market_ws_client.py`.

### Verification
- `pytest tests/test_market_ws_client.py` passed.
- `pytest tests/test_binance_endpoints_map.py` passed.

### Next Steps
- [ ] 🔲 Review and refine blueprint details
- [ ] 🔲 Implement full WebSocket client logic
- [ ] 🔲 Migrate existing market data consumers to WebSocket
- [ ] 🔲 Monitor and optimize performance

## 2025-11-26: RID: INT-01-C0-HARNESS

- INT-01.C0: оновлено інтеграційний трейд-луп (актуальні timestamps + cooldown через config); harness більше не упирається в stale-guard AuroraBridge.

## 2025-11-26: RID: INT-01-C1-BASELINE

- Повернув `BinanceExecutionAdapterV2` через наследника + helper-и `_create_success_feedback/_create_error_feedback/_build_signed_request`, щоб не ламати контракт ExecPosRuntimeV2 (additive-only, без зміни існуючих гілок).
- `pytest tests/domains/execution_position -q` → 573 passed, 11 skipped, 2 xfailed; це відновило baseline перед DM-driven equity gates.

## 2025-11-26: RID: INT-01-C2

- INT-01.C2: інтегрований DecisionMaking у трейд-луп ExecPosRuntimeV2; побудований DM-driven positive equity тест.

## 2025-11-26: RID: INT-01-C3

- INT-01.C3: інтегровано DM-driven equity<=0 гейти в інтеграційний трейд-луп; equity_free≤0 більше не доходить до AuroraBridge/ExecPosRuntimeV2 (жодних CMD:OPEN/place_order).

---

## 2025-11-26: RID: AURORA-EXEC-ALGO-SERVICE-PHASE3

### Summary
Phase 3 Algo Service Rollout: Testnet Config, Acceptance Tests, Consistency Guards.

### Tasks Completed
- **Testnet Config**: Created `configs/execution_testnet_algo.yaml` with `use_algo_service_for_conditionals: true`.
- **Consistency Audit**: Added `audit_algo_orders_consistency` to `BinanceExecutionAdapter`.
- **CLI Tool**: Created `tools/audit_algo_orders.py`.
- **Integration Tests**: Created `tests/integration/test_algo_service_lifecycle.py` (4 scenarios passed).
- **Verification**: Verified endpoints map and fixed bugs in adapter/tests.

### Files
- `configs/execution_testnet_algo.yaml`
- `tools/audit_algo_orders.py`
- `tests/integration/test_algo_service_lifecycle.py`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`
- `docs/ALGO_SERVICE_MIGRATION.md`

## 2025-11-26: RID: EXEC-AUDIT-V2-FULL-EP-DOMAIN

- Completed full forensic audit of `execution_position` ExecPosRuntimeV2 + BinanceExecutionAdapterV2 domain; see `docs/EXEC_POS_RUNTIME_V2_AUDIT.md` and `docs/EXEC_POS_RUNTIME_V2_AUDIT_CHECKLIST.md` for full report (freeze vs reality, invariant table, risk map, coverage and backlog).

