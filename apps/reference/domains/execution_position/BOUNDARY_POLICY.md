# ADR-0R: ExecutionPosition Decomposition — Truth-Boundary Policy
# Status: ACTIVE | Date: 2026-04-19 | Package: 0R

## Context

The `execution_position` domain is being incrementally decomposed from the monolithic
`ExecPosFSM` into peer modules (bracket_ownership, fill_ingress_coordinator,
bracket_health, startup_truth_orchestrator, position_policy_mediator).

This ADR establishes the minimum legitimacy rules for that decomposition to prevent
unbounded private-state spread into extracted modules.

---

## Forbidden Patterns (new code MUST NOT introduce these)

1. **Cross-module direct orchestrator access**
   - FORBIDDEN: `self._fsm._startup_truth_orchestrator.X()`
   - FORBIDDEN: `self._fsm._bracket_ownership.X()` (from outside bracket_ownership)
   - FORBIDDEN: `self._fsm._fill_ingress_coordinator.X()` (from outside fill_ingress_coordinator)
   - REASON: Peer modules must not chain through other peer modules via the FSM back-ref.
     Use the FSM-level delegator surface instead.

2. **Direct raw-state dict access on the back-ref**
   - FORBIDDEN: `self._fsm._pending_brackets[...]` (dict mutation from a peer module)
   - FORBIDDEN: `self._fsm._symbol_brackets[sym] = ...` (write from a peer module)
   - FORBIDDEN: `self._fsm._latest_portfolio_state[...]` (write from a peer module)
   - REASON: Peer modules may READ these for snapshot/observability purposes only.
     All WRITES must route through an FSM-sanctioned mutator method.

3. **Undocumented 6A→6B cross-calls**
   - FORBIDDEN: Any new invocation of a future 6B mutating method from within 6A
     without an explicit "0R-3 SEAM" comment referencing the package responsible.

---

## Sanctioned Access Patterns (explicitly allowed for extracted peer modules)

### Allowed reads via back-ref (`self._fsm.X`)
These are stable FSM reader surfaces that peer modules may call:

| Access | Owner | Purpose |
|--------|-------|---------|
| `self._fsm._trade_lifecycle_log_path()` | FSM | Log path for lifecycle records |
| `self._fsm._emit_observability_event()` | FSM | Observability hook |
| `self._fsm._get_async_loop()` | FSM | Async loop access |
| `self._fsm._submit_async()` | FSM | Async task submission |
| `self._fsm._has_active_lifecycle_for_symbol()` | FSM | Lifecycle existence check |
| `self._fsm._manage_state_value()` | FSM | State reader (read-only) |
| `self._fsm._close_state_value()` | FSM | State reader (read-only) |
| `self._fsm._open_strategy_by_symbol` | FSM | Strategy map (read-only snapshot) |
| `self._fsm.manage_flows` | FSM | Flow map (read-only snapshot) |
| `self._fsm.close_flows` | FSM | Flow map (read-only snapshot) |
| `self._fsm._symbol_brackets` | FSM | Bracket map (read-only snapshot) |
| `self._fsm._pending_brackets` | FSM | WAL map (read-only snapshot) |
| `self._fsm.config` | FSM | Config (read-only) |

### Allowed via FSM-level delegators (must go through FSM, not directly to peer)
| FSM delegator | Routes to | Reason |
|---------------|-----------|--------|
| `self._fsm._persist_restore_artifact_snapshot()` | `startup_truth_orchestrator` | 0R: bracket_ownership uses this surface |

### Temporary seam (documented, deferred to 6B)
| Call | Located in | Marked with |
|------|------------|-------------|
| `self._fsm._apply_authoritative_restore_record()` | `startup_truth_orchestrator._run_restore_artifact_authoritative_read` | `# 0R-3 SEAM (6A→6B):` comment |

---

## Deferred Historical Violations (not fixed in 0R — explicitly named)

The following pre-existing accesses in extracted modules are known violations of the
above policy that were present at extraction time. They are DEFERRED, not approved:

| Module | Access | Classification | Deferred to |
|--------|--------|----------------|------------|
| `fill_ingress_coordinator` | `self._fsm._evt_handlers` | Internal registry access | Package 4 reopen or 7 |
| `fill_ingress_coordinator` | `self._fsm._latest_portfolio_state` | Live cache read | Package 4 reopen |
| `fill_ingress_coordinator` | `self._fsm._latest_portfolio_position_amt` | Live cache read | Package 4 reopen |
| `startup_truth_orchestrator` | `self._fsm._portfolio_event_stage_traces` | Internal trace map read | Package 6C |
| `startup_truth_orchestrator` | `self._fsm._portfolio_event_stage_trace_order` | Internal trace order read | Package 6C |
| All modules | `self._fsm._emit_execution_bus_event` | Internal bus dispatch | Future audit |

These are read-only accesses in all cases. None perform writes to FSM private state.
They are listed here so the next package author can see the explicit deferred backlog.

---

## Audit Baseline (grep commands)

Run these to audit compliance at any future point:

```powershell
# 1. All private back-ref accesses in extracted modules
Select-String -Path apps\reference\domains\execution_position\position_policy_mediator.py,apps\reference\domains\execution_position\bracket_ownership.py,apps\reference\domains\execution_position\fill_ingress_coordinator.py,apps\reference\domains\execution_position\bracket_health.py,apps\reference\domains\execution_position\startup_truth_orchestrator.py -Pattern "self\._fsm\._" | Select-Object LineNumber, Line

# 2. Any peer module directly accessing another peer module via FSM back-ref
Select-String -Path apps\reference\domains\execution_position\*.py -Pattern "self\._fsm\.(_(startup_truth_orchestrator|bracket_ownership|fill_ingress_coordinator|bracket_health|position_policy_mediator))" | Where-Object { $_.Filename -ne 'fsm.py' }

# 3. Undocumented 6A→6B seam calls (any _apply_authoritative_restore_record without seam comment)
Select-String -Path apps\reference\domains\execution_position\startup_truth_orchestrator.py -Pattern "_apply_authoritative_restore_record"
```

---

## Enforcement

- This policy is enforced by code review for all new packages (6B, 6C, 7+).
- Any new `self._fsm._X` access in an extracted module that does not appear in the
  Sanctioned Access list above requires an explicit ADR update or a SEAM comment.
- The grep baseline above must be re-run before each new package is closed.
