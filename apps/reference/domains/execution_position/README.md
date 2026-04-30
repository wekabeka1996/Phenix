# execution_position — Domain README

> **Authoritative domain documentation.** For auto-generated docs see `docs/` (may be stale).

## 1. Purpose

`execution_position` is the **execution soldier** of the trading system. It receives trade intents from `decision_making`, translates them into exchange orders via `BinanceAdapter`, tracks order/position lifecycle through a 3-FSM system, manages bracket orders (SL/TP), handles exposure tracking, reconciliation, and orphan cleanup.

**It does NOT make trading decisions.**

## 2. Responsibility Boundary

Owns:
- Order placement validation and normalization (qty, price, notional)
- Order lifecycle FSM (open → manage → close)
- Bracket order management (SL/TP placement, adjustment, cancel)
- Exposure tracking and fail-closed guarding
- Order timeout / stale detection (Watchdog)
- Orphan order cleanup and reconciliation (OrderGuardian)
- Leverage configuration and bootstrapping

Does NOT own:
- Trade signal generation (→ decision_making)
- Risk assessment (→ risk_management)
- Exchange adapter wire protocol (→ adapters/binance_adapter)
- Position tracking aggregation (→ position_tracking)

## 3. State Ownership

| State | Owner | File |
|-------|-------|------|
| Order tracking (runtime) | `OrderIndex` | `order_index.py` |
| Position tracking (runtime) | `ManageFlowFSM` | `fsm_manage.py` |
| Exposure state | `ExposureGuard` / `ExposureManager` | `exposure_guard.py`, `exposure_manager.py` |
| Order persistence | `OrderLedger` | `infra/order_ledger.py` |

### OrderStatus Enums (3 intentional layers)

| Layer | File | Members | Purpose |
|-------|------|---------|---------|
| Domain contract | `contracts.py` | PENDING, PLACED, PARTIAL, FILLED, CANCELLED, REJECTED, EXPIRED | Internal domain lifecycle |
| Binance wire format | `idempotent_cancel.py` | NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED | Exchange-native spelling |
| Persistence | `infra/order_ledger.py` | PENDING, ACTIVE, CANCELLED, FILLED, REJECTED, EXPIRED, UNKNOWN | SQLite storage |

These are **intentionally separate** — each models a different layer's view of order state. Do not merge.

## 4. FSM Architecture

```
ExecPosFSM (orchestrator)
  ├── OpenFlowFSM:   IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
  ├── ManageFlowFSM: FLAT → OPENED → TRACKING → BRACKETS_PENDING → BRACKETS_PLACED → ...
  └── CloseFlowFSM:  FLAT → OPENED → CLOSE_COND → EMIT_DEC_CLOSE → DONE
```

- `ExecPosFSM` subscribes to bus events and routes to sub-FSMs
- `OpenFlowFSM` validates CMD:OPEN and emits DEC:OPEN
- `ManageFlowFSM` tracks positions, places/adjusts brackets, handles exits
- `CloseFlowFSM` processes CMD:CLOSE (soldier pattern — only explicit close)

## 5. Events

### Consumed (9)

| Event | Source |
|-------|--------|
| `EVT:TRADE_INTENT_PROPOSED` | decision_making |
| `EVT:TRADE_INTENT_REJECTED` | decision_making |
| `EVT:PORTFOLIO_STATE_UPDATED` | position_tracking |
| `EVT:FEATURES_CALCULATED` | feature_engineering |
| `EVT:REGIME_DETECTED` | regime_detector |
| `EVT:ORDER_ACK` | adapter |
| `EVT:ORDER_FILL` | adapter |
| `EVT:SYMBOL_TIDY` | self |
| `CMD:CLOSE` | decision_making |

### Emitted (31 registered in verb_registry)

See `domain_dict.json` for the full export list. Key events:
- `DEC:OPEN`, `DEC:CLOSE` — adapter commands
- `DEC:PLACE_ORDER`, `DEC:CANCEL_ORDER`, `DEC:ADJUST`, `DEC:BATCH` — bracket management
- `EVT:EXECUTION_GUARD_BLOCKED`, `EVT:EXECUTION_DIVERGENCE_DETECTED` — observability
- `EVT:EXECUTION_CLOSE_RECONCILED`, `EVT:EXECUTION_TIDY_PERFORMED` — reconciliation
- `ERR:OPEN`, `ERR:EXECUTION_FAILED`, `ERR:FATAL_CONFIG_MISMATCH` — errors

## 6. File Map

### FSM Orchestration (4 files, ~4,651 LOC)
| File | Role |
|------|------|
| `fsm.py` | Main orchestrator (~2,056 LOC) |
| `fsm_open.py` | Open flow FSM (589 LOC) |
| `fsm_manage.py` | Manage flow FSM (1,826 LOC) |
| `fsm_close.py` | Close flow FSM (180 LOC) |

### Guards & Managers (7 files)
| File | Role |
|------|------|
| `exposure_guard.py` | Fail-closed exposure guard (1,067 LOC) |
| `exposure_manager.py` | Exposure tracking and reserve management |
| `order_guardian.py` | Orphan cleanup and reconciliation (1,433 LOC) |
| `bracket_manager.py` | SL/TP bracket placement |
| `watchdog.py` | Order timeout detection |
| `entry_manager.py` | Entry lifecycle management |

### Execution (3 files)
| File | Role |
|------|------|
| `open_executor.py` | Order placement execution |
| `close_executor.py` | Position close execution |
| `intent_router.py` | Route intents to CMD:OPEN/CMD:CLOSE |

### Utilities (8 files)
| File | Role |
|------|------|
| `contracts.py` | Domain enums, Pydantic models, validation |
| `reasons.py` | Cancel/reject reason constants (SSOT) |
| `utils.py` | Shared utilities (client_order_id gen, rounding) |
| `qty_normalizer.py` | Strict qty/price normalization |
| `idempotent_cancel.py` | Idempotent cancel with -2011 absorption |
| `order_index.py` | Order tracking index (SSOT) |
| `soft_clip.py` | Soft limit / position clipping engine |
| `stopprice_validation.py` | Stop price validation |

### Infrastructure (3 files)
| File | Role |
|------|------|
| `infra/order_ledger.py` | SQLite order persistence |
| `infra/ledger_store_adapter.py` | Ledger store adapter |
| `pending_brackets_wal.py` | WAL for bracket state recovery |

### Observability (5 files)
| File | Role |
|------|------|
| `aurora_log_adapter.py` | Structured trade logging |
| `metrics_collector.py` | Metrics collection |
| `metrics_aggregator.py` | Metrics aggregation |
| `drift_monitor.py` | Drift detection |
| `health_metrics.py` | Health metrics mixin |

### Config & Bootstrap (5 files)
| File | Role |
|------|------|
| `config_resolver.py` | Config resolution mixin |
| `leverage_config.py` | Leverage configuration |
| `leverage_service.py` | Leverage verification |
| `bootstrapping/leverage_bootstrapper.py` | Leverage bootstrap at startup |
| `adapter_init.py` | Adapter initialization mixin |

### Other (3 files)
| File | Role |
|------|------|
| `async_scheduling.py` | Async scheduling mixin |
| `utils_event_bus.py` | Local event bus utility |
| `event_handlers.py` | Event handler dispatch (727 LOC) |

## 7. Fail-Closed Rules

- **Missing config → crash** (no silent fallback to global config)
- **Exposure breach → deny** (ExposureGuard blocks CMD:OPEN)
- **Unknown order status → safe** (IdempotentCancel treats -2011 as success)
- **Stale order → cancel** (Watchdog detects timeout → cancel)
- **Close flow → soldier** (only executes explicit CMD:CLOSE, no autonomous close)
- **Max-hold → DEC:CLOSE** (ManageFlowFSM emits DEC:CLOSE on timeout)

## 8. Cancel/Timeout/Reconcile Policy

| Scenario | Handler | Reason Code |
|----------|---------|-------------|
| Fill TTL expired | Watchdog | `CANCEL_TTL_EXPIRED` |
| Signal superseded | EntryManager | `CANCEL_SUPERSEDED` |
| Regime change | EntryManager | `CANCEL_STALE_REGIME` |
| Panic killswitch | FSM | `CANCEL_PANIC_KILL` |
| Orphan brackets | OrderGuardian | `EVT:EXECUTION_TIDY_PERFORMED` |
| Tidy triggered | OrderGuardian | `EVT:SYMBOL_TIDY` |
| Close reconciled | OrderGuardian | `EVT:EXECUTION_CLOSE_RECONCILED` |

## 9. Forbidden Patterns

- Do NOT import state enums from external domains
- Do NOT bypass ExposureGuard for order placement
- Do NOT create new cancel reason strings — use `reasons.py`
- Do NOT merge the 3 OrderStatus enums
- Do NOT add trading decision logic — this domain executes, not decides
- Do NOT add autonomous close logic — CloseFlow is a soldier (explicit CMD:CLOSE only)

## 10. Testing

```bash
pytest tests/domains/execution_position/ -v        # 44 focused tests (364 functions)
pytest tests/order_guardian/ -v                     # 4 guardian tests (37 functions)
pytest tests/integration/ -k "execpos or ep01" -v   # Integration tests
```

**Total test surface:** ~147 files, ~1,192 test functions across all directories.

## 11. Cross-Domain Coupling

| Direction | What | Why |
|-----------|------|-----|
| EP → shared | `NormalizedRejectReasons` via `shared/types.py` | Leverage reject codes (NRR-020..024) |
| EP → Adapter | `BinanceAdapter` import (7 files) | Exchange API calls |
| EP → vfoundation | Message, WAL, emit_compat | Infrastructure |
| DM → EP | Event-based only (CMD:OPEN, CMD:CLOSE) | Clean event-driven |

## 12. Contract Boundary Policy

### Owned contracts (registry owner = execution_position)
All `DEC:*`, `EVT:EXECUTION_*`, `EVT:EXIT_MATCH_*`, `EVT:EXPOSURE_*`, `EVT:ORDER_*`,
`EVT:LIMIT_ORDER_TIMEOUT` *(deprecated — no live emitter since J2; see note below)*,
`EVT:MANAGE_SKIPPED`, `EVT:PENDING_BRACKETS_*`, `EVT:SYMBOL_TIDY`,
`ERR:OPEN`, `ERR:EXECUTION_FAILED`, `ERR:FATAL_CONFIG_MISMATCH`.

> **Deprecation (J4, 2026-04-30):** `EVT:LIMIT_ORDER_TIMEOUT` has no live runtime emitter
> after `LimitOrderMonitor` was retired in J2. The active timeout event is
> **`EVT:ORDER_TIMEOUT`**, emitted by `EntryManager.handle_order_timeout()` via
> `OrderTimeoutWatchdog` callback. `EVT:ORDER_TIMEOUT` carries `timeout_type`
> (ACK_TIMEOUT / FILL_TIMEOUT) as payload discriminator. The export is retained in
> `domain_dict.json` for staged retirement.

### Sanctioned co-emission (EP emits, another domain owns)
| Contract | Owner | EP emitter | Why EP co-emits |
|----------|-------|-----------|-----------------|
| `EVT:TRADE_INTENT_REJECTED` | decision_making | `intent_router.py` | Intent fails at execution boundary (exposure guard, leverage) |
| `EVT:TRADE_EXECUTED` | position_tracking | `watchdog.py` | REST polling fallback when WS misses fills |

### NRR dependency
`NormalizedRejectReasons` is imported via `apps.reference.shared.types` (re-export facade).
The canonical definition lives in `decision_making/normalized_reject_reasons.py`.
EP uses 5 NRR codes: NRR-020 through NRR-024 (leverage/margin verification failures).

### Forbidden boundary patterns
- Do NOT import directly from `decision_making.*` — use `shared/types.py` for cross-domain types
- Do NOT emit events owned by other domains without explicit `co_emitters` in verb_registry
- Do NOT define local NRR codes — all NRR codes live in canonical `NormalizedRejectReasons`
- Do NOT create parallel contract registries — all contracts in `verb_registry_v1.yaml`

## 13. Known Structural Debt

- Triple OrderStatus enum (documented, not mergeable without heavy blast radius)
- 3 ghost pycache packages cleaned in 2026-03-14 audit (aggregator_oco, observability, shadow_execpos)
- `fsm.py` at 2,056 LOC is large but cohesive as orchestrator
- Heavy Binance adapter coupling (7 files) — acceptable for current single-exchange architecture

---
*Version: 1.1.0 — Updated 2026-03-14 (EP-CONTRACT-BOUNDARY)*
