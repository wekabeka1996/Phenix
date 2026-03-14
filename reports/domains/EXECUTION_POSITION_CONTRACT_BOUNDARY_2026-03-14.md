# Execution Position — Contract Boundary Cleanup Report

**Date:** 2026-03-14
**Package:** EP-CONTRACT-BOUNDARY
**Status:** COMPLETE

---

## 1. Executive Summary

Resolved all 3 co-emitter gaps identified in the EP domain audit and eliminated the
cross-domain NRR import coupling. All changes are minimal, safe, and backward-compatible.

**Verdict:** Contract boundaries are now explicit, documented, and enforced by 8 guardrail tests.

---

## 2. The 3 Disputed Contracts

### EVT:TRADE_INTENT_REJECTED
- **Registry owner:** decision_making
- **EP emitter:** `intent_router.py:181/202/211/234`
- **DM emitter:** `intent_emitter.py:165`, `mean_reversion_handler.py:333`, `md_amr_handler.py:599/631`
- **Semantic:** DM rejects at strategy level (safety gates, regime, etc.); EP rejects at execution boundary (exposure guard, leverage, etc.)

### EVT:EXPOSURE_SUMMARY_UPDATED
- **Registry owner was:** risk_management
- **Actual emitter:** execution_position ONLY — `event_handlers.py:134/149/659`, `exposure_manager.py:328/403`
- **Schema location:** `execution_position/schemas/exposure_summary_updated_v1.json`
- **risk_management emits this:** **NEVER** — zero emission sites found in risk_management
- **Consumers:** decision_making, strategies

### EVT:TRADE_EXECUTED
- **Registry owner:** position_tracking
- **Primary emitter:** adapter (`binance_ws_client.py:383`)
- **Fallback emitter:** EP watchdog (`watchdog.py:403`) — REST polling when WS misses fills
- **Schema location:** `position_tracking/schemas/trade_executed_v1.json`
- **PT role:** schema owner + authoritative consumer (`position_tracking.py:66`)

---

## 3. Ownership Resolution Table

| Contract | Old Owner | Actual Emitter(s) | Resolution | Risk |
|----------|-----------|-------------------|------------|------|
| EVT:TRADE_INTENT_REJECTED | decision_making | DM + EP | **KEEP_OWNER_ALLOW_COEMIT** — added `co_emitters: [execution_position]` | Low |
| EVT:EXPOSURE_SUMMARY_UPDATED | risk_management | EP only | **MOVE_OWNER** — changed to `owner: execution_position` (sole emitter + schema) | Low |
| EVT:TRADE_EXECUTED | position_tracking | adapter + EP watchdog | **KEEP_OWNER_ALLOW_COEMIT** — added `co_emitters: [adapters, execution_position]` | Low |

---

## 4. NRR Boundary Decision

**Decision: Use existing `shared/types.py` re-export facade.**

Evidence:
- `apps/reference/shared/types.py` already exists with explicit `NormalizedRejectReasons` re-export
- Convention documented in its docstring: "New shared types MUST be added here (not ad-hoc cross-domain imports)"
- `leverage_service.py` was the ONLY EP file importing directly from `decision_making`
- EP uses 5 NRR codes: NRR-020 through NRR-024 (leverage/margin verification)

Change applied:
```python
# Before:
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons

# After:
from apps.reference.shared.types import NormalizedRejectReasons
```

This eliminates the last direct EP→DM import. All cross-domain communication is now event-based or via the shared re-export facade.

---

## 5. Files Changed

| File | Action | What |
|------|--------|------|
| `apps/reference/dictionaries/verb_registry_v1.yaml` | Modified | EXPOSURE_SUMMARY_UPDATED owner → EP; added co_emitters + notes to 3 entries |
| `apps/reference/domains/execution_position/leverage_service.py` | Modified | NRR import → `shared/types` |
| `apps/reference/domains/execution_position/domain_dict.json` | Modified | Added co_emission_policy + nrr_dependency to ssot_notes |
| `apps/reference/domains/execution_position/README.md` | Modified | Added §12 Contract Boundary Policy (v1.1.0) |
| `apps/reference/domains/decision_making/domain_dict.json` | Modified | EXPOSURE_SUMMARY_UPDATED source → execution_position |
| `tests/domains/execution_position/test_ep_contract_boundary_guardrails.py` | **NEW** | 8 guardrail tests |

---

## 6. Tests Added

**File:** `tests/domains/execution_position/test_ep_contract_boundary_guardrails.py` — 8 tests

| Test Class | Count | What it guards |
|------------|-------|---------------|
| `TestExposureOwnership` | 2 | EXPOSURE_SUMMARY_UPDATED owner is EP, schema is in EP |
| `TestCoEmitterAnnotations` | 2 | TRADE_INTENT_REJECTED and TRADE_EXECUTED have co_emitters annotations |
| `TestNRRBoundary` | 2 | leverage_service uses shared/types; no direct DM imports in EP |
| `TestDomainDictBoundaryNotes` | 2 | co_emission_policy and nrr_dependency documented in domain_dict |

---

## 7. Audit Question Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Which 3 contracts? | TRADE_INTENT_REJECTED, EXPOSURE_SUMMARY_UPDATED, TRADE_EXECUTED |
| 2 | Why does EP emit each? | Intent boundary rejection, sole exposure tracking, REST polling fallback |
| 3 | Is registry owner wrong? | Yes for EXPOSURE_SUMMARY_UPDATED (was risk_management, never emits). No for the other two. |
| 4 | Classification? | EXPOSURE: misplaced ownership (fixed). TRADE_INTENT_REJECTED: valid co-emission. TRADE_EXECUTED: valid co-emission. |
| 5 | NRR boundary? | Use `shared/types.py` re-export (already exists, now applied). |

---

## 8. Risks and Recommended Next Package

### Remaining risks
- None from this package — all changes are backward-compatible metadata/import fixes

### Recommended next packages
1. **P2: Schema coverage push** — add schemas for ~20 active EP events with `schema: null`
2. **P3: Contract architecture doc update** — add co_emitters policy to `docs/contracts/CONTRACT_ARCHITECTURE.md`
3. **Domain audit: position_tracking** — next critical domain in the audit sequence
