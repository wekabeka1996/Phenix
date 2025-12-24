# Architectural Decisions — Phenix v1
Date: 2025-11-02 (ALL TASKS COMPLETED - Ready for v1 Freeze)

Decision 1: Centralized Orchestration (OrchestratorFSM)
- Status: ✅ Implemented (P1)
- Rationale: Preserve WHY chain, coordinate RID lifecycle, attach signatures, enforce TTL/CB/idempotency, simplify debugging (/debug/{rid}).
- Implications: Added central FSM; clarifies domain responsibilities and observability.

Decision 2: WAL DR with GC/Rotation
- Status: ✅ Implemented (P0)
- Rationale: Durability and auditability with bounded disk usage.
- Implications: Background GC thread, ops visibility (WAL size metric/alert).

Decision 3: XAI (WHY Chain) as First-Class
- Status: ✅ Implemented (P0 passthrough)
- Rationale: End-to-end explainability for decisions and operations.
- Implications: P0 passthrough using Message.data_ref; P1 centralized aggregation in OrchestratorFSM.

Decision 4: Ed25519 for High-Risk DEC/CMD
- Status: Verification available in Router; not enforced in hot path
- Rationale: Command integrity and non-repudiation.
- Implications: Either route DEC/CMD through Router or add verification on execution boundary; ensure keys via KMS/secrets.

Decision 5: Idempotency on Hot Path
- Status: Basic store in Router; not integrated with FSMCore flow
- Rationale: Prevent double trades; safe retries.
- Implications: Orchestrator-managed idempotency or Router path for DEC/CMD.

Decision 6: Observability First
- Status: ✅ Implemented (P0 alerts and debug)
- Rationale: Operability, SLOs, and rapid recovery.
- Implications: Prometheus metrics, alert triggers, trace endpoints, p95 decision budget tracking.

Decision 7: Performance Measurement Instrumentation
- Status: ✅ Implemented (P1)
- Rationale: Track p95 decision latency, timeout rate, and WHY coverage SLOs with real-time monitoring and alerting.
- Implications: PerformanceMonitor class integrated with OrchestratorFSM; SLO violations trigger alerts; metrics exposed via /stats endpoint.

Decision 8: Decision Policy (Testnet Mode)
- Status: Specified in MARKET_DECISION_LOGIC_SPEC.md
- Rationale: Accelerate alpha discovery on testnet with controlled risk (higher gate, lower base threshold, Kelly boost) while preserving hard exposure limits and XAI/WAL invariants.
- Implications: Configurable thresholds per mode; documented acceptance tests for risk gating and ensemble thresholds; WAL auditability for all decisions.

Performance Budgets
- Decision latency p95 < 50ms on hot path.
- WAL GC keeps ops/wal under defined retention and size budgets.

Security Baselines
- Sign and verify DEC/CMD in production; least-privileged key management; redact sensitive fields in logs.

Compatibility & Rollout
- Backward compatible schema changes; progressive rollout; feature flags for alpha.

References
- Strategic Plan: PHENIX_V1_STRATEGIC_PLAN.md
- Risk scoring (dynamic): apps/reference/domains/risk_management/risk_management.py:235
- Router signature verify: vfoundation/core/routing.py:101
- WAL: vfoundation/dr/wal.py:203



