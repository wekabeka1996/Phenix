# Latency profile

Ten Cockpit-to-Aurora GET round trips:

- minimum: 2,050 ms;
- maximum: 2,134 ms;
- mean: 2,080.3 ms.

Operator-file validation runs on the periodic readiness publication owner, not per packet. Packet polling reads the atomic publication and persists the validated compact packet.
