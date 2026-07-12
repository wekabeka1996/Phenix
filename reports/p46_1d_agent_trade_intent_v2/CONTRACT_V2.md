# Agent Trade Intent V2 Contract

## FACTS

Exact fields:

`contract_version`, `session_id`, `participant_id`, `agent_id`, `symbol`, `intent_type`, `side`, `strategy_or_reason`, `confidence`, `max_position_horizon_sec`, `context_version`, `context_ack_version`, `evidence_refs`, `subagent_acknowledgements`, `lease_reference`, `client_intent_id`, `created_at`.

Supported operation: `OPEN` only. `CLOSE`, `REDUCE`, `CANCEL`, and `AMEND` fail contract validation because their no-sizing lifecycle authority was not proven for this ingress.

Forbidden caller fields rejected through `extra="forbid"`:

`qty`, `quantity`, `notional`, `position_size`, `leverage`, `margin`, `margin_allocation`, `raw_exchange_params`, `exchange_order_id`, `precision`, `step_size`, and every unknown field.

Additional validation: timezone timestamp, alphanumeric symbol, bounded confidence, non-empty identities/references, unique refs, and context ACK not newer than observed context.

## INFERENCES

- The caller can express direction, rationale, confidence, horizon, and evidence but cannot shape an executable order.

## ASSUMPTIONS

- `client_intent_id` is the idempotency identity across HTTP, IPC, sizing, and command trace.

## UNKNOWNS

- Future close/reduce contract semantics require a separate lifecycle proof.

