# Execution Position Code Groups Overview

**Date:** 2025-11-21
**Scope:**
- `apps/reference/domains/execution_position/**`
- `apps/reference/tools/**`
- `apps/reference/utils/**`
- `apps/reference/service/**` (Found to be missing/empty)

## 1. Group Taxonomy

This document groups the codebase into logical clusters to facilitate analysis, deduplication, and understanding of the Execution Position domain.

- **Group A: ExecPos Runtime & State**
  Core logic for the Execution Position domain, including FSMs, runtime management, state tracking, safety guards, and configuration. This is the "heart" of the domain.

- **Group B: ExecPos Domain Adapters & Ports**
  Interfaces and implementations for external communication: exchange adapters, logging adapters, and bridges to other services.

- **Group C: ExecPos-specific Tools & XAI**
  Tools designed specifically for analyzing, debugging, or replaying Execution Position data (e.g., order tracing, TCA, replay harnesses). Includes domain-specific tests found in the source tree.

- **Group D: Generic Tools**
  General-purpose tools found in `apps/reference/tools` that are not strictly tied to Execution Position logic. (None identified in this pass).

- **Group E: Shared Utils**
  Utilities located in `apps/reference/utils` that are used by Execution Position and potentially other domains.

- **Group F: Services / Connectors**
  Service connectors located in `apps/reference/service`. (Directory was not found).

## 2. Groups and Files

### Group A: ExecPos Runtime & State
*Core FSMs, runtime, state management, safety, and config.*

| File Path | Role | Notes |
| :--- | :--- | :--- |
| `apps/reference/domains/execution_position/agg_oco_introspection.py` | Introspection | Logic for inspecting OCO orders |
| `apps/reference/domains/execution_position/brackets_config.py` | Config | Configuration for bracket orders |
| `apps/reference/domains/execution_position/contracts.py` | Contracts | Data classes and interfaces |
| `apps/reference/domains/execution_position/drift_monitor.py` | Monitoring | Monitors state drift |
| `apps/reference/domains/execution_position/exposure_guard.py` | Safety | Guard against excessive exposure |
| `apps/reference/domains/execution_position/fsm_close.py` | FSM | Finite State Machine for closing positions |
| `apps/reference/domains/execution_position/fsm_manage.py` | FSM | Finite State Machine for managing positions |
| `apps/reference/domains/execution_position/fsm_open.py` | FSM | Finite State Machine for opening positions |
| `apps/reference/domains/execution_position/idempotent_cancel.py` | Idempotency | Logic for idempotent cancellations |
| `apps/reference/domains/execution_position/manage_config.py` | Config | Configuration for management logic |
| `apps/reference/domains/execution_position/metrics_aggregator.py` | Metrics | Aggregates runtime metrics |
| `apps/reference/domains/execution_position/metrics_collector.py` | Metrics | Collects runtime metrics |
| `apps/reference/domains/execution_position/order_index.py` | State | Indexing and retrieval of orders |
| `apps/reference/domains/execution_position/runtime_factory.py` | Factory | Creates runtime instances |
| `apps/reference/domains/execution_position/soft_clip.py` | Logic | Logic for soft clipping orders |
| `apps/reference/domains/execution_position/utils.py` | Domain Utils | Local utilities for the domain |
| `apps/reference/domains/execution_position/utils_event_bus.py` | Domain Utils | Event bus utilities |
| `apps/reference/domains/execution_position/watchdog.py` | Monitoring | System watchdog |
| `apps/reference/domains/execution_position/__init__.py` | Package | Package initialization |
| `apps/reference/domains/execution_position/shadow_execpos/async_manager.py` | Async Runtime | Manages async tasks in shadow mode |
| `apps/reference/domains/execution_position/shadow_execpos/gatekeeper.py` | Safety | Gatekeeper for shadow execution |
| `apps/reference/domains/execution_position/shadow_execpos/idempotency.py` | Idempotency | Idempotency logic for shadow mode |
| `apps/reference/domains/execution_position/shadow_execpos/logging_v2.py` | Logging | Structured logging for shadow mode |
| `apps/reference/domains/execution_position/shadow_execpos/price_enricher.py` | Enrichment | Enriches data with price info |
| `apps/reference/domains/execution_position/shadow_execpos/runtime.py` | Core Runtime | Main runtime loop for shadow execution |
| `apps/reference/domains/execution_position/shadow_execpos/types.py` | Types | Type definitions for shadow mode |
| `apps/reference/domains/execution_position/shadow_execpos/wal_writer.py` | Persistence | Write-Ahead Log writer |
| `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` | Monitoring | Watchdog for shadow mode |
| `apps/reference/domains/execution_position/shadow_execpos/__init__.py` | Package | Package initialization |

### Group B: ExecPos Domain Adapters & Ports
*Exchange adapters, logging adapters, and bridges.*

| File Path | Role | Notes |
| :--- | :--- | :--- |
| `apps/reference/domains/execution_position/aurora_log_adapter.py` | Logging Adapter | Adapter for Aurora logging |
| `apps/reference/domains/execution_position/binance_execution_adapter.py` | Exchange Adapter | Binance specific execution logic |
| `apps/reference/domains/execution_position/execution_adapter.py` | Adapter Interface | Base interface for execution adapters |
| `apps/reference/domains/execution_position/simulated_adapter.py` | Simulation Adapter | Adapter for simulated execution |
| `apps/reference/domains/execution_position/shadow_execpos/event_adapter.py` | Event Adapter | Adapts events for shadow processing |
| `apps/reference/domains/execution_position/shadow_execpos/execution_service.py` | Service Adapter | Interface to execution service |
| `apps/reference/domains/execution_position/shadow_execpos/exposure_bridge.py` | Bridge Adapter | Bridge to exposure service |

### Group C: ExecPos-specific Tools & XAI
*Analysis, tracing, replay, and domain-specific tests.*

| File Path | Role | Notes |
| :--- | :--- | :--- |
| `apps/reference/domains/execution_position/test_binance_adapter_methods.py` | Test | Specific test for Binance adapter |
| `apps/reference/domains/execution_position/test_order_index.py` | Test | Specific test for Order Index |
| `apps/reference/domains/execution_position/shadow_execpos/ab_replay.py` | Replay Tool | A/B Replay functionality |
| `apps/reference/tools/order_trace/engine.py` | Trace Tool | Engine for order tracing |
| `apps/reference/tools/order_trace/parsers.py` | Trace Tool | Parsers for order trace data |
| `apps/reference/tools/order_trace/types.py` | Trace Tool | Types for order tracing |
| `apps/reference/tools/order_trace/__init__.py` | Trace Tool | Package initialization |
| `apps/reference/tools/tca_execpos/engine.py` | TCA Tool | Transaction Cost Analysis engine |
| `apps/reference/tools/tca_execpos/loader.py` | TCA Tool | Data loader for TCA |
| `apps/reference/tools/tca_execpos/model.py` | TCA Tool | Data models for TCA |
| `apps/reference/tools/tca_execpos/__init__.py` | TCA Tool | Package initialization |

### Group D: Generic Tools
*General purpose tools.*
*(None identified in the target scope)*

### Group E: Shared Utils
*Utilities shared across domains.*

| File Path | Role | Notes |
| :--- | :--- | :--- |
| `apps/reference/utils/tp_sl_calculator.py` | Logic | Calculator for TP/SL logic |
| `apps/reference/utils/trade_cooldowns.py` | Logic | Logic for trade cooldowns |
| `apps/reference/utils/trading_modes.py` | Logic | Definitions of trading modes |
| `apps/reference/utils/__init__.py` | Package | Package initialization |

### Group F: Services / Connectors
*External service connectors.*
*(Directory `apps/reference/service` not found)*

## 3. Documentation Files
*Documentation found within the domain structure.*

- `apps/reference/domains/execution_position/EXECUTION_POSITION_INVARIANTS.md`
- `apps/reference/domains/execution_position/docs/EP_FSM_EXTRACTION_AUDIT.md`
- `apps/reference/domains/execution_position/docs/EP_RUNTIME_SWITCH_PLAN.md`
- `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`
- `apps/reference/domains/execution_position/docs/FSM_EVENT_MAP.md`

## 4. Notes for Further Analysis

- **Shadow ExecPos Separation:** The `shadow_execpos` subdirectory contains a nearly complete parallel runtime (runtime, watchdog, adapters). This suggests a migration or A/B testing phase. Care should be taken to distinguish "legacy" vs "shadow" vs "target" state.
- **Utils Location:** `apps/reference/domains/execution_position/utils.py` and `utils_event_bus.py` are local to the domain. Check if `utils_event_bus.py` duplicates logic from `vfoundation` or other shared event buses.
- **Tools Specificity:** The tools in `apps/reference/tools` (`order_trace`, `tca_execpos`) are highly specific to Execution Position. They might belong closer to the domain code if they are not used by other domains.
- **Missing Services:** The `apps/reference/service` directory was expected but not found. Service connectors might be located elsewhere or integrated into adapters.
