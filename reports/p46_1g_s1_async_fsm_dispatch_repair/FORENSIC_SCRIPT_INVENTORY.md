# Forensic Script Inventory

## FACTS

| Section | Lines | Classification | Evidence |
|---|---:|---|---|
| Contract/authority/IPC harness | 82-733 | `CANONICAL_PATH_REPRODUCER` | Uses the P46 HTTP/TCP harness and registered command path. |
| Correlated counters and venue queries | 82-986 | `FORENSIC_OBSERVABILITY` | Records command/FSM/adapter and reconciliation data. |
| Direct `place_market_entry` | 734-780 | `DIRECT_ADAPTER_BYPASS` | Calls the adapter without canonical FSM dispatch. |
| Direct cancel/close | 826-866 | `DIRECT_ADAPTER_BYPASS` | Performs lifecycle writes directly through the adapter. |
| Emergency close/cancel | 898-943 | `EMERGENCY_CONTAINMENT` | Narrow proof-related containment after failure. |

- Path: `scripts/p46_1g_r_canonical_venue_proof.py`.
- Preserved SHA256: `6b5a05ec066cfd1cef3f68ba731ae8c131250fff4b82b65267f05541d5499771`.
- The original file remains untracked and byte-for-byte unmodified.

## INFERENCES

- It is useful as forensic input but cannot establish canonical lifecycle success because its normal submit path bypasses FSM dispatch.

## ASSUMPTIONS

- No external process changed the untracked script during this package.

## UNKNOWNS

- The provenance of the pre-existing untracked file before this run is not encoded in Git.
