# Latency profile

P2 round trip was 2,094–2,443 ms. P3 round trip was 14–48 ms (mean 25.7 ms).

Measured P3 reducer phases, mean milliseconds:

- decision bounded tail: 5.962;
- portfolio bounded tail: 2.641;
- market publication read/projection: 0.588;
- order bounded tail: 0.394;
- positions: 0.004;
- complete card construction before serialization: 9.940.

The measured dominant reducer component is the decision tail. Approximately 15.8 ms of mean end-to-end time remains outside card construction (Cockpit proxy, validation, SQLite persistence, loopback, and serialization combined); this is an inference from subtraction, not separately instrumented spans.

P4's narrow optimization candidate is a compact atomic recent-decision publication/read model. Do not optimize UI polling or add caching until that tail is measured independently.
