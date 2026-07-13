# Deterministic Proof

## FACTS

- S2/S1 focused suite: `23 passed`.
- Expanded sizing/V2/authority/config suite: `93 passed`.
- P46-1F/FSM/recovery/startup/shutdown/registry suite: `100 passed, 14 skipped`.
- Terminal-agent regression: `578 passed, 13 skipped`, with three development-config warnings.
- Tests cover prior rejection, below/exact/above floor, cap, price motion, single fee application, single exposure application, stale/missing snapshots, missing config/filters, unit conversion, deterministic result, caller qty rejection, no DEC/adapter on exposure rejection, and S1 async dispatch.

## INFERENCES

- Deterministic evidence supports the corrected proof target without weakening risk policy.

## ASSUMPTIONS

- Skipped tests are not counted as proof.

## UNKNOWNS

- The previously observed broad execution-position suite-level stall was not used as proof.
