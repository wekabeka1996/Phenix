# P46-1E Canonical Session, Participant, and Lease Authority

## FACTS

- Starting SHA: `a3f44a2e7bbdd420b914808689461e2771454f44`; local/remote matched, expected ancestor present, status clean, ahead/behind `0/0`.
- Decision: `EXISTING_AUTHORITY_REQUIRES_NARROW_ADAPTER`.
- Canonical owners: `TradingSessionAuthorityStore` owns sessions, participants, and leases in one process.
- V2 production composition now injects `CanonicalV2AuthorityProvider` and the existing `PositionQueriesSizingAdapterV2` into the existing IPC bridge.
- A valid main participant with an active lease produced exactly one `CMD:EXTERNAL_OPEN_REQUEST_V1`; tested authority failures produced zero commands.
- No Cockpit, provider, FSM execution, adapter mutation, exchange, or Testnet operation occurred.
- Final SHA and push result are recorded after report commit in the coordination report and Git history.

## INFERENCES

- The package establishes the single-process authority boundary required for a later controlled FSM runtime proof.

## ASSUMPTIONS

- Existing `PositionQueries` remains the approved Phenix sizing owner.

## UNKNOWNS

- Multiprocess/distributed authority locking and durable authority restart are outside this package.
- No canonical context-ACK provider exists; YAML explicitly marks `context_ack_policy: defer_unavailable`.

## Verdict

`P46_1E_SESSION_PARTICIPANT_LEASE_AUTHORITY_VALIDATED`
