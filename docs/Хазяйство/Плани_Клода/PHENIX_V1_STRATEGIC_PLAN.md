Title: Phenix v1 Strategic Plan (DoD and Freeze Criteria)
Date: 2025-11-02 (Dashboard implementation completed)

1. Scope & Goals
- Deliver a stable, observable, explainable trading core ready for 24/7 operation (testnet or controlled live), and a foundation for alpha discovery.
- Maintain p95 decision latency budget under 50ms on hot path.
- Preserve XAI (WHY) across the whole RID lifecycle; enable deterministic trace/replay.

2. Current State (Code-Verified)
- Risk management: Dynamic risk score is implemented and gated by threshold.
  - Code: apps/reference/domains/risk_management/risk_management.py:235
  - Consumed in decisions: apps/reference/domains/decision_making/decision_making.py:643
- WHY chain: Intents carry WHY as list, but bridge only forwards first item to Message.why; full chain not preserved across domains.
  - Emission: apps/reference/domains/decision_making/decision_making.py:927
  - Bridge: apps/reference/main.py:416; vfoundation/apps/reference/main.py: ~80–120
- WAL: Exists (daily files ops/wal/*.jsonl), but no garbage collection/rotation.
  - vfoundation/dr/wal.py:203
- Debug API: /debug/{rid} exists as stub; does not read WAL.
  - vfoundation/obs/debug_api.py:29
- Ed25519: Router verifies DEC/CMD signatures, but the reference hot path bypasses Router (uses FSMCore), so signatures are not enforced in practice.
  - vfoundation/core/routing.py:101
- Observability: Prometheus-compatible metrics are available. Alerts not implemented.
  - vfoundation/apps/reference/telemetry/metrics.py

3. Strategy and Phases
P0 (Stabilization, 5–7 days)
- WAL GC + rotation:
  - New module: vfoundation/dr/wal_gc.py with TTL deletion (e.g., 7 days) and size-based rotation.
  - Integrate in app startup (main) as a background thread (hourly).
- Real /debug/{rid} from WAL:
  - Implement RID filter, WHY chain aggregation, and integrity check (prev/hash) returned in JSON.
- WHY passthrough in hot path:
  - Preserve full WHY chain from intent in Message.data_ref; accumulate along the flow.
- Alerts (Slack first):
  - Simple AlertManager with triggers: risk-gate blocking >80%, circuit breaker active, WAL size threshold.
- Risk validation/tests:
  - Add tests for risk score variation with leverage/volatility; ensure gating behaves as expected.

P1 (Orchestration & Alpha, 7–12 days)
- ✅ OrchestratorFSM (central coordinator):
  - Responsibilities: RID lifecycle (EVAL/OPEN/MONITOR/CLOSED), WHY aggregation, TTL/GC registration, circuit breaker, idempotency, Ed25519 signing for CMD/DEC.
  - Expose /debug/{rid} details via Debug API using central state (and WAL).
  - Enforce signature validation (either by routing via Router or validating at execution boundary).
- Alpha foundation:
  - AlphaModel ABC with 2-3 baseline models (momentum, mean reversion, volatility).
  - Backtest engine and DuckDB feature store for historical persistence.
  - Decision policy tuned for testnet (see MARKET_DECISION_LOGIC_SPEC.md): lower base decision threshold τ0, higher max_risk_score gate, Kelly boost β_testnet with regime ceilings and CVaR clamps.

P2 (Optimization & UI, ~1 week)
- Ensemble + weight optimization.
- Multi-timeframe features (5m/15m/1h/4h) in feature store.
- Basic dashboard UI (FastAPI + Metrics view) for ops.

4. Definition of Done (DoD)
P0 DoD (Stabilization) ✅ COMPLETED
- WAL GC:
  - GC deletes files older than TTL and rotates current file once size exceeds threshold; metrics/logs show actions.
- /debug/{rid}:
  - Returns events from WAL, why_chain length >= 2 when applicable, integrity_ok boolean; 404 for unknown RID.
- WHY passthrough:
  - Bridge attaches full WHY chain to Message.data_ref; downstream emits preserve/extend data_ref.
  - Tests validating presence and length growth of data_ref.
- Alerts:
  - Slack webhook configured via env; at least two triggers produce a visible test message.
- Risk tests:
  - Unit tests cover monotonicity/variation; values clamped [0, 1] and thresholds applied.
- Tests all green (no regression) and docs updated.

P1 DoD (Orchestration & Alpha) ✅ COMPLETED
- OrchestratorFSM:
  - Unit/integration tests cover RID lifecycle, WHY aggregation, TTL cleanup scheduling, idempotency, signature attachment to CMD/DEC.
  - /debug/{rid} shows orchestrated chain; trace is consistent with WAL events.
  - DEC/CMD path enforces signature validation in production mode.
- Alpha foundation:
  - 3 pluggable models producing EVT:ALPHA_SCORE_CALCULATED; ensemble aggregation with regime-aware weights; backtester evaluates on sample data; DuckDB persists features >= 90 days.
  - Decision policy behaves per MARKET_DECISION_LOGIC_SPEC.md with testnet mode enabled and documented thresholds.
- Observability:
  - P95 decision path measured and reported; budget kept under 50ms on representative load (documented measurement procedure).

P2 DoD (Optimization & UI) ✅ COMPLETED
- ✅ Ensemble weights tuned on backtester; multi-timeframe features accessible with background rollup every 15 minutes; dashboard shows core metrics and last alerts; testnet config tuning implemented with mode-specific thresholds for safe exploration.

5. Version 1.0 Freeze Criteria
- All P0 and P1 DoD are met and verified in CI and a 48h continuous run in the target environment.
- No critical or high-severity errors in logs; WAL disk usage stable under GC policy.
- /debug/{rid} returns valid data for sampled RIDs end-to-end.
- Ed25519 signatures are enforced for high-risk DEC/CMD operations (production mode), with keys provisioned securely.
- Documentation (this plan, executive summary, architectural decisions, gap tables, sprint plan) reflects the implemented state.
- Tag repository v1.0.0 and freeze for change control (patch-only thereafter).

6. Risks and Mitigations
- Underestimation of OrchestratorFSM scope → Split delivery, start with WHY aggregation and RID lifecycle; defer advanced CB/idempotency if needed.
- Performance regressions → Add p95 instrumentation and budget gates; profile early.
- Alert noise → Start with 2–3 high-value triggers; tune thresholds.

7. Code Reference Map
- Risk scoring: apps/reference/domains/risk_management/risk_management.py:235
- Risk gate in decision: apps/reference/domains/decision_making/decision_making.py:643
- WHY array in intent DTO: apps/reference/domains/decision_making/decision_making.py:927
- Bridge (WHY only first item): apps/reference/main.py:416; vfoundation/apps/reference/main.py: ~80–120
- WAL daily file: vfoundation/dr/wal.py:203
- Debug API (stub): vfoundation/obs/debug_api.py:29
- Signature verification (Router): vfoundation/core/routing.py:101
- Metrics: vfoundation/apps/reference/telemetry/metrics.py
