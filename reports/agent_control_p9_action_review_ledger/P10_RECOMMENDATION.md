# P10 recommendation

Build a read-only completed-review index and scenario calibration report:

- query by symbol, horizon, expected/realized scenario, and review status;
- measure scenario frequency and calibration without model/provider calls;
- define retention/rotation for the append-only ledger;
- add multi-process writer locking only if a second legitimate writer appears;
- keep full reviews referenced outside AgentFeedPacket because only 334 estimated tokens remain.

Do not add model invocation, AgentIntent, order routing, Cockpit mutations, authority, or autonomous loops in P10 without a separate explicit package.
