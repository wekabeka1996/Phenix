# Read Model Contract

## FACTS
- Schema: `p46.read-model.v1` with strict, frozen Pydantic models.
- Common envelope includes runtime/environment/config/session/data versions, generated/source timestamps, freshness, and source references.
- Aggregate includes session, bounded participants, active/expired/released leases, context identity/items, and lifecycle/reconciliation.
- Ordering and content hash/data version are deterministic for the same inputs.
- Missing timestamp cannot produce `FRESH`.

## INFERENCES
- Stable IDs and source references permit evidence reconstruction without exposing raw memory or hidden reasoning.

## ASSUMPTIONS
- Schema changes require a new explicitly supported version.

## UNKNOWNS
- No schema evolution beyond v1 is defined.
