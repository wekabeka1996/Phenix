# PHASE 2 — Async / Event Causal Chain Audit

Scope: execution_position.zip, phase groups G1/G2/G4/G5/G7/G10.

Static scan coverage:
- 43 / 43 phase files
- 21,795 non-comment LOC scanned
- 78.1% of all Python source LOC in uploaded domain

Focused semantic read:
- approx. 3.1k LOC manually read around task scheduling, event ingress, flow result dispatch, bracket parallel placement, close/cancel, guardian loop, watchdog, sidecar/mediator.
- approx. 14% of phase-scope LOC, focused on highest async-risk surfaces.

Runtime proof:
- none. Findings are static/forensic and require targeted tests or live-log confirmation.

Top findings:
1. P1: FSM cleanup loop catches asyncio.CancelledError and continues while True. Shutdown does not cancel/track this task.
2. P1: DEC flow can be appended to WAL but not executed when async loop is absent; non-BATCH logs error, BATCH path has no equivalent terminal failure.
3. P1: Bracket parallel placement uses gather(return_exceptions=False) then fallback sequential retry with same client IDs; partial success/in-flight sibling can race/double-submit.
4. P2: _submit_async is fire-and-forget and does not retain task/future handles or propagate exceptions.
5. P2: PositionPolicySidecar in enable mode has real action path through CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST -> mediator -> CMD:CLOSE -> async DEC execution. This is bounded, but not recommendation-only.
6. P3: OrderGuardian uses direct asyncio.sleep while most deterministic loops use get_clock().
