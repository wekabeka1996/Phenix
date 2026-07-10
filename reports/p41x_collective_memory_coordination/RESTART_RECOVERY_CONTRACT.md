# Restart Recovery Contract

`recover_session()`:

1. Discovers and loads the latest deterministic checkpoint, if present.
2. Replays events after the checkpoint sequence.
3. Restores instruction versions, feature histories, portfolio state, leases, cursors, and pending commands.
4. Classifies valid and expired leases; expired leases remain fail-closed unless YAML explicitly permits reacquisition.
5. Classifies `dispatch_started` commands as dispatch-in-doubt.
6. Requires the configured exchange reconciliation hook before declaring dispatch-in-doubt recovery ready.
7. Never invokes the FSM callback or resubmits a command during recovery.
8. Persists an explicit recovery report event.

The two-phase dispatch marker is written before invoking the FSM callback. A retry after an uncertain callback returns the existing command without invoking the callback again.
