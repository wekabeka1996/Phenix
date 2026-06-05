# ADR-0R: ExecutionPosition Decomposition - Truth-Boundary Policy
# Status: ACTIVE | Date: 2026-04-19 | Package: 0R

## Context

The `execution_position` domain was incrementally decomposed from the monolithic
`ExecPosFSM` into peer modules while keeping `fsm.py` as the intentional root
orchestration anchor.

Current physical locations for the peer modules named in this ADR:
- `flows/manage/bracket_ownership.py`
- `orchestration/fill_ingress_coordinator.py`
- `flows/manage/bracket_health.py`
- `state/startup_truth_orchestrator.py`
- `sidecar/position_policy_mediator.py`

Old flat import paths may still exist as compatibility stubs. They are not
removed by this ADR or by Phase 9B.

This ADR establishes the minimum legitimacy rules for decomposition so that
extracted modules do not spread unbounded writes into FSM private state.

---

## Forbidden Patterns

1. **Cross-module direct orchestrator access**
   - FORBIDDEN: `self._fsm._startup_truth_orchestrator.X()`
   - FORBIDDEN: `self._fsm._bracket_ownership.X()`
   - FORBIDDEN: `self._fsm._fill_ingress_coordinator.X()`
   - REASON: Peer modules must not chain through other peer modules via the FSM
     back-ref. Use the FSM-level delegator surface instead.

2. **Direct raw-state dict writes on the back-ref**
   - FORBIDDEN: `self._fsm._pending_brackets[...]`
   - FORBIDDEN: `self._fsm._symbol_brackets[sym] = ...`
   - FORBIDDEN: `self._fsm._latest_portfolio_state[...] = ...`
   - REASON: Peer modules may read snapshots for observability purposes, but
     writes must route through an FSM-sanctioned mutator.

3. **Undocumented cross-package seam calls**
   - FORBIDDEN: Any new invocation of a deferred mutating seam without an
     explicit `0R-3 SEAM` comment naming the responsible package.

---

## Sanctioned Access Patterns

### Allowed reads via back-ref (`self._fsm.X`)

| Access | Owner | Purpose |
|--------|-------|---------|
| `self._fsm._trade_lifecycle_log_path()` | FSM | Log path for lifecycle records |
| `self._fsm._emit_observability_event()` | FSM | Observability hook |
| `self._fsm._get_async_loop()` | FSM | Async loop access |
| `self._fsm._submit_async()` | FSM | Async task submission |
| `self._fsm._has_active_lifecycle_for_symbol()` | FSM | Lifecycle existence check |
| `self._fsm._manage_state_value()` | FSM | State reader |
| `self._fsm._close_state_value()` | FSM | State reader |
| `self._fsm._open_strategy_by_symbol` | FSM | Strategy map snapshot |
| `self._fsm.manage_flows` | FSM | Flow map snapshot |
| `self._fsm.close_flows` | FSM | Flow map snapshot |
| `self._fsm._symbol_brackets` | FSM | Bracket map snapshot |
| `self._fsm._pending_brackets` | FSM | WAL map snapshot |
| `self._fsm.config` | FSM | Read-only config |

### Allowed via FSM-level delegators

| FSM delegator | Routes to | Reason |
|---------------|-----------|--------|
| `self._fsm._persist_restore_artifact_snapshot()` | `startup_truth_orchestrator` | Stable FSM-owned seam |

### Temporary seam

| Call | Located in | Marked with |
|------|------------|-------------|
| `self._fsm._apply_authoritative_restore_record()` | `startup_truth_orchestrator._run_restore_artifact_authoritative_read` | `# 0R-3 SEAM` comment |

---

## Deferred Historical Violations

These read-only accesses were present at extraction time and remain deferred:

| Module | Access | Classification | Deferred to |
|--------|--------|----------------|------------|
| `fill_ingress_coordinator` | `self._fsm._evt_handlers` | Internal registry access | Package 4 reopen or 7 |
| `fill_ingress_coordinator` | `self._fsm._latest_portfolio_state` | Live cache read | Package 4 reopen |
| `fill_ingress_coordinator` | `self._fsm._latest_portfolio_position_amt` | Live cache read | Package 4 reopen |
| `startup_truth_orchestrator` | `self._fsm._portfolio_event_stage_traces` | Internal trace map read | Package 6C |
| `startup_truth_orchestrator` | `self._fsm._portfolio_event_stage_trace_order` | Internal trace order read | Package 6C |
| All modules | `self._fsm._emit_execution_bus_event` | Internal bus dispatch | Future audit |

---

## Audit Baseline

```powershell
# 1. All private back-ref accesses in extracted modules
Select-String -Path `
  apps\reference\domains\execution_position\sidecar\position_policy_mediator.py,`
  apps\reference\domains\execution_position\flows\manage\bracket_ownership.py,`
  apps\reference\domains\execution_position\orchestration\fill_ingress_coordinator.py,`
  apps\reference\domains\execution_position\flows\manage\bracket_health.py,`
  apps\reference\domains\execution_position\state\startup_truth_orchestrator.py `
  -Pattern "self\._fsm\._" | Select-Object LineNumber, Line

# 2. Any peer module directly accessing another peer module via FSM back-ref
Get-ChildItem apps\reference\domains\execution_position -Recurse -Filter *.py `
  | Select-String -Pattern "self\._fsm\.(_(startup_truth_orchestrator|bracket_ownership|fill_ingress_coordinator|bracket_health|position_policy_mediator))" `
  | Where-Object { $_.Filename -ne 'fsm.py' }

# 3. Undocumented seam calls
Select-String -Path apps\reference\domains\execution_position\state\startup_truth_orchestrator.py `
  -Pattern "_apply_authoritative_restore_record"
```

---

## Enforcement

- This policy is enforced by code review for decomposition work.
- Any new `self._fsm._X` access in an extracted module that is not listed above
  requires an ADR update or an explicit seam comment.
- The audit baseline should be rerun before closing future structural packages.
