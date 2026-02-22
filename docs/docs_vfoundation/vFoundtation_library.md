
---

# `vfoundation` — Library Blueprint

**Version:** 1.0
**Status:** Foundation Blueprint
**Description:** Foundational library for building production-ready FSM-based LLM agents with contracts, observability, XAI, Disaster Recovery, and governance.

---

## 0. Overview

Modern AI-driven systems (including LLM-agents) require **strict contracts**, **deterministic state management**, **explainability**, and **fault tolerance**.

`vfoundation` is a **contract-first framework** that provides:
- **FSM Core** — finite state machine infrastructure
- **XAI Layer** — explainability storage and audit
- **Disaster Recovery** — WAL, snapshots, replay
- **Governance** — dictionaries, CLI, RFC workflow

> Any contradiction between code and this document is resolved in favor of this document.

---

## 1. Design Principles

### 1.1 Core Constraints

- **Contracts are the source of truth:** dictionaries define the verb-space, not code.
- **Runtime ≠ SSOT:** CI controls drift.
- **LLM-Friendly Modularity:** modules ≤ 500 LOC, isolated context windows.
- **No cross-domain imports** without a contract record (e.g., `risk.py` must not import `exec.py` directly).

### 1.2 Message Protocol

All inter-module communication uses **FSM Messages**:

```json
{
  "op": "ASK",
  "verb": "EVAL_RISK",
  "src": "sizer",
  "dst": "risk",
  "rid": "uuid4",
  "pld": {},
  "why_chain": []
}
```

Fields: `op` (ASK, DEC, EVT, CMD, ERR), `verb`, `pld` (payload), `why_chain`, `trace_id`.

### 1.3 Invariants

1. **Additive-Only Evolution:** no breaking changes, only additions.
2. **Contract > Code:** contracts always override implementation.
3. **Fail-Closed:** on timeout/CB-open → `DENY`.
4. **Explain Everything:** every message must carry `why`.
5. **Graceful Degradation:** partial failure must not cascade.
6. **Freeze Discipline:** breaking changes require RFC approval.
7. **LLM-Friendly Modularity:** ≤ 500 LOC per module, isolated context.

---

## 2. Architecture

### 2.1 High-Level Topology

```
┌─────────────────────────────────────────────────────┐
│                  Meta-FSM (cold/warm)                │
└───────────────────────┬─────────────────────────────┘
                        │
     ┌──────────────────┴──────────────────┐
     │                                     │
┌────┴────────────┐               ┌────────┴────────┐
│ Domain: Risk &  │               │ Domain: Exec &  │
│ Strategy        │               │ Position        │
│  [risk_mgr]     │               │  [exec_gw]      │
└─────────────────┘               └─────────────────┘
```

### 2.2 Component Summary

| Component                       | Description                                          | Path          |
| ------------------------------- | ---------------------------------------------------- | ------------- |
| **FSM Core**                    | In-proc async FSM engine                             | hot-path      |
| **Domain FSMs**                 | Per-domain FSMs (risk, exec, data, audit)            | hot-path      |
| **Meta-FSM**                    | Cross-domain coordination                            | warm/cold     |
| **Adapters**                    | Legacy integration layer                             | configurable  |
| **Schemas / Dictionaries**      | JSON/YAML contract definitions                       | SSOT          |
| **Entropy / Topology Monitors** | Drift and anomaly detection                          | cold-path     |
| **WAL / Snapshots**             | Write-Ahead Logging for DR                           | persistent    |
| **CLI / SDK**                   | Developer tooling (`vfound`)                         | dev/CI        |

---

## 3. Build Phases

---

### Phase 1 — Core Foundation & FSM Infrastructure

**Goal:** Establish the foundational FSM runtime.

**Deliverables:**
- `FSMCore` (in-proc, async, Redis-backed)
- Canonical `FSMMessage` schema (see §1.2)
- TTL + retry_policies + circuit_breaker
- `global_dict.yaml` — defines allowed verbs/ops

**Capabilities:**
- `emit / subscribe / route`
- Schema validation (Pydantic / JSON Schema)
- Distributed tracing (`trace_id`, `rid`)
- WAL integration (write-path)

**Exit Criteria:**
- 10 000 events/s, p95 latency ≤ 10 ms
- TTL and retry logic verified
- Contract tests pass

---

### Phase 2 — Legacy Integration Layer

**Goal:** Safely wrap existing code with FSM contracts.

**Deliverables:**
- `importlib`-hook for call interception
- `@fsm_call(op, verb)` decorator
- Migration modes: `shadow → audit → adapter → hybrid → pure-FSM`
- Import call-graph analysis (`vfound analyze imports`)

**Capabilities:**
- Emit `EVT:LEGACY_CALL` for all legacy calls
- Full idempotency tracking
- Route via FSM when adapter is ready
- `audit_mode` → XAI + WAL

**Exit Criteria:**
- All modes functional
- Latency overhead < 10 ms
- Domain Dictionaries auto-generated from import graph

---

### Phase 3 — Domain FSMs & Meta-FSM

**Goal:** Deploy per-domain FSMs and cross-domain coordination.

**Deliverables:**
- Domain FSMs (risk, exec, audit, data) on `FSMCore`
- Meta-FSM for cross-domain routing
- `domain_dict.json` per domain:

```json
{
  "domain_name": "risk_strategy",
  "modules": ["risk_manager", "sizer"],
  "imports": ["EVT:FEATURE_CALC"],
  "exports": ["DEC:EVAL_TRADE", "CMD:OPEN_POSITION"]
}
```

**Capabilities:**
- Hot-path intra-domain transitions
- Meta-FSM inter-domain routing
- TTL profiles: `critical / normal / background`
- Per-domain audit/logging

**Exit Criteria:**
- All domain contracts verified
- Meta-FSM handles `EVT:REGIME_SHIFT` correctly
- Latency and scalability targets met

---

### Phase 4 — Observability, Entropy, Topology, XAI

**Goal:** Full system visibility and explainability.

**Deliverables:**
- `EntropyMonitor` — detects distribution drift, emits `EVT:ENTROPY_SPIKE`
- `TopologyAuditor` — detects dependency drift, emits `EVT:TOPOLOGY_DRIFT_DETECTED`
- `trace_id = rid`; `/debug/{rid}` API
- `why` (hot-path, ≤ 80 chars) + `why_chain` (audit-path)

**Capabilities:**
- Online entropy scoring
- Trigger alerts on anomalies
- XAI store: JSONL + OpenTelemetry export
- `/metrics`, `/statdump` endpoints

**Exit Criteria:**
- why_chain coverage ≥ 95%
- End-to-end trace verifiable per `rid`
- Entropy alerts functional

---

### Phase 5 — Resilience & Recovery (DR Layer)

**Goal:** Production-grade fault tolerance and state recovery.

**Deliverables:**
- Write-Ahead Log (WAL) with Merkle-chain hash verification
- FSM state snapshots
- `replay_from_wal()` with deduplication per `rid`
- `circuit_breaker` with `half_open → closed` recovery
- Per-event `retry_policies` and TTL profiles

**Capabilities:**
- RPO < 1 min, RTO < 5 min
- Graceful degradation: `reduce_only` on partial failure
- Fail-closed on any unresolvable state
- Immutable audit log with `sig` verification for CMD/DEC

**Exit Criteria:**
- DR replay verified end-to-end
- CB transitions tested under chaos
- Compliance with Constitution FSM v2.2 §8

---

### Phase 6 — Governance, CLI, Schemas

**Goal:** Prevent schema bloat and maintain contract discipline.

**Deliverables:**
- `vfound` CLI: `analyze`, `lint`, `adapter gen`, `simulate`, `migrate`
- Schema-governance: versioning (`_v1`, `_v2`), deprecation windows ≥ 2 releases
- RFC workflow for new verbs/events
- `auto_test_generator` + `contract_validator` for LLM pipeline

**Capabilities:**
- CLI validates all contracts
- Governance changelog (RFCs, diffs)
- Schema linting in CI
- Additive-only migration (`v1 → v2`)

**Exit Criteria:**
- 0 breaking changes without RFC approval
- All verbs additive-only
- CLI coverage ≥ 95%

---

### Phase 7 — Security & Compliance

**Goal:** Cryptographic safety for all critical FSM operations.

**Deliverables:**
- Signatures for `CMD/*` / `DEC/*` (Ed25519 / KMS)
- Immutable WAL (WORM storage)
- PII redaction/hashing in logs and traces
- Sandbox for legacy adapters
- Policy engine for verb-level rate limits

**Capabilities:**
- All CMD/DEC verified before FSM delivery
- Immutable audit trail
- RBAC/ABAC for `/debug`, `/replay`, `/metrics`
- Secret management via KMS only

**Exit Criteria:**
- 100% CMD/DEC signed
- 0 unsigned deliveries to FSM
- WAL integrity verified via Merkle-root

---

### Phase 8 — Validation & Certification

**Goal:** Prove system readiness for production via comprehensive testing.

**Deliverables:**
- Contract tests per verb
- 2-domain end-to-end flows (EVAL → RISK → EXEC)
- Chaos tests: TIMEOUT, DELAY, NETWORK LOSS
- DR tests: replay from WAL
- Performance tests: p95, throughput

**Capabilities:**
- Test suite: `tests/foundation/`
- Coverage ≥ 95%, ERR rate ≤ 1%
- Metrics summary report

**Exit Criteria — 9 Certification Dimensions:**

1. Reliability
2. Recoverability
3. Traceability
4. Security
5. Modularity
6. Predictability
7. Scalability
8. XAI coverage ≥ 95%
9. LLM integration stable

When all 9 pass → `vfoundation` is **ready for production**.

---

## 4. Phase Summary Table

| Phase              | Milestone                   | Key Deliverables                         | Exit Criteria                         |
| ------------------ | --------------------------- | ---------------------------------------- | ------------------------------------- |
| Core FSM           | FSM engine live             | routing, schema validation               | 10k ev/s, p95 ≤ 10 ms                |
| Legacy Integration | audit mode active           | shadow, audit, adapter modes             | overhead < 10 ms                      |
| Domains            | all domains deployed        | domain FSMs, TTL profiles                | meta-FSM routing verified             |
| Observability      | monitoring live             | Entropy/Topo monitors, debug API         | why ≥ 95%, trace end-to-end           |
| DR & Resilience    | WAL/snapshot live           | replay, CB, retry policies               | RTO ≤ 5 min, RPO ≤ 1 min             |
| Governance & CLI   | CI enforced                 | RFC workflow, lint, migrate              | CI blocks breaking changes            |
| Security           | signatures + sandbox live   | audit trails, redaction                  | 100% CMD/DEC signed                   |
| Validation         | certification complete      | chaos, contract, DR tests                | all 9 DoD dimensions pass             |

---

## 5. Definition of Done

> **`vfoundation` is production-ready when:**

1. FSM processes 10 000 events/s with p95 ≤ 10 ms.
2. All external interfaces are covered by contract tests.
3. All contracts verified (100% contract coverage).
4. State recovery from WAL completes within 5 min (RTO).
5. Why-coverage ≥ 95%; all traces are end-to-end traceable.
6. Security signatures active on all CMD/DEC.
7. Governance RFC workflow enforced; all verbs additive-only.
8. LLM pipeline auto-tests pass ≥ 90%.
9. All 9 certification dimensions verified.
10. DR-replay and chaos tests confirm fail-closed behavior.

---

## 6. Extensions & Roadmap

- **Aurora:** FSM layer, DR, XAI integrated into the main trading system.
- **LLM-agents:** contract-first generation, auto-tests, freeze-discipline enforced.
- **Verticals:** fintech, healthcare, robotics, IoT — any domain requiring deterministic event-driven safety.

---

# Blueprint v1.1 — Additive Extensions to `vfoundation`

## A) Core Principles (unchanged)

- **Migration modes:** Shadow → Audit → Adapter → Hybrid → Pure-FSM
- **Contract-first:** dictionary = SSOT; code always secondary
- **Fail-closed + Safety-veto:** TTL/CB, deny-by-default
- **DR/XAI/Observability:** WAL + snapshots, why_chain, trace_id
- **Governance/CLI:** linting, RFC, auto-tests for LLM

---

## B) New Features in v1.1

### B1. CLI Migration Tooling

- **Goal:** Reduce migration friction to near-zero.
- **Deliverable:** `vfound migrate --domain <d> --from <files>` → generates adapters (`@fsm_call`), Domain Dictionary, contract stubs.
- **Input:** `vfound analyze imports` output.
- **Validation:** verb mapping correctness; `data_ref` for large payloads.
- **Exit:** p95 overhead ≤ 10 ms; 100% contract-tests green post-migration.

### B2. LLM Pipeline Integration

- **Goal:** Safe LLM-assisted code generation within contract boundaries.
- **Deliverable:** `contract_validator` (pre-gen) + `auto_test_generator` (post-gen); auto RFC draft from call-graph.
- **Entry:** LLM cannot generate unknown/deprecated verbs.
- **Validation:** no hallucinated verbs; tests cover valid/invalid/TTL/idempotency.
- **Exit:** simple flows pass ≥ 90%; complex ≥ 70%; regression ≤ 10%/30% respectively.

### B3. DR for Legacy Adapters (Replayable)

- **Goal:** Legacy calls are recoverable from WAL.
- **Deliverable:** WAL records `EVT:LEGACY_CALL` with `rid`; adapters enforce idempotency.
- **Entry:** `audit` mode required.
- **Validation:** `vfound replay legacy <rid>`; DENY on non-idempotent unsafe replay.
- **Exit:** RTO ≤ 5 min, RPO ≤ 1 min for all legacy-wrapped domains.

### B4. Observability Diff (Legacy vs FSM)

- **Goal:** Quantify the gap between legacy and FSM call paths.
- **Deliverable:** `/debug/{rid}` shows before/after diff (latency, entropy delta, centrality delta).
- **Entry:** available from `adapter` mode onward.
- **Validation:** semantic diff in CI; latency/ERR comparison per mode.
- **Exit:** measurable improvement: X% latency reduction, Y% error reduction vs baseline.

### B5. Security Signatures for Legacy

- **Goal:** Legacy paths are not a signature bypass vector.
- **Deliverable:** mandatory `sig` on `DEC/*` from adapters (Ed25519/KMS); args redacted in WAL.
- **Entry:** enforced in hybrid mode.
- **Validation:** FSM rejects unsigned DEC; PII masked in all logs.
- **Exit:** 100% CMD/DEC signed; 0 unsigned deliveries.

### B6. DoD Extension — CLI Coverage

- **Goal:** No undocumented or untested CLI paths.
- **Deliverable:** CLI coverage report for all commands (analyze/lint/migrate/trace/replay).
- **Entry:** CI gate.
- **Validation:** `vfound report cli-coverage`.
- **Exit:** ≥ 95% CLI workflow coverage.

---

## C) Risk Register

| Risk                   | Trigger              | Mitigation                                        | Exit Threshold                           |
| ---------------------- | -------------------- | ------------------------------------------------- | ---------------------------------------- |
| Latency regression     | p95 > 10 ms          | in-proc queue, CB, capped TTL                     | p95 ≤ 10 ms (hot)                       |
| Schema bloat           | > N fields/nesting   | schema-budget, versioning, shared `$ref`          | warn at 80%, block at 100%              |
| Non-idempotent legacy  | ERR on replay        | force `rid`; DENY + advice                        | 0 non-replayable adapters               |
| LLM hallucination      | fake verbs generated | pre-gen validator, post-gen tests                 | simple ≥ 90%, complex ≥ 70% pass        |
| WAL I/O saturation     | write stall          | async batching, compression, Merkle-root          | WAL I/O < 70% capacity                 |
| Unsigned CMD/DEC       | missing `sig` field  | mandatory sig, RBAC on debug                      | 100% signed CMD/DEC                     |

---

## D) Architecture Diagrams

### D1. Legacy Integration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   Meta-FSM (cold/warm)                          │
│          ALERT, RECONCILE, WHY_EXPLAIN, MODE CMD                │
└─────────────────┬──────────────────────────┬────────────────────┘
                  │                          │
┌─────────────────┴──────────┐  ┌────────────┴────────────────────┐
│ Domain FSM: risk_strategy  │  │ Domain FSM: execution           │
│ (hot: EVAL, DEC, CMD)      │  │ (hot: OPEN/CLOSE)               │
│                            │  │                                  │
│  [Adapter]   [risk_mgr]    │  │  [exec_gw]                      │
│   ↓                        │  │                                  │
│  EVT:LEGACY_CALL           │  │                                  │
└────────────────────────────┘  └─────────────────────────────────┘
         ↓
WAL / Snapshot (immutable, Merkle)
```

### D2. Migration Mode Progression

```
Monolith (direct imports)
  → Shadow    (observe only)       → produces: graph.json, entropy baseline
  → Audit     (WAL)                → emits: EVT:LEGACY_CALL + why_chain
  → Adapter   (@fsm_call)          → routes: ASK/DEC via FSM
  → Hybrid    (partial FSM)        → domain-by-domain cutover
  → Pure-FSM  (legacy removed)     → full contract enforcement
```

---

## E) RFC Definitions

### RFC-001: Legacy Integration (`LEGACY_CALL`)

| Field          | Value                                                  |
| -------------- | ------------------------------------------------------ |
| **ops**        | `EVT \| ASK \| DEC \| ERR`                             |
| **modes**      | `shadow \| audit \| adapter \| hybrid \| pure_fsm`     |

**Schemas:**

- `EVT:LEGACY_CALL`: `{ func: str, args: obj, legacy_mode: enum, legacy: true }`
- `DEC:LEGACY_OK`: `{ ok: bool, result: obj|null, why, why_explain_ref }`
- `ERR:LEGACY_NON_IDEMPOTENT`: `{ code, detail, advice }`

**Routing:** `EVT:LEGACY_CALL → legacy_adapter`
**Constraints:** overhead ≤ 10 ms; WAL on; signatures required on DEC.

---

### RFC-002: Observability Diff

- `/debug/{rid}` returns **before/after diff**: FSM vs legacy path — latency, entropy-delta, centrality-delta.
- Trace tags: `legacy_span=true`, `mode=shadow|adapter|fsm`.

---

### RFC-003: DR Replay Semantics

- WAL entries contain: `rid`, `span_id`, `hash_prev`.
- Replay policy: DENY non-idempotent calls; safe replay requires idempotency verification.
- Snapshot record fields: `uri, ts, sha256, merkle_root`.

---

### RFC-004: Security Signatures

- Mandatory signatures for `CMD/*` and `DEC/*`: Ed25519/KMS.
- Signed payload: `op, verb, rid, ts, src, dst, pld_hash`.
- FSM rejects unsigned delivery.

---

## F) Delivery Schedule

| Phase                    | Duration     | Key Artifacts                                         | Exit Criteria                                               |
| ------------------------ | ------------ | ----------------------------------------------------- | ----------------------------------------------------------- |
| 1. Core FSM              | 1 sprint     | `fsm_core`, `message`, `global_dict v1`               | 10k ev/s, p95 ≤ 10 ms, contract-tests green                |
| 2. Legacy Layer          | 1–2 sprints  | `analyze`, `migrate`, adapters, RFC-001               | shadow/audit/adapter functional; overhead ≤ 10 ms          |
| 3. Domains + Meta        | 2 sprints    | domain_dicts, meta-fsm                                | all contracts verified; hybrid cutover successful           |
| 4. Observability         | 1 sprint     | entropy/topology monitors, `/debug`, RFC-002          | why ≥ 95%, trace end-to-end, diff report working           |
| 5. DR / Resilience       | 1 sprint     | WAL + snapshots, RFC-003                              | RTO ≤ 5 min, RPO ≤ 1 min, replay verified                  |
| 6. Governance / CLI      | 1 sprint     | linting, schema-budget, RFC workflow                  | 0 breaking changes without RFC; CLI coverage ≥ 95%         |
| 7. Security              | 0.5–1 sprint | signatures, redaction, RFC-004                        | 100% CMD/DEC signed; RBAC on debug endpoints               |
| 8. Validation (final)    | 2 sprints    | 2-domain / chaos / DR / perf tests                    | all 9 DoD dimensions pass                                   |

**KPI Summary:**
`p95(hot) ≤ 50 ms` · `cold-path ≤ 100 ms` · `why-coverage ≥ 95%` · `ERR:TIMEOUT ≤ 1%` · `CB-OPEN < 2%` · `RTO ≤ 5 min` · `RPO ≤ 1 min` · `CLI-coverage ≥ 95%`

---

## G) Recommended First Steps

1. Fast-track review and approval of **RFC-001..004**.
2. Run `analyze imports` to auto-generate **draft Domain Dictionaries**.
3. Deploy **Shadow → Audit** mode on the first critical flow (EVAL → OPEN).
4. Enable **Adapter mode** incrementally; measure overhead and why-coverage.
5. Activate **signatures** on DEC/CMD; plug in WAL snapshots.
6. Validate `/debug` diff and DR-replay end-to-end.

