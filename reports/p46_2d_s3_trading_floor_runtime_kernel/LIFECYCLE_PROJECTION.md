# Lifecycle Projection

## FACTS

Position, order, pending command, FSM decision, and reconciliation state exist in multiple main-process runtime objects. No single bounded read API exposes all required fields with stable source references and one data version.

No projection was added because the mandatory context/memory ownership gate failed first. Empty arrays were not fabricated as absence proof.

## INFERENCES

A future projection can be read-only over existing owners, but must explicitly mark `MISSING` or `UNKNOWN` surfaces.

## ASSUMPTIONS

Venue-confirmed state requires existing reconciliation evidence.

## UNKNOWNS

Which existing reconciliation object is intended to publish the aggregate data version.
