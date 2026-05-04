# execution_position - Domain README

> Authoritative package-local documentation for the `execution_position` domain.
> Generated docs under `docs/` are secondary summaries. Phase 9B syncs them to
> the accepted Phase 8 skeleton layout without changing runtime behavior.

## 1. Purpose

`execution_position` is the execution soldier of the trading system. It receives
trade intents from `decision_making`, translates them into exchange orders via
the adapter boundary, tracks lifecycle through open/manage/close flows, manages
brackets, enforces exposure and leverage guardrails, restores truth at startup,
and reconciles orphaned or stale runtime state.

It does not make trading decisions.

## 2. Responsibility Boundary

Owns:
- Order placement validation and normalization
- Order and position lifecycle execution
- Bracket placement, cleanup, and reconciliation
- Exposure, leverage, and execution fail-closed guardrails
- Runtime/state restoration and ledger persistence
- Telemetry, watchdog, and position-policy sidecar integration

Does not own:
- Signal generation
- Portfolio strategy logic
- Exchange wire protocol implementation
- Cross-domain risk policy definition

## 3. Physical Skeleton

### Intentional root anchors

These files are intentionally root-level public API or facade anchors:

| Path | Role |
|------|------|
| `fsm.py` | Root orchestration anchor for `ExecPosFSM`; intentionally not moved |
| `contracts.py` | Root public contract API anchor |
| `reasons.py` | Root canonical reason constant source |
| `utils.py` | Root utility API anchor |
| `__init__.py` | Package marker |

These root anchors are not unfinished migration debt. They are the accepted
final root surface after Phase 8 physical skeleton migration and Phase 9A
guardrails.

### Root shadowing constraints

The following package paths are forbidden because they would shadow accepted
root module import surfaces:

- Do not create `execution_position/contracts/`
- Do not create `execution_position/utils/`

`contract_layer/` remains a separate additive package and must not shadow
`contracts.py`.

### Current semantic subpackages

| Package | Purpose | Example files |
|---------|---------|---------------|
| `contract_layer/` | Additive contract helpers and schemas | `numeric.py`, `trade_executed_contracts.py` |
| `telemetry/` | Observability and metrics | `metrics_collector.py`, `drift_monitor.py` |
| `guardian/` | Guardian and cancel bridges | `order_guardian.py`, `guardian_reconcile_cancel_bridge.py` |
| `state/` | Truth, ledger, restore, startup state | `order_ledger.py`, `startup_truth_orchestrator.py` |
| `guards/` | Exposure, leverage, qty, soft clip | `exposure_guard.py`, `leverage_service.py` |
| `adapters/` | Adapter and scheduling mixins | `adapter_init.py`, `watchdog.py` |
| `sidecar/` | Position policy sidecar and mediator | `position_policy_sidecar.py`, `position_policy_mediator.py` |
| `flows/open/` | Open-flow intake and submission | `fsm_open.py`, `open_executor.py` |
| `flows/manage/` | Manage/bracket lifecycle | `fsm_manage.py`, `bracket_manager.py` |
| `flows/close/` | Close-flow execution and cancel seams | `fsm_close.py`, `close_executor.py` |
| `orchestration/` | Event ingress and routing helpers | `event_handlers.py`, `fill_ingress_coordinator.py` |
| `support/` | Non-shadowing support utilities | `stopprice_validation.py`, `utils_event_bus.py` |

### Compatibility stubs

Flat root compatibility stubs from Phase 8 remain in place as temporary
migration shims. They preserve old import paths while callers transition to the
semantic packages above. Phase 9 does not remove them.

## 4. State Ownership

| State | Owner | Current file |
|-------|-------|--------------|
| Order tracking (runtime) | `OrderIndex` | `state/order_index.py` |
| Position tracking (runtime) | `ManageFlowFSM` | `flows/manage/fsm_manage.py` |
| Exposure state | `ExposureGuard` / `ExposureManager` | `guards/exposure_guard.py`, `guards/exposure_manager.py` |
| Order persistence | `OrderLedger` | `state/order_ledger.py` |

### OrderStatus enums (3 intentional layers)

| Layer | File | Purpose |
|-------|------|---------|
| Domain contract | `contracts.py` | Internal domain lifecycle |
| Binance wire format | `guardian/idempotent_cancel.py` | Exchange-native spelling |
| Persistence | `state/order_ledger.py` | SQLite storage |

These remain intentionally separate. Do not merge them.

## 5. FSM Architecture

```text
ExecPosFSM (root orchestration anchor in fsm.py)
  |- OpenFlowFSM:   flows/open/fsm_open.py
  |- ManageFlowFSM: flows/manage/fsm_manage.py
  `- CloseFlowFSM:  flows/close/fsm_close.py
```

- `fsm.py` remains the root orchestration anchor because its import, patch, and
  source-inspection surface is intentionally frozen.
- The specialized flow implementations live under `flows/open/`,
  `flows/manage/`, and `flows/close/`.

## 6. File Map

### Root anchors
- `fsm.py`
- `contracts.py`
- `reasons.py`
- `utils.py`

### Contract layer
- `contract_layer/numeric.py`
- `contract_layer/reasons.py`
- `contract_layer/typed_results.py`
- `contract_layer/terminal_order_contracts.py`
- `contract_layer/trade_executed_contracts.py`
- `contract_layer/trade_intent_reject_contracts.py`

### Telemetry
- `telemetry/aurora_log_adapter.py`
- `telemetry/metrics_collector.py`
- `telemetry/metrics_aggregator.py`
- `telemetry/health_metrics.py`
- `telemetry/drift_monitor.py`
- `telemetry/intent_boundary_audit.py`

### Guardian and cancel
- `guardian/order_guardian.py`
- `guardian/idempotent_cancel.py`
- `guardian/cancel_submission_adapter.py`
- `guardian/cancel_bridge_utils.py`
- `guardian/guardian_background_orphan_cancel_bridge.py`
- `guardian/guardian_old_bracket_cleanup_bridge.py`
- `guardian/guardian_pre_close_cleanup_bridge.py`
- `guardian/guardian_reconcile_cancel_bridge.py`

### State and restore
- `state/order_index.py`
- `state/order_ledger.py`
- `state/ledger_store_adapter.py`
- `state/restore_artifact.py`
- `state/authoritative_restore_apply.py`
- `state/startup_reconstruction.py`
- `state/startup_truth_orchestrator.py`
- `state/truth_hardening.py`

### Guards
- `guards/exposure_guard.py`
- `guards/exposure_manager.py`
- `guards/soft_clip.py`
- `guards/qty_normalizer.py`
- `guards/leverage_config.py`
- `guards/leverage_service.py`
- `guards/bootstrapping/leverage_bootstrapper.py`

### Adapters
- `adapters/adapter_init.py`
- `adapters/async_scheduling.py`
- `adapters/config_resolver.py`
- `adapters/watchdog.py`

### Sidecar
- `sidecar/position_policy_sidecar.py`
- `sidecar/position_policy_mediator.py`

### Flows
- `flows/open/fsm_open.py`
- `flows/open/trade_intent_open_intake.py`
- `flows/open/intent_router.py`
- `flows/open/entry_manager.py`
- `flows/open/open_executor.py`
- `flows/open/open_submission_adapter.py`
- `flows/open/open_dispatch_adapter.py`
- `flows/manage/fsm_manage.py`
- `flows/manage/bracket_manager.py`
- `flows/manage/bracket_math.py`
- `flows/manage/bracket_health.py`
- `flows/manage/bracket_ownership.py`
- `flows/manage/pending_brackets_wal.py`
- `flows/manage/manage_max_hold_close_bridge.py`
- `flows/close/fsm_close.py`
- `flows/close/close_executor.py`
- `flows/close/close_submission_adapter.py`
- `flows/close/close_producer_bridge.py`
- `flows/close/reconcile_close_cancel_bridge.py`
- `flows/close/tracked_close_teardown_cancel_bridge.py`

### Orchestration and support
- `orchestration/event_handlers.py`
- `orchestration/fill_ingress_coordinator.py`
- `support/stopprice_validation.py`
- `support/utils_event_bus.py`

## 7. Boundary reminders

- Do not import state enums from external domains.
- Do not bypass `ExposureGuard` for order placement.
- Do not create new cancel reason strings; use `reasons.py`.
- Do not merge the layered `OrderStatus` enums.
- Do not add trading decision logic here.
- Do not add autonomous close logic; close remains command-driven.

## 8. Testing

```bash
pytest tests/domains/execution_position -q
pytest tests/order_guardian -q
```

## 9. Contract boundary notes

- `contracts.py` remains the root public contract API anchor.
- `reasons.py` remains the root canonical reason source.
- `contract_layer/` is additive and separate from `contracts.py`.
- Compatibility stubs remain present and documented as temporary shims.

### Timeout contract deprecation

`EVT:LIMIT_ORDER_TIMEOUT` is deprecated and has no live runtime emitter after
the `LimitOrderMonitor` retirement. The active timeout contract is
`EVT:ORDER_TIMEOUT`, emitted by `EntryManager.handle_order_timeout()` through
the `OrderTimeoutWatchdog` callback path with `timeout_type` payload
discrimination. The deprecated export remains in `domain_dict.json` for staged
retirement.

---

Version: 1.2.0 - Phase 9B physical skeleton path sync
