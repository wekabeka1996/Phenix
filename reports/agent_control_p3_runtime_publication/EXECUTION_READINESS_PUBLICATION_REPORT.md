# Execution readiness publication report

The atomic readiness publication is schema-valid and consumed before in-process or disk fallback. Every invariant carries status, evidence source, source timestamp, detail, and opaque ref.

Live P3 relay result:

- source owner: `publication_relay_no_runtime`;
- `runtime_available=false`;
- mode, filters, precision/minimums, reduce-only visibility, idempotency, lifecycle reconciliation, bracket ownership, and trace identity: `missing`;
- publisher secret isolation: `ready` because secret-bearing attributes are excluded by construction.

This is partial readiness publication, not execution readiness. Direct main wiring can publish initialized ExecPos evidence after a future safe restart, but P3 did not restart the active hybrid runtime because no repository-owned disarm mode guarantees zero orders.
