# EXEC_POS_RUNTIME_V2 — Audit Checklist

**Task:** EXEC-AUDIT-V2-FULL
**Date:** 2025-11-26
**Status:** ✅ Complete

---

## 1. Invariant Table

| ID | Description | Source | Status | Comment |
| :--- | :--- | :--- | :--- | :--- |
| INV-01 | **Single Gatekeeper**: Only `AuroraBridge` handles `EVT:TRADE_INTENT_PROPOSED` for execution path. | Freeze Doc | ✅ Verified | `main.py` L95: AuroraBridge is sole listener; `runtime_factory.py` disables direct runtime listener |
| INV-02 | **No Dangerous Defaults**: No hardcoded `symbol` (e.g. 'BTCUSDT') or default quantities in runtime. | Freeze Doc | ✅ Verified | `cancel_order` rejects missing symbol; test `test_adapter_symbol_defaults.py` |
| INV-03 | **Brackets Logic**: `entry_price > 0` required before SL/TP placement. | Freeze Doc | ✅ Verified | `runtime.py` L703-718; test `test_e004_entry_price_flow.py` |
| INV-04 | **Brackets Quantity**: Max 1 SL + 1 TP per side; $\sum qty(SL, TP) \le position$. | Freeze Doc | ✅ Verified | `bracket_service.py` L498-504, `_enforce_size_invariants()`; tests in `test_bracket_service.py` |
| INV-05 | **Timeouts Handling**: Adapter timeouts yield `ADAPTER_ERROR_TIMEOUT`; `PLACE_FAILED` logged as ERROR. | Freeze Doc | ✅ Verified | `execution_service.py` L178, L192; test `test_execution_service_connect_timeout_flow.py` |
| INV-06 | **Time-Sync Policy**: Offset cache used; WARN thresholds respected; no log spam. | Freeze Doc | ✅ Verified | `TIME_DRIFT_WARN_CHANGE_THRESHOLD_MS`; test `test_binance_adapter_time_sync.py` |
| INV-07 | **DM Equity Gating**: ExecPos is unaware of equity; all gating happens in DecisionMaking. | Freeze Doc | ✅ Verified | No equity logic in `runtime.py`; DM owns `PortfolioSnapshot` |
| INV-08 | **Payload Normalization**: `symbol`, `quantity`, `idempotent_key` are normalized/validated. | Freeze Doc | ✅ Verified | Pydantic `TradeIntentPayload`, `OpenCommandPayload` validation |
| INV-09 | **ExecutionResult Contract**: `success`, `error_kind`, `is_timeout`, `is_rate_limited`, `why` are always populated. | Freeze Doc | ✅ Verified | `ExecutionResult` @dataclass; `_classify_place_error()` maps all errors |
| INV-10 | **Snapshot State**: Timeout/Error leads to `UNKNOWN` state; blocks bracket eval until refreshed. | Freeze Doc | ✅ Verified | `runtime.py` L665-682; test `test_agg_oco_timeout_and_snapshot_state.py` |
| INV-11 | **cycle_id in clientOrderId**: Enables orphan detection | JOURNAL C1/R2-D | ✅ Verified | `parse_cycle_id_from_client_order_id()`; test `test_client_order_id_contract.py` |
| INV-12 | **Fill qty normalized to abs()** | JOURNAL B1 | ✅ Verified | `_build_trade_executed_payload()`; test `test_trade_executed_qty_normalization.py` |
| INV-13 | **Time drift WARN only on material change** | JOURNAL F1 | ✅ Verified | `TIME_DRIFT_WARN_CHANGE_THRESHOLD_MS` prevents log spam |

## 2. Module Review Status

| Module | Reviewed? | Coverage | Key Findings |
| :--- | :--- | :--- | :--- |
| `shadow_execpos/runtime.py` | ✅ Yes | 86% | Main orchestrator, all handlers verified, no P0/P1 issues |
| `shadow_execpos/execution_service.py` | ✅ Yes | 89% | Error classification complete, timeout handling correct |
| `shadow_execpos/watchdog.py` | ✅ Yes | 93% | Detect-only, delegates to BracketService |
| `shadow_execpos/bracket_service.py` | ✅ Yes | 91% | Pure evaluation, invariants enforced |
| `binance_execution_adapter.py` | ✅ Yes | 41% | Large WS module; P2 issues: reconnect backoff, -4024 retry race |
| `contracts.py` | ✅ Yes | 61% | DTO models, partial coverage due to edge cases |
| `legacy/` | ✅ Yes | N/A | Archived, no V2 imports; isolation verified |
| `shadow_execpos/gatekeeper.py` | ✅ Yes | 94% | Entry validation ported correctly |
| `shadow_execpos/close_flow.py` | ✅ Yes | 95% | Close planning logic verified |
| `shadow_execpos/trailing.py` | ✅ Yes | 93% | Log-only trailing (no auto-adjust) |
| `shadow_execpos/position_model.py` | ✅ Yes | 98% | PositionState, apply_fill verified |
| `shadow_execpos/idempotency.py` | ✅ Yes | 95% | Fill/event deduplication working |

## 3. Test Coverage Verification

| Test Type | Status | Coverage % | Notes |
| :--- | :--- | :--- | :--- |
| Unit Tests | ✅ Complete | 62% (overall) | 573 passed, 11 skipped, 2 xfailed |
| Integration Tests | ✅ Complete | — | 9 trade loop tests, all passing |
| Shadow/Replay | ✅ Complete | 90-99% | `ab_replay.py` 99%, `agg_oco_replay.py` 90% |
| V2 Core Modules | ✅ Complete | 86-94% | Excellent coverage on critical paths |

## 4. Issue Summary

### P2 Issues (Medium Priority)

| ID | Description | Location | Action |
| :--- | :--- | :--- | :--- |
| P2-01 | WS reconnect lacks backoff cap | `binance_execution_adapter.py` L480-580 | Add exponential backoff |
| P2-02 | -4024 retry race condition | `binance_execution_adapter.py` L1004-1067 | Add idempotency key |
| P2-03 | `idempotent_cancel.py` low coverage | L152-255 | Increase test coverage |
| P2-04 | `async_manager.py` edge cases | L37-119 | Add failure path tests |

### P3 Issues (Low Priority)

| ID | Description | Action |
| :--- | :--- | :--- |
| P3-01 | Dead module: `agg_oco_introspection.py` | Remove or archive |
| P3-02 | Dead module: `aurora_log_adapter.py` | Remove or archive |
| P3-03 | Dead module: `drift_monitor.py` | Remove or archive |
| P3-04 | Dead module: `order_index.py` | Remove or archive |
| P3-05 | Magic error strings in adapter | Extract to constants |
| P3-06 | Dead `_is_brackets_suppressed()` | Remove |

## 5. Sign-Off

| Reviewer | Date | Verdict |
| :--- | :--- | :--- |
| GitHub Copilot (Claude Opus 4.5) | 2025-11-26 | ✅ **GO** — Domain approved for freeze |

**Summary:** All 13 invariants verified. No P0/P1 issues found. 4 P2 issues (maintenance debt), 6 P3 issues (cosmetic). Test coverage excellent on V2 core (86-94%).

---

*Checklist completed by EXEC-AUDIT-V2-FULL task*
