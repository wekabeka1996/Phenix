# ADR-003: Message Protocol Drift (v=1 vs Constitution v=2)

**Date:** 2026-02-22  
**Status:** ACCEPTED  
**Deciders:** vFoundation team  
**Source:** Staff Architect audit (v1.3), claim #3

---

## Context

The Constitution FSM.md §5.2 defines the canonical Message envelope as:

| Field | Constitution (§5.2) | Runtime (`protocol.py`) | Drift |
|-------|---------------------|-------------------------|-------|
| `v` | `2` | `1` | **Version mismatch** |
| `data_ref` | `[{uri, sha256, bytes, ctype, ttl_ms}]` | `List[str]` | **Schema structural mismatch** |
| `sig` | mandatory for CMD/DEC (§11) | `Optional[str] = None` | Enforcement gap |

Three-phase drift:
1. **Version drift** (`v=1` vs `v=2`): No runtime impact, but makes envelope non-compliant with Constitution.
2. **data_ref schema drift**: Constitution expects a list of rich objects; runtime uses `List[str]` (URI-only).
   Consumers that parse `data_ref` fields expecting objects will fail.
3. **sig enforcement gap**: Constitution §11 mandates `sig` for CMD/DEC; runtime allows `None`.

## Decision

- Phases 9–13 do **not** change the runtime Message model (would be a breaking change to all producers/consumers).
- The drift is accepted as a **known, documented technical debt** pending Phase 14.
- Phase 14.3 will:
  1. Bump `v=1` → `v=2` in `protocol.py` (coordinated with all consumers)
  2. Migrate `data_ref: List[str]` → `data_ref: List[DataRef]` (Pydantic BaseModel)
  3. Add `sig` validator that emits `DeprecationWarning` for CMD/DEC without `sig`
  4. Provide migration guide for all adapters and FSM state machines

## Consequences

- Until Phase 14.3: the drift is known, documented, and monitored.
- New code in Phases 9–13 must use `data_ref: List[str]` (current runtime schema), not the Constitution schema.
- Logging/observability tools must not assume `data_ref` elements are dicts.
- `sig` enforcement: no new validation added until Phase 14.3.
- This ADR is linked from Constitution_FSM.md §5.2 as a footnote.

---

*See also: [Constitution_FSM.md §5.2](Constitution_FSM.md), [protocol.py](../../vfoundation/core/protocol.py)*
