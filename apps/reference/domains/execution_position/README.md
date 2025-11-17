# Execution Position Domain

## Overview

The `execution_position` domain implements the position execution and lifecycle logic used by the reference app. It is organized as a set of cooperating modules and three FSM flows (Open / Manage / Close). The code in this directory contains the domain FSMs, adapters (live & simulated), guards, correlation helpers and support utilities.

## Architecture

### 3-FSM Design

The domain contains three specialized Finite State Machines:

1. **OpenFlowFSM** - Handles position opening and entry orders
2. **ManageFlowFSM** - Manages active positions with bracket orders (SL/TP)
3. **CloseFlowFSM** - Monitors exit conditions and handles position closure

### Key Components

- **ExecPosFSM** - Main orchestrator managing per-symbol FSM instances
- **ExposureGuard** - Risk management with fail-closed logic
- **OrderTimeoutWatchdog** - Monitors order ACK/FILL timeouts
- **OrderGuardian** - Handles orphan cleanup and position reconciliation
- **Adapters** - Concrete adapters (e.g., Binance) and a simulated adapter for tests

## Domain tree (modules)

Compact index of primary non-document modules in this folder with one-line descriptions:

- `fsm.py` — ExecPosFSM (orchestrator): initialize adapters, wire Open/Manage/Close flows, append DEC to WAL, route events.
- `fsm_open.py` — OpenFlowFSM: validate `CMD:OPEN`, idempotency, rounding, emit `DEC:OPEN`.
- `fsm_manage.py` — ManageFlowFSM: manage active positions, decide bracket placement (SL/TP), emulate OCO, trailing/quick-profit logic.
- `fsm_close.py` — CloseFlowFSM: expiry/manual-close rules and emit `DEC:CLOSE`.
- `exposure_guard.py` — ExposureGuard: pre-open exposure checks, pending/postfill reservations, fallback and soft-clip scaffolding.
- `order_guardian.py` — OrderGuardian wrapper: orphan detection/cleanup and bracket ownership coordination.
- `order_index.py` — OrderIndex: in-memory correlator mapping rid/idempotent_key/clientOrderId ↔ exchangeOrderId.
- `execution_adapter.py` — AbstractExecutionAdapter: adapter interface expected by FSM (place/cancel/get_open_orders/get_open_positions/get_status).
- `binance_execution_adapter.py` — BinanceExecutionAdapter: concrete Binance REST/WebSocket adapter with idempotent cancels and error recovery.
- `simulated_adapter.py` — SimulatedExecutionAdapter: deterministic shadow adapter for tests and local development.
- `watchdog.py` — OrderTimeoutWatchdog: track ACK/FILL timeouts, REST polling fallback, and idempotent cancellation on expiry.
- `utils.py` — Utilities: price quantization, anti-2021 guards, deterministic clientOrderId generation, TP/SL calculations.
- `utils_event_bus.py` — LocalBus: tiny in-process pub/sub for intra-domain routing when global FSM is not used.
- `idempotent_cancel.py` — Idempotent cancel helper: safe cancellation helper used by adapters to absorb 'unknown order' errors.
- `metrics_aggregator.py` / `metrics_collector.py` — Metrics helpers: domain counters and aggregation for observability.
- `soft_clip.py` — Soft-clip scaffolding: dynamic exposure reduction helpers referenced by ExposureGuard.
- `drift_monitor.py` — Drift monitor: detect portfolio vs exchange position drift and surface alerts.
- `aurora_log_adapter.py` — Aurora log adapter: structured audit/event logging to `aurora_events.jsonl`.

## Event Flow

```
CMD:OPEN → DEC:OPEN → EVT:TRADE_EXECUTED → Position Tracking → Bracket Placement
                                      ↓
CMD:CLOSE ← DEC:CLOSE ← Time/Event Rules
```

## Configuration

The domain supports both Pydantic and dict-based configuration. Example snippet:

```yaml
trading:
  execution:
    manage:
      brackets:
        enable: true
        sl:
          fixed_bps: 50
        tp:
          fixed_bps: 100
        offset_bps: 5
        oco_emulation: true
```

### Configuration Contract

- Canonical schema: `config_schema_v1.py`
- Resolver inventory & ownership: `config_contract_map.md`
- Validation pipeline: `python config_validate.py --ci`

ExecPosFSM, ManageFlowFSM, ExposureGuard and the adapter stack **must** obtain configuration through the resolvers described in the contract map (`resolve_execution_manage_config`, `resolve_brackets_config`, `resolve_exposure_policy`, `get_trade_cooldown_sec_for_symbol`). Direct YAML traversal is frozen for SSOT v1.0.

## Risk Management

- **Exposure Limits**: Position size and notional value controls
- **Fail-Closed Logic**: Conservative behavior on exchange/API errors
- **Order Timeouts**: Automatic cancellation of stuck orders via `watchdog`
- **Orphan Detection**: Cleanup of unmatched orders via `order_guardian`

## Testing

Unit and integration tests exercise FSM transitions, adapter interactions and guard behaviors. Run tests from project root:

```powershell
pytest -q
```

## Observability

- Audit logs: adapters and FSMs emit structured entries via `aurora_log_adapter`.
- Metrics: exposed through `metrics_aggregator` / `metrics_collector` (order counts, timeouts, guard triggers).
- WAL: DEC decisions are appended for durability; review `artifacts/` during debugging.

## Known caveats & recommendations

- `ExposureGuard` concurrency: current code mutates reservation structures without an `asyncio.Lock` — recommend adding a lightweight async lock to prevent races.
- `Message` contract: `vfoundation/core/protocol.py` does not contain `parent_rid`; plans assuming it must use `parent_span_id`/`data_ref` instead or extend the Message schema.
- WAL replay: DEC append exists but a startup replay path for `ExecPosFSM` is not implemented — add WAL rehydration for durable recovery if required.

## Next steps (suggested)

1. Add `asyncio.Lock` to `ExposureGuard` and run related tests.
2. Decide whether to extend `Message` schema or update provenance assumptions.
3. Implement WAL replay for FSM rehydration (Wave 1 safety feature).

---

If you want, I can now annotate the smaller helper modules in-place (e.g., `soft_clip.py`, `idempotent_cancel.py`) or implement the `ExposureGuard` locking change and run unit tests.

<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\README.md
