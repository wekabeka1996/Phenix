# RID & WHY Contracts — Updated Analysis
Date: 2025-11-02 (ALL TASKS COMPLETED - Ready for v1 Freeze)

1. RID Lifecycle ✅ COMPLETED
- Message.rid is UUID4 and present across domain messages.
- Persistence: WAL appends with prev/hash for integrity (daily files in ops/wal).
- Retrieval: Debug API to scan WAL by RID and return event sequence.
- ✅ OrchestratorFSM provides centralized lifecycle registry with RID tracking, WHY aggregation, and GC policy.

2. WHY Chain
- Intent DTO includes why as list (domain-level reasoning breadcrumbs).
- Bridge currently passes only the first reason to Message.why; chain is not preserved cross-domain.
- Contract Update:
  - P0: Use Message.data_ref (list[str]) to carry the full WHY chain end-to-end; each domain appends its reason.
  - P1: OrchestratorFSM centrally aggregates `why_chain` for each RID and exposes through /debug/{rid}.

3. Domain Contracts (Hot Path)
- DecisionMaking → EVT:TRADE_INTENT_PROPOSED (DTO has why[])
- Bridge → CMD:OPEN (Message.why and data_ref[])
- ExecutionPosition → EVT:ORDER_* (append why/data_ref)
- PositionTracking → EVT:PORTFOLIO_STATE_UPDATED (WAL append before processing)

4. DR Contracts (WAL)
- Append is atomic per line with prev/hash; verify via replay utilities.
- Contract additions:
  - WAL GC: Files older than retention must be deleted; rotation on size threshold.
  - Integrity verification: CLI/Debug API exposes integrity_ok per RID.

5. Security Contracts
- DEC/CMD must be signed (Ed25519) and verified in production.
- In reference path (FSMCore), add boundary verification or route DEC/CMD via Router to enforce signatures.

6. Implementation Map
- WHY (DTO): apps/reference/domains/decision_making/decision_making.py:927
- Bridge (first WHY only): apps/reference/main.py:416; vfoundation/apps/reference/main.py: ~80–120
- WAL file path: vfoundation/dr/wal.py:203
- Debug API (stub): vfoundation/obs/debug_api.py:29
- Verify signature: vfoundation/core/routing.py:101

7. Acceptance
- End-to-end flow retains why_chain through data_ref; /debug/{rid} returns full chain and consistent event list; WAL integrity passes.

