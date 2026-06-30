# Capability descriptor design

`ExecutionCapabilityDescriptorV0` fields:

- `name`, optional `symbol`;
- `status`: ready/degraded/missing/unknown;
- `evidence_level`: runtime_owner/configured_only/exchange_confirmed/unavailable;
- `owner`, `source_ts_ms`, `detail`;
- compact `constraints`, `raw_ref`, and `missing_reason`.

`SymbolConstraintSummaryV0` carries only requested symbol precision/minimum values and explicit missing fields. `ExecutionReadinessSummaryV0` counts descriptor statuses and deduplicates reasons.

Classification rules:

- fresh live filter with complete values: ready/exchange_confirmed;
- stale/runtime cache: degraded/runtime_owner;
- typed instrument values only: degraded/configured_only;
- absent symbol: missing/unavailable;
- local deterministic normalizer with complete loaded constraints: ready/runtime_owner;
- explicit reduce-only contract/owner method: ready/runtime_owner, while exchange acceptance remains false.

The builder never reads adapter credentials, refreshes filters, or calls order/close/protect methods.
