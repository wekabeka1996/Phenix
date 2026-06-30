# Latency profile

P2 round trip was 2,094-2,443 ms. P3 relay was 14-48 ms, mean 25.7 ms. P4 direct main was 9-40 ms, mean 19 ms.

P4 reducer phase means:

- decision/direct-publication check: 0.767 ms;
- order warning tail: 0.796 ms;
- portfolio tail: 3.040 ms;
- positions: 0.004 ms;
- market projection: 0.178 ms;
- complete card construction: 5.227 ms.

The single narrow optimization skips the bounded decision-ledger read only when all requested `(symbol, timeframe)` rows are current direct-main publications. Advisory warning visibility remains through the bounded order-log tail. Decision phase fell about 87% from P3's 5.962 ms.
