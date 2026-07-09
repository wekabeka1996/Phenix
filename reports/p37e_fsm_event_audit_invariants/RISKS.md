# CLI Event Audit Invariant Risks

## Policy Risks
- Low. Restricting the command fields to `testnet_only=True` prevents live account interactions.

## Route Risks
- Low. Audit logs are kept inside the session context.

## What Remains Unproven
- Multi-node verification and centralized FSM state validation.
