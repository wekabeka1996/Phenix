# Structured Response Schema

Allowed `action` values:

`WAIT`, `SKIP`, `PUBLISH_OBSERVATION`, `PUBLISH_RISK_WARNING`, `REQUEST_ORDER`, `REQUEST_CANCEL`, `REQUEST_CLOSE`, `REQUEST_REVIEW`, `EMIT_SOS`.

Required response metadata:

`agent_id`, `session_id`, `turn_id`, `based_on_collective_version`, `instruction_version`, `owned_symbol`, `rationale_summary`, `requested_tool`, `confidence`, `created_at`.

The action/tool mapping is explicit: `WAIT`/`SKIP` use `none`; every publication/request/SOS action uses its matching registered tool. Confidence is `0..1`; rationale is bounded; payload rejects secret, signature, raw exchange, shell, filesystem, and git fields. Response validation rejects wrong symbol, stale versions, identity mismatch, duplicate CLI response IDs, malformed JSON, and unauthorized tools.

Provider/process failures are still structured `REQUEST_REVIEW` responses with `confidence: 0`, explicit `error_code`, and `provider_state` such as `PROVIDER_FAILURE`, `INVALID_RESPONSE`, `CLI_FAILURE`, or `CANCELLED`.

