# Contract Layer Architecture

## Purpose
This document defines the single sources of truth for all contract-layer components
in the Aurora trading system. Every contract-related addition, schema, or enumeration
must follow the rules below.

---

## 1. Contract Registry SSOT

| Aspect | Answer |
|--------|--------|
| **Canonical source** | `apps/reference/dictionaries/verb_registry_v1.yaml` |
| **What it defines** | Every active `(op, verb)` contract on the application bus |
| **Who loads it** | `VerbSchemaRegistry` in `vfoundation/core/schema_registry.py` |
| **Entry fields** | `op`, `verb`, `owner`, `status`, `schema` (path or null), `since` |
| **Valid statuses** | `active`, `experimental`, `deprecated` |
| **Valid ops** | `ASK`, `DEC`, `CMD`, `EVT`, `UPD`, `ERR` (defined in `vfoundation/core/protocol.py`) |

### Rules
1. **Every new bus event/command MUST be registered** in `verb_registry_v1.yaml` before first emit.
2. **Schema path** should point to the owning domain's `schemas/` directory when a schema exists.
3. **Owner** must be set to the domain that emits the event (not `unknown`).
4. **No duplicate `(op, verb)` pairs** — enforced by `test_contract_registry_audit.py`.
5. **Fail-closed wildcards** — `CMD`, `DEC`, `ERR` wildcards must remain `false`.

### Where NOT to register
- vfoundation-internal infrastructure events (FSM, routing, topology) operate below the application bus and are not registered here. See Section 6.

---

## 2. Schema SSOT

| Aspect | Answer |
|--------|--------|
| **Canonical location** | Domain-local `schemas/` directories |
| **Registry link** | `verb_registry_v1.yaml` → `schema:` field points to the file |
| **Format** | JSON Schema (prefer draft-07 for new schemas) |
| **Runtime loader** | `VerbSchemaRegistry.load_registry()` compiles `Draft7Validator` instances |

### Schema directory layout
```
schemas/                                          # Legacy root schemas (pre-domain era)
apps/reference/schemas/                           # App-level shared schemas
apps/reference/domains/<domain>/schemas/           # Domain-owned schemas (preferred)
```

### Rules
1. **New schemas go in the owning domain's `schemas/` directory.**
2. The `verb_registry_v1.yaml` `schema:` field is the SSOT for which schema validates which contract.
3. Schemas not referenced by the registry are either sub-schemas (internal) or orphans.
4. Do not create duplicate schemas in multiple locations.

---

## 3. WhyCode SSOT

| Aspect | Answer |
|--------|--------|
| **Canonical source** | `vfoundation/core/why_codes.py` |
| **Status** | CANONICAL — all consumers must import from here |
| **Compatibility shim** | `apps/reference/domains/decision_making/why_codes.py` re-exports from canonical |

### Rules
1. **All new WhyCode members** must be added to `vfoundation/core/why_codes.py`.
2. **Never add WhyCode members to the decision_making shim** — it is read-only re-export.
3. **NRR codes in WhyCode are DEPRECATED** — they have semantic drift vs canonical NRR. Use `NormalizedRejectReasons` for NRR codes. Do not add new NRR members to WhyCode.

---

## 4. NRR (Normalized Reject Reasons) SSOT

| Aspect | Answer |
|--------|--------|
| **Canonical source** | `apps/reference/domains/decision_making/normalized_reject_reasons.py` |
| **Re-export** | `apps/reference/shared/types.py` (identity-preserving re-export) |
| **Format** | `NRR-\d{3}` for numeric codes, `NRR-CFG-\d{3}` for config codes |

### Rules
1. **All new NRR codes** must be added to `NormalizedRejectReasons` class.
2. **Ad-hoc NRR-like codes** (e.g. `NRR-LEV-REDUCE`) violate the format contract and should be migrated to numeric codes.
3. Do not duplicate NRR codes in WhyCode or any other enum.

---

## 5. Other Sources — Classification

| Source | Location | Status | Purpose |
|--------|----------|--------|---------|
| **verb_registry_v1.yaml** | `apps/reference/dictionaries/` | **CANONICAL** | Contract registry |
| **VerbSchemaRegistry** | `vfoundation/core/schema_registry.py` | **DERIVED** | Runtime compiled cache of registry |
| **SchemaRegistry (lifecycle)** | `vfoundation/core/schema_version.py` | **INFRASTRUCTURE** | Schema lifecycle tracking utility |
| **VERB_PAYLOAD_MAP** | `vfoundation/core/payloads.py` | **COMPATIBILITY** | Typed Pydantic payloads (11 pairs). Not used in production. Domain-local models are used instead |
| **WhyCode (vfoundation)** | `vfoundation/core/why_codes.py` | **CANONICAL** | Why-chain explanation codes |
| **WhyCode (decision_making)** | `apps/reference/domains/decision_making/why_codes.py` | **COMPATIBILITY** | Re-export shim from canonical |
| **NormalizedRejectReasons** | `apps/reference/domains/decision_making/normalized_reject_reasons.py` | **CANONICAL** | NRR reject reason codes |
| **Op type** | `vfoundation/core/protocol.py` | **CANONICAL** | `Literal["ASK","DEC","CMD","EVT","UPD","ERR"]` |
| **Domain-local payload models** | Various `contracts.py` / `schemas.py` | **CANONICAL (per-domain)** | Domain-owned Pydantic models for their own events |

### Source lifecycle

```
CANONICAL ──────→ active, authoritative, all new additions go here
DERIVED ────────→ computed from CANONICAL at runtime, never edited directly
COMPATIBILITY ──→ re-export from CANONICAL, exists for backward compat only
INFRASTRUCTURE ─→ utility/tooling, not a contract source
DEPRECATED ─────→ scheduled for removal, must not be used for new code
```

---

## 6. Forbidden Patterns

1. **Do not create new WhyCode enums** in any domain. Import from `vfoundation/core/why_codes.py`.
2. **Do not add bus events without registering** in `verb_registry_v1.yaml`.
3. **Do not create NRR codes outside** `NormalizedRejectReasons`.
4. **Do not add entries to `VERB_PAYLOAD_MAP`** unless migrating to a centralized payload approach (currently frozen as compatibility-only).
5. **Do not use `vfoundation.core.why_codes.NRR_*` members** for NRR logic — use `NormalizedRejectReasons` directly.

---

## 7. Test Guardrails

| Test | File | What it guards |
|------|------|---------------|
| Registry schema integrity | `tests/contracts/test_contract_registry_audit.py` | All schema refs resolve, no dead paths |
| Registry no duplicates | same | No duplicate (op, verb) pairs |
| Fail-closed policies | same | CMD/DEC/ERR wildcards stay false |
| Core contracts registered | same | 16 runtime-critical contracts present |
| Schema-required contracts | same | Critical contracts have schemas on disk |
| WhyCode SSOT identity | `tests/contracts/test_contract_ssot_guardrails.py` | decision_making WhyCode IS vfoundation WhyCode |
| NRR SSOT identity | same | shared re-export IS canonical NRR |
| No new WhyCode sources | same | No independent WhyCode enums outside canonical |
| Config namespace SSOT | `tests/config/test_config_namespace_ssot.py` | Default config = aurora, no dead trees |

---

## 8. Migration Notes

### WhyCode (completed 2026-03-14)
- 7 codes (6 SIZING + SIGNAL_NEUTRAL) promoted from decision_making fork to vfoundation canonical
- decision_making `why_codes.py` converted to thin re-export wrapper
- `format_why_with_details` signature unified to variadic `*details: str`
- NRR codes in WhyCode marked deprecated (semantic drift vs canonical NRR)

### VERB_PAYLOAD_MAP (frozen)
- 11 typed (op,verb) → Pydantic pairs exist but are never called from production code
- Domain-local payload models (OrderPayload, CmdOpenPayload, FeaturesCalculatedPayloadV1, etc.) are the actual runtime validators
- No changes until a centralized Pydantic migration decision is made

### NRR ad-hoc codes (pending)
- binance_adapter uses non-standard codes (NRR-LEV-REDUCE, NRR-CANCEL-STRICT, etc.)
- These should be normalized to NRR-\d{3} format in a future wave
