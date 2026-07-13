# Context Publication

## FACTS

The canonical memory store can deterministically summarize record IDs, instruction versions, event IDs, command IDs, and source references. It does not currently publish the required immutable Trading Floor context projection from main.

No main production constructor owns both the writer and the context manifest. Missing context therefore remains typed unavailable under S1/S2 contracts.

## INFERENCES

Generating a context version from dashboard files inside main would be cross-process file authority and would not solve ownership.

## ASSUMPTIONS

Context version changes must originate through canonical append operations.

## UNKNOWNS

Approved critical/unresolved item taxonomy for the future bounded projection.
