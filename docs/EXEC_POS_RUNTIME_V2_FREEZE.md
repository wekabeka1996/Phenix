# EXEC_POS_RUNTIME_V2 — Freeze Document

## 1. Scope & Role
- ExecPosRuntimeV2 is the canonical runtime for the execution_position domain (Binance USDT-M futures).
- It orchestrates trade intents, fills, bracket evaluation, and adapter execution via BinanceExecutionAdapterV2.
- Legacy ExecPosFSM remains only as archived reference under `apps/reference/domains/execution_position/legacy`.

## 2. Runtime Topology
- TRADE_INTENT_PROPOSED → AuroraBridge → CMD:OPEN → ExecPosRuntimeV2 → ExecutionService → BinanceExecutionAdapterV2.
- Fills/positions → BracketService (shadow_execpos) → watchdog/agg_oco rules → SL/TP plans → ExecutionService.
- Key modules: `shadow_execpos/runtime.py`, `shadow_execpos/execution_service.py`, `binance_execution_adapter.py`, `shadow_execpos/watchdog.py`, `shadow_execpos/bracket_service.py`, `contracts.py`.

## 3. Core Invariants
- Single gatekeeper: AuroraBridge handles TRADE_INTENT; no dangerous symbol defaults.
- Payload normalization (symbol/quantity/idempotent_key), ExecutionResult contract: `success`, `error_kind`, `is_timeout`, `is_rate_limited`, `why`.
- Brackets: `entry_price > 0` before SL/TP; max 1 SL and 1 TP per symbol+side; Σ qty(SL,TP) ≤ position size; missing/extra handled via watchdog/agg_oco invariants.
- Timeouts: adapter timeouts yield `ADAPTER_ERROR_TIMEOUT`, PLACE_FAILED logged at ERROR; snapshot_state becomes UNKNOWN and blocks bracket evaluation until refreshed (except first fill with no snapshot).

## 4. Adapters & Time Sync
- Canonical adapter: `BinanceExecutionAdapterV2` (binance_execution_adapter.py), selected by adapter_factory for live/testnet/hybrid.
- Time sync/drift: offset cache with WARN thresholds; avoids repeated spam when offset stable.
- get_open_orders retry/backoff: fixed attempts, backoff delays; empty responses are not retried; fallback mode invoked on exhaustion.

## 5. Tests & Coverage
- Latest snapshot: `pytest tests/domains/execution_position -q` → 0 failed, 570 passed, 11 skipped, 2 xfailed (583 collected). Remaining xfail: A/B replay harness.
- Coverage plan: `pytest tests/domains/execution_position --cov=apps/reference/domains/execution_position --cov-report=term-missing -q` (not run in this session). Focus files if <70%: `shadow_execpos/runtime.py`, `shadow_execpos/execution_service.py`, `binance_execution_adapter.py`, agg_oco/watchdog layers.

## 6. Legacy Notes
- Legacy ExecPosFSM files reside in `apps/reference/domains/execution_position/legacy/`; root stubs re-export for compatibility.
- Legacy tests live under `tests/domains/execution_position/legacy/` (marked `execpos_legacy`); they do not define V2 behavior. Any essential logic is mirrored in V2 tests.
- New changes must target ExecPosRuntimeV2; legacy code is frozen/archival unless critical fixes are required.
