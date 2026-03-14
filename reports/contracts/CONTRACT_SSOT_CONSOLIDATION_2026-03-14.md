# Contract SSOT Consolidation Report

**Date:** 2026-03-14
**Package:** CONTRACT-SSOT-CONSOLIDATION
**Status:** COMPLETE

---

## 1. Executive Verdict

The contract layer now has an explicit, documented, and test-guarded SSOT model.
Before this package, 8+ contract-definition sources existed with overlapping scopes,
a forked WhyCode enum, and no architecture spec defining ownership. The system now
has clear answers to:

1. **Contract registry SSOT** — `verb_registry_v1.yaml` (87 active entries)
2. **Schema SSOT** — domain-local `schemas/` directories, linked via verb_registry `schema:` field
3. **WhyCode SSOT** — `vfoundation/core/why_codes.py` (72 members, unified)
4. **NRR SSOT** — `NormalizedRejectReasons` in `decision_making/normalized_reject_reasons.py`

Score: **8/10** (up from 7/10 in preceding audit). Remaining gaps are documented follow-ups.

---

## 2. Canonical Sources Chosen

| Layer | Canonical Source | Format |
|-------|-----------------|--------|
| Contract registry | `apps/reference/dictionaries/verb_registry_v1.yaml` | YAML |
| Schemas | Domain-local `schemas/` dirs, linked by registry | JSON Schema (draft-07) |
| WhyCode | `vfoundation/core/why_codes.py` | Python Enum (72 members) |
| NRR codes | `apps/reference/domains/decision_making/normalized_reject_reasons.py` | Python class (60 codes) |
| Op types | `vfoundation/core/protocol.py` | `Literal["ASK","DEC","CMD","EVT","UPD","ERR"]` |

---

## 3. All Sources — Status Classification

| Source | Location | Status | Notes |
|--------|----------|--------|-------|
| verb_registry_v1.yaml | `apps/reference/dictionaries/` | **CANONICAL** | Primary contract registry |
| VerbSchemaRegistry | `vfoundation/core/schema_registry.py` | **DERIVED** | Runtime cache compiled from registry |
| SchemaRegistry (lifecycle) | `vfoundation/core/schema_version.py` | **INFRASTRUCTURE** | Lifecycle tracking utility |
| VERB_PAYLOAD_MAP | `vfoundation/core/payloads.py` | **COMPATIBILITY** | 11 entries, frozen, not used in prod |
| WhyCode (vfoundation) | `vfoundation/core/why_codes.py` | **CANONICAL** | Unified with SIZING/SIGNAL codes |
| WhyCode (decision_making) | `apps/reference/domains/decision_making/why_codes.py` | **COMPATIBILITY** | Thin re-export from vfoundation |
| NormalizedRejectReasons | `apps/reference/domains/decision_making/normalized_reject_reasons.py` | **CANONICAL** | 60 NRR codes |
| NRR (shared re-export) | `apps/reference/shared/types.py` | **COMPATIBILITY** | Identity-preserving re-export |
| Op type | `vfoundation/core/protocol.py` | **CANONICAL** | Foundational type def |
| Domain payload models | Various `contracts.py`/`schemas.py` | **CANONICAL (per-domain)** | Runtime validators |

---

## 4. Safe Changes Applied

### 4a. WhyCode Fork Resolution
- **Promoted 7 codes** from decision_making fork to vfoundation canonical:
  - `SIZING_KELLY_FRACTION`, `SIZING_CAPPED_BY_LIQUIDITY`, `SIZING_FLOORED_BY_MIN_SIZE`
  - `SIZING_ERROR_NO_INSTRUMENT_SPECS`, `SIZING_ERROR_QTY_ZERO_AFTER_ROUNDING`, `SIZING_SUCCESS`
  - `SIGNAL_NEUTRAL`
- **Converted** `apps/reference/domains/decision_making/why_codes.py` to thin re-export
- **Marked NRR codes in WhyCode as DEPRECATED** (semantic drift vs canonical NRR)
- **Unified `format_why_with_details`** signature to variadic `*details: str`
- **Added SIZING and SIGNAL categories** to module docstring

### 4b. Registry Deprecations (12 dead entries)
Marked the following entries as `status: deprecated` with `deprecated_since: 2026-03-14`:

| Entry | Former Status | Reason |
|-------|---------------|--------|
| DEC:CANCEL | experimental | No emitter found in codebase |
| EVT:EXPIRED | experimental | No emitter found |
| EVT:FILL | experimental | No emitter found |
| EVT:MARKET_TICK_FORWARDED | active | Dead — never implemented |
| EVT:MR_SIGNAL_PRODUCED | experimental | Dead — removed with scoring refactor |
| EVT:NEOCORTEX_STATE_UPDATED | experimental | No emitter found |
| EVT:ORCHESTRATOR_ERROR | experimental | No emitter found |
| EVT:ORDER_EXECUTED | experimental | No emitter found |
| EVT:PARTIAL_FILL | experimental | No emitter found |
| EVT:REJECTED | experimental | No emitter found |
| EVT:TICK_RECEIVED | experimental | Superseded by MARKET_TICK_RECEIVED |
| EVT:VERB | experimental | Placeholder — never used |

### 4c. VERB_PAYLOAD_MAP Freeze
- Updated docstring to declare module as **COMPATIBILITY-ONLY, frozen at 11 entries**
- Added guardrail test `TestVerbPayloadMapFrozen` that fails if entry count changes

---

## 5. Architecture Spec Created

**File:** `docs/contracts/CONTRACT_ARCHITECTURE.md`

Covers:
- Contract registry SSOT (rules, where NOT to register)
- Schema SSOT (directory layout, rules)
- WhyCode SSOT (rules, re-export boundary)
- NRR SSOT (format contract, ad-hoc code problem)
- Full source classification table
- Forbidden patterns
- Test guardrail inventory
- Migration notes

---

## 6. Guardrail Tests Added

**File:** `tests/contracts/test_contract_ssot_guardrails.py` — 9 tests

| Test Class | Count | What it guards |
|------------|-------|---------------|
| `TestWhyCodeSSOT` | 4 | DM WhyCode IS vfoundation WhyCode (identity), helpers are canonical, SIZING/SIGNAL present, no local class def |
| `TestNRRSSOT` | 2 | Shared NRR re-export IS canonical, NRR codes match format |
| `TestVerbPayloadMapFrozen` | 1 | VERB_PAYLOAD_MAP stays at 11 entries |
| `TestContractRegistryOwnership` | 2 | Registry file exists, no alternative registries |

---

## 7. Test Results

```
tests/contracts/                         — 300 passed
tests/vfoundation/core/test_why_codes.py — 15 passed
tests/unit/test_nrr_mapping_catalog.py   — 5 passed
tests/config/test_config_namespace_ssot.py — 3 passed
tests/vfoundation/test_shared_types.py   — 4 passed
```

**Total: 327 passed, 0 failed**

---

## 8. Risks and Follow-Up Packages

### Low risk — in this package
- WhyCode NRR codes marked deprecated but not removed (backward compat)
- VERB_PAYLOAD_MAP frozen but not removed (backward compat)

### Follow-up packages (not in scope)

| Priority | Package | Description |
|----------|---------|-------------|
| P2 | NRR ad-hoc code migration | Normalize `NRR-LEV-REDUCE`, `NRR-CANCEL-STRICT` etc. to `NRR-\d{3}` format |
| P2 | Schema coverage push | Add schemas for ORDER_REJECTED, ORDER_PLACED, ACCOUNT_UPDATE_RECEIVED etc. |
| P3 | WhyCode import migration | Migrate all `from decision_making.why_codes` imports to `from vfoundation.core.why_codes` |
| P3 | NRR WhyCode removal | Remove 9 deprecated NRR members from vfoundation WhyCode enum |
| P3 | VERB_PAYLOAD_MAP decision | Either promote to active Pydantic migration or remove entirely |
| P3 | vfoundation events policy | Decide registration policy for internal meta-FSM events |

---

## Files Changed

| File | Action |
|------|--------|
| `vfoundation/core/why_codes.py` | Added 7 codes (SIZING, SIGNAL), marked NRR deprecated, unified format_why_with_details |
| `apps/reference/domains/decision_making/why_codes.py` | Replaced entire file with thin re-export from vfoundation |
| `vfoundation/core/payloads.py` | Updated docstring: COMPATIBILITY-ONLY, frozen |
| `apps/reference/dictionaries/verb_registry_v1.yaml` | Marked 12 dead entries as deprecated |
| `docs/contracts/CONTRACT_ARCHITECTURE.md` | **NEW** — contract-layer architecture spec |
| `tests/contracts/test_contract_ssot_guardrails.py` | **NEW** — 9 SSOT guardrail tests |
| `reports/contracts/CONTRACT_SSOT_CONSOLIDATION_2026-03-14.md` | **NEW** — this report |
