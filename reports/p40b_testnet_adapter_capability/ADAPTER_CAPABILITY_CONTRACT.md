# P40B Adapter Capability Contract

## FACTS
- `AdapterCapability` is the explicit pre-submit capability descriptor for agent testnet handoff.
- Required fields: `adapter_id`, `environment`, `order_submit_enabled`, `no_order_observation_mode`, `supports_cancel`, `supports_close`, `source_of_truth`, `checked_at`.
- Allowed environments are `testnet`, `sandbox`, `mainnet`, and `unknown`; only `testnet` and `sandbox` can pass pre-submit validation.
- Missing descriptors fail closed before any exchange submit transition.
- `no_order_observation_mode=True` fails closed before any exchange submit transition.
- `order_submit_enabled=False` fails closed before any exchange submit transition.
- URL strings are secondary safety checks only; a testnet-looking URL without a descriptor is rejected.
- Audit rejection records preserve `agent_id`, `agent_number`, `session_id`, `command_id`, `event_id`, `rationale`, reason, and timestamp.

## INFERENCES
- This replaces URL-string confidence with Pydantic descriptor validation at the FSM handoff safety boundary.
- The existing compatibility alias `AdapterCapabilityDescriptor = AdapterCapability` keeps older imports callable while exposing the P40B model name.

## ASSUMPTIONS
- `source_of_truth` should point to the runtime/config descriptor provider used by a later execution adapter integration step.
- `checked_at` is supplied by the adapter capability producer rather than inferred from URL parsing.

## UNKNOWNS
- No external testnet exchange ACK or fill was attempted or proven by P40B.
- No live adapter descriptor producer was wired in this task; this task hardens and validates the guard contract.
