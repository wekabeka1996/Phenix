# Parity acknowledgement model design

`FilterParityAcknowledgementV0` stores symbol, venue/environment, parity/severity, first/last seen, four configured and exchange values, field differences, compatibility, acknowledgement state/time/note, review/block flags, and opaque refs.

State identity is SHA-256 over canonical configured ref, exchange ref, and parity status. The optional `filter_parity_operator_acknowledgements_v0.json` file is read-only input and applies only when symbol, venue, environment, and `state_ref` all match. Status compatibility is enforced: `acknowledged_conservative` cannot apply to risky/stale/missing state, and stale/missing only retain explicit non-acceptance (`rejected`/`expired`). Missing, malformed, oversized, stale-state, or incompatible records produce `unacknowledged`; they never fail open.

Classification:

- exact values: `match/info/exact_match/not_required`;
- stricter compatible configuration: `conservative_mismatch/warning/compatible_conservative/unacknowledged`;
- looser or grid-incompatible configuration: `risky_mismatch/critical/incompatible_or_looser/unacknowledged`, YAML review and pre-authority execution block required;
- stale/missing: unavailable and unacknowledged, with pre-authority execution block required.

No model method writes YAML, changes filters, accesses credentials, or calls an exchange/execution adapter.
