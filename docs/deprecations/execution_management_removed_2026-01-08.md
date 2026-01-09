# Tombstone: Execution Management Domain

**Removed Date:** 2026-01-08
**Former Path:** `apps/reference/domains/execution_management`
**Reason:** Zombie / Stub domain + misleading documentation.
**Replacement:** `apps/reference/domains/execution_position` (ExecPosFSM) / `AuroraBridge`

## Context
The `execution_management` domain was a non-functional stub containing only logging logic and documentation describing a hypothetical "Event Coordinator" architecture.
Investigation proved it was never wired into `main.py` and performed no runtime actions.
Its intended role (handling `EVT:TRADE_INTENT_PROPOSED`) is fully covered by `execution_position` and `AuroraBridge`.

## Actions Taken
*   Deleted domain folder.
*   Deleted tests (`tests/test_execution_management.py`).
*   Renamed misleading logging handler in `main.py` from `execution_management` to `execution_position` (as it was filtering execution_position logs).

## Commit Reference
(This removal is part of Task EM-ZOMBIE-01)
