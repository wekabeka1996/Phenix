# Failure And Restart Proof

## FACTS

Existing canonical-memory tests prove deterministic reopen/recovery within the terminal-agent runtime. They do not prove main-process ownership acquisition, duplicate process rejection, or dashboard-client continuity.

The following S3 proofs were not runnable without implementing the prohibited partial migration:

- duplicate writer blocks startup;
- main restart reconstructs the same owner generation;
- dashboard operates as a non-writer client;
- runtime generation invalidates the old handshake.

## INFERENCES

The absence of a writer lease is itself a restart/cutover blocker.

## ASSUMPTIONS

Existing JSONL artifacts must not be rewritten to test ownership.

## UNKNOWNS

Crash behavior during a future ownership handoff.
