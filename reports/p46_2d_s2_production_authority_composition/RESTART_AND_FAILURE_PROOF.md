# Restart and Failure Proof

## Proven by S1

- disconnect and timeout are typed;
- response correlation is strict;
- runtime-generation change invalidates the client generation;
- duplicate request ID is idempotent and conflicting reuse fails closed.

## Not Proven in S2

- production main restart with live canonical context/lifecycle stores;
- FastAPI reconnect followed by current production authority read;
- Cockpit approval invalidation after canonical context mutation.

No cached accepted production result exists because production composition remains unavailable.
