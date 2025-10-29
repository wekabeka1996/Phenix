# Copilot Instructions — QuantumTraderX → vFoundation (FSM Federation)

**Respond to humans in Ukrainian. Generate files in English.** Work ADDITIVE-ONLY.
.venv/Scripts/Activate.ps1 all run commands.
## Big picture (read first)
- This repo migrates QuantumTraderX to a **federated FSM** on vFoundation: TRADE (hot path) + LEARN (cold).
- Central coordination = **OrchestratorFSM** (RID lifecycle, why_chain, TTL/CB/idempotency) + **MetaFSM** (registry, schema canary, freeze).
- Source of truth: `docs/ROADMAP_DELTA_EMPTY_BRANCH.md`, `docs/CENTRAL_FSM_SPEC.md` (follow their order of onboarding).

## Architecture map (where to look)
- Library: `vfoundation/` (core FSM/router/ttl/idempotency; DR: wal/merkle/snapshot/replay; obs: logging/why/tracing; security: ed25519/rbac).
- Reference app: `apps/reference/` with domains: `risk_strategy`, `execution_position`, `xai_audit`, `analyzer`, `data_monitoring`, `reward_alysha`, `rl_core`.
- Schemas & dictionaries: `dictionaries/*.yaml` → generated `schemas/*.json` (JSON Schema 2020-12, `$id` required).

## Developer workflow (do this first)
- **Contracts first** → run schema generation → then adapters/FSM.
- Commands (examples): 
  - Generate schemas: `vfound schema`
  - Run tests: `pytest -q` ; coverage target (FSM) ≥ 90%
  - Debug: FastAPI `GET /debug/{rid}`, `/metrics`, `/replay`
- Hot path SLO: **p95 ≤ 50 ms** (overall ≤ 100 ms); timeout_rate ≤ 1%; WHY-coverage ≥ 95%.

## Conventions (must follow)
- **Task tracking**: edit `TODO.md` using GitHub task lists; one atomic task per line; link PR at the end; after merge → tick and remove the line in a follow-up commit.
- **Journaling**: every action → `JOURNAL.md` entry with `RID`, short `why` (≤ 80 chars), and links to PR/artefacts.
- **Commits**: Conventional Commits (e.g., `docs(playbook): add Copilot guide [FSMP-P0]`).
- **Contracts**: JSON Schema **2020-12**, additive-only versioning. No breaking edits; use new versions.
- **Security**: sign high-risk `DEC/CMD` (OPEN/CLOSE/ADJUST) with **Ed25519**; secrets in KMS; redact sensitive fields.
- **Logs**: structured JSONL to stdout (event stream); heavy XAI to cold storage via `why_explain_ref`.

## Domain order & FSM counts (v1)
1) `execution_position` — Order/Position/Bracket (3 FSM)  
2) `risk_strategy` — Safety + Sizing (2)  
3) `analyzer` — Signal + Regime (2)  
4) `xai_audit` (1) → then `data_monitoring` (2), `reward_alysha` (1), `rl_core` (3)

## Folder-by-folder playbook
Contracts → ACL/Adapter → FSM wrapper → Shadow (dual-read, zero-write; drift < 1%) → Canary (single-writer 10–20%) → Cutover → DR replay.

> If any required doc is missing, answer `NOOP` with the missing paths and stop.
