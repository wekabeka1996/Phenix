# PRESERVE_EXECUTION_MATRIX.md
# P37D — Execution/FSM/Logging Preservation Matrix

## What Must Stay Active in agent_arena_testnet mode

The following subsystems MUST remain active because they handle testnet order execution,
position accounting, FSM state machine transitions, event logging, and reconciliation.
None of these are autonomous decision makers — they are infrastructure.

---

## 1. Core FSM / Event Bus

| Subsystem | Files | Status | Rationale |
|-----------|-------|--------|-----------|
| FSM core (`vfoundation.core.FSMCore`) | `strategies/registry.py` L18, `strategies/plugins/aurora_builtin.py` L18 | **PRESERVE** | FSM routes all events; disabling it would stop the entire runtime |
| Event bus (`fsm.emit`, `fsm.listen`) | `main.py` L653, L1083, L1106 | **PRESERVE** | Agent commands arrive via event bus; must stay alive |
| `CMD:PROCESS_STRATEGY` listener | `aurora_builtin.py` L67 | **DISABLE** (when strategy disabled) | Strategies do not register when `enabled=False` |
| `EVT:REGIME_DETECTED` listener | `aurora_builtin.py` L68 | **DISABLE** (when strategy disabled) | Same — not registered when `_DisabledAuroraHandlerWrapper` returned |

---

## 2. Testnet Exchange Adapter

| Subsystem | Config / File | Status | Rationale |
|-----------|--------------|--------|-----------|
| Binance testnet adapter | `adapters/binance_ws_client.py` | **PRESERVE** | Accepts FSM commands for testnet order submission |
| `observe_order_lifecycle` | `adapters/binance_ws_client.py` L29, L35 | **PRESERVE** | Passive lifecycle observation — no order emission |
| `is_live_execution = False` | `agent_bridge/execution_readiness.py` L99 | **ENFORCE** | Must always be False in agent_arena_testnet |
| `no_order_observation_mode` | `agent_bridge/execution_readiness.py` L101 | **ENFORCE** (=True if agent is only observing) | Safely isolates from execution when agent does not yet command |

---

## 3. Order Lifecycle

| Subsystem | Config / File | Status | Rationale |
|-----------|--------------|--------|-----------|
| `order_lifecycle` config | `config/domains/execution_position.py` L920 | **PRESERVE** | Controls bracket orders, lifecycle tracking |
| `_startup_truth_orchestrator` | `agent_bridge/execution_readiness.py` L191 | **PRESERVE** | Manages open-position truth at startup |
| `_bracket_ownership` | `agent_bridge/execution_readiness.py` L196 | **PRESERVE** | Tracks bracket positions per symbol |
| `_idempotent_cancel_helper` | `agent_bridge/execution_readiness.py` L184 | **PRESERVE** | Prevents duplicate order submission |
| Reconciliation config | `config/domains/execution_position.py` L71, L449 | **PRESERVE** | TTL-based in-flight order reconciliation |
| `MDAMRReconciliationConfig` | `config/strategies/md_amr.py` L104 | **PRESERVE** | Md_amr specific reconciliation; irrelevant if md_amr disabled |

---

## 4. Recorder / Data Logger

| Subsystem | File | Status | Rationale |
|-----------|------|--------|-----------|
| `CsvRecorder` | `domains/data_recorder/recorder.py`, `main.py` L622 | **PRESERVE** | Records all FSM events for audit/debugging |
| `csv_recorder.start()` | `main.py` L1122 | **PRESERVE** | Must remain running throughout session |
| `decision_forensics.py` | `decision_making/observability/decision_forensics.py` | **PRESERVE** | Decision audit trails for rejected/blocked signals |
| `reject_wal.py` | `decision_making/intent/reject_wal.py` | **PRESERVE** | Write-ahead log for rejected trade intents |

---

## 5. Position Sync / Portfolio State

| Subsystem | File | Status | Rationale |
|-----------|------|--------|-----------|
| `EVT:PORTFOLIO_STATE_UPDATED` | `aurora_builtin.py` L75 | **PRESERVE** (even when strategy disabled) | Kept at FSM level independently of strategy state |
| `EVT:EXPOSURE_SUMMARY_UPDATED` | `aurora_builtin.py` L77 | **PRESERVE** | Required for exposure gate decisions |
| `EVT:ORDER_STATE_CHANGED` | `aurora_builtin.py` L79 | **PRESERVE** | Required for bracket/lifecycle reconciliation |
| `EVT:TRADE_EXECUTED` | `aurora_builtin.py` L74 | **PRESERVE** | Must sync position state |

---

## 6. Cockpit / API / Session / Event Logs

| Subsystem | File | Status | Rationale |
|-----------|------|--------|-----------|
| `agent_bridge/publication.py` | `publication.py` | **PRESERVE** | Publishes execution readiness snapshots to Cockpit |
| `agent_bridge/execution_readiness.py` | `execution_readiness.py` | **PRESERVE** | Read-only inspector; does not emit orders |
| `shadow_telemetry` domain | `domains/shadow_telemetry/` | **PRESERVE** | Shadow decision ledger for observability |
| `correlation_store` | `agent_bridge/execution_readiness.py` L202 | **PRESERVE** | Trace correlation for session identity |

---

## Summary Table

| Category | PRESERVE count | DISABLE count |
|----------|----------------|---------------|
| FSM / Event bus | 3 | 2 (when strategy disabled) |
| Testnet adapter | 4 | 0 |
| Order lifecycle | 5 | 0 |
| Recorder/Logger | 4 | 0 |
| Position sync | 5 | 0 |
| Cockpit / API | 4 | 0 |
| Strategy plugins | 0 | 5 (aurora, mr, amr, ata, mdamr) |

**Verdict: Disabling strategies at SSOT level is sufficient. All execution/FSM/logging infrastructure is independent and preservable.**
