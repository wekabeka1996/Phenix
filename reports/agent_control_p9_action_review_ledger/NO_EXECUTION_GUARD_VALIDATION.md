# No-execution guard validation

Validated failures include:

- non-null model-call reference;
- `submitted=true`;
- order id, client order id, exchange order id, fill id, or trade id keys;
- hypothetical action with a non-hypothetical execution status;
- secret-looking payload;
- malformed packet linkage;
- missing/wrong supersession;
- mutation of immutable pre-action identity.

Allowed statuses all state non-submission. Runtime execution logs had zero consequential command matches. ActionReview has no adapter, HTTP client, provider client, bus command, or execution method.
