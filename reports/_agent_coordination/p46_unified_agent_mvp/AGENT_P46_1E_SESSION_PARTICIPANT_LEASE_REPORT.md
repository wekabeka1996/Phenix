# P46-1E Coordination Report

## FACTS

- Start: `a3f44a2e7bbdd420b914808689461e2771454f44`, clean and synchronized.
- Selection: `EXISTING_AUTHORITY_REQUIRES_NARROW_ADAPTER`.
- One single-process owner now governs TradingSession, Participant, and SymbolLease; P41 memory leases remain evidence only.
- Existing V2 IPC, PositionQueries sizing, registered command, and FSM boundary were reused.
- Proof: valid authority emits exactly one registered command; authority/sizing failures emit zero; `125 passed`; terminal regression `582 passed, 9 skipped` with explicit repo `PYTHONPATH`.
- Verdict: `P46_1E_SESSION_PARTICIPANT_LEASE_AUTHORITY_VALIDATED`.

## INFERENCES

- P46 may proceed to explicit session provisioning and controlled FSM runtime validation without adding another authority path.

## ASSUMPTIONS

- V1 compatibility is removed only in a dedicated migration.

## UNKNOWNS

- FSM/exchange/lifecycle behavior and multiprocess durability remain unproven.
