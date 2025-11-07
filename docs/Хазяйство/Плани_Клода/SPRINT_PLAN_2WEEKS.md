# Sprint Plan (2 Weeks) — Phenix v1
Date: 2025-11-02 (ALL TASKS COMPLETED - Ready for v1 Freeze)

Objectives
- P0 stabilization: WAL GC/rotation, real /debug/{rid}, WHY passthrough, alerts, risk validation.
- Start P1: OrchestratorFSM skeleton + AlphaModel ABC.

Week 1 (P0 Focus) ✅ COMPLETED
Day 1–2: WAL GC/Rotation
- Implement vfoundation/dr/wal_gc.py (TTL delete + size rotation); unit tests.
- Integrate into apps/reference/main.py and vfoundation/apps/reference/main.py startup.
- Acceptance: TTL 7d; rotation works; metrics/logs visible.

Day 3: /debug/{rid} from WAL
- Implement RID-based scan in vfoundation/obs/debug_api.py; assemble why_chain and integrity.
- Acceptance: Valid JSON with events/count/why_chain/integrity_ok; returns 404 for unknown.

Day 4: WHY passthrough in hot path
- Update bridge to attach full WHY chain in Message.data_ref; ensure ExecPos preserves.
- Tests: verify data_ref propagation across domains.

Day 5: Alerts (Slack)
- Implement apps/reference/telemetry/{alerts,alert_triggers}.py; add 2–3 triggers.
- Wire triggers in risk/execution.
- Acceptance: Test Slack message via webhook env; silent fallback if not configured.

Day 6: Risk validation & tests
- Add unit tests for risk score variation and gating; review thresholds from config.
- Acceptance: Tests pass; logs show risk score inputs/outputs.

Day 7: P0 Gate Review
- Run full tests; smoke run; review metrics/alerts; document status.

Week 2 (Start P1) ✅ COMPLETED
Day 8–9: OrchestratorFSM Skeleton ✅ COMPLETED
- Create apps/reference/orchestrator/{types.py, orchestrator_fsm.py}; register listeners.
- Implement RID lifecycle and WHY aggregation first; add tests.

Day 10–11: AlphaModel ABC + Baseline Models ✅ COMPLETED
- Create alpha_search/alpha_model.py and 3 baseline models (momentum, mean reversion, volatility).
- Integrate with DecisionMaking for EVT:ALPHA_SCORE_CALCULATED emission.
- Comprehensive tests added.

Day 12–14: Performance Measurement + Integration ✅ COMPLETED
- Implement PerformanceMonitor with SLO tracking and alerting.
- Wire OrchestratorFSM into main flow.
- Update docs and finalize P1 milestones.

Success Criteria ✅ COMPLETED
- P0 DoD items completed; Orchestrator skeleton exists; AlphaModel ABC ready.

