# Mechanical invariants validation

`ExecutionBodyCard` reports nine invariant names: mode/testnet visibility, exchange filters, precision/minimums, reduce-only close/protect, duplicate/idempotency protection, lifecycle reconciliation, bracket ownership, trace identity, and secret isolation.

Unknown or unavailable runtime evidence is reported as `unknown`, `missing`, or `degraded`. The bridge does not reimplement, disable, or weaken execution controls. It does not read secrets; therefore secret isolation is honestly `unknown` with a note that secrets were intentionally not inspected.

Tests pass an execution object whose submit method raises if invoked. Packet production succeeds without calling it. Route inspection proves all bridge routes expose exactly GET.

Offline evidence had no importable live execution runtime: lifecycle reconciliation was degraded, bracket/filter/precision/mode states were unknown, and recent trace identity was available from the bounded decision ledger. These states are visible in the sample.
