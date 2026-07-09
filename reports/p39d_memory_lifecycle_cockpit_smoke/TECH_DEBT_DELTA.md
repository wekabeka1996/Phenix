# Tech Debt Delta

FACTS:
- RETIRED: Trading-session memory was not callable from Cockpit session/event lifecycle.
- CONVERTED_TO_RUNTIME_CHECK: Missing agent/session identity now returns API errors and is covered by tests.
- MITIGATED: Rationale and FSM decision events now produce append-only memory records.
- DEFERRED_WITH_REASON: Hot-reload scheduler loop remains deferred because P39D only connects instruction ACK memory lifecycle.
- DEFERRED_WITH_REASON: Real exchange testnet execution proof remains deferred because this task forbids exchange execution changes.

INFERENCES:
- This narrows P39 runtime debt to scheduler wiring, full FSM runtime handoff, and long-running session proof.

ASSUMPTIONS:
- Memory lifecycle API routes are acceptable interim integration points for MVP smoke.

UNKNOWNS:
- Whether the future 4-hour runner will call the same endpoints or import `AgentMemoryLifecycle` directly.
