# Latency profile

Ten sequential Cockpit-to-Aurora GET round trips:

- minimum: 2,064 ms;
- maximum: 2,146 ms;
- mean: 2,077.4 ms.

History writes happen on the 30-second readiness publication cadence, not per packet request. Packet requests read the atomic publication and persist validated payloads in Cockpit SQLite.
