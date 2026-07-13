# P46-2D-S1 Main-Process Authority Query Bridge

AGENT_IDENTITY:
  agent_name: Codex primary runtime integration
  task_id: P46_2D_S1_MAIN_PROCESS_AUTHORITY_QUERY_BRIDGE
  branch: p46-2d-s1-main-process-authority-bridge-primary-20260713
  worktree: C:\Users\wekab\Music\Phenix-p46-2d-s1-bridge
  started_at: 2026-07-13
  finished_at: 2026-07-13T19:31:43+03:00

## Verdict

`P46_2D_S1_AUTHORITY_BRIDGE_VALIDATED_REPROOF_INCOMPLETE`

## FACTS

- Start SHA: `67c74289496b7cdd113a4087fc0a07d977f30046`; required ancestor `bebaa7d3` was present.
- Existing `tcp://127.0.0.1:7102` JSONL transport now supports bounded typed request/reply on the same listener.
- Strict query and response models cover compatibility, session read model, proposal dry-run, and result retrieval.
- FastAPI production composition creates an IPC client and owns no session authority or accepted-result cache.
- Windows `spawn` proof used distinct main-query and FastAPI PIDs and passed read-model plus accepted dry-run over HTTP/TCP.
- New focused tests: `6 passed`; complete shadow-telemetry domain: `139 passed`.
- Terminal-agent regression: `578 passed`, `13 skipped` (skips not counted as proof).
- Execution effects in the proof: command `0`, FSM `0`, adapter `0`, exchange `0`.
- Cockpit `e3762864` was unchanged: `44 passed`, one known EZE legacy failure; lint and build passed.

## INFERENCES

- The existing IPC is sufficient for a bounded semantic query bridge; a second daemon, broker, or port is unnecessary.
- Correlation, deadlines, runtime generation, and strict schemas materially close the transport-level process boundary.

## ASSUMPTIONS

- The configured read-model runtime ID remains the canonical compatibility identity for edge and main runtime.

## UNKNOWNS

- Baseline `apps/reference/main.py` has no production-composed canonical context/lifecycle projection reader or pure exposure-preview provider. Therefore `RuntimeAuthorityQueryService` cannot be honestly attached to the live composition root yet.
- The complete three-process Cockpit Express approval and main-context-version invalidation repro was not run.
- Provider and exchange runtime were intentionally not called.

## Coordinator Summary

Transport contracts, FastAPI edge composition, fail-closed behavior, and separate-process A-to-B proof are validated. Do not close P46-2D until main composition supplies real context/lifecycle/exposure readers and the unchanged Cockpit client completes the full approval/invalidation repro.
