# Execution Position & Adapter Audit Report

**Date:** 2025-11-26 (Updated)
**Scope:** `apps/reference/domains/execution_position`, `apps/reference/main.py` (AuroraBridge), Binance Adapters.
**Status:** AUDIT ONLY (No code changes).

---

## 1. Runtime режими та точки входу

### 1.1 Runtime Mode Enforcement
*   **Current Mode:** `v2` only – `ExecPosRuntimeV2` wrapped by `V2RuntimeFacade` (no legacy runtime is instantiated).
*   **Legacy Mode:** Explicitly removed in `runtime_factory.py`. Configuration `execution_position.runtime_mode: legacy` raises `ValueError`.
*   **Resolution Logic:** `apps/reference/main.py::_resolve_execpos_runtime_mode` still reads `execution_position.runtime_mode`, but any `"legacy"` value fails early inside `build_execution_runtime`.

### 1.2 Основні точки входу (V2)

| Event / Command | Source | Entry Point (File::Method) | Payload Fields (Key) | Runtime Path |
| :--- | :--- | :--- | :--- | :--- |
| `EVT:TRADE_INTENT_PROPOSED` | DecisionMaking | `apps/reference/domains/execution_position/runtime_factory.py::V2RuntimeFacade.on_trade_intent_proposed` | `symbol`, `side`, `quantity`/`qty`, `price`, `rid`, `metadata.idempotent_key` | **Direct V2 path:** builds `ENTRY_INTENT` and schedules `ExecPosRuntimeV2.handle`. |
| `EVT:TRADE_INTENT_PROPOSED` | DecisionMaking | `apps/reference/main.py::AuroraBridge.on_trade_intent_proposed` (via global handler) | expects `instrument`/`symbol`, nested `order.qty`/`order.price` | **Bridge path:** applies QoS + portfolio freshness gates, then calls `_dispatch_open` → `CMD:OPEN` → `execution_position.handle` (CMD:OPEN contract is now partially broken, see §2). |
| `CMD:OPEN` | AuroraBridge | `apps/reference/domains/execution_position/runtime_factory.py::V2RuntimeFacade.handle` | `pld.symbol`, `pld.side`, `pld.qty`, optional `pld.price`, `pld.order_type`, `pld.tif`, `pld.idempotent_key` | Converted by `MessageToRuntimeEventAdapter` into `ENTRY_INTENT`; for current DTOs `qty` is often `None` → rejected by Gatekeeper. |
| `CMD:CLOSE` / `CMD:FORCE_CLOSE` | Manual/Strategy | `V2RuntimeFacade.handle` → `MessageToRuntimeEventAdapter.from_legacy_message` | `pld.symbol`, optional `pld.qty`, `pld.reason` | Mapped to `CLOSE_INTENT` (with `is_force=True` for `FORCE_CLOSE`). |
| `CMD:CANCEL` | Manual/Strategy | `V2RuntimeFacade.handle` → `MessageToRuntimeEventAdapter.from_legacy_message` | `pld.symbol`, `pld.order_id`/`pld.client_order_id` | Mapped to `CANCEL_INTENT` and forwarded to ExecutionService. |
| `EVT:TRADE_EXECUTED` | BinanceExecutionAdapter (WS) | `apps/reference/domains/execution_position/runtime_factory.py::V2RuntimeFacade.on_trade_executed` | WS-normalized trade payload (`symbol`, `side`, `quantity`, `price`, `clientOrderId`, `orderId`, etc.) | Fetches open orders snapshot → emits `ORDERS_SNAPSHOT` → forwards `TRADE_EXECUTED` to runtime. |
| `EVT:ACCOUNT_UPDATE_RECEIVED` | BinanceExecutionAdapter (WS) | `apps/reference/domains/execution_position/runtime_factory.py::V2RuntimeFacade.on_account_update` | `balances`, list of normalized `positions` | Emits `ORDERS_SNAPSHOT` and per-position `POSITION_SYNC` into runtime. |

### 1.3 FSM Core Subscriptions

**File:** `runtime_factory.py:46-52`
```python
fsm.listen("EVT:TRADE_EXECUTED", facade.on_trade_executed)
fsm.listen("EVT:ACCOUNT_UPDATE_RECEIVED", facade.on_account_update)
fsm.listen("EVT:TRADE_INTENT_PROPOSED", facade.on_trade_intent_proposed)
```

**Updated finding:** `EVT:TRADE_INTENT_PROPOSED` is still listened to by **both** AuroraBridge and `V2RuntimeFacade`, but because the Bridge expects the legacy `instrument` + `order.{qty,price}` contract, only the **direct V2 facade** path currently produces a valid `ENTRY_INTENT`. This means portfolio freshness and QoS gates implemented in AuroraBridge are effectively **bypassed** for the active V2 runtime.

---

## 2. Interface Contracts (Payload-Level)

### 2.1 DecisionMaking → AuroraBridge (TRADE_INTENT_PROPOSED)

| Field | Expected by AuroraBridge | Actual Usage | Status | Comment |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `instrument` OR `symbol` | `intent_msg.pld.get("instrument") or intent_msg.pld.get("symbol")` | **AMBIGUOUS** | Supports both, but prefers `instrument` (legacy). |
| `side` | `side` | `intent_msg.pld.get("side")` | OK | |
| `qty` | `order.qty` | `order_details.get("qty")` | OK | Nested in `order` dict. |
| `price` | `order.price` | `order_details.get("price")` | OK | Nested in `order` dict. |
| `order_type` | N/A | Hardcoded to `"LIMIT"` | **RIGID** | Bridge forces LIMIT orders. |

### 2.2 AuroraBridge → CMD:OPEN → V2RuntimeFacade

| Field | Expected by Facade | Sent by Bridge | Status | Comment |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `symbol` | `symbol` (resolved) | OK | |
| `side` | `side` | `side` | OK | |
| `qty` | `qty` | `qty` | OK | |
| `price` | `price` | `price` | OK | |
| `order_type` | `order_type` | `"LIMIT"` | OK | |
| `tif` | `tif` | `"GTC"` | OK | |

### 2.3 ExecutionService → BinanceExecutionAdapter (place_order)

| Field | Expected by Adapter | Sent by Service | Status | Comment |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `symbol` | `symbol` | OK | |
| `side` | `side` | `side` | OK | |
| `qty` | `quantity` | `quantity` | **NAMING** | Adapter uses `quantity` internally but accepts `qty` in payload? Checked: Adapter `_adapt_quantity` handles it. |
| `reduceOnly` | `reduceOnly` | `reduce_only` | **NAMING** | Adapter handles `reduceOnly` key, Service sends `reduce_only`. Adapter `place_order_v2` maps it. |
| `stopPrice` | `stopPrice` | `stop_price` | **NAMING** | Adapter `place_order_v2` maps `stop_price` to `stopPrice`. |

### 2.4 V2 entry chain (updated view)

For the **active** execution path (DecisionMaking → `V2RuntimeFacade` → `ExecPosRuntimeV2` → `ExecutionService` → `BinanceExecutionAdapter.place_order_v2`):

- Decision emits flat DTO with `symbol`, `side`, `quantity`, `price`, `idempotent_key`.  
- `V2RuntimeFacade.on_trade_intent_proposed` builds `ENTRY_INTENT` with `payload["quantity"]` populated from `quantity` and forwards it to `ExecPosRuntimeV2.handle`.  
- `_handle_entry_intent` passes `symbol`, `side`, `order_type`, `quantity`, `price`, and **`client_order_id=None`** into `ExecutionService.place_order`.  
- ExecutionService prefers `adapter.place_order_v2`, which maps these to Binance REST fields and returns dicts normalized for success/failure, including `error_kind` and `reason_code` for errors/timeouts.  

Important gaps in this chain today:

- `idempotent_key` never becomes `client_order_id` for entries (entry idempotency gap).  
- Runtime ignores `error_kind` / `is_timeout` when deciding how to react to adapter failures.  
- AuroraBridge path is still wired but uses an outdated DTO contract, so its CMD:OPENs are effectively rejected and its safety gates are bypassed for V2.

---

## 3. Behavioral Invariants Execution

| ID | Invariant | Status | Evidence/Comment |
| :--- | :--- | :--- | :--- |
| **EP-INV-001** | **Aggregated OCO:** "Exactly one TP+SL set per (symbol, side); all entries integrate into shared brackets." | **UNKNOWN** | Tests are failing (`test_baseline_open_creates_single_sl_tp`). Logic exists in `BracketService` but runtime integration seems flaky. |
| **EP-INV-002** | **Fail-Closed Exposure:** "If exposure/balance unknown or stale, CMD:OPEN is rejected." | **OK** | `AuroraBridge` has `_is_portfolio_fresh` check. `ExecPosRuntimeV2` has `gatekeeper`. |
| **EP-INV-003** | **Symbol Consistency:** "Symbol does not change hop-by-hop." | **BROKEN** | `instrument` (Decision) -> `symbol` (Bridge). Aliasing exists. |
| **EP-INV-004** | **Entry Price Validity:** "Position must have valid `avg_entry_price` > 0 for brackets." | **RISK** | Runtime warns `BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE` if missing. |

### 3.2 Updated invariant status (this audit)

| ID | Updated Status | Evidence / Comment |
| :--- | :--- | :--- |
| **EP-INV-001 Aggregated OCO** | **BROKEN** | `test_agg_oco_replay_long_run.py` (both synthetic and real replay) detects duplicate TP orders and SL qty > position. |
| **EP-INV-002 Fail-Closed Exposure** | **BROKEN / DRIFT** | Active ENTRY_INTENT path goes through V2 facade (no portfolio freshness gate); AuroraBridge gate covers only the now-broken CMD:OPEN path. |
| **EP-INV-003 Symbol Consistency** | **BROKEN (legacy), RISK (V2)** | Missing symbol in CMD:OPEN leads to `ENTRY_INTENT.symbol=None` and `"UNKNOWN"` symbol in legacy ManageFlow tests. |
| **EP-INV-004 Entry Price Validity (E-004)** | **OK (for WS → runtime)** | E-004 tests confirm correct WS normalization and runtime parsing; runtime logs clear warnings when entryPrice is missing. |
| **EP-INV-005 Single Position per Symbol** | **OK** | Runtime state keyed by symbol; no evidence of multi-position per symbol in tests. |
| **EP-INV-006 SL requirement for open positions** | **UNKNOWN / PARTIALLY BROKEN** | Watchdog tests see more or different recommendations than expected; behavior is stricter but not aligned with old assertions. |
| **EP-INV-007 Timeout classification** | **PARTIALLY OK** | ConnectTimeout is classified and surfaced via `error_kind`, but runtime doesn’t yet react differently to timeouts vs other errors. |

---

## 4. Known Issues (Specific Problems)

| ID | Severity | Location | Type | Description | Fix Idea |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EP-001-DOUBLE-HANDLING** | **P0** | `runtime_factory.py:58` vs `main.py:460` | Logic Bug | `EVT:TRADE_INTENT_PROPOSED` is handled by BOTH `AuroraBridge` (converting to `CMD:OPEN`) and `V2RuntimeFacade` (converting to `ENTRY_INTENT`). This causes double execution risk or race conditions. | Remove listener from `V2RuntimeFacade` or `AuroraBridge`. Bridge should likely be the sole gatekeeper. |
| **EP-002-NAMING-DRIFT** | **P2** | `main.py:360` | Naming | `AuroraBridge` looks for `instrument` first, then `symbol`. DecisionMaking sends `instrument` (legacy). | Standardize on `symbol` everywhere. |
| **EP-003-HARDCODED-LIMIT** | **P1** | `main.py:380` | Contract | `AuroraBridge` hardcodes `order_type="LIMIT"` and `tif="GTC"`. Prevents MARKET orders or IOC strategies. | Pass `order_type` from intent payload. |
| **EP-004-MISSING-ENTRY-PRICE** | **P1** | `shadow_execpos/runtime.py:1050` | Data Integrity | If `avg_entry_price` is 0/None (e.g. from WS update without it), brackets are skipped. | Ensure Adapter enriches entry price or fetch via REST if missing. |
| **EP-005-ADAPTER-NAMING** | **P2** | `binance_execution_adapter.py` | Naming | Adapter mixes `qty`/`quantity`, `stopPrice`/`stop_price`, `reduceOnly`/`reduce_only`. | Standardize internal keys in Adapter. |

### 4.2 Updated issues from this audit

| ID | Severity | Location (key files) | Type | Short description |
| :--- | :--- | :--- | :--- | :--- |
| **EP-001-SYMBOL-NONE** | P1 | `main.py::_dispatch_open`, `shadow_execpos/event_adapter.py`, `legacy/fsm_manage.py` | Naming / Contract | CMD:OPEN can be built without `symbol`, yielding `ENTRY_INTENT.symbol=None` and `"UNKNOWN"` symbol in legacy ManageFlow, breaking tick-size resolution and bracket placement. |
| **EP-002-CONNECT-TIMEOUT-PLACE-ORDER** | P1 | `binance_execution_adapter._place_binance_order_async`, `shadow_execpos/execution_service`, `shadow_execpos/runtime` | Timeout / Error handling | ConnectTimeout is correctly classified as `ADAPTER_ERROR_TIMEOUT` but runtime doesn’t implement timeout-specific behavior (no FORCE_SNAPSHOT / bracket suppression, no dedicated PLACE_FAILED log). |
| **EP-003-ALGO-ENDPOINT-MIGRATION-RISK** | P2 | `binance_execution_adapter.py` | Architecture | Adapter uses only `/fapi/v1/order` for all orders; no `/fapi/v1/algoOrder` usage, so OCO semantics are entirely local and may miss exchange-native protections. |
| **EP-004-BRIDGE-VS-FACADE-PATH-DRIFT** | P0 | `main.py::AuroraBridge.on_trade_intent_proposed`, `runtime_factory.py::V2RuntimeFacade.on_trade_intent_proposed` | Wiring / Contract | Two listeners on TRADE_INTENT; only V2 facade matches modern DTO, while Bridge contract is partially broken, meaning its QoS/freshness gates are effectively bypassed. |
| **EP-005-ENTRY-IDEMPOTENCY-GAP** | P1 | `shadow_execpos/runtime.py::_handle_entry_intent` | Idempotency | `idempotent_key` is never mapped to `client_order_id` for ENTRY_INTENT, so entry orders lack idempotent clientOrderIds even though adapter supports them. |
| **EP-008-BRACKET-PLACEMENT-NOT-TRIGGERED** | P1 | `shadow_execpos/runtime.py::_evaluate_brackets` / `_apply_bracket_plan` | Logic | Multiple tests show no SL/TP orders placed after fills; bracket plans appear to be computed but not executed. |
| **EP-009-MARK-PRICE-SIGNING-MOCK-BREAK** | P2 | `binance_execution_adapter.py::_get_mark_price_async` | Testability | Mark-price helper now fails when `api_secret` is mocked (non-bytes), leading to `TypeError` and `mark_price=None` in tests. |

---

## 5. Suspected Weak Spots

*   **SW-001 Race Condition (Bridge vs Facade):** Two listeners on `EVT:TRADE_INTENT_PROPOSED` with different contracts; future changes could re-activate Bridge path and cause double handling or inconsistent gating.  
*   **SW-002 Error Propagation:** `BinanceExecutionAdapter` and `ExecutionService` classify errors, but higher layers (runtime/Bridge/ExecutionManagement) largely ignore `error_kind` / `reason_code`, relying only on logs.  
*   **SW-003 Snapshot Consistency:** `ExecPosRuntimeV2` relies heavily on `ORDERS_SNAPSHOT`; delayed/empty snapshots can desync mirror vs exchange state and confuse bracket/watchdog logic.  
*   **SW-004 Timeout/Retry Policy:** ConnectTimeouts are classified but there is no unified policy for snapshot refresh / backoff / bracket suppression at runtime level; retries exist only in isolated adapter paths.

---

## 6. Tests & Coverage (Execution + Adapter)

### 6.1 Test Inventory Summary
*   **Total tests collected (domain):** 573
*   **Passed:** 543
*   **Failed:** 20
*   **Skipped:** 10

#### Main test files (execution_position domain)

| Файл | Що перевіряє |
|------|--------------|
| `test_adapter_factory.py` | Factory creation for different trading modes |
| `test_adapter_precision_guards.py` | Qty/price quantization and min_notional validation |
| `test_aggregated_oco_dr_restart.py` | Aggregated OCO recovery after restart |
| `test_agg_oco_manual_cancel.py` | Manual cancellation of OCO brackets |
| `test_agg_oco_races_close_and_reopen.py` | Race conditions between close and reopen |
| `test_agg_oco_races_guard_loop_vs_trade.py` | Guard loop vs trade execution races |
| `test_agg_oco_replay_long_run.py` | Long-running OCO replay scenarios |
| `test_agg_oco_size_sync.py` | OCO size synchronization |
| `test_agg_oco_symbol_profiles.py` | Symbol-specific OCO profiles |
| `test_agg_oco_timeout_and_snapshot_state.py` | Timeout and snapshot state handling |
| `test_binance_adapter_duplicate_idempotency.py` | -4116 duplicate clientOrderId handling |
| `test_binance_adapter_time_sync.py` | Time synchronization with Binance |
| `test_brackets_config.py` | Bracket configuration parsing |
| `test_bracket_aggregator.py` | Bracket aggregation logic |
| `test_bracket_eval_snapshot_logging.py` | Bracket evaluation logging |
| `test_bracket_state_divergence.py` | Bracket state divergence detection |
| `test_client_order_id_contract.py` | clientOrderId format validation |
| `test_e004_entry_price_flow.py` | E-004 entry price invariant |
| `test_execpos_metrics_fills.py` | Fill metrics tracking |
| `test_exit_order_classification.py` | Exit order kind classification (SL/TP/FLAT_CLOSE) |
| `test_exposure_guard.py` | Exposure guard logic |
| `test_guardian_no_autoheal_v2.py` | Guardian without auto-heal |
| `test_percent_price_error.py` | -4024 PERCENT_PRICE error handling |
| `test_position_side_contracts.py` | Position side contracts |
| `test_trade_executed_qty_normalization.py` | Fill qty normalization (R2-F) |
| `test_watchdog.py` | Watchdog violation detection |

### 6.2 Failing Tests (Current State)
Command: `pytest tests/domains/execution_position -q --maxfail=999`

| # | File | Test Name | Short description |
|---|------|-----------|-------------------|
| 1 | `shadow_execpos/test_ab_replay_basic.py` | `test_ab_replay_full_lifecycle` | Expected 3 adapter calls in A/B replay; actual is 2. |
| 2 | `shadow_execpos/test_ab_replay_basic.py` | `test_ab_replay_happy_path` | A/B replay diff reports fewer actual adapter calls than expected. |
| 3 | `test_percent_price_error.py` | `test_get_mark_price_async_success` | Mark price is `None` due to `TypeError` when api_secret is `MagicMock`. |
| 4 | `legacy/test_manage_flow_fsm.py` | `test_calculate_bracket_prices_and_get_opposite` | Legacy ManageFlow `_calculate_bracket_prices` signature changed (missing `tick_size`/`offset_bps`). |
| 5 | `test_bracket_eval_snapshot_logging.py` | `test_bracket_eval_snapshot_logging` | `PositionState.__init__` no longer accepts `side` kwarg. |
| 6 | `shadow_execpos/test_watchdog_ported_logic.py` | `test_analyze_no_violations` | Watchdog returns non-empty recommendations where test expects none. |
| 7 | `shadow_execpos/test_watchdog_ported_logic.py` | `test_no_sl_for_open_position` | Not all recommendations have `action == ALERT` as asserted. |
| 8 | `shadow_execpos/test_watchdog_ported_logic.py` | `test_position_normalization_various_formats` | Expected 3 recommendations; actual count is 6. |
| 9 | `shadow_execpos/test_execution_service_connect_timeout_flow.py` | `test_execution_service_logs_place_failed` | No log message containing `SHADOW_EXEC_POS_PLACE_FAILED` captured on timeout. |
| 10 | `test_agg_oco_replay_long_run.py` | `test_agg_oco_replay_long_run_invariants` | Aggregated OCO invariants violated (multiple TPs, SL qty > position). |
| 11 | `test_agg_oco_replay_long_run.py` | `test_agg_oco_real_replay_invariants` | Same aggregated OCO violations on real replay sample. |
| 12 | `shadow_execpos/test_execution_service_error_handling.py` | `test_adapter_failure_logs_place_failed` | No `SHADOW_EXEC_POS_PLACE_FAILED` log on adapter error. |
| 13 | `shadow_execpos/test_execution_service_error_handling.py` | `test_adapter_timeout_logs_place_failed_with_timeout_kind` | Same logging expectation failure for timeout path. |
| 14 | `shadow_execpos/test_bracket_wiring.py` | `test_bracket_plan_logged_but_no_side_effects` | `runtime._metrics["brackets_alerts"] == 0` (expected 1). |
| 15 | `shadow_execpos/test_bracket_wiring.py` | `test_bracket_evaluate_called_on_trade_executed_long_position` | `KeyError: 'symbol'` in captured callback payload. |
| 16 | `shadow_execpos/test_execution_service_adapter_errors.py` | `test_place_order_adapter_connect_timeout_marked_failed` | Expected PLACE_FAILED log on ConnectTimeout, none found. |
| 17 | `shadow_execpos/test_execution_service_adapter_errors.py` | `test_place_order_adapter_returns_error_dict_marked_failed` | Expected PLACE_FAILED log on error dict, none found. |
| 18 | `legacy/test_manage_flow_more.py` | `test_place_brackets_and_on_bracket_placed` | `dec` is `None`; legacy FSM fails with `tick_size missing for symbol UNKNOWN`. |
| 19 | `shadow_execpos/test_v2_runtime_smoke.py` | `test_runtime_smoke_open_fill_brackets` | No SL/TP orders in adapter after open+fill. |
| 20 | `shadow_execpos/test_oco_scenarios_v2_full.py` | `test_baseline_open_creates_single_sl_tp` | `execution_service.place_order.await_count == 0` (expected 1–2 bracket placements). |

**Analysis:** Together these failures highlight: (1) aggregated OCO invariant violations; (2) missing or changed bracket placement behavior; (3) logging contract drift for ExecutionService/adapter errors; (4) legacy FSM API drift; and (5) mark-price helper testability issues.

**IMPORTANT:** Tests are NOT fixed or removed at this stage.

---

## 7. Binance Adapter Comparison

### 7.1 Two Binance Adapters

| Aspect | `binance_execution_adapter.py` | `adapters/binance_adapter.py` |
|--------|-------------------------------|------------------------------|
| **Base Class** | `AbstractExecutionAdapter` | `AbstractExchangeAdapter` |
| **Purpose** | Execution orders (place/cancel) | General exchange operations |
| **WebSocket** | Yes, USER_DATA_STREAM | No (REST-only) |
| **Time sync** | `_sync_time_with_server()` | `_sync_time()` with lock |
| **Retry policy** | No automatic retry (except -429) | 1 retry on timeout |
| **Signature** | Custom `_get_signed_params` | `_sign_build()` |
| **Error codes** | Bracket-specific handling | General BinanceAPIError |

### 7.2 Potential Conflicts

1. **Different time sync mechanisms** - may cause different offsets
2. **Different retry policies** - inconsistent behavior
3. **Different signature implementations** - potential signature mismatch

---

## 8. Audit Limitations

1. **No live tests executed** - only unit tests
2. **No runtime logs analyzed** - code analysis only
3. **Not all config variations covered** - focus on default behavior
4. **Other domains (decision_making, risk_management) read only for payload understanding**

---

## 9. Recommendations for Next Stages

### Stage 1: Linters
- [ ] Check naming consistency (qty vs quantity)
- [ ] Check type annotations

### Stage 2: Tests
- [ ] Resolve 5 failing tests (legacy vs v2 interface)
- [ ] Add tests for double TRADE_INTENT_PROPOSED handling
- [ ] Add tests for ORDER_TYPE override

### Stage 3: Documentation
- [ ] Document payload contracts for each hop
- [ ] Migration guide from legacy to v2 runtime

---

**Audit Completion Date:** 2025-11-26
**Status:** COMPLETED (analytical phase)
