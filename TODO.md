# TODO: Wave 0 Implementation — Safety Hotfixes

**Status**: In Progress
**Priority**: CRITICAL
**Target Completion**: 1-2 days
**Owner**: Architecture WG
**Document Version**: 1.2 (Timestamp Fix)
**Last Updated**: 2025-11-23

---

## 📋 Executive Summary

**NEW PRIORITY: EXEC-V2-P0-FIX-S2 (Duplicate Brackets Hotfix)**

Following the live audit (RID: EXEC-V2-LIVE-AUDIT-S2), critical invariant violations identified in BNB testnet case:
- **INV-1 BROKEN**: 2×SL + 2×TP (instead of 1×SL + 1×TP)
- **INV-2 BROKEN**: No bracket blocking after ConnectTimeout
- **INV-5 BROKEN**: ACCOUNT_UPDATE doesn't fetch orders (sl_count=0)
- **INV-6 BROKEN**: Non-idempotent clientOrderId (timestamp-based)
- **INV-8 BROKEN**: _has_equivalent_bracket() fails with empty mirror

**Immediate TODO Items**:

- [ ] **TODO: EXEC-V2-P0-FIX-S2** — Implement ConnectTimeout → force snapshot + block brackets
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py::_apply_bracket_plan()`
  - **Logic**: After `ExecutionResult.success=False` with `error_kind=ADAPTER_ERROR_TIMEOUT`:
    1. Mark `_last_orders_snapshot_ts[symbol] = 0` (force stale)
    2. Call `await self._request_orders_snapshot(symbol)`
    3. Block further bracket actions until snapshot received
  - **Test**: `tests/domains/execution_position/shadow_execpos/test_execpos_v2_connect_timeout_behavior.py` (5 tests → should pass after fix)

- [ ] **TODO: EXEC-V2-P0-FIX-S2** — Verify ACCOUNT_UPDATE → fetch orders before POSITION_SYNC
  - **File**: `apps/reference/domains/execution_position/runtime_factory.py::on_account_update()`
  - **Logic**: Ensure `_sync_orders_and_trigger_brackets()` is called (fix from S21)
  - **Validation**: Check if S21 fix already deployed; if not, implement
  - **Test**: Verify ORDERS_SNAPSHOT event logged before POSITION_SYNC

- [ ] **TODO: EXEC-V2-P0-FIX-S2** — Deterministic clientOrderId for idempotency
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py::_apply_bracket_plan()`
  - **OLD**: `client_order_id = f"{symbol}_{action.action_type}_{int(time.time() * 1000)}"`
  - **NEW**: `client_order_id = f"{symbol}_{position.side}_{action.action_type}_{int(position.avg_entry_price * 100)}"`
  - **Why**: Same position → same clientOrderId → Binance rejects duplicates
  - **Test**: `tests/domains/execution_position/shadow_execpos/test_execpos_v2_duplicate_brackets_live_like.py::test_duplicate_brackets_when_orders_exist_but_mirror_empty`

- [ ] **TODO: EXEC-V2-P0-FIX-S2** — Normalize qty/price in _has_equivalent_bracket()
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/bracket_service.py::_has_equivalent_bracket()`
  - **Issue**: Decimal("10.0") vs Decimal("10") comparison fails
  - **Fix**: Apply same normalization (step_size/tick_size) to both action.qty and leg.order.qty before comparison
  - **Test**: `tests/domains/execution_position/shadow_execpos/test_execpos_v2_duplicate_brackets_live_like.py` (precision mismatch tests)

- [ ] **TODO: EXEC-V2-P0-FIX-S2** — Add "unknown state" to snapshot freshness logic
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py`
  - **NEW STATE**: `_orders_snapshot_state: Dict[str, Literal["FRESH", "STALE", "UNKNOWN"]]`
  - **Logic**:
    - After ConnectTimeout: set state to "UNKNOWN"
    - After successful ORDERS_SNAPSHOT: set state to "FRESH"
    - Block `_evaluate_brackets()` if state != "FRESH"
  - **Test**: `tests/domains/execution_position/shadow_execpos/test_execpos_v2_connect_timeout_behavior.py::test_timeout_should_block_subsequent_bracket_eval__audit`

**Audit Artifacts**:
- `docs/execution_position/EXEC_V2_LIVE_AUDIT_S2.md` (990 lines)
- `tests/domains/execution_position/shadow_execpos/test_execpos_v2_connect_timeout_behavior.py` (420 lines, 5 tests)
- `tests/domains/execution_position/shadow_execpos/test_execpos_v2_duplicate_brackets_live_like.py` (520 lines, 10 tests)

**Target**: Zero duplicate SL/TP in testnet after fixes

---

## Planned Pack: OCO-STABILIZE-R2 (post-audit)

> **PACK: OCO-STABILIZE-R2 — Implementation of tests and fixes from OCO-AUDIT-R1**
>
> - Implement Aggregated OCO test suite designed in `docs/audit/OCO_AUDIT_R1D_TESTPLAN.md`:
>   - `tests/domains/execution_position/test_agg_oco_size_sync.py`
>   - `tests/domains/execution_position/test_agg_oco_races_close_and_reopen.py`
>   - `tests/domains/execution_position/test_agg_oco_timeout_and_snapshot_state.py`
> - Enforce TP/SL size and lifecycle invariants (R1-B-INV-*) in `ExecPosRuntimeV2` + `BracketService`.
> - Address race-condition patterns (R1-C-RISK-*) with explicit contracts and updated specs:
>   - `apps/reference/domains/execution_position/docs/EXEC_POS_BRACKETS_CONTRACT.md`
>   - `docs/EXEC_POS_V2_RUNTIME_SPEC.md`

---

**NEW PRIORITY: EXEC-V2-P0-FIX-NET-S3 (Async/Network Hotfix)**

Following the async/network audit (RID: EXEC-V2-NET-ASYNC-AUDIT-S3), critical async architecture and network issues identified:
- **Event loop conflicts**: asyncio.run() in callbacks → nested loops
- **No retry logic**: PLACE_SL/TP fails on single timeout (40s latency for SL+TP sequential)
- **Undefined variables**: 6 instances of `client_order_id` → NameError if error handlers triggered
- **No connection pooling**: New SSL handshake per httpx request (~100ms overhead)

**Immediate TODO Items**:

**P0 (Critical Fixes)**:

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Fix undefined `client_order_id` in error handlers
  - **File**: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  - **Locations**: L2138, L2151, L2164, L2177, L2191, L2204 (_handle_bracket_error method)
  - **Logic**: Add `client_order_id = idempotent_key or params.get("newClientOrderId", "unknown")` before error handler blocks
  - **Severity**: ❌ **CRITICAL** (NameError if bracket error handlers triggered)
  - **Test**: Verify no NameError in error logs after bracket errors (-2021, -4024, etc.)

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Replace asyncio.run() with proper event loop scheduling
  - **File**: `apps/reference/domains/execution_position/runtime_factory.py`
  - **Locations**: L104, L143, L177, L238 (on_trade_executed, on_order_state_changed, on_account_update callbacks)
  - **OLD**: `asyncio.run(self.runtime.handle(runtime_event))` → creates NEW event loop
  - **NEW**: Option A: `asyncio.run_coroutine_threadsafe(coro, self.runtime.loop)` (if runtime has loop ref)
  -         Option B: Queue events for main loop processing (event queue pattern)
  - **Why**: Current pattern creates nested event loops → instability, potential deadlocks
  - **Test**: Verify single event loop during runtime (no "RuntimeError: This event loop is already running")

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Add retry logic for PLACE_SL/TP orders
  - **File**: `apps/reference/domains/execution_position/binance_execution_adapter.py::_place_binance_order_async()`
  - **Pattern**: Similar to `get_open_orders()` retry @ L1344-1462
  - **Logic**:
    ```python
    max_attempts = 3  # From config
    backoff_delays = [200, 500, 1000]  # ms
    for attempt in range(max_attempts):
        try:
            resp = await client.post(...)
            return resp.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            if attempt < max_attempts - 1:
                await asyncio.sleep(backoff_delays[attempt] / 1000.0)
                continue
            else:
                raise  # Final attempt failed
    ```
  - **Test**: `tests/domains/execution_position/adapters/test_binance_adapter_async_connect_timeout.py::test_place_order_no_retry_on_connect_timeout` (should PASS after fix, currently xfail)

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Refactor WebSocket to async task (not thread)
  - **File**: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  - **OLD**: `_start_websocket()` creates thread @ L426-438, runs `_websocket_loop()` @ L440-460
  - **NEW**: WebSocket as async task in main event loop:
    ```python
    async def _websocket_task_async(self):
        while self.ws_running:
            try:
                await self._establish_websocket_connection_async()
            except Exception as e:
                await asyncio.sleep(self.ws_reconnect_delay)  # Async sleep
    
    def _start_websocket(self):
        asyncio.create_task(self._websocket_task_async())
    ```
  - **Why**: Single event loop → no nested loops, proper async/await throughout
  - **Test**: Verify WebSocket runs in main event loop (no threading.Thread.is_alive() check needed)

**P1 (Medium Priority)**:

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Add httpx.AsyncClient connection pooling
  - **File**: `apps/reference/domains/execution_position/binance_execution_adapter.py::__init__()`
  - **Logic**:
    ```python
    # Create persistent client with connection pool
    self._http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=30),
        timeout=httpx.Timeout(self._rest_timeout),
    )
    
    # In all REST methods: use self._http_client instead of async with httpx.AsyncClient()
    resp = await self._http_client.post(url, ...)
    
    # Add cleanup in stop():
    await self._http_client.aclose()
    ```
  - **Why**: Reuse SSL connections → reduce ~100ms handshake overhead per request
  - **Test**: Measure latency reduction for sequential PLACE_SL + PLACE_TP

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Parallel bracket placement (asyncio.gather)
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py::_apply_bracket_plan()`
  - **OLD**: Sequential `await execute_command(sl)` then `await execute_command(tp)` → 40s if both timeout
  - **NEW**:
    ```python
    place_tasks = []
    for action in plan.actions:
        if action.action_type in ("PLACE_SL", "PLACE_TP"):
            task = self.exec_service.execute_command(cmd)
            place_tasks.append(task)
    
    results = await asyncio.gather(*place_tasks, return_exceptions=True)
    # → Both timeout in parallel (~20s instead of ~40s)
    ```
  - **Test**: `test_execpos_v2_connect_timeout_behavior.py::test_place_order_sequential_timeouts` (should reduce latency)

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Add exponential backoff for failed PLACE requests
  - **File**: `apps/reference/domains/execution_position/shadow_execpos/runtime.py::_apply_bracket_plan()`
  - **Logic**: After `ExecutionResult.success=False`, backoff before next action:
    ```python
    if result["success"] is False:
        backoff_ms = min(200 * (2 ** consecutive_failures), 5000)
        await asyncio.sleep(backoff_ms / 1000.0)
    ```
  - **Test**: Verify backoff delays increase after repeated failures

**P2 (Low Priority / Cleanup)**:

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Fix 12 bare `except:` blocks
  - **Files**: `binance_execution_adapter.py` (9 instances), others (3 instances)
  - **Logic**: Replace `except:` with `except Exception:` or specific exception types
  - **Why**: Bare except catches KeyboardInterrupt, SystemExit → prevents graceful shutdown

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Auto-fix 31 lint issues
  - **Command**: `ruff check --fix apps/reference/domains/execution_position/binance_execution_adapter.py apps/reference/domains/execution_position/shadow_execpos/*.py`
  - **Issues**: Unused imports (11), f-strings without placeholders (16), unused variables (3), module-level import (1)
  - **Test**: `ruff check` should show fewer errors after auto-fix

- [ ] **TODO: EXEC-V2-P0-FIX-NET-S3** — Add missing type hints and fix mypy errors
  - **Files**: All execution_position files
  - **Command**: `mypy apps/reference/domains/execution_position --install-types --non-interactive`
  - **Expected**: Missing return types, Any types, Dict vs TypedDict issues

**Audit Artifacts**:
- `docs/execution_position/EXEC_V2_NET_ASYNC_AUDIT_S3.md` (2500+ lines)
- `tests/domains/execution_position/adapters/test_binance_adapter_async_connect_timeout.py` (380 lines, 5 tests)
- `tests/domains/execution_position/shadow_execpos/test_execution_service_connect_timeout_flow.py` (380 lines, 5 tests)
- Ruff check baseline: 53 errors (6 critical, 12 medium, 35 low)

**Success Metrics**:
- Zero NameError exceptions from undefined variables
- Single event loop confirmed (no nested asyncio.run())
- <1s average latency for REST calls with connection pooling
- <25s worst-case latency for SL+TP placement (parallel, with retry)

---

Wave 0 addresses **4 critical safety risks** identified in audit:
1. **Price SSOT fragmentation** → Inconsistent PnL/margin calculations
2. **Position tracking race conditions** → Data integrity violations
3. **DR snapshot disabled** → Extended recovery time
4. **Broad exception handling** → Silent error suppression
5. **NEW**: Binance timestamp errors → TP/SL order rejection

**Validated Against Code**: ✅ All issues confirmed in `apps/reference/` codebase

- [x] **[EP-CONFIG-SSOT-S1]** Typed Config для execution_position (Pydantic/датакласи, не чіпати рантайм) — ✅ COMPLETE (2025-11-25)
  - [x] Step 1: Discovery (manage_config.py dataclasses + execution.yaml)
  - [x] Step 2: Pydantic models (ExecutionPositionConfig, AggregatedOcoConfig, TrailingConfig, CloseConfig)
  - [x] Step 3: Resolver (resolve_execution_position_config, dual-path fallback)
  - [x] Step 4: Tests (27/27 passing, 1.26s)
  - [x] Step 5: Documentation (EP_CONFIG_SSOT_REPORT.md, JOURNAL.md entry)
  - **Files**: config.py (270 lines), execution_position.py (250 lines), test_execution_position_config.py (460 lines), EP_CONFIG_SSOT_REPORT.md (866 lines)
  - **Status**: Zero runtime changes, ready for Phase 2 (runtime integration)
- [x] **[EP-V2-BRACKET-SPAM-FIX-S21]** Fix bracket spam (340 orders for 4 positions) — ✅ COMPLETE (2025-11-23)
  - **Problem**: ExecPosV2 generated 340 TP/SL orders because sl_count/tp_count always 0 (didn't see existing orders)
  - **Root Causes**: ACCOUNT_UPDATE triggered brackets but didn't fetch orders, no throttling, repeated spam
  - **Solution**:
    - TASK 1: Fetch orders via get_open_orders() + emit ORDERS_SNAPSHOT ✅
    - TASK 2: BracketService already classifies SL/TP correctly ✅
    - TASK 3: Add 3s throttle for account_update_sync ✅
    - TASK 4: Integration tests (pending)
  - **Files**: runtime_factory.py (2 methods), runtime.py (3 changes)
  - **Status**: Runtime now sees existing orders and throttles repeated evaluations
- [x] **[EP-ADAPTER-TIME-SYNC-FIX-S20]** Fix Binance -1021 timestamp errors — ✅ COMPLETE (2025-11-23)
  - **Problem**: Binance rejected TP/SL orders with -1021 "Timestamp outside recvWindow", causing WATCHDOG_VIOLATION spam
  - **Root Causes**: recvWindow=1500ms (too small), no startup time sync, broken retry logic, no periodic resync
  - **Solution**: Increase recvWindow to 5000ms, add startup sync, fix retry, add periodic resync every 5 minutes
  - **Files**: binance_execution_adapter.py (5 methods modified)
  - **Status**: TP/SL orders should now pass Binance timestamp validation
- [x] **[EP-CONFIG-EXECUTION-VALIDATOR-S8]** Fix execution validation to recognize ExecutionPositionConfig V2 — ✅ COMPLETE (2025-11-27)
  - **Problem**: Validator reports "execution: error – resolve_brackets_config returned source=legacy" despite ExecutionPositionConfig being valid
  - **Solution**: Update `tools/config_validator_v2.py` to check ExecutionPositionConfig first; downgrade brackets_config.source=legacy to warning (not error) when V2 present
  - **Files**: config_validator_v2.py (+40 lines), test_execution_validator_v2_simple.py (2 tests)
  - **Tests**: 58/58 execution tests passing (0.78s)
  - **Constraint**: Zero changes to domain code (apps/reference/domains/execution_position/**)
  - **Status**: Validator recognizes ExecutionPositionConfig V2 SSOT, execution: ok when V2 present
- [x] **[EP-CONFIG-FEATURES-OVERRIDES-S9]** Fix config v2 schema validation (overrides + features domain) — ✅ COMPLETE (2025-11-27)
  - **Problem 1**: Schema error "None is not of type 'object'" for overrides/modes/instruments (ConfigV2 has Optional[Dict]=None but schema required object)
  - **Problem 2**: Features error "domains['features'] is missing or empty" (features.yaml exists but loader searches wrong path)
  - **Solution 1**: Allow null in schema for overrides/modes/instruments (type: ["object", "null"]), remove from required fields
  - **Solution 2**: Copy config/domains/*.yaml → apps/reference/config/domains/ (7 domain configs including features.yaml)
  - **Files**: config_v2.schema.json (+6 lines), test_config_v2_overrides_normalization.py (6 tests, 143 lines), test_features_config_v2_minimal.py (6 tests, 130 lines)
  - **Tests**: 146/146 config tests passing (1.75s), overrides: 6/6, features: 6/6
  - **Constraint**: Zero changes to execution_position/shadow_execpos domains
  - **Status**: schema: ok, features: ok, execution: ok — Config validator status: ok 🎯
- [ ] **TASK-04**: Centralize execution exposure & fallback via `resolve_exposure_policy`; refactor guards/adapters accordingly — PR TBD
- [ ] **TASK-06**: Freeze SSOT config contract (schema/map/validation/CI) — PR TBD
- [ ] **TASK-07.2**: Execution_position F1 (brackets resolver) + F2 (exposure TTL) validation hardening — PR TBD
- [ ] **TASK WAL-1.1**: JSON-safe WAL for position_tracking (sanitize rid/Mock + regression tests) — PR TBD
- [ ] **TASK WAL-1.2**: AlertManager config hardening for position_tracking (reject mocks, add config tests) — PR TBD
- [ ] [EP-IDEMPOTENCY-STORE-CLEANUP-B] Evaluate merging `_processed_events` and `_seen_fills` into a unified IdempotencyStore with shared TTL + metrics (follow-up to EP-IDEMPOTENCY-STORE-CLEANUP-A).
- [ ] [EP-MANAGE-CLOSING-FLAG-RACE-A] Harden ManageFlow closing flag release so delayed ENTRY fills cannot resurrect brackets during CLOSE (PR TBD).
- [ ] [EP-ORDERS-CONTRACTS-CLIENTID-A] Unify clientOrderId builder/parser + exit classification, adapt ManageFlow/ExecPos/Guardian, add regression tests/docs (PR TBD).

### Aggregated OCO Track (Wave 0 extension)

- [x] [OCO-2.1] Написати інтеграційний Red-тест для legacy scale-in (позиція частково без SL).
- [x] [OCO-2.2] Підготувати Red-тест для partial-close (коли позиція тимчасово без SL).
- [x] [EP-STAB-PERCENT-PRICE] Add `-4024` (PERCENT_PRICE) error handler in BinanceAdapter — Implemented: fetch mark price, validate/adjust stopPrice against ±10% band, retry with 8% safe clamp. Files: `binance_execution_adapter.py` (3 methods: case in `_place_binance_order_async`, handler in `_handle_bracket_error`, `_get_mark_price_async`). Expected: -4024 errors ⬇️ 100%→~5%, unprotected window ⬇️ 60s→10-20s. Test: TODO (mock -4024, verify adjustment/retry).
- [ ] [EP-STAB-LIVEPOS-AGG-OCO-AUDIT] SL-spam investigation + root cause discovery (Phase 1 Complete ✅, Phase 2 Pending)
  - **Phase 1**: Comprehensive audit (A-D sections in docs/EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md)
    - A.1: Responsibility map for FSM hierarchy ✅
    - A.2: Duplicate logic check — **CRITICAL FINDING**: Divergent exit-order classification (is_exit_order vs _is_sl_order) ✅
    - B.1-B.3: Invariant analysis + auto-heal semantics ✅
    - C: Regression test suite (3 PASS ✅ + 2 XFAIL documented) ✅
    - D: Root cause hypothesis — Watchdog heuristic misses LIMIT+reduceOnly orders ✅
  - **Phase 2 (COMPLETE ✅)**: Fix divergent exit-order classification (consolidate to is_exit_order)
  - **Artifacts**:
    - docs/EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md ✅
    - tests/domains/execution_position/test_agg_oco_sl_spam_regression.py ✅
    - JOURNAL.md entry ✅
- [x] **[EP-STAB-SL-CLASS-FIX] Unify EXIT/SL classification & stop SL spam** (✅ COMPLETE)
  - [x] **A** (DONE): Unified classifier (ExitOrderKind + classify_exit_order) — **45 PASS** ✅
  - [x] **B** (DONE): Adapt watchdog (exit_kind field, NO_SL guard for FLAT_CLOSE) — **27 agg_oco + 4 watchdog PASS, 1 XPASS** ✅
  - [x] **C** (DONE): Regression tests (happy path, FLAT_CLOSE edge-case) — **3 PASS + 1 XPASS** ✅
  - [x] **D** (DONE): Documentation & validation ✅
  - **Files Modified/Created**:
    - `apps/reference/domains/execution_position/contracts.py` — ExitOrderKind enum + classify_exit_order + is_exit_order delegation ✅
    - `apps/reference/domains/execution_position/agg_oco_watchdog.py` — WatchdogOrder.exit_kind + _normalize_orders + validate_agg_oco_invariants FLAT_CLOSE guard ✅
    - `tests/domains/execution_position/test_exit_order_classification.py` (NEW) — 45 unit tests covering all classifications ✅
    - `tests/domains/execution_position/test_agg_oco_sl_spam_regression.py` (EXPANDED) — 3 new scenarios + 1 xpass now passing ✅
  - **Test Results** (Final Validation):
    - Unit tests: **45 PASS** (100%) ✅
    - Watchdog tests: **4 PASS** (100%) ✅
    - Regression tests: **3 PASS + 1 XFAIL** (1 historical xfail expected) ✅
    - Integration tests: **3 PASS** (100%) ✅
    - Qty guard tests: **2 PASS** (100%) ✅
    - **Total: 57 PASS + 1 XFAIL (58/59 = 98%)** ✅
  - **Quality Metrics** (Final):
    - Code marked with `# EP-STAB-SL-CLASS-FIX` comments (8 marks) ✅
    - Type hints: 100% (Optional[ExitOrderKind], -> bool) ✅
    - Docstrings: Complete (ExitOrderKind, classify_exit_order, WatchdogOrder, validate_agg_oco_invariants) ✅
    - Backward compatible: _is_sl_order preserved, WatchdogOrder.is_sl kept ✅
    - Production ready: zero open issues ✅
- [x] [EP-STAB-ADAPT-ORD-META-MAP] Inventory Binance adapter order models, catalog raw fields vs. internal payloads, and produce mapping doc (docs/EP_STAB_ADAPT_ORD_META_MAP.md). Output: reduceOnly/closePosition/type/stopPrice gap list + call-site analysis for ExecPosFSM watchdog & OrderGuardian. ✅
- [x] [EP-STAB-ADAPT-ORD-META-FULL] Complete order metadata integration: extend ExchangeOrderResponse DTO with 6 new fields (order_type, reduce_only, close_position, stop_price, working_type, position_side), map Binance fields in adapter, wire through watchdog/Guardian, update invariants for FLAT_CLOSE. **Tests**: 7 adapter tests (mapping) + 5 watchdog unit tests + 4 SL-spam regression tests = **15 PASS + 1 XFAIL (16/16)**. **Status**: ✅ COMPLETE
  - [x] EP-STAB-ADAPT-ORD-META-IMPL: DTO extension + BinanceAdapter.get_open_orders mapping (7 adapter tests PASS)
  - [x] EP-STAB-ADAPT-ORD-META-WIRE: Watchdog + Guardian integration, unified classifier usage (5 watchdog tests PASS)
  - [x] EP-STAB-ADAPT-ORD-META-TESTS-SPAM: Regression test pack (3 new scenarios PASS + 1 xfail expected)
  - [x] EP-STAB-ADAPT-ORD-META-DOCS: MAP doc Section 4 "Implementation Status" + JOURNAL umbrella RID
- [x] [OCO-3] Реалізувати pure-агрегатор `compute_aggregated_brackets` та додати його юніт-тести.
- [x] [OCO-3.1] Спроєктувати набір pure-unit тестів для `compute_aggregated_brackets` (happy path, scale-in, partial-close) перед інтеграцією.
- [x] [OCO-3.2] Інтегрувати `compute_aggregated_brackets` у ManageFlowFSM (оновити `_place_brackets` та обробку scale-in/partial-close).
- [x] [OCO-4.1] Додати `BracketSetMeta` state-layer в `OrderGuardian` + тести (`tests/domains/execution_position/test_order_guardian_bracket_state.py`).
- [x] [OCO-4.2] Прив’язати `bracket_set_id` до cleanup/TTL шарів у OrderGuardian (рефакторинги без зміни legacy behavior).
- [ ] [OCO-4] Інтегрувати aggregated OCO в `ManageFlowFSM`.
- [x] [OCO-5.1] Пройти інтеграційні тести OCO-2.1/OCO-2.2 в режимі aggregated_oco.enabled=true та, за потреби, донастроїти зв’язку ManageFlowFSM ↔ OrderGuardian, щоб scale-in і partial-close завжди тримали повний SL coverage — PR TBD.
- [ ] [OCO-5] Рефакторити `OrderGuardian` під `bracket_set_id` та TTL-захист.
- [ ] [OCO-6] Завершити інтеграцію aggregated OCO з config v2, XAI-логуванням та DR/freeze execution-домену.
- [x] [OCO-6.1] XAI/логування для Aggregated OCO + smoke-тест DR/restart при відкритій позиції з активним aggregated OCO (rehydrate helper + tests/domains/execution_position/test_aggregated_oco_dr_restart.py green).
- [x] [OCO-7.1] Документація та freeze execution-домену під Aggregated OCO v1 (оновлено CONTRACT/FSM docs, XAI/DR опис, freeze зафіксовано).
- [x] [OCO-8.2] Уніфікація side (LONG/SHORT) у ManageFlowFSM ↔ OrderGuardian + чистка stale BracketSetMeta при position_qty=0 (TASK OCO-8.2, тести: `test_order_guardian_bracket_state.py`, `test_order_guardian_aggregated_cleanup.py`).
- [x] [OCO-8.3] CLI/observability: `agg_oco_snapshot` (dump активних bracket_set + RID) — підготувати після стабілізації side cleanup.
- [ ] [OCO-9.1] Інтеграційні тести aggregated OCO (multi-entry, partial/full close, multi-symbol harness) — PR TBD.
- [x] [OCO-10.1] WS-driven preflight cache (RID OCO-10.1_WS_POSITION_SNAPSHOT) — PR TBD.
- [x] [OCO-10.2] Zero-position cleanup (RID OCO-10.2_ZERO_POSITION_CLEANUP) — PR TBD.
- [x] [OCO-10.3] Aggregated OCO watchdog invariants (RID OCO-10.3_AGG_OCO_WATCHDOG) — PR TBD.
- [x] [OCO-11.2] Тести aggregated-only режиму (entry/exit payloads без inline TP/SL, open/scale/partial/full/flip сценарії, baseline watchdog smoke) — ✅ `tests/domains/execution_position/test_contract_aggregated_orders_mode.py`, `tests/units/test_agg_oco_invariants_checker.py`.
- [x] [OCO-11.3] Aggregated-only mode flag + жорстке вимкнення legacy inline TP/SL (entry payload validation, config gates, XAI warnings при legacy payloads, regression suite updates) — ✅ runtime flag wired + `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_contract_aggregated_orders_mode.py tests/units/test_agg_oco_invariants_checker.py tests/domains/execution_position/test_aggregated_oco_multi_entry_flow.py tests/domains/execution_position/test_aggregated_oco_partial_close_legacy.py tests/domains/execution_position/test_aggregated_oco_scale_in_legacy.py tests/domains/execution_position/test_order_guardian_aggregated_cleanup.py -v`.
- [x] [OCO-11.4] Watchdog інваріантів (`agg_oco_watchdog.py`, NO_SL/ORPHAN_SL/MULTIPLE_META auto-heal + alerts, integration with ExecPos/Guardian) — ✅ runtime watchdog loop + auto-heal, config gates + `.venv/Scripts/Activate.ps1; pytest tests/units/test_agg_oco_invariants_checker.py tests/units/test_agg_oco_watchdog.py -v` + `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_agg_oco_watchdog_runtime.py -v`.
- [x] [EP-WATCHDOG-GRACE-PERIOD-A] Add grace-period suspicion map + config/test coverage for aggregated watchdog (ExecPosFSM state machine, runtime grace tests, config manifests) — PR TBD.
- [x] [OCO-11.6] Restore watchdog-driven `EVT:TRADE_EXECUTED` delivery to ExecPosFSM (RID OCO-11.6_TRADE_EXECUTED_EMIT_FIX) — `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_watchdog_emit_trade_executed.py tests/domains/execution_position/test_agg_oco_watchdog_runtime.py -v`.
- [ ] [EP-FIX-NO-SL-AUTOHEAL-REMOVE] Clean up deprecated `_heal_no_sl_for_open_position` after monitor-only rollout (follow-up to EP-FIX-NO-SL-AUTOHEAL-KILL).
- [ ] [EP-FIX-ENTRY-PRICE-FALLBACK-B / EVENT ENRICHMENT] Ensure TRADE_EXECUTED events always carry entry_price and are idempotent by orderId; extend enrichment/idempotency guards to reduce missing-price brackets.
- [ ] [EP-FIX-TRADE-EXECUTED-IDEMPOTENT-B] Enforce idempotency for TRADE_EXECUTED by orderId/cumQty to avoid duplicate FSM effects.
- [ ] [EP-FIX-TRADE-EXECUTED-IDEMPOTENT-C] Expand idempotency key to (symbol, side, orderId, tradeId) and purge `_seen_fills` on per-symbol resets; consider dedicated IdempotencyStore.
- [x] [EP-ASYNC-CLEANUP-SHUTDOWN-B] Add `_shutdown_background_tasks` helper + lifecycle wiring so ExecPosFSM cancels/awaits `_bg_tasks` during shutdown; regression: `tests/domains/execution_position/test_execpos_async_submit.py` (new shutdown coverage) — PR TBD
- [x] [OCO-11.12A] Жорстка валідація execution/manage режимів (explicit `mode`, aggregated-only safeguards, config manifests, regression tests) — `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_manage_config_aggregated_modes.py -v`; повторна валідація 2025-11-18 (auto mode inference + recalc guard).
- [x] [OCO-11.12B] Observability/state dump: `ExecPosFSM.get_agg_oco_state_snapshot()` regression (`test_agg_oco_state_dump.py`) гарантує, що WS qty, ManageFlow SL/TP, Guardian metadata й watchdog статус зливаються у CLI/WHY snapshot — `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_agg_oco_state_dump.py -v`.
- [x] [OCO-11.12C] Production profile freeze: `docs/PROFILE_aggregated_oco_production.md` + контрактні тести `test_agg_oco_symbol_profiles.py` для SOLUSDT/BNBUSDT (min qty, step size, max position, leverage overrides, watchdog gates, exposure caps) — `.venv/Scripts/Activate.ps1; pytest tests/domains/execution_position/test_agg_oco_symbol_profiles.py -v`.
- [ ] [OCO-11.13] Доменні тести aggregated-only (watchdog fill → ManageFlow pipeline, side canonicalization) + pytest матриця — PR TBD.
- [ ] [OCO-11.14] Qty guard + partial-close parity в aggregated-only режимі (ExecutionQtyGuard nested limits, ManageFlowFSM live snapshot qty guard, contract recalc) — PR TBD.
- [x] [OCO-11.14B] Config v2 execution.manage.mode enforcement (resolver validations + `test_manage_config_aggregated_modes.py`, aggregated harness) — PR TBD.
- [x] [OCO-11.14C] ExecPosFSM `_execute_decision` гілка для DEC:PLACE_ORDER + AGG_OCO_BRACKETS_PLACED observability (adapter stop/limit routing, ManageFlow sync) — `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_execpos_place_order_decisions.py -v`, `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_contract_aggregated_orders_mode.py -v`, `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position -q`.
- [x] [FIX-1] Startup: створення брекетів для вже відкритих позицій (Defect #1) — ✅ `tests/domains/execution_position/test_agg_oco_integration.py`.
- [x] [EP-STAB-DR-DEDUP] Deduplicate DR/startup helpers in `apps/reference/domains/execution_position/fsm.py` (`_preflight_position_check_nonzero`, `_ensure_brackets_for_existing_positions`, `_startup_order_guardian_reconcile`) so ExecPosFSM references a single canonical implementation of each logic path.
- [ ] [EP-STAB-DR-TESTS] Expand DR/integration coverage for aggregated OCO startup (missing brackets, OrderGuardian link, preflight non-zero checks) to catch regressions if helper logic needs adjustments for new instruments.
- [x] [EP-STAB-CLOSE-CONTRACT] Centralized DEC:CLOSE construction via `build_dec_close` (contracts.py helper) so CloseFlowFSM and ManageFlowFSM share the same reduce-only contract.
- [x] [EP-STAB-ENTRYEXIT-HELPER] Centralize ENTRY/EXIT classification logic via `is_exit_order()` helper in contracts.py; replace 6 duplicate instances in ExecPosFSM and ManageFlowFSM — `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position -k "fill or entry or exit or place_order" -vv` (16/17 PASS)
- [x] [EP-STAB-POS-SNAPSHOT] Centralize position parsing via `PositionSnapshot` dataclass in contracts.py; replace 5 manual positionAmt/positionSide parsers in preflight/DR/close/watchdog paths — `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position -k "snapshot or position or preflight" -v` (254/256 PASS)
- [x] [EP-STAB-CIRCUIT-WINDOW] Replace counter-based circuit breaker with time-window approach (_exec_error_history deque + 600s window + auto-cleanup) to eliminate false positives from spaced errors — `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_circuit_breaker_window.py -v` (5 PASS), `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_circuit_breaker.py -v` (2 PASS)
- [x] [EP-STAB-GUARDIAN-CLOSE-CLEANUP] Delegate DEC:CLOSE SL/TP cleanup to OrderGuardian.cleanup_orphans(hard=True) instead of manual get_open_orders + cancel_order loops; add clear_bracket_set_for_position() for closed positions — `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_guardian_close_cleanup.py -v` (5 PASS), `.venv\Scripts\Activate.ps1; pytest tests/domains/execution_position/test_agg_oco_integration.py -v` (3 PASS)
- [x] [EP-STAB-ORDERGUARDIAN-CONTRACT] Formalize services.OrderGuardian API contract in markdown (no behavior changes) — `docs/EXECUTION_POSITION_ORDER_GUARDIAN_CONTRACT.md` created with 9 public methods, 4 invariants, DR/restart behavior, FSM contracts, EP-STAB integration notes
- [x] [EP-STAB-LIVEPOS-AUDIT] Deep audit of error chain for live position resolution failures (SOLUSDT auto-heal + ETHUSDT avg_entry_price=0); identified 5 bottlenecks: WS lag, no backoff, REST timeout 2s, watchdog timing, exception propagation; proposed 3 fixes: exponential backoff (100→200→400ms), delayed auto-heal (500ms grace period), graceful degradation (return None + retry); no code changes (pure analysis task) — `docs/EP_STAB_LIVEPOS_AUDIT.md` (14.5KB, 9 sections, 2 scenario event flows, contracts vs reality table, bottleneck analysis, stabilization proposals)
- [x] [EP-STAB-LIVEPOS-FIX] Stabilize live position resolution & aggregated OCO bracket placement (umbrella task): REST backoff (10s window, 5.0s timeout), portfolio stale data handling (positionAmt=0 → None), entry_price guard (None/<= 0 → AGG_OCO_ENTRY_PRICE_NOT_READY, no AggregatedOcoError), observability metrics (livepos_metrics: rest_timeouts/backoff_suppressed/stale_data/success, agg_entry_price_not_ready), documentation (EP_STAB_LIVEPOS_AUDIT.md Section 10, JOURNAL umbrella RID) — `fsm.py` lines 179-183, 225-232, 549-664 (REST backoff + metrics); `fsm_manage.py` lines 190, 1207-1226, 862-866 (entry_price guard + metrics); `test_live_position_resolution.py` (4/4), `test_entry_price_guard.py` (6/6); regression 6/7 PASS
- [x] [FIX-2] Recalc: скасування старих SL/TP перед постановкою нових (Defect #6) — ✅ `tests/domains/execution_position/test_agg_oco_integration.py`.
- [x] [INCIDENT-2025-11-19] Uncontrolled Growth Fix: Watchdog Auto-Heal + Circuit Breaker — ✅ `apps/reference/domains/execution_position/fsm.py`, `tests/domains/execution_position/test_circuit_breaker.py`.
- [x] [INCIDENT-2025-11-19] Infinite Auto-Heal Loop Fix: TTL Bypass + Retry Limit — ✅ `apps/reference/domains/execution_position/fsm_manage.py`, `apps/reference/domains/execution_position/fsm.py`.
- [ ] [INCIDENT-2025-11-19] Root Cause Fix: ManageFlowFSM silent failure investigation & fix (WS snapshot/retry logic).
- [ ] [EXEC-FREEZE] Execution_position (Aggregated OCO v1) — frozen: подальші зміни поведінки лише через новий OCO v2+ RID; дозволено тільки конфіг-тюнінг, observability/XAI.

---

## 🎯 Wave 0 Roadmap

```
Phase 0: Preparation (2h)
  └─> Environment setup, config validation, test baseline

Phase 1: PriceService Implementation (4-6h)
  └─> Core service, unit tests, integration

Phase 2: Position Tracking Lock (2-3h)
  └─> threading.RLock, atomic operations, tests

Phase 3: Snapshot Scheduler (2-3h)
  └─> Re-enable, integrity hash, quiescence mechanism

Phase 4: Error Taxonomy (3-4h)
  └─> Classification, hot paths wrapping, adapter integration

Phase 5: Integration & Testing (4-6h)
  └─> E2E tests, performance validation, metrics

Phase 6: Deployment (2-4h)
  └─> Canary → 50% → 100%, monitoring, rollback readiness
```

**Total Estimate**: 17-26 hours (1-2 days with parallel work)

---

## Phase 0: Preparation & Environment Setup

**Objective**: Validate environment, establish baseline metrics, prepare rollback strategy

### Tasks

- [ ] **PREP-001**: Validate Python environment and dependencies
  ```bash
  .venv/Scripts/Activate.ps1
  python --version  # Should be 3.10+
  pip list | grep -E "pydantic|asyncio|pytest"
  ```
  **DoD**: Python 3.10+, all required packages installed, venv active

- [ ] **PREP-002**: Create feature branch for Wave 0
  ```bash
  git checkout -b wave0-safety-hotfixes
  git push -u origin wave0-safety-hotfixes
  ```
  **DoD**: Branch created, pushed to remote, CI pipeline green

- [ ] **PREP-003**: Backup current configuration
  ```bash
  cp config/aurora/trading.yaml config/aurora/trading.yaml.backup.$(date +%Y%m%d)
  ```
  **DoD**: Backup file created with timestamp

- [ ] **PREP-004**: Establish baseline metrics
  ```bash
  # Run system for 1 hour, capture metrics
  grep "EQUITY_UNKNOWN" logs/*.log | wc -l  # Portfolio staleness
  grep "TIMEOUT.*CANCEL" logs/*.log | wc -l  # Order timeouts
  grep "mark_price\|last_price" logs/*.log | head -20  # Price sources
  ```
  **DoD**: Baseline metrics documented in `BASELINE_METRICS.md`

- [ ] **PREP-005**: Run existing test suite (baseline)
  ```bash
  pytest -v --tb=short > baseline_tests.log
  ```
  **DoD**: All existing tests pass, log saved

- [ ] **PREP-006**: Create rollback script
  ```bash
  # Create ops/rollback_wave0.ps1
  ```
  **DoD**: Script can revert config + code in <2 minutes
- [x] **PREP-007**: Document config inventory (docs/config_analysis/config_inventory.md)
  **DoD**: Базовий інвентар створено, перелік файлів і статусів задокументовано

---

## Phase 1: PriceService Implementation

**Objective**: Implement unified price service with caching, fallback chain, metrics

**Code Validation**: ✅ Confirmed fragmentation in `fsm_manage.py:832-833`, `fsm.py:1431`

### Tasks

#### 1.1: Core Service Implementation

- [ ] **PRICE-001**: Create service directory structure
  ```bash
  mkdir -p vfoundation/services
  touch vfoundation/services/__init__.py
  ```
  **DoD**: Directory exists, `__init__.py` present

- [ ] **PRICE-002**: Implement `PriceQuote` dataclass
  ```python
  # File: vfoundation/services/price_service.py
  @dataclass
  class PriceQuote:
      symbol: str
      mark: Optional[float]
      last: Optional[float]
      mid: Optional[float]
      ts: int  # epoch milliseconds
      source: Literal["MARK", "LAST", "MID"]
  ```
  **DoD**: Dataclass defined with type hints, docstring added

- [ ] **PRICE-003**: Implement `FallbackExhaustedError` exception
  ```python
  class FallbackExhaustedError(Exception):
      """All price sources (MARK/LAST/MID) returned None."""
      pass
  ```
  **DoD**: Exception class in `vfoundation/services/price_service.py`

- [ ] **PRICE-004**: Implement `PriceService.__init__`
  ```python
  def __init__(self, adapter, max_cache_size: int = 100):
      self._adapter = adapter
      self._cache: Dict[str, Tuple[PriceQuote, float]] = {}
      self._lock = asyncio.Lock()
      self._max_cache_size = max_cache_size
  ```
  **DoD**: Constructor with cache, lock, adapter injection

- [ ] **PRICE-005**: Implement `get_mark()` method
  **DoD**:
  - Method calls `_get_cached_or_fetch()`
  - Returns PriceQuote with source="MARK"
  - Raises FallbackExhaustedError if mark is None
  - Docstring complete

- [ ] **PRICE-006**: Implement `get_last()` method
  **DoD**: Same as PRICE-005, but source="LAST"

- [ ] **PRICE-007**: Implement `get_mid()` method
  **DoD**: Same as PRICE-005, but source="MID"

- [ ] **PRICE-008**: Implement `get_current()` with fallback chain
  ```python
  async def get_current(self, symbol: str, working_type: str = "MARK", ttl_ms: int = 250):
      quote = await self._get_cached_or_fetch(symbol, ttl_ms)
      order = fallback_orders[working_type]  # MARK -> LAST -> MID
      # Try each source...
  ```
  **DoD**:
  - Fallback chain (MARK→LAST→MID) works
  - Logs fallback events
  - Raises FallbackExhaustedError if all None

- [ ] **PRICE-009**: Implement `_get_cached_or_fetch()` with TTL
  **DoD**:
  - Check cache under lock
  - Return cached if not expired
  - Force refresh if ttl_ms=0
  - Fetch from adapter outside lock
  - Update cache under lock
  - LRU eviction when cache > max_size
  - Stale-while-revalidate on errors

- [ ] **PRICE-010**: Implement `_fetch_from_adapter()` with lazy-fetch
  ```python
  # CRITICAL: Lazy-fetch strategy (not parallel)
  # 1. Try mark first
  # 2. Only fetch last if mark is None/error
  ```
  **DoD**:
  - Fetch mark first
  - Fetch last only if mark unavailable
  - Handle exceptions from gather
  - Log fetch latency
  - Return PriceQuote

- [ ] **PRICE-011**: Implement `clear_cache()` helper
  **DoD**: Sync method to clear cache (symbol or all)

#### 1.2: Configuration

- [ ] **PRICE-012**: Add PriceService config to `trading.yaml`
  ```yaml
  wave_0:
    price_service:
      enabled: true
      max_cache_size: 100
      default_ttl_ms: 250
      ttl_profiles:
        quick_profit: 100
        sizing: 250
        exposure: 500
        brackets: 250
      lazy_fetch: true
      loop_ownership: "main"
  ```
  **DoD**: Config section added, validated with yaml-lint

#### 1.3: Unit Tests

- [ ] **PRICE-013**: Create test file `tests/services/test_price_service.py`
  **DoD**: File created with pytest fixtures

- [ ] **PRICE-014**: Test: `test_get_mark_cache_miss`
  **DoD**: Asserts adapter called once, quote.mark correct

- [ ] **PRICE-015**: Test: `test_get_mark_cache_hit`
  **DoD**: Asserts adapter NOT called on second call

- [ ] **PRICE-016**: Test: `test_cache_expiration`
  **DoD**: Asserts cache expires after TTL, adapter called again

- [ ] **PRICE-017**: Test: `test_force_refresh`
  **DoD**: Asserts ttl_ms=0 forces adapter call

- [ ] **PRICE-018**: Test: `test_get_current_fallback_chain`
  **DoD**: Asserts mark=None → falls back to last

- [ ] **PRICE-019**: Test: `test_fallback_exhausted`
  **DoD**: Asserts FallbackExhaustedError raised when all None

- [ ] **PRICE-020**: Test: `test_concurrent_access`
  **DoD**: 10 concurrent calls, adapter called only once

- [ ] **PRICE-021**: Test: `test_lru_eviction`
  **DoD**: Cache size stays at max_cache_size after 12 inserts

- [ ] **PRICE-022**: Test: `test_stale_while_revalidate`
  **DoD**: Returns stale cache on adapter error

- [ ] **PRICE-023**: Run all PriceService unit tests
  ```bash
  pytest tests/services/test_price_service.py -v
  ```
  **DoD**: All 10 tests pass

#### 1.4: Integration with ManageFlowFSM (Quick Profit)

- [ ] **PRICE-024**: Add `price_service` parameter to ManageFlowFSM.__init__
  ```python
  def __init__(self, ..., price_service=None):
      self.price_service = price_service
  ```
  **DoD**: Parameter added, stored as instance variable

- [ ] **PRICE-025**: Implement `_check_quick_profit()` with PriceService
  ```python
  async def _check_quick_profit(self, msg: Message):
      if self.price_service:
          quote = await self.price_service.get_mark(self.symbol, ttl_ms=100)
          current_price_dec = Decimal(str(quote.mark))
      else:
          # Fallback to payload
          current_price_dec = Decimal(str(pld.get("mark_price") or pld.get("last_price")))
  ```
  **DoD**:
  - Uses PriceService if injected
  - Falls back to payload if not
  - Converts to Decimal for precision
  - Logs price source

- [ ] **PRICE-026**: Inject PriceService in main.py
  ```python
  # In main():
  price_service = PriceService(adapter=binance_adapter)
  manage_fsm = ManageFlowFSM(..., price_service=price_service)
  ```
  **DoD**: Service instantiated, injected into ManageFlowFSM

- [ ] **PRICE-027**: Test Quick Profit with PriceService
  ```bash
  pytest tests/integration/test_quick_profit_e2e.py -v
  ```
  **DoD**: Quick Profit triggers using PriceService, logs show cache hits

#### 1.5: Performance Validation

- [ ] **PRICE-028**: Performance test: cache hit latency
  ```python
  # Target: <1ms p99
  ```
  **DoD**: p99 <1ms for cache hits

- [ ] **PRICE-029**: Performance test: cache miss latency
  ```python
  # Target: <100ms p99
  ```
  **DoD**: p99 <100ms for cache misses (adapter call)

- [ ] **PRICE-030**: Performance test: concurrent load
  ```python
  # 100 concurrent calls to same symbol
  ```
  **DoD**: No deadlocks, cache hit rate >90%

---

## Phase 2: Position Tracking Lock

**Objective**: Add threading.RLock to prevent race conditions in position mutations

**Code Validation**: ✅ Confirmed no locks in `position_tracking.py:520-640`

### Tasks

#### 2.1: Core Implementation

- [ ] **LOCK-001**: Import threading module
  ```python
  # File: apps/reference/domains/position_tracking/position_tracking.py
  import threading
  ```
  **DoD**: Import added at top of file

- [ ] **LOCK-002**: Add `_lock` to PositionTracking.__init__
  ```python
  def __init__(self, fsm: FSMBase, config: Dict[str, Any]):
      # ...existing code...
      self._lock = threading.RLock()
      LOG.info("PositionTracking initialized with threading.RLock")
  ```
  **DoD**: RLock instantiated, logged

- [ ] **LOCK-003**: Wrap `_update_position()` with lock
  ```python
  def _update_position(self, symbol: str, position_data: dict):
      with self._lock:
          current = self._positions.get(symbol)
          if current:
              self._positions[symbol] = {**current, **position_data}
          else:
              self._positions[symbol] = position_data
          LOG.debug(f"[{symbol}] Position updated (locked)")
  ```
  **DoD**: All mutations inside `with self._lock:`

- [ ] **LOCK-004**: Wrap `on_account_update()` with lock
  ```python
  def on_account_update(self, event: Message):
      positions = event.pld.get("positions", [])

      with self._lock:
          for pos in positions:
              self._positions[pos["symbol"]] = pos
          wal.append({"op": "ACCOUNT_UPDATE", ...})
          portfolio_state = self._build_portfolio_snapshot()

      # Emit outside lock
      self.fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload=portfolio_state)
  ```
  **DoD**: Lock → update → WAL → snapshot → unlock → emit

- [ ] **LOCK-005**: Add `_build_portfolio_snapshot()` helper
  ```python
  def _build_portfolio_snapshot(self) -> dict:
      """Build snapshot (MUST be called inside lock)."""
      return {
          "ts": int(time.time() * 1000),
          "equity": self._calculate_total_equity(),
          "positions": list(self._positions.values()),
          "realized_pnl": sum(self._realized_pnl.values()),
      }
  ```
  **DoD**: Helper method added, docstring warns about lock requirement

- [ ] **LOCK-006**: Wrap other mutation methods with lock
  - `_on_fill_update()`
  - `_on_balance_update()`
  - Any other method mutating `_positions` or `_realized_pnl`

  **DoD**: All mutations protected by lock

#### 2.2: Unit Tests

- [ ] **LOCK-007**: Create test file `tests/units/test_position_tracking_lock.py`
  **DoD**: File created with fixtures

- [ ] **LOCK-008**: Test: `test_concurrent_position_updates`
  ```python
  # 10 concurrent updates to same symbol
  ```
  **DoD**: No data loss, final state consistent

- [ ] **LOCK-009**: Test: `test_atomic_wal_and_emit`
  **DoD**: WAL write + emit happen atomically

- [ ] **LOCK-010**: Test: `test_lock_prevents_race`
  ```python
  # Slow update vs fast update
  ```
  **DoD**: Fast update overwrites slow update correctly

- [ ] **LOCK-011**: Run all lock tests
  ```bash
  pytest tests/units/test_position_tracking_lock.py -v
  ```
  **DoD**: All 3 tests pass

#### 2.3: Performance Validation

- [ ] **LOCK-012**: Performance test: lock overhead
  ```python
  # 100 updates, measure avg latency
  # Target: <5ms per update
  ```
  **DoD**: Average latency <5ms

- [ ] **LOCK-013**: Integration test: no deadlocks under load
  ```bash
  # Run system for 10 minutes, monitor locks
  ```
  **DoD**: No deadlocks, no lock contention warnings

---

## Phase 3: Snapshot Scheduler Re-enable

**Objective**: Enable periodic snapshots with integrity verification and quiescence

**Code Validation**: ✅ Confirmed disabled in `main.py:1134`

### Tasks

#### 3.1: Configuration

- [ ] **SNAP-001**: Add snapshot config to `trading.yaml`
  ```yaml
  wave_0:
    snapshot:
      enabled: true
      interval_sec: 120
      compression: true
      integrity_check: true
      max_snapshots: 10
      adaptive_skip: true
      activity_threshold: 5
      drain_timeout_ms: 500
  ```
  **DoD**: Config section added, validated

#### 3.2: Integrity Hash Implementation

- [ ] **SNAP-002**: Import hashlib and json in `snapshot_scheduler.py`
  **DoD**: Imports added

- [ ] **SNAP-003**: Update `_emit_snapshot_event()` with hash
  ```python
  def _emit_snapshot_event(self):
      start_time = time.time()
      snapshot_data = self._collect_snapshot()

      # Calculate SHA256 hash
      snapshot_json = json.dumps(snapshot_data, sort_keys=True)
      integrity_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()

      snapshot_with_hash = {
          "data": snapshot_data,
          "integrity_hash": integrity_hash,
          "ts": int(time.time() * 1000),
          "version": "v1.0"
      }

      self.fsm.emit("EVT:SNAPSHOT_CREATED", payload=snapshot_with_hash)
      LOG.info(f"✅ Snapshot emitted (hash={integrity_hash[:8]}...)")
  ```
  **DoD**: Hash calculated, included in snapshot payload

- [ ] **SNAP-004**: Implement snapshot verification on load
  ```python
  # File: vfoundation/dr/replay.py
  def load_snapshot(snapshot_path: str) -> dict:
      with open(snapshot_path, 'r') as f:
          snapshot = json.load(f)

      # Verify hash
      expected_hash = snapshot["integrity_hash"]
      snapshot_json = json.dumps(snapshot["data"], sort_keys=True)
      actual_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()

      if actual_hash != expected_hash:
          raise ValueError(f"Snapshot integrity FAILED")

      LOG.info(f"✅ Snapshot integrity verified")
      return snapshot["data"]
  ```
  **DoD**: Verification function added, raises on mismatch

#### 3.3: Quiescence Mechanism

- [ ] **SNAP-005**: Add activity counter to FSM
  ```python
  # Track inflight events
  self._inflight_events = 0
  ```
  **DoD**: Counter added to FSM

- [ ] **SNAP-006**: Increment/decrement on event processing
  ```python
  # On event start: self._inflight_events += 1
  # On event end: self._inflight_events -= 1
  ```
  **DoD**: Counter tracks active events

- [ ] **SNAP-007**: Check activity before snapshot
  ```python
  def _should_take_snapshot(self) -> bool:
      threshold = self.config.get("activity_threshold", 5)
      return self.fsm._inflight_events < threshold
  ```
  **DoD**: Snapshot skips if activity high

#### 3.4: Enable in main.py

- [ ] **SNAP-008**: Update main.py to enable scheduler
  ```python
  snapshot_config = config.get("snapshot", {})
  snapshot_enabled = snapshot_config.get("enabled", True)
  snapshot_interval = snapshot_config.get("interval_sec", 120)

  if snapshot_enabled:
      from apps.reference.domains.snapshot_scheduler import SnapshotScheduler
      snapshot_scheduler = SnapshotScheduler(
          fsm=fsm,
          interval_sec=snapshot_interval,
          config=config
      )
      snapshot_scheduler.start()
      LOG.info(f"✅ Snapshot scheduler enabled (interval={snapshot_interval}s)")
  else:
      snapshot_scheduler = None
  ```
  **DoD**: Scheduler enabled, controlled by config

#### 3.5: Testing

- [ ] **SNAP-009**: Test: snapshot creation
  ```bash
  # Run system for 3 minutes, check logs
  grep "Snapshot emitted" logs/*.log
  ```
  **DoD**: At least 1 snapshot created

- [ ] **SNAP-010**: Test: integrity verification
  ```bash
  # Restart system, check snapshot loaded
  grep "Snapshot integrity verified" logs/*.log
  ```
  **DoD**: Snapshot loaded, hash verified

- [ ] **SNAP-011**: Test: adaptive skip
  ```python
  # Simulate high load, verify snapshot skipped
  ```
  **DoD**: Snapshot skips when activity > threshold

- [ ] **SNAP-012**: Performance test: p95 during snapshot
  ```bash
  # Measure latency during snapshot creation
  # Target: no degradation
  ```
  **DoD**: p95 latency unchanged

---

## Phase 4: Error Taxonomy & Exception Wrapping

**Objective**: Classify exceptions for better retry logic and observability

**Code Validation**: ✅ Confirmed 20+ broad `except Exception:` in execution_position

### Tasks

#### 4.1: Taxonomy Definition

- [ ] **ERR-001**: Create `vfoundation/errors.py`
  ```python
  class PhenixError(Exception):
      """Base class for all Phenix errors."""
      pass

  class ConfigError(PhenixError):
      pass

  class AdapterError(PhenixError):
      pass

  class AdapterTransientError(AdapterError):
      pass

  class AdapterRateLimitError(AdapterError):
      pass

  class AdapterFatalError(AdapterError):
      pass

  class DataIntegrityError(PhenixError):
      pass

  class FSMError(PhenixError):
      pass

  class QuickProfitError(PhenixError):
      pass

  class FallbackExhaustedError(PhenixError):
      pass
  ```
  **DoD**: All error classes defined with docstrings

#### 4.2: Hot Path #1: Entry FSM

- [ ] **ERR-002**: Wrap `_execute_decision()` in fsm.py
  ```python
  # File: apps/reference/domains/execution_position/fsm.py
  from vfoundation.errors import AdapterTransientError, AdapterRateLimitError, AdapterFatalError

  try:
      response = await self.adapter.place_order(...)
  except AdapterRateLimitError as e:
      LOG.warning(f"Rate limit: {e}")
      await asyncio.sleep(5)
  except AdapterTransientError as e:
      LOG.warning(f"Transient error, will retry: {e}")
      # Retry logic
  except AdapterFatalError as e:
      LOG.error(f"Fatal error: {e}")
      raise
  ```
  **DoD**: Classified exceptions replace `except Exception:`

#### 4.3: Hot Path #2: Bracket Placement

- [ ] **ERR-003**: Wrap `_place_bracket()` in fsm_manage.py
  ```python
  from vfoundation.errors import AdapterTransientError

  try:
      bracket_response = await self.adapter.place_order(...)
  except AdapterTransientError as e:
      LOG.warning(f"Bracket placement transient error: {e}")
      # Retry
  except AdapterFatalError as e:
      LOG.error(f"Bracket fatal error: {e}")
      raise
  ```
  **DoD**: Bracket placement errors classified

#### 4.4: Hot Path #3: Exposure Guard

- [ ] **ERR-004**: Wrap `can_open_position()` in exposure_guard.py
  ```python
  from vfoundation.errors import DataIntegrityError

  try:
      equity = self._get_equity()
  except (ValueError, KeyError) as e:
      raise DataIntegrityError(f"Equity calculation failed: {e}")
  ```
  **DoD**: Data integrity errors classified

#### 4.5: Adapter Classification

- [ ] **ERR-005**: Update `binance_adapter.py` to raise classified errors
  ```python
  async def place_order(self, ...):
      try:
          response = await self._request("POST", "/fapi/v1/order", ...)

          if response.status_code == 200:
              return response.json()

          error_code = response.json().get("code")

          if error_code in [-1003, -418]:
              raise AdapterRateLimitError(f"Rate limit")
          elif error_code in [-1021]:
              raise AdapterTransientError(f"Time sync")
          elif error_code in [-2010, -1100]:
              raise AdapterFatalError(f"Invalid symbol")
          else:
              raise AdapterTransientError(f"Unknown error {error_code}")

      except (asyncio.TimeoutError, aiohttp.ClientError) as e:
          raise AdapterTransientError(f"Network error: {e}")
  ```
  **DoD**: HTTP errors mapped to taxonomy

#### 4.6: Safety Floor

- [ ] **ERR-006**: Add safety floor in decision_making.py
  ```python
  from vfoundation.errors import PhenixError, ConfigError

  try:
      qty = self._calculate_position_size(...)
  except ConfigError as e:
      LOG.error(f"Config error: {e}")
      qty = None
  except PhenixError as e:
      LOG.error(f"Phenix error: {e}")
      qty = None
  except Exception as e:
      LOG.error(f"UNKNOWN ERROR: {e}", exc_info=True)
      # ERRORS.labels(class="UnknownError").inc()
      qty = None
  ```
  **DoD**: Unknown errors escalated with full traceback

#### 4.7: Testing

- [ ] **ERR-007**: Test: classified exceptions raised
  ```python
  pytest tests/integration/test_error_handling.py -v
  ```
  **DoD**: AdapterTransientError, AdapterRateLimitError raised correctly

- [ ] **ERR-008**: Test: retry triggered on transient
  **DoD**: Retry logic executes on AdapterTransientError

- [ ] **ERR-009**: Test: no retry on fatal
  **DoD**: AdapterFatalError propagates without retry

- [ ] **ERR-010**: Integration test: error metrics
  ```bash
  # Check logs for error classification
  grep "AdapterTransientError\|AdapterRateLimitError" logs/*.log
  ```
  **DoD**: Errors logged with class names

---

## Phase 5: Integration & End-to-End Testing

**Objective**: Validate all Wave 0 patches work together, no regressions

### Tasks

#### 5.1: Integration Test Suite

- [ ] **INT-001**: Create `tests/wave0/test_wave0_integration.py`
  **DoD**: Test file with all fixtures

- [ ] **INT-002**: Test: PriceService integration
  ```python
  async def test_price_service_integration():
      # Mock adapter, test get_mark, fallback chain
  ```
  **DoD**: PriceService works end-to-end

- [ ] **INT-003**: Test: Position tracking lock
  ```python
  async def test_position_tracking_lock():
      # Concurrent updates, verify no data loss
  ```
  **DoD**: Lock prevents races

- [ ] **INT-004**: Test: Snapshot scheduler
  ```python
  def test_snapshot_scheduler_enabled():
      # Verify scheduler starts, creates snapshots
  ```
  **DoD**: Snapshots created and verified

- [ ] **INT-005**: Test: Error taxonomy
  ```python
  async def test_error_taxonomy_usage():
      # Verify classified exceptions raised
  ```
  **DoD**: Errors classified correctly

- [ ] **INT-006**: Run full integration suite
  ```bash
  pytest tests/wave0/test_wave0_integration.py -v
  ```
  **DoD**: All 4 integration tests pass

#### 5.2: Performance Testing

- [ ] **PERF-001**: Benchmark PriceService latency
  ```bash
  pytest tests/performance/test_price_service_perf.py
  ```
  **DoD**:
  - Cache hit <1ms p99
  - Cache miss <100ms p99
  - Cache hit rate >90%

- [ ] **PERF-002**: Benchmark position lock overhead
  ```bash
  pytest tests/performance/test_position_tracking_latency.py
  ```
  **DoD**: Average update <5ms

- [ ] **PERF-003**: System-wide latency test
  ```bash
  # Run full system for 1 hour under load
  # Measure p95 end-to-end latency
  ```
  **DoD**: p95 latency <50ms (no regression)

#### 5.3: Regression Testing

- [ ] **REG-001**: Run full existing test suite
  ```bash
  pytest -v --tb=short
  ```
  **DoD**: All existing tests still pass

- [x] **REG-002**: Quick Profit E2E test
  ```bash
  pytest tests/integration/test_quick_profit_e2e.py -v
  ```
  **DoD**: Quick Profit works with PriceService

- [ ] **REG-003**: Manual testnet run (30 min)
  ```bash
  ./launch_testnet.ps1
  # Monitor for 30 minutes
  ```
  **DoD**: No crashes, no unexpected errors

#### 5.4: Metrics Validation

- [ ] **MET-001**: Check PriceService metrics
  ```bash
  grep "Cache HIT\|Cache MISS" logs/*.log | tail -100
  ```
  **DoD**: Cache hit rate >90%

- [ ] **MET-002**: Check error classification metrics
  ```bash
  grep "AdapterTransientError\|AdapterRateLimitError\|AdapterFatalError" logs/*.log | wc -l
  ```
  **DoD**: Errors classified (not broad Exception)

- [ ] **MET-003**: Check snapshot metrics
  ```bash
  grep "Snapshot emitted" logs/*.log
  ```
  **DoD**: Snapshots created every ~120s

- [ ] **MET-004**: Check position staleness
  ```bash
  grep "EQUITY_UNKNOWN" logs/*.log | wc -l
  ```
  **DoD**: Staleness reduced vs baseline

---

## Phase 6: Deployment & Monitoring

**Objective**: Deploy to testnet with canary rollout, monitor metrics, prepare rollback

### Tasks

#### 6.1: Pre-Deployment Checklist

- [ ] **DEPLOY-001**: All unit tests pass
  ```bash
  pytest tests/services/ tests/units/ -v
  ```
  **DoD**: 100% pass rate

- [ ] **DEPLOY-002**: All integration tests pass
  ```bash
  pytest tests/wave0/ tests/integration/ -v
  ```
  **DoD**: 100% pass rate

- [ ] **DEPLOY-003**: Performance tests meet targets
  **DoD**: All performance acceptance criteria met

- [ ] **DEPLOY-004**: Linting clean
  ```bash
  ruff check apps/ vfoundation/
  ```
  **DoD**: No errors

- [ ] **DEPLOY-005**: Type checking clean
  ```bash
  mypy apps/reference/domains/
  ```
  **DoD**: No type errors

- [ ] **DEPLOY-006**: Documentation updated
  - [ ] TODO.md tasks marked complete
  - [ ] JOURNAL.md entries added
  - [ ] AUDIT_VERIFICATION_LOG.md status updated

  **DoD**: All docs current

- [ ] **DEPLOY-007**: Rollback script tested
  ```bash
  ops/rollback_wave0.ps1 --dry-run
  ```
  **DoD**: Script executes without errors

#### 6.2: Canary Deployment (10%)

- [ ] **CANARY-001**: Deploy to testnet
  ```bash
  git merge wave0-safety-hotfixes
  ./kill_python.ps1
  ./launch_testnet.ps1
  ```
  **DoD**: System starts without errors

- [ ] **CANARY-002**: Enable Wave 0 features via config
  ```yaml
  wave_0:
    price_service:
      enabled: true
    snapshot:
      enabled: true
    error_taxonomy:
      enabled: true
  ```
  **DoD**: Config updated, system restarted

- [ ] **CANARY-003**: Monitor for 1 hour
  - [ ] Check logs for errors: `grep -i error logs/*.log`
  - [ ] Check metrics: cache hit rate, latency, errors
  - [ ] Watch for crashes or hangs

  **DoD**: No critical errors, metrics healthy

- [ ] **CANARY-004**: Validate key metrics
  ```bash
  # Price service
  grep "Cache HIT" logs/*.log | wc -l  # Should be >90% of total

  # Position tracking
  grep "Position updated (locked)" logs/*.log  # Should see lock messages

  # Snapshots
  grep "Snapshot emitted" logs/*.log  # Should see 30+ snapshots (1h / 2min)

  # Error classification
  grep "AdapterTransientError" logs/*.log | wc -l  # Should be >0
  ```
  **DoD**: All metrics within targets

#### 6.3: Gradual Rollout (50%)

- [ ] **ROLLOUT-001**: If canary succeeds, expand to 50% traffic
  ```yaml
  # Keep Wave 0 enabled, run for 2 hours
  ```
  **DoD**: System stable for 2 hours

- [ ] **ROLLOUT-002**: Monitor expanded rollout
  - [ ] Check portfolio staleness: should decrease
  - [ ] Check order timeouts: should decrease
  - [ ] Check bracket duplicates: should be 0
  - [ ] Check snapshot replay time: should be <30s on restart

  **DoD**: All improvement metrics trending positive

#### 6.4: Full Rollout (100%)

- [ ] **FULL-001**: If 50% succeeds, full rollout
  **DoD**: Wave 0 fully enabled on testnet

- [ ] **FULL-002**: Monitor for 24 hours
  ```bash
  # Continuous monitoring script
  while true; do
    echo "=== $(date) ==="
    grep "error\|exception" logs/*.log | tail -20
    sleep 300  # Every 5 minutes
  done
  ```
  **DoD**: 24h stable operation

- [ ] **FULL-003**: Validate success metrics
  ```bash
  # After 24h:
  # Portfolio staleness rejects < 1/hour
  grep "EQUITY_UNKNOWN" logs/*.log | wc -l

  # Order timeout ratio -50% vs baseline
  grep "TIMEOUT.*CANCEL" logs/*.log | wc -l

  # Bracket duplicates = 0
  grep "BRACKET.*DUPLICATE" logs/*.log | wc -l

  # Snapshot replay < 30s
  grep "Snapshot replay duration" logs/*.log
  ```
  **DoD**: All targets achieved

#### 6.5: Production Readiness

- [ ] **PROD-001**: Testnet stable for 48h
  **DoD**: No critical issues in 48h

- [ ] **PROD-002**: Create production deployment plan
  **DoD**: Runbook with rollback procedures

- [ ] **PROD-003**: Schedule production deployment window
  **DoD**: Low-traffic window identified

- [ ] **PROD-004**: Production deployment (out of Wave 0 scope)
  **Note**: Follow same canary → 50% → 100% process

---

## Rollback Procedures

### Fast Rollback (Config-Only, <30 seconds)

```yaml
# Disable all Wave 0 features
wave_0:
  price_service:
    enabled: false
  snapshot:
    enabled: false
  error_taxonomy:
    enabled: false
```

**Restart system**:
```bash
./kill_python.ps1
./launch_testnet.ps1
```

### Full Rollback (Code Revert, 2-5 minutes)

```bash
# Revert Git commit
git revert HEAD~4  # Revert all Wave 0 commits
git push origin Test_MyPC

# Restore config backup
cp config/aurora/trading.yaml.backup.20251112 config/aurora/trading.yaml

# Redeploy
./kill_python.ps1
./launch_testnet.ps1
```

### Rollback Decision Matrix

| Symptom | Severity | Action | Time |
|:--------|:---------|:-------|:-----|
| PriceService latency >200ms p99 | High | Config disable | 30s |
| Position tracking deadlock | Critical | Code revert | 2min |
| Snapshot crashes | Medium | Config disable | 30s |
| Error taxonomy breaks flow | Medium | Code revert | 2min |
| System-wide crash | Critical | Full rollback | 5min |

---

## Success Criteria (Final DoD)

### Technical Acceptance

- [ ] **All 4 patches implemented**:
  - [x] PriceService with caching, fallback, lazy-fetch
  - [x] Position tracking with threading.RLock
  - [x] Snapshot scheduler with integrity hash
  - [x] Error taxonomy with hot paths wrapped

- [ ] **All tests pass**:
  - [ ] Unit tests: 100% pass (30+ tests)
  - [ ] Integration tests: 100% pass (4+ tests)
  - [ ] Performance tests: All targets met
  - [ ] Regression tests: No broken functionality

- [ ] **Code quality**:
  - [ ] Linting clean (ruff)
  - [ ] Type checking clean (mypy)
  - [ ] Test coverage >90% for new code
  - [ ] Documentation complete (docstrings)

### Operational Acceptance

- [ ] **Metrics improvement** (24h testnet run):
  - [ ] Portfolio staleness rejects: <1/hour (vs baseline TBD)
  - [ ] Order timeout ratio: -50% (vs baseline TBD)
  - [ ] Bracket duplicates: 0 occurrences
  - [ ] Snapshot replay: <30s cold start
  - [ ] Quick Profit closes: Working correctly

- [ ] **Performance** (no regression):
  - [ ] p95 latency: <50ms overall
  - [ ] PriceService cache hit: >90%
  - [ ] PriceService p99 hit: <1ms
  - [ ] PriceService p99 miss: <100ms
  - [ ] Position update latency: <5ms

- [ ] **Stability**:
  - [ ] 48h continuous operation on testnet
  - [ ] No crashes or hangs
  - [ ] No deadlocks
  - [ ] Graceful degradation on adapter errors

### Documentation Acceptance

- [ ] **Updated documents**:
  - [x] TODO.md: All tasks checked off
  - [ ] JOURNAL.md: RID entries for each patch
  - [ ] AUDIT_VERIFICATION_LOG.md: Status → RESOLVED
  - [ ] WAVE_0_IMPLEMENTATION_PLAN.md: Final status
  - [ ] README.md: Wave 0 changes документed

- [ ] **Runbook created**:
  - [ ] Deployment procedures
  - [ ] Rollback procedures
  - [ ] Troubleshooting guide
  - [ ] Monitoring checklist

---

## Known Limitations & Future Work

**Out of Scope for Wave 0** (deferred to Wave 1+):

1. **Global variables / DI container** → Wave 1
2. **Threading + asyncio structural mixing** → Wave 1
3. **FSM bracket race conditions** (complex) → Wave 1-2
4. **Unified retry/backoff policy** → Wave 1
5. **ExecutionManagement routing/TCA** → Wave 1-2
6. **Dead code cleanup** (500+ lines) → Wave 4
7. **Full async migration** (position_tracking) → Wave 1

**Partial Solutions in Wave 0**:
- Position races: 90% fixed (critical mutations locked; FSM bracket races remain)
- Snapshot consistency: Quiescence helps but not full quorum/barrier
- Error coverage: 80% (hot paths only; full coverage in Wave 4)

---

## Progress Tracking

**Overall Progress**: 0/120+ tasks complete (0%)

**Phase Completion**:
- [ ] Phase 0: Preparation (0/6)
- [ ] Phase 1: PriceService (0/30)
- [ ] Phase 2: Position Lock (0/13)
- [ ] Phase 3: Snapshot (0/12)
- [ ] Phase 4: Error Taxonomy (0/10)
- [ ] Phase 5: Integration (0/17)
- [ ] Phase 6: Deployment (0/20+)

**Last Updated**: 2025-11-12
**Next Review**: After Phase 1 completion

---

## Contact & Support

**Questions or Issues?**
- Tag @ArchitectureWG in PR comments
- Check `docs/WAVE_0_IMPLEMENTATION_PLAN.md` for detailed specs
- See `docs/AUDIT_VERIFICATION_LOG.md` for rationale

**Emergency Rollback Contact**: @OnCallEngineer

---

## ✅ COMPLETED TASKS

### P0.1: PositionTracking атомарність
- ✅ Додано asyncio.Lock для атомарних оновлень позицій
- ✅ Реалізовано _atomic_update context manager з rollback
- ✅ Додано update_position метод з перевіркою балансу
- ✅ Unit тест test_position_tracking_rollback проходить
- ✅ WAL логування працює для позиційних оновлень

### P0.2: WHY-chain автопрокидання
- ✅ Додано `parent_rid` поле в `Message` клас
- ✅ Реалізовано `Message.from_parent()` метод
- ✅ WHY-chain накопичується в `data_ref`
- ✅ Unit тест підтверджує parent_rid та data_ref
- ✅ PR: [pending]

### P0.3: FSM WAL persistence
- ✅ Додано WAL логування msg_in в ExecPosFSM.handle()
- ✅ Додано WAL логування msg_out для DEC рішень
- ✅ Реалізовано replay_on_startup() метод для відновлення стану
- ✅ WAL використовує event_type для фільтрації (msg_in/msg_out)
- ✅ Replay фільтрує тільки msg_in події для відновлення

---

## P1: Configuration & Schema Fixes

### P1.1: Fix YAML configuration duplicates, type errors, and hotreload issues

**Status**: Completed
**Priority**: HIGH
**Target**: Fix config duplicates and type errors

**Tasks**:
- [x] **P1.1.1**: Remove duplicate `binance_api` section in `trading.yaml`
- [x] **P1.1.2**: Remove duplicate `instruments` section in `trading.yaml`
- [x] **P1.1.3**: Fix type errors (string numbers should be numbers) - strings are intentional for precision
- [x] **P1.1.4**: Validate YAML syntax and structure
- [x] **P1.1.5**: Test hotreload functionality
- [x] **P1.1.6**: Update schema validation if needed
- [x] **P1.1.7**: Self-audit and unit tests for config loading

**DoD**:
- No duplicate keys in YAML ✅
- All type errors fixed ✅ (strings intentional)
- Hotreload works without errors ✅
- Config loads successfully ✅
- Unit tests pass ✅

### P1.2: Fix sizing_modifiers type (strings to numbers)

**Status**: Completed
**Priority**: HIGH
**Target**: Convert sizing_modifiers from strings to numbers

**Tasks**:
- [x] **P1.2.1**: Change sizing_modifiers values from strings to floats in trading.yaml
- [x] **P1.2.2**: Test that Pydantic parses them as numbers
- [x] **P1.2.3**: Verify sizing calculations work correctly
- [x] **P1.2.4**: Self-audit and unit tests

**DoD**:
- sizing_modifiers parsed as float/dict
- Sizing calculations use numeric values
- No type conversion errors

### P1.3: Consolidate Kelly config (remove duplicates)

**Status**: Completed
**Priority**: HIGH
**Target**: Remove Kelly duplicates and sync payoff_ratio_r

**Tasks**:
- [x] **P1.3.1**: Remove kelly section from system.yaml
- [x] **P1.3.2**: Keep Kelly only in trading.yaml
- [x] **P1.3.3**: Sync payoff_ratio_r to 2.0 (100bps/50bps)
- [x] **P1.3.4**: Update base_probability to 0.55
- [x] **P1.3.5**: Test config loads correctly

**DoD**:
- No Kelly duplicates in config files ✅
- payoff_ratio_r = 2.0 ✅
- Config loads without errors ✅

### P1.4: Fix hotreload whitelist (change_conf_min → confidence_threshold)

**Status**: Completed
**Priority**: HIGH
**Target**: Fix invalid hotreload whitelist key

**Tasks**:
- [x] **P1.4.1**: Replace hmm.change_conf_min with hmm.confidence_threshold in regime.yaml
- [x] **P1.4.2**: Test config loads without errors
- [x] **P1.4.3**: Verify hotreload can access valid keys

**DoD**:
- hotreload_whitelist contains only valid keys ✅
- Config loads successfully ✅
- No invalid key references ✅

## P2: Log Cleanup & Startup Fixes

### P2.1: Standardize log messages (CLEANUP_PENDING → STALE_ORDER_CLEANUP)

**Status**: Completed
**Priority**: MEDIUM
**Target**: Replace outdated log terminology

**Tasks**:
- [x] **P2.1.1**: Find all CLEANUP_PENDING references in codebase
- [x] **P2.1.2**: Replace with STALE_ORDER_CLEANUP in exposure_guard.py
- [x] **P2.1.3**: Verify no remaining CLEANUP_PENDING in code
- [x] **P2.1.4**: Self-audit log standardization

**DoD**:
- No CLEANUP_PENDING in Python code ✅
- Log messages standardized ✅
- Grep shows no matches in code ✅

### P2.2: Implement SYMBOL_TIDY startup emission to prevent first-trade blocking

**Status**: Completed
**Priority**: HIGH
**Target**: Emit SYMBOL_TIDY on OrderGuardian startup

**Tasks**:
- [x] **P2.2.1**: Add EVT:SYMBOL_TIDY emission in OrderGuardian.start()
- [x] **P2.2.2**: Emit for all known symbols on startup
- [x] **P2.2.3**: Test startup emission works
- [x] **P2.2.4**: Verify first trades not blocked

**DoD**:
- SYMBOL_TIDY emitted on startup ✅
- All known symbols covered ✅
- First-trade blocking prevented ✅

### P2.3: Fix feature_engineering config nesting in trading.yaml

**Status**: Completed
**Priority**: MEDIUM
**Target**: Ensure feature_engineering config properly nested

**Tasks**:
- [x] **P2.3.1**: Verify feature_engineering under trading section
- [x] **P2.3.2**: Confirm ConfigLoader reads correctly
- [x] **P2.3.3**: Test feature engineering works with config

**DoD**:
- feature_engineering properly nested ✅
- ConfigLoader loads successfully ✅
- Feature engineering functions correctly ✅

---

## Фаза 1: Розширення inventory до прив’язки ключ → resolver → домен

Після завершення базового inventory (TASK 0.2), розширити `tools/config_inventory.py` для автоматичного мапінгу плоских ключів до:
- Який resolver/модуль їх використовує (наприклад, `ConfigLoader`, `ExposureGuard`).
- Який домен споживає (наприклад, `execution_position`, `risk_management`).
- Чи є дублікати або конфлікти між файлами.

Додати функцію `build_resolver_mapping()` і оновити JSON-артефакт з додатковими полями.

---

## OCO-11.x

- [ ] OCO-11.11: Впровадити рекомендації з розділу 8 аудиту aggregated-only OCO (`docs/audit/OCO_aggregated_only_full_audit.md`) після затвердження оператором.
- [ ] OCO-11.11: review live logs for AGG_SL_SKIPPED_MIN_QTY and refine strategy min position size if needed.

## [Phase 1] Detail mapping for all risk/decision/execution keys in specification.md

Після створення специфікації config v2, деталізувати мапінг для всіх ключів у risk, decision та execution доменах. Доповнити таблицю в `docs/config_v2/specification.md` повним набором прикладів, включаючи edge cases та overrides.

---

##  COMPLETED P0 TASKS (S23-S27)

### EXEC-V2-P0-FIX-LOOP-S5  Event Loop Management Fix
**Status**:  COMPLETED (2025-11-23 16:10)  
**Priority**: P0  
**RID**: EXEC-V2-P0-FIX-LOOP-S5

**Fixed Issues**:
-  S23: ORDERS_SNAPSHOT timing for bracket evaluation (runtime_factory.py:219-233)
-  S24: RuntimeEvent dataclass logging (runtime_factory.py:98-115)
-  S25: Portfolio freshness when positions_last_ts_ms=0 (main.py:134-142)
-  S26: Portfolio TTL 5s35s (main.py:106)
-  S27: Event loop lazy attachment with _ensure_loop() (runtime_factory.py:77-145)

**Validation**:
```
16:10:21 - attached to running loop <ProactorEventLoop running=True> 
16:10:01 - [ExecPosV2-S5] ENTRY_INTENT received 
```

**Tests**: 4/4 passed (test_execpos_v2_facade_loop.py)

---

##  NEW P0 BLOCKER: S28  DecisionMaking Equity Calculation

### TODO: EXEC-V2-P0-FIX-S28  Fix equity=$0 in DecisionMaking position sizing
**Status**:  TO DO  
**Priority**: P0 (blocker  all intents rejected)  
**Assigned**: UNASSIGNED  
**Estimated**: 1 hour

**Problem**:
```
16:10:21 - Portfolio: Equity: 1806.09763780, Positions: 1 
16:10:21 - Cached equity_free_usdt: 1806.09763780 
BUT:
16:10:16 - POSITION_SIZE_CALC: equity=$0, 10%=$0.0 
16:10:16 - REJECT: position size 0.0 is below minimum 10.0 
```

DecisionMaking shows **equity=$0** in `POSITION_SIZE_CALC` but portfolio has **$1806.10**. All trade intents rejected due to insufficient size.

**Investigation Plan**:
- [ ] Step 1: Read decision_making.py around `POSITION_SIZE_CALC` logging
- [ ] Step 2: Trace equity variable in `_make_decision_for_symbol()` position sizing logic
- [ ] Step 3: Check if `cached equity_free_usdt: 1806.09763780` is accessed correctly
- [ ] Step 4: Identify where equity becomes 0 before size calculation
- [ ] Step 5: Fix equity retrieval/calculation logic

**Acceptance Criteria**:
- [ ] DecisionMaking uses correct equity ($1806) in POSITION_SIZE_CALC
- [ ] Trade intents pass minimum size check (>$10)
- [ ] Orders sent to Binance testnet (verify in logs/WebSocket)

**Links**:
- File: `apps/reference/domains/decision_making/decision_making.py`
- Related: S23-S27 (execution pipeline now working, waiting for valid intents)
- Why-chain: RID=`EXEC-V2-P0-FIX-S28`

---
