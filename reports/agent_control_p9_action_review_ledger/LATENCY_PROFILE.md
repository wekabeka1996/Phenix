# Latency profile

Ten measured Cockpit packet round trips:

- minimum: 13 ms;
- maximum: 39 ms;
- mean: 25.9 ms.

The review ledger is a small bounded read during packet construction. `reducer_timings_ms.action_review_memory` is separately reported in packets. No model, network provider, or execution request occurs in this phase.
