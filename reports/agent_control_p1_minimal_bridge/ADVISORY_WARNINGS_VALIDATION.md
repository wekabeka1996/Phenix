# Advisory warnings validation

`BusinessWarningsCard.policy` is fixed to `advisory_only`. Recent bounded order-log block/reject events become `would_block`; readiness absence becomes `warning`. The exporter does not call, toggle, or enforce any gate.

Observed sanitized examples include `REGIME_GATE_BLOCKED` and `READINESS_DATA_MISSING`. Other runtime reason codes may be surfaced verbatim as compact codes/messages, capped at 24 entries and deduplicated by code and symbol.

Validation proves warning data is structurally separate from execution invariants and that missing market truth creates a visible readiness warning. It does not prove semantic completeness for every historical gate family; absent bounded evidence remains absent rather than inferred.
