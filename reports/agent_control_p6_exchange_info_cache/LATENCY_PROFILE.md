# Latency profile

- Ten Cockpit round trips: minimum 2,049 ms, maximum 2,135 ms, mean 2,073.6 ms.
- Success rate: 10/10.
- Public exchange refresh runs outside packet construction on a background owner; packet requests read the atomic readiness publication.
